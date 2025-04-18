import json
import logging
import os
import datetime
from typing import Dict, List, Optional, Any, Tuple
import re
from conversation_manager import ConversationManager

# Setup logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s %(levelname)s:%(name)s:%(message)s', 
                   datefmt='%Y-%m-%d %H:%M:%S')
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
                try:
                    patterns = json.loads(content)
                    if not patterns or "common_queries" not in patterns:
                        logger.error("Invalid query_patterns.json format: missing common_queries")
                        return {}
                    return patterns.get("common_queries", {})
                except json.JSONDecodeError as je:
                    logger.error(f"JSON parsing error in query_patterns.json: {je}")
                    return {}
            logger.error("No valid JSON content found in query_patterns.json")
            return {}
    except FileNotFoundError:
        logger.error("query_patterns.json not found")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error loading query patterns: {e}")
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
This is a system for querying a database.
The main entities are:
- Leads: Potential customers who have shown interest
- Leads/Households: People with active contracts
- Contracts: Agreements between customers and agencies
- Care Stays: Specific care services with caregivers
- Agencies: Companies that provide caregivers to customers
- Caregivers: People who do the care services
"""
    
    # Create the prompt content
    prompt_content = f"""
You are a query selection assistant for a senior care database system. Your task is to select the most appropriate database query based on a user's request.

{domain_context}

Conversation history:
{history_context}

User request: "{user_request}"

Now this are the available queries:
{json.dumps(query_descriptions, indent=2)}

Selection Process:
1. Identify the main topic: Statistics, Customers/Leads, Contracts, Care Stays, Agencies
2. Check temporal dimension: current or specific period?
3. Determine specific entities: specific customer, all customers or specific agency?
4. Select the most specific matching query

General information for your understanding:
- ChatBotUser is a seller, who mediates between customers and agencies
- Sellers buy leads and try to convert them to customers
- Agencies propose caretakers via the seller to this customer
- Seller is the contactperson of the customer
- Seller communicates with the agency regarding the customer via tickets
- A caretaker beeing at the customer is called a care_stay.
- Technically a care_stay exists before the arrival of the caretaker, including information about arrival and departure.
- A contract has one or more care_stays hwich usualy are without a space in between. 
- If there is a space between care_stays, this is a pause.
- A termination ("Kündigung") is the end of a contract but might be not serious if the customer stays with the seller, but changes the agency. In this case the seller kept the customer.
- Seller asks this chatbot for data about the one customer or quantitative information about many customers like "how many customers/terminations/pauses/... do I have?"

Available Queries and Their Purpose:
- get_active_care_stays_now: Current active care stays elements (=how many customers are currently active)
- get_care_stays_by_date_range: MAIN FUNCTION for time-based queries (=how many customers have been active in a period)
- get_contract_terminations: All Contract terminations with separeted categories (serious_terminations and agency_switch_count) 
- get_customer_history: Complete customer history including all care_stay elements and contract elements 
- get_customer_on_pause: Customers currently on pause
- get_customer_tickets: All tickets written regarding a customer written with the contracted agency (customers dont write tickets)
- get_monthly_performance: Monthly performance metrics for a seller, also average commision per customer
- get_leads: gives back all leads which are owned by the seller, filtered by a time period, including many information
- get_leads_converted_to_customers: Leads converted to customers in given period
- get_care_givers_for_customer: Caregivers("BK"/"Pflegekraft") for a specific customer
- get_leads_count: Count of leads in a specific period
- get_contract_count: Count of new contracts in a period
- get_contract_details: Detailed information about a contract 
- get_cvr_lead_contract: Lead to contract conversion rate
- get_customers_on_pause: Customers currently on pause

Frequently Used Terms:
- Kunde: Customer, that usually has a contract with an agency. Can also be in the lead state
- Lead: Mostly a potential customer showing interest. Sometimes term is abused for customers
- Vertrag: Mostly used for technical state of beeing not a lead anymore, but having a care stay, that is in active state ("Bestätigt")
- Agentur: Company providing caregivers
- Kündigung: Termination/ of contract (serious or agency change)

Example User Questions:
- "Welche Pflegeinsätze habe ich gerade" → get_active_care_stays_now
- "Wie viele Kunden hatte ich im [Zeitraum]?" → get_care_stays_by_date_range
- "Was weisst du über den Kunden Müller?" → get_customer_history OR get_customer_tickets for qualitative information
- "Welche Kündigungen gab es im [Zeitraum]?" → get_contract_terminations
- "Wie viele Kunden sind in Pause?" → get_customers_on_pause
- "Was ist meine Abschlussquote?" → get_cvr_lead_contract
- "Was ist meine durchschnittliche Provision pro Kunde" → get_monthly_performance

Parameter Handling:
- Use CURRENT SYSTEM DATE as end_date for "since X" or "from X" without specified end
- For "last X days/weeks/months", calculate start_date from current date
- For specific periods like "in January", determine both start and end dates
- For "this month/quarter/year", use period start as start_date and current date as end_date
"""
    
    # Return as messages array for API call
    return [
        {"role": "system", "content": """Du bist ein Abfrage-Auswahlassistent für ein Datenbanksystem. 
Antworte NUR mit einem validen JSON-Objekt im folgenden Format:
{
  "query": "name_der_ausgewählten_abfrage",
  "parameters": { "param1": "wert1", "param2": "wert2" },
  "confidence": 5,  # Wert zwischen 1-5, wobei 5 die höchste Konfidenz darstellt
  "reasoning": "Kurze Begründung für die Auswahl dieser Abfrage"
}

Wichtig: Die "query" MUSS exakt einem der verfügbaren Abfragenamen entsprechen."""},
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

def call_llm(messages: List[Dict], model: str = "gpt-4o", expect_json: bool = True) -> str:
    """Send messages to LLM and get response
    
    This is a placeholder function - replace with your actual LLM call implementation.
    """
    # For demo purposes we'll use OpenAI, but this should be replaced with your actual LLM setup
    try:
        import openai
        
        # If using OpenAI
        if not os.getenv("OPENAI_API_KEY"):
            logger.warning("OpenAI API key not found. Using mock response for demo.")
            if expect_json:
                return '{"query": "get_active_care_stays_now", "parameters": {"seller_id": "user_id"}, "confidence": 3}'
            else:
                return "Bitte konkretisiere deine Anfrage. Möchtest du allgemeine Informationen oder spezifische Daten sehen?"
        
        # Call LLM with messages
        response = openai.chat.completions.create(
            model=model,
            messages=messages
              # Lower temperature for more deterministic responses
        )
        if expect_json:
            return response.choices[0].message.content
        else:
            return response.choices[0].message.content.strip()
            
    except Exception as e:
        logger.error(f"Error calling LLM: {e}")
        # Fallback response
        if expect_json:
            return '{"query": "get_active_care_stays_now", "parameters": {"seller_id": "user_id"}, "confidence": 1}'
        else:
            return "Bitte präzisiere deine Anfrage. Was genau möchtest du wissen?"

def parse_llm_response(response_text: str) -> Dict:
    """Parse the LLM response into a structured format"""
    if not response_text:
        logger.error("Empty response text received")
        return {}
        
    logger.debug(f"Parsing response text: {response_text[:200]}...")
    
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
                logger.debug(f"Extracted potential JSON: {json_str[:200]}...")
                return json.loads(json_str)
                
            # Try looking for code blocks with JSON
            code_block_matches = re.findall(r'```(?:json)?\s*({[\s\S]*?})\s*```', response_text)
            if code_block_matches:
                for match in code_block_matches:
                    try:
                        logger.debug(f"Found code block with potential JSON: {match[:200]}...")
                        return json.loads(match)
                    except json.JSONDecodeError:
                        continue
        except Exception as nested_e:
            logger.error(f"Failed to extract JSON from response: {nested_e}")
        
        # Return a fallback response if all parsing fails
        logger.error("All JSON parsing attempts failed")
        return {
            "query": "get_active_care_stays_now",  # Default query using correct field name
            "reasoning": "Failed to parse LLM response",
            "parameters": {"seller_id": "user_id"},
            "confidence": 0
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
) -> Tuple[Optional[str], Optional[Dict], Optional[Dict]]:
    """Select the most appropriate query using LLM
    
    Args:
        user_request: The user's natural language request
        conversation_history: Optional list of previous conversation messages
        user_id: Optional user ID for parameter extraction
        
    Returns:
        Tuple containing (selected_query_name, parameters_dict, human_in_loop_dict)
        where human_in_loop_dict is None if no clarification is needed, otherwise contains clarification info
        Returns (None, None, error_dict) if selection fails
    """
    # Logging the starting point of query selection
    logger.info(f"QUERY SELECTION START - User request: '{user_request}'")

    try:
        # Create selection prompt
        messages = create_query_selection_prompt(user_request, conversation_history)
        logger.info("QUERY SELECTION - Prompt creation complete")
        
        if not messages:
            logger.error("QUERY SELECTION ERROR - Failed to create query selection prompt")
            return None, None, {"error": "Fehler bei der Erstellung des Auswahlprompts"}

        # Get LLM response
        try:
            logger.info("QUERY SELECTION - Calling LLM for query classification")
            llm_response = call_llm(messages)
            logger.debug(f"QUERY SELECTION - Raw LLM response: {llm_response[:200]}...")
            
            if not llm_response:
                logger.error("QUERY SELECTION ERROR - Empty LLM response")
                return None, None, {"error": "Keine Antwort vom Sprachmodell erhalten"}
        except Exception as e:
            logger.error(f"QUERY SELECTION ERROR - LLM call failed: {e}")
            return None, None, {"error": "Fehler bei der Kommunikation mit dem Sprachmodell"}

        # Parse response
        try:
            logger.info("QUERY SELECTION - Parsing LLM response")
            selection_data = parse_llm_response(llm_response)
            
            if not selection_data:
                logger.error("QUERY SELECTION ERROR - Empty selection data after parsing")
                return None, None, {"error": "Leere Antwort vom Sprachmodell"}
                
            # Prüfe auf "query" oder "selected_query" als Fallback
            selected_query = None
            if "query" in selection_data:
                selected_query = selection_data.get("query")
            elif "selected_query" in selection_data:
                selected_query = selection_data.get("selected_query")
                selection_data["query"] = selected_query  # Für Konsistenz
            
            if not selected_query:
                logger.error("QUERY SELECTION ERROR - Missing query field in LLM response")
                logger.error(f"QUERY SELECTION ERROR - Response content: {llm_response[:200]}...")
                return None, None, {"error": "Ungültiges Antwortformat vom Sprachmodell"}
            
            logger.info(f"QUERY SELECTION - Selected query: '{selected_query}'")
                
        except Exception as e:
            logger.error(f"QUERY SELECTION ERROR - Failed to parse LLM response: {e}")
            logger.error(f"QUERY SELECTION ERROR - Response content: {llm_response[:200]}...")
            return None, None, {"error": "Fehler bei der Verarbeitung der Modellantwort"}

        parameters = selection_data.get("parameters", {})
        confidence = selection_data.get("confidence", 0)
        reasoning = selection_data.get("reasoning", "No reasoning provided")
        
        logger.info(f"QUERY SELECTION - Query: '{selected_query}', Confidence: {confidence}")
        logger.info(f"QUERY SELECTION - Reasoning: {reasoning}")
        logger.info(f"QUERY SELECTION - Parameters: {parameters}")

        # Post-process parameters
        try:
            logger.info("QUERY SELECTION - Post-processing parameters")
            parameters = post_process_llm_parameters(user_request, parameters)
            logger.info(f"QUERY SELECTION - Final parameters after post-processing: {parameters}")
        except Exception as e:
            logger.error(f"QUERY SELECTION ERROR - Parameter post-processing failed: {e}")
            return None, None, {"error": "Fehler bei der Parameterverarbeitung"}

        # Check confidence and need for clarification
        if confidence < 3:  # Niedrige Konfidenz
            logger.info(f"QUERY SELECTION - Low confidence ({confidence}) for query selection")
            logger.info("QUERY SELECTION - Checking for human-in-loop activation")
            human_in_loop = check_for_human_in_loop(user_request, selected_query, parameters, confidence)
            
            if human_in_loop:
                logger.info("QUERY SELECTION - Human-in-loop activated")
                if isinstance(human_in_loop, dict) and 'message' in human_in_loop:
                    logger.info(f"QUERY SELECTION - Human-in-loop message: '{human_in_loop['message']}'")
                return selected_query, parameters, human_in_loop
            else:
                logger.info("QUERY SELECTION - Human-in-loop not activated despite low confidence")

        # Log selection for feedback
        logger.info("QUERY SELECTION - Recording selection for feedback")
        log_selection_for_feedback(user_request, selection_data)
        
        logger.info("QUERY SELECTION COMPLETE - Returning selected query")
        return selected_query, parameters, None

    except Exception as e:
        logger.error(f"QUERY SELECTION ERROR - Unexpected error: {e}")
        return None, None, {"error": "Unerwarteter Fehler bei der Anfrageauswahl"}

def check_for_human_in_loop(
    user_request: str, 
    selected_query: str, 
    parameters: Dict,
    confidence: int
) -> Optional[Dict]:
    """Check if clarification is needed and return a text question
    
    Args:
        user_request: The original user request
        selected_query: The selected query name
        parameters: The extracted parameters
        confidence: The confidence level (1-5)
        
    Returns:
        None if no clarification needed, otherwise a dict with clarification message
    """
    
    logger.info(f"HUMAN-IN-LOOP - Starting check for query: {selected_query}")
    logger.debug(f"HUMAN-IN-LOOP - Parameters: {parameters}, Confidence: {confidence}")
    
    if confidence < 3:
        # Extrahiere den Kundennamen für Kontextinformationen
        customer_name = parameters.get("customer_name", "")
        logger.info(f"HUMAN-IN-LOOP - Low confidence detected: {confidence}/5. Customer name: '{customer_name}'")
        
        # Create a prompt for the LLM to generate a clarification question
        clarification_prompt = [
            {
                "role": "system", 
                "content": """Du bist ein hilfreicher Assistent für ein Pflegevermittlungssystem.
Deine Aufgabe ist es, präzise und hilfreiche Rückfragen zu formulieren, wenn eine Benutzeranfrage nicht eindeutig ist.

Verfügbare Queries und ihre Verwendung:
- get_active_care_stays_now: Aktuelle Pflegeeinsätze (benötigt optional eine Agentur-ID)
- get_care_stays_by_date_range: Pflegeeinsätze in einem Zeitraum (benötigt Start- und Enddatum)
- get_customer_history: Kundenhistorie (benötigt Kundennamen)
- get_contract_terminations: Vertragskündigungen in einem Zeitraum

Die Benutzeranfrage war zu ungenau, um direkt eine Datenabfrage durchzuführen. 
Stelle eine präzise, kurze Rückfrage, die hilft, die fehlenden Parameter zu erhalten.

Deine Rückfrage sollte:
- Höflich und hilfreich sein
- Sich auf den Kontext der ursprünglichen Anfrage beziehen
- Nach spezifischen Parametern fragen, die für die Abfrage benötigt werden
- Kurz und prägnant sein (max. 1-2 Sätze)
"""
            },
            {
                "role": "user", 
                "content": f"""
Benutzeranfrage: "{user_request}"

Ausgewählte Abfrage: {selected_query}

Verfügbare Parameter: {json.dumps(parameters)}

Generiere eine hilfreiche Rückfrage, um die notwendigen Informationen zu erhalten.
"""
            }
        ]
        
        logger.info(f"HUMAN-IN-LOOP - Generating clarification message for query: {selected_query}")
        try:
            # Call LLM to generate the clarification text
            clarification_message = call_llm(clarification_prompt, expect_json=False)
            logger.info(f"HUMAN-IN-LOOP - Generated clarification: '{clarification_message}'")
            
            # Check if there are reasonable parameter options to provide
            query_patterns = load_query_patterns()
            query_data = {}
            
            if selected_query in query_patterns:
                query_data = query_patterns[selected_query]
                logger.info(f"HUMAN-IN-LOOP - Found query pattern for: {selected_query}")
            
            # Load required parameters
            required_params = query_data.get("required_parameters", [])
            logger.info(f"HUMAN-IN-LOOP - Required parameters: {required_params}")
            
            # Check for missing required parameters
            missing_params = []
            for param in required_params:
                param_name = param.get("name", "")
                if not param_name:
                    continue
                    
                # Check if this parameter is missing or has a placeholder value
                param_value = parameters.get(param_name)
                if param_value is None or param_value == "" or param_value == "N/A":
                    missing_params.append(param_name)
            
            logger.info(f"HUMAN-IN-LOOP - Missing parameters: {missing_params}")
            
            if missing_params:
                logger.info(f"HUMAN-IN-LOOP - Activating human-in-loop for missing params: {missing_params}")
                return {
                    "message": clarification_message,
                    "missing_parameters": missing_params,
                    "query": selected_query,
                    "current_parameters": parameters
                }
            else:
                logger.info("HUMAN-IN-LOOP - No missing required parameters found")
                return None
                
        except Exception as e:
            logger.error(f"HUMAN-IN-LOOP ERROR - Failed to generate clarification: {e}")
            # Fallback to a generic clarification message
            return {
                "message": "Um Ihnen besser helfen zu können, könnten Sie bitte Ihre Anfrage präzisieren?",
                "query": selected_query,
                "current_parameters": parameters
            }
            
    logger.info("HUMAN-IN-LOOP - Not activated: confidence high enough")
    return None

def process_text_clarification_response(
    clarification_context: Dict,
    user_response: str,
    original_user_request: str,
    conversation_history: Optional[List[Dict]] = None
) -> Tuple[Optional[str], Optional[Dict]]:
    """Process the user's text response to a clarification question"""
    
    # Create conversation manager instance
    conv_manager = ConversationManager()
    
    # Check for simple affirmative responses first
    if conv_manager.is_affirmative_response(user_response):
        # If the user simply confirms, maintain original intent
        logger.info("Detected affirmative response, maintaining original query intent")
        original_query = clarification_context.get("original_query", "")
        original_parameters = clarification_context.get("original_parameters", {})
        
        if original_query:
            return original_query, original_parameters
    
    query_type = clarification_context.get("query_type")
    original_query = clarification_context.get("original_query", "")
    original_parameters = clarification_context.get("original_parameters", {})
    
    logger.debug(f"Processing clarification response: '{user_response}'")
    logger.debug(f"Clarification context: {clarification_context}")
    
    # Create a prompt for the LLM to analyze the response
    analysis_prompt = [
        {
            "role": "system",
            "content": """Du bist ein hilfreicher Assistent für ein Pflegevermittlungssystem.
Deine Aufgabe ist es, die Antwort des Benutzers auf eine Rückfrage zu analysieren und die passende Query auszuwählen.

WICHTIG: Achte auf den Konversationskontext und die Kontinuität.
Wenn ein Benutzer auf eine Rückfrage mit einer einfachen Bestätigung wie 'ja' oder 'ja bitte' antwortet,
wechsle NICHT das Thema. Führe stattdessen die zuvor besprochene Aktion aus.

Verfügbare Queries:
- get_customer_history: Vollständige Kundenhistorie (Verträge, Einsätze)
- get_customer_tickets: Kommunikationshistorie und Notizen
- get_care_stays_by_date_range: Kundenstatistiken für Zeiträume
- get_contract_terminations: Vertragskündigungen
- get_customers_on_pause: Kunden in Pause

Antworte im EXAKTEN JSON-Format:
{
  "selected_query": "name_der_query",
  "confidence": 5,
  "parameters": {}
}"""
        }
    ]
    
    # Include conversation history if available
    if conversation_history:
        # Add up to 3 most recent messages for context
        for i, msg in enumerate(conversation_history[-3:]):
            if isinstance(msg, dict) and "role" in msg and "content" in msg:
                analysis_prompt.append(msg)
    
    # Add user's response context
    analysis_prompt.append({
        "role": "user",
        "content": f"""Ursprüngliche Anfrage: "{original_user_request}"
Kontext der Rückfrage: {clarification_context}
Antwort des Benutzers: "{user_response}"

Wähle die am besten passende Query und Parameter basierend auf ALLEN verfügbaren Kontext.
Gib AUSSCHLIESSLICH ein JSON-Objekt zurück, keine zusätzlichen Erklärungen."""
    })
    
    try:
        # Get analysis from LLM
        llm_response = call_llm(analysis_prompt)
        logger.debug(f"Raw LLM response for clarification: {llm_response}")
        
        if not llm_response:
            logger.error("Empty LLM response for clarification")
            # Fallback to original query if possible
            if original_query:
                return original_query, original_parameters
            return None, None
            
        # Parse the LLM response
        try:
            # Try to parse as direct JSON
            analysis = json.loads(llm_response)
            selected_query = analysis.get("selected_query")
            parameters = analysis.get("parameters", {})
            
            # Add customer_name to parameters if it was in original_parameters
            if "customer_name" in original_parameters:
                parameters["customer_name"] = original_parameters["customer_name"]
                
            logger.info(f"Successfully parsed LLM response as JSON: {analysis}")
            return selected_query, parameters
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid LLM response format: {e}")
            logger.error(f"Failed JSON: {llm_response}")
            
            # Try to extract JSON from text response
            try:
                # Look for JSON pattern
                json_start = llm_response.find('{')
                json_end = llm_response.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    json_str = llm_response[json_start:json_end]
                    logger.debug(f"Extracted JSON string: {json_str}")
                    analysis = json.loads(json_str)
                    selected_query = analysis.get("selected_query")
                    parameters = analysis.get("parameters", {})
                    
                    # Add customer_name to parameters if it was in original_parameters
                    if "customer_name" in original_parameters:
                        parameters["customer_name"] = original_parameters["customer_name"]
                        
                    logger.info(f"Extracted JSON from LLM response: {analysis}")
                    return selected_query, parameters
            except Exception as ex:
                logger.error(f"Failed to extract JSON from response: {ex}")
            
            # Fallback to original query if possible
            if original_query:
                logger.info(f"Falling back to original query: {original_query}")
                return original_query, original_parameters
            
            # Last resort fallback to get_customer_history if customer_name is present
            if "customer_name" in original_parameters:
                logger.info(f"Last resort fallback to get_customer_history for customer: {original_parameters['customer_name']}")
                return "get_customer_history", original_parameters
                
            return None, None
            
    except Exception as e:
        logger.error(f"Error processing clarification response: {e}")
        # Fallback to original query if possible
        if original_query:
            return original_query, original_parameters
        return None, None

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

def determine_if_clarification_needed(query_possibilities, user_request, session_data=None):
    """
    Determine if clarification is needed based on query possibilities
    """
    # If no possibilities found, no clarification needed (we'll handle differently)
    if not query_possibilities:
        return None
    
    # Check for confidence levels
    top_confidence = 0
    selected_query = None
    parameters = {}
    
    # Find query with highest confidence
    for possibility in query_possibilities:
        confidence = possibility.get("confidence", 0)
        if confidence > top_confidence:
            top_confidence = confidence
            selected_query = possibility.get("query_name")
            parameters = possibility.get("parameters", {})
    
    # Need for human-in-loop decision based on confidence threshold
    if top_confidence < 5:  # Configurable threshold
        logger.debug(f"Confidence {top_confidence} below threshold, clarification needed")
        
        # Create a conversation-aware clarification prompt using ConversationManager
        conv_manager = ConversationManager()
        
        # Get conversation context if session data is provided
        context_prompt = ""
        if session_data and "conversation_history" in session_data:
            context_prompt = conv_manager.extract_conversation_topic(session_data)
            if context_prompt:
                context_prompt = f"\nAktuelle Gesprächskontext: {context_prompt}"
        
        # Create clarification message with context awareness
        clarification_message = f"""Ich sehe, dass Sie nach Informationen zu {selected_query} fragen.{context_prompt}
Bitte bestätigen Sie, dass ich die richtige Information abrufen soll, oder geben Sie weitere Details an."""
        
        return {
            "clarification_type": "text_clarification",
            "clarification_message": clarification_message,
            "possible_queries": [selected_query],
            "clarification_context": {
                "query_type": "general",
                "original_query": selected_query,
                "original_parameters": parameters
            }
        }
    
    return None