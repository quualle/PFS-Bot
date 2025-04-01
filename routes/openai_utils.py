"""
OpenAI utility functions for the XORA application.
This module contains functions for interacting with the OpenAI API.
"""

import json
import logging
import openai
from flask import flash
from routes.utils import debug_print

def create_function_definitions():
    """
    Erstellt die Function-Definitionen für OpenAI's Function-Calling basierend auf 
    den definierten Abfragemustern.
    
    Returns:
        list: Eine Liste von Function-Definitionen im Format, das von OpenAI erwartet wird
    """
    function_definitions = [
        {
            "type": "function",
            "function": {
                "name": "get_care_stays",
                "description": "Gibt Informationen zu aktuellen Pflegeaufenthalten für den Verkäufer zurück",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["active", "all", "past"],
                            "description": "Filter für den Status der Aufenthalte"
                        }
                    },
                    "required": ["status"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_kpi_data",
                "description": "Gibt KPI-Daten (Key Performance Indicators) für den angegebenen Zeitraum zurück, z.B. Abschlussquote",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string", 
                            "format": "date",
                            "description": "Startdatum im Format YYYY-MM-DD"
                        },
                        "end_date": {
                            "type": "string",
                            "format": "date", 
                            "description": "Enddatum im Format YYYY-MM-DD"
                        }
                    },
                    "required": ["start_date", "end_date"]
                }
            }
        }
    ]
    return function_definitions

def contact_openai(messages, model=None):
    """
    Sendet Nachrichten an die OpenAI API und gibt die Antwort zurück.
    
    Args:
        messages: Liste von Nachrichten im OpenAI-Format
        model: Zu verwendendes Modell (Standard: gpt-4o)
        
    Returns:
        tuple: (Antworttext, tool_calls)
    """
    model = 'gpt-4o'  # Changed from gpt-4o-preview to gpt-4o to match the model used in the chat route
    debug_print("API Calls", "contact_openai wurde aufgerufen – jetzt auf gpt-4o gesetzt.")
    try:
        # Create the tool definitions first
        tools = create_function_definitions()
        
        # Add explicit tool_choice parameter to guide the model to use functions
        response = openai.chat.completions.create(
            model=model, 
            messages=messages,
            tools=tools,  # Add the tools parameter
            tool_choice="auto"  # Auto lets the model decide when to use functions
        )
        
        if response and response.choices:
            assistant_message = response.choices[0].message
            antwort_content = assistant_message.content.strip() if assistant_message.content else ""
            debug_print("API Calls", f"Antwort von OpenAI: {antwort_content}")

            # Check if the model chose to call a function
            tool_calls = assistant_message.tool_calls
            if tool_calls:
                debug_print("API Calls", f"Function Calls erkannt: {tool_calls}")
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    debug_print("API Calls", f"Funktion vom LLM gewählt: {function_name}, Argumente: {function_args}")

            return antwort_content, tool_calls  # Return both the content and tool calls
        else:
            antwort_content = "Keine Antwort erhalten."
            debug_print("API Calls", antwort_content)
            return antwort_content, None
        
    except Exception as e:
        debug_print("API Calls", f"Fehler: {e}")
        flash(f"Ein Fehler ist aufgetreten: {e}", 'danger')
        return None, None
