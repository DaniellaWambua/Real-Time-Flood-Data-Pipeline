"""
CLI script to change an existing user's password.

Companion to create_user.py: the proposal's authentication module
(3.6.2) implies admin-provisioned accounts rather than public
self-registration, so there is no "forgot password" web flow either.
An admin changes a password the same way an account gets created, from
the backend/ directory:

    python change_password.py <username> <new_password>

Example:
    python change_password.py admin a-new-password123
"""

import sys

import models


def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <username> <new_password>")
        sys.exit(1)

    username, new_password = sys.argv[1], sys.argv[2]

    if models.get_user_by_username(username) is None:
        print(f"Error: no user named '{username}' exists.")
        sys.exit(1)

    models.update_password(username, new_password)
    print(f"Password updated for user '{username}'.")


if __name__ == "__main__":
    main()
