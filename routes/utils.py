"""
Shared utility functions for the XORA application.
This module contains functions and decorators used across multiple blueprints.
"""

import logging
from functools import wraps
from flask import session, jsonify

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
