"""
Password quality check, applied wherever a password is set: invite and reset links, the Settings page
and the command-line scripts. Follows NIST SP 800-63B-4: a minimum length, a check against common and
guessable passwords (zxcvbn), and no rules about upper case, digits or symbols.
"""
from zxcvbn import zxcvbn

MIN_LENGTH = 12
MAX_LENGTH = 128
MIN_SCORE = 3  # zxcvbn 0 to 4; 3 is "strong"

# Words anyone would guess for this system. A password may contain them, but must still be strong without them.
SYSTEM_WORDS = ("flood", "floods", "nairobi", "mathare", "ngong", "river", "warning", "password", "strathmore", "kenya")


def _personal_words(username=None, full_name=None, email=None, organisation=None):
    words = [username or ""]
    if email:
        words.append(email.split("@")[0])
    for text in (full_name, organisation):
        words.extend((text or "").split())
    return [w.lower() for w in words if len(w) >= 3]


def _without(password, words):
    rest = password.lower()
    for word in sorted(words, key=len, reverse=True):
        rest = rest.replace(word, "")
    return rest


def check(password, username=None, full_name=None, email=None, organisation=None):
    """None when the password is acceptable, otherwise a sentence saying what to change."""
    if len(password) < MIN_LENGTH:
        return f"password must be at least {MIN_LENGTH} characters"
    if len(password) > MAX_LENGTH:
        return f"password must be at most {MAX_LENGTH} characters"

    personal = _personal_words(username, full_name, email, organisation)
    lowered = password.lower()
    for word in (username, (email or "").split("@")[0]):
        if word and len(word) >= 4 and word.lower() in lowered:
            return "password must not contain your username or email address"

    result = zxcvbn(password, user_inputs=personal + list(SYSTEM_WORDS))
    if result["score"] < MIN_SCORE:
        feedback = result["feedback"]
        hint = feedback.get("warning") or " ".join(feedback.get("suggestions") or [])
        return "password is too easy to guess" + (f". {hint}" if hint else "")

    rest = _without(password, personal + list(SYSTEM_WORDS))
    if not rest.strip() or zxcvbn(rest)["score"] < MIN_SCORE:
        return "password is built around your name or words like flood or Mathare. Add words of your own"
    return None
