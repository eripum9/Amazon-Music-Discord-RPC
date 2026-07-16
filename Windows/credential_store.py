# MIT License - Copyright (c) 2026 eripum9

import ctypes
import hashlib
import os
from ctypes import wintypes


CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    def __init__(self, app_name, config_path):
        scope = hashlib.sha256(os.path.abspath(config_path).lower().encode("utf-8")).hexdigest()[:16]
        self._prefix = f"{app_name}:{scope}"
        self._advapi32 = None
        if os.name == "nt" and hasattr(ctypes, "WinDLL"):
            try:
                library = ctypes.WinDLL("advapi32", use_last_error=True)
                library.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
                library.CredWriteW.restype = wintypes.BOOL
                library.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
                library.CredReadW.restype = wintypes.BOOL
                library.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
                library.CredDeleteW.restype = wintypes.BOOL
                library.CredFree.argtypes = [ctypes.c_void_p]
                library.CredFree.restype = None
                self._advapi32 = library
            except OSError:
                self._advapi32 = None

    @property
    def available(self):
        return self._advapi32 is not None

    def target(self, key):
        return f"{self._prefix}:{key}"

    def write(self, key, value):
        if not self.available:
            return False
        raw = str(value or "").encode("utf-8")
        if not raw or len(raw) > 2560:
            return False
        blob = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        credential = _CREDENTIALW()
        credential.Type = CRED_TYPE_GENERIC
        credential.TargetName = self.target(key)
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = CRED_PERSIST_LOCAL_MACHINE
        credential.UserName = self._prefix
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            return False
        return self.read(key) == str(value)

    def read(self, key):
        if not self.available:
            return ""
        pointer = ctypes.POINTER(_CREDENTIALW)()
        if not self._advapi32.CredReadW(self.target(key), CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
            return ""
        try:
            credential = pointer.contents
            raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            return raw.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return ""
        finally:
            self._advapi32.CredFree(pointer)

    def delete(self, key):
        if not self.available:
            return False
        if self._advapi32.CredDeleteW(self.target(key), CRED_TYPE_GENERIC, 0):
            return True
        return ctypes.get_last_error() == ERROR_NOT_FOUND
