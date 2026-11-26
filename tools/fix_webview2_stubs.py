"""One-off: swap the plain-function IUnknown stubs for real ctypes prototypes.

`ctypes.cast()` cannot convert a plain Python function into a function
pointer - it needs a `WINFUNCTYPE` instance. This rewrites the three stub
assignments inside `_make_handler` and adds the prototype definitions.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "kali" / "webview2.py"

src = io.open(TARGET, encoding="utf-8").read()

# 1. Point the vtable at the prototype-backed function pointers.
src = src.replace(
    "vtbl[0] = ctypes.cast(_query_interface_stub, c_void_p)",
    "vtbl[0] = ctypes.cast(_query_interface_fn, c_void_p)")
src = src.replace(
    "vtbl[1] = ctypes.cast(_addref_stub, c_void_p)",
    "vtbl[1] = ctypes.cast(_addref_fn, c_void_p)")
src = src.replace(
    "vtbl[2] = ctypes.cast(_release_stub, c_void_p)",
    "vtbl[2] = ctypes.cast(_release_fn, c_void_p)")

# 2. Add the prototypes right after the stub definitions.
if "_query_interface_fn = " not in src:
    marker = "def _release_stub(this):\n    return 1\n"
    addition = marker + (
        "\n\n"
        "# COM calls these through the vtable, so they must be real function\n"
        "# pointers with the right calling convention - a plain Python\n"
        "# function cannot be cast to a pointer.\n"
        "_QUERY_INTERFACE_PROTO = ctypes.WINFUNCTYPE(\n"
        "    HRESULT, c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(c_void_p))\n"
        "_ADDREF_PROTO = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)\n"
        "_RELEASE_PROTO = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)\n"
        "\n"
        "_query_interface_fn = _QUERY_INTERFACE_PROTO(_query_interface_stub)\n"
        "_addref_fn = _ADDREF_PROTO(_addref_stub)\n"
        "_release_fn = _RELEASE_PROTO(_release_stub)\n"
    )
    if marker not in src:
        print("marker not found")
        raise SystemExit(1)
    src = src.replace(marker, addition, 1)

io.open(TARGET, "w", encoding="utf-8", newline="\n").write(src)
print("patched the IUnknown stubs")
