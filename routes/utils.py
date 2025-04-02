"""
Shared utility functions for the XORA application.
This module contains functions and decorators used across multiple blueprints.
"""

import logging
from functools import wraps
from flask import session, jsonify
import uuid  # Für UUID-Generierung in ensure_user_id

# Authentication decorator
def login_required(f):
    """
    Decorator that ensures a user is logged in before accessing a route.
    If not logged in, returns a 401 authentication error.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:  # Basic check, improve as needed
             logging.warning("Access denied: User not logged in.")
             return jsonify({"error": "Authentication required", "status": "error"}), 401
        return f(*args, **kwargs)
    return decorated_function

def debug_print(category, message):
    """
    Print debug messages with a category prefix.
    Used for development and troubleshooting.
    """
    print(f"DEBUG [{category}]: {message}")
    logging.debug(f"[{category}] {message}")

def ensure_user_id():
    """
    Stellt sicher, dass ein user_id in der Session existiert.
    Erzeugt eine neue UUID, wenn keine vorhanden ist.
    """
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
