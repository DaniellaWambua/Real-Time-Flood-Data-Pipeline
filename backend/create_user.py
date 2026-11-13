"""
Create a user. Accounts are provisioned by an administrator; there is no public registration.
From backend/:

    python create_user.py <username> <password> <role> [email]

Roles are listed in config.ROLES. The email is only needed for Google sign-in
(it can be added later with set_user_email.py).
"""

import sys

import config
import models


def main():
    if len(sys.argv) not in (4, 5):
        print(f"Usage: python {sys.argv[0]} <username> <password> <role> [email]")
        print(f"Valid roles: {', '.join(config.ROLES)}")
        sys.exit(1)

    username, password, role = sys.argv[1], sys.argv[2], sys.argv[3]
    email = sys.argv[4] if len(sys.argv) == 5 else None

    if role not in config.ROLES:
        print(f"Error: '{role}' is not a valid role.")
        print(f"Valid roles: {', '.join(config.ROLES)}")
        sys.exit(1)

    if models.get_user_by_username(username) is not None:
        print(f"Error: a user named '{username}' already exists.")
        sys.exit(1)

    if email is not None and models.get_user_by_email(email) is not None:
        print(f"Error: '{email}' is already linked to another account.")
        sys.exit(1)

    user_id = models.create_user(username, password, role, email=email)
    print(f"Created user '{username}' (id={user_id}, role={role}, email={email}).")


if __name__ == "__main__":
    main()
