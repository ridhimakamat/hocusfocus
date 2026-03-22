"""
FocusFlow — auth.py
Simple local auth using a JSON file.
Passwords hashed with hashlib (built-in, no install needed).
"""

import json
import os
import hashlib
import secrets

USERS_FILE = "users.json"


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def _load() -> dict:
    if not os.path.isfile(USERS_FILE):
        return {}
    with open(USERS_FILE, "r") as f:
        return json.load(f)


def _save(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def register(name: str, email: str, password: str):
    """Returns (success, message)."""
    email = email.strip().lower()
    users = _load()
    if email in users:
        return False, "An account with this email already exists."
    salt   = secrets.token_hex(16)
    hashed = _hash(password, salt)
    users[email] = {"name": name.strip(), "email": email,
                    "password": hashed, "salt": salt}
    _save(users)
    return True, "Account created successfully."


def login(email: str, password: str):
    """Returns (success, message, user_dict)."""
    email = email.strip().lower()
    users = _load()
    if email not in users:
        return False, "No account found with that email.", {}
    user = users[email]
    if _hash(password, user["salt"]) != user["password"]:
        return False, "Incorrect password.", {}
    return True, "Welcome back!", {"email": email, "name": user["name"]}


def get_user(email: str) -> dict:
    users = _load()
    return users.get(email.lower(), {})
