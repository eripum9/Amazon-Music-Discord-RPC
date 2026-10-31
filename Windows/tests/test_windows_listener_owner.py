# MIT License - Copyright (c) 2026 eripum9

import ctypes
import os
import runpy
import socket
import struct
import sys
from types import SimpleNamespace

import pytest

import windows_listener_owner as owner


PORT = 9222
PATH = r"C:\Program Files\Amazon Music\Amazon Music.exe"


def _row4(pid=11, port=PORT, state=2, upper=0):
    return struct.pack("<6I", state, 0, socket.htons(port) | upper, 0, 0, pid)


def _row6(pid=11, port=PORT, state=2, upper=0):
    return struct.pack(
        "<16sII16sIIII", bytes(16), 0, socket.htons(port) | upper,
        bytes(16), 0, 0, state, pid,
    )


def _table(*rows):
    return struct.pack("<I", len(rows)) + b"".join(rows)


def _size(pointer):
    return ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32)).contents


class FakeBackend:
    """Exercise the real allocation/parser/orchestration code via native-shaped calls."""

    def __init__(self, ipv4=None, ipv6=None):
        self.tables = {2: ipv4 or [_table(_row4())], 23: ipv6 or [_table()]}
        self.reads = {2: 0, 23: 0}
        self.calls = []
        self.opened = []
        self.closed = []
        self.queried = []
        self.waited = []
        self.paths = {}
        self.open_errors = {}
        self.image_error = None
        self.wait_state = owner._WAIT_TIMEOUT
        self.wait_error = 6
        self.close_errors = {}
        self.error = 0
        self.image_length = None

    def last_error(self):
        return self.error

    def GetExtendedTcpTable(self, buffer, size, ordered, family, table_class, reserved):
        assert ordered is False
        assert table_class == 3
        assert reserved == 0
        self.calls.append((family, _size(size).value))
        values = self.tables[family]
        value = values[min(self.reads[family], len(values) - 1)]
        if isinstance(value, int):
            return value
        if buffer is None or _size(size).value < len(value):
            _size(size).value = len(value)
            return 122
        ctypes.memmove(buffer, value, len(value))
        _size(size).value = len(value)
        self.reads[family] += 1
        return 0

    def OpenProcess(self, access, inherit, pid):
        assert access == 0x1000 | 0x00100000
        assert inherit is False
        if pid in self.open_errors:
            self.error = self.open_errors[pid]
            return None
        handle = (1 << 40) + pid
        self.opened.append(handle)
        return handle

    def QueryFullProcessImageNameW(self, handle, flags, buffer, size):
        assert flags == 0
        assert _size(size).value == len(buffer) == owner._MAX_IMAGE_CHARS
        self.queried.append(handle)
        if self.image_error is not None:
            self.error = self.image_error
            return 0
        path = self.paths.get(handle - (1 << 40), PATH)
        buffer.value = path
        _size(size).value = len(path) if self.image_length is None else self.image_length
        return 1

    def WaitForSingleObject(self, handle, timeout):
        assert timeout == 0
        # Every successful process has remained open throughout both snapshots.
        assert self.reads == {2: 2, 23: 2}
        assert not self.closed
        self.waited.append(handle)
        self.error = self.wait_error
        return self.wait_state

    def CloseHandle(self, handle):
        self.closed.append(handle)
        self.error = self.close_errors.get(handle, 0)
        return not self.error


@pytest.fixture
def api(monkeypatch):
    backend = FakeBackend()
    monkeypatch.setattr(owner, "_Win32Backend", lambda: backend)
    return backend


def _assert_failure(result, status, stage=None, code=None):
    assert result["entries"] == []
    assert result["status"] == status
    assert result["backend"] == "win32"
    assert 0 <= result["duration_ms"]
    assert len(result["error"]) < 80
    assert "C:" not in result["error"]
    if stage is not None:
        assert result["stage"] == stage
    if code is not None:
        assert result["windows_error_code"] == code


def test_layouts_are_fixed_width_and_match_native_offsets():
    assert ctypes.sizeof(owner._MibTcpRowOwnerPid) == 24
    assert ctypes.sizeof(owner._MibTcp6RowOwnerPid) == 56
    assert owner._MibTcpRowOwnerPid.dwLocalPort.offset == 8
    assert owner._MibTcpRowOwnerPid.dwOwningPid.offset == 20
    assert owner._MibTcp6RowOwnerPid.dwLocalPort.offset == 20
    assert owner._MibTcp6RowOwnerPid.dwState.offset == 48
    assert owner._MibTcp6RowOwnerPid.dwOwningPid.offset == 52


def test_dual_stack_port_order_dedup_and_multiple_owners(api):
    api.tables = {
        2: [_table(_row4(11, upper=0xABCD0000), _row4(11),
                   _row4(99, port=PORT + 1), _row4(98, port=PORT + 2, state=5))],
        23: [_table(_row6(22, upper=0xDEAD0000), _row6(11),
                    _row6(97, port=PORT + 1), _row6(96, port=PORT + 2, state=5))],
    }
    api.paths[22] = r"D:\Other\other.exe"
    result = owner.query_listener_owners(PORT)
    assert result["status"] == "success"
    assert result["entries"] == [
        {"Pid": 11, "Pids": [11], "Names": ["Amazon Music.exe"], "Paths": [PATH]},
        {"Pid": 22, "Pids": [22], "Names": ["other.exe"], "Paths": [api.paths[22]]},
    ]
    assert len(api.opened) == len(api.queried) == len(api.waited) == 2
    assert api.closed == list(reversed(api.opened))
    assert result["stage"] == "complete"
    assert result["error"] == ""


def test_ipv6_only_listener_is_discovered(api):
    api.tables = {2: [_table()], 23: [_table(_row6())]}
    assert owner.query_listener_owners(PORT)["entries"][0]["Pid"] == 11


def test_no_listener_requires_both_tables_and_opens_nothing(api):
    api.tables = {2: [_table(_row4(port=PORT + 1))], 23: [_table()]}
    result = owner.query_listener_owners(PORT)
    assert result["status"] == "no_listener"
    assert result["entries"] == []
    assert api.reads == {2: 1, 23: 1}
    assert api.opened == []


@pytest.mark.parametrize("family", [2, 23])
def test_either_address_family_failure_is_fail_closed(api, family):
    api.tables[family] = [5]
    _assert_failure(owner.query_listener_owners(PORT), "access_denied", "tcp_snapshot", 5)
    assert api.opened == []


def test_table_buffer_can_grow_between_probe_and_read(api, monkeypatch):
    original = api.GetExtendedTcpTable
    calls = 0

    def growing(buffer, size, ordered, family, table_class, reserved):
        nonlocal calls
        if family == 2:
            calls += 1
            if calls < 3:
                _size(size).value = 28 if calls == 1 else 52
                return 122
        return original(buffer, size, ordered, family, table_class, reserved)

    monkeypatch.setattr(api, "GetExtendedTcpTable", growing)
    assert owner.query_listener_owners(PORT)["status"] == "success"
    assert calls == 5  # Three initial calls, then probe + read for recheck.


@pytest.mark.parametrize("required", [0, 3, owner._MAX_TABLE_BYTES + 1])
def test_invalid_or_oversized_buffer_requests_fail_without_allocating(api, monkeypatch, required):
    def invalid_size(buffer, size, *args):
        assert buffer is None
        _size(size).value = required
        return 122

    monkeypatch.setattr(api, "GetExtendedTcpTable", invalid_size)
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_snapshot", 122)


def test_buffer_growth_retries_are_bounded(api, monkeypatch):
    calls = 0

    def growing(buffer, size, *args):
        nonlocal calls
        calls += 1
        _size(size).value += 28
        return 122

    monkeypatch.setattr(api, "GetExtendedTcpTable", growing)
    result = owner.query_listener_owners(PORT)
    _assert_failure(result, "api_error", "tcp_snapshot", 122)
    assert result["error"] == "tcp_buffer_retry_limit"
    assert calls == owner._MAX_TABLE_CALLS


def test_non_growing_insufficient_buffer_is_rejected(api, monkeypatch):
    def stagnant(buffer, size, *args):
        _size(size).value = 28
        return 122

    monkeypatch.setattr(api, "GetExtendedTcpTable", stagnant)
    result = owner.query_listener_owners(PORT)
    _assert_failure(result, "api_error", "tcp_snapshot", 122)
    assert result["error"] == "invalid_tcp_buffer_size"


@pytest.mark.parametrize("payload", [
    b"\x00", struct.pack("<I", 1),
    struct.pack("<I", 2) + _row4(), struct.pack("<I", 0xFFFFFFFF) + _row4(),
])
def test_malformed_or_truncated_tables_fail_closed(api, payload):
    api.tables[2] = [payload]
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_snapshot")
    assert api.opened == []


def test_row_count_limit_even_when_buffer_is_large_enough(api, monkeypatch):
    monkeypatch.setattr(owner, "_MAX_TABLE_ROWS", 1)
    api.tables[2] = [_table(_row4(), _row4())]
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_snapshot")


@pytest.mark.parametrize("reported", [0, 3, 1000])
def test_invalid_success_buffer_size_is_rejected(api, monkeypatch, reported):
    original = api.GetExtendedTcpTable

    def corrupt(buffer, size, *args):
        code = original(buffer, size, *args)
        if code == 0:
            _size(size).value = reported
        return code

    monkeypatch.setattr(api, "GetExtendedTcpTable", corrupt)
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_snapshot")


def test_success_with_null_probe_is_not_accepted(api, monkeypatch):
    monkeypatch.setattr(api, "GetExtendedTcpTable", lambda *args: 0)
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_snapshot")


def test_zero_listener_pid_is_not_an_identity(api):
    api.tables[2] = [_table(_row4(0))]
    _assert_failure(owner.query_listener_owners(PORT), "identity_unavailable")


@pytest.mark.parametrize("split_families", [False, True])
def test_owner_limit_is_bounded_including_across_families(api, monkeypatch, split_families):
    monkeypatch.setattr(owner, "_MAX_OWNERS", 1)
    api.tables[2] = [_table(_row4(11)) if split_families else _table(_row4(11), _row4(22))]
    if split_families:
        api.tables[23] = [_table(_row6(22))]
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_snapshot")
    assert api.opened == []


@pytest.mark.parametrize("code,status", [(5, "access_denied"), (87, "listener_changed"), (6, "api_error")])
def test_open_failure_closes_all_previously_opened_handles(api, code, status):
    api.tables[2] = [_table(_row4(11), _row4(22))]
    api.open_errors[22] = code
    _assert_failure(owner.query_listener_owners(PORT), status, "open_process", code)
    assert api.closed == api.opened
    assert len(api.closed) == 1


@pytest.mark.parametrize("code,status", [(5, "access_denied"), (122, "api_error"), (6, "api_error")])
def test_image_query_failure_closes_handle_and_preserves_numeric_code(api, code, status):
    api.image_error = code
    _assert_failure(owner.query_listener_owners(PORT), status, "query_image", code)
    assert api.closed == api.opened


@pytest.mark.parametrize("path", ["", "relative.exe", r"C:relative.exe", r"\rooted.exe", "C:\\bad\x00name.exe", "C:\\bad\nname.exe", "C:\\"])
def test_unavailable_or_nonabsolute_image_is_rejected(api, path):
    api.paths[11] = path
    _assert_failure(owner.query_listener_owners(PORT), "identity_unavailable", "query_image")
    assert api.closed == api.opened


@pytest.mark.parametrize("length", [0, owner._MAX_IMAGE_CHARS, owner._MAX_IMAGE_CHARS + 1])
def test_invalid_image_length_is_rejected(api, length):
    api.image_length = length
    _assert_failure(owner.query_listener_owners(PORT), "identity_unavailable", "query_image")
    assert api.closed == api.opened


@pytest.mark.parametrize("replacement", [_table(), _table(_row4(22)), _table(_row4(11), _row4(22))])
def test_owner_set_change_or_disappearance_invalidates_all_entries(api, replacement):
    api.tables[2].append(replacement)
    _assert_failure(owner.query_listener_owners(PORT), "listener_changed", "tcp_recheck")
    assert api.closed == api.opened
    assert api.waited == []


def test_recheck_family_failure_discards_resolved_identity(api):
    api.tables[23] = [_table(), 50]
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "tcp_recheck", 50)
    assert api.closed == api.opened


def test_exited_process_with_same_pid_still_in_snapshot_is_rejected(api):
    api.wait_state = owner._WAIT_OBJECT_0
    _assert_failure(owner.query_listener_owners(PORT), "listener_changed", "process_liveness")
    assert api.closed == api.opened


def test_second_owner_exit_discards_every_identity_and_closes_every_handle(api, monkeypatch):
    api.tables[2] = [_table(_row4(11), _row4(22))]
    original = api.WaitForSingleObject

    def wait(handle, timeout):
        original(handle, timeout)
        return owner._WAIT_OBJECT_0 if handle == (1 << 40) + 22 else owner._WAIT_TIMEOUT

    monkeypatch.setattr(api, "WaitForSingleObject", wait)
    _assert_failure(owner.query_listener_owners(PORT), "listener_changed", "process_liveness")
    assert len(api.waited) == 2
    assert api.closed == list(reversed(api.opened))


def test_ipv6_owner_change_is_detected_during_recheck(api):
    api.tables[23] = [_table(), _table(_row6(22))]
    _assert_failure(owner.query_listener_owners(PORT), "listener_changed", "tcp_recheck")
    assert api.closed == api.opened


@pytest.mark.parametrize("state,code", [(owner._WAIT_FAILED, 6), (12345, None)])
def test_liveness_api_failure_invalidates_all_entries(api, state, code):
    api.wait_state = state
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "process_liveness", code)
    assert api.closed == api.opened


def test_close_failure_attempts_every_handle_and_invalidates_success(api):
    api.tables[2] = [_table(_row4(11), _row4(22))]
    api.close_errors[(1 << 40) + 22] = 6
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "close_handle", 6)
    assert api.closed == list(reversed(api.opened))


def test_exceptions_do_not_leak_paths_or_skip_cleanup(api, monkeypatch):
    def fail(*args):
        raise RuntimeError(r"secret path C:\private\image.exe")

    monkeypatch.setattr(api, "QueryFullProcessImageNameW", fail)
    result = owner.query_listener_owners(PORT)
    _assert_failure(result, "api_error", "query_image")
    assert "secret" not in repr(result)
    assert api.closed == api.opened


def test_cleanup_exception_does_not_skip_other_handles(api, monkeypatch):
    api.tables[2] = [_table(_row4(11), _row4(22))]
    original = api.CloseHandle

    def close(handle):
        original(handle)
        if handle == (1 << 40) + 22:
            raise RuntimeError("close failure")
        return True

    monkeypatch.setattr(api, "CloseHandle", close)
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "close_handle")
    assert api.closed == list(reversed(api.opened))


@pytest.mark.parametrize("port", [True, False, None, "9222", 0, -1, 65536, 1.5])
def test_invalid_port_is_rejected_before_loading_backend(monkeypatch, port):
    def forbidden():
        pytest.fail("backend must not load for invalid input")

    monkeypatch.setattr(owner, "_Win32Backend", forbidden)
    _assert_failure(owner.query_listener_owners(port), "api_error", "validate_port", 87)


def test_load_failure_returns_only_sanitized_diagnostic(monkeypatch):
    def fail():
        exc = OSError("secret DLL path")
        exc.winerror = 126
        raise exc

    monkeypatch.setattr(owner, "_Win32Backend", fail)
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "load_backend", 126)


def test_nonwindows_backend_does_not_try_loading_dll(monkeypatch):
    monkeypatch.setattr(owner, "os", SimpleNamespace(name="posix"))
    _assert_failure(owner.query_listener_owners(PORT), "api_error", "load_backend", 50)


def test_import_never_loads_a_windows_dll(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("import must not load DLLs")

    monkeypatch.setattr(ctypes, "WinDLL", forbidden, raising=False)
    runpy.run_path(owner.__file__)


def test_dll_loading_is_system32_only_and_signatures_use_pointer_sized_handles(monkeypatch):
    loads = []

    class Function:
        pass

    def load(name, **kwargs):
        loads.append((name, kwargs))
        return SimpleNamespace(**{function: Function() for function in (
            "GetExtendedTcpTable", "OpenProcess", "QueryFullProcessImageNameW",
            "WaitForSingleObject", "CloseHandle",
        )})

    monkeypatch.setattr(owner, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(ctypes, "WinDLL", load, raising=False)
    backend = owner._Win32Backend()
    assert loads == [(name, {"use_last_error": True, "winmode": 0x800})
                     for name in ("iphlpapi.dll", "kernel32.dll")]
    assert backend.OpenProcess.restype is ctypes.c_void_p
    for function in (backend.QueryFullProcessImageNameW, backend.WaitForSingleObject, backend.CloseHandle):
        assert function.argtypes[0] is ctypes.c_void_p
    assert len(backend.GetExtendedTcpTable.argtypes) == 6
    assert ctypes.sizeof(backend.GetExtendedTcpTable.restype) == 4


@pytest.mark.skipif(os.name != "nt", reason="native Windows listener smoke test")
@pytest.mark.parametrize("family,address", [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")])
def test_native_temporary_listener_belongs_to_current_python(family, address):
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        try:
            if family == socket.AF_INET6:
                listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            listener.bind((address, 0))
        except OSError:
            if family == socket.AF_INET6:
                pytest.skip("IPv6 loopback is unavailable")
            raise
        listener.listen(1)
        result = owner.query_listener_owners(listener.getsockname()[1])
        assert result["status"] == "success", result
        entry = next(item for item in result["entries"] if item["Pid"] == os.getpid())
        assert entry["Pids"] == [os.getpid()]
        # Windows virtual environments can run the base interpreter via a redirector.
        interpreters = (sys.executable, getattr(sys, "_base_executable", sys.executable))
        assert any(os.path.samefile(entry["Paths"][0], path) for path in interpreters)
        assert entry["Names"] == [os.path.basename(entry["Paths"][0])]


@pytest.mark.parametrize("state", [0, 1, 2, 6])
def test_listener_table_rows_count_even_when_state_field_is_unreliable(api, state):
    # Observed on a real Windows 11 machine: the Amazon Music listener row came
    # back from TCP_TABLE_OWNER_PID_LISTENER with dwState=6.
    api.tables = {2: [_table(_row4(11, state=state))], 23: [_table()]}
    result = owner.query_listener_owners(PORT)
    assert result["status"] == "success"
    assert [entry["Pid"] for entry in result["entries"]] == [11]
