def format_customer_details(result_data):
    """Formatiert Kundendaten für bessere Lesbarkeit"""
    try:
        if not result_data or "data" not in result_data or not result_data["data"]:
            return "Keine Kundendaten gefunden."
        
        customer = result_data["data"][0]
        output = f"# Kundenübersicht für {customer['first_name']} {customer['last_name']}\n\n"
        
        # Basisdaten
        output += f"**Kunde seit:** {format_date(customer['lead_created_at'])}\n"
        output += f"**Anzahl Verträge:** {customer['contracts_count']}\n"
        output += f"**Anzahl Care Stays:** {customer['care_stays_count']}\n"
        output += f"**Gesamte Betreuungstage:** {customer['total_care_days'] or 0}\n"
        output += f"**Zusammenarbeit mit Agenturen:** {customer['agencies'] or 'Keine'}\n\n"
        
        # Vertragsübersicht
        if customer.get('contracts_summary'):
            output += "## Vertragsübersicht\n"
            for line in customer['contracts_summary'].split('\n'):
                if line.strip():
                    output += f"- {line}\n"
            output += "\n"
        
        # Care Stays Übersicht
        if customer.get('care_stays_summary'):
            output += "## Pflegeeinsätze\n"
            for line in customer['care_stays_summary'].split('\n'):
                if line.strip():
                    output += f"- {line}\n"
            output += "\n"
            
        # Zusammenfassung
        output += "## Zusammenfassung\n"
        first_date = format_date(customer.get('first_contract_date', ''))
        output += f"Kunde seit {first_date}" 
        
        if customer.get('care_stays_count') and int(customer.get('care_stays_count', 0)) > 0:
            if customer.get('total_care_days'):
                avg_duration = int(customer['total_care_days']) / int(customer['care_stays_count'])
                output += f" mit durchschnittlich {avg_duration:.1f} Tagen pro Einsatz.\n"
            else:
                output += ".\n"
        else:
            output += ".\n"
        
        return output
    except Exception as e:
        logging.exception(f"Fehler bei der Formatierung der Kundendaten: {e}")
        return f"Fehler bei der Formatierung: {str(e)}"

def format_date(date_str):
    """Formatiert ein Datum in lesbares Format"""
    if not date_str:
        return "unbekannt"
    try:
        # Versuche zuerst ISO-Format zu parsen
        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date_obj.strftime("%d.%m.%Y")
    except ValueError:
        try:
            # Versuche andere gängige Formate
            from dateutil import parser
            date_obj = parser.parse(date_str)
            return date_obj.strftime("%d.%m.%Y")
        except:
            # Fallback: Gib das Original zurück
            return date_str

def extract_date_params(user_message):
    """Extract date parameters from user message for months like 'Mai'."""
    import datetime  # Local import to ensure we have the right module
    import re
    extracted_args = {}
    
    # Map German month names to numbers
    month_map = {
        "januar": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
        "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12
    }
    
    user_message_lower = user_message.lower()
    current_date = datetime.datetime.now()  # Using full namespace
    current_year = current_date.year
    
    # Extract year if present
    year_match = re.search(r'\b(20\d\d)\b', user_message)
    extracted_year = int(year_match.group(1)) if year_match else current_year
    
    # Check for month mentions
    for month_name, month_num in month_map.items():
        if month_name in user_message_lower:
            # Use extracted year or current year
            year = extracted_year
                
            # Create start and end dates for the month
            start_date = datetime.date(year, month_num, 1)  # Using datetime.date
            if month_num == 12:
                end_date = datetime.date(year, 12, 31)
            else:
                next_month_date = datetime.date(year, month_num + 1, 1)
                end_date = next_month_date - datetime.timedelta(days=1)
                
            extracted_args["start_date"] = start_date.strftime("%Y-%m-%d")
            extracted_args["end_date"] = end_date.strftime("%Y-%m-%d")
            debug_print("Datumsextraktion", f"Erkannter Monat: {month_name}, Jahr: {year}, Start: {extracted_args['start_date']}, Ende: {extracted_args['end_date']}")
            return extracted_args
    
    # Fall back to dateparser for more complex date expressions
    parsed_date = dateparser.parse(
        user_message,
        languages=["de"],
        settings={"PREFER_DATES_FROM": "future"},
    )
    if parsed_date:
        extracted_args["year_month"] = parsed_date.strftime("%Y-%m")
        # Create start/end dates for the month
        year = parsed_date.year
        month = parsed_date.month
        
        start_date = datetime.date(year, month, 1)
        if month == 12:
            end_date = datetime.date(year, 12, 31)
        else:
            next_month_date = datetime.date(year, month + 1, 1)
            end_date = next_month_date - datetime.timedelta(days=1)
        
        extracted_args["start_date"] = start_date.strftime("%Y-%m-%d")
        extracted_args["end_date"] = end_date.strftime("%Y-%m-%d")
        debug_print("Datumsextraktion", f"Erkanntes Datum: {extracted_args}")
    
    return extracted_args

def extract_enhanced_parameters(user_message, selected_tool, tools_info):
    """
    Extrahiert verschiedene Parameter aus der Benutzeranfrage basierend auf dem ausgewählten Tool
    
    Args:
        user_message: Die Nachricht des Benutzers
        selected_tool: Der Name des ausgewählten Tools
        tools_info: Informationen über alle verfügbaren Tools
        
    Returns:
        dict: Extrahierte Parameter für die Anfrage
    """
    params = {}
    
    # Standardparameter aus anderen Extraktionen
    date_params = extract_enhanced_date_params(user_message)
    params.update(date_params)
    
    # Tool-spezifische Parameter extrahieren
    if selected_tool == "get_contracts_by_agency":
        # Agentur-Namen extrahieren
        agency_name = extract_agency_name(user_message)
        if agency_name:
            params["agency_name"] = agency_name
    
    elif selected_tool == "get_customer_history":
        # Kundennamen extrahieren
        customer_name = extract_customer_name(user_message)
        if customer_name:
            params["customer_name"] = customer_name
    
    # Ergänze mit LLM-basierter Parameterextraktion für komplexere Fälle
    if selected_tool in tools_info:
        required_params = tools_info[selected_tool].get("required_parameters", [])
        missing_params = [p for p in required_params if p not in params and p != "seller_id"]
        
        if missing_params:
            llm_params = extract_parameters_with_llm(user_message, selected_tool, missing_params)
            params.update(llm_params)
    
    return params

def extract_agency_name(user_message):
    """
    Extrahiert den Namen einer Agentur aus einer Benutzeranfrage
    
    Sucht nach bekannten Agentur-Namen oder nach typischen Mustern wie "Agentur XYZ"
    oder "mit XYZ" in verschiedenen Variationen.
    
    Args:
        user_message: Die Nachricht des Benutzers
        
    Returns:
        str or None: Der extrahierte Agenturname oder None
    """
    user_message = user_message.lower()
    
    # Liste bekannter Agenturen (aus der Datenbank oder Konfiguration)
    known_agencies = [
        "senioport", "medipe", "promedica", "aterima", "pflegehelden", 
        "felizajob", "polonia", "carema", "advitum", "care-work"
    ]
    
    # Nach bekannten Agenturen suchen
    for agency in known_agencies:
        if agency in user_message:
            return agency
    
    # Nach Mustern suchen wie "Agentur XYZ", "mit XYZ", "von XYZ"
    agency_patterns = [
        r'agentur[:\s]+([a-zäöüß\s]+)',
        r'mit der[:\s]+([a-zäöüß\s]+)(?:agentur|vermittlung)',
        r'mit[:\s]+([a-zäöüß\s]+)(?:agentur|vermittlung)',
        r'von[:\s]+([a-zäöüß\s]+)(?:agentur|vermittlung)',
        r'bei[:\s]+([a-zäöüß\s]+)',
        r'durch[:\s]+([a-zäöüß\s]+)'
    ]
    
    for pattern in agency_patterns:
        match = re.search(pattern, user_message)
        if match:
            # Bereinigen des extrahierten Textes
            agency_name = match.group(1).strip()
            # Entfernen von Stoppwörtern am Ende
            agency_name = re.sub(r'\b(der|die|das|und|oder|als|wie)\s*$', '', agency_name).strip()
            if agency_name:
                return agency_name
    
    return None

def extract_customer_name(user_message):
    """
    Extrahiert einen Kundennamen aus einer Benutzeranfrage
    
    Sucht nach typischen Mustern wie "Kunde XYZ", "Herr XYZ", "Frau XYZ" oder 
    "über XYZ" in verschiedenen Variationen.
    
    Args:
        user_message: Die Nachricht des Benutzers
        
    Returns:
        str or None: Der extrahierte Kundenname oder None
    """
    user_message = user_message.lower()
    
    # Spezielle Behandlung für Kunde "Küll" mit verschiedenen Schreibweisen
    kull_variations = ["küll", "kull", "kühl", "kuehl", "kuell"]
    for variation in kull_variations:
        if variation in user_message:
            logging.info(f"Spezialfall erkannt: Kunde 'Küll' (Variation '{variation}')")
            return "Küll"
    
    # Spezieller Regex für Küll aufgrund der Häufigkeit dieses Kunden
    kull_patterns = [
        r'kunde[n]?[:\s]+(k[uü][eh]?ll)',
        r'kunden[:\s]+(k[uü][eh]?ll)',
        r'herr[n]?[:\s]+(k[uü][eh]?ll)',
        r'zum kunden (k[uü][eh]?ll)',
        r'über (k[uü][eh]?ll)'
    ]
    
    for pattern in kull_patterns:
        match = re.search(pattern, user_message)
        if match:
            logging.info(f"Kunde 'Küll' erkannt mit Muster: {pattern}")
            return "Küll"
    
    # Nach Mustern suchen wie "Kunde XYZ", "Herr XYZ", "Frau XYZ", "über XYZ"
    customer_patterns = [
        r'kunde[n]?[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'kunden[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'herr[n]?[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'frau[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'familie[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'über[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'von[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'für[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'bei[:\s]+([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'zum kunden ([a-zäöüß0-9\s\(\)\[\]\-]+)',
        r'namens ([a-zäöüß0-9\s\(\)\[\]\-]+)'
    ]
    
    for pattern in customer_patterns:
        match = re.search(pattern, user_message)
        if match:
            # Bereinigen des extrahierten Textes
            customer_name = match.group(1).strip()
            # Entfernen von Stoppwörtern am Ende
            customer_name = re.sub(r'\b(der|die|das|und|oder|als|wie)\s*$', '', customer_name).strip()
            
            # Prüfen auf übliche Abkürzungen oder unerwünschte Teile
            if len(customer_name) > 2 and not customer_name.startswith(('der ', 'die ', 'das ')):
                logging.info(f"Erkannter Kundenname: {customer_name}")
                return customer_name
    
    # Nach alleinstehenden Namen suchen, wenn sie in Anführungszeichen stehen
    quotes_pattern = r'["\']([a-zäöüß0-9\s\(\)\[\]\-]{3,})["\']'
    match = re.search(quotes_pattern, user_message)
    if match:
        customer_name = match.group(1).strip()
        logging.info(f"Kundenname in Anführungszeichen erkannt: {customer_name}")
        return customer_name
    
    return None

def extract_parameters_with_llm(user_message, tool_name, missing_params):
    """
    Extrahiert Parameter mithilfe eines LLM-Aufrufs für komplexere Anfragen
    
    Args:
        user_message: Die Nachricht des Benutzers
        tool_name: Der Name des ausgewählten Tools
        missing_params: Liste der fehlenden Parameter
        
    Returns:
        dict: Extrahierte Parameter
    """
    if not missing_params:
        return {}
    
    system_prompt = f"""
    Du bist ein Spezialist für die Extraktion von Parametern aus Benutzeranfragen.
    Deine Aufgabe ist es, die folgenden Parameter aus der Anfrage zu extrahieren:
    {', '.join(missing_params)}
    
    Für das Tool '{tool_name}'.
    
    Antworte AUSSCHLIESSLICH im JSON-Format: {{"param1": "wert1", "param2": "wert2", ...}}
    
    WICHTIG: 
    - Bei Agenturnamen (agency_name): Extrahiere den Namen ohne "Agentur" oder "Vermittlung"
    - Bei Kundennamen (customer_name): Extrahiere den Namen ohne Titel wie "Herr" oder "Frau"
    - Wenn ein Parameter nicht gefunden werden kann, lasse ihn weg (gib kein leeres Feld zurück)
    """
    
    messages = [
        {"role": "developer", "content": system_prompt},
        {"role": "user", "content": f"Benutzeranfrage: '{user_message}'\nExtrahiere die benötigten Parameter."}
    ]
    
    try:
        response = openai.chat.completions.create(
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
                
                # Parameter bereinigen
                for key, value in list(extracted_params.items()):
                    if isinstance(value, str):
                        # Entferne Anführungszeichen und Sonderzeichen am Anfang und Ende
                        value = value.strip('"\'.,;: ')
                        # Entferne Füllwörter und Titel
                        value = re.sub(r'^(agentur|firma|vermittlung|herr|frau|familie)\s+', '', value, flags=re.IGNORECASE)
                        extracted_params[key] = value
                
                return extracted_params
        except json.JSONDecodeError:
            logging.warning(f"Konnte JSON nicht aus LLM-Antwort parsen: {response_text}")
        
        # Fallback: Manuelles Parsing wenn JSON-Parse fehlschlägt
        extracted_params = {}
        for param in missing_params:
            # Hier ist die korrigierte Zeile mit doppelten geschweiften Klammern
            param_match = re.search(rf'"{param}":\s*"?([^",}}]*)"?', response_text)
            if param_match:
                value = param_match.group(1).strip()
                if value:
                    extracted_params[param] = value
        
        return extracted_params
    except Exception as e:
        logging.error(f"Fehler bei LLM-Parameterextraktion: {e}")
        return {}

def extract_enhanced_date_params(user_message):
    """
    Erweiterte Version von extract_date_params mit mehr Robustheit:
    - Unterstützt mehrere Sprachen (DE, EN)
    - Erweiterte Regex-Patterns für Monatsnamen
    - Bessere Fehlerbehandlung
    - Kontextbewusste Datumsergänzung
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
                debug_print("Datumsextraktion", f"Extrahierter Monat: {month_name}, Jahr: {year}, Start: {extracted_args['start_date']}, Ende: {extracted_args['end_date']}")
                return extracted_args
            except ValueError as e:
                debug_print("Datumsextraktion", f"Fehler bei der Datumskonvertierung: {e}")
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
            debug_print("Datumsextraktion", f"Erkanntes Datum via dateparser: {extracted_args}")
    except Exception as e:
        debug_print("Datumsextraktion", f"Fehler bei dateparser: {e}")
    
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
        debug_print("Datumsextraktion", f"Fallback auf aktuellen Monat: {extracted_args}")
    
    return extracted_args

def extract_enhanced_date_params(user_message):
    """
    Erweiterte Version von extract_date_params mit mehr Robustheit:
    - Unterstützt mehrere Sprachen (DE, EN)
    - Erweiterte Regex-Patterns für Monatsnamen
    - Bessere Fehlerbehandlung
    - Kontextbewusste Datumsergänzung
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
                debug_print("Datumsextraktion", f"Extrahierter Monat: {month_name}, Jahr: {year}, Start: {extracted_args['start_date']}, Ende: {extracted_args['end_date']}")
                return extracted_args
            except ValueError as e:
                debug_print("Datumsextraktion", f"Fehler bei der Datumskonvertierung: {e}")
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
            debug_print("Datumsextraktion", f"Erkanntes Datum via dateparser: {extracted_args}")
    except Exception as e:
        debug_print("Datumsextraktion", f"Fehler bei dateparser: {e}")
    
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
        debug_print("Datumsextraktion", f"Fallback auf aktuellen Monat: {extracted_args}")
    
    return extracted_args
