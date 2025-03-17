from flask import Blueprint, request, jsonify, session, current_app, Response, url_for, redirect
from werkzeug.security import check_password_hash
import json
import time
import os
import logging
import sys
import traceback
import uuid
from datetime import datetime, timedelta
import openai

api = Blueprint('api', __name__, url_prefix='/api')

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import BigQuery functions and query selector
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from bigquery_functions import handle_function_call, get_user_id_from_email
from query_selector import select_query_with_llm, update_selection_feedback

# Helper functions from app.py
def download_wissensbasis(max_retries=5, backoff_factor=1):
    """Lädt die Wissensbasis aus der Cloud oder local"""
    try:
        # First try local file
        local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "wissensbasis.json")
        if os.path.exists(local_path):
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
                
        # If no local file, try to load from themen.txt
        return lade_themen()
    except Exception as e:
        logging.error(f"Error downloading wissensbasis: {e}")
        return None

def lade_themen():
    """Lädt die Themen aus der Datei."""
    dateipfad = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "themen.txt")
    return lese_themenhierarchie(dateipfad)

def lese_themenhierarchie(dateipfad):
    """Liest die Themenhierarchie aus einer Textdatei."""
    themen_dict = {}
    aktuelles_thema = None
    aktuelles_unterthema = None
    
    try:
        with open(dateipfad, 'r', encoding='utf-8') as datei:
            for zeile in datei:
                zeile = zeile.strip()
                if not zeile:
                    continue
                
                if zeile.startswith('#'):  # Hauptthema
                    aktuelles_thema = zeile[1:].strip()
                    themen_dict[aktuelles_thema] = {}
                elif zeile.startswith('##'):  # Unterthema
                    aktuelles_unterthema = zeile[2:].strip()
                    if aktuelles_thema:
                        themen_dict[aktuelles_thema][aktuelles_unterthema] = {
                            "title": aktuelles_unterthema,
                            "beschreibung": "",
                            "inhalt": []
                        }
                elif aktuelles_thema and aktuelles_unterthema:  # Inhalt
                    themen_dict[aktuelles_thema][aktuelles_unterthema]["inhalt"].append(zeile)
        
        return themen_dict
    except Exception as e:
        logging.error(f"Fehler beim Lesen der Themenhierarchie: {e}")
        return {}

def store_chatlog(user_name, chat_history):
    """Speichert den Chat-Verlauf für statistische Zwecke"""
    try:
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "user_name": user_name,
            "chat_history": chat_history
        }
        # In a real implementation, this would be saved to a database or file
        logging.info(f"Chat log stored for user {user_name} at {timestamp}")
    except Exception as e:
        logging.error(f"Error storing chat log: {e}")

def store_feedback(feedback_type, comment, chat_history):
    """Speichert Feedback zu einer Antwort"""
    try:
        timestamp = datetime.now().isoformat()
        feedback_entry = {
            "timestamp": timestamp,
            "feedback_type": feedback_type,
            "comment": comment,
            "last_exchange": chat_history[-1] if chat_history else None
        }
        # In a real implementation, this would be saved to a database or file
        logging.info(f"Feedback stored: {feedback_type} at {timestamp}")
        return True
    except Exception as e:
        logging.error(f"Error storing feedback: {e}")
        return False

def calculate_chat_stats():
    """Berechnet Statistiken über die Chat-Nutzung"""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")
    year = now.strftime("%Y")
    
    # In a real implementation, this would query a database
    # Here we're just returning mock data
    return {
        "total": 1245,
        "year": 845,
        "month": 124,
        "today": 12
    }

def log_notfall_event(user_id, notfall_art, user_message):
    """Loggt ein Notfall-Event"""
    try:
        timestamp = datetime.now().isoformat()
        log_entry = {
            "timestamp": timestamp,
            "user_id": user_id,
            "notfall_art": notfall_art,
            "message": user_message
        }
        
        log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "notfall_logs.json")
        
        # Lade existierende Logs oder erstelle neue Liste
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []
        
        # Füge neuen Eintrag hinzu
        logs.append(log_entry)
        
        # Speichere zurück
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
            
        logging.info(f"Notfall-Event protokolliert für User {user_id}")
    except Exception as e:
        logging.error(f"Fehler beim Loggen des Notfall-Events: {e}")

def debug_print(category, message):
    """Debug-Ausgabe mit Zeitstempel und Kategorie"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{category}] {message}")
    sys.stdout.flush()

def load_tool_config():
    """Lädt die Tool-Konfiguration aus einer YAML-Datei"""
    TOOL_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tool_config.yaml")
    try:
        import yaml
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tool-Konfiguration: {e}")
        # Fallback-Konfiguration
        return {
            "tool_categories": {
                "time_query": {
                    "patterns": ["care stays", "carestays", "einsätze", "monat", "monatlich", "jahr", "jährlich"],
                    "default_tool": "get_care_stays_by_date_range"
                }
            },
            "fallback_tool": "get_active_care_stays_now"
        }

def extract_enhanced_date_params(query_text):
    """Erweiterte Extraktion von Datumsparametern aus einer Anfrage"""
    date_params = extract_date_params(query_text)  # Start mit einfacher Extraktion
    
    if not date_params:
        # Versuche mit dateparser für komplexere Formulierungen
        try:
            # Datumsbereiche in der Anfrage suchen
            query_lower = query_text.lower()
            
            # Versuche, spezifische Datumsmuster zu erkennen
            date_phrases = [
                "letzte woche", "diese woche", "nächste woche",
                "letztes jahr", "dieses jahr", "nächstes jahr",
                "letztes quartal", "dieses quartal", "nächstes quartal",
                "gestern", "heute", "morgen",
                "letzte 7 tage", "letzte 30 tage", "letzte 90 tage"
            ]
            
            for phrase in date_phrases:
                if phrase in query_lower:
                    # Berechne Start- und Enddatum basierend auf dem Datumsbegriff
                    now = datetime.now()
                    
                    if phrase == "letzte woche":
                        start_date = now - timedelta(days=now.weekday() + 7)
                        end_date = start_date + timedelta(days=6)
                    elif phrase == "diese woche":
                        start_date = now - timedelta(days=now.weekday())
                        end_date = start_date + timedelta(days=6)
                    elif phrase == "nächste woche":
                        start_date = now - timedelta(days=now.weekday()) + timedelta(days=7)
                        end_date = start_date + timedelta(days=6)
                    elif phrase == "letztes jahr":
                        start_date = datetime(now.year - 1, 1, 1)
                        end_date = datetime(now.year - 1, 12, 31)
                    elif phrase == "dieses jahr":
                        start_date = datetime(now.year, 1, 1)
                        end_date = datetime(now.year, 12, 31)
                    elif phrase == "nächstes jahr":
                        start_date = datetime(now.year + 1, 1, 1)
                        end_date = datetime(now.year + 1, 12, 31)
                    elif phrase == "letztes quartal":
                        current_quarter = (now.month - 1) // 3 + 1
                        if current_quarter == 1:
                            start_date = datetime(now.year - 1, 10, 1)
                            end_date = datetime(now.year - 1, 12, 31)
                        else:
                            start_month = (current_quarter - 2) * 3 + 1
                            end_month = (current_quarter - 1) * 3
                            start_date = datetime(now.year, start_month, 1)
                            end_date = datetime(now.year, end_month, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][end_month - 1])
                    elif phrase == "dieses quartal":
                        current_quarter = (now.month - 1) // 3 + 1
                        start_month = (current_quarter - 1) * 3 + 1
                        end_month = current_quarter * 3
                        start_date = datetime(now.year, start_month, 1)
                        end_date = datetime(now.year, end_month, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][end_month - 1])
                    elif phrase == "nächstes quartal":
                        current_quarter = (now.month - 1) // 3 + 1
                        if current_quarter == 4:
                            start_date = datetime(now.year + 1, 1, 1)
                            end_date = datetime(now.year + 1, 3, 31)
                        else:
                            start_month = current_quarter * 3 + 1
                            end_month = (current_quarter + 1) * 3
                            start_date = datetime(now.year, start_month, 1)
                            end_date = datetime(now.year, end_month, [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][end_month - 1])
                    elif phrase == "gestern":
                        start_date = now - timedelta(days=1)
                        start_date = datetime(start_date.year, start_date.month, start_date.day)
                        end_date = start_date
                    elif phrase == "heute":
                        start_date = datetime(now.year, now.month, now.day)
                        end_date = start_date
                    elif phrase == "morgen":
                        start_date = now + timedelta(days=1)
                        start_date = datetime(start_date.year, start_date.month, start_date.day)
                        end_date = start_date
                    elif phrase == "letzte 7 tage":
                        end_date = datetime(now.year, now.month, now.day)
                        start_date = end_date - timedelta(days=7)
                    elif phrase == "letzte 30 tage":
                        end_date = datetime(now.year, now.month, now.day)
                        start_date = end_date - timedelta(days=30)
                    elif phrase == "letzte 90 tage":
                        end_date = datetime(now.year, now.month, now.day)
                        start_date = end_date - timedelta(days=90)
                    
                    date_params['start_date'] = start_date.isoformat()
                    date_params['end_date'] = end_date.isoformat()
                    break
            
            # Wenn immer noch keine Daten gefunden wurden, versuche es mit dateparser
            if not date_params:
                import re
                # Einfache Datumsmuster mit dateparser versuchen
                date_strings = re.findall(r'\b\d{1,2}[\./]\d{1,2}[\./](?:\d{2}|\d{4})\b|\b\d{1,2}[\. ]+(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)[\. ]+\d{4}\b', query_text, re.IGNORECASE)
                
                if len(date_strings) >= 2:
                    # Wenn zwei Datumsangaben gefunden wurden, interpretiere sie als Start- und Enddatum
                    import dateparser
                    start_date = dateparser.parse(date_strings[0], languages=['de'])
                    end_date = dateparser.parse(date_strings[1], languages=['de'])
                    
                    if start_date and end_date:
                        date_params['start_date'] = start_date.isoformat()
                        date_params['end_date'] = end_date.isoformat()
                
        except Exception as e:
            logging.error(f"Fehler bei der erweiterten Datumsextraktion: {e}")
    
    return date_params

def extract_date_params(query_text):
    """Extrahiert Datumsparameter aus einer Anfrage"""
    date_params = {}
    
    # Einfache Monate erkennen
    months = {
        'januar': 1, 'februar': 2, 'märz': 3, 'april': 4, 'mai': 5, 'juni': 6,
        'juli': 7, 'august': 8, 'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12,
        'jan': 1, 'feb': 2, 'mär': 3, 'apr': 4, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'okt': 10, 'nov': 11, 'dez': 12
    }
    
    # Aktuelles Jahr und aktuellen Monat ermitteln
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Monatsnamen in der Anfrage suchen
    query_lower = query_text.lower()
    for month_name, month_number in months.items():
        if month_name in query_lower:
            # Start- und Enddatum für diesen Monat
            start_date = datetime(current_year, month_number, 1)
            if month_number == 12:
                end_date = datetime(current_year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(current_year, month_number + 1, 1) - timedelta(days=1)
            
            # ISO-Format für die Daten
            date_params['start_date'] = start_date.isoformat()
            date_params['end_date'] = end_date.isoformat()
            break
    
    # "Letzten Monat" erkennen
    if 'letzten monat' in query_lower or 'vormonat' in query_lower:
        # Letzten Monat berechnen
        if current_month == 1:
            last_month = 12
            last_month_year = current_year - 1
        else:
            last_month = current_month - 1
            last_month_year = current_year
        
        # Start- und Enddatum für den letzten Monat
        start_date = datetime(last_month_year, last_month, 1)
        if last_month == 12:
            end_date = datetime(last_month_year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(last_month_year, last_month + 1, 1) - timedelta(days=1)
        
        date_params['start_date'] = start_date.isoformat()
        date_params['end_date'] = end_date.isoformat()
    
    # "Diesen Monat" erkennen
    if 'diesen monat' in query_lower or 'aktuellen monat' in query_lower:
        # Start- und Enddatum für den aktuellen Monat
        start_date = datetime(current_year, current_month, 1)
        if current_month == 12:
            end_date = datetime(current_year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(current_year, current_month + 1, 1) - timedelta(days=1)
        
        date_params['start_date'] = start_date.isoformat()
        date_params['end_date'] = end_date.isoformat()
    
    # Jahr erkennen
    import re
    year_pattern = r'(20\d{2})'
    year_match = re.search(year_pattern, query_text)
    if year_match:
        year = int(year_match.group(1))
        # Wenn kein Monat spezifiziert wurde, nehmen wir das ganze Jahr
        if 'start_date' not in date_params:
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31)
            date_params['start_date'] = start_date.isoformat()
            date_params['end_date'] = end_date.isoformat()
    
    return date_params

def create_system_prompt(table_schema):
    """Erstellt den System-Prompt für den Bot"""
    prompt = "Du bist ein hilfreicher KI-Assistent, der bei der Verwaltung von Pflegedaten hilft."
    prompt += "\n\nDu hast Zugriff auf eine Datenbank mit folgenden Tabellen:\n"
    
    for table_name, table_info in table_schema.get("tables", {}).items():
        prompt += f"\n- {table_name}: {table_info.get('description', 'Keine Beschreibung')}"
        prompt += "\n  Felder:"
        for field_name, field_info in table_info.get("columns", {}).items():
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

def create_function_definitions():
    """Erstellt Funktionsdefinitionen für das OpenAI-API"""
    try:
        # Lade die Abfragemuster
        query_patterns_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "query_patterns.json")
        with open(query_patterns_path, 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
        
        tools = []
        
        for function_name, details in query_patterns.get('common_queries', {}).items():
            # Erstelle die Parameter für die Funktion
            parameters = {
                "type": "object",
                "properties": {},
                "required": details.get('required_parameters', [])
            }
            
            # Füge alle Parameter hinzu
            for param in details.get('required_parameters', []) + details.get('optional_parameters', []):
                param_details = details.get('parameter_descriptions', {}).get(param, {})
                param_type = param_details.get('type', 'string')
                
                param_def = {
                    "type": param_type
                }
                
                # Füge Beschreibung hinzu, wenn vorhanden
                if 'description' in param_details:
                    param_def["description"] = param_details['description']
                
                # Füge Enum-Werte hinzu, wenn vorhanden
                if 'enum' in param_details:
                    param_def["enum"] = param_details['enum']
                
                parameters["properties"][param] = param_def
            
            # Erstelle die Funktionsdefinition
            function_def = {
                "type": "function",
                "function": {
                    "name": function_name,
                    "description": details.get('description', ''),
                    "parameters": parameters
                }
            }
            
            tools.append(function_def)
        
        return tools
    
    except Exception as e:
        logging.error(f"Fehler beim Erstellen der Funktionsdefinitionen: {e}")
        return []

def select_optimal_tool_with_reasoning(user_message, tools, tool_config):
    """Wählt das optimale Tool basierend auf der Nutzernachricht aus"""
    debug_print("Tool Selector", f"Starting tool selection for message: {user_message[:50]}...")
    
    # Check if the bigquery LLM selector should be used
    try:
        selected_tool, params = select_query_with_llm(user_message)
        debug_print("Tool Selector", f"LLM selected tool: {selected_tool}")
        
        # If no tool was selected, apply fallbacks
        if not selected_tool:
            selected_tool = apply_fallback_strategies(user_message, tool_config)
        
        reasoning = "Selected based on LLM analysis"
        return selected_tool, reasoning
        
    except Exception as e:
        debug_print("Tool Selector", f"Error in LLM tool selection: {e}")
        logging.error(f"Error in LLM tool selection: {e}")
        # Fallback to pattern-based approach below
    
    # Pattern-based approach
    best_tool = None
    max_matches = 0
    relevant_patterns = []
    
    for category, category_info in tool_config.get("tool_categories", {}).items():
        patterns = category_info.get("patterns", [])
        
        # Count matches for this category
        match_count = 0
        matched_patterns = []
        
        for pattern in patterns:
            if pattern.lower() in user_message.lower():
                match_count += 1
                matched_patterns.append(pattern)
        
        # If this category has more matches than the current best, update
        if match_count > max_matches:
            max_matches = match_count
            best_tool = category_info.get("default_tool")
            relevant_patterns = matched_patterns
    
    # Check for force_tool_patterns that immediately select a specific tool
    for tool_name, patterns in tool_config.get("force_tool_patterns", {}).items():
        for pattern in patterns:
            if pattern.lower() in user_message.lower():
                best_tool = tool_name
                reasoning = f"Forced selection due to exact match with pattern: '{pattern}'"
                debug_print("Tool Selector", f"Force-selected tool {best_tool}: {reasoning}")
                return best_tool, reasoning
    
    # If no matches or too general, use fallback
    if max_matches == 0 or best_tool is None:
        best_tool = apply_fallback_strategies(user_message, tool_config)
        reasoning = "Fallback selection - no specific patterns matched"
    else:
        reasoning = f"Selected based on {max_matches} pattern matches: {', '.join(relevant_patterns)}"
    
    debug_print("Tool Selector", f"Selected tool {best_tool}: {reasoning}")
    return best_tool, reasoning

def apply_fallback_strategies(user_message, tool_config):
    """Wendet Fallback-Strategien an, wenn keine direkten Pattern-Matches gefunden wurden"""
    # Temporale Muster prüfen (für Datumsabfragen)
    temporal_indicators = ["monat", "jahr", "woche", "letzte", "nächste", "zwischen", "von", "bis", "seit", "zeitraum"]
    if any(indicator in user_message.lower() for indicator in temporal_indicators):
        return "get_care_stays_by_date_range"
    
    # Default Fallback aus der Konfiguration
    return tool_config.get("fallback_tool", "get_active_care_stays_now")

def process_user_query(user_message, session_data):
    """Prozessiert eine Nutzeranfrage mit dem mehrstufigen Ansatz"""
    try:
        # Lade erforderliche Daten
        query_patterns_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "query_patterns.json")
        table_schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "table_schema.json")
        
        with open(query_patterns_path, 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
        
        with open(table_schema_path, 'r', encoding='utf-8') as f:
            table_schema = json.load(f)
        
        # Lade Wissensbasis
        wissensbasis = download_wissensbasis()
        if not wissensbasis:
            return "Die Wissensbasis konnte nicht geladen werden."
        
        # Erstelle System-Prompt
        system_prompt = create_system_prompt(table_schema)
        prompt_wissensbasis_abschnitte = [
            f"Thema: {thema}, Unterthema: {unterthema_full}, Beschreibung: {details.get('beschreibung', '')}, Inhalt: {'. '.join(details.get('inhalt', []))}"
            for thema, unterthemen in wissensbasis.items()
            for unterthema_full, details in unterthemen.items()
        ]
        system_prompt += f"\n\nWissensbasis:\n{chr(10).join(prompt_wissensbasis_abschnitte)}"
        
        # Personalisierung hinzufügen
        user_name = session_data.get("user_name", "")
        seller_id = session_data.get("seller_id")
        
        system_prompt = (
            f"Der Name deines Gesprächspartners lautet {user_name}.\n"
            + system_prompt
            + (f"\n\nDu sprichst mit einem Vertriebspartner mit der ID {seller_id}." if seller_id else "")
        )
        
        # Erstelle Funktionsdefinitionen
        tools = create_function_definitions()
        
        # Wähle das optimale Tool
        tool_config = load_tool_config()
        selected_tool, reasoning = select_optimal_tool_with_reasoning(user_message, tools, tool_config)
        debug_print("Query Processing", f"Selected tool: {selected_tool} - Reason: {reasoning}")
        
        # Extrahiere Datums-Parameter
        date_params = extract_enhanced_date_params(user_message)
        
        # Erstelle die Nachrichten
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        
        # Erstelle Tool-Choice, wenn ein Tool gewählt wurde
        tool_choice = {"type": "function", "function": {"name": selected_tool}} if selected_tool else "auto"
        
        # Erste Antwort vom LLM
        debug_print("API Calls", f"First call with tool_choice: {tool_choice}")
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            tools=tools,
            tool_choice=tool_choice
        )
        
        assistant_message = response.choices[0].message
        
        # Verarbeite die Antwort
        if assistant_message.tool_calls:
            debug_print("API Calls", f"Tool calls detected: {len(assistant_message.tool_calls)}")
            function_responses = []
            
            for tool_call in assistant_message.tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)
                debug_print("Function", f"Name: {function_name}, Args before: {function_args}")
                
                # Standardargumente hinzufügen
                if seller_id:
                    function_args["seller_id"] = seller_id
                
                # Datums-Parameter hinzufügen, wenn nicht bereits gesetzt
                for key, value in date_params.items():
                    if key not in function_args or not function_args[key]:
                        function_args[key] = value
                
                debug_print("Function", f"Args after: {function_args}")
                function_response = handle_function_call(function_name, function_args)
                
                function_responses.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": function_response,
                    }
                )
            
            # Zweiter Aufruf mit den Funktionsergebnissen
            second_messages = messages + [assistant_message.model_dump(exclude_unset=True)] + function_responses
            debug_print("API Calls", f"Second call with {len(function_responses)} function responses")
            second_response = openai.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=second_messages
            )
            final_message = second_response.choices[0].message
            return final_message.content
        else:
            debug_print("API Calls", "No tool calls, using direct response")
            return assistant_message.content
    
    except Exception as e:
        error_message = f"Error processing user query: {str(e)}"
        logging.error(error_message)
        traceback.print_exc()
        return f"Es ist ein Fehler bei der Verarbeitung aufgetreten: {str(e)}"

def stream_response(messages, tools, tool_choice, seller_id, date_params, user_message, session_data):
    """Streaming-Response für die Chat-Antwort"""
    try:
        # Show we're starting the process
        yield 'data: ' + json.dumps({'type': 'status', 'content': 'Starting response generation...'}) + '\n\n'
        
        # First API call to determine the tool to use
        debug_print("Streaming", f"Making first API call with tool_choice: {tool_choice}")
        
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            stream=True
        )
        
        # Storage for the assistant message
        assistant_message_content = ""
        function_calls = []
        current_function_call = None
        
        # Process the streaming response for the first call
        for chunk in response:
            if chunk.choices[0].delta.tool_calls:
                # If we have a tool call
                delta = chunk.choices[0].delta
                tool_call_delta = delta.tool_calls[0]
                
                # If this is the start of a function call
                if tool_call_delta.index == 0 and tool_call_delta.function.name:
                    current_function_call = {
                        "id": "",
                        "name": tool_call_delta.function.name,
                        "arguments": ""
                    }
                    yield 'data: ' + json.dumps({'type': 'tool_start', 'content': f'Using {tool_call_delta.function.name} to answer your question...'}) + '\n\n'
                
                # Append function arguments if present
                if tool_call_delta.function.arguments:
                    if current_function_call:
                        current_function_call["arguments"] += tool_call_delta.function.arguments
                
                # If we have an ID, save it
                if hasattr(tool_call_delta, 'id') and tool_call_delta.id:
                    if current_function_call:
                        current_function_call["id"] = tool_call_delta.id
            
            elif chunk.choices[0].delta.content:
                # If it's regular content
                content_chunk = chunk.choices[0].delta.content
                assistant_message_content += content_chunk
                yield 'data: ' + json.dumps({'type': 'text', 'content': content_chunk}) + '\n\n'
            
            # Check for the end of the message
            if chunk.choices[0].finish_reason == "tool_calls":
                # Complete the function call if not done yet
                if current_function_call:
                    function_calls.append(current_function_call)
                    current_function_call = None
                    
                    # Prepare for executing the function calls
                    for call in function_calls:
                        function_name = call["name"]
                        try:
                            function_args = json.loads(call["arguments"])
                        except json.JSONDecodeError:
                            function_args = {}
                        
                        # Add seller_id and date parameters if applicable
                        if seller_id:
                            function_args["seller_id"] = seller_id
                        
                        # Add date parameters if they exist and aren't already set
                        for param, value in date_params.items():
                            if param not in function_args or not function_args[param]:
                                function_args[param] = value
                        
                        # Show that we're executing the function
                        yield 'data: ' + json.dumps({'type': 'status', 'content': f'Executing {function_name}...'}) + '\n\n'
                        
                        # Execute the function
                        function_response = handle_function_call(function_name, function_args)
                        
                        # Update the stored messages with the function call and response
                        assistant_message = {
                            "role": "assistant",
                            "content": assistant_message_content
                        }
                        if function_calls:
                            assistant_message["tool_calls"] = function_calls
                        
                        # Add the assistant message
                        updated_messages = messages + [assistant_message]
                        
                        # Add the function response
                        updated_messages.append({
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": function_response
                        })
                        
                        # Make a new API call with the function result
                        yield 'data: ' + json.dumps({'type': 'status', 'content': 'Processing results...'}) + '\n\n'
                        
                        second_response = openai.chat.completions.create(
                            model="gpt-3.5-turbo",
                            messages=updated_messages,
                            stream=True
                        )
                        
                        # Collect the final response
                        final_response = ""
                        for chunk in second_response:
                            if chunk.choices[0].delta.content:
                                content_chunk = chunk.choices[0].delta.content
                                final_response += content_chunk
                                yield 'data: ' + json.dumps({'type': 'text', 'content': content_chunk}) + '\n\n'
                        
                        # Store in chat history if requested and we have session data
                        if session_data and "chat_history" in session_data and session_data["chat_history"] is not None:
                            user_id = session_data.get("user_id")
                            if user_id:
                                # Update chat history
                                chat_history = session_data["chat_history"]
                                chat_key = session_data.get("chat_key")
                                
                                if chat_key and final_response:
                                    chat_history.append({"user": user_message, "bot": final_response})
                                    session[chat_key] = chat_history
                                    
                                    # Store chat logs
                                    user_name = session_data.get("user_name")
                                    if user_name:
                                        store_chatlog(user_name, chat_history)
    
    except Exception as e:
        error_message = f"Error in streaming response: {str(e)}"
        logging.error(error_message)
        traceback.print_exc()
        yield 'data: ' + json.dumps({'type': 'error', 'content': error_message}) + '\n\n'

# Authentication routes
@api.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({'success': False, 'message': 'Username is required'}), 400
    
    # Store user in session
    user_id = str(uuid.uuid4())
    session['user_id'] = user_id
    session['user_name'] = username
    
    # Store user in session
    session['user'] = {
        'id': user_id,
        'name': username,
        'role': 'user'
    }
    
    # Start the chat history for this user
    chat_key = f"chat_history_{user_id}"
    if chat_key not in session:
        session[chat_key] = []
    
    return jsonify({
        'success': True,
        'user': session['user'],
        'message': 'Login successful'
    })

@api.route('/auth/google-login')
def google_login():
    """Google OAuth Login Route"""
    # Create URL for Google OAuth page
    redirect_uri = url_for('api.google_callback', _external=True)
    
    google_auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        'client_id': os.getenv('GOOGLE_CLIENT_ID'),
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'email profile',
        'access_type': 'online',
        'state': 'direct_test'
    }
    
    auth_url = f"{google_auth_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
    return redirect(auth_url)

@api.route('/auth/google-callback')
def google_callback():
    """Callback for Google OAuth"""
    code = request.args.get('code')
    
    if not code:
        return jsonify({'success': False, 'message': 'Login failed (no code received)'}), 400
    
    # Exchange code for token
    try:
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'code': code,
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'redirect_uri': url_for('api.google_callback', _external=True),
            'grant_type': 'authorization_code'
        }
        
        token_response = requests.post(token_url, data=token_data)
        
        if not token_response.ok:
            return jsonify({'success': False, 'message': f'Token retrieval failed: {token_response.text}'}), 400
        
        token_info = token_response.json()
        access_token = token_info.get('access_token')
        
        # Get user info
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        
        if not userinfo_response.ok:
            return jsonify({'success': False, 'message': f'User info retrieval failed: {userinfo_response.text}'}), 400
        
        user_info = userinfo_response.json()
        
        # Update session
        email = user_info.get('email')
        name = user_info.get('name')
        
        # Set session variables
        user_id = str(uuid.uuid4())
        session['user_id'] = user_id
            
        session['email'] = email
        session['google_user_email'] = email
        session['user_name'] = name
        session['is_logged_via_google'] = True
        
        # Get seller_id if email is available
        if email:
            seller_id = get_user_id_from_email(email)
            session['seller_id'] = seller_id
        
        # Set user info in session
        session['user'] = {
            'id': user_id,
            'name': name,
            'email': email,
            'role': 'user'
        }
        
        # Start chat history for this user
        chat_key = f"chat_history_{user_id}"
        if chat_key not in session:
            session[chat_key] = []
        
        session.modified = True
        
        # Redirect to frontend after successful login
        frontend_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')
        return redirect(f"{frontend_url}/chat")
    
    except Exception as e:
        logging.error(f"Error in Google login: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Login error: {str(e)}'}), 500

@api.route('/auth/admin-login', methods=['POST'])
def admin_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')
    
    if not email or not password:
        return jsonify({'success': False, 'message': 'Email and password are required'}), 400
    
    # In a real application, you would validate against a database
    # This is a placeholder for demonstration
    if email == 'admin@xora.com' and password == 'admin123':
        user_id = 'admin-1'
        session['user_id'] = user_id
        session['user_name'] = 'Admin User'
        session['email'] = email
        
        # Get seller_id if applicable
        seller_id = get_user_id_from_email(email)
        if seller_id:
            session['seller_id'] = seller_id
        
        session['user'] = {
            'id': user_id,
            'name': 'Admin User',
            'email': email,
            'role': 'admin'
        }
        
        # Start the chat history for this user
        chat_key = f"chat_history_{user_id}"
        if chat_key not in session:
            session[chat_key] = []
        
        return jsonify({
            'success': True,
            'user': session['user'],
            'message': 'Admin login successful'
        })
    
    return jsonify({'success': False, 'message': 'Invalid email or password'}), 401

@api.route('/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    session.pop('user_name', None)
    session.pop('email', None)
    session.pop('seller_id', None)
    session.pop('user', None)
    session.pop('notfall_mode', None)
    
    # Don't clear chat history to preserve it for returning users
    
    return jsonify({
        'success': True,
        'message': 'Logout successful'
    })

@api.route('/auth/status', methods=['GET'])
def auth_status():
    user = session.get('user')
    
    return jsonify({
        'isAuthenticated': bool(user),
        'user': user
    })

# Chat routes
@api.route('/chat/history', methods=['GET'])
def get_chat_history():
    user = session.get('user')
    
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    user_id = user.get('id')
    chat_key = f"chat_history_{user_id}"
    chat_history = session.get(chat_key, [])
    
    # Convert to the format expected by the frontend
    formatted_history = []
    for entry in chat_history:
        user_msg = {
            'id': f"user-{len(formatted_history)}",
            'role': 'user',
            'content': entry.get('user', ''),
            'timestamp': datetime.now().isoformat()
        }
        bot_msg = {
            'id': f"bot-{len(formatted_history)}",
            'role': 'bot',
            'content': entry.get('bot', ''),
            'timestamp': datetime.now().isoformat()
        }
        formatted_history.extend([user_msg, bot_msg])
    
    return jsonify({
        'success': True,
        'history': formatted_history
    })

@api.route('/chat/message', methods=['POST'])
def send_message():
    user = session.get('user')
    
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    data = request.get_json()
    user_message = data.get('message')
    notfall_mode = data.get('notfallmodus') == '1'
    notfall_art = data.get('notfallart', '')
    stream = data.get('stream', False)
    
    if not user_message:
        return jsonify({'success': False, 'message': 'Message is required'}), 400
    
    user_id = user.get('id')
    user_name = user.get('name')
    seller_id = session.get('seller_id')
    
    # Set notfall_mode in session if needed
    if notfall_mode:
        session['notfall_mode'] = True
        user_message = (
            f"ACHTUNG NOTFALL - Thema 9: Notfälle & Vertragsgefährdungen.\n"
            f"Ausgewählte Notfalloption(en): {notfall_art}\n\n"
            + user_message
        )
        log_notfall_event(user_id, notfall_art, user_message)
    else:
        session.pop('notfall_mode', None)
    
    # If streaming is requested, use the streaming endpoint
    if stream and request.headers.get("Accept") == "text/event-stream":
        try:
            # Load schema files
            table_schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "table_schema.json")
            with open(table_schema_path, "r", encoding="utf-8") as f:
                table_schema = json.load(f)
            
            # Load wissensbasis
            wissensbasis = download_wissensbasis()
            if not wissensbasis:
                yield 'data: ' + json.dumps({'type': 'error', 'content': 'Die Wissensbasis konnte nicht geladen werden.'}) + '\n\n'
                return
            
            # Setup system prompt
            system_prompt = create_system_prompt(table_schema)
            prompt_wissensbasis_abschnitte = [
                f"Thema: {thema}, Unterthema: {unterthema_full}, Beschreibung: {details.get('beschreibung', '')}, Inhalt: {'. '.join(details.get('inhalt', []))}"
                for thema, unterthemen in wissensbasis.items()
                for unterthema_full, details in unterthemen.items()
            ]
            system_prompt += f"\n\nWissensbasis:\n{chr(10).join(prompt_wissensbasis_abschnitte)}"
            system_prompt = (
                f"Der Name deines Gesprächspartners lautet {user_name}.\n"
                + system_prompt
                + (f"\n\nDu sprichst mit einem Vertriebspartner mit der ID {seller_id}." if seller_id else "")
            )
            
            # Setup tools and message
            tools = create_function_definitions()
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            
            # Session data for the streaming function
            chat_key = f"chat_history_{user_id}"
            if chat_key not in session:
                session[chat_key] = []
            chat_history = session[chat_key]
            
            session_data = {
                "user_id": user_id,
                "user_name": user_name,
                "seller_id": seller_id,
                "email": session.get("email"),
                "chat_key": chat_key,
                "chat_history": chat_history
            }
            
            # Setup tool selection
            tool_config = load_tool_config()
            selected_tool, reasoning = select_optimal_tool_with_reasoning(user_message, tools, tool_config)
            tool_choice = {"type": "function", "function": {"name": selected_tool}} if selected_tool else "auto"
            
            # Stream the response
            return Response(
                stream_response(
                    messages, 
                    tools, 
                    tool_choice, 
                    seller_id, 
                    extract_enhanced_date_params(user_message), 
                    user_message, 
                    session_data
                ),
                content_type="text/event-stream"
            )
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f"Error in streaming: {str(e)}"
            }), 500
    
    # Non-streaming approach
    try:
        # Set up session data
        chat_key = f"chat_history_{user_id}"
        if chat_key not in session:
            session[chat_key] = []
        chat_history = session[chat_key]
        
        session_data = {
            "user_id": user_id,
            "user_name": user_name,
            "seller_id": seller_id,
            "email": session.get("email"),
            "chat_key": chat_key
        }
        
        # Process the query
        bot_response = process_user_query(user_message, session_data)
        
        # Save the conversation
        chat_history.append({"user": user_message, "bot": bot_response})
        session[chat_key] = chat_history
        store_chatlog(user_name, chat_history)
        
        # Create response objects for the frontend
        message_id = f"{int(time.time())}-{len(chat_history) - 1}"
        
        # These are for the frontend display in the current format
        user_message_obj = {
            'id': f"user-{message_id}",
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now().isoformat()
        }
        
        bot_message_obj = {
            'id': f"bot-{message_id}",
            'role': 'bot',
            'content': bot_response,
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify({
            'success': True,
            'response': bot_response,
            'message_id': f"bot-{message_id}"
        })
    except Exception as e:
        logging.exception("Error in chat message processing")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@api.route('/chat/clear', methods=['POST'])
def clear_chat():
    user = session.get('user')
    
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    user_id = user.get('id')
    chat_key = f"chat_history_{user_id}"
    
    session[chat_key] = []
    
    return jsonify({
        'success': True,
        'message': 'Chat history cleared'
    })

@api.route('/feedback', methods=['POST'])
def store_feedback():
    user = session.get('user')
    
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    data = request.get_json()
    message_id = data.get('message_id')
    feedback_type = data.get('feedback_type')
    comment = data.get('comment', '')
    
    if not message_id or not feedback_type:
        return jsonify({'success': False, 'message': 'Message ID and feedback type are required'}), 400
    
    user_id = user.get('id')
    chat_key = f"chat_history_{user_id}"
    chat_history = session.get(chat_key, [])
    
    # Save the feedback
    store_feedback(feedback_type, comment, chat_history)
    
    # Update the feedback in chat history if possible
    message_idx = int(message_id.split('-')[1]) if '-' in message_id else -1
    if 0 <= message_idx < len(chat_history):
        # We store feedback in a more complex app, here we're just acknowledging it
        pass
    
    return jsonify({
        'success': True,
        'message': 'Feedback submitted successfully'
    })

@api.route('/toggle_notfall', methods=['POST'])
def toggle_notfall():
    user = session.get('user')
    
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    data = request.get_json()
    active = data.get('active', False)
    
    if active:
        session['notfall_mode'] = True
    else:
        session.pop('notfall_mode', None)
    
    return jsonify({
        'success': True,
        'notfall_active': 'notfall_mode' in session
    })

@api.route('/stats', methods=['GET'])
def get_stats():
    user = session.get('user')
    
    if not user:
        return jsonify({'success': False, 'message': 'Authentication required'}), 401
    
    stats = calculate_chat_stats()
    
    return jsonify({
        'success': True,
        'stats': stats
    })
