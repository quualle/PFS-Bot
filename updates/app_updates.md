# App.py Updates

## Import Section
Add these import statements at the top of the file (after the existing imports):

```python
# Import the LLM-based query selector
try:
    from query_selector import select_query_with_llm, update_selection_feedback
    USE_LLM_QUERY_SELECTOR = True
    logging.info("LLM-based query selector loaded successfully")
except ImportError as e:
    logging.warning(f"LLM-based query selector not available: {e}")
    USE_LLM_QUERY_SELECTOR = False
```

## select_optimal_tool_with_reasoning Function
Replace the existing `select_optimal_tool_with_reasoning` function with this updated version:

```python
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
            
            # Nutze die select_query_with_llm Methode zur semantischen Auswahl
            query_name, parameters = select_query_with_llm(
                user_message, 
                conversation_history=None,  # TODO: Könnte session.get('chat_history') sein
                user_id=None  # Wird später im Code mit seller_id ergänzt
            )
            
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
    
    # SCHICHT 1: Direkte Muster-Erkennung für häufige Anfragen
    # Prüfe auf explizite Muster, die bestimmte Tools erzwingen
    for tool_name, patterns in tool_config.get("force_tool_patterns", {}).items():
        for pattern in patterns:
            if pattern.lower() in user_message_lower:
                debug_print("Tool-Auswahl", f"Regelbasierte Auswahl: Erkanntes Muster '{pattern}'")
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
            debug_print("Tool-Auswahl", f"Kategorie-basierte Auswahl: {', '.join(detected_categories)}")
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
```

Note: Because of duplicated function definitions in the app.py file, carefully check that you replace both instances of the function for a clean implementation. 

You may need to also update any function calls that use legacy patterns to work with the updated function.

## Updating Feedback Collection

If you want to add a feedback loop for improving the LLM query selector, you can add code before the final return of query results to update the feedback results:

```python
# Add this where the function call results are processed
if USE_LLM_QUERY_SELECTOR:
    # After executing the function and getting results
    try:
        # Mark this query selection as successful if results were returned without error
        update_selection_feedback(user_message, selected_query, success=True)
    except Exception as e:
        logging.error(f"Error updating selection feedback: {e}")
```