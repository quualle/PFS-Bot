import json
import logging
import os
import datetime
from typing import Dict, List, Optional, Any, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_query_patterns() -> Dict:
    """Load query patterns from the JSON file"""
    try:
        with open("query_patterns.json", "r", encoding="utf-8") as f:
            # Skip the first few lines that contain comments
            content = f.read()
            # Find the actual JSON content (skipping comment lines)
            json_start = content.find('{')
            if json_start >= 0:
                content = content[json_start:]
                return json.loads(content).get("common_queries", {})
            return {}
    except Exception as e:
        logger.error(f"Error loading query patterns: {e}")
        return {}

def create_query_selection_prompt(
    user_request: str, 
    conversation_history: Optional[List[Dict]] = None
) -> List[Dict]:
    """Create a comprehensive prompt for query selection"""
    
    query_patterns = load_query_patterns()
    
    # Extract important information about each query
    query_descriptions = []
    for query_name, query_data in query_patterns.items():
        query_info = {
            "name": query_name,
            "description": query_data.get("description", ""),
            "required_parameters": query_data.get("required_parameters", []),
            "optional_parameters": query_data.get("optional_parameters", []),
            "result_structure": query_data.get("result_structure", {})
        }
        
        # Add use cases and limitations if available
        if "use_cases" in query_data:
            query_info["use_cases"] = query_data.get("use_cases", [])
        if "avoid_when" in query_data:
            query_info["avoid_when"] = query_data.get("avoid_when", [])
            
        query_descriptions.append(query_info)
    
    # Include conversation history context if available
    history_context = ""
    if conversation_history and len(conversation_history) > 0:
        history_context = "Previous conversation:\n"
        for i, message in enumerate(conversation_history[-3:]):  # Include last 3 messages
            role = message.get("role", "")
            content = message.get("content", "")
            history_context += f"{role}: {content}\n"
    
    # Get current date and time for accurate date processing
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    current_time_context = f"Current system date: {current_date}\n"
    
    # Provide domain context
    domain_context = """
Dies ist ein System zur Datenabfrage für ein Pflegevermittlungsunternehmen.
Die Hauptentitäten sind:
- Leads: Potentielle Kunden, die Interesse gezeigt haben
- Kunden/Haushalte: Personen mit aktiven Verträgen
- Verträge: Vereinbarungen zwischen Kunden und Agenturen
- Care Stays: Konkrete Pflegeeinsätze mit Pflegekräften
- Agenturen: Vermitteln Pflegekräfte an Kunden
- Pflegekräfte: Personen, die Pflegedienste anbieten
"""
    
    # Decision tree guidance
    decision_tree = """
Folge diesem Entscheidungsprozess:
1. Identifiziere das Hauptthema der Anfrage: Kunden, Verträge, Einsätze, Agenturen, Statistik
2. Prüfe zeitliche Dimension: aktuell, vergangen, zukünftig, Zeitraum?
3. Bestimme spezifische Entitäten: bestimmter Kunde, alle Kunden, bestimmte Agentur?
4. Wähle die Query mit der höchsten Spezifität für diese Kombination

Beispielentscheidungen:
- "Zeige aktuelle Einsätze" → get_active_care_stays_now (aktueller Zeitpunkt)
- "Zeige Einsätze im Mai" → get_care_stays_by_date_range (spezifischer Zeitraum)
- "Zeige Kunde Müller" → get_customer_history (spezifischer Kunde)
- "Wieviel Umsatz im letzten Quartal?" → get_monthly_performance (Umsatzstatistik mit Zeitraum)
- "Welche Kündigungen gab es im Mai?" → get_contract_terminations (Kündigungsstatistik mit Zeitraum)
- "Wie viele Kunden habe ich aktuell?" → get_active_care_stays_now (aktuelle Kundenzahl)
- "Wie viele Kunden sind in Pause?" → get_customers_on_pause (Kunden ohne aktiven Care Stay)
- "Wie viele neue Kunden habe ich abgeschlossen?" → get_contract_count (neue Vertragsabschlüsse)
- "Welche neuen Verträge habe ich abgeschlossen?" → get_contract_details (detaillierte Vertragsdetails)
- "Wie viele Leads habe ich gekauft?" → get_leads_count (Anzahl der Leads)
- "Welche Leads habe ich gekauft?" → get_leads (detaillierte Lead-Details)
- "Was ist meine Abschlussquote?" → get_cvr_lead_contract (Conversion Rate Leads zu Verträgen)
- "Wie viele neu abgeschlossene Kunden oder Verträge habe ich?" → get_contract_count (neue Vertragsabschlüsse)
- "Welche Verträge habe ich abgeschlossen?" → get_contract_details (detaillierte Vertragsdetails)
"""
    
    # Create the prompt content
    prompt_content = f"""
You are a query selection assistant for a senior care database system. Your task is to select the most appropriate database query based on a user's request.

{domain_context}

{current_time_context}

{history_context}

User request: "{user_request}"

Available queries:
{json.dumps(query_descriptions, indent=2)}

{decision_tree}

Instructions:
1. Analyze the user request to understand the semantic meaning and intent
2. Consider which required parameters are available or can be inferred from the request
3. Select the most appropriate query from the available options
4. Explain your reasoning for this selection
5. Identify any parameters that need to be extracted from the request

Date Parameter Handling:
- ALWAYS use the CURRENT SYSTEM DATE as the end_date when the user says "since X" or "from X" without specifying an end date
- For phrases like "in the last X days/weeks/months", calculate the start_date from the current system date and set end_date to the current system date
- For specific time periods like "in January", determine both start_date and end_date based on the mentioned period
- For questions about "this month/quarter/year", use the beginning of the current month/quarter/year as start_date and current system date as end_date
- Today's date should be determined dynamically from the system, not hardcoded

Important considerations:
- Zeit-basierte Abfragen (wie get_care_stays_by_date_range) benötigen klar definierte Zeiträume
- Performance-Abfragen (wie get_monthly_performance) benötigen spezifische Zeiträume
- Für Fragen nach aktiven Kunden oder der aktuellen Kundenzahl IMMER get_active_care_stays_now verwenden
- Für Fragen nach Kunden in Pause/Betreuungspause NUR get_customers_on_pause verwenden
- Für Fragen nach Umsatz oder Einnahmen get_revenue_by_agency oder get_monthly_performance bevorzugen
- Für Fragen nach spezifischen Kunden get_customer_history bevorzugen
- Für Fragen nach Kündigungen oder Vertragsenden get_contract_terminations verwenden und immer 'ernsthaft' und 'agenturwechsel' separat und summiert zurückgeben
- Für Fragen nach gekündigten Verträgen mit Unterscheidung zwischen 'ernsthaften' Kündigungen und 'Agenturwechsel' get_contract_terminations verwenden
- Für Fragen nach Tickets get_customer_tickets verwenden
- Für Fragen nach Betreuungskräften/Pflegekräften bei einem bestimmten Kunden get_care_givers_for_customer verwenden
- Für Fragen nach der ANZAHL von Leads und gekauften Kontakten get_leads_count verwenden
- Für Fragen nach WELCHE Leads gekauft wurden oder bei Anfragen nach Details zu Leads get_leads verwenden
- Für Fragen nach Abschlussquoten oder Conversion Rate IMMER get_cvr_lead_contract mit Zeitraumfilter verwenden
- Für Fragen nach der ANZAHL neu abgeschlossener Kunden oder Verträge IMMER get_contract_count verwenden
- Für Fragen nach WELCHE Verträge abgeschlossen wurden oder bei Anfragen nach Details zu neuen Verträgen get_contract_details verwenden

Format your response as JSON with these fields:
- selected_query: [query name]
- reasoning: [explanation]
- parameters: [extracted parameters object with parameter names as keys]
- confidence: [1-5 scale, where 5 is highest confidence]
- parameter_extraction_strategy: [explanation of how parameters should be obtained if they're not clear from the request]
"""
    
    # Return as messages array for API call
    return [
        {"role": "system", "content": "You are a query selection assistant for a database system. Respond only with valid JSON."},
        {"role": "user", "content": prompt_content}
    ]

def post_process_llm_parameters(user_request: str, parameters: Dict) -> Dict:
    """
    Post-processes parameters extracted by the LLM to make sure date handling is correct,
    especially for queries with "since" or relative time references.
    
    Args:
        user_request: The original user request
        parameters: The parameters extracted by the LLM
        
    Returns:
        The updated parameters dict
    """
    user_request_lower = user_request.lower()
    today = datetime.datetime.now().date()
    
    # Handle "since" expressions specifically
    if ('start_date' in parameters and 'end_date' not in parameters and 
        any(term in user_request_lower for term in ['seit', 'since', 'from', 'ab dem'])):
        # If user asked about something "since X date" but no end_date was specified,
        # set end_date to today
        parameters['end_date'] = today.strftime('%Y-%m-%d')
        logger.info(f"'Seit' erkannt ohne Enddatum, setze end_date auf heute: {parameters['end_date']}")
    
    # Handle other date scenarios if needed
    
    return parameters

def call_llm(messages: List[Dict], model: str = "gpt-3.5-turbo") -> str:
    """Send messages to LLM and get response
    
    This is a placeholder function - replace with your actual LLM call implementation.
    """
    # For demo purposes we'll use OpenAI, but this should be replaced with your actual LLM setup
    try:
        import openai
        
        # If using OpenAI
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning("OpenAI API key not found. Using mock response for demo.")
            return '{"selected_query": "get_active_care_stays_now", "reasoning": "Mock response", "parameters": {"seller_id": "user_id"}, "confidence": 3, "parameter_extraction_strategy": "Get seller_id from user session"}'
        
        # Current OpenAI API syntax
        response = openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,  # Low temperature for more deterministic responses
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling LLM: {e}")
        # Fallback response
        return '{"selected_query": "get_active_care_stays_now", "reasoning": "Fallback due to error", "parameters": {"seller_id": "user_id"}, "confidence": 1, "parameter_extraction_strategy": "Get seller_id from user session"}'

def parse_llm_response(response_text: str) -> Dict:
    """Parse the LLM response into a structured format"""
    try:
        # Attempt to parse the response as JSON
        return json.loads(response_text)
    except json.JSONDecodeError:
        # If JSON parsing fails, try to extract the JSON part from the response
        logger.warning("Failed to parse LLM response as JSON. Attempting to extract JSON.")
        try:
            # Look for JSON-like patterns in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                return json.loads(json_str)
        except Exception as nested_e:
            logger.error(f"Failed to extract JSON from response: {nested_e}")
        
        # Return a fallback response if all parsing fails
        return {
            "selected_query": "get_active_care_stays_now",  # Default query
            "reasoning": "Failed to parse LLM response",
            "parameters": {"seller_id": "user_id"},
            "confidence": 0,
            "parameter_extraction_strategy": "Get seller_id from user session"
        }

def log_selection_for_feedback(user_request: str, selection_data: Dict, result_success: bool = None) -> None:
    """Log query selection for feedback and improvement"""
    try:
        feedback_log = {
            "timestamp": str(datetime.datetime.now()),
            "user_request": user_request,
            "selected_query": selection_data.get("selected_query"),
            "confidence": selection_data.get("confidence"),
            "reasoning": selection_data.get("reasoning"),
            "success": result_success
        }
        
        # Append to feedback log file
        with open("query_selection_feedback.jsonl", "a") as f:
            f.write(json.dumps(feedback_log) + "\n")
            
    except Exception as e:
        logger.error(f"Error logging selection feedback: {e}")

def select_query_with_llm(
    user_request: str, 
    conversation_history: Optional[List[Dict]] = None,
    user_id: Optional[str] = None
) -> Tuple[str, Dict, Optional[Dict]]:
    """Select the most appropriate query using LLM
    
    Args:
        user_request: The user's natural language request
        conversation_history: Optional list of previous conversation messages
        user_id: Optional user ID for parameter extraction
        
    Returns:
        Tuple containing (selected_query_name, parameters_dict, human_in_loop_dict)
        where human_in_loop_dict is None if no clarification is needed, otherwise contains clarification info
    """
    # Create prompt messages
    messages = create_query_selection_prompt(user_request, conversation_history)
    
    # Call LLM
    llm_response = call_llm(messages)
    
    # Parse response
    parsed_response = parse_llm_response(llm_response)
    
    # Get the selected query and parameters
    selected_query = parsed_response.get("selected_query")
    parameters = parsed_response.get("parameters", {})
    confidence = parsed_response.get("confidence", 0)
    
    # Post-process parameters to handle date expressions correctly
    parameters = post_process_llm_parameters(user_request, parameters)
    
    # If user_id is provided and seller_id is needed, use it
    if user_id and "seller_id" in parameters and parameters["seller_id"] == "user_id":
        parameters["seller_id"] = user_id
    
    # Log selection for feedback if confidence is low
    if confidence < 3:
        log_selection_for_feedback(user_request, parsed_response)
    
    # Check if human-in-the-loop is needed
    human_in_loop = check_for_human_in_loop(user_request, selected_query, parameters, confidence)
    
    return selected_query, parameters, human_in_loop

def check_for_human_in_loop(
    user_request: str, 
    selected_query: str, 
    parameters: Dict,
    confidence: int
) -> Optional[Dict]:
    """Check if clarification is needed and return a text question instead of button options
    
    Args:
        user_request: The original user request
        selected_query: The selected query name
        parameters: The extracted parameters
        confidence: The confidence level (1-5)
        
    Returns:
        None if no clarification needed, otherwise a dict with clarification message
    """
    # Die Entscheidung wird nun vollständig dem LLM überlassen
    # Eine Rückfrage wird nur noch gestellt, wenn die Konfidenz niedrig ist
    
    # Low confidence triggers clarification
    if confidence < 3:
        logger.info(f"Niedrige Konfidenz ({confidence}) für {selected_query}, erstelle text-basierte Rückfrage")
        
        # Falls es sich um eine Kundenanfrage handelt
        if selected_query == "get_customer_history" and "customer_name" in parameters:
            customer_name = parameters.get("customer_name", "unbekannt")
            logger.info(f"Erstelle text-basierte Rückfrage für Kunden: {customer_name}")
            
            # Wir speichern hier die möglichen Queries für die spätere Verarbeitung
            available_queries = {
                "historiedaten": "get_customer_history",
                "historie": "get_customer_history",
                "kundenhistorie": "get_customer_history",
                "kundendaten": "get_customer_history",
                "ticket": "get_customer_tickets",
                "tickets": "get_customer_tickets",
                "ticketinhalte": "get_customer_tickets",
                "vertrag": "get_customer_contracts",
                "verträge": "get_customer_contracts",
                "vertragsinformationen": "get_customer_contracts"
            }
            
            return {
                "type": "text_clarification",
                "query": selected_query,
                "message": f"Ich kann dir verschiedene Informationen zu {customer_name} geben. Möchtest du allgemeine Kundenhistorie, Ticketinhalte oder Vertragsinformationen?",
                "context": {
                    "customer_name": customer_name,
                    "clarification_type": "customer_info",
                    "available_queries": available_queries
                }
            }
        
        # Agency queries that might need clarification
        elif selected_query in ["get_agency_performance", "get_revenue_by_agency"]:
            logger.info(f"Erstelle text-basierte Zeitraum-Rückfrage für {selected_query}")
            
            # Wir speichern hier die möglichen Zeiträume für die spätere Verarbeitung
            available_timeframes = {
                "letzter monat": "last_month",
                "letzten monat": "last_month",
                "diesen monat": "current_month",
                "aktueller monat": "current_month",
                "aktuelles quartal": "current_quarter",
                "dieses quartal": "current_quarter",
                "dieses jahr": "year_to_date",
                "jahr": "year_to_date",
                "gesamtes jahr": "year_to_date"
            }
            
            return {
                "type": "text_clarification",
                "query": selected_query,
                "message": f"Für welchen Zeitraum möchtest du die Informationen sehen? Zum Beispiel 'letzter Monat', 'aktuelles Quartal' oder 'dieses Jahr'?",
                "context": {
                    "clarification_type": "timeframe",
                    "original_query": selected_query,
                    "available_timeframes": available_timeframes
                }
            }
        
        # General low confidence handling
        else:
            # Use the available query patterns to suggest alternatives
            query_patterns = load_query_patterns()
            
            # Hole die 3 wahrscheinlichsten Abfragen als Vorschläge
            potential_queries = [selected_query] + [q for q in query_patterns.keys() if q != selected_query][:2]
            query_descriptions = []
            
            for query in potential_queries:
                description = query_patterns.get(query, {}).get("description", query)
                query_descriptions.append(f"'{description}'")
            
            # Erstelle eine textbasierte Rückfrage
            options_text = ", ".join(query_descriptions[:-1]) + " oder " + query_descriptions[-1]
            
            # Dictionary zur Zuordnung von Beschreibung zu Query erstellen
            query_mapping = {}
            for query in potential_queries:
                description = query_patterns.get(query, {}).get("description", query).lower()
                query_mapping[description.lower()] = query
            
            return {
                "type": "text_clarification",
                "query": selected_query,
                "message": f"Ich bin mir nicht sicher, welche Informationen du genau suchst. Möchtest du {options_text}?",
                "context": {
                    "clarification_type": "query_selection",
                    "original_parameters": parameters.copy(),
                    "query_mapping": query_mapping
                }
            }
    
    # No clarification needed
    logger.info(f"Keine Rückfrage nötig für {selected_query}")
    return None

# Function to process user's text clarification response
def process_text_clarification_response(
    clarification_context: Dict,
    user_response: str,
    original_user_request: str
) -> Tuple[str, Dict]:
    """Process the user's text response to a clarification question
    
    Args:
        clarification_context: The context from the original clarification
        user_response: The user's text response to the clarification
        original_user_request: The original user request
        
    Returns:
        Tuple containing (selected_query_name, parameters_dict)
    """
    logger.info(f"Processing text clarification response: '{user_response}'")
    
    # Lowercase for better matching
    user_response_lower = user_response.lower()
    
    # Get the clarification type from context
    clarification_type = clarification_context.get("clarification_type")
    
    # Initialize default values
    selected_query = None
    parameters = {}
    
    if clarification_type == "customer_info":
        # Handle customer information clarification
        customer_name = clarification_context.get("customer_name")
        available_queries = clarification_context.get("available_queries", {})
        
        # Try to match response with available queries
        selected_query = None
        for keyword, query in available_queries.items():
            if keyword in user_response_lower:
                selected_query = query
                break
        
        # Default to customer history if no match
        if not selected_query:
            # If response is vague, default to history
            if any(word in user_response_lower for word in ["ja", "alles", "allgemein", "all", "info"]):
                selected_query = "get_customer_history"
            else:
                # Parse intent with simple keyword matching
                if any(word in user_response_lower for word in ["ticket", "support", "probleme"]):
                    selected_query = "get_customer_tickets"
                elif any(word in user_response_lower for word in ["vertrag", "vertrage", "verträge"]):
                    selected_query = "get_customer_contracts"
                else:
                    selected_query = "get_customer_history"  # Default
        
        # Set parameters
        parameters = {"customer_name": customer_name}
        
    elif clarification_type == "timeframe":
        # Handle timeframe clarification
        original_query = clarification_context.get("original_query")
        available_timeframes = clarification_context.get("available_timeframes", {})
        
        # Try to match response with available timeframes
        selected_timeframe = None
        for keyword, timeframe in available_timeframes.items():
            if keyword in user_response_lower:
                selected_timeframe = timeframe
                break
        
        # Default to current month if no match
        if not selected_timeframe:
            if "letzte" in user_response_lower or "vergangene" in user_response_lower:
                selected_timeframe = "last_month"
            elif "quartal" in user_response_lower:
                selected_timeframe = "current_quarter"
            elif "jahr" in user_response_lower:
                selected_timeframe = "year_to_date"
            else:
                selected_timeframe = "current_month"  # Default
        
        # Set query and parameters
        selected_query = original_query
        parameters = {"timeframe": selected_timeframe}
        
    elif clarification_type == "query_selection":
        # Handle query selection clarification
        query_mapping = clarification_context.get("query_mapping", {})
        original_parameters = clarification_context.get("original_parameters", {})
        
        # Try to match response with query descriptions
        for description, query in query_mapping.items():
            if description in user_response_lower:
                selected_query = query
                break
        
        # If no match found, use the first option as default
        if not selected_query and query_mapping:
            selected_query = list(query_mapping.values())[0]
        
        # Set parameters (use original parameters)
        parameters = original_parameters
    
    else:
        # Fallback for unknown clarification type
        logger.warning(f"Unknown clarification type: {clarification_type}")
        # Use a generic approach based on keywords in the response
        if "kunde" in user_response_lower or "kunden" in user_response_lower:
            selected_query = "get_customer_history"
        elif "vertrag" in user_response_lower or "verträge" in user_response_lower:
            selected_query = "get_customer_contracts"
        elif "ticket" in user_response_lower:
            selected_query = "get_customer_tickets"
        elif "leistung" in user_response_lower or "performance" in user_response_lower:
            selected_query = "get_agency_performance"
        else:
            # Default to a general query
            selected_query = "get_agency_performance"
    
    # Log the clarification process
    try:
        clarification_log = {
            "timestamp": str(datetime.datetime.now()),
            "original_request": original_user_request,
            "user_response": user_response,
            "selected_query": selected_query,
            "parameters": parameters
        }
        
        with open("text_clarification_log.jsonl", "a") as f:
            f.write(json.dumps(clarification_log) + "\n")
    except Exception as e:
        logger.error(f"Error logging text clarification: {e}")
    
    logger.info(f"Selected query from text clarification: {selected_query} with parameters: {parameters}")
    return selected_query, parameters


# Legacy function to process button-based clarification response (for backward compatibility)
def process_clarification_response(
    clarification_option: Dict, 
    original_user_request: str
) -> Tuple[str, Dict]:
    """Process the user's response to a button-based clarification question
    
    Args:
        clarification_option: The option selected by the user
        original_user_request: The original user request
        
    Returns:
        Tuple containing (selected_query_name, parameters_dict)
    """
    # Log that a human-in-the-loop clarification was used
    try:
        clarification_log = {
            "timestamp": str(datetime.datetime.now()),
            "original_request": original_user_request,
            "clarification_option": clarification_option
        }
        
        with open("clarification_log.jsonl", "a") as f:
            f.write(json.dumps(clarification_log) + "\n")
    except Exception as e:
        logger.error(f"Error logging clarification: {e}")
    
    # Return the selected query and parameters from the clarification option
    return clarification_option.get("query"), clarification_option.get("params", {})

# Function to update the feedback with the result
def update_selection_feedback(user_request: str, selected_query: str, success: bool) -> None:
    """Update the feedback log with the success/failure of the query"""
    try:
        # Read the existing log
        feedback_entries = []
        if os.path.exists("query_selection_feedback.jsonl"):
            with open("query_selection_feedback.jsonl", "r") as f:
                for line in f:
                    entry = json.loads(line.strip())
                    feedback_entries.append(entry)
        
        # Find and update the matching entry
        for entry in feedback_entries:
            if (entry.get("user_request") == user_request and 
                entry.get("selected_query") == selected_query and
                entry.get("success") is None):
                entry["success"] = success
                entry["updated_at"] = str(datetime.datetime.now())
                break
        
        # Write the updated log
        with open("query_selection_feedback.jsonl", "w") as f:
            for entry in feedback_entries:
                f.write(json.dumps(entry) + "\n")
                
    except Exception as e:
        logger.error(f"Error updating selection feedback: {e}")