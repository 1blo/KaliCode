"""Generate a release keystore for the Kali Code Android app.

The keystore and its passwords stay OUT of git. Only
`keystore.properties.example` is committed.

Usage:
    python tools/make_keystore.py
    python tools/make_keystore.py --password "mysecret" --alias kalicode
"""
from __future__ import annotations

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID_DIR = ROOT / "android"
KEYSTORE = ANDROID_DIR / "kali-release.jks"
PROPS = ANDROID_DIR / "keystore.properties"

EXAMPLE = """# Copy to keystore.properties and fill in your values.
# keystore.properties is git-ignored - never commit the real one.
storeFile=kali-release.jks
storePassword=CHANGE_ME
keyAlias=kalicode
keyPassword=CHANGE_ME
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate the Android release keystore")
    ap.add_argument("--password", default=None,
                    help="the store/key password (generated if omitted)")
    ap.add_argument("--alias", default="kalicode", help="the key alias")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing keystore")
    args = ap.parse_args()

    if KEYSTORE.exists() and not args.force:
        print(f"{KEYSTORE} already exists (use --force to replace it)")
        return 1

    password = args.password or secrets.token_urlsafe(18)

    keytool = Path(
        subprocess.run(["where", "keytool"], capture_output=True, text=True,
                       shell=True).stdout.splitlines()[0]
    )
    if not keytool.exists():
        print("keytool not found - is a JDK installed?")
        return 1

    cmd = [
        str(keytool), "-genkeypair", "-v",
        "-keystore", str(KEYSTORE),
        "-alias", args.alias,
        "-keyalg", "RSA", "-keysize", "2048",
        "-validity", "10000",
        "-storepass", password,
        "-keypass", password,
        "-dname", "CN=Kali Code, OU=Software, O=Kali Code, L=Internet, C=US",
    ]
    print("running:", " ".join(cmd[:6]), "...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[:800])
        return result.returncode

    PROPS.write_text(
        f"storeFile={KEYSTORE.name}\n"
        f"storePassword={password}\n"
        f"keyAlias={args.alias}\n"
        f"keyPassword={password}\n",
        encoding="utf-8",
    )
    (ANDROID_DIR / "keystore.properties.example").write_text(EXAMPLE, encoding="utf-8")

    print(f"\nKeystore: {KEYSTORE}")
    print(f"Properties: {PROPS}")
    print("\nThe password was generated. Store it somewhere safe - you need it")
    print("to sign future releases, and it cannot be recovered from the APK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
