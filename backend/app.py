from flask import Flask, render_template, redirect, url_for, request, session, jsonify
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash
import os
import secrets
from datetime import datetime, timedelta

# Import API routes
from api.routes import api

# Create Flask app
app = Flask(__name__, static_folder='../frontend/build/static', template_folder='../frontend/build')

# Configure app
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Register API routes
app.register_blueprint(api)

# Exempt API routes from CSRF protection for frontend usage
csrf.exempt(api)

# Root route - serve React frontend in production
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Serve the React frontend for any non-API route"""
    return render_template('index.html')

# For development only - remove in production
@app.route('/api/debug/session')
def debug_session():
    """Debug endpoint to view session data (development only)"""
    if app.debug:
        return jsonify({
            'user': session.get('user'),
            'chat_history': session.get('chat_history', []),
            'session_data': dict(session)
        })
    return jsonify({'error': 'Debug endpoints only available in development mode'}), 403

# Handle 404 errors
@app.errorhandler(404)
def not_found(e):
    """Return JSON 404 for API routes, or serve the React app for frontend routes"""
    if request.path.startswith('/api/'):
        return jsonify(error=str(e)), 404
    return render_template('index.html')

if __name__ == '__main__':
    # For development, allow all origins for API requests
    if app.debug:
        from flask_cors import CORS
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)