"""
OpenAI utility functions for the XORA application.
This module contains functions for interacting with the OpenAI API.
"""

import json
import logging
import openai
import tiktoken
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

def count_tokens(messages, model=None):
    """
    Zählt die Token in einer Liste von Nachrichten für das angegebene Modell.
    
    Args:
        messages: Liste von Nachrichten im Format {'role': '...', 'content': '...'}
        model: Zu verwendendes Modell (Standard: gpt-4o)
        
    Returns:
        int: Anzahl der Token
    """
    model = 'gpt-4o'
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    token_count = 0
    for msg in messages:
        token_count += len(encoding.encode(msg['content']))
        token_count += 4
    token_count += 2
    return token_count

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

def create_system_prompt(table_schema=None):
    """
    Erstellt einen System-Prompt für OpenAI basierend auf dem Datenbankschema.
    
    Args:
        table_schema: Schema der Datenbank-Tabellen (Default: None)
        
    Returns:
        str: Der generierte System-Prompt
    """
    # Bestehendes System-Prompt generieren
    prompt = "Du bist ein hilfreicher KI-Assistent, der bei der Verwaltung von Pflegedaten hilft."
    prompt += "\n\nDu hast Zugriff auf eine Datenbank mit folgenden Tabellen:\n"
    
    if table_schema:
        for table_name, table_info in table_schema.get("tables", {}).items():
            prompt += f"\n- {table_name}: {table_info.get('description', 'Keine Beschreibung')}"
            prompt += "\n  Felder:"
            for field_name, field_info in table_info.get("fields", {}).items():
                prompt += f"\n    - {field_name}: {field_info.get('description', 'Keine Beschreibung')}"
    
    # Ergänze das Prompt mit wichtigen Anweisungen zur Funktionsnutzung
    prompt += """
    
    KRITISCH WICHTIG: Du bist ein Assistent, der NIEMALS Fragen zu Datenbank-Daten direkt beantwortet!
    
    1. Bei JEDER Frage zu Care Stays, Verträgen, Leads oder anderen Daten MUSST du eine der bereitgestellten Funktionen verwenden.
    2. Ohne Funktionsaufruf hast du KEINEN Zugriff auf aktuelle Daten.
    3. Generiere NIEMALS Antworten aus eigenem Wissen, wenn die Information in der Datenbank zu finden ist.
    4. Bei zeitbezogenen Anfragen (z.B. "im Mai") nutze IMMER die Funktion get_care_stays_by_date_range.
    
    Dein Standardverhalten bei Datenabfragen:
    1. Analysiere die Nutzerfrage
    2. Wähle die passende Funktion
    3. Rufe die Funktion mit korrekten Parametern auf
    4. Warte auf das Ergebnis
    5. Nutze dieses Ergebnis für deine Antwort
    """
    
    return prompt
