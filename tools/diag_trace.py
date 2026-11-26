"""Diagnostic: trace the WebView2Host.create() step by step."""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import HRESULT, c_void_p, c_wchar_p

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kali.webview2 as wv2
import kali.desktop_shell as ds

user32 = ds._user32

print("step 1: init com")
print("   ", wv2.WebView2Host._init_com())

WNDCLASS = type("WNDCLASS", (ctypes.Structure,), {
    "_fields_": [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", ctypes.WINFUNCTYPE(
            ds._LRESULT, ctypes.wintypes.HWND, ctypes.c_uint,
            ds._WPARAM, ds._LPARAM)),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HANDLE),
        ("hbrBackground", ctypes.wintypes.HANDLE),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
    ],
})


def wndproc(hwnd, msg, wparam, lparam):
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


proc = ctypes.WINFUNCTYPE(
    ds._LRESULT, ctypes.wintypes.HWND, ctypes.c_uint,
    ds._WPARAM, ds._LPARAM)(wndproc)
cls = WNDCLASS()
cls.style = ds._CS_HREDRAW | ds._CS_VREDRAW
cls.lpfnWndProc = proc
cls.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
cls.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32512))
cls.lpszClassName = "KaliCodeTrace"
user32.RegisterClassW(ctypes.byref(cls))

hwnd = user32.CreateWindowExW(
    0, "KaliCodeTrace", "Kali Code", ds._WS_OVERLAPPEDWINDOW,
    50, 50, 1200, 800, None, None,
    ctypes.windll.kernel32.GetModuleHandleW(None), None)
user32.ShowWindow(hwnd, 5)
user32.UpdateWindow(hwnd)
print("step 2: hwnd:", hwnd)

# Patch the internals so every stage prints.
orig_env_cb = wv2.WebView2Host._on_env_ready
orig_ctrl_cb = wv2.WebView2Host._on_ctrl_ready


def env_cb(self, error_code, env):
    print("   [env cb] hr:", hex(int(error_code) & 0xFFFFFFFF),
          "env:", hex(env or 0))
    return orig_env_cb(self, error_code, env)


def ctrl_cb(self, error_code, ctrl):
    print("   [ctrl cb] hr:", hex(int(error_code) & 0xFFFFFFFF),
          "ctrl:", hex(ctrl or 0))
    return orig_ctrl_cb(self, error_code, ctrl)


wv2.WebView2Host._on_env_ready = env_cb
wv2.WebView2Host._on_ctrl_ready = ctrl_cb

orig_method = wv2._method


def traced_method(interface, index, restype, argtypes):
    fn = orig_method(interface, index, restype, argtypes)
    return fn


host = wv2.WebView2Host("http://127.0.0.1:8769/", user_data_folder=None)
print("step 3: create...")
ok = host.create(hwnd)
print("step 4: create ->", ok)
print("   env:", hex(wv2._addr(host._env) if host._env else 0))
print("   ctrl:", hex(wv2._addr(host._controller) if host._controller else 0))
print("   webview:", hex(wv2._addr(host._webview) if host._webview else 0))
print("   settings:", hex(wv2._addr(host._settings) if host._settings else 0))
time.sleep(2)
host.close()
user32.DestroyWindow(hwnd)
print("done")
