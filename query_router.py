"""
Query Router Module

Dieses Modul ist verantwortlich für die Entscheidung, wie eine Benutzeranfrage bearbeitet werden soll:
1. Wissensbasis-Anfrage (qualitative Informationen)
2. Konversationelle Anfrage (einfache Fragen, Begrüßungen)
3. Datenbankabfrage (quantitative Daten über Kunden, Verträge, etc.)

Es stellt die erste Entscheidungsebene dar und leitet die Anfrage an die entsprechenden
Verarbeitungssysteme weiter.
"""

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from utils import debug_print

# Setup logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s %(levelname)s:%(name)s:%(message)s', 
                   datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

# Versuche, die bestehenden Funktionen zu importieren
try:
    from app import debug_print, call_llm
except ImportError:
    # Fallback-Implementierungen, falls die Funktionen nicht importiert werden können
    def debug_print(category, message):
        """Vereinfachte Debug-Print-Funktion, falls die Original-Funktion nicht verfügbar ist"""
        logger.debug(f"{category}: {message}")
    
    def call_llm(messages, model="gpt-4o", expect_json=True, conversation_history=None):
        """
        Verbesserte LLM-Aufruf-Funktion mit Konversationshistorie.
        Diese sollte die bestehende call_llm Funktion in app.py ersetzen.
        """
        import openai
        
        try:
            # Log the request (but sanitize it to avoid logging sensitive info)
            safe_messages = "Messages for LLM (first 100 chars): " + str(messages[0]['content'])[:100] + "..."
            logger.info(f"ROUTER LLM CALL - {safe_messages}")
            
            # Make the API call
            response = openai.chat.completions.create(
                model=model,
                messages=messages
            )
            
            content = response.choices[0].message.content
            
            # Parse JSON if expected and possible
            if expect_json:
                try:
                    json_response = json.loads(content)
                    return json_response
                except json.JSONDecodeError:
                    logger.warning(f"ROUTER LLM CALL - Expected JSON but got non-JSON response: {content[:100]}...")
                    if '{' in content and '}' in content:
                        # Try to extract JSON object if it's embedded in other text
                        try:
                            json_str = content[content.find('{'):content.rfind('}')+1]
                            return json.loads(json_str)
                        except:
                            pass
                    
                    # Return raw content if JSON parsing fails
                    return content
            
            return content
        except Exception as e:
            error_message = f"Error calling LLM: {str(e)}"
            logger.error(f"ROUTER LLM CALL ERROR - {error_message}")
            if expect_json:
                return {"error": error_message}
            return error_message


def determine_query_approach(user_message, conversation_history=None) -> Tuple[str, float, str]:
    """
    First-layer LLM decision to determine if a query requires:
    1. Knowledge base (wissensbasis) for qualitative company/process information
    2. Function calling for customer/quantitative data access
    3. Simple conversational response for general queries
    
    Args:
        user_message: The user's message/question
        conversation_history: Optional previous conversation context
        
    Returns:
        tuple: (approach, confidence, reasoning)
            approach: "wissensbasis", "function_calling", or "conversational"
            confidence: float between 0-1 indicating confidence
            reasoning: string explaining the decision
    """
    # Log the beginning of the approach determination process
    logger.info(f"ROUTING: determine_query_approach() aufgerufen für: '{user_message}'")
    
    # Create decision prompt
    prompt = f"""
    Analyze this user query and determine the most appropriate approach to answer it.
    
    Current date: {datetime.now().strftime("%Y-%m-%d")}

    User query: ""{user_message}""
    --END OF USER QUERY--
    
    You have three possibilities to bring up an answer:

    1. No tool needed - Use this for:
    - Simple greetings or chitchat (like "Hallo", "Wie geht's?")
    - Basic calculations or questions not related to your domain
    - Requests to summarize the conversation
    - General questions that don't need specific company knowledge or data
    
    2. Wissensbasis (Knowledge Base) - Use this for:
    - Questions about how our company works
    - How-to guides and process questions
    - Information about our CRM system
    - General qualitative knowledge about our operations
    - Questions that don't require specific customer data or numbers
    - Questions about terms, abbreviations, or concepts used in the company
    
    3. Function Calling (Database Queries) - Use this for:
    - Questions about specific customers or customer data
    - Numerical/statistical reports (revenue, performance)
    - Contract information for specific customers
    - Care stays, lead data, or ticketing information
    - Any queries requiring real-time data from our database
    
    Analyze the query carefully. Determine which approach would provide the best answer.
    
    Return a JSON object with these fields:
    - "approach": Either "wissensbasis", "function_calling", or "conversational"
    - "confidence": A number between 0 and 1 indicating your confidence
    - "reasoning": A brief explanation of your decision
    """
    
    messages = [
        {"role": "developer", "content": "You are a routing assistant for a senior care services company. You decide which approach is best for the user's query. Respond in JSON format."},
        {"role": "user", "content": prompt}
    ]
    
    # Add relevant conversation history if available
    if conversation_history:
        context_message = "Previous conversation context:\n"
        for i, message in enumerate(conversation_history[-3:]):  # Last 3 messages
            role = message.get("role", "")
            content = message.get("content", "")
            context_message += f"{role}: {content}\n"
        
        messages.insert(1, {"role": "developer", "content": context_message})
    
    # Call LLM
    try:
        response = call_llm(messages, "gpt-4o")  # Using a smaller, faster model for this decision
        
        # Parse response
        if isinstance(response, str):
            try:
                result = json.loads(response)
            except json.JSONDecodeError:
                logger.error(f"QUERY ROUTING - Failed to parse LLM response as JSON: {response[:100]}...")
                return "function_calling", 0.3, "Error parsing router response"
        else:
            result = response
        
        approach = result.get("approach", "conversational")  # Default to conversational if parsing fails
        confidence = float(result.get("confidence", 0.5))
        if confidence < 0.4:  # Set an appropriate threshold
            logger.info(f"ROUTING: Niedrige Konfidenz ({confidence}), Fallback auf 'conversational'")
            approach = "conversational"
        reasoning = result.get("reasoning", "No reasoning provided")
        
        logger.info(f"ROUTING: '{approach}' Modus gewählt (Konfidenz: {confidence:.2f})")
        
        return approach, confidence, reasoning
    except Exception as e:
        logger.error(f"Error in determine_query_approach: {e}")
        # Default to function_calling as fallback
        return "function_calling", 0.3, f"Error in approach determination: {str(e)}"


def determine_function_need(user_message, query_patterns, conversation_history=None):
    """
    Second-layer LLM decision to determine if clarification is needed for function selection
    and what the best function would be.
    
    Args:
        user_message: The user's message/question
        query_patterns: Dictionary of available query patterns
        conversation_history: Optional previous conversation context
    
    Returns:
        tuple: (needs_clarification, selected_function, possible_functions, parameters, clarification_message, reasoning)
    """
    logger.info(f"FUNCTION NEED - Determining function need for: '{user_message}'")
    
    # Create a list of available functions for the LLM to choose from
    function_descriptions = []
    for func_name, func_data in query_patterns.items():
        desc = func_data.get("description", "")
        params = func_data.get("required_parameters", [])
        param_desc = ", ".join([p.get("name", "") for p in params])
        function_descriptions.append({
            "name": func_name,
            "description": desc,
            "parameters": param_desc
        })
    
    # Create the prompt for the LLM
    prompt = f"""
    Analyze this user query and determine the most appropriate database function to call.
    
    Current date: {datetime.now().strftime("%Y-%m-%d")}
    
    User query: ""{user_message}""
    
    Available functions:
    {json.dumps(function_descriptions, indent=2)}
    
    Determine:
    1. Which function best matches the user's query?
    2. Are there multiple possible functions that could be used?
    3. Do we have enough information to call the function or do we need clarification?
    4. What parameters can be extracted from the query?
    
    Return a JSON object with these fields:
    - "needs_clarification": true/false indicating if we need more information
    - "selected_function": name of the best matching function
    - "possible_functions": array of function names that could be used
    - "parameters": object containing extracted parameters
    - "clarification_message": message to ask user if clarification is needed
    - "reasoning": brief explanation of your decision
    """
    
    messages = [
        {"role": "developer", "content": "You are a function selection assistant for a senior care database. Help determine the best function to call."},
        {"role": "user", "content": prompt}
    ]
    
    # Add conversation history context if available
    if conversation_history:
        context_message = "Previous conversation context:\n"
        for i, message in enumerate(conversation_history[-3:]):
            role = message.get("role", "")
            content = message.get("content", "")
            context_message += f"{role}: {content}\n"
        
        messages.insert(1, {"role": "developer", "content": context_message})
    
    # Call LLM
    try:
        response = call_llm(messages, "gpt-4o")
        
        # Parse response
        if isinstance(response, str):
            try:
                result = json.loads(response)
            except json.JSONDecodeError:
                logger.error(f"FUNCTION NEED - Failed to parse LLM response: {response[:100]}...")
                return True, "get_active_care_stays_now", ["get_active_care_stays_now"], {}, "Könnten Sie Ihre Anfrage bitte präzisieren?", "Error parsing response"
        else:
            result = response
        
        needs_clarification = result.get("needs_clarification", True)
        selected_function = result.get("selected_function", "get_active_care_stays_now")
        possible_functions = result.get("possible_functions", [selected_function])
        parameters = result.get("parameters", {})
        clarification_message = result.get("clarification_message", "Könnten Sie Ihre Anfrage bitte präzisieren?")
        reasoning = result.get("reasoning", "No reasoning provided")
        
        logger.info(f"FUNCTION NEED - Selected function: {selected_function}, Needs clarification: {needs_clarification}")
        logger.info(f"FUNCTION NEED - Reasoning: {reasoning}")
        
        # Fill in default date parameters if needed
        # Common practice in the original code
        if selected_function in ["get_monthly_performance", "get_care_stays_by_date_range"] and "start_date" not in parameters:
            # Get current month start and end
            current_date = datetime.now()
            month_start = datetime(current_date.year, current_date.month, 1)
            
            if current_date.month == 12:
                month_end = datetime(current_date.year, 12, 31)
            else:
                next_month = datetime(current_date.year, current_date.month + 1, 1)
                month_end = next_month - timedelta(days=1)
            
            parameters["start_date"] = month_start.strftime("%Y-%m-%d")
            parameters["end_date"] = month_end.strftime("%Y-%m-%d")
            
            logger.info(f"FUNCTION NEED - Added default date parameters: {parameters['start_date']} to {parameters['end_date']}")
        
        return needs_clarification, selected_function, possible_functions, parameters, clarification_message, reasoning
        
    except Exception as e:
        logger.error(f"Error in determine_function_need: {e}")
        # Default values in case of error
        return True, "get_active_care_stays_now", ["get_active_care_stays_now"], {}, "Bei der Verarbeitung Ihrer Anfrage ist ein Fehler aufgetreten. Könnten Sie es anders formulieren?", f"Error: {str(e)}"


def handle_conversational_clarification(user_message, previous_clarification_data=None, conversation_history=None):
    """
    Processes a user's response to a clarification request in a conversational manner.
    
    Args:
        user_message: The user's response to the clarification request
        previous_clarification_data: Data from the previous clarification request
        conversation_history: The conversation history for better context
        
    Returns:
        tuple: (is_resolved, function_name, parameters, new_clarification_data)
            is_resolved: Whether the clarification has been resolved
            function_name: The selected function name (if resolved)
            parameters: Parameters for the function (if resolved)
            new_clarification_data: New clarification data (if not resolved)
    """
    logger.info(f"ROUTING: SZENARIO 4 - Verarbeite Rückfrageantwort: '{user_message}'")
    debug_print("Clarification", f"Verarbeite Rückfrageantwort: {user_message}")
    
    if not previous_clarification_data:
        logger.error("CLARIFICATION - Missing previous clarification data")
        return True, "get_active_care_stays_now", {}, None
    
    # Extract previous context
    original_query = previous_clarification_data.get("original_question", "")
    possible_queries = previous_clarification_data.get("possible_queries", [])
    prev_parameters = previous_clarification_data.get("parameters", {})
    
    # Create a prompt to analyze the user's response to the clarification
    prompt = f"""
    You are helping to resolve a clarification for a database query.
    
    Original user query: "{original_query}"
    
    Our previous clarification question to the user was:
    "{previous_clarification_data.get('clarification_message', '')}"
    
    The user has responded with:
    "{user_message}"
    
    Possible functions that could be used:
    {json.dumps(possible_queries)}
    
    Current parameters we have:
    {json.dumps(prev_parameters)}
    
    Based on the user's response, please determine:
    1. Is the clarification resolved? (Can we proceed with a specific function?)
    2. Which function should be used?
    3. What parameters can be extracted from the combination of original query and response?
    4. If clarification is not resolved, what follow-up question should we ask?
    
    Return a JSON object with these fields:
    - "is_resolved": true/false
    - "function_name": name of the function to use if resolved
    - "parameters": object containing all parameters (including from original query)
    - "follow_up_question": question to ask if not resolved
    """
    
    messages = [
        {"role": "developer", "content": "You are a clarification resolution assistant. Help determine if we have enough information now."},
        {"role": "user", "content": prompt}
    ]
    
    # Add conversation history for context if available
    if conversation_history:
        context_message = "Relevant conversation history:\n"
        for i, message in enumerate(conversation_history[-3:]):
            role = message.get("role", "")
            content = message.get("content", "")
            context_message += f"{role}: {content}\n"
        
        messages.insert(1, {"role": "developer", "content": context_message})
    
    # Call LLM
    try:
        response = call_llm(messages, "gpt-4o")
        
        # Parse response
        if isinstance(response, str):
            try:
                result = json.loads(response)
            except json.JSONDecodeError:
                logger.error(f"CLARIFICATION - Failed to parse LLM response: {response[:100]}...")
                # Default to resolving with first possible query
                return True, possible_queries[0] if possible_queries else "get_active_care_stays_now", prev_parameters, None
        else:
            result = response
        
        is_resolved = result.get("is_resolved", False)
        function_name = result.get("function_name", possible_queries[0] if possible_queries else "get_active_care_stays_now")
        parameters = result.get("parameters", prev_parameters)
        follow_up_question = result.get("follow_up_question", "Könnten Sie bitte weitere Details angeben?")
        
        logger.info(f"CLARIFICATION - Resolution result: is_resolved={is_resolved}, function={function_name}")
        
        if is_resolved:
            # Clarification resolved, return function and parameters
            logger.info("CLARIFICATION - Rückfrageprozess erfolgreich abgeschlossen")
            return True, function_name, parameters, None
        else:
            # Still need more clarification
            logger.info("CLARIFICATION - Rückfrageprozess nicht abgeschlossen, weitere Klärung erforderlich")
            new_clarification_data = {
                "original_question": original_query,
                "clarification_message": follow_up_question,
                "possible_queries": possible_queries,
                "parameters": parameters
            }
            return False, None, None, new_clarification_data
            
    except Exception as e:
        logger.error(f"Error in handle_conversational_clarification: {e}")
        # Default to resolving with the first possible query in case of error
        logger.info("CLARIFICATION - Rückfrageprozess nicht abgeschlossen, Fehler aufgetreten")
        return True, possible_queries[0] if possible_queries else "get_active_care_stays_now", prev_parameters, None


def is_knowledge_base_query(user_message, conversation_history=None) -> bool:
    """
    Quick check to determine if a query is likely to be answerable from the knowledge base
    rather than requiring database access.
    
    Args:
        user_message: The user's message/question
        conversation_history: Optional previous conversation context
        
    Returns:
        bool: True if likely a knowledge base query, False otherwise
    """
    # Common patterns for knowledge base queries
    knowledge_patterns = [
        r"was (ist|sind|bedeutet|heißt)",
        r"wie (funktioniert|geht|macht man)",
        r"wofür (steht|ist|wird verwendet)",
        r"erkläre",
        r"erklär mir",
        r"definition von",
        r"bedeutung von",
        r"wozu dient",
    ]
    
    # Check for knowledge patterns
    user_message_lower = user_message.lower()
    for pattern in knowledge_patterns:
        if re.search(pattern, user_message_lower):
            logger.info(f"KNOWLEDGE CHECK - Detected knowledge base query pattern: '{pattern}' in '{user_message}'")
            return True
    
    # No obvious knowledge pattern, could still be a knowledge query but need more analysis
    return False


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
                system_prompt = create_enhanced_system_prompt(function_name, conversation_history)
                
                messages = [
                    {"role": "developer", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "function", "name": function_name, "content": tool_result}
                ]
                
                # Use conversation history for better context
                response = openai.chat.completions.create(
                    model="gpt-4o",
                    messages=messages
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
    
    # Aktuelles Datum für zeitliche Anfragen
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    
    # Füge das aktuelle Datum zu Session-Daten hinzu
    session_data["current_date"] = current_date_str
    
    debug_print("Anfrage", f"Verarbeite Anfrage: '{user_message}'")
    
    # STEP 1: Determine if this query requires wissensbasis or function calling
    approach, confidence, reasoning = determine_query_approach(user_message, conversation_history)
    
    # STEP 2: Handle based on the determined approach
    if approach == "conversational":
        logger.info("ROUTING: SZENARIO 1 - Konversationelle Anfrage erkannt")
        debug_print("Anfrage", "Konversationelle Anfrage erkannt")
        
        # Einfache LLM-Antwort generieren
        messages = [
            {"role": "system", "content": "Du bist ein hilfsbereiter Assistent für Pflege und Seniorenbetreuung."},
            {"role": "user", "content": user_message}
        ]
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            
            answer = response.choices[0].message.content
            logger.info("ROUTING: SZENARIO 1 - Einfache Konversation abgeschlossen")
            return answer
        except Exception as e:
            logger.error(f"Error in conversational response: {e}")
            return "Es tut mir leid, ich hatte Schwierigkeiten, Ihre Anfrage zu verstehen. Könnten Sie es bitte anders formulieren?"
    
    elif approach == "wissensbasis":
        logger.info("ROUTING: SZENARIO 2 - Wissensbasis-Anfrage gestartet")
        debug_print("Anfrage", "Wissensbasis-Anfrage erkannt")
        try:
            # Vereinfachte Version ohne den vollen Wissensbasis-Code
            # In Ihrem Code würde hier die Vektorsuche und Retrieval stattfinden
            
            # Dummy-Implementation für dieses Beispiel
            # Im realen Code würde hier ein Aufruf an die Wissensbasis-Suche erfolgen
            
            # Nach erfolgreicher Ausführung
            logger.info("ROUTING: SZENARIO 2 - Wissensdatenbank-Anfrage abgeschlossen")
            
            # Da wir die echte Wissensbasis-Suche hier nicht implementieren,
            # geben wir eine generische Antwort zurück
            return "Dies würde normalerweise eine Antwort aus der Wissensdatenbank sein."
        except Exception as e:
            logger.error(f"Error in knowledge base response: {e}")
            return "Es tut mir leid, ich konnte keine relevanten Informationen in unserer Wissensbasis finden."
    
    # STEP 3: If we reach here, it's a function_calling approach
    logger.info("ROUTING: SZENARIO 3 - Datenbank-Anfrage erkannt, bestimme passende Funktion")
    debug_print("Anfrage", "Datenbank-Anfrage erkannt, bestimme passende Funktion")
    
    # Load query patterns
    try:
        with open('query_patterns.json', 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
    except Exception as e:
        logger.error(f"Error loading query patterns: {e}")
        return "Es tut mir leid, ich konnte die Anfragemuster nicht laden."
    
    # STEP 4: Determine if clarification is needed
    needs_clarification, selected_function, possible_functions, parameters, clarification_message, reasoning = determine_function_need(
        user_message, 
        query_patterns.get('common_queries', {}),
        conversation_history
    )
    
    if needs_clarification:
        logger.info(f"ROUTING: SZENARIO 4 - Rückfrage notwendig für Funktion")
        
        # Save the clarification state
        session["clarification_in_progress"] = True
        clarification_data = {
            "original_question": user_message,
            "clarification_message": clarification_message,
            "possible_queries": possible_functions,
            "parameters": parameters
        }
        session["clarification_data"] = clarification_data
        
        # Return the clarification message
        return clarification_message
    
    # STEP 5: No clarification needed, execute function directly
    logger.info(f"ROUTING: SZENARIO 3 - Direkte Funktionsausführung: {selected_function}")
    
    # Add seller_id from session data if needed
    if "seller_id" not in parameters and "seller_id" in session_data:
        parameters["seller_id"] = session_data.get("seller_id")
    
    # Execute function
    try:
        # Import the function if it's not available yet
        if "handle_function_call" not in globals():
            try:
                from bigquery_functions import handle_function_call
            except ImportError:
                logger.error("Could not import handle_function_call")
                return "Es tut mir leid, ich konnte die Datenbankfunktionen nicht laden."
        
        debug_print("Tool", f"Führe Tool aus: {selected_function} mit Parametern: {parameters}")
        tool_result = handle_function_call(selected_function, parameters)
        
        # Generate response with the function result
        system_prompt = create_enhanced_system_prompt(selected_function, conversation_history)
        
        messages = [
            {"role": "developer", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "function", "name": selected_function, "content": tool_result}
        ]
        
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        
        final_response = response.choices[0].message.content
        logger.info("ROUTING: SZENARIO 3 - Datenbankanfrage erfolgreich abgeschlossen")
        
        return final_response
    except Exception as e:
        logger.error(f"Error executing function {selected_function}: {e}")
        return f"Es tut mir leid, bei der Ausführung der Datenbankabfrage ist ein Fehler aufgetreten: {str(e)}"
