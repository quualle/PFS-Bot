from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, flash, Response, current_app
import logging
import json

# Blueprint Definition
chat_bp = Blueprint('chat', __name__)

# Import necessary functions from the main app
from app import (
    conversation_manager, extract_date_params, select_optimal_tool_with_reasoning,
    load_tool_config, calculate_chat_stats, store_chatlog, download_wissensbasis
)

# Import OpenAI utilities from the utility module
from routes.openai_utils import contact_openai, count_tokens, create_function_definitions, create_system_prompt

# Import stream utilities from the stream utils module
from routes.stream_utils import stream_response, stream_text_response, generate_clarification_stream, generate_conversational_clarification_stream

# Import BigQuery functions
from bigquery_functions import handle_function_call

# Import extraction utilities
from extract import format_customer_details

@chat_bp.route("/clarify", methods=["POST"])
def handle_clarification():
    """
    Verarbeitet die Antwort auf eine Rückfrage - unterstützt sowohl Legacy Button-Modus als auch
    neue konversationelle Rückfragen
    """
    try:
        # Stellen wir sicher, dass eine Benutzer-Session existiert
        if not session.get("user_id"):
            logging.warning("Clarification-Anfrage ohne aktive Benutzer-Session")
            return jsonify({"error": "Keine aktive Benutzer-Session gefunden"}), 400
        
        # Für AJAX-Anfragen
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        
        # Debug-Informationen
        logging.info(f"Verarbeite Clarification-Antwort, AJAX: {is_ajax}")
        
        # Prüfen, ob wir im konversationellen oder Button-Modus sind
        conversational_mode = session.get("clarification_in_progress", False)
        
        if conversational_mode:
            # Konversationeller Modus: Antwort als natürlichen Text behandeln
            user_message = request.form.get("message", "").strip()
            
            if not user_message:
                error_msg = "Keine Antwort auf die Rückfrage angegeben"
                logging.error(error_msg)
                if is_ajax:
                    return jsonify({"error": error_msg}), 400
                flash(error_msg, "warning")
                return redirect(url_for("chat.chat"))
            
            # Benutzerantwort wird in der normalen Chat-Route verarbeitet
            # Wir senden eine Erfolgsmeldung zurück, da die Verarbeitung im Chat-Handler erfolgt
            if is_ajax:
                return jsonify({"success": True, "message": "Antwort wird verarbeitet"})
            return redirect(url_for("chat.chat"))
        
        # Legacy Button-Modus
        try:
            # Lese die Option aus dem Formular
            selected_option_index = int(request.form.get("option_index", "0"))
            logging.info(f"Ausgewählter Options-Index: {selected_option_index}")
        except ValueError:
            error_msg = "Ungültiger Options-Index Format (keine Zahl)"
            logging.error(f"Fehler beim Parsen des Options-Index: {request.form.get('option_index')}")
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat.chat"))
            
        # Prüfe, ob die Human-in-Loop-Daten in der Session vorhanden sind
        human_in_loop_data = session.get("human_in_loop_data")
        
        # Logge die vorhandenen Session-Daten für Debugging
        session_keys = list(session.keys())
        logging.debug(f"Verfügbare Session-Keys: {session_keys}")
        
        if not human_in_loop_data:
            error_msg = "Keine Rückfrage-Daten in der Session gefunden"
            logging.error(error_msg)
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat.chat"))
            
        if "options" not in human_in_loop_data:
            error_msg = "Ungültige Rückfrage-Daten: Keine Optionen vorhanden"
            logging.error(f"human_in_loop_data ohne 'options': {human_in_loop_data}")
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat.chat"))
            
        options = human_in_loop_data.get("options", [])
        logging.info(f"Anzahl verfügbarer Optionen: {len(options)}")
        
        # Prüfe, ob der Index gültig ist
        if selected_option_index < 0 or selected_option_index >= len(options):
            error_msg = f"Ungültiger Options-Index: {selected_option_index} (max: {len(options)-1})"
            logging.error(error_msg)
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat.chat"))
            
        # Hole ausgewählte Option
        selected_option = options[selected_option_index]
        logging.info(f"Ausgewählte Option: {selected_option.get('text')} -> {selected_option.get('query')}")
        
        # Verarbeiten von Parametern, speziell für den Kunden Küll
        params = selected_option.get("params", {})
        if params and "customer_name" in params:
            customer_name = params["customer_name"]
            if customer_name.lower() in ["küll", "kull", "kühl", "kuehl", "kuell"]:
                logging.info("Normalisiere Kunden-Parameter 'Küll'")
                params["customer_name"] = "Küll"
                selected_option["params"] = params

        # Extrahiere die benötigten Informationen
        selected_query = selected_option.get("query")
        selected_params = selected_option.get("params", {})
        
        # Verarbeitung direkt hier für Kundenabfragen
        if selected_query == "get_customer_history" and "customer_name" in selected_params:
            try:
                # Kundenname extrahieren
                customer_name = selected_params.get("customer_name")
                
                # seller_id aus der Session hinzufügen
                if "seller_id" in session:
                    selected_params["seller_id"] = session.get("seller_id")
                
                logging.info(f"Führe direkt get_customer_history für '{customer_name}' aus")
                
                # Funktion direkt aufrufen
                result = handle_function_call(selected_query, selected_params)
                result_data = json.loads(result)
                
                # Ergebnis formatieren und den Chat-Verlauf aktualisieren
                if "data" in result_data and len(result_data["data"]) > 0:
                    formatted_result = format_customer_details(result_data)
                    
                    # Original-Anfrage holen
                    original_request = session.get("human_in_loop_original_request", "")
                    
                    # Chat-History aktualisieren
                    chat_key = f"chat_history_{session.get('user_id')}"
                    chat_history = session.get(chat_key, [])
                    
                    # Benutzeranfrage und Antwort hinzufügen
                    chat_history.append({"role": "user", "content": original_request})
                    chat_history.append({"role": "assistant", "content": formatted_result})
                    session[chat_key] = chat_history
                    
                    # Erfolg zurückgeben
                    if is_ajax:
                        return jsonify({
                            "success": True, 
                            "response": formatted_result,
                            "message": "Kundeninformationen erfolgreich abgerufen."
                        })
                    else:
                        # Bei normaler Anfrage: Flash-Nachricht und Weiterleitung
                        flash("Kundeninformationen erfolgreich abgerufen.", "success")
                        # WICHTIG: Antwort in der Session speichern für die Anzeige
                        session["last_response"] = formatted_result
                        session.modified = True
                        return redirect(url_for("chat.chat"))
                else:
                    # Keine Daten gefunden
                    error_msg = f"Keine Daten für Kunde '{customer_name}' gefunden."
                    if is_ajax:
                        return jsonify({"error": error_msg})
                    flash(error_msg, "warning")
                    return redirect(url_for("chat.chat"))
            
            except Exception as e:
                logging.error(f"Fehler bei direkter Kundenanfrage: {str(e)}")
                if is_ajax:
                    return jsonify({"error": str(e)})
                flash(f"Fehler bei der Verarbeitung: {str(e)}", "danger")
                return redirect(url_for("chat.chat"))
        
        # Für andere Anfragen: in Session speichern für nächsten Request
        session["human_in_loop_clarification_response"] = selected_option
        
        # Speichere den original request für die Kontext-Kontinuität
        if "human_in_loop_original_request" in session:
            original_request = session.get("human_in_loop_original_request")
            session["pending_query"] = original_request
            logging.info(f"Original-Anfrage gespeichert: {original_request}")
        else:
            logging.warning("Keine Original-Anfrage in der Session gefunden")
        
        # Entferne die Human-in-the-Loop-Daten aus der Session
        session.pop("human_in_loop_data", None)
        session.pop("human_in_loop_original_request", None)
        
        # Stelle sicher, dass der Chatverlauf erhalten bleibt
        session.modified = True
        
        # Bei AJAX-Anfragen mehr Informationen zurückgeben für clientseitige Verarbeitung
        if is_ajax:
            logging.info("Sende AJAX-Erfolgsantwort mit Option")
            # Hier nehmen wir an, dass im nächsten Request eine Antwort erstellt wird
            # Daher senden wir ein Signal an die Client-Seite, dass es eine Anfrage gab,
            # die beim nächsten Request beantwortet wird (im GET handler der chat route)
            return jsonify({
                "success": True, 
                "message": "Option ausgewählt",
                "selected_option": selected_option.get("text", ""),
                "query": selected_query,
                "need_followup": True
            })
        
        # Ansonsten wie gehabt weiterleiten
        logging.info("Weiterleitung zur Chat-Seite")
        return redirect(url_for("chat.chat"))
    except Exception as e:
        # Allgemeine Fehlerbehandlung
        logging.error(f"Fehler bei der Verarbeitung der Clarification-Antwort: {str(e)}")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": str(e)}), 500
        flash(f"Fehler: {str(e)}", "danger")
        return redirect(url_for("chat.chat"))

@chat_bp.route("/", methods=["GET", "POST"])
def chat():
    # Function implementation will be added in a separate edit to avoid token limits
    return render_template("chat.html")

@chat_bp.route('/update_stream_chat_history', methods=['POST'])
def update_stream_chat_history():
    """
    Update chat history in the session from streaming responses
    """
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400
            
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({'error': 'No active user session'}), 400
            
        # Get history key for this user
        chat_key = f"chat_history_{user_id}"
        chat_history = session.get(chat_key, [])
        
        # Add the streamed message to chat history
        message = {
            'role': 'assistant',
            'content': data['message']
        }
        
        # Überprüfe, ob bereits eine Nachricht mit diesem Inhalt vorhanden ist
        # (Verhindert Duplikate bei mehrfachen Frontend-Updates)
        message_exists = any(
            msg.get('role') == 'assistant' and msg.get('content') == message['content'] 
            for msg in chat_history
        )
        
        if not message_exists:
            chat_history.append(message)
            session[chat_key] = chat_history
            session.modified = True
            logging.info(f"Chat history updated with streamed message, length: {len(chat_history)}")
        else:
            logging.info("Message already exists in chat history, skipping")
        
        return jsonify({'success': True})
    except Exception as e:
        logging.error(f"Error updating chat history: {str(e)}")
        return jsonify({'error': str(e)}), 500

@chat_bp.route('/get_clarification_response', methods=['GET'])
def get_clarification_response():
    """
    AJAX endpoint to get a response after a human-in-loop clarification button was clicked.
    This allows the client to update the UI without a page refresh.
    """
    try:
        # Prüfe Benutzer-Session
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Keine aktive Benutzer-Session gefunden"}), 400
            
        # Prüfe, ob eine Rückfrage-Antwort vorhanden ist
        if "human_in_loop_clarification_response" not in session:
            return jsonify({"error": "Keine Rückfrage-Antwort in der Session gefunden"}), 404
            
        # Hole die gespeicherte Antwort
        clarification_response = session.get("human_in_loop_clarification_response")
        original_request = session.get("pending_query", "")
        
        # Lösche die temporären Daten
        session.pop("human_in_loop_clarification_response", None)
        session.pop("pending_query", None)
        
        logging.info(f"Verarbeite Rückfrage-Antwort: {clarification_response}")
        
        # Extrahiere Query und Parameter
        selected_query = clarification_response.get("query")
        selected_params = clarification_response.get("params", {})
        
        # Seller ID hinzufügen
        if "seller_id" in session and "seller_id" not in selected_params:
            selected_params["seller_id"] = session.get("seller_id")
            
        logging.info(f"Führe Abfrage aus: {selected_query} mit Parametern: {selected_params}")
        
        # Funktion aufrufen
        try:
            result = handle_function_call(selected_query, selected_params)
            result_data = json.loads(result)
            
            # Antwort formatieren basierend auf dem Abfragetyp
            formatted_result = ""
            if selected_query == "get_customer_history" and "data" in result_data:
                formatted_result = format_customer_details(result_data)
            else:
                # Generischer Fallback für andere Abfragetypen
                formatted_result = f"Ergebnis der Abfrage '{selected_query}':\n\n{json.dumps(result_data, indent=2, ensure_ascii=False)}"
                
            # Chat-History aktualisieren
            chat_key = f"chat_history_{user_id}"
            chat_history = session.get(chat_key, [])
            
            # Benutzeranfrage und Antwort hinzufügen
            chat_history.append({"role": "user", "content": original_request})
            chat_history.append({"role": "assistant", "content": formatted_result})
            session[chat_key] = chat_history
            
            # Speichere den aktualisierten Verlauf
            try:
                user_name = session.get("user_name", "unknown")
                store_chatlog(user_name, chat_history)
            except Exception as log_error:
                logging.error(f"Fehler beim Speichern des Chat-Logs: {str(log_error)}")
            
            # Berechne Chat-Statistiken
            try:
                calculate_chat_stats()
            except Exception as stat_error:
                logging.error(f"Fehler bei Chat-Statistik: {str(stat_error)}")
            
            # Erfolg zurückgeben
            return jsonify({
                "success": True,
                "response": formatted_result,
                "message": "Anfrage erfolgreich verarbeitet"
            })
            
        except Exception as func_error:
            error_msg = str(func_error)
            logging.error(f"Fehler bei Funktionsaufruf: {error_msg}")
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logging.error(f"Allgemeiner Fehler bei Rückfrage-Verarbeitung: {str(e)}")
        return jsonify({"error": str(e)}), 500

@chat_bp.route('/clear_chat_history', methods=['POST'])
def clear_chat_history():
    """
    Löscht den Chatverlauf des aktuellen Benutzers
    """
    try:
        user_id = session.get("user_id")
        if not user_id:
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "Keine Benutzer-Session gefunden"}), 400
            flash("Keine aktive Benutzer-Session gefunden.", "warning")
            return redirect(url_for("chat.chat"))
            
        # Chatverlauf-Key für diesen Benutzer
        chat_key = f"chat_history_{user_id}"
        
        # Chatverlauf löschen
        if chat_key in session:
            session.pop(chat_key)
            logging.info(f"Chatverlauf für Benutzer {user_id} gelöscht")
            
        # AJAX oder normale Anfrage?
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": True, "message": "Chatverlauf wurde gelöscht"})
            
        flash("Der Chatverlauf wurde gelöscht.", "success")
        return redirect(url_for("chat.chat"))
    except Exception as e:
        logging.error(f"Fehler beim Löschen des Chatverlaufs: {str(e)}")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": str(e)}), 500
        flash(f"Fehler: {str(e)}", "danger")
        return redirect(url_for("chat.chat"))
