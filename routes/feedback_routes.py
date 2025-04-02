from flask import Blueprint, request, jsonify, session, current_app
import logging
import json

# Blueprint Definition
feedback_bp = Blueprint('feedback', __name__)

# Import necessary functions from utils module
from routes.utils import store_feedback

@feedback_bp.route('/store_feedback', methods=['POST'])
def store_feedback_route():
    """
    Speichert Feedback zur UI oder Chat-Antworten
    """
    try:
        # JSON-Daten aus dem Request extrahieren
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'Keine Daten erhalten'}), 400
            
        # Extrahiere die Feedback-Daten
        feedback_type = data.get('type', '')
        comment = data.get('comment', '')
        rated_message = data.get('message', '')
        
        # Prüfe auf erforderliche Felder
        if not feedback_type:
            return jsonify({'success': False, 'error': 'Kein Feedback-Typ angegeben'}), 400
            
        # Chat-Historie aus der Session holen, falls vorhanden
        user_id = session.get('user_id', 'unknown')
        chat_key = f"chat_history_{user_id}"
        chat_history = session.get(chat_key, [])
        
        # Feedback speichern
        store_feedback(feedback_type, comment, chat_history, rated_message)
        
        # Erfolg zurückmelden
        return jsonify({'success': True, 'message': 'Feedback erfolgreich gespeichert'})
    except Exception as e:
        logging.error(f"Fehler beim Speichern des Feedbacks: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
