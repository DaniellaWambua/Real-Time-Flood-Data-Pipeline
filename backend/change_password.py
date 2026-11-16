"""
Change a user's password. From backend/:

    python change_password.py <username> <new_password>
"""

import sys

import models
import password_policy


def main():
    if len(sys.argv) != 3:
        print(f"Usage: python {sys.argv[0]} <username> <new_password>")
        sys.exit(1)

    username, new_password = sys.argv[1], sys.argv[2]

    user = models.get_user_by_username(username)
    if user is None:
        print(f"Error: no user named '{username}' exists.")
        sys.exit(1)

    problem = password_policy.check(new_password, username, user.get("full_name"), user.get("email"),
                                    user.get("organisation"))
    if problem:
        print(f"Error: {problem}.")
        sys.exit(1)

    models.update_password(username, new_password)
    print(f"Password updated for user '{username}'.")


if __name__ == "__main__":
    main()
