from flask import Blueprint, request, jsonify, session, redirect, url_for, flash, render_template, current_app
from werkzeug.security import check_password_hash
import logging
import os

# Blueprint Definition
user_bp = Blueprint('user', __name__)

# Import necessary functions from the main app
from app import ensure_user_id

@user_bp.route('/get_username', methods=['GET'])
def get_username():
    """
    Liefert den Benutzernamen aus der Session
    """
    return jsonify({'username': session.get('user_name', '')})

@user_bp.route('/set_username', methods=['POST'])
def set_username():
    """
    Setzt den Benutzernamen in der Session
    """
    try:
        username = request.form.get('username', '').strip()
        if username:
            session['user_name'] = username
            return jsonify({'success': True, 'username': username})
        return jsonify({'error': 'Kein Benutzername angegeben'}), 400
    except Exception as e:
        logging.error(f"Fehler beim Setzen des Benutzernamens: {str(e)}")
        return jsonify({'error': str(e)}), 500

@user_bp.route('/check_login')
def check_login():
    """
    Prüft, ob der Benutzer eingeloggt ist und liefert entsprechende Informationen zurück
    """
    try:
        # Benutzer-ID sicherstellen
        ensure_user_id()
        
        # Prüfe alle relevanten Session-Daten
        user_id = session.get('user_id', '')
        user_name = session.get('user_name', '')
        seller_id = session.get('seller_id', '')
        email = session.get('email', '')
        
        # Notfall-Modus
        notfall_mode = session.get('notfall_mode', False)
        
        # Daten zurückgeben
        return jsonify({
            'logged_in': bool(user_id),
            'user_id': user_id,
            'user_name': user_name,
            'seller_id': seller_id,
            'email': email,
            'notfall_mode': notfall_mode,
            'session_active': True
        })
    except Exception as e:
        logging.error(f"Fehler bei Login-Check: {str(e)}")
        return jsonify({
            'logged_in': False,
            'error': str(e),
            'session_active': False
        }), 500

@user_bp.route('/reset_session')
def reset_session():
    """
    Setzt die Session zurück, ohne den Benutzer komplett auszuloggen
    (nützlich bei Problemen mit der Session)
    """
    try:
        # Wichtige Daten speichern
        user_id = session.get('user_id', '')
        user_name = session.get('user_name', '')
        seller_id = session.get('seller_id', '')
        email = session.get('email', '')
        
        # Session leeren
        session.clear()
        
        # Wichtige Daten wiederherstellen
        session['user_id'] = user_id
        session['user_name'] = user_name
        session['seller_id'] = seller_id
        session['email'] = email
        
        return jsonify({
            'success': True,
            'message': 'Session zurückgesetzt'
        })
    except Exception as e:
        logging.error(f"Fehler beim Zurücksetzen der Session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@user_bp.route('/toggle_notfall_mode', methods=['POST'])
def toggle_notfall_mode():
    """
    Schaltet den Notfall-Modus ein oder aus
    """
    try:
        current_mode = session.get('notfall_mode', False)
        new_mode = not current_mode
        
        session['notfall_mode'] = new_mode
        
        # Notfall-Ereignis loggen
        user_id = session.get('user_id', 'unknown')
        message = f"Notfall-Modus {'aktiviert' if new_mode else 'deaktiviert'}"
        
        if 'log_notfall_event' in globals():
            from app import log_notfall_event
            log_notfall_event(user_id, 'toggle_mode', message)
        
        return jsonify({
            'success': True,
            'notfall_mode': new_mode,
            'message': f"Notfall-Modus {'aktiviert' if new_mode else 'deaktiviert'}"
        })
    except Exception as e:
        logging.error(f"Fehler beim Umschalten des Notfall-Modus: {str(e)}")
        return jsonify({'error': str(e)}), 500

@user_bp.route('/logout')
def logout():
    """
    Loggt den Benutzer aus und leert die Session
    """
    # Speichere einige Werte für Logging
    try:
        user_id = session.get('user_id', 'unknown')
        user_name = session.get('user_name', 'unknown')
        seller_id = session.get('seller_id', 'unknown')
        
        logging.info(f"Logout für Benutzer: {user_id} ({user_name}), Verkäufer: {seller_id}")
        
        # Session leeren
        session.clear()
        
        flash("Sie wurden erfolgreich abgemeldet.", "success")
    except Exception as e:
        logging.error(f"Fehler beim Logout: {str(e)}")
        flash(f"Fehler beim Abmelden: {str(e)}", "danger")
    
    return redirect(url_for('user.login'))

@user_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Einfache Login-Seite
    """
    # Bei GET-Anfrage, prüfen ob Benutzer bereits eingeloggt ist
    if request.method == 'GET' and session.get('user_id'):
        return redirect(url_for('chat.chat'))
    
    # Bei POST-Anfrage: Login-Formular verarbeiten
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        
        if not username:
            flash("Bitte geben Sie einen Benutzernamen ein.", "warning")
            return redirect(url_for('user.login'))
        
        # Einfacher login ohne Passwort-Prüfung
        session['user_id'] = username.lower()  # Kleinbuchstaben für Konsistenz
        session['user_name'] = username
        
        # Standardwerte für neue Benutzer
        if 'seller_id' not in session:
            session['seller_id'] = "default_seller"
        
        logging.info(f"Login für Benutzer: {username}")
        
        # Erfolgreiche Anmeldung
        flash(f"Willkommen, {username}!", "success")
        
        return redirect(url_for('chat.chat'))
    
    # Login-Formular anzeigen
    return render_template('login.html')

@user_bp.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    """
    Admin-Login mit Passwort-Prüfung
    """
    if request.method == 'POST':
        password = request.form.get('password', '')
        
        # Passwort prüfen
        admin_password_hash = os.environ.get('ADMIN_PASSWORD_HASH')
        
        if not admin_password_hash:
            flash("Admin-Passwort wurde nicht konfiguriert.", "danger")
            return render_template('admin_login.html')
        
        if check_password_hash(admin_password_hash, password):
            # Erfolgreicher Login
            session['admin_authenticated'] = True
            return redirect(url_for('admin.edit'))
        else:
            # Falsches Passwort
            flash("Falsches Passwort.", "danger")
    
    return render_template('admin_login.html')
