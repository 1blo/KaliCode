# Kali Code 1.1.0

Released 2026-11-25.

## What's new in 1.1.0

### A desktop app

Kali Code is no longer terminal-only. `KaliCode.exe --gui` opens a
native window with a session rail, the conversation, a details panel
and a row of panes for changes, files, the plan and tasks - the
same shape as the Claude app. It runs on the WebView2 runtime that
ships with Windows, so there is nothing extra to install.

The window starts its own server and connects by itself, so there is
no access token to copy. If WebView2 is missing it falls back to your
default browser.

### A native Android app

A Kotlin + Jetpack Compose client for the same server: streaming
chat, tool cards, permission prompts, model and permission-mode
pickers, and automatic reconnection. The phone is always a client -
the agent runs on the server.

### One session-aware server

The server keeps a registry of sessions. The desktop app, the phone
app and the browser PWA all talk to the same server over the same
protocol, and can watch the same session at the same time.

## Included

### Windows

- `KaliCode.exe` - the single-file executable.
- `KaliCode-1.1.0-win64.zip` - the executable in a zip.

Run `KaliCode.exe --gui` for the desktop app, or `KaliCode.exe` for the terminal.

### Android

- `KaliCode-1.1.0-android.apk` - the native phone client.

Install it on the phone, then enter your server URL and the access token printed by the server. The desktop app writes both to `%LOCALAPPDATA%\KaliCode\desktop.json`.

## Checksums

```
2ac1beb031b319bb08d6ff4f614fd69a13500d1fcedc58d5ffc98f07e41a4086  KaliCode-1.1.0-android.apk
dcecf702fecf9583f76c6525aedbc9b16c00cfcc332c8038452df2437691a4d5  KaliCode-1.1.0-win64.zip
26c0e35b8e48221ddc02b8d79bdbaa28dfc033ea3c107628169aa9d7efb0631f  KaliCode.exe
```
