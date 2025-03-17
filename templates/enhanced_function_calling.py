import json
import logging
import re
import os
import dateparser
from datetime import datetime, timedelta
import yaml
from typing import Dict, List, Any, Optional, Tuple

# Pfad zur Konfigurationsdatei
TOOL_CONFIG_PATH = "tool_config.yaml"

def load_tool_config():
    """Lädt die Tool-Konfiguration aus einer YAML-Datei"""
    try:
        if not os.path.exists(TOOL_CONFIG_PATH):
            create_default_tool_config()
            
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tool-Konfiguration: {e}")
        # Fallback-Konfiguration
        return {
            "tool_categories": {
                "time_query": {
                    "patterns": ["care stays", "carestays", "einsätze", "monat", "monatlich", "jahr", "jährlich", 
                               "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", 
                               "september", "oktober", "november", "dezember"],
                    "default_tool": "get_care_stays_by_date_range"
                },
                "contract_query": {
                    "patterns": ["vertrag", "verträge", "contract", "contracts"],
                    "default_tool": "get_active_contracts"
                },
                "lead_query": {
                    "patterns": ["lead", "leads", "kunde", "kunden"],
                    "default_tool": "get_recent_leads"
                },
                "statistics_query": {
                    "patterns": ["statistik", "statistics", "performance", "umsatz", "revenue"],
                    "default_tool": "get_user_statistics"
                }
            },
            "fallback_tool": "get_care_stays_by_date_range",
            "force_tool_patterns": {
                "get_care_stays_by_date_range": ["im monat", "im jahr", "in 2025", "im mai", "im april", "im märz"]
            }
        }

def process_user_query(user_message, session_data, tools, openai_client, handle_function_call_fn):
    """
    Verbesserter mehrstufiger Prozess zur intelligenten Verarbeitung von Benutzeranfragen
    
    Args:
        user_message: Die Anfrage des Benutzers
        session_data: Session-Daten (user_id, user_name, seller_id, etc.)
        tools: Liste der verfügbaren Tools/Funktionen
        openai_client: OpenAI Client-Instanz
        handle_function_call_fn: Funktion zum Ausführen von Function Calls
        
    Returns:
        str: Die generierte Antwort
    """
    # Lade Konfiguration
    tool_config = load_tool_config()
    
    # Debug-Logging
    logging.info(f"Verarbeite Anfrage: '{user_message}'")
    
    # SCHRITT 1+2: Kategorie erkennen und Tool auswählen
    selected_tool, reasoning = select_optimal_tool_with_reasoning(
        user_message, tools, tool_config, openai_client
    )
    logging.info(f"Ausgewähltes Tool: {selected_tool}, Begründung: {reasoning}")
    
    # SCHRITT 3: Parameter extrahieren (Hybrid-Ansatz)
    extracted_params = extract_parameters_hybrid(
        user_message, selected_tool, session_data, tools, openai_client
    )
    logging.info(f"Extrahierte Parameter: {extracted_params}")
    
    # SCHRITT 4: Tool ausführen
    try:
        tool_result = execute_tool(selected_tool, extracted_params, handle_function_call_fn)
        logging.info(f"Tool-Ausführung erfolgreich")
        
        # Analysiere das Ergebnis für bessere Protokollierung
        try:
            result_data = json.loads(tool_result)
            result_status = result_data.get("status", "unbekannt")
            result_count = len(result_data.get("data", [])) if "data" in result_data else "keine Daten"
            logging.info(f"Tool-Ergebnis: Status={result_status}, Datensätze={result_count}")
        except:
            logging.info("Konnte Tool-Ergebnis nicht parsen")
    except Exception as e:
        logging.error(f"Fehler bei der Tool-Ausführung: {e}")
        return f"Bei der Verarbeitung Ihrer Anfrage ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut oder formulieren Sie Ihre Anfrage anders."
    
    # SCHRITT 5: Antwort generieren
    try:
        final_response = generate_response_with_tool_result(
            user_message, selected_tool, tool_result, reasoning, openai_client
        )
        logging.info(f"Antwort generiert (gekürzt): {final_response[:100]}...")
        return final_response
    except Exception as e:
        logging.error(f"Fehler bei der Antwortgenerierung: {e}")
        # Fallback: Generiere einfache Antwort direkt aus dem Tool-Ergebnis
        try:
            result_data = json.loads(tool_result)
            if "data" in result_data and len(result_data["data"]) > 0:
                return f"Ich habe {len(result_data['data'])} Datensätze gefunden. Hier sind die Informationen: {json.dumps(result_data['data'][:5], indent=2)}"
            else:
                return "Leider wurden keine Daten zu Ihrer Anfrage gefunden."
        except:
            return "Es konnten keine passenden Daten gefunden werden. Bitte versuchen Sie es mit einer anderen Anfrage."


def select_optimal_tool_with_reasoning(user_message, tools, tool_config, openai_client):
    """
    Wählt das optimale Tool anhand eines mehrschichtigen Ansatzes
    """
    user_message_lower = user_message.lower()
    
    # SCHICHT 1: Direkte Muster-Erkennung für häufige Anfragen
    # Prüfe auf explizite Muster, die bestimmte Tools erzwingen
    for tool_name, patterns in tool_config.get("force_tool_patterns", {}).items():
        for pattern in patterns:
            if pattern.lower() in user_message_lower:
                return tool_name, f"Regelbasierte Auswahl: Erkanntes Muster '{pattern}'"
    
    # SCHICHT 2: Kategorie-Erkennung
    detected_categories = []
    for category, config in tool_config.get("tool_categories", {}).items():
        for pattern in config.get("patterns", []):
            if pattern.lower() in user_message_lower:
                detected_categories.append(category)
                break
    
    # Wenn Kategorien erkannt wurden, beschränke Tool-Auswahl
    if detected_categories:
        category_tools = []
        for category in detected_categories:
            default_tool = tool_config["tool_categories"][category].get("default_tool")
            if default_tool:
                category_tools.append(default_tool)
        
        if len(category_tools) == 1:
            return category_tools[0], f"Kategorie-basierte Auswahl: Erkannte Kategorie(n) {', '.join(detected_categories)}"
    
    # SCHICHT 3: LLM-basierte Entscheidung mit Chain-of-Thought
    system_prompt = """
    Du bist ein Experte für die Auswahl des optimalen Tools basierend auf Benutzeranfragen.
    Deine Aufgabe ist es, das am besten geeignete Tool für die Anfrage auszuwählen.
    
    WICHTIGE REGELN:
    - Bei ALLEN Fragen zu Daten (Care Stays, Verträge, Leads, etc.) MUSS ein passendes Tool gewählt werden
    - Bei Fragen zu bestimmten Zeiträumen (Monaten, Jahren) wähle immer get_care_stays_by_date_range
    - Bei unklaren Anfragen zu Care Stays wähle immer get_care_stays_by_date_range
    - Gehe bei Datenbankabfragen immer auf Nummer sicher und wähle ein Tool
    
    Führe eine Chain-of-Thought durch:
    1. Analysiere die Art der Anfrage (Was wird gefragt? Wozu?)
    2. Identifiziere Schlüsselwörter und Absichten (Zeitraum, Benutzer, Statistiken?)
    3. Wähle das am besten geeignete Tool
    
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
        {"role": "system", "content": system_prompt + "\n\nVerfügbare Tools:\n" + tool_descriptions},
        {"role": "user", "content": f"Benutzeranfrage: '{user_message}'\nWelches Tool passt am besten?"}
    ]
    
    try:
        response = openai_client.chat.completions.create(
            model="o3-mini",
            messages=messages,
            max_tokens=250  # Mehr Tokens für Chain-of-Thought
        )
        
        response_text = response.choices[0].message.content.strip()
        logging.info(f"LLM Tool-Auswahl: {response_text}")
        
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
        logging.error(f"Fehler bei LLM Tool-Auswahl: {e}")
        reasoning = f"LLM-Fehler: {str(e)}"
    
    # SCHICHT 4: Fallback-Mechanismus
    # Bei unsicheren/nicht erkannten Anfragen, verwende das Fallback-Tool
    fallback_tool = tool_config.get("fallback_tool", "get_care_stays_by_date_range")
    
    # Prüfe auf Datumserwähnungen als zusätzliche Heuristik für Fallback
    date_params = extract_enhanced_date_params(user_message)
    if date_params and "start_date" in date_params and "end_date" in date_params:
        return "get_care_stays_by_date_range", f"Fallback aufgrund erkannter Datumsinformationen: {date_params}"
    
    return fallback_tool, f"Fallback zur Standardabfrage. Reasoning: {reasoning}"


def extract_enhanced_date_params(user_message):
    """
    Erweiterte Version von extract_date_params mit mehr Robustheit
    """
    extracted_args = {}
    
    # Deutsche und englische Monatsnamen
    month_map = {
        # Deutsche Monatsnamen (mit Variationen)
        "januar": 1, "jan": 1, "jänner": 1,
        "februar": 2, "feb": 2, 
        "märz": 3, "mar": 3, "maerz": 3,
        "april": 4, "apr": 4,
        "mai": 5,
        "juni": 6, "jun": 6,
        "juli": 7, "jul": 7,
        "august": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "oktober": 10, "okt": 10, "oct": 10,
        "november": 11, "nov": 11,
        "dezember": 12, "dez": 12, "dec": 12,
        
        # Englische Monatsnamen
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    
    user_message_lower = user_message.lower()
    current_date = datetime.now()
    current_year = current_date.year
    
    # 1. Erkennung von expliziten Jahren (z.B. "2025")
    year_match = re.search(r'\b(20\d\d)\b', user_message)
    extracted_year = int(year_match.group(1)) if year_match else current_year
    
    # 2. Prüfe auf Monatsnamen
    for month_name, month_num in month_map.items():
        # Suche nach "im [Monat]" oder "[Monat] 2023" Patterns mit Wortgrenzen
        month_patterns = [
            fr'\b{month_name}\b',  # Nur den Monatsnamen
            fr'im\s+{month_name}\b',  # "im [Monat]"
            fr'{month_name}\s+{extracted_year}\b',  # "[Monat] 2025"
        ]
        
        if any(re.search(pattern, user_message_lower) for pattern in month_patterns):
            # Bestimme Jahr basierend auf Kontext
            year = extracted_year
            
            # Erstelle Start- und Enddaten für den Monat
            try:
                start_date = datetime(year, month_num, 1)
                
                # Bestimme den letzten Tag des Monats
                if month_num == 12:
                    end_date = datetime(year, 12, 31)
                else:
                    next_month_date = datetime(year, month_num + 1, 1)
                    end_date = next_month_date - timedelta(days=1)
                
                extracted_args["start_date"] = start_date.strftime("%Y-%m-%d")
                extracted_args["end_date"] = end_date.strftime("%Y-%m-%d")
                logging.info(f"Extrahierter Monat: {month_name}, Jahr: {year}, Start: {extracted_args['start_date']}, Ende: {extracted_args['end_date']}")
                return extracted_args
            except ValueError as e:
                logging.error(f"Fehler bei der Datumskonvertierung: {e}")
                continue
    
    # 3. Dateparser als Fallback für komplexere Datumsausdrücke
    try:
        parsed_date = dateparser.parse(
            user_message,
            languages=["de", "en"],
            settings={"PREFER_DATES_FROM": "future"}
        )
        
        if parsed_date:
            # Speichere Jahr-Monat Format
            extracted_args["year_month"] = parsed_date.strftime("%Y-%m")
            
            # Erstelle Start- und Enddaten für den gefundenen Monat
            year = parsed_date.year
            month = parsed_date.month
            
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year, 12, 31)
            else:
                next_month_date = datetime(year, month + 1, 1)
                end_date = next_month_date - timedelta(days=1)
            
            extracted_args["start_date"] = start_date.strftime("%Y-%m-%d")
            extracted_args["end_date"] = end_date.strftime("%Y-%m-%d")
            logging.info(f"Erkanntes Datum via dateparser: {extracted_args}")
    except Exception as e:
        logging.error(f"Fehler bei dateparser: {e}")
    
    # 4. Standardwerte für den aktuellen Monat als letzte Fallback-Option
    if not extracted_args and ("monat" in user_message_lower or "month" in user_message_lower):
        current_month = current_date.month
        start_date = datetime(current_year, current_month, 1)
        
        if current_month == 12:
            end_date = datetime(current_year, 12, 31)
        else:
            next_month_date = datetime(current_year, current_month + 1, 1)
            end_date = next_month_date - timedelta(days=1)
        
        extracted_args["start_date"] = start_date.strftime("%Y-%m-%d")
        extracted_args["end_date"] = end_date.strftime("%Y-%m-%d")
        logging.info(f"Fallback auf aktuellen Monat: {extracted_args}")
    
    return extracted_args


def extract_parameters_hybrid(user_message, selected_tool, session_data, tools, openai_client):
    """
    Hybrider Ansatz zur Parameterextraktion
    """
    # 1. Initialisiere Parameter mit bekannten Werten aus der Session
    params = {}
    if "seller_id" in session_data and session_data["seller_id"]:
        params["seller_id"] = session_data["seller_id"]
    
    # 2. Tool-Definition finden
    tool_info = None
    for tool in tools:
        if tool["function"]["name"] == selected_tool:
            tool_info = tool["function"]
            break
    
    if not tool_info:
        logging.error(f"Tool-Definition für '{selected_tool}' nicht gefunden")
        return params
    
    # Erforderliche Parameter identifizieren
    required_params = tool_info["parameters"].get("required", [])
    all_params = list(tool_info["parameters"]["properties"].keys())
    
    # 3. Algorithmus-basierte Extraktion von Datumsinformationen
    if any(param.endswith("_date") for param in all_params):
        date_params = extract_enhanced_date_params(user_message)
        params.update(date_params)
    
    # 4. Extraktion von ID-basierten Parametern mit Regex
    id_params = extract_ids_with_regex(user_message)
    params.update(id_params)
    
    # 5. LLM-basierte Extraktion für verbleibende Parameter
    # Überprüfen, ob wir alle erforderlichen Parameter haben
    missing_required = [p for p in required_params if p not in params]
    
    if missing_required:
        # Versuche, fehlende Parameter mit LLM zu extrahieren
        llm_params = extract_params_with_llm(user_message, selected_tool, missing_required, tool_info, openai_client)
        params.update(llm_params)
    
    # 6. Standardwerte für optionale Parameter
    query_patterns = load_query_patterns()
    if selected_tool in query_patterns.get("common_queries", {}):
        defaults = query_patterns["common_queries"][selected_tool].get("default_values", {})
        for param, value in defaults.items():
            if param not in params:
                params[param] = value
    
    # 7. Typ-Konvertierung (Integer-Parameter)
    convert_parameter_types(params, tool_info)
    
    # 8. Validierung: Überprüfe, ob alle erforderlichen Parameter vorhanden sind
    still_missing = [p for p in required_params if p not in params]
    if still_missing:
        logging.warning(f"Nach allen Extraktionsversuchen fehlen immer noch Parameter: {still_missing}")
    
    return params


def extract_ids_with_regex(user_message):
    """Extrahiert IDs mit Regex-Mustern"""
    extracted = {}
    
    # MongoDB ObjectId Format (24 Hex-Zeichen)
    mongo_id_match = re.search(r'\b([0-9a-f]{24})\b', user_message, re.IGNORECASE)
    if mongo_id_match:
        # Entscheide, welcher Parameter basierend auf Kontext
        if "verkäufer" in user_message.lower() or "seller" in user_message.lower():
            extracted["seller_id"] = mongo_id_match.group(1)
        elif "lead" in user_message.lower() or "kunde" in user_message.lower():
            extracted["lead_id"] = mongo_id_match.group(1)
        elif "agentur" in user_message.lower() or "agency" in user_message.lower():
            extracted["agency_id"] = mongo_id_match.group(1)
    
    return extracted


def extract_params_with_llm(user_message, tool_name, missing_params, tool_info, openai_client):
    """
    Extrahiert Parameter mittels LLM für komplexere Fälle
    """
    system_prompt = f"""
    Du bist ein Spezialist für die Extraktion von Parametern aus Benutzeranfragen.
    Deine Aufgabe ist es, die folgenden Parameter für das Tool '{tool_name}' zu extrahieren:
    {', '.join(missing_params)}
    
    Antworte NUR im JSON-Format: {{"param1": "wert1", "param2": "wert2", ...}}
    
    Parameterinformationen:
    """
    
    # Füge Parameterbeschreibungen hinzu
    for param in missing_params:
        if param in tool_info["parameters"]["properties"]:
            param_info = tool_info["parameters"]["properties"][param]
            param_type = param_info.get("type", "string")
            param_desc = param_info.get("description", "Keine Beschreibung")
            system_prompt += f"- {param} (Typ: {param_type}): {param_desc}\n"
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Benutzeranfrage: '{user_message}'\nExtrahiere NUR die benötigten Parameter."}
    ]
    
    try:
        response = openai_client.chat.completions.create(
            model="o3-mini",
            messages=messages,
            max_tokens=150
        )
        
        response_text = response.choices[0].message.content.strip()
        
        # Versuche, JSON aus der Antwort zu extrahieren
        try:
            # Sucht nach JSON-Objekten in der Antwort, auch wenn Text drumherum ist
            json_match = re.search(r'({[^{}]*})', response_text)
            if json_match:
                extracted_params = json.loads(json_match.group(1))
                return extracted_params
        except json.JSONDecodeError:
            logging.warning(f"Konnte JSON nicht aus LLM-Antwort parsen: {response_text}")
        
        # Fallback: Manuelles Parsing wenn JSON-Parse fehlschlägt
        extracted_params = {}
        for param in missing_params:
            param_match = re.search(rf'"{param}":\s*"?([^",}]*)"?', response_text)
            if param_match:
                extracted_params[param] = param_match.group(1).strip()
        
        return extracted_params
    except Exception as e:
        logging.error(f"Fehler bei LLM-Parameterextraktion: {e}")
        return {}


def convert_parameter_types(params, tool_info):
    """Konvertiert Parameter in die richtigen Typen basierend auf der Tool-Definition"""
    if not tool_info or "parameters" not in tool_info or "properties" not in tool_info["parameters"]:
        return
    
    for param, value in list(params.items()):
        if param in tool_info["parameters"]["properties"]:
            param_info = tool_info["parameters"]["properties"][param]
            param_type = param_info.get("type", "string")
            
            # Konvertiere nur, wenn der Wert noch nicht den richtigen Typ hat
            if param_type == "integer" and not isinstance(value, int):
                try:
                    params[param] = int(value)
                except (ValueError, TypeError):
                    logging.warning(f"Konnte Parameter '{param}' nicht zu Integer konvertieren: {value}")
            elif param_type == "boolean" and not isinstance(value, bool):
                if isinstance(value, str):
                    params[param] = value.lower() in ("true", "yes", "1", "wahr", "ja")


def execute_tool(tool_name, params, handle_function_call_fn):
    """
    Führt das Tool mit den extrahierten Parametern aus
    Mit zusätzlichem Logging für besseres Debugging
    """
    logging.info(f"Führe Tool aus: {tool_name} mit Parametern: {params}")
    
    try:
        # Standardwerte für optionale Parameter
        if "limit" not in params:
            params["limit"] = 500
        
        result = handle_function_call_fn(tool_name, params)
        
        # Versuche das Ergebnis zu parsen, um bessere Logs zu generieren
        try:
            parsed_result = json.loads(result)
            if "status" in parsed_result:
                logging.info(f"Tool-Ausführungsstatus: {parsed_result['status']}")
            if "data" in parsed_result:
                data_count = len(parsed_result["data"])
                logging.info(f"Anzahl der Ergebnisse: {data_count}")
                if data_count == 0:
                    logging.warning("Keine Daten in der Ergebnismenge!")
        except:
            logging.info("Konnte Tool-Ergebnis nicht parsen")
        
        return result
    except Exception as e:
        error_msg = f"Fehler bei der Ausführung von {tool_name}: {str(e)}"
        logging.error(error_msg)
        return json.dumps({"status": "error", "message": error_msg, "data": []})


def generate_response_with_tool_result(user_message, tool_name, tool_result, reasoning, openai_client):
    """
    Generiert eine benutzerfreundliche, informative Antwort basierend auf den Tool-Ergebnissen
    Mit Chain-of-Thought für bessere Qualität
    """
    system_prompt = """
    Du bist ein hilfreicher Assistent, der Datenbankanfragen präzise und direkt beantwortet.
    Dir wird ein Funktionsergebnis bereitgestellt. Nutze es, um eine benutzerfreundliche, 
    informative Antwort zu erstellen.
    
    WICHTIGE REGELN:
    1. Antworte IMMER direkt und ohne Einleitungen wie "Basierend auf den Daten..." oder "Ich habe die Daten abgerufen..."
    2. Beginne deine Antwort mit einer klaren Zusammenfassung der wichtigsten Daten
    3. Strukturiere komplexe Informationen mit Aufzählungspunkten für bessere Lesbarkeit
    4. Führe einen Chain-of-Thought durch, um die wichtigsten Erkenntnisse zu extrahieren:
       - Was sind die Kernfakten in den Daten?
       - Wie sind diese für den Benutzer relevant?
       - Gibt es auffällige Muster oder Zusammenhänge?
    5. Wenn keine Daten gefunden wurden, sage das klar und prägnant
    6. Verwende korrektes Deutsch mit professionellem Vokabular
    
    ANTWORTSTRUKTUR:
    1. Kurze Hauptaussage (1 Satz)
    2. Detaillierte Ausführung (ggf. mit Aufzählungspunkten)
    3. Falls relevant: Vorschlag für weitere Analysen oder verwandte Informationen
    
    WICHTIG: Die Antwort sollte direkt, präzise und hilfreich sein, ohne zu viel Fülltext.
    """
    
    try:
        # Parse das Tool-Ergebnis
        result_data = json.loads(tool_result)
        
        # Chain-of-Thought Struktur
        cot_prompt = f"""
        Bevor du antwortest, analysiere die Daten:
        1. Tool-Begründung: {reasoning}
        2. Anzahl der Datensätze: {len(result_data.get('data', []))}
        3. Datentyp: {tool_name}
        
        Denke in logischen Schritten:
        - Was ist die Kernfrage des Benutzers?
        - Welche Daten sind am relevantesten für diese Frage?
        - Wie kann ich diese Daten am klarsten präsentieren?
        
        WICHTIG: Deine finale Antwort darf KEINE Erwähnung dieser Analyseschritte enthalten!
        """
        
        messages = [
            {"role": "system", "content": system_prompt + cot_prompt},
            {"role": "user", "content": user_message},
            {"role": "function", "name": tool_name, "content": tool_result}
        ]
        
        response = openai_client.chat.completions.create(
            model="o3-mini",
            messages=messages,
            temperature=0.3,  # Niedrigere Temperatur für präzisere Antworten
            max_tokens=500
        )
        
        return response.choices[0].message.content
    except json.JSONDecodeError:
        logging.error(f"Konnte Tool-Ergebnis nicht parsen: {tool_result}")
        return "Bei der Verarbeitung der Daten ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut."
    except Exception as e:
        logging.error(f"Fehler bei der Antwortgenerierung: {e}")
        # Fallback: Einfache Antwort
        try:
            result_data = json.loads(tool_result)
            status = result_data.get("status", "unknown")
            if status == "success" and "data" in result_data and len(result_data["data"]) > 0:
                data_count = len(result_data["data"])
                return f"Es wurden {data_count} Datensätze gefunden. Hier sind die wichtigsten Informationen: {json.dumps(result_data['data'][:3], indent=2, ensure_ascii=False)}"
            else:
                return "Leider wurden keine passenden Daten zu Ihrer Anfrage gefunden."
        except:
            return "Es ist ein technisches Problem aufgetreten. Bitte versuchen Sie es später erneut."


def load_query_patterns():
    """Lädt die Query-Patterns aus der JSON-Datei"""
    try:
        with open("query_patterns.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Fehler beim Laden der Query-Patterns: {e}")
        return {"common_queries": {}}


def create_default_tool_config():
    """Erstellt eine Standard-Tool-Konfigurationsdatei"""
    default_config = {
        "tool_categories": {
            "time_query": {
                "patterns": ["care stays", "carestays", "einsätze", "monat", "monatlich", "jahr", "jährlich", 
                           "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", 
                           "september", "oktober", "november", "dezember"],
                "default_tool": "get_care_stays_by_date_range"
            },
            "contract_query": {
                "patterns": ["vertrag", "verträge", "contract", "contracts"],
                "default_tool": "get_active_contracts"
            },
            "lead_query": {
                "patterns": ["lead", "leads", "kunde", "kunden"],
                "default_tool": "get_recent_leads"
            },
            "statistics_query": {
                "patterns": ["statistik", "statistics", "performance", "umsatz", "revenue"],
                "default_tool": "get_user_statistics"
            }
        },
        "fallback_tool": "get_care_stays_by_date_range",
        "force_tool_patterns": {
            "get_care_stays_by_date_range": ["im monat", "im jahr", "in 2025", "im mai", "im april", "im märz"]
        }
    }
    
    try:
        with open(TOOL_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
        logging.info(f"Standard-Tool-Konfigurationsdatei erstellt: {TOOL_CONFIG_PATH}")
    except Exception as e:
        logging.error(f"Fehler beim Erstellen der Tool-Konfigurationsdatei: {e}")