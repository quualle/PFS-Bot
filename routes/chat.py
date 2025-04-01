# routes/chat.py

import os
import json
import logging
import traceback
from flask import (
    Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, Response, current_app
)

# Placeholder for dependencies (to be imported/moved later)
# from .. import db # Example for database
# from ..utils import store_chatlog, store_feedback, get_user_id_from_email, log_notfall_event
# from ..llm_logic import (
#     download_wissensbasis, create_system_prompt, create_function_definitions,
#     select_optimal_tool_with_reasoning, stream_response, stream_text_response,
#     generate_clarification_stream, process_direct_conversation, load_tool_config,
#     extract_date_params # Assuming these are defined elsewhere
# )
# import openai # Assuming openai client is configured in app factory

chat_bp = Blueprint('chat', __name__, template_folder='../templates') # Point to parent templates

# --- Placeholder Functions (Replace with actual imports/logic) ---
def get_user_id_from_email(email):
    print(f"WARN: Dummy get_user_id_from_email called in chat.py for {email}")
    # Replace with actual logic from app.py or utils
    if email == "marco.heer@pflegehilfe-senioren.de": return "62d00b56a384fd908f7f5a6c"
    if email == "gf@pflegehilfe-senioren.de": return "62d00b56a384fd908f7f5a6c"
    return None

def download_wissensbasis():
    print("WARN: Dummy download_wissensbasis called in chat.py")
    # Replace with actual logic
    try:
        # Simulate loading from a file relative to the main app path maybe?
        # Need robust path handling here.
        # Assuming app.py is in the root for now:
        # base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # file_path = os.path.join(base_path, 'wissensbasis.json')
        # with open(file_path, 'r', encoding='utf-8') as f:
        #     return json.load(f)
        return {"General": {"Welcome": {"description": "Welcome message", "inhalt": ["Hello!"]}}}
    except Exception as e:
        logging.error(f"Dummy download_wissensbasis error: {e}")
        return None

def log_notfall_event(user_id, art, msg):
     print(f"WARN: Dummy log_notfall_event called for user {user_id}, type: {art}")
     pass # Replace with actual logging

def create_system_prompt(schema):
     print("WARN: Dummy create_system_prompt called")
     return "You are a helpful assistant." # Replace

def create_function_definitions():
     print("WARN: Dummy create_function_definitions called")
     return [] # Replace
     
def extract_date_params(text):
     print("WARN: Dummy extract_date_params called")
     return {} # Replace

def select_optimal_tool_with_reasoning(msg, tools, config):
     print("WARN: Dummy select_optimal_tool_with_reasoning called")
     return "direct_conversation", "Defaulting to conversation" # Replace
     
def load_tool_config():
     print("WARN: Dummy load_tool_config called")
     return {} # Replace

def stream_response(*args, **kwargs):
    print("WARN: Dummy stream_response called")
    def generator():
        yield "event: message\ndata: {\"text\": \"(Dummy Stream Response)\"}\n\n"
        yield "event: end\ndata: {}\n\n"
    return generator() # Replace
    
def generate_clarification_stream(*args, **kwargs):
    print("WARN: Dummy generate_clarification_stream called")
    def generator():
        yield "event: message\ndata: {\"text\": \"(Dummy Clarification Stream)\"}\n\n"
        yield "event: end\ndata: {}\n\n"
    return generator() # Replace

def stream_text_response(*args, **kwargs):
    print("WARN: Dummy stream_text_response called")
    def generator():
        yield "event: message\ndata: {\"text\": \"(Dummy Text Stream)\"}\n\n"
        yield "event: end\ndata: {}\n\n"
    return generator() # Replace
    
def process_direct_conversation(*args, **kwargs):
    print("WARN: Dummy process_direct_conversation called")
    def generator():
        yield "event: message\ndata: {\"text\": \"(Dummy Direct Conversation)\"}\n\n"
        yield "event: end\ndata: {}\n\n"
    return generator() # Replace

def store_chatlog(user_name, history):
    print(f"WARN: Dummy store_chatlog called for {user_name}")
    pass # Replace

def store_feedback(feedback_type, comment, chat_history, message):
    print(f"WARN: Dummy store_feedback called: {feedback_type}")
    pass # Replace

# --- Routes --- 

@chat_bp.route("/", methods=["GET"])
def redirect_to_chat():
    """Redirects the root URL to the main chat interface."""
    return redirect(url_for('.chat_route')) # Use relative blueprint redirect
    
@chat_bp.route("/chat", methods=["GET", "POST"])
def chat_route():
    """Main chat interface route."""
    try:
        # --- Session & User Check (Requires auth blueprint logic first) ---
        # This assumes user is already authenticated by a middleware or auth check
        user_id = session.get("user_id")
        user_name = session.get("user_name")

        # If no username, redirect to login (likely handled by @login_required later)
        if not user_name:
            # Assuming the auth blueprint is named 'auth'
            flash("Please log in to access the chat.", "warning")
            return redirect(url_for("auth.login")) 

        seller_id = session.get("seller_id")
        # Attempt to get seller_id if missing and email exists
        if not seller_id and session.get("email"):
            seller_id = get_user_id_from_email(session.get("email"))
            if seller_id:
                session["seller_id"] = seller_id
                session.modified = True
                
        # --- Chat History Management ---
        chat_key = f"chat_history_{user_id}"
        if chat_key not in session:
            session[chat_key] = []
        chat_history = session[chat_key]
        display_chat_history = chat_history # Keep it simple for now

        # --- Load Schemas/Patterns (Need robust path handling) ---
        try:
            # Assuming these files are in the root relative to app.py
            # base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # with open(os.path.join(base_path, "table_schema.json"), "r", encoding="utf-8") as f:
            #     table_schema = json.load(f)
            # with open(os.path.join(base_path, "query_patterns.json"), "r", encoding="utf-8") as f:
            #     query_patterns = json.load(f)
            table_schema = {"tables": {}} # Dummy data
            query_patterns = {"common_queries": {}} # Dummy data
        except Exception as e:
            logging.error(f"Error loading schema/pattern files in chat blueprint: {e}")
            table_schema = {"tables": {}}
            query_patterns = {"common_queries": {}}
            flash("Error loading configuration files.", "danger")

        # --- POST Request Handling (LLM Interaction) ---
        if request.method == "POST":
            user_message = request.form.get("message", "").strip()
            notfall_aktiv = request.form.get("notfallmodus") == "1"
            notfall_art = request.form.get("notfallart", "").strip()
            stream_mode = request.form.get("stream", "0") == "1"

            if not user_message:
                flash("Please enter a message.", "warning")
                return jsonify({"error": "Please enter a message."}), 400

            wissensbasis = download_wissensbasis()
            if not wissensbasis:
                flash("Knowledge base could not be loaded.", "danger")
                return jsonify({"error": "Knowledge base could not be loaded."}), 500

            if notfall_aktiv:
                session["notfall_mode"] = True
                user_message = (
                    f"EMERGENCY MODE - Topic 9: Emergencies & Contract Risks.\n"
                    f"Selected option(s): {notfall_art}\n\n" + user_message
                )
                log_notfall_event(user_id, notfall_art, user_message)
            else:
                session.pop("notfall_mode", None)

            system_prompt = create_system_prompt(table_schema) # Simplified for now
            # Add wissensbasis and user context to prompt (logic from app.py)
            system_prompt += f"\n\nUser Name: {user_name}" 
            if seller_id: system_prompt += f" Seller ID: {seller_id}"
             # Add Wissensbasis content here if needed for context

            tools = create_function_definitions()
            messages = [
                {"role": "developer", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            
            session_data = {
                "user_id": user_id,
                "user_name": user_name,
                "seller_id": seller_id,
                "email": session.get("email"),
                "chat_key": chat_key,
                "chat_history": list(chat_history) if stream_mode else None
            }

            try:
                if stream_mode and request.headers.get("Accept") == "text/event-stream":
                    # Placeholder: Determine tool/approach (using dummy function for now)
                    tool_config = load_tool_config()
                    selected_tool, _ = select_optimal_tool_with_reasoning(user_message, tools, tool_config)
                    
                    # --- Simplified Tool Handling for Blueprint --- 
                    if selected_tool == "human_in_loop_clarification":
                        human_in_loop_data = session.get("human_in_loop_data") # Needs setup
                        return Response(generate_clarification_stream(human_in_loop_data), content_type="text/event-stream")
                    elif selected_tool == "direct_conversation": 
                        return Response(process_direct_conversation(messages, session_data), content_type="text/event-stream")
                    # Add Wissensbasis check? (from original app.py)
                    # elif is_wissensbasis_query(user_message): ... stream_text_response ... 
                    else: # Default to general stream_response (might involve tool calls)
                         date_params = extract_date_params(user_message)
                         # Assuming stream_response handles potential tool calls internally based on messages/tools
                         return Response(stream_response(messages, tools, None, seller_id, date_params, user_message, session_data), content_type="text/event-stream")
                    # --- End Simplified Tool Handling ---
                    
                else: # Non-streaming request (if ever used)
                    # Placeholder for non-streaming logic (might be deprecated)
                     flash("Non-streaming responses not fully supported in this version.", "warning")
                     return redirect(url_for('.chat_route'))

            except Exception as e:
                logging.exception(f"Error during LLM interaction in chat blueprint")
                flash(f"An error occurred: {str(e)}", "danger")
                # For AJAX stream requests, we can't easily flash/redirect. Send error event?
                if stream_mode:
                     # Send an error event back via SSE
                     error_message = json.dumps({"error": f"Processing error: {str(e)}"})
                     return Response(f"event: error\ndata: {error_message}\n\n", content_type="text/event-stream", status=500)
                else:
                     return redirect(url_for('.chat_route'))

        # --- GET Request Handling --- 
        # Render the chat template
        return render_template(
            "chat.html",
            chat_history=display_chat_history,
            user_name=user_name,
            # Add other necessary template variables (e.g., notfall_mode_active)
            notfall_mode_active=session.get('notfall_mode', False)
        )

    except Exception as e:
        logging.exception("Error in chat route")
        flash(f"An unexpected error occurred: {str(e)}", "danger")
        # Attempt to redirect to login if it's an auth issue, otherwise maybe an error page
        return redirect(url_for("auth.login"))

@chat_bp.route('/clear_chat_history', methods=['POST'])
def clear_chat_history():
    """Clears the chat history for the current user in the session."""
    try:
        user_id = session.get('user_id')
        if not user_id:
            flash('User not recognized.', 'danger')
            return redirect(url_for('.chat_route')) # Relative redirect

        chat_key = f'chat_history_{user_id}'
        if chat_key in session:
            session.pop(chat_key)
            session.modified = True
            flash('Chat history cleared successfully.', 'success')
        else:
            flash('No chat history to clear.', 'info')
        return redirect(url_for('.chat_route')) # Relative redirect
    except Exception as e:
        logging.exception("Error clearing chat history")
        flash(f'An error occurred while clearing history: {str(e)}', 'danger')
        return redirect(url_for('.chat_route'))

@chat_bp.route('/update_stream_chat_history', methods=['POST'])
def update_stream_chat_history():
    """Endpoint called by frontend JS after a stream completes to update session."""
    try:
        data = request.json
        user_message = data.get('user_message')
        bot_response = data.get('bot_response')
        
        if not user_message or bot_response is None: # Allow empty bot response maybe?
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
            
        user_id = session.get("user_id")
        user_name = session.get("user_name") # Needed for store_chatlog
        
        if not user_id or not user_name:
            logging.warning("Update chat history request received without active session.")
            return jsonify({'success': False, 'error': 'No active session'}), 401 # Unauthorized
            
        chat_key = f'chat_history_{user_id}'
        chat_history = session.get(chat_key, [])
        
        # Add the user message and the complete bot response
        chat_history.append({"role": "user", "content": user_message})
        chat_history.append({"role": "assistant", "content": bot_response}) # Using assistant role
        
        session[chat_key] = chat_history
        session.modified = True
        
        # Persist the updated history (using placeholder)
        store_chatlog(user_name, chat_history) 
        
        return jsonify({'success': True})
        
    except Exception as e:
        logging.exception("Error updating chat history from stream")
        return jsonify({'success': False, 'error': str(e)}), 500

@chat_bp.route('/store_feedback', methods=['POST'])
def store_feedback_route():
    """Stores user feedback about a specific message."""
    try:
        data = request.get_json()
        feedback_type = data.get("feedback_type") # e.g., 'positive', 'negative'
        comment = data.get("comment", "").strip()
        message = data.get("message", "").strip() # The assistant message being rated
        
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User not recognized"}), 401

        if not feedback_type or not message:
             return jsonify({"success": False, "message": "Missing feedback type or message"}), 400
        
        chat_key = f'chat_history_{user_id}'
        chat_history = session.get(chat_key, [])
        
        # Call placeholder store_feedback function 
        store_feedback(feedback_type, comment, chat_history, message)
        
        return jsonify({"success": True}), 200
    except Exception as e:
        logging.exception("Error storing feedback")
        return jsonify({"success": False, "error": str(e)}), 500

# Ensure 'chat.html' exists in the templates folder
