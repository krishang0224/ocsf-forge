"""Explicit authentication actions and outcomes for structured logs."""

import re

AUTH_ACTIONS = {
    "login": (1, "Logon", "Unknown"),
    "logon": (1, "Logon", "Unknown"),
    "authentication": (1, "Logon", "Unknown"),
    "authenticate": (1, "Logon", "Unknown"),
    "login_success": (1, "Logon", "Success"),
    "logon_success": (1, "Logon", "Success"),
    "authentication_success": (1, "Logon", "Success"),
    "login_failure": (1, "Logon", "Failure"),
    "login_failed": (1, "Logon", "Failure"),
    "failed_login": (1, "Logon", "Failure"),
    "logon_failure": (1, "Logon", "Failure"),
    "authentication_failure": (1, "Logon", "Failure"),
    "logout": (2, "Logoff", "Unknown"),
    "logoff": (2, "Logoff", "Unknown"),
}
OUTCOMES = {
    "success": "Success", "successful": "Success", "succeeded": "Success", "allowed": "Success",
    "failure": "Failure", "failed": "Failure", "denied": "Failure", "blocked": "Failure",
}


def authentication_action(action: str, item: dict) -> tuple[int, str, str] | None:
    normalized = re.sub(r"[\s.-]+", "_", action.strip().lower())
    classification = AUTH_ACTIONS.get(normalized)
    if classification is None:
        return None
    activity, name, implied = classification
    explicit = {
        OUTCOMES.get(str(item[key]).strip().lower(), "Unknown")
        for key in ("status", "outcome") if key in item
    }
    known = (explicit | {implied}) - {"Unknown"}
    if len(known) > 1:
        raise ValueError("Conflicting authentication outcomes")
    return activity, name, next(iter(known), "Unknown")
