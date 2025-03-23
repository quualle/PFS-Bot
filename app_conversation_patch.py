"""
Patch-Datei für app.py mit Änderungen zur Integration des ConversationManager.

Dieses Skript enthält die Funktionen, die in app.py aktualisiert werden sollten,
um die vollständige Konversationshistorie in LLM-Aufrufen zu verwenden.

Anwendung:
1. Importiere die hier definierten Funktionen in app.py
2. Ersetze die bestehenden Funktionen mit den neuen Versionen
"""

import json
import logging
from typing import Dict, List, Any, Optional
from conversation_manager import ConversationManager

# Setup logging
logger = logging.getLogger(__name__)

# Erstelle eine Instanz des ConversationManager
conversation_manager = ConversationManager(max_history=10)

def call_llm(messages, model="o3-mini", conversation_history=None):
    """
    Verbesserte LLM-Aufruf-Funktion mit Konversationshistorie.
    Diese sollte die bestehende call_llm Funktion in app.py ersetzen.
    """
    # Wenn Konversationshistorie vorhanden ist, integriere sie mit den aktuellen Nachrichten
    if conversation_history:
        # Verwende nur die neuesten Nachrichten, um Token-Limits zu vermeiden
        relevant_history = conversation_history[-5:]  # Anzahl nach Bedarf anpassen
        
        # Füge History am Anfang der messages hinzu, erhalte die Reihenfolge
        context_messages = []
        for msg in relevant_history:
            # Vermeide Duplikate
            if all(not (m.get('content') == msg.get('content') and 
                        m.get('role') == msg.get('role')) 
                  for m in messages):
                context_messages.append(msg)
        
        messages = context_messages + messages
    
    # Integration in bestehende OpenAI-Aufrufe
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4  # Niedrigere Temperatur für präzisere Antworten
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Fehler beim Aufrufen des LLM: {e}")
        return None

def process_user_query(user_message, session_data):
    """
    Verbesserte Version der process_user_query Funktion mit Konversationshistorie.
    Diese sollte die bestehende process_user_query Funktion in app.py ersetzen.
    """
    conversation_history = session_data.get("conversation_history", [])
    
    # Check if there's an ongoing clarification dialog
    if session.get("clarification_in_progress"):
        clarification_data = session.get("clarification_data", {})
        debug_print("Clarification", "Processing response to clarification")
        
        # Check if this is a text-based clarification
        if clarification_data.get("clarification_type") == "text_clarification":
            debug_print("Clarification", "Processing text-based clarification")
            
            # Use our new text-based processing function from query_selector
            original_question = clarification_data.get("original_question", "")
            clarification_context = clarification_data.get("clarification_context", {})
            
            # Import the new function if needed
            from query_selector import process_text_clarification_response
            
            # Process the user's text response - PASS CONVERSATION HISTORY
            function_name, parameters = process_text_clarification_response(
                clarification_context,
                user_message,
                original_question,
                conversation_history  # Pass the conversation history
            )
            
            # Clean up clarification state
            session.pop("clarification_in_progress", None)
            session.pop("clarification_data", None)
            
            # Mark as resolved with the function and parameters from text processing
            is_resolved = True
            new_clarification_data = None
        else:
            # Legacy button-based or conversational clarification
            is_resolved, function_name, parameters, new_clarification_data = handle_conversational_clarification(
                user_message, clarification_data, conversation_history  # Pass conversation history here too
            )
        
        if is_resolved:
            # Clarification resolved, continue with function execution
            debug_print("Clarification", f"Resolved: using function {function_name}")
            session.pop("clarification_in_progress", None)
            session.pop("clarification_data", None)
            
            # Add standard parameters
            if "seller_id" in parameters and "seller_id" in session_data:
                parameters["seller_id"] = session_data.get("seller_id")
            
            # Execute function
            debug_print("Tool", f"Führe Tool aus: {function_name} mit Parametern: {parameters}")
            tool_result = handle_function_call(function_name, parameters)
            
            # SCHRITT 4: Spezialbehandlung für bestimmte Abfragen
            formatted_result = None
            try:
                if function_name == "get_customer_history":
                    formatted_result = format_customer_details(json.loads(tool_result))
                    debug_print("Antwort", "Kunde-Historie formatiert")
            except Exception as format_error:
                debug_print("Antwort", f"Fehler bei der Formatierung: {format_error}")
            
            # SCHRITT 5: Antwort generieren
            try:
                # Wenn bereits eine formatierte Antwort vorliegt, nutze diese
                if formatted_result:
                    # Update conversation history before returning
                    session_data = conversation_manager.update_conversation(
                        session_data, 
                        user_message, 
                        formatted_result, 
                        {"name": function_name, "content": tool_result}
                    )
                    return formatted_result
                
                # Andernfalls erstelle einen angepassten System-Prompt für die LLM-Antwort
                system_prompt = create_enhanced_system_prompt(function_name)
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "function", "name": function_name, "content": tool_result}
                ]
                
                # Use conversation history for better context
                response = openai.chat.completions.create(
                    model="o3-mini",
                    messages=messages,
                    temperature=0.4  # Niedrigere Temperatur für präzisere Antworten
                )
                
                final_response = response.choices[0].message.content
                
                # Update conversation history with this interaction
                session_data = conversation_manager.update_conversation(
                    session_data, 
                    user_message, 
                    final_response, 
                    {"name": function_name, "content": tool_result}
                )
                
                debug_print("Antwort", f"Antwort generiert (gekürzt): {final_response[:100]}...")
                return final_response
            except Exception as e:
                # Fallback antwort
                debug_print("Antwort", f"Fehler bei der Antwortgenerierung: {e}")
                fallback = generate_fallback_response(function_name, tool_result)
                
                # Still update conversation history with fallback
                session_data = conversation_manager.update_conversation(
                    session_data, 
                    user_message, 
                    fallback, 
                    {"name": function_name, "content": tool_result}
                )
                
                return fallback
        else:
            # Need more clarification
            session["clarification_data"] = new_clarification_data
            
            # Update conversation history with this clarification
            session_data = conversation_manager.update_conversation(
                session_data, 
                user_message, 
                new_clarification_data["clarification_message"]
            )
            
            return new_clarification_data["clarification_message"]
    
    # Rest of the function remains unchanged...
    # ...
    
    # Update conversation history before returning the final response
    if 'final_response' in locals():
        session_data = conversation_manager.update_conversation(
            session_data, 
            user_message, 
            final_response
        )

def create_enhanced_system_prompt(function_name, session_data=None):
    """
    Erstellt einen kontextbewussten System-Prompt basierend auf der Funktion und Konversationshistorie.
    
    Args:
        function_name: Name der ausgeführten Funktion
        session_data: Optionale Session-Daten mit Konversationshistorie
        
    Returns:
        Erweiterter System-Prompt
    """
    # Basis-Prompt aus der bestehenden Funktion
    base_prompt = """Du bist ein hilfreicher Assistent für ein Pflegevermittlungssystem.
Deine Aufgabe ist es, SQL-Abfrageergebnisse zu interpretieren und dem Benutzer zu erklären.
Antworte immer auf Deutsch.
Gib möglichst vollständige und detaillierte Antworten."""

    # Ergänze funktionsspezifische Anweisungen
    if function_name == "get_customer_history":
        base_prompt += """
Du erhältst Informationen über die Kundenhistorie.
Erkläre die wichtigsten Aspekte der Kundenhistorie, wie Verträge und Einsätze.
Formatiere die Ausgabe übersichtlich mit Listenelementen für verschiedene Verträge und Einsätze."""
    elif function_name == "get_customer_tickets":
        base_prompt += """
Du erhältst Ticket-Informationen für einen Kunden.
Fasse die wichtigsten Tickets und deren Inhalte zusammen, sortiert nach Datum.
Hebe besonders wichtige oder aktuelle Tickets hervor."""
    # Weitere funktionsspezifische Anweisungen...
    
    # Kontextbewusstsein hinzufügen, wenn Session-Daten verfügbar sind
    if session_data:
        # Verwende ConversationManager für kontextbewusstes Prompt-Enhancement
        context_prompt = conversation_manager.create_context_aware_system_prompt(
            base_prompt, session_data
        )
        return context_prompt
    
    return base_prompt

# Weitere Funktionen, die aktualisiert werden müssen...
