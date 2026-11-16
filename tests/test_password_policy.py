"""
Checks for the password quality rules (backend/password_policy.py): length, common and guessable
passwords, personal details, and passwords built around the system's own words.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import password_policy  # noqa: E402

PERSON = {"username": "officer1", "full_name": "Amina Kariuki", "email": "amina.k@example.org"}


def check(password):
    return password_policy.check(password, **PERSON)


def test_strong_passphrases_are_accepted():
    assert check("kettle sings at dawn") is None
    assert check("correct horse battery staple") is None
    assert check("Tr0ub4dor&3xyz-blue") is None


def test_short_and_overlong_passwords_are_refused():
    assert "at least 12" in check("Xq9!vT2#p")
    assert "at most 128" in check("a" * 129)


def test_common_and_patterned_passwords_are_refused():
    assert "too easy to guess" in check("password123456")
    assert "too easy to guess" in check("qwertyuiopasdf")
    assert "too easy to guess" in check("aaaaaaaaaaaaaaaa")


def test_username_and_email_cannot_be_used():
    assert "username or email" in check("officer1-secure-77")
    assert "username or email" in check("amina.k-blue-kettle")


def test_passwords_built_around_system_words_or_names_are_refused():
    assert "built around" in check("mathare-flood-2024")
    assert "built around" in check("Nairobi River Flood Warning")


def test_no_rules_about_character_types():
    # All lower case, no digits or symbols, but long and unguessable: accepted, as NIST requires
    assert check("blue kettle sings at dawn") is None
