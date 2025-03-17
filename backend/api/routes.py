from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import check_password_hash
import json
import time
from datetime import datetime

api = Blueprint('api', __name__, url_prefix='/api')

# Authentication routes
@api.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'message': 'Username is required'}), 400
    
    # Store user in session
    session['user'] = {
        'id': str(int(time.time())),  # Simple ID based on timestamp
        'name': username,
        'role': 'user'
    }
    
    return jsonify({
        'success': True,
        'user': session['user'],
        'message': 'Login successful'
    })

@api.route('/auth/admin-login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400
    
    # In a real application, you would validate against a database
    # This is a placeholder for demonstration
    if email == 'admin@xora.com' and password == 'admin123':
        session['user'] = {
            'id': 'admin-1',
            'name': 'Admin User',
            'email': email,
            'role': 'admin'
        }
        return jsonify({
            'success': True,
            'user': session['user'],
            'message': 'Admin login successful'
        })
    
    return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

@api.route('/auth/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    session.pop('chat_history', None)
    
    return jsonify({
        'success': True,
        'message': 'Logout successful'
    })

@api.route('/auth/status', methods=['GET'])
def auth_status():
    user = session.get('user')
    
    return jsonify({
        'isAuthenticated': bool(user),
        'user': user
    })

# Chat routes
@api.route('/chat/history', methods=['GET'])
def get_chat_history():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    chat_history = session.get('chat_history', [])
    
    return jsonify({
        'success': True,
        'history': chat_history
    })

@api.route('/chat/message', methods=['POST'])
def send_message():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    data = request.get_json()
    user_message = data.get('message')
    notfall_mode = data.get('notfallmodus') == '1'
    stream = data.get('stream', False)
    
    if not user_message:
        return jsonify({'success': False, 'message': 'Message is required'}), 400
    
    # Process message through the existing backend logic
    # For now, we'll simulate a response
    bot_response = generate_bot_response(user_message, notfall_mode)
    
    # Save to chat history
    if 'chat_history' not in session:
        session['chat_history'] = []
    
    message_id = f"{int(time.time())}-{len(session['chat_history'])}"
    
    session['chat_history'].append({
        'id': f"user-{message_id}",
        'role': 'user',
        'content': user_message,
        'timestamp': datetime.now().isoformat()
    })
    
    session['chat_history'].append({
        'id': f"bot-{message_id}",
        'role': 'bot',
        'content': bot_response,
        'timestamp': datetime.now().isoformat()
    })
    
    # Save session after modification
    session.modified = True
    
    return jsonify({
        'success': True,
        'response': bot_response,
        'message_id': f"bot-{message_id}"
    })

@api.route('/chat/clear', methods=['POST'])
def clear_chat():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    session.pop('chat_history', None)
    
    return jsonify({
        'success': True,
        'message': 'Chat history cleared'
    })

@api.route('/feedback', methods=['POST'])
def store_feedback():
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    data = request.get_json()
    message_id = data.get('message_id')
    feedback_type = data.get('feedback_type')
    comment = data.get('comment', '')
    
    if not message_id or not feedback_type:
        return jsonify({'success': False, 'message': 'Message ID and feedback type are required'}), 400
    
    # In a real application, you would store feedback in a database
    # For now, we'll just acknowledge it
    
    # Update feedback in chat history if possible
    chat_history = session.get('chat_history', [])
    for message in chat_history:
        if message.get('id') == message_id:
            message['feedback'] = feedback_type
            session.modified = True
            break
    
    return jsonify({
        'success': True,
        'message': 'Feedback submitted successfully'
    })

# Helper function to simulate bot responses
def generate_bot_response(user_message, notfall_mode=False):
    
    # In a real implementation, this would connect to your existing logic
    # For demonstration, we'll create a simple response
    
    if notfall_mode:
        return f"EMERGENCY MODE ACTIVE. I'll prioritize your request: '{user_message}'. Please provide any additional details about the emergency situation."
    
    if 'hello' in user_message.lower() or 'hi' in user_message.lower():
        return "Hello! I'm XORA, your Pflegehilfe für Senioren Companion. How can I assist you today?"
        
    if 'customer' in user_message.lower() or 'kunden' in user_message.lower():
        return "I can help you with customer information. Please provide more specific details about what you're looking for, such as active customers, contract terminations, or customer history."
        
    if 'agency' in user_message.lower() or 'agentur' in user_message.lower():
        return "I can provide information about agencies. We work with several agencies like Senioport, Medipe, and Promedica. What specific information are you looking for?"
        
    if 'care stay' in user_message.lower() or 'carestay' in user_message.lower() or 'einsatz' in user_message.lower():
        return "Care stays are managed through our system. We currently have multiple active care stays. Would you like to know about specific care stays, or summary statistics?"
    
    return "I understand you're asking about: '" + user_message + "'. To provide the most accurate information, could you please be more specific about what you need?"
