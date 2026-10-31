# MIT License - Copyright (c) 2026 eripum9

"""Fail-closed TCP listener identity discovery; callers decide whether to trust it.

Only the requested listener PIDs are opened. Handles remain held across the
second IPv4/IPv6 snapshot and a nonblocking liveness check. This is a bounded
observation, not an atomic guarantee about a subsequent network connection.
"""

import ctypes
import ntpath
import os
import socket
import time


_DWORD = ctypes.c_uint32
_BOOL = ctypes.c_int32
_HANDLE = ctypes.c_void_p
_AF_INET = 2
_AF_INET6 = 23
_TCP_TABLE_OWNER_PID_LISTENER = 3
_MIB_TCP_STATE_LISTEN = 2
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_SYNCHRONIZE = 0x00100000
_LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_PARAMETER = 87
_ERROR_INSUFFICIENT_BUFFER = 122
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_WAIT_FAILED = 0xFFFFFFFF
_MAX_TABLE_CALLS = 4
_MAX_TABLE_BYTES = 16 * 1024 * 1024
_MAX_TABLE_ROWS = 131072
_MAX_OWNERS = 128
_MAX_IMAGE_CHARS = 32768


class _MibTcpRowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("dwState", _DWORD),
        ("dwLocalAddr", _DWORD),
        ("dwLocalPort", _DWORD),
        ("dwRemoteAddr", _DWORD),
        ("dwRemotePort", _DWORD),
        ("dwOwningPid", _DWORD),
    ]


class _MibTcp6RowOwnerPid(ctypes.Structure):
    _fields_ = [
        ("ucLocalAddr", ctypes.c_ubyte * 16),
        ("dwLocalScopeId", _DWORD),
        ("dwLocalPort", _DWORD),
        ("ucRemoteAddr", ctypes.c_ubyte * 16),
        ("dwRemoteScopeId", _DWORD),
        ("dwRemotePort", _DWORD),
        ("dwState", _DWORD),
        ("dwOwningPid", _DWORD),
    ]


class _DiscoveryFailure(Exception):
    def __init__(self, status, error, code=None):
        self.status = status
        self.error = error
        self.code = code
        super().__init__(error)


def _api_failure(error, code):
    status = "access_denied" if code == _ERROR_ACCESS_DENIED else "api_error"
    return _DiscoveryFailure(status, error, code)


class _Win32Backend:
    """Lazy bindings: importing this module never loads a Windows DLL."""

    def __init__(self):
        if os.name != "nt":
            raise _DiscoveryFailure("api_error", "windows_required", 50)
        self._iphlpapi = ctypes.WinDLL(
            "iphlpapi.dll", use_last_error=True,
            winmode=_LOAD_LIBRARY_SEARCH_SYSTEM32,
        )
        self._kernel32 = ctypes.WinDLL(
            "kernel32.dll", use_last_error=True,
            winmode=_LOAD_LIBRARY_SEARCH_SYSTEM32,
        )
        self.GetExtendedTcpTable = self._iphlpapi.GetExtendedTcpTable
        self.GetExtendedTcpTable.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_DWORD), _BOOL,
            _DWORD, ctypes.c_int32, _DWORD,
        ]
        self.GetExtendedTcpTable.restype = _DWORD
        self.OpenProcess = self._kernel32.OpenProcess
        self.OpenProcess.argtypes = [_DWORD, _BOOL, _DWORD]
        self.OpenProcess.restype = _HANDLE
        self.QueryFullProcessImageNameW = self._kernel32.QueryFullProcessImageNameW
        self.QueryFullProcessImageNameW.argtypes = [
            _HANDLE, _DWORD, ctypes.POINTER(ctypes.c_wchar), ctypes.POINTER(_DWORD),
        ]
        self.QueryFullProcessImageNameW.restype = _BOOL
        self.WaitForSingleObject = self._kernel32.WaitForSingleObject
        self.WaitForSingleObject.argtypes = [_HANDLE, _DWORD]
        self.WaitForSingleObject.restype = _DWORD
        self.CloseHandle = self._kernel32.CloseHandle
        self.CloseHandle.argtypes = [_HANDLE]
        self.CloseHandle.restype = _BOOL

    @staticmethod
    def last_error():
        return ctypes.get_last_error()


def _table_pids(api, family, port):
    row_type = _MibTcpRowOwnerPid if family == _AF_INET else _MibTcp6RowOwnerPid
    row_size = ctypes.sizeof(row_type)
    capacity = 0
    for _ in range(_MAX_TABLE_CALLS):
        buffer = ctypes.create_string_buffer(capacity) if capacity else None
        size = _DWORD(capacity)
        code = api.GetExtendedTcpTable(
            buffer, ctypes.byref(size), False, family,
            _TCP_TABLE_OWNER_PID_LISTENER, 0,
        )
        if code == _ERROR_INSUFFICIENT_BUFFER:
            required = size.value
            if required < 4 or required > _MAX_TABLE_BYTES or required <= capacity:
                raise _DiscoveryFailure("api_error", "invalid_tcp_buffer_size", code)
            capacity = required
            continue
        if code:
            raise _api_failure("tcp_table_failed", code)
        if buffer is None or size.value < 4 or size.value > capacity:
            raise _DiscoveryFailure("api_error", "invalid_tcp_table_size")

        count = _DWORD.from_buffer_copy(buffer).value
        if count > _MAX_TABLE_ROWS or count > (size.value - 4) // row_size:
            raise _DiscoveryFailure("api_error", "invalid_tcp_row_count")
        pids = set()
        for index in range(count):
            row = row_type.from_buffer_copy(buffer, 4 + index * row_size)
            if socket.ntohs(row.dwLocalPort & 0xFFFF) == port:
                if not row.dwOwningPid:
                    raise _DiscoveryFailure("identity_unavailable", "invalid_listener_pid")
                pids.add(row.dwOwningPid)
                if len(pids) > _MAX_OWNERS:
                    raise _DiscoveryFailure("api_error", "too_many_listener_owners")
        return pids
    raise _DiscoveryFailure(
        "api_error", "tcp_buffer_retry_limit", _ERROR_INSUFFICIENT_BUFFER,
    )


def _listener_pids(api, port):
    pids = _table_pids(api, _AF_INET, port) | _table_pids(api, _AF_INET6, port)
    if len(pids) > _MAX_OWNERS:
        raise _DiscoveryFailure("api_error", "too_many_listener_owners")
    return pids


def _image_path(api, handle):
    buffer = ctypes.create_unicode_buffer(_MAX_IMAGE_CHARS)
    size = _DWORD(len(buffer))
    if not api.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
        raise _api_failure("query_image_failed", api.last_error())
    if not 0 < size.value < len(buffer):
        raise _DiscoveryFailure("identity_unavailable", "invalid_image_length")
    path = buffer[:size.value]
    drive, tail = ntpath.splitdrive(path)
    if (not drive or not tail.startswith("\\") or not ntpath.basename(path)
            or any(ord(char) < 32 for char in path)):
        raise _DiscoveryFailure("identity_unavailable", "invalid_image_path")
    return path


def _check_alive(api, handle):
    state = api.WaitForSingleObject(handle, 0)
    if state == _WAIT_OBJECT_0:
        raise _DiscoveryFailure("listener_changed", "listener_process_exited")
    if state == _WAIT_FAILED:
        raise _api_failure("process_wait_failed", api.last_error())
    if state != _WAIT_TIMEOUT:
        raise _DiscoveryFailure("api_error", "invalid_process_wait_result")


def query_listener_owners(port):
    """Return exact-PID image entries, or empty entries and bounded diagnostics.

    Diagnostics contain only fixed labels and numeric error codes, never paths
    or exception text. No result is cached and no identity is authorized here.
    Native calls, allocations, rows and handles are bounded; Windows API calls
    themselves do not provide a hard wall-clock deadline.
    """
    started = time.perf_counter()
    stage = "validate_port"
    entries = []
    handles = []
    failure = None
    status = "success"
    api = None
    try:
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise _DiscoveryFailure("api_error", "invalid_port", _ERROR_INVALID_PARAMETER)
        stage = "load_backend"
        api = _Win32Backend()
        stage = "tcp_snapshot"
        pids = _listener_pids(api, port)
        if not pids:
            status = "no_listener"
        else:
            for pid in sorted(pids):
                stage = "open_process"
                handle = api.OpenProcess(
                    _PROCESS_QUERY_LIMITED_INFORMATION | _SYNCHRONIZE, False, pid,
                )
                if not handle:
                    code = api.last_error()
                    if code == _ERROR_INVALID_PARAMETER:
                        raise _DiscoveryFailure("listener_changed", "listener_pid_unavailable", code)
                    raise _api_failure("open_process_failed", code)
                handles.append(handle)
                stage = "query_image"
                path = _image_path(api, handle)
                entries.append({"Pid": pid, "Pids": [pid],
                                "Names": [ntpath.basename(path)], "Paths": [path]})
            stage = "tcp_recheck"
            if _listener_pids(api, port) != pids:
                raise _DiscoveryFailure("listener_changed", "listener_owners_changed")
            stage = "process_liveness"
            for handle in handles:
                _check_alive(api, handle)
        stage = "complete"
    except _DiscoveryFailure as exc:
        failure = exc
    except OSError as exc:
        failure = _api_failure("native_api_exception", getattr(exc, "winerror", None))
    except Exception:
        failure = _DiscoveryFailure("api_error", "unexpected_backend_error")
    finally:
        for handle in reversed(handles):
            try:
                if not api.CloseHandle(handle) and failure is None:
                    failure = _api_failure("close_handle_failed", api.last_error())
                    stage = "close_handle"
            except Exception:
                if failure is None:
                    failure = _DiscoveryFailure("api_error", "close_handle_exception")
                    stage = "close_handle"

    result = {
        "entries": entries if failure is None else [],
        "status": failure.status if failure else status,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "backend": "win32",
        "stage": stage,
        "error": failure.error if failure else "",
    }
    if failure is not None and failure.code is not None:
        result["windows_error_code"] = int(failure.code)
    return result
