"""Private local storage, with Windows DPAPI protection for credentials."""

import ctypes
import json
import os
from pathlib import Path
import subprocess
import tempfile


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        # Use the current SID (works with localized account names). Do this
        # before creating plaintext configuration, logs, or credential files.
        sid = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"], text=True
        ).strip().split(',')[-1].strip('"')
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r",
             f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    else:
        path.chmod(0o700)


def atomic_write(path: Path, data: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".bridge-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def dpapi(data: bytes, *, decrypt: bool = False) -> bytes:
    # DPAPI's default scope is the current Windows user. No machine-wide flag.
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    result = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN: fail instead of opening an unexpected UI.
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(result.data)


def credential_path(root: Path) -> Path:
    return root / ("credentials.dpapi" if os.name == "nt" else "credentials.json")


def save_credentials(root: Path, values: dict) -> None:
    data = json.dumps(values).encode("utf-8")
    atomic_write(credential_path(root), dpapi(data) if os.name == "nt" else data)


def load_credentials(root: Path) -> dict:
    data = credential_path(root).read_bytes()
    return json.loads(dpapi(data, decrypt=True) if os.name == "nt" else data)
