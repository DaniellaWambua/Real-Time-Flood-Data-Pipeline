"""
CLI script to enrol an existing user in TOTP-based 2FA (db/add_2fa_columns.py,
models.set_totp_secret/enable_totp), without needing the /totp/setup and
/totp/enable routes' QR-code round trip through the frontend. From the
backend/ directory:

    python enable_totp.py <username>

Prints the manual-entry key and, if the qrcode package is available, saves
a scannable PNG next to this script. Scan it (or type the key) into an
authenticator app, then re-run with the --confirm flag and the 6-digit code
it shows to actually switch 2FA on:

    python enable_totp.py <username> --confirm <code>
"""

import sys

import pyotp

import models

TOTP_ISSUER = "Flood Early Warning System"


def main():
    if len(sys.argv) not in (2, 4):
        print(f"Usage: python {sys.argv[0]} <username>")
        print(f"       python {sys.argv[0]} <username> --confirm <code>")
        sys.exit(1)

    username = sys.argv[1]
    user = models.get_user_by_username(username)
    if user is None:
        print(f"Error: no user named '{username}'.")
        sys.exit(1)

    if len(sys.argv) == 4:
        if sys.argv[2] != "--confirm":
            print(f"Usage: python {sys.argv[0]} <username> --confirm <code>")
            sys.exit(1)
        code = sys.argv[3]
        if not user.get("totp_secret"):
            print("Error: run this script without --confirm first to generate a secret.")
            sys.exit(1)
        if not pyotp.TOTP(user["totp_secret"]).verify(code, valid_window=1):
            print("Error: that code didn't verify. Check the time on your phone and this machine match.")
            sys.exit(1)
        models.enable_totp(user["id"])
        print(f"2FA is now enabled for '{username}'.")
        return

    secret = pyotp.random_base32()
    models.set_totp_secret(user["id"], secret)

    uri = pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=TOTP_ISSUER)
    print(f"Secret for '{username}' (enter manually if you can't scan a QR code): {secret}")
    print(f"Provisioning URI: {uri}")

    try:
        import qrcode

        qr_path = f"totp_qr_{username}.png"
        qrcode.make(uri).save(qr_path)
        print(f"QR code saved as an image to backend/{qr_path}.")
        print("The terminal can't display it itself, so it needs opening separately:")
        print(f"  macOS: open {qr_path}")
        print("Then scan it with your authenticator app, or skip it and enter the secret above manually.")

        if sys.platform == "darwin":
            import subprocess

            try:
                subprocess.run(["open", qr_path], check=False)
            except OSError:
                pass
    except ImportError:
        print("(qrcode package not installed, so no PNG was saved; use the manual key above.)")

    print(f"\nOnce your app shows a code, run: python {sys.argv[0]} {username} --confirm <code>")


if __name__ == "__main__":
    main()
