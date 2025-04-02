"""
Shared utility functions for the XORA application.
This module contains functions and decorators used across multiple blueprints.
"""

import logging
from functools import wraps
from flask import session, jsonify
import uuid  # Für UUID-Generierung in ensure_user_id
import os  # Für Dateipfad-Operationen
from datetime import datetime  # Für Zeitstempel bei Feedback

# Konstanten
FEEDBACK_FOLDER = 'feedback'  # Aus app.py übernommen
if not os.path.exists(FEEDBACK_FOLDER):
    os.makedirs(FEEDBACK_FOLDER)

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

def store_feedback(feedback_type, comment, chat_history, rated_message=""):
    """
    Speichert das Feedback als Textdatei im FEEDBACK_FOLDER.
    
    Args:
        feedback_type: Art des Feedbacks (UI, Antwort, etc.)
        comment: Kommentar des Benutzers
        chat_history: Liste der Chat-Nachrichten
        rated_message: Optional, spezifische Nachricht, die bewertet wird
    """
    # Make sure the feedback directory exists
    os.makedirs(FEEDBACK_FOLDER, exist_ok=True)
    
    name_in_session = session.get('user_name', 'Unbekannt')
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{name_in_session}_{feedback_type}_{timestamp_str}.txt"
    filepath = os.path.join(FEEDBACK_FOLDER, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Feedback-Typ: {feedback_type}\n")
        f.write(f"Zeitpunkt: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        f.write(f"Benutzer: {name_in_session}\n\n")
        
        # Add the specific message being rated
        if rated_message:
            f.write(f"Bewertete Nachricht:\n{rated_message}\n\n")
            
        f.write(f"Kommentar:\n{comment}\n\n")
        f.write("----- Chatverlauf -----\n\n")
        for idx, convo in enumerate(chat_history):
            user_msg = convo.get('user', '').replace('\n', ' ')
            bot_msg = convo.get('bot', '').replace('\n', ' ')
            f.write(f"Nachricht {idx+1}:\n")
            f.write(f"  User: {user_msg}\n")
            f.write(f"  Bot : {bot_msg}\n\n")
