"""Build the Kali Code Android APK.

Sets up the Android SDK location (ANDROID_SDK_ROOT / local.properties), then
runs the Gradle wrapper.

Usage:
    python tools/build_apk.py                 # debug APK
    python tools/build_apk.py --release       # release APK
    python tools/build_apk.py --clean

The SDK is expected at:
    %LOCALAPPDATA%\\Temp\\opencode\\android\\sdk
unless ANDROID_SDK_ROOT points somewhere else.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID_DIR = ROOT / "android"

DEFAULT_SDK = Path(
    os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
) / "Temp" / "opencode" / "android" / "sdk"

# A JDK that can run Gradle 8.10 + AGP 8.7 (Java 17+).
JDK_CANDIDATES = [
    os.environ.get("JAVA_HOME", ""),
    r"C:\Users\milanvivas\tools\jdk-21.0.13+9",
    r"C:\Program Files\Java\jdk-21",
    r"C:\Program Files\Eclipse Adoptium\jdk-21",
]


def find_sdk() -> Path | None:
    candidates = [
        os.environ.get("ANDROID_SDK_ROOT", ""),
        os.environ.get("ANDROID_HOME", ""),
        str(DEFAULT_SDK),
        str(Path.home() / "AppData" / "Local" / "Android" / "Sdk"),
    ]
    for c in candidates:
        if c and (Path(c) / "platform-tools").exists():
            return Path(c)
    return None


def find_java() -> str | None:
    for c in JDK_CANDIDATES:
        if c and (Path(c) / "bin" / "java.exe").exists():
            return c
    found = shutil.which("java")
    if found:
        return str(Path(found).parent.parent)
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the Kali Code APK")
    ap.add_argument("--release", action="store_true",
                    help="build the release APK instead of debug")
    ap.add_argument("--clean", action="store_true", help="clean before building")
    ap.add_argument("--sdk", default=None, help="path to the Android SDK")
    args = ap.parse_args()

    sdk = Path(args.sdk) if args.sdk else find_sdk()
    if not sdk:
        print("Android SDK not found. Set ANDROID_SDK_ROOT or pass --sdk.")
        return 1
    print(f"SDK: {sdk}")

    java_home = find_java()
    if not java_home:
        print("A JDK 17+ is required (set JAVA_HOME).")
        return 1
    print(f"JDK: {java_home}")

    env = dict(os.environ)
    env["ANDROID_SDK_ROOT"] = str(sdk)
    env["ANDROID_HOME"] = str(sdk)
    env["JAVA_HOME"] = java_home
    env["PATH"] = str(Path(java_home) / "bin") + os.pathsep + env.get("PATH", "")

    # local.properties tells Gradle where the SDK is.
    # AGP's SdkLocator rejects a Windows path with backslashes, so use
    # forward slashes here.
    (ANDROID_DIR / "local.properties").write_text(
        f"sdk.dir={sdk.as_posix()}\n", encoding="utf-8")

    task = "assembleRelease" if args.release else "assembleDebug"
    cmd = [str(ANDROID_DIR / ("gradlew.bat" if os.name == "nt" else "gradlew"))]
    if args.clean:
        cmd.append("clean")
    cmd.append(task)

    print("running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=ANDROID_DIR, env=env)
    if result.returncode != 0:
        return result.returncode

    apk_dir = ANDROID_DIR / "app" / "build" / "outputs" / "apk"
    for apk in sorted(apk_dir.rglob("*.apk")):
        size = apk.stat().st_size / (1024 * 1024)
        print(f"Built: {apk}  ({size:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
