from utils import debug_print
import json
import logging
import openai
from extract import extract_enhanced_date_params


def load_tool_descriptions():
    """Lädt die Tools-Definitionen aus der query_patterns.json-Datei"""
    try:
        with open('query_patterns.json', 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
        return query_patterns.get('common_queries', {})
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tool-Definitionen: {e}")
        return {}

def create_tool_description_prompt():
    """Erstellt eine benutzerfreundliche Beschreibung aller verfügbaren Tools"""
    tools = load_tool_descriptions()
    
    descriptions = []
    for tool_name, tool_info in tools.items():
        desc = f"TOOL: {tool_name}\n"
        desc += f"BESCHREIBUNG: {tool_info['description']}\n"
        desc += f"PARAMETER: {', '.join(tool_info['required_parameters'])}"
        if tool_info.get('optional_parameters'):
            desc += f" (optional: {', '.join(tool_info['optional_parameters'])})"
        desc += "\n"
        
        # Füge Beispielanwendungsfälle hinzu, falls vorhanden
        if 'active_care_stays_now' in tool_name:
            desc += "ANWENDUNGSFÄLLE: Aktuelle Kunden, laufende Betreuungen, momentane Situation\n"
        elif 'contract_terminations' in tool_name:
            desc += "ANWENDUNGSFÄLLE: Kündigungen, beendete Verträge, verlorene Kunden\n"
        elif 'customers_on_pause' in tool_name:
            desc += "ANWENDUNGSFÄLLE: Kunden in Pause, Verträge ohne aktive Betreuung\n"
        elif 'care_stays_by_date_range' in tool_name:
            desc += "ANWENDUNGSFÄLLE: Betreuungen in bestimmten Monaten/Jahren, zeitraumbezogene Analysen\n"
        
        descriptions.append(desc)
    
    return "\n".join(descriptions)

def select_tool(user_message):
    """Wählt das passende Tool für die Benutzeranfrage mithilfe des LLM aus"""
    tool_descriptions = create_tool_description_prompt()
    
    # Erstellen eines präzisen Prompts für das LLM
    prompt = f"""
        Du bist ein Experte für die Analyse von Benutzeranfragen in einem CRM-System für Pflegevermittlung. 
        Wähle das optimale Tool basierend auf der folgenden Anfrage.

        BENUTZERANFRAGE: "{user_message}"

        VERFÜGBARE TOOLS:
        {tool_descriptions}

        WICHTIG:
        - Wähle genau EIN Tool aus
        - Extrahiere alle notwendigen Parameter aus der Anfrage
        - Bei zeitbezogenen Anfragen, nutze immer das Tool für Datumsintervalle (get_care_stays_by_date_range)
        - Bei Fragen zu aktuellen Kunden nutze immer get_active_care_stays_now
        - Bei Kündigungen und Vertragsfragen nutze immer get_contract_terminations

        ANTWORTFORMAT:
        {
        "tool": "name_des_tools",
        "reasoning": "Begründung für die Auswahl",
        "parameters": {
            "param1": "Wert1",
            "param2": "Wert2"
        }
        }
        """
    
    try:
        # LLM-Anfrage
        response = openai.chat.completions.create(
            model="o3-mini", # oder o3-mini, je nach Verfügbarkeit
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        
        # Antwort parsen
        response_text = response.choices[0].message.content
        result = json.loads(response_text)
        
        # Debugging-Informationen
        logging.debug(f"LLM hat Tool '{result['tool']}' ausgewählt. Begründung: {result['reasoning']}")
        
        return result
    except Exception as e:
        logging.error(f"Fehler bei der LLM-Tool-Auswahl: {e}")
        # Fallback auf ein Standard-Tool
        return {
            "tool": "get_active_care_stays_now",
            "reasoning": "Fallback aufgrund eines Fehlers",
            "parameters": {}
        }

def select_optimal_tool_with_reasoning(user_message, tools, tool_config):
    """
    Wählt das optimale Tool anhand des semantischen Verständnisses der Anfrage.
    Nutzt entweder die LLM-basierte Methode oder Pattern-Matching je nach Konfiguration.
    """
    # Prüfen, ob wir die LLM-basierte Methode verwenden sollen
    if 'USE_LLM_QUERY_SELECTOR' in globals() and USE_LLM_QUERY_SELECTOR:
        debug_print("Tool-Auswahl", "Verwende LLM-basierte Abfrage-Auswahl")
        try:
            # Extrahiere die verfügbaren Tool-Namen
            available_tool_names = [tool["function"]["name"] for tool in tools]
            
            # Human-in-the-loop Behandlung
            if "human_in_loop_clarification_response" in session:
                # Verarbeite Antwort auf eine vorherige Rückfrage
                debug_print("Tool-Auswahl", "Verarbeite Human-in-the-loop Rückmeldung")
                clarification_option = session.pop("human_in_loop_clarification_response")
                original_request = session.pop("human_in_loop_original_request", user_message)
                
                # Verarbeite die Benutzerantwort zur Rückfrage
                query_name, parameters = process_clarification_response(
                    clarification_option, original_request
                )
            else:
                # Normale Verarbeitung ohne vorherige Rückfrage
                # Nutze die select_query_with_llm Methode zur semantischen Auswahl
                query_name, parameters, human_in_loop = select_query_with_llm(
                    user_message, 
                    conversation_history=None,  # TODO: Könnte session.get('chat_history') sein
                    user_id=None  # Wird später im Code mit seller_id ergänzt
                )
                
                # Prüfen, ob eine menschliche Interaktion erforderlich ist
                if human_in_loop:
                    debug_print("Tool-Auswahl", f"Human-in-the-loop für Query: {query_name}")
                    logging.info(f"Human-in-the-loop aktiviert für Query: {query_name}, Parameter: {parameters}")
                    
                    # Tiefere Debug-Informationen protokollieren
                    if isinstance(human_in_loop, dict):
                        logging.debug(f"Human-in-loop Daten: {json.dumps(human_in_loop)}")
                    else:
                        logging.warning(f"Human-in-loop hat unerwartetes Format: {type(human_in_loop)}")
                        
                    # Wir speichern den human_in_loop-Status in der Session
                    session["human_in_loop_data"] = human_in_loop
                    session["human_in_loop_original_request"] = user_message
                    session.modified = True
                    
                    # Sicherstellen, dass wir eine gültige Nachricht haben
                    message = "Weitere Details benötigt"
                    try:
                        if human_in_loop and isinstance(human_in_loop, dict):
                            message = human_in_loop.get('message', message)
                            
                            # Prüfen auf Optionen
                            options = human_in_loop.get('options', [])
                            if options:
                                logging.info(f"Human-in-loop enthält {len(options)} Optionen")
                                for i, option in enumerate(options):
                                    logging.debug(f"Option {i}: {option.get('text')} -> {option.get('query')}")
                    except Exception as e:
                        logging.error(f"Fehler beim Zugriff auf human_in_loop Daten: {e}")
                    
                    # Hier geben wir ein spezielles Tool zurück, das die UI anweist, eine Rückfrage zu stellen
                    return "human_in_loop_clarification", f"Rückfrage erforderlich: {message}"
                
                # Normale Verarbeitung, wenn keine human-in-loop Clarification benötigt wird
            
            # Prüfe, ob das gewählte Tool verfügbar ist
            if query_name in available_tool_names:
                debug_print("Tool-Auswahl", f"LLM hat Tool gewählt: {query_name}")
                return query_name, f"LLM-basierte Auswahl: {query_name}"
            else:
                debug_print("Tool-Auswahl", f"LLM-gewähltes Tool {query_name} ist nicht verfügbar")
        except Exception as e:
            debug_print("Tool-Auswahl", f"Fehler bei LLM-Auswahl: {e}")
            logging.exception("Fehler bei LLM-Auswahl des Tools")
            # Falls ein Fehler auftritt, fallen wir zurück auf Pattern-Matching
    
    # Falls LLM-Auswahl nicht aktiviert oder fehlgeschlagen ist:
    # Fallback auf traditionelles Pattern-Matching oder Chain-of-Thought LLM
    user_message_lower = user_message.lower()
    
    # SCHICHT 1 & 2 entfernt - Überlassen wir dem LLM die Entscheidung
    # Keine hardcodierten Regeln oder Muster mehr
    
    # SCHICHT 3: LLM-basierte Entscheidung mit Chain-of-Thought
    system_prompt = """
    Du bist ein Experte für die Auswahl des optimalen Tools basierend auf Benutzeranfragen.
    Deine Aufgabe ist es, das am besten geeignete Tool für die gegebene Anfrage auszuwählen.
    
    Führe eine Chain-of-Thought durch:
    1. Analysiere die Art der Anfrage (Was wird gefragt? Wozu?)
    2. Identifiziere Schlüsselwörter und Absichten (Zeitraum, Benutzer, Statistiken?)
    3. Wähle das am besten geeignete Tool aus den verfügbaren Optionen
    
    Antworte in diesem Format:
    ANALYSE: [Deine Analyse der Anfrage]
    SCHLÜSSELWÖRTER: [Erkannte Schlüsselwörter]
    TOOL: [Name des gewählten Tools]
    """
    
    # Erstelle Tool-Übersichtsbeschreibungen für den Prompt
    tool_descriptions = ""
    for tool in tools:
        tool_name = tool["function"]["name"]
        tool_desc = tool["function"]["description"]
        required_params = tool["function"]["parameters"].get("required", [])
        tool_descriptions += f"- {tool_name}: {tool_desc}\n  Benötigte Parameter: {', '.join(required_params)}\n"
    
    # LLM-Aufruf für Tool-Auswahl
    messages = [
        {"role": "developer", "content": system_prompt + "\n\nVerfügbare Tools:\n" + tool_descriptions},
        {"role": "user", "content": f"Benutzeranfrage: '{user_message}'\nWelches Tool passt am besten?"}
    ]
    
    try:
        debug_print("Tool-Auswahl", "Starte LLM-Aufruf zur Tool-Bestimmung")
        response = openai.chat.completions.create(
            model="o3-mini",
            messages=messages,
            max_tokens=250
        )
        
        response_text = response.choices[0].message.content.strip()
        debug_print("Tool-Auswahl", f"LLM Tool-Auswahl: {response_text}")
        
        # Parse das strukturierte Antwortformat
        tool_match = re.search(r'TOOL:\s*(\w+)', response_text)
        if tool_match:
            tool_choice = tool_match.group(1)
            
            # Überprüfe, ob das Tool existiert
            for tool in tools:
                if tool["function"]["name"] == tool_choice:
                    return tool_choice, response_text
        
        # Extrahiere Reasoning, auch wenn Tool nicht gefunden wurde
        analysis = re.search(r'ANALYSE:\s*(.+?)(?=SCHLÜSSELWÖRTER:|$)', response_text, re.DOTALL)
        reasoning = analysis.group(1).strip() if analysis else response_text
    except Exception as e:
        debug_print("Tool-Auswahl", f"Fehler bei LLM Tool-Auswahl: {e}")
        reasoning = f"LLM-Fehler: {str(e)}"
    
    # SCHICHT 4: Fallback-Mechanismus
    # Bei unsicheren/nicht erkannten Anfragen, verwende das Fallback-Tool
    fallback_tool = tool_config.get("fallback_tool", "get_care_stays_by_date_range")
    
    # Prüfe auf Datumserwähnungen als zusätzliche Heuristik für Fallback
    date_params = extract_enhanced_date_params(user_message)
    if date_params and "start_date" in date_params and "end_date" in date_params:
        debug_print("Tool-Auswahl", f"Fallback aufgrund erkannter Datumsinformationen")
        return "get_care_stays_by_date_range", f"Fallback aufgrund erkannter Datumsinformationen: {date_params}"
    
    debug_print("Tool-Auswahl", f"Fallback zur Standardabfrage: {fallback_tool}")
    return fallback_tool, f"Fallback zur Standardabfrage. Reasoning: {reasoning}"

def load_tool_config():
    """Liefert die Standard-Tool-Konfiguration"""
    # Direkte Rückgabe der Standardkonfiguration ohne Datei-Zugriff
    return {
        "description": "Tool-Konfiguration für LLM-basierte Entscheidungen",
        "fallback_tool": "get_care_stays_by_date_range",
        "use_llm_selection": True
    }
