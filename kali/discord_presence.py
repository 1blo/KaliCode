"""Discord Rich Presence for Kali Code.

Shows, on the user's Discord profile:

    [Kali Code logo]  Using Kali Code
                      <AI-generated chat title>
                      <elapsed timer>

Discord RPC requires an Application ID. Kali Code's app id lives in
~/.kali/settings.json under "discord": {"clientId": "..."}. If it is missing
the whole module stays dormant - Kali Code works fine without Discord.

The module is deliberately dependency-light: it speaks the Discord IPC
protocol directly over the local named pipe (``\\\\.\\pipe\\discord-ipc-N`` on
Windows, ``/tmp/discord-ipc-N`` on Unix), so there is no third-party runtime
requirement. ``pypresence`` is used only as an optional fallback.
"""
from __future__ import annotations

import asyncio
import json
import os
import struct
import time
from dataclasses import dataclass, field

from .resources import resource_dir

# Discord IPC opcodes
OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

# Discord activity type 0 == "Playing"
ACTIVITY_PLAYING = 0


def _assets_dir() -> str:
    """Directory holding the bundled Discord assets.

    Uses the resource helper so it works inside a PyInstaller bundle.
    """
    return str(resource_dir("assets"))


@dataclass
class PresenceConfig:
    client_id: str = ""
    app_name: str = "Kali Code"
    state_text: str = "Using Kali Code"
    # Rich Presence asset key (uploaded in the Discord dev portal under
    # Rich Presence -> Art Assets). Discord resolves it to an image.
    large_image: str = "kali"
    large_text: str = "Kali Code"
    # Fallback: the app icon CDN URL. Used if the asset key is unknown.
    large_image_url: str = ""
    small_image: str = ""
    small_text: str = ""
    enabled: bool = True


@dataclass
class PresenceState:
    """Everything that can change during a session."""

    title: str = ""            # AI-generated chat title
    state: str = "Using Kali Code"
    started_at: float = field(default_factory=time.time)
    # Optional transient status ("Running Bash", "Reading file", ...)
    activity: str = ""
    details: str = ""


class DiscordIpc:
    """Minimal Discord local-RPC client (newline-free, length-prefixed frames)."""

    def __init__(self, client_id: str):
        self.client_id = client_id
        self._handle = None
        self._proc = None
        self._read_task: asyncio.Task | None = None
        self._connected = False
        self._assets: dict[str, str] = {}
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1

    # ------------------------------------------------------------- plumbing
    def _open_pipe(self):
        """Open the Discord IPC channel. Returns a file-like object."""
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            GENERIC_READ = 0x80000000
            GENERIC_WRITE = 0x40000000
            OPEN_EXISTING = 3
            INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateFileW.restype = wintypes.HANDLE
            kernel32.CreateFileW.argtypes = [
                wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
            ]
            last_error = None
            for i in range(10):
                path = rf"\\.\pipe\discord-ipc-{i}"
                h = kernel32.CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0,
                                         None, OPEN_EXISTING, 0, None)
                if h != INVALID_HANDLE_VALUE:
                    return _WindowsPipe(h, kernel32)
                last_error = ctypes.get_last_error()
            raise ConnectionError(
                f"Discord IPC pipe not found (winerror {last_error}). "
                "Is Discord running?"
            )

        # POSIX: Discord uses a unix domain socket.
        import socket

        for i in range(10):
            path = f"/tmp/discord-ipc-{i}"
            if not os.path.exists(path):
                continue
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.connect(path)
                return _UnixPipe(sock)
            except OSError:
                sock.close()
        raise ConnectionError("Discord IPC socket not found. Is Discord running?")

    @staticmethod
    def _frame(op: int, payload: dict) -> bytes:
        body = json.dumps(payload).encode("utf-8")
        return struct.pack("<ii", op, len(body)) + body

    def _send(self, op: int, payload: dict) -> None:
        if self._handle is None:
            raise ConnectionError("IPC not open")
        self._handle.write(self._frame(op, payload))
        self._handle.flush()

    def _read_exact(self, n: int) -> bytes:
        if self._handle is None:
            raise ConnectionError("IPC not open")
        data = self._handle.read(n)
        if data is None or len(data) < n:
            raise ConnectionError("Discord closed the IPC connection")
        return data

    def _read_frame(self) -> tuple[int, dict]:
        op = struct.unpack("<i", self._read_exact(4))[0]
        length = struct.unpack("<i", self._read_exact(4))[0]
        body = self._read_exact(length) if length else b"{}"
        try:
            return op, json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            return op, {}

    # --------------------------------------------------------------- public
    def connect(self) -> None:
        self._handle = self._open_pipe()
        self._send(OP_HANDSHAKE, {"v": 1, "client_id": self.client_id})
        op, data = self._read_frame()
        if op == OP_CLOSE or data.get("evt") == "ERROR":
            raise ConnectionError(
                f"Discord rejected the handshake: {data.get('message', data)} "
                f"(check the client id {self.client_id})"
            )
        if data.get("evt") != "READY":
            raise ConnectionError(f"Unexpected handshake response: {data}")
        self._connected = True

    def request(self, cmd: str, args: dict | None = None) -> dict:
        rid = self._next_id
        self._next_id += 1
        payload = {"cmd": cmd, "nonce": f"kali-{rid}", "args": args or {}}
        self._send(OP_FRAME, payload)
        while True:
            op, data = self._read_frame()
            if op == OP_CLOSE:
                raise ConnectionError("Discord closed the connection")
            if data.get("cmd") == cmd and data.get("nonce") == payload["nonce"]:
                if data.get("evt") == "ERROR":
                    raise RuntimeError(data.get("message", "Discord RPC error"))
                return data.get("data") or {}

    def upload_asset(self, path: str) -> str:
        """Upload an image and return the Discord asset key (e.g. '12345')."""
        with open(path, "rb") as fh:
            data = fh.read()
        ext = os.path.splitext(path)[1].lstrip(".").lower() or "png"
        res = self.request("UPLOAD", {"file": f"data:image/{ext};base64,"
                                           + _b64(data)})
        asset = res.get("asset")
        if not asset:
            raise RuntimeError(f"Discord did not return an asset: {res}")
        return asset

    def set_activity(self, activity: dict) -> None:
        self.request("SET_ACTIVITY", {"activity": activity, "pid": os.getpid()})

    def close(self) -> None:
        self._connected = False
        if self._handle is not None:
            try:
                self._send(OP_CLOSE, {})
            except Exception:
                pass
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


class _WindowsPipe:
    """File-like wrapper over a Win32 named-pipe handle."""

    def __init__(self, handle, kernel32):
        self._h = handle
        self._k = kernel32

    def read(self, n: int) -> bytes:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_string_buffer(n)
        read = wintypes.DWORD(0)
        ok = self._k.ReadFile(wintypes.HANDLE(self._h), buf, n,
                              ctypes.byref(read), None)
        if not ok:
            return b""
        return buf.raw[: read.value]

    def write(self, data: bytes) -> int:
        import ctypes
        from ctypes import wintypes

        written = wintypes.DWORD(0)
        ok = self._k.WriteFile(wintypes.HANDLE(self._h), data, len(data),
                               ctypes.byref(written), None)
        return written.value if ok else 0

    def flush(self) -> None:
        pass

    def close(self) -> None:
        import ctypes
        from ctypes import wintypes

        try:
            self._k.CloseHandle(wintypes.HANDLE(self._h))
        except Exception:
            pass


class _UnixPipe:
    """File-like wrapper over a unix domain socket."""

    def __init__(self, sock):
        self._s = sock

    def read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._s.recv(n - len(buf))
            if not chunk:
                return buf
            buf += chunk
        return buf

    def write(self, data: bytes) -> int:
        return self._s.sendall(data) or len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        try:
            self._s.close()
        except Exception:
            pass


class DiscordPresence:
    """High-level Rich Presence controller used by Kali Code."""

    def __init__(self, cfg: PresenceConfig):
        self.cfg = cfg
        self.ipc: DiscordIpc | None = None
        self.state = PresenceState()
        self._asset_keys: dict[str, str] = {}
        self._task: asyncio.Task | None = None
        self._stop = False
        self.last_error: str = ""

    # ------------------------------------------------------------ lifecycle
    @property
    def active(self) -> bool:
        return self.ipc is not None and self.ipc._connected

    def start(self) -> bool:
        """Connect to Discord and upload assets. Returns True on success."""
        if not self.cfg.enabled or not self.cfg.client_id:
            return False
        try:
            self.ipc = DiscordIpc(self.cfg.client_id)
            self.ipc.connect()
            self._task = asyncio.create_task(self._heartbeat())
            return True
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.ipc = None
            return False

    def stop(self) -> None:
        self._stop = True
        if self._task:
            self._task.cancel()
            self._task = None
        if self.ipc:
            try:
                self.ipc.set_activity({"name": self.cfg.app_name, "type": ACTIVITY_PLAYING})
            except Exception:
                pass
            self.ipc.close()
            self.ipc = None

    # -------------------------------------------------------------- updates
    def set_title(self, title: str) -> None:
        """Set the AI-generated chat title shown under the activity name."""
        self.state.title = (title or "").strip()
        self._push()

    def set_activity(self, text: str) -> None:
        """Set the transient status line (e.g. 'Running Bash')."""
        self.state.activity = (text or "").strip()
        self._push()

    def clear_activity(self) -> None:
        self.state.activity = ""
        self._push()

    def _push(self) -> None:
        """Send the current activity to Discord right away.

        The heartbeat refreshes every 20s, but title/activity changes should
        appear instantly rather than up to 20 seconds later.
        """
        ipc = self.ipc
        if ipc is None or not getattr(ipc, "_connected", False):
            return
        try:
            ipc.set_activity(self.build_activity())
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"

    def build_activity(self) -> dict:
        details = self.state.activity or self.state.title or "Kali Code"
        act: dict = {
            "type": ACTIVITY_PLAYING,
            "name": self.cfg.app_name,
            "details": details,
            "state": self.cfg.state_text,
            "timestamps": {"start": int(self.state.started_at)},
        }
        assets: dict = {"large_text": self.cfg.large_text}
        # Discord resolves either a Rich Presence asset key (e.g. "kali") or a
        # direct image URL. The URL always renders, so prefer it when set and
        # fall back to the asset key otherwise.
        if self.cfg.large_image_url:
            assets["large_image"] = self.cfg.large_image_url
        elif self.cfg.large_image:
            assets["large_image"] = self.cfg.large_image
        if self.cfg.small_image:
            assets["small_image"] = self.cfg.small_image
            assets["small_text"] = self.cfg.small_text
        if assets:
            act["assets"] = assets
        return act

    async def _heartbeat(self) -> None:
        """Keep the presence alive and the timer ticking."""
        while not self._stop:
            try:
                if self.ipc is not None and self.ipc._connected:
                    self.ipc.set_activity(self.build_activity())
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                self.ipc = None
                return


def load_config(settings: dict | None = None) -> PresenceConfig:
    """Read Discord settings from ~/.kali/settings.json."""
    settings = settings or {}
    section = settings.get("discord") or {}
    if not isinstance(section, dict):
        section = {}
    return PresenceConfig(
        client_id=str(section.get("clientId") or section.get("client_id") or ""),
        app_name=str(section.get("appName") or "Kali Code"),
        state_text=str(section.get("stateText") or "Using Kali Code"),
        large_image=str(section.get("largeImage") or "kali"),
        large_text=str(section.get("largeText") or "Kali Code"),
        large_image_url=str(section.get("largeImageUrl") or ""),
        small_image=str(section.get("smallImage") or ""),
        small_text=str(section.get("smallText") or ""),
        enabled=bool(section.get("enabled", True)),
    )
