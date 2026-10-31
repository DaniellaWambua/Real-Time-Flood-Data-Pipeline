"""
CLI script to attach (or clear) a Gmail address on an existing,
already-provisioned user, so that account can also sign in with Google
(routes_auth.py's POST /login/google). From the backend/ directory:

    python set_user_email.py <username> <email>
    python set_user_email.py <username> --clear

This never creates an account; run create_user.py first if the username
doesn't exist yet.
"""

import sys

import models


def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <username> <email>")
        print(f"       python {sys.argv[0]} <username> --clear")
        sys.exit(1)

    username, email_arg = sys.argv[1], sys.argv[2]
    email = None if email_arg == "--clear" else email_arg

    user = models.get_user_by_username(username)
    if user is None:
        print(f"Error: no user named '{username}'.")
        sys.exit(1)

    if email is not None:
        existing = models.get_user_by_email(email)
        if existing is not None and existing["id"] != user["id"]:
            print(f"Error: '{email}' is already linked to another account.")
            sys.exit(1)

    models.set_user_email(user["id"], email)
    if email is None:
        print(f"Cleared the email on '{username}'.")
    else:
        print(f"'{username}' can now sign in with Google using {email}.")


if __name__ == "__main__":
    main()
