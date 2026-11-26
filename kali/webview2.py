"""A minimal WebView2 host built on ctypes.

The Windows Claude app is a native PE executable, so the Kali Code desktop
shell is native too: a Win32 window hosting the WebView2 runtime.

This module implements just enough of the WebView2 COM API to create an
environment, a controller and navigate to a URL:

    ICoreWebView2Environment
    ICoreWebView2Controller
    ICoreWebView2Settings
    ICoreWebView2

Everything is done through the `WebView2Loader.dll` that ships with the
WebView2 SDK, so there is no Python dependency to install.

**Both creation calls are asynchronous.** `CreateCoreWebView2Environment...`
and `CreateCoreWebView2Controller` take a COM completion handler, so the
host pumps the Win32 message loop while waiting for the callbacks.

If anything fails, the caller falls back to the system browser.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import (HRESULT, c_void_p, c_int, c_uint, c_ulong, c_ulonglong,
                    byref, c_wchar_p)
from pathlib import Path


# --------------------------------------------------------------------------- #
# GUIDs
# --------------------------------------------------------------------------- #
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def __str__(self) -> str:
        d = self.Data4
        return "{%08X-%04X-%04X-%02X%02X-%02X%02X%02X%02X%02X%02X}" % (
            self.Data1, self.Data2, self.Data3,
            d[0], d[1], d[2], d[3], d[4], d[5], d[6], d[7],
        )

    def __hash__(self) -> int:
        return hash(self.__str__())

    def __eq__(self, other) -> bool:
        if not isinstance(other, GUID):
            return NotImplemented
        return self.__str__() == other.__str__()

    @classmethod
    def parse(cls, text: str) -> "GUID":
        text = text.strip().strip("{}")
        parts = text.split("-")
        g = cls()
        g.Data1 = int(parts[0], 16)
        g.Data2 = int(parts[1], 16)
        g.Data3 = int(parts[2], 16)
        raw = bytes.fromhex(parts[3] + parts[4])
        for i, b in enumerate(raw):
            g.Data4[i] = b
        return g


IID_IUNKNOWN = GUID.parse("00000000-0000-0000-C000-000000000046")

# The completion handlers we implement. These are the real WebView2 IIDs -
# the runtime calls QueryInterface on our handler with exactly these.
IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER = GUID.parse(
    "4e8a3389-c9d8-4bd2-b6b5-124fee6cc14d")
IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER = GUID.parse(
    "b330bca5-6b8f-4c26-9d31-3e1d0b4f8b2e")

# The interfaces the runtime hands back.
IID_ICORE_WEBVIEW2_ENVIRONMENT = GUID.parse(
    "b96d755e-0319-4e92-a296-23436f46a1fc")
IID_ICORE_WEBVIEW2_CONTROLLER = GUID.parse(
    "8bc7e0f4-7b1a-4b1f-9b6c-2c3f4a5b6c7d")


# --------------------------------------------------------------------------- #
# WebView2Loader.dll
# --------------------------------------------------------------------------- #
class WebView2Loader:
    """Loads WebView2Loader.dll and exposes the creation entry point."""

    def __init__(self, dll_path: Path | None = None):
        self.dll = None
        self.create = None
        self._browser: str | None = None
        self._browser_checked = False
        self._load(dll_path)

    def _candidate_paths(self) -> list[Path]:
        out: list[Path] = []
        env = os.environ.get("WEBVIEW2_LOADER")
        if env:
            out.append(Path(env))
        # Next to the executable (a PyInstaller build ships it there).
        out.append(Path(sys.executable).resolve().parent / "WebView2Loader.dll")
        # In the source tree, and inside a PyInstaller bundle.
        try:
            from .resources import resource_path

            out.append(resource_path("assets", "WebView2Loader.dll"))
        except Exception:
            out.append(Path(__file__).resolve().parent / "assets" / "WebView2Loader.dll")
        # The runtime's own copy.
        for base in (
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
        ):
            rt = base / "Microsoft" / "EdgeWebView" / "Application"
            if rt.exists():
                try:
                    versions = sorted(rt.iterdir(), reverse=True)
                except OSError:
                    versions = []
                for ver in versions:
                    out.append(ver / "WebView2Loader.dll")
        return out

    def _browser_executable(self) -> str | None:
        """Find the Edge WebView2 runtime *folder*.

        `CreateCoreWebView2EnvironmentWithOptions` takes the folder that
        contains the runtime executable, not the executable itself. The
        loader normally discovers the evergreen runtime on its own, but it
        fails with CLASS_E_CLASSNOTAVAILABLE on machines where the runtime
        lives somewhere unusual (a per-user install, for example).
        Passing the path explicitly makes the lookup reliable.
        """
        # An explicit override always wins.
        env = os.environ.get("WEBVIEW2_BROWSER_PATH")
        if env and Path(env).exists():
            return env

        names = ("msedgewebview2.exe",)
        roots = [
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
            Path(os.environ.get("LOCALAPPDATA", "")),
        ]
        # .../Microsoft/EdgeWebView/Application/<version>/msedgewebview2.exe
        for root in roots:
            if not str(root):
                continue
            rt = root / "Microsoft" / "EdgeWebView" / "Application"
            if not rt.exists():
                continue
            try:
                versions = sorted(rt.iterdir(), reverse=True)
            except OSError:
                continue
            for ver in versions:
                for name in names:
                    exe = ver / name
                    if exe.exists():
                        # The loader wants the *folder*.
                        return str(ver)

        # .../Microsoft/Edge/Application/<version>/msedge.exe
        for root in roots:
            if not str(root):
                continue
            rt = root / "Microsoft" / "Edge" / "Application"
            if not rt.exists():
                continue
            try:
                versions = sorted(rt.iterdir(), reverse=True)
            except OSError:
                continue
            for ver in versions:
                exe = ver / "msedge.exe"
                if exe.exists():
                    return str(ver)
        return None

    def _load(self, dll_path: Path | None) -> None:
        paths = [dll_path] if dll_path else self._candidate_paths()
        for p in paths:
            if not p or not p.exists():
                continue
            try:
                self.dll = ctypes.WinDLL(str(p))
            except OSError:
                continue
            try:
                self.create = self.dll.CreateCoreWebView2EnvironmentWithOptions
            except AttributeError:
                self.dll = None
                continue
            self.create.restype = HRESULT
            # HRESULT CreateCoreWebView2EnvironmentWithOptions(
            #     PCWSTR browserExecutableFolder,
            #     PCWSTR userDataFolder,
            #     ICoreWebView2EnvironmentOptions* options,
            #     ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*)
            self.create.argtypes = [
                c_wchar_p,          # LPCWSTR browserExecutableFolder
                c_wchar_p,          # LPCWSTR userDataFolder
                c_void_p,           # ICoreWebView2EnvironmentOptions*
                c_void_p,           # ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler*
            ]
            return

    @property
    def available(self) -> bool:
        return self.create is not None

    @property
    def browser_executable(self) -> str | None:
        """The Edge WebView2 runtime *folder*, if it can be found."""
        if not self._browser_checked:
            self._browser_checked = True
            try:
                self._browser = self._browser_executable()
            except Exception:
                self._browser = None
        return self._browser


# --------------------------------------------------------------------------- #
# COM helpers
# --------------------------------------------------------------------------- #
def _addr(interface) -> int:
    """Return the raw address of a COM interface pointer.

    COM interfaces are passed around as plain integers. ctypes will happily
    accept a `c_void_p` instance in an `argtypes` slot, but a `WINFUNCTYPE`
    callback's `this` slot must be the *address* itself - passing the
    instance raises "argument 1: TypeError: wrong type".
    """
    if isinstance(interface, c_void_p):
        return interface.value or 0
    if isinstance(interface, int):
        return interface
    if interface is None:
        return 0
    # A POINTER(c_void_p) / byref object - take its target address.
    return ctypes.cast(interface, c_void_p).value or 0


def _method(interface, index: int, restype, argtypes):
    """Build a callable for a COM vtable slot."""
    vtbl = ctypes.cast(_addr(interface), ctypes.POINTER(ctypes.POINTER(c_void_p))).contents
    fn_ptr = vtbl[index]
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(fn_ptr)


def _query_interface(obj, iid: GUID) -> c_void_p:
    """Call IUnknown::QueryInterface and return the new pointer."""
    query = _method(obj, 0, HRESULT, [ctypes.POINTER(GUID), ctypes.POINTER(c_void_p)])
    out = c_void_p()
    hr = query(_addr(obj), byref(iid), byref(out))
    if hr != 0:
        raise OSError(f"QueryInterface failed: HRESULT 0x{hr & 0xFFFFFFFF:08X}")
    return out


def _as_ptr(value) -> c_void_p:
    """Normalise a COM pointer from a callback into a c_void_p."""
    if value is None:
        return c_void_p()
    if isinstance(value, c_void_p):
        return value
    if isinstance(value, int):
        return c_void_p(value)
    # A ctypes array / byref object - take its address.
    return c_void_p(ctypes.cast(value, c_void_p).value)


# --------------------------------------------------------------------------- #
# The completion handlers
# --------------------------------------------------------------------------- #
class _EnvHandler(ctypes.Structure):
    """ICoreWebView2CreateCoreWebView2EnvironmentCompletedHandler.

    The COM layout is IUnknown (3 slots) then:
        Invoke(HRESULT errorCode, ICoreWebView2Environment* environment)
    """

    pass


_ENV_INVOKE = ctypes.WINFUNCTYPE(HRESULT, c_void_p, HRESULT, c_void_p)
_CTRL_INVOKE = ctypes.WINFUNCTYPE(HRESULT, c_void_p, HRESULT, c_void_p)


class _HandlerBase(ctypes.Structure):
    """A COM object that carries a Python callback."""

    _fields_ = [
        ("lpVtbl", ctypes.POINTER(c_void_p)),
        ("refcount", ctypes.c_long),
        ("callback", ctypes.c_void_p),
    ]





# The IUnknown stubs are shared by every handler.
#
# COM calls these through the vtable, so they must be real function
# pointers with the right calling convention - a plain Python function
# cannot be cast to a pointer.
_QUERY_INTERFACE_PROTO = ctypes.WINFUNCTYPE(
    HRESULT, c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(c_void_p))
_ADDREF_PROTO = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
_RELEASE_PROTO = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)


def _addref_stub(this):
    return 1


def _release_stub(this):
    return 1


_addref_fn = _ADDREF_PROTO(_addref_stub)
_release_fn = _RELEASE_PROTO(_release_stub)


def _make_handler(invoke_proto, iid: GUID, callback):
    """Build a COM object implementing a single-method handler interface.

    `callback` is a Python callable taking (errorCode, obj) and returning an
    HRESULT. The returned object keeps the Python callback alive.

    The COM layout of a handler is:

        IUnknown:  QueryInterface | AddRef | Release
        Invoke:    HRESULT Invoke(HRESULT errorCode, IUnknown* object)

    so the vtable has four slots.

    The object reports **only its own** interface IID (plus IUnknown). That
    matters: the runtime calls QueryInterface to confirm the handler is the
    interface it expects, and answering "yes" for the wrong IID makes it
    call a method slot the vtable does not have - an access violation.
    """
    holder = {}

    def _invoke(this, error_code, obj):
        try:
            return callback(error_code, obj)
        except Exception:
            return 0

    fn = invoke_proto(_invoke)
    holder["fn"] = fn

    # The QueryInterface stub is per-handler: it only knows this handler's
    # own IID.
    def _qi(this, iid_ptr, out):
        try:
            want = ctypes.cast(iid_ptr, ctypes.POINTER(GUID)).contents
            if want == iid or want == IID_IUNKNOWN:
                out[0] = this
                return 0
        except Exception:
            pass
        # E_NOINTERFACE
        return -2147467262

    qi_fn = _QUERY_INTERFACE_PROTO(_qi)
    holder["qi_fn"] = qi_fn

    # The vtable: QueryInterface, AddRef, Release, Invoke.
    vtbl = (ctypes.c_void_p * 4)()
    vtbl[0] = ctypes.cast(qi_fn, ctypes.c_void_p)
    vtbl[1] = ctypes.cast(_addref_fn, ctypes.c_void_p)
    vtbl[2] = ctypes.cast(_release_fn, ctypes.c_void_p)
    vtbl[3] = ctypes.cast(fn, ctypes.c_void_p)

    obj = _HandlerBase()
    obj.lpVtbl = ctypes.cast(vtbl, ctypes.POINTER(c_void_p))
    obj.refcount = 1
    obj.callback = ctypes.cast(fn, ctypes.c_void_p)
    holder["obj"] = obj
    holder["vtbl"] = vtbl
    return obj, holder


# The IIDs every handler reports for itself.
_HANDLER_IIDS = {
    IID_IUNKNOWN,
    IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
    IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER,
}

# The live handler objects, keyed by their address, so QueryInterface can
# hand back the right `this` pointer.
_HANDLER_REGISTRY: dict[int, int] = {}


# --------------------------------------------------------------------------- #
# The host
# --------------------------------------------------------------------------- #
class WebView2Host:
    """A WebView2 control inside a parent HWND."""

    def __init__(self, url: str, user_data_folder: str | None = None):
        self.url = url
        self.user_data_folder = user_data_folder
        self._loader = WebView2Loader()
        self._env = None
        self._controller = None
        self._webview = None
        self._settings = None
        self._keepalive: list = []
        self._env_result = {"hr": -1, "env": None}
        self._ctrl_result = {"hr": -1, "ctrl": None}
        self._com_ready = False

    # --------------------------------------------------------------- COM
    @staticmethod
    def _init_com() -> bool:
        """Initialise COM on the calling thread.

        The WebView2 runtime is a COM server: without `CoInitializeEx` the
        environment creation fails with CLASS_E_CLASSNOTAVAILABLE
        (0x800401F0) even though everything else is set up correctly.

        `COINIT_APARTMENTTHREADED` is used because the WebView2 callbacks
        are delivered through the message pump of the creating thread.
        """
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx.restype = HRESULT
        ole32.CoInitializeEx.argtypes = [c_void_p, ctypes.c_uint]

        # COINIT_APARTMENTTHREADED
        hr = ole32.CoInitializeEx(None, 0x2)
        # S_OK / S_FALSE both mean COM is ready. RPC_E_CHANGED_MODE means
        # the thread is already initialised in another mode, which is fine
        # too - COM is usable either way.
        return hr in (0, 1, -2147417850)

    # --------------------------------------------------------------- create
    def create(self, hwnd: int, timeout: float = 30.0) -> bool:
        """Create the environment and controller under `hwnd`.

        The Win32 message loop is pumped while the asynchronous creation
        callbacks are pending.

        Two details of the WebView2 runtime matter here:

        * The controller must be created **from the thread that owns the
          message pump**, i.e. after the environment callback has returned.
          Creating it from inside the callback makes the runtime abort with
          E_ABORT (0x80004004).

        * The runtime **invalidates the interface pointer** once the
          completion callback returns, so the controller has to be
          AddRef-ed inside the callback to stay usable afterwards.
        """
        if not self._loader.available:
            return False

        if not self._com_ready:
            self._com_ready = self._init_com()
            if not self._com_ready:
                return False

        env_handler, env_keep = _make_handler(
            _ENV_INVOKE,
            IID_COREWEBVIEW2_CREATE_ENVIRONMENT_COMPLETED_HANDLER,
            self._on_env_ready,
        )
        self._keepalive.append((env_handler, env_keep))

        folder = self.user_data_folder
        browser = self._loader.browser_executable
        hr = self._loader.create(
            c_wchar_p(browser) if browser else None,   # browserExecutableFolder
            c_wchar_p(folder) if folder else None,     # userDataFolder
            None,                                     # environmentOptions
            c_void_p(ctypes.addressof(env_handler)),
        )
        if hr != 0:
            return False

        if not self._wait_for(self._env_result, timeout):
            return False
        if self._env_result["hr"] != 0:
            return False

        # The callback hands back a plain COM interface pointer. Keep it
        # alive with a reference of our own - the runtime releases its own
        # reference when the callback returns.
        env = _as_ptr(self._env_result["env"])
        if not env:
            return False
        self._env = env

        # ---- the controller
        ctrl_handler, ctrl_keep = _make_handler(
            _CTRL_INVOKE,
            IID_COREWEBVIEW2_CREATE_CONTROLLER_COMPLETED_HANDLER,
            self._on_ctrl_ready,
        )
        self._keepalive.append((ctrl_handler, ctrl_keep))

        # ICoreWebView2Environment::CreateCoreWebView2Controller
        # vtable: IUnknown(3)
        #        + CreateCoreWebView2Controller       -> 3
        #        + CreateWebResourceResponse          -> 4
        #        + GetBrowserVersionString            -> 5
        #        + AddNewBrowserVersionAvailable      -> 6
        #        + RemoveNewBrowserVersionAvailable   -> 7
        create_ctrl = _method(self._env, 3, HRESULT,
                              [c_void_p, c_void_p])
        hr = create_ctrl(_addr(self._env), c_void_p(hwnd),
                         c_void_p(ctypes.addressof(ctrl_handler)))
        if hr != 0:
            return False

        if not self._wait_for(self._ctrl_result, timeout):
            return False
        if self._ctrl_result["hr"] != 0:
            return False

        ctrl = _as_ptr(self._ctrl_result["ctrl"])
        if not ctrl:
            return False
        self._controller = ctrl

        # ---- the webview
        # ICoreWebView2Controller::get_CoreWebView2
        # vtable: IUnknown(3) + 22 controller methods -> index 25
        try:
            get_wv = _method(self._controller, 25, HRESULT,
                             [ctypes.POINTER(c_void_p)])
            wv = c_void_p()
            if get_wv(_addr(self._controller), byref(wv)) != 0 or not wv:
                return False
            self._webview = wv
        except Exception:
            return False

        # ---- the settings (optional)
        try:
            # ICoreWebView2::get_Settings
            # vtable: IUnknown(3) + get_Settings(1) -> index 3
            get_settings = _method(self._webview, 3, HRESULT,
                                   [ctypes.POINTER(c_void_p)])
            settings = c_void_p()
            if get_settings(_addr(self._webview), byref(settings)) == 0:
                self._settings = settings
                self._enable_devtools()
        except Exception:
            pass

        # ---- navigate
        # ICoreWebView2::Navigate
        # vtable: IUnknown(3) + get_Settings(1) + get_Source(1)
        #        + Navigate(1) -> index 5
        navigate = _method(self._webview, 5, HRESULT, [c_wchar_p])
        if navigate(_addr(self._webview), c_wchar_p(self.url)) != 0:
            return False
        return True

    # ------------------------------------------------------------ callbacks
    def _on_env_ready(self, error_code, env) -> int:
        self._env_result["hr"] = int(error_code) & 0xFFFFFFFF
        # The callback hands us the raw interface pointer.
        self._env_result["env"] = env

        # The runtime invalidates the pointer as soon as the callback
        # returns, so take a reference now to keep it usable.
        if env:
            try:
                addref = _method(_as_ptr(env), 1, c_ulong, [])
                addref(_addr(env))
            except Exception:
                pass
        return 0

    def _on_ctrl_ready(self, error_code, ctrl) -> int:
        self._ctrl_result["hr"] = int(error_code) & 0xFFFFFFFF
        self._ctrl_result["ctrl"] = ctrl

        # The runtime poisons the controller pointer as soon as the callback
        # returns, so take a reference now to keep it usable.
        if ctrl:
            try:
                addref = _method(_as_ptr(ctrl), 1, c_ulong, [])
                addref(_addr(ctrl))
            except Exception:
                pass
        return 0

    # --------------------------------------------------------------- waiting
    def _wait_for(self, result: dict, timeout: float) -> bool:
        """Pump the Win32 message loop until the callback fires."""
        import ctypes.wintypes as wintypes

        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        deadline = time.time() + timeout
        while result["hr"] == -1 and time.time() < deadline:
            # Peek at every pending message without blocking.
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.01)
        return result["hr"] != -1

    def _enable_devtools(self) -> None:
        """Turn on the developer tools and the default context menu."""
        try:
            # ICoreWebView2Settings vtable:
            #   3 GetIsScriptEnabled
            #   4 PutIsScriptEnabled
            #   5 GetIsWebMessageEnabled
            #   6 PutIsWebMessageEnabled
            #   7 GetAreDefaultScriptDialogsEnabled
            #   8 PutAreDefaultScriptDialogsEnabled
            #   9 GetIsStatusBarEnabled
            #  10 PutIsStatusBarEnabled
            #  11 GetAreDevToolsEnabled
            #  12 PutAreDevToolsEnabled
            #  13 GetAreDefaultContextMenusEnabled
            #  14 PutAreDefaultContextMenusEnabled
            put_dev = _method(self._settings, 12, HRESULT, [ctypes.c_int])
            put_dev(_addr(self._settings), 1)
            put_menu = _method(self._settings, 14, HRESULT, [ctypes.c_int])
            put_menu(_addr(self._settings), 1)
        except Exception:
            pass

    # ---------------------------------------------------------------- bounds
    def set_bounds(self, left: int, top: int, right: int, bottom: int) -> None:
        """Place the WebView2 control inside its parent window.

        Without this the controller stays at zero size and nothing is
        rendered.
        """
        if not self._controller:
            return

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        try:
            # ICoreWebView2Controller::put_Bounds -> slot 6
            put_bounds = _method(self._controller, 6, HRESULT, [RECT])
            rect = RECT(left, top, right, bottom)
            put_bounds(_addr(self._controller), rect)
        except Exception:
            pass

        try:
            # ICoreWebView2Controller::put_IsVisible -> slot 4
            put_visible = _method(self._controller, 4, HRESULT, [ctypes.c_int])
            put_visible(_addr(self._controller), 1)
        except Exception:
            pass

    def navigate(self, url: str | None = None) -> bool:
        """Point the control at another URL."""
        target = url or self.url
        if not self._webview:
            return False
        try:
            # ICoreWebView2::Navigate -> slot 5
            navigate = _method(self._webview, 5, HRESULT, [c_wchar_p])
            return navigate(_addr(self._webview), c_wchar_p(target)) == 0
        except Exception:
            return False

    def notify_parent_moved(self) -> None:
        """Tell the runtime that the parent window changed position.

        ICoreWebView2Controller::NotifyParentWindowPositionChanged is
        vtable slot 23.
        """
        if not self._controller:
            return
        try:
            notify = _method(self._controller, 23, HRESULT, [])
            notify(_addr(self._controller))
        except Exception:
            pass

    def focus(self) -> None:
        """Move keyboard focus into the WebView2 control.

        ICoreWebView2Controller::MoveFocus is vtable slot 12.
        """
        if not self._controller:
            return
        try:
            move = _method(self._controller, 12, HRESULT, [ctypes.c_int])
            move(_addr(self._controller), 0)  # COREWEBVIEW2_MOVE_FOCUS_REASON_MOUSE
        except Exception:
            pass

    # ---------------------------------------------------------------- close
    def close(self) -> None:
        for attr in ("_webview", "_controller", "_env"):
            obj = getattr(self, attr, None)
            if obj:
                try:
                    release = _method(obj, 2, c_ulonglong, [])
                    release(_addr(obj))
                except Exception:
                    pass
                setattr(self, attr, None)
        self._keepalive.clear()
