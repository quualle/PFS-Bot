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
        query_descriptions.append({
            "name": query_name,
            "description": query_data.get("description", ""),
            "required_parameters": query_data.get("required_parameters", []),
            "optional_parameters": query_data.get("optional_parameters", []),
            "result_structure": query_data.get("result_structure", {})
        })
    
    # Include conversation history context if available
    history_context = ""
    if conversation_history and len(conversation_history) > 0:
        history_context = "Previous conversation:\n"
        for i, message in enumerate(conversation_history[-3:]):  # Include last 3 messages
            role = message.get("role", "")
            content = message.get("content", "")
            history_context += f"{role}: {content}\n"
    
    # Create the prompt content
    prompt_content = f"""
You are a query selection assistant for a senior care database system. Your task is to select the most appropriate database query based on a user's request.

{history_context}

User request: "{user_request}"

Available queries:
{json.dumps(query_descriptions, indent=2)}

Instructions:
1. Analyze the user request to understand the semantic meaning and intent
2. Consider which required parameters are available or can be inferred from the request
3. Select the most appropriate query from the available options
4. Explain your reasoning for this selection
5. Identify any parameters that need to be extracted from the request

Important considerations:
- Time-based queries (like get_care_stays_by_date_range) need clear date ranges
- Customer queries (like get_customer_history) require identification information
- Performance queries (like get_monthly_performance) need specific time periods
- For questions about active care stays, prefer get_active_care_stays_now
- For questions about revenue or earnings, prefer get_revenue_by_agency or get_monthly_performance
- For questions about specific customers, prefer get_customer_history
- For terminations or contract ends, prefer get_contract_terminations

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
) -> Tuple[str, Dict]:
    """Select the most appropriate query using LLM
    
    Args:
        user_request: The user's natural language request
        conversation_history: Optional list of previous conversation messages
        user_id: Optional user ID for parameter extraction
        
    Returns:
        Tuple containing (selected_query_name, parameters_dict)
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
    
    return selected_query, parameters

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