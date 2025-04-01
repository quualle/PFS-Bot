# routes/auth.py

import os
import json
import uuid
import logging
import requests
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app
from werkzeug.security import check_password_hash # Assuming used for standard login
from dotenv import load_dotenv

# Load environment variables (needed for Google creds etc.)
load_dotenv()

auth_bp = Blueprint('auth', __name__)

# --- Helper Functions (Potentially move to a utils/user_management module later) ---

# Placeholder: Replace with your actual BigQuery function to get user by email
def get_user_id_from_email(email):
    print(f"WARN: Dummy get_user_id_from_email for {email}")
    # Example Logic (replace with BQ query)
    if email == "marco.heer@pflegehilfe-senioren.de":
        return "62d00b56a384fd908f7f5a6c"
    if email == "gf@pflegehilfe-senioren.de":
         return "62d00b56a384fd908f7f5a6c" # Using Marco's ID for Norman as per original code
    return None # Default if not found

# Placeholder: Replace with your actual BigQuery function to get user by username
# This needs to fetch the HASHED password
def get_user_by_username(username):
    print(f"WARN: Dummy get_user_by_username for {username}")
    # Example (Replace with BQ query returning hashed password)
    # DO NOT STORE PLAIN TEXT PASSWORDS
    # Use werkzeug.security.generate_password_hash to store hashes
    if username == "admin": # Example admin user
        # Example hash for password 'adminpass'. Generate properly!
        hashed_pass = 'pbkdf2:sha256:600000$...' # Replace with actual hash
        return {'id': 'admin001', 'username': 'admin', 'password': hashed_pass, 'role': 'admin'}
    # Add logic for regular users if standard login is used
    return None

# --- Google OAuth Routes ---

@auth_bp.route('/google_login')
def google_login():
    """Initiates the Google OAuth2 login flow."""
    redirect_uri = url_for('auth.google_callback', _external=True)
    google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        'client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'email profile openid',
        'access_type': 'online'
    }
    auth_url = f"{google_auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return redirect(auth_url)

@auth_bp.route('/google_callback')
def google_callback():
    """Handles the callback from Google after user authorization."""
    code = request.args.get('code')
    if not code:
        flash('Google login failed (no code received).', 'danger')
        return redirect(url_for('auth.login'))

    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'code': code,
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'redirect_uri': url_for('auth.google_callback', _external=True),
            'grant_type': 'authorization_code'
        }
        token_response = requests.post(token_url, data=token_data)
        token_response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        token_info = token_response.json()
        access_token = token_info['access_token']

        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()

        email = user_info.get('email')
        name = user_info.get('name')

        if not email:
            flash('Google login failed (could not retrieve email).', 'danger')
            return redirect(url_for('auth.login'))
            
        # Ensure user_id exists or create a new one
        user_id = session.get('user_id') or str(uuid.uuid4())
        session['user_id'] = user_id
        
        session['email'] = email
        session['google_user_email'] = email # Explicitly store google email
        session['user_name'] = name # Use Google name by default
        session['is_logged_via_google'] = True
        session['access_token'] = access_token # Store token if needed for API calls

        # Get seller_id based on email
        seller_id = get_user_id_from_email(email)
        session['seller_id'] = seller_id
        if not seller_id:
             logging.warning(f"No Seller ID found for Google logged-in user: {email}")

        # --- Special handling for specific emails (Keep as is from original) ---
        marco_id = "62d00b56a384fd908f7f5a6c"
        norman_email = "gf@pflegehilfe-senioren.de"
        marco_email = "marco.heer@pflegehilfe-senioren.de"
        if email == norman_email:
            logging.warning(f"Special Handling: Norman logged in ({email}), using Marco's ID: {marco_id}")
            session['user_id'] = marco_id
            session['seller_id'] = marco_id
        elif email == marco_email:
            logging.warning(f"Special Handling: Marco logged in ({email}), ensuring correct ID: {marco_id}")
            session['user_id'] = marco_id
            session['seller_id'] = marco_id
        # --- End Special Handling ---
        
        session.modified = True
        flash(f'Successfully logged in as {name} ({email}) via Google.', 'success')
        # Redirect to chat or appropriate dashboard based on role (if applicable)
        return redirect(url_for('chat.chat_route')) # Assuming chat blueprint is 'chat'

    except requests.exceptions.RequestException as e:
        logging.error(f"Google OAuth network error: {e}", exc_info=True)
        flash(f'Google login network error: {e}', 'danger')
    except Exception as e:
        logging.error(f"Google OAuth callback error: {e}", exc_info=True)
        flash(f'An error occurred during Google login: {e}', 'danger')
        
    return redirect(url_for('auth.login'))

# --- Standard Login/Logout Routes ---

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handles standard username/password login and Admin password login."""
    if 'user_id' in session and session.get('is_logged_via_google'):
         return redirect(url_for('chat.chat_route')) # Already logged in via Google
    if 'admin_logged_in' in session:
         return redirect(url_for('admin_topic_editor.admin_dashboard')) # Assuming admin blueprint

    if request.method == 'POST':
        # Check for Admin Password first (based on original code structure)
        password = request.form.get('password', '')
        admin_password = os.getenv('ADMIN_PASSWORD', None)
        
        if admin_password and password == admin_password:
            session['admin_logged_in'] = True
            session['role'] = 'admin' # Assign role
            flash('Successfully logged in as Administrator.', 'success')
            return redirect(url_for('admin_topic_editor.admin_dashboard')) # Redirect to admin page
        else:
            # --- Implement Standard User Login (if applicable) ---
            # username = request.form.get('username')
            # user_data = get_user_by_username(username) # Fetch user incl. hashed password
            # if user_data and check_password_hash(user_data.get('password', ''), password):
            #     session['user_id'] = user_data['id']
            #     session['username'] = user_data['username']
            #     session['role'] = user_data.get('role', 'user')
            #     flash('Login successful!', 'success')
            #     return redirect(url_for('chat.chat_route'))
            # --- End Standard User Login --- 
            
            flash('Invalid password.', 'danger') # Or Invalid credentials if standard login used
            # No redirect here, just re-render the login page with the flash message
            
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    """Logs the user out by clearing the session."""
    was_admin = session.get('admin_logged_in')
    session.clear()
    flash('Successfully logged out.', 'success')
    if was_admin:
        return redirect(url_for('auth.login')) # Admins go back to login
    else:
        # For Google users, redirecting might trigger auto-login again if cookies persist.
        # Consider redirecting to a logged-out confirmation page or Google's logout URL.
        return redirect(url_for('auth.login')) 

@auth_bp.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    """Handles the specific admin password login (seems redundant with /login)."""
    # This seems to duplicate the admin password check in /login
    # Recommend consolidating into /login unless there's a specific reason
    if request.method == 'POST':
        password = request.form.get('password', '')
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if admin_password and password == admin_password:
            session.clear() # Clear previous session if any
            session['admin_logged_in'] = True
            session['role'] = 'admin'
            flash('Successfully logged in as Administrator.', 'success')
            return redirect(url_for('admin_topic_editor.admin_dashboard'))
        else:
            flash('Invalid Admin Password.', 'danger')
            
    return render_template('admin_login.html')

# --- Session Info / Management Routes ---

@auth_bp.route('/check_login')
def check_login():
    """Debug route to display current session status."""
    if not session.get('admin_logged_in'): # Protect this debug route maybe?
        # Or check for a specific debug user role
        # return "Access Denied", 403
        pass # Currently open
        
    session_data = dict(session)
    output = "<h1>Login Status</h1>"
    # Mask sensitive keys before displaying
    keys_to_mask = ['access_token'] # Add other sensitive keys if needed
    for key in keys_to_mask:
        if key in session_data:
            session_data[key] = "********"
            
    output += "<pre>" + json.dumps(session_data, indent=2) + "</pre>"
    output += "<p><a href='/reset_session'>Reset Session (Keep user_id)</a></p>"
    output += "<p><a href='/logout'>Full Logout</a></p>"
    return output

@auth_bp.route('/reset_session')
def reset_session():
    """Clears most session data but keeps user_id."""
    user_id = session.get('user_id')
    is_admin = session.get('admin_logged_in')
    session.clear()
    if user_id:
        session['user_id'] = user_id
    if is_admin: # Preserve admin status if desired during reset
         session['admin_logged_in'] = True
         session['role'] = 'admin'
    session.modified = True
    flash('Session reset (user_id kept).', 'info')
    return redirect(url_for('auth.check_login'))

# --- Username Routes ---

@auth_bp.route('/get_username', methods=['GET'])
def get_username():
    """API endpoint to get the current user's name from session."""
    user_name = session.get('user_name', 'Gast') # Default to 'Guest'
    return jsonify({'user_name': user_name}), 200

@auth_bp.route('/set_username', methods=['POST'])
def set_username():
    """API endpoint to set the user's name in the session."""
    # Consider if this is needed if Google provides the name
    username = request.form.get('username', '').strip()
    if not username:
         return jsonify({'success': False, 'message': 'Username cannot be empty.'}), 400
    if len(username) < 2:
        return jsonify({'success': False, 'message': 'Username too short.'}), 400
        
    session['user_name'] = username
    session.modified = True
    return jsonify({'success': True, 'user_name': username}), 200

# Ensure templates 'login.html', 'admin_login.html' exist
# Ensure chat blueprint is named 'chat' and has 'chat_route'
# Ensure admin blueprint is named 'admin_topic_editor' and has 'admin_dashboard'
