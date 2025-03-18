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
"""
    
    # Create the prompt content
    prompt_content = f"""
You are a query selection assistant for a senior care database system. Your task is to select the most appropriate database query based on a user's request.

{domain_context}

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

Important considerations:
- Time-based queries (like get_care_stays_by_date_range) need clear date ranges
- Performance queries (like get_monthly_performance) need specific time periods
- For questions about active care stays, prefer get_active_care_stays_now
- For questions about revenue or earnings, prefer get_revenue_by_agency or get_monthly_performance
- For questions about specific customers, prefer get_customer_history
- For terminations or contract ends, prefer get_contract_terminations and always give back 'ernsthafte' terminations and 'agenturwechsel' separately and as a sum
- For questions about terminated contracts with distinctions between 'ernsthaft' terminations and 'agenturwechsel', use get_contract_terminations
- For questions about "Pause". "Betreuungspause" or any other terms which describes a customer still be under contract but currently without carestay, use get_customers_on_pause
- For questions about tickets, use get_customer_tickets

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
    """Check if human-in-the-loop clarification is needed
    
    Args:
        user_request: The original user request
        selected_query: The selected query name
        parameters: The extracted parameters
        confidence: The confidence level (1-5)
        
    Returns:
        None if no clarification needed, otherwise a dict with clarification info
    """
    # Cases that trigger human-in-the-loop clarification:
    # 1. Low confidence in query selection
    # 2. Customer-specific queries without sufficient specificity
    # 3. Ambiguous time frames
    # 4. Specific query types that often need clarification
    
    # Prüfen auf den Kunden "Küll" im Text selbst (unabhängig von Parametern)
    user_request_lower = user_request.lower()
    kull_variations = ["küll", "kull", "kühl", "kuehl", "kuell"]
    
    is_kull_request = False
    for variation in kull_variations:
        if variation in user_request_lower:
            is_kull_request = True
            # Wenn Küll im Text ist, aber nicht in den Parametern, fügen wir ihn hinzu
            if "customer_name" not in parameters:
                parameters["customer_name"] = "Küll"
                logger.info("Spezialfall: Kunde 'Küll' erkannt und Parameter ergänzt")
            else:
                # Wenn ein anderer Kunde in den Parametern ist, prüfen und ggf. korrigieren
                if parameters["customer_name"].lower() not in kull_variations:
                    logger.warning(f"Parameter-Kunde '{parameters['customer_name']}' stimmt nicht mit erkanntem Küll überein")
                    parameters["customer_name"] = "Küll"
            break
    
    # Customer-specific query with vague request
    if selected_query == "get_customer_history" and "customer_name" in parameters:
        # Spezialbehandlung für Kunde "Küll" (verschiedene Schreibweisen normalisieren)
        if parameters.get("customer_name", "").lower() in kull_variations:
            parameters["customer_name"] = "Küll"
            logger.info("Kundenname normalisiert zu 'Küll'")
            
        # Logs zur besseren Fehleranalyse
        logger.info(f"Human-in-loop Check für Kunde: {parameters.get('customer_name')}")
            
        # Rückfrage nur bei kurzen Anfragen oder bei Küll (da häufiger Kunde)
        if len(user_request.split()) < 12 or is_kull_request:
            customer_name = parameters.get("customer_name", "unbekannt")
            logger.info(f"Erstelle Human-in-the-Loop Rückfrage für Kunden: {customer_name}")
            
            # Parameter-Kopien für verschiedene Optionen erstellen
            history_params = parameters.copy()
            tickets_params = parameters.copy()
            contracts_params = parameters.copy()
            
            return {
                "type": "clarification",
                "query": selected_query,
                "message": f"Möchtest du eine allgemeine Zusammenfassung zur Kundenhistorie von {customer_name}, "
                          f"eine Auswertung der Ticketinhalte oder eine andere spezielle Art von Informationen?",
                "options": [
                    {"text": "Allgemeine Kundenhistorie", "query": "get_customer_history", "params": history_params},
                    {"text": "Ticketinhalte", "query": "get_customer_tickets", "params": tickets_params},
                    {"text": "Vertragsinformationen", "query": "get_customer_contracts", "params": contracts_params}
                ]
            }
    
    # Agency queries that might need clarification
    elif selected_query in ["get_agency_performance", "get_revenue_by_agency"]:
        if confidence < 4 or "date_from" not in parameters or "date_to" not in parameters:
            logger.info(f"Erstelle Zeitraum-Rückfrage für {selected_query}")
            
            # Parameter-Kopien für die verschiedenen Optionen
            month_params = parameters.copy()
            month_params["timeframe"] = "last_month"
            
            quarter_params = parameters.copy()
            quarter_params["timeframe"] = "current_quarter"
            
            year_params = parameters.copy() 
            year_params["timeframe"] = "year_to_date"
            
            return {
                "type": "clarification",
                "query": selected_query,
                "message": f"Möchtest du die Leistung für einen bestimmten Zeitraum sehen oder allgemeine Informationen?",
                "options": [
                    {"text": "Letzter Monat", "query": selected_query, "params": month_params},
                    {"text": "Aktuelles Quartal", "query": selected_query, "params": quarter_params},
                    {"text": "Gesamtes Jahr", "query": selected_query, "params": year_params}
                ]
            }
    
    # Low confidence for any query type
    elif confidence < 2:
        logger.info(f"Niedrige Konfidenz ({confidence}) für {selected_query}, erstelle Alternativen")
        
        # Use the available query patterns to suggest alternatives
        query_patterns = load_query_patterns()
        suggested_queries = []
        
        # Original parameters kopieren
        original_params = parameters.copy()
        
        # Add the originally selected query as an option
        suggested_queries.append({
            "text": query_patterns.get(selected_query, {}).get("description", selected_query),
            "query": selected_query,
            "params": original_params
        })
        
        # Add 2-3 other potential queries as options
        potential_queries = [q for q in query_patterns.keys() if q != selected_query][:2]
        for query in potential_queries:
            # Leere parameter für Alternativen
            alt_params = {}
            # Falls Kundenname oder andere wichtige Parameter vorhanden sind, übernehmen
            if "customer_name" in parameters:
                alt_params["customer_name"] = parameters["customer_name"]
            
            suggested_queries.append({
                "text": query_patterns.get(query, {}).get("description", query),
                "query": query,
                "params": alt_params
            })
        
        return {
            "type": "clarification",
            "query": selected_query,
            "message": "Ich bin mir nicht sicher, welche Informationen du genau suchst. Bitte wähle eine der folgenden Optionen:",
            "options": suggested_queries
        }
    
    # No clarification needed
    logger.info(f"Keine Rückfrage nötig für {selected_query}")
    return None

# Function to process user's clarification response
def process_clarification_response(
    clarification_option: Dict, 
    original_user_request: str
) -> Tuple[str, Dict]:
    """Process the user's response to a clarification question
    
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