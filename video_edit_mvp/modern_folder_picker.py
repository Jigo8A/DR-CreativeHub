from __future__ import annotations

import ctypes
import uuid
from ctypes import wintypes
from pathlib import Path


CLSID_FILE_OPEN_DIALOG = "DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7"
IID_FILE_OPEN_DIALOG = "D57C7288-D4AD-4768-BE02-9D969532D960"
IID_SHELL_ITEM = "43826D1E-E718-42EE-BC55-A1E261C37BFE"
FOS_PICKFOLDERS = 0x20
FOS_FORCEFILESYSTEM = 0x40
FOS_PATHMUSTEXIST = 0x800
FOS_NOCHANGEDIR = 0x8
SIGDN_FILESYSPATH = 0x80058000
CLSCTX_INPROC_SERVER = 0x1
COINIT_APARTMENTTHREADED = 0x2
ERROR_CANCELLED = 0x800704C7
HRESULT = ctypes.c_long


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def pick_folder(initial_dir: Path) -> str:
    ole32 = ctypes.WinDLL("ole32")
    shell32 = ctypes.WinDLL("shell32")
    dialog = ctypes.c_void_p()
    initialized = False
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = HRESULT
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = HRESULT
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None

    hr = ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
    if _ok(hr):
        initialized = True
    elif _unsigned(hr) != 0x80010106:
        _raise_for_hr(hr)

    try:
        clsid = GUID.from_string(CLSID_FILE_OPEN_DIALOG)
        iid_dialog = GUID.from_string(IID_FILE_OPEN_DIALOG)
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid),
            None,
            CLSCTX_INPROC_SERVER,
            ctypes.byref(iid_dialog),
            ctypes.byref(dialog),
        )
        _raise_for_hr(hr)

        _set_dialog_options(dialog)
        _call(dialog, 17, HRESULT, wintypes.LPCWSTR)("Selecionar pasta")
        _call(dialog, 18, HRESULT, wintypes.LPCWSTR)("Selecionar")
        _set_initial_folder(dialog, shell32, initial_dir)

        hr = _call(dialog, 3, HRESULT, wintypes.HWND)(None)
        if _unsigned(hr) == ERROR_CANCELLED:
            return ""
        _raise_for_hr(hr)

        result = ctypes.c_void_p()
        _raise_for_hr(_call(dialog, 20, HRESULT, ctypes.POINTER(ctypes.c_void_p))(ctypes.byref(result)))
        try:
            return _shell_item_path(result, ole32)
        finally:
            _release(result)
    finally:
        if dialog:
            _release(dialog)
        if initialized:
            ole32.CoUninitialize()


def _set_dialog_options(dialog: ctypes.c_void_p) -> None:
    options = wintypes.DWORD()
    get_options = _call(dialog, 10, HRESULT, ctypes.POINTER(wintypes.DWORD))
    set_options = _call(dialog, 9, HRESULT, wintypes.DWORD)
    _raise_for_hr(get_options(ctypes.byref(options)))
    options.value |= FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST | FOS_NOCHANGEDIR
    _raise_for_hr(set_options(options.value))


def _set_initial_folder(dialog: ctypes.c_void_p, shell32: ctypes.OleDLL, initial_dir: Path) -> None:
    if not initial_dir.exists():
        return
    shell_item = ctypes.c_void_p()
    iid_shell_item = GUID.from_string(IID_SHELL_ITEM)
    shell32.SHCreateItemFromParsingName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHCreateItemFromParsingName.restype = HRESULT
    hr = shell32.SHCreateItemFromParsingName(
        str(initial_dir),
        None,
        ctypes.byref(iid_shell_item),
        ctypes.byref(shell_item),
    )
    if _ok(hr):
        try:
            _raise_for_hr(_call(dialog, 12, HRESULT, ctypes.c_void_p)(shell_item))
        finally:
            _release(shell_item)


def _shell_item_path(shell_item: ctypes.c_void_p, ole32: ctypes.OleDLL) -> str:
    path_pointer = ctypes.c_void_p()
    get_display_name = _call(shell_item, 5, HRESULT, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p))
    _raise_for_hr(get_display_name(SIGDN_FILESYSPATH, ctypes.byref(path_pointer)))
    try:
        return ctypes.wstring_at(path_pointer)
    finally:
        ole32.CoTaskMemFree(path_pointer)


def _call(com_object: ctypes.c_void_p, index: int, restype, *argtypes):
    vtable = ctypes.cast(com_object, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    address = vtable[index]
    method = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(address)
    return lambda *args: method(com_object, *args)


def _release(com_object: ctypes.c_void_p) -> None:
    _call(com_object, 2, wintypes.ULONG)()


def _ok(hr: int) -> bool:
    return _unsigned(hr) in {0, 1}


def _unsigned(hr: int) -> int:
    return hr & 0xFFFFFFFF


def _raise_for_hr(hr: int) -> None:
    if not _ok(hr):
        raise ctypes.WinError(hr)
