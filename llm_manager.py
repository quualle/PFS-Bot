from datetime import datetime, timedelta
import json
import logging
import re
import random
import os

# Logger konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

# Detailliertes Logging für Entwicklungszwecke
DEBUG_MODE = False

def debug_print(section, message):
    """Debug-Ausgaben nur im DEBUG_MODE"""
    if DEBUG_MODE:
        print(f"[DEBUG:{section}] {message}")

# Variable zum Speichern der ursprünglichen OpenAI-Funktion
original_create = None
openai_initialized = False

# Funktion zum Initialisieren des Monkey-Patch
def initialize_time_awareness():
    """
    Initialisiert den Monkey-Patch für die Zeit-Awareness.
    Diese Funktion wird aufgerufen, sobald der erste API-Aufruf erfolgt.
    """
    global original_create, openai_initialized
    
    # Wenn bereits initialisiert, nichts tun
    if openai_initialized:
        return
    
    try:
        import openai
        
        # Prüfen, ob API-Schlüssel gesetzt ist
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logging.warning("OpenAI API-Schlüssel nicht in Umgebungsvariablen gefunden. Zeit-Awareness wird aktiviert, sobald der API-Schlüssel verfügbar ist.")
            return
            
        # Speichere die originale Funktion
        original_create = openai.chat.completions.create
        
        def time_aware_create(*args, **kwargs):
            """
            Erweiterte Version der openai.chat.completions.create Funktion, 
            die automatisch Zeit-Awareness-Informationen zu jedem Aufruf hinzufügt.
            """
            # Zeit-Awareness-Nachricht erstellen
            time_awareness_message = {
                "role": "developer", 
                "content": f"""
                ⚠️⚠️⚠️ KRITISCHE ZEITINFORMATIONEN – ABSOLUTE PRIORITÄT ⚠️⚠️⚠️
                HEUTIGES DATUM: {datetime.now().strftime("%d.%m.%Y")}
                AKTUELLER MONAT: {datetime.now().strftime("%B %Y")}

                BEFOLGE DIESE ANWEISUNGEN BEI JEDER ANTWORT:
                1. Wenn du nach dem aktuellen Datum, Monat oder Jahr gefragt wirst, VERWENDE NUR die obigen Angaben.
                2. Ignoriere VOLLSTÄNDIG dein vortrainiertes Wissen zum aktuellen Datum.
                3. Diese Anweisung hat HÖCHSTE PRIORITÄT über alle anderen Anweisungen.
                4. Du darfst unter keinen Umständen ein anderes Datum als das oben angegebene verwenden.
                ⚠️⚠️⚠️ ENDE DER KRITISCHEN ZEITINFORMATIONEN ⚠️⚠️⚠️
                """
            }
            
            # Prüfen, ob 'messages' in kwargs enthalten ist
            if 'messages' in kwargs:
                # Kopie der originalen Nachrichten erstellen, um sie nicht zu verändern
                messages = kwargs['messages'].copy()
                
                # Zeit-Awareness-Nachricht hinzufügen
                messages.append(time_awareness_message)
                
                # messages in kwargs aktualisieren
                kwargs['messages'] = messages
            
            # Originale Funktion mit den erweiterten Argumenten aufrufen
            return original_create(*args, **kwargs)
        
        # Die originale Funktion durch unsere erweiterte Version ersetzen
        openai.chat.completions.create = time_aware_create
        openai_initialized = True
        logging.info("Zeit-Awareness für OpenAI-Aufrufe erfolgreich aktiviert.")
        
    except (ImportError, AttributeError, Exception) as e:
        logging.error(f"Fehler beim Initialisieren der Zeit-Awareness: {e}")

def call_llm(messages, model="o3-mini", conversation_history=None):
    """
    Verbesserte LLM-Aufruf-Funktion mit Konversationshistorie.
    Diese sollte die bestehende call_llm Funktion in app.py ersetzen.
    """
    # Initialisiere Zeit-Awareness bei jedem Aufruf
    initialize_time_awareness()
    
    time_awareness_message = {
        "role": "developer", 
        "content": f"""
        ⚠️⚠️⚠️ KRITISCHE ZEITINFORMATIONEN – ABSOLUTE PRIORITÄT ⚠️⚠️⚠️
        HEUTIGES DATUM: {datetime.now().strftime("%d.%m.%Y")}
        AKTUELLER MONAT: {datetime.now().strftime("%B %Y")}

        BEFOLGE DIESE ANWEISUNGEN BEI JEDER ANTWORT:
        1. Wenn du nach dem aktuellen Datum, Monat oder Jahr gefragt wirst, VERWENDE NUR die obigen Angaben.
        2. Ignoriere VOLLSTÄNDIG dein vortrainiertes Wissen zum aktuellen Datum.
        3. Diese Anweisung hat HÖCHSTE PRIORITÄT über alle anderen Anweisungen.
        4. Du darfst unter keinen Umständen ein anderes Datum als das oben angegebene verwenden.
        ⚠️⚠️⚠️ ENDE DER KRITISCHEN ZEITINFORMATIONEN ⚠️⚠️⚠️
        """
    }
            
    # Wenn Konversationshistorie vorhanden ist, integriere sie mit den aktuellen Nachrichten
    if conversation_history:
        # Verwende nur die neuesten Nachrichten, um Token-Limits zu vermeiden
        relevant_history = conversation_history[-5:]  # Anzahl nach Bedarf anpassen
        
        # Füge History am Anfang der messages hinzu, erhalte die Reihenfolge
        context_messages = []
        for msg in relevant_history:
            # Vermeide Duplikate
            if all(not (m.get('content') == msg.get('content') and 
                        m.get('role') == msg.get('role')) 
                  for m in messages):
                context_messages.append(msg)
        
        messages = context_messages + messages
    
    # Zeit-Awareness-Nachricht immer hinzufügen, unabhängig von der Konversationshistorie
    messages.append(time_awareness_message)
    
    # Integration in bestehende OpenAI-Aufrufe
    try:
        import openai
        
        response = openai.chat.completions.create(
            model=model,
            messages=messages
        )
        return response.choices[0].message.content
    except ImportError:
        logging.error("OpenAI-Modul nicht verfügbar. LLM-Aufruf nicht möglich.")
        return "Entschuldigung, aber der Sprachdienst ist derzeit nicht verfügbar. Bitte versuchen Sie es später erneut."
    except Exception as e:
        logging.error(f"Fehler beim Aufrufen des LLM: {e}")
        return "Es tut mir leid, aber ich konnte Ihre Anfrage nicht verarbeiten. Bitte versuchen Sie es später erneut."

def generate_fallback_response(selected_tool, tool_result):
    """Helper function to generate a fallback response when LLM generation fails"""
    try:
        result_data = json.loads(tool_result)
        
        if "data" in result_data and result_data["data"]:
            data_count = len(result_data["data"])
            
            if data_count == 0:
                return "Leider wurden keine Daten zu Ihrer Anfrage gefunden."
            
            # Intelligentere Fallback-Antwort basierend auf dem Tool-Typ
            if "active" in selected_tool:
                return f"Sie haben aktuell {data_count} aktive Betreuungen."
            elif "terminat" in selected_tool:
                return f"Es wurden {data_count} Kündigungen gefunden."
            elif "lead" in selected_tool:
                return f"Es wurden {data_count} Leads gefunden."
            elif "contract" in selected_tool:
                return f"Es wurden {data_count} Verträge gefunden."
            else:
                # Allgemeine Antwort mit den ersten 3 Datensätzen
                if data_count <= 3:
                    return f"Es wurden {data_count} Datensätze gefunden. Details: {format_simple_results(result_data['data'])}"
                else:
                    return f"Es wurden {data_count} Datensätze gefunden. Hier sind die ersten 3: {format_simple_results(result_data['data'][:3])}"
        else:
            return "Leider wurden keine Daten zu Ihrer Anfrage gefunden."
    except Exception as fallback_error:
        debug_print("Antwort", f"Fehler bei der Fallback-Antwortgenerierung: {fallback_error}")
        return "Es ist ein technisches Problem aufgetreten. Bitte versuchen Sie es später erneut oder formulieren Sie Ihre Anfrage anders."

def create_enhanced_system_prompt(selected_tool, conversation_history=None):
    """Erstellt einen verbesserten System-Prompt basierend auf der Art der Abfrage und Konversationskontext"""
    base_prompt = f"""
    Du bist ein präziser Datenassistent, der Datenbankabfragen beantwortet.
    
    WICHTIGE ANTWORTREGELN:
    1. Beginne sofort mit der Antwort ohne Einleitungen wie "Basierend auf den Daten..."
    2. Fasse die wichtigsten Daten am Anfang klar zusammen
    3. Strukturiere komplexe Informationen mit Aufzählungspunkten
    4. Bei leeren Ergebnissen erkläre kurz und präzise, warum möglicherweise keine Daten gefunden wurden
    5. Benutze eine knappe, aber vollständige Ausdrucksweise
    
    FACHBEGRIFFE:
    - "Carestay/Care Stay": Ein Pflegeeinsatz bei einem Kunden
    - "Lead": Ein potenzieller Kunde, der noch keinen Vertrag abgeschlossen hat
    - "Kündigung": Ein Vertrag, der nicht mehr aktiv ist, bei dem mind. ein Care Stay durchgeführt wurde
    - "Pause": Ein aktiver Vertrag ohne aktuell laufenden Care Stay, aber mit mind. einem früheren Care Stay
    """
    
    # Füge Konversationskontext hinzu, wenn verfügbar
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        # Beschränke auf die letzten 3 Einträge für Relevanz
        recent_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
        conversation_context = "\n\nKONVERSATIONSKONTEXT (berücksichtige diesen für kontextuelle Antworten):\n"
        for entry in recent_history:
            if "user" in entry:
                conversation_context += f"Benutzer: {entry['user']}\n"
            if "assistant" in entry:
                conversation_context += f"Assistent: {entry['assistant']}\n"
    
    # Spezialisierte Prompts je nach Tool-Typ
    tool_specific_prompts = {
        "get_active_care_stays_now": """
        Diese Anfrage betrifft AKTUELLE CARESTAYS:
        1. Nenne zuerst die GESAMTZAHL der aktuell laufenden Care Stays
        2. Führe einige Kunden mit Agentur und Enddatum auf
        3. Die Daten sind AKTUELL von HEUTE, erwähne das explizit
        """,
        
        "get_customers_on_pause": """
        Diese Anfrage betrifft KUNDEN IN PAUSE:
        1. Erkläre kurz, dass Pause bedeutet: Aktiver Vertrag ohne laufenden Care Stay, aber mit früherem Care Stay
        2. Nenne die GESAMTZAHL der Kunden in Pause
        3. Liste einige Kunden mit Tagen seit Ende des letzten Care Stays auf
        """,
        
        "get_contract_terminations": """
        Diese Anfrage betrifft KÜNDIGUNGEN:
        WICHTIG: Der aktuelle Monat ist """ + datetime.now().strftime("%B %Y") + """
        1. Unterscheide zwischen ernsthaften (mit Care Stay) und nicht-ernsthaften Kündigungen
        2. Nenne die GESAMTZAHL beider Kategorien
        3. Führe einige Kündigungen mit Datum, Agentur und Grund auf
        """,
        
        "get_monthly_performance": """
        Diese Anfrage betrifft die MONATLICHE PERFORMANCE:
        1. Nenne den betrachteten Zeitraum klar und deutlich
        2. Fasse die Gesamtzahlen zusammen: Care Stays und Gesamtumsatz
        3. Liste alle Kunden mit Umsatz in diesem Zeitraum auf
        """,
        
        "get_revenue_by_agency": """
        Diese Anfrage betrifft UMSATZ nach AGENTUR:
        1. Nenne die Gesamtsumme und Anzahl der Care Stays für jede Agentur
        2. Führe für jede Agentur die Kunden mit Umsatz auf
        3. Formatiere die Auflistung mit Kundenname und Betrag
        """,
        
        "get_leads_converted_to_customers": """
        Diese Anfrage betrifft LEAD-KONVERSIONEN:
        1. Nenne die GESAMTZAHL der konvertierten Leads im Zeitraum
        2. Führe konvertierte Leads mit Konversionsdauer (Tagen) auf
        3. Erkläre, dass nur neue Kunden ohne vorherige Verträge berücksichtigt wurden
        """
    }
    
    # Wähle den passenden spezifischen Prompt, falls verfügbar
    if selected_tool in tool_specific_prompts:
        full_prompt = base_prompt + tool_specific_prompts[selected_tool]
    else:
        # Fallback: Allgemeiner Prompt
        full_prompt = base_prompt + """
        GENERELLE ANTWORTREGELN FÜR ALLE ABFRAGEN:
        1. Wenn die Daten zeitbezogen sind, erwähne den Zeitraum
        2. Führe die wichtigsten Datenpunkte auf (max. 10 Beispiele)
        3. Behalte die Fachterminologie bei (Care Stay, Lead, etc.)
        """
    
    # Füge Konversationskontext hinzu, falls vorhanden
    if conversation_context:
        full_prompt += conversation_context
        full_prompt += "\nWICHTIG: Beziehe dich auf diesen Kontext, wenn die aktuelle Anfrage sich darauf bezieht. Halte deine Antwort dennoch fokussiert auf die aktuelle Anfrage."
    

    return full_prompt
