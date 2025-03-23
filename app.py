import os
import json
import re
import time
import logging
import logging
import datetime
from functools import wraps
import traceback
import uuid
import tempfile
import requests  # Added import for requests
from datetime import datetime, timedelta
import dateparser
from conversation_manager import ConversationManager

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, Response
from flask_wtf import CSRFProtect
from flask_session import Session
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account
from google.cloud import bigquery
from werkzeug.utils import secure_filename
import openai
import tiktoken
import yaml
import re
from sql_query_helper import apply_query_enhancements

try:
    from query_selector import select_query_with_llm, update_selection_feedback, process_clarification_response, process_text_clarification_response
    USE_LLM_QUERY_SELECTOR = True
    logging.info("LLM-based query selector loaded successfully")
except ImportError as e:
    logging.warning(f"LLM-based query selector not available: {e}")
    USE_LLM_QUERY_SELECTOR = False

def load_tool_config():
    """Lädt die Tool-Konfiguration aus einer YAML-Datei"""
    TOOL_CONFIG_PATH = "tool_config.yaml"
    try:
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tool-Konfiguration: {e}")
        # Einfache leere Konfiguration ohne hartcodierte Regeln
        return {
            "description": "Tool-Konfiguration für LLM-basierte Entscheidungen"
        }

conversation_manager = ConversationManager(max_history=10)


###########################################
# PINECONE: gRPC-Variante laut Quickstart
###########################################
from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec

# Zusätzliche Importe für Dateiverarbeitung
from PyPDF2 import PdfReader
import docx

# Für Datum / Statistik
from datetime import datetime

from bigquery_functions import (
    handle_function_call, 
    summarize_query_result, 
    get_user_id_from_email
)

# Laden der Umgebungsvariablen aus .env
load_dotenv()

# Google OAuth Konfiguration
def configure_google_auth(app):
    """Konfiguriert die direkte Google OAuth-Authentifizierung."""
    # Stellen Sie sicher, dass die Umgebungsvariablen gesetzt sind
    if not os.getenv('GOOGLE_CLIENT_ID') or not os.getenv('GOOGLE_CLIENT_SECRET'):
        print("WARNUNG: Google OAuth-Credentials nicht gesetzt!")
    
    # Direkten Login-Endpoint definieren - make route path and function name match
    @app.route('/google_login')
    def google_login():
        """Eine direkte Google-Login-Route"""
        # Erstelle eine URL für die Google OAuth-Seite
        redirect_uri = url_for('google_callback', _external=True)
        print(f"Redirect URI being used: {redirect_uri}")  # Add this debug line
        
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

    # Callback für den direkten Login
    @app.route('/google_callback')
    def google_callback():
        """Callback für den direkten Google-Login"""
        code = request.args.get('code')
        
        if not code:
            flash('Login fehlgeschlagen (kein Code erhalten).', 'danger')
            return redirect(url_for('login'))
        
        # Code gegen Token tauschen
        try:
            token_url = "https://oauth2.googleapis.com/token"
            token_data = {
                'code': code,
                'client_id': os.getenv('GOOGLE_CLIENT_ID'),
                'client_secret': os.getenv('GOOGLE_CLIENT_SECRET'),
                'redirect_uri': url_for('google_callback', _external=True),
                'grant_type': 'authorization_code'
            }
            
            token_response = requests.post(token_url, data=token_data)
            
            if not token_response.ok:
                flash(f'Token-Abruf fehlgeschlagen: {token_response.text}', 'danger')
                return redirect(url_for('login'))
            
            token_info = token_response.json()
            access_token = token_info.get('access_token')
            
            # Benutzerinfo abrufen
            userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
            headers = {'Authorization': f'Bearer {access_token}'}
            userinfo_response = requests.get(userinfo_url, headers=headers)
            
            if not userinfo_response.ok:
                flash(f'Userinfo-Abruf fehlgeschlagen: {userinfo_response.text}', 'danger')
                return redirect(url_for('login'))
            
            user_info = userinfo_response.json()
            
            # Session aktualisieren
            email = user_info.get('email')
            name = user_info.get('name')
            
            # Setze die Session-Variablen
            user_id = session.get('user_id')
            if not user_id:
                user_id = str(uuid.uuid4())
                session['user_id'] = user_id
                
            session['email'] = email
            session['google_user_email'] = email
            session['user_name'] = name
            session['is_logged_via_google'] = True
            
            # Seller ID abrufen, wenn eine E-Mail vorhanden ist
            if email:
                seller_id = get_user_id_from_email(email)
                session['seller_id'] = seller_id
                if seller_id:
                    print(f"Seller ID gefunden und gesetzt: {seller_id}")
                else:
                    print(f"Keine Seller ID für E-Mail {email} gefunden")
            
            session.modified = True
            
            flash('Login erfolgreich!', 'success')
            return redirect(url_for('chat'))
        
        except Exception as e:
            print(f"Fehler beim Google-Login: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'Fehler bei der Anmeldung: {str(e)}', 'danger')
            return redirect(url_for('login'))
    
    # Hilfsfunktion zur OAuth-Diagnose
    @app.route('/debug_oauth')
    def debug_oauth():
        """Diagnosewerkzeug für die OAuth-Konfiguration"""
        output = "<h1>OAuth Debug Info</h1>"
        
        # Umgebungsvariablen überprüfen (ohne Secrets zu zeigen)
        client_id = os.getenv('GOOGLE_CLIENT_ID', 'Nicht gesetzt')
        client_secret_status = "Gesetzt" if os.getenv('GOOGLE_CLIENT_SECRET') else "Nicht gesetzt"
        
        output += f"<p>GOOGLE_CLIENT_ID: {client_id[:5]}...{client_id[-5:] if len(client_id) > 10 else ''}</p>"
        output += f"<p>GOOGLE_CLIENT_SECRET: {client_secret_status}</p>"
        
        # Session-Status
        output += "<h2>Session Status</h2>"
        session_values = {k: v for k, v in session.items()}
        output += f"<pre>{json.dumps(session_values, indent=2)}</pre>"
        
        # Test Links - FIXED THIS LINE TO USE THE CORRECT FUNCTION NAME
        output += "<h2>Test Links</h2>"
        output += f"<p><a href='{url_for('google_login')}'>Google Login</a></p>"
        
        return output
    
    return app


app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Sicherheitskonfiguration der Session
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Google OAuth konfigurieren
app = configure_google_auth(app)
Session(app)

logging.basicConfig(level=logging.DEBUG)

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'uploaded_files')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# CSRF-Schutz
csrf = CSRFProtect(app)

openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    raise ValueError("Der OpenAI API-Schlüssel ist nicht gesetzt.")

###########################################
# Pinecone-Initialisierung (gRPC)
###########################################
pinecone_api_key = os.getenv('PINECONE_API_KEY')
pinecone_env = os.getenv('PINECONE_ENV')  # z.B. 'us-east-1'
pinecone_index_name = os.getenv('PINECONE_INDEX_NAME')

if not pinecone_api_key or not pinecone_index_name:
    raise ValueError("Bitte Pinecone API-Key und INDEX_NAME in .env setzen.")

# Pinecone-Client erstellen
pc = Pinecone(api_key=pinecone_api_key)
# Du kannst pinecone_env hier ggf. nicht explizit angeben – 
# Pinecone gRPC nutzt 'us-west1-gcp' oder 'us-east-1' ggf. 
# laut Projekt-Einstellungen.

# Index ggf. anlegen (Dimension=1536 für text-embedding-ada-002)
if not pc.has_index(pinecone_index_name):
    pc.create_index(
        name=pinecone_index_name,
        dimension=3072,
        metric="cosine",
        spec=ServerlessSpec(
            cloud="aws",
            region=pinecone_env or "us-east-1"
        )
    )
# Optional: Warten, bis Index ready
while not pc.describe_index(pinecone_index_name).status["ready"]:
    time.sleep(1)

# Index-Handle holen
index = pc.Index(pinecone_index_name)

###########################################
# Google Cloud Storage + Sonstige Einstellungen
###########################################
service_account_path = '/home/PfS/service_account_key.json'
if not os.path.exists(service_account_path):
    raise FileNotFoundError(f"Service Account Datei nicht gefunden: {service_account_path}")

credentials = service_account.Credentials.from_service_account_file(service_account_path)
client = storage.Client(credentials=credentials)
bucket_name = 'wissensbasis'
bucket = client.bucket(bucket_name)
wissensbasis_blob_name = 'wissensbasis.json'

DEBUG_CATEGORIES = {
    "API Calls": True,
    "Wissensbasis Download/Upload": True,
    "Bearbeiten von Einträgen": False,
    "Verschieben von Einträgen": False,
    "Sortieren von Einträgen": False,
    "UI Aktionen": False
}

def debug_print(category, message):
    if DEBUG_CATEGORIES.get(category, False):
        print(f"[{category}] {message}")

themen_datei = '/home/PfS/themen.txt'

#############################
# Neuer Ordner für Chat-Logs
#############################
CHATLOG_FOLDER = 'chatlogs'
if not os.path.exists(CHATLOG_FOLDER):
    os.makedirs(CHATLOG_FOLDER)

#############################
# Neuer Ordner für Feedback
#############################
FEEDBACK_FOLDER = 'feedback'
if not os.path.exists(FEEDBACK_FOLDER):
    os.makedirs(FEEDBACK_FOLDER)

def store_chatlog(user_name, chat_history):
    """
    Speichert den Chatverlauf als Textdatei in CHATLOG_FOLDER.
    Dateiname enthält den user_name und Datum + Uhrzeit.
    """
    if not user_name:
        user_name = "Unbekannt"

    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{user_name}_{timestamp_str}.txt"
    filepath = os.path.join(CHATLOG_FOLDER, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        for idx, convo in enumerate(chat_history):
            user_msg = convo.get('user', '').replace('\n', ' ')
            bot_msg = convo.get('bot', '').replace('\n', ' ')
            f.write(f"Nachricht {idx+1}:\n")
            f.write(f"  User: {user_msg}\n")
            f.write(f"  Bot : {bot_msg}\n\n")

def store_feedback(feedback_type, comment, chat_history):
    name_in_session = session.get('user_name', 'Unbekannt')
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{name_in_session}_{feedback_type}_{timestamp_str}.txt"
    filepath = os.path.join(FEEDBACK_FOLDER, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Feedback-Typ: {feedback_type}\n")
        f.write(f"Kommentar:\n{comment}\n\n")
        f.write("----- Chatverlauf -----\n\n")
        for idx, convo in enumerate(chat_history):
            user_msg = convo.get('user', '').replace('\n', ' ')
            bot_msg = convo.get('bot', '').replace('\n', ' ')
            f.write(f"Nachricht {idx+1}:\n")
            f.write(f"  User: {user_msg}\n")
            f.write(f"  Bot : {bot_msg}\n\n")

###########################################
# Chat-Statistik
###########################################
def calculate_chat_stats():
    total_count = 0
    year_count = 0
    month_count = 0
    day_count = 0

    now = datetime.now()
    current_year = now.year
    current_month = now.month
    current_day = now.day

    for filename in os.listdir(CHATLOG_FOLDER):
        if not filename.endswith(".txt"):
            continue
        
        filepath = os.path.join(CHATLOG_FOLDER, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Anzahl Chatnachrichten (Anzahl "User:" Vorkommen)
        message_pairs = content.count("User:")
        total_count += message_pairs


        try:
            date_str = filename.split("_")[1]  # => "YYYY-mm-dd"
            y, m, d = date_str.split("-")
            y, m, d = int(y), int(m), int(d)
        except:
            continue

        if y == current_year:
            year_count += message_pairs
            if m == current_month:
                month_count += message_pairs
                if d == current_day:
                    day_count += message_pairs

    return {
        'total': total_count,
        'year': year_count,
        'month': month_count,
        'today': day_count
    }

###########################################
# Download/Upload Wissensbasis (JSON)
###########################################
service_account_path = '/home/PfS/service_account_key.json'
if not os.path.exists(service_account_path):
    raise FileNotFoundError(f"Service Account Datei nicht gefunden: {service_account_path}")

credentials = service_account.Credentials.from_service_account_file(service_account_path)
client = storage.Client(credentials=credentials)
bucket_name = 'wissensbasis'
bucket = client.bucket(bucket_name)
wissensbasis_blob_name = 'wissensbasis.json'

def download_wissensbasis(max_retries=5, backoff_factor=1):
    debug_print("Wissensbasis Download/Upload", f"Versuche, Wissensbasis von '{wissensbasis_blob_name}' herunterzuladen.")
    blob = bucket.blob(wissensbasis_blob_name)

    content = '{}'
    for attempt in range(1, max_retries + 1):
        try:
            if blob.exists():
                content = blob.download_as_text(encoding='utf-8')
                debug_print("Wissensbasis Download/Upload", "Wissensbasis erfolgreich heruntergeladen.")
                break
            else:
                debug_print("Wissensbasis Download/Upload", "Wissensbasis-Datei existiert nicht.")
                break
        except Exception as e:
            debug_print("Wissensbasis Download/Upload", f"Fehler: {e}")
            if attempt < max_retries:
                wait_time = backoff_factor * (2 ** (attempt - 1))
                debug_print("Wissensbasis Download/Upload", f"Retry {attempt}: Warte {wait_time}s.")
                time.sleep(wait_time)
            else:
                flash(f"Fehler beim Herunterladen der Wissensbasis: {e}", 'danger')
                break

    wissensbasis = json.loads(content)
    for thema, unterthemen in wissensbasis.items():
        for unterthema, details in unterthemen.items():
            normalized_details = {key.lower(): value for key, value in details.items()}
            unterthemen[unterthema] = normalized_details
            normalized_details.setdefault('beschreibung', '')
            normalized_details.setdefault('inhalt', [])
    return wissensbasis

def upload_wissensbasis(wissensbasis, max_retries=5, backoff_factor=1):
    debug_print("Wissensbasis Download/Upload", "Versuche, Wissensbasis hochzuladen.")
    blob = bucket.blob(wissensbasis_blob_name)
    for attempt in range(1, max_retries + 1):
        try:
            blob.upload_from_string(
                json.dumps(wissensbasis, ensure_ascii=False, indent=4),
                content_type='application/json'
            )
            debug_print("Wissensbasis Download/Upload", "Wissensbasis hochgeladen.")
            time.sleep(0.5)
            return
        except Exception as e:
            debug_print("Wissensbasis Download/Upload", f"Fehler: {e}")
            if attempt < max_retries:
                wait_time = backoff_factor * (2 ** (attempt - 1))
                debug_print("Wissensbasis Download/Upload", f"Retry {attempt}: Warte {wait_time}s.")
                time.sleep(wait_time)
            else:
                flash(f"Fehler beim Hochladen der Wissensbasis: {e}", 'danger')

###########################################
# Themen (themen.txt) laden/aktualisieren
###########################################
themen_datei = '/home/PfS/themen.txt'

def lese_themenhierarchie(dateipfad):
    if not os.path.exists(dateipfad):
        return {}
    with open(dateipfad, 'r', encoding='utf-8') as f:
        zeilen = f.readlines()

    themen_dict = {}
    aktuelles_thema = None
    for zeile in zeilen:
        zeile = zeile.strip()
        if not zeile:
            continue
        match_thema = re.match(r'Thema\s*\d+:\s*.*', zeile)
        if match_thema:
            thema_key = zeile
            themen_dict[thema_key] = {}
            aktuelles_thema = thema_key
            continue
        match_unterpunkt = re.match(r'(\d+[a-z]*)\)?\s*([^/]+)\s*(//\s*(.*))?$', zeile)
        if match_unterpunkt:
            punkt_nummer = match_unterpunkt.group(1)
            punkt_titel = match_unterpunkt.group(2).strip()
            punkt_beschreibung = match_unterpunkt.group(4).strip() if match_unterpunkt.group(4) else ""
            if aktuelles_thema:
                themen_dict[aktuelles_thema][punkt_nummer] = {
                    "title": punkt_titel,
                    "beschreibung": punkt_beschreibung
                }
    return themen_dict

def lade_themen():
    return lese_themenhierarchie(themen_datei)

def get_next_thema_number(themen_dict):
    numbers = []
    for thema in themen_dict.keys():
        match = re.match(r'Thema\s+(\d+):\s+.*', thema)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers) + 1 if numbers else 1

def aktualisiere_themen(themen_dict):
    def sort_key(k):
        match = re.match(r'(\d+)([a-z]*)', k)
        if match:
            num = int(match.group(1))
            suf = match.group(2)
            return (num, suf)
        return (0, k)
    with open(themen_datei, 'w', encoding='utf-8') as file:
        for thema, unterpunkte in themen_dict.items():
            file.write(f"{thema}\n")
            sorted_up = sorted(unterpunkte.items(), key=lambda x: sort_key(x[0]))
            for punkt_nummer, punkt_info in sorted_up:
                punkt_titel = punkt_info['title']
                punkt_beschreibung = punkt_info.get('beschreibung', '')
                if punkt_beschreibung:
                    file.write(f"{punkt_nummer}) {punkt_titel}\t\t\t// {punkt_beschreibung}\n")
                else:
                    file.write(f"{punkt_nummer}) {punkt_titel}\n")
            file.write("\n")


###########################################
# Notfall-LOG-Funktion
###########################################
def log_notfall_event(user_id, notfall_art, user_message):
    log_path = "notfall_logs.json"
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "notfall_art": notfall_art,
        "message": user_message
    }
    logs = []
    if os.path.exists(log_path):
        with open(log_path, 'r', encoding='utf-8') as f:
            try:
                logs = json.load(f)
            except:
                logs = []
    logs.append(log_entry)
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

###########################################
# Wissenseintrag in JSON + Pinecone speichern
###########################################
def speichere_wissensbasis(eintrag):
    wissensbasis = download_wissensbasis()
    thema = eintrag.get("thema", "").strip()
    unterthema_full = eintrag.get("unterthema", "").strip()
    beschreibung = eintrag.get("beschreibung", "").strip()
    inhalt = eintrag.get("inhalt", "").strip()

    if thema and unterthema_full:
        match_unterthema = re.match(r'(\d+[a-z]*)\)\s*(.*)', unterthema_full)
        if match_unterthema:
            unterthema_key = match_unterthema.group(1)
            unterthema_title = match_unterthema.group(2)
        else:
            unterthema_key = unterthema_full
            unterthema_title = ""

        unterthema_full_key = f"{unterthema_key}) {unterthema_title}"

        if thema not in wissensbasis:
            wissensbasis[thema] = {}
        if unterthema_full_key not in wissensbasis[thema]:
            wissensbasis[thema][unterthema_full_key] = {
                "beschreibung": beschreibung,
                "inhalt": []
            }
        if beschreibung:
            wissensbasis[thema][unterthema_full_key]["beschreibung"] = beschreibung
        if inhalt:
            wissensbasis[thema][unterthema_full_key]["inhalt"].append(inhalt)

        debug_print("Bearbeiten von Einträgen", f"Eintrag hinzugefügt/aktualisiert: {eintrag}")
        upload_wissensbasis(wissensbasis)

        # Pinecone: Upsert
        doc_id = f"{thema}-{unterthema_full_key}-{uuid.uuid4()}"
       
    else:
        flash("Thema und Unterthema müssen angegeben werden.", 'warning')



###########################################
# Kontakt mit OpenAI
###########################################
def contact_openai(messages, model=None):
    model = 'o3-mini'  # Changed from o3-mini-preview to o3-mini to match the model used in the chat route
    debug_print("API Calls", "contact_openai wurde aufgerufen – jetzt auf o3-mini gesetzt.")
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

def count_tokens(messages, model=None):
    model = 'o3-mini'
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


###########################################
# BigQuery Datenbezug
###########################################

def get_user_id_from_email(email):
    """
    Ruft die _id eines Benutzers aus BigQuery basierend auf seiner E-Mail-Adresse ab.
    """
    if not email:
        print("Keine E-Mail-Adresse angegeben")
        return None
        
    try:
        # Service-Account-Datei für BigQuery
        service_account_path = '/home/PfS/gcpxbixpflegehilfesenioren-a47c654480a8.json'
        if not os.path.exists(service_account_path):
            print(f"Service Account Datei nicht gefunden: {service_account_path}")
            return None
        
        client = bigquery.Client.from_service_account_json(service_account_path)
        
        # SQL-Abfrage mit Parameter
        query = """
        SELECT _id
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.proto_users`
        WHERE email = @email
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        
        print(f"Abfrage seller_id für E-Mail: {email}")
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        # Ergebnis verarbeiten
        for row in results:
            print(f"Seller-ID gefunden: {row['_id']}")
            return row['_id']
            
        print(f"Keine Seller-ID für E-Mail {email} gefunden")
        return None
    
    except Exception as e:
        print(f"Fehler beim Abrufen der seller_id: {str(e)}")
        return None

def get_bigquery_client():
    """Erstellt und gibt einen BigQuery-Client zurück."""
    service_account_path = '/home/PfS/gcpxbixpflegehilfesenioren-a47c654480a8.json'
    return bigquery.Client.from_service_account_json(service_account_path)

def get_leads_for_seller(seller_id):
    """Ruft die Leads für einen bestimmten Verkäufer aus BigQuery ab."""
    try:
        client = get_bigquery_client()
        
        query = """
        SELECT 
            l._id, 
            l.first_name,
            l.last_name,
            l.email,
            l.phone,
            l.created_at,
            l.updated_at,
            l.status
        FROM 
            `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` l
        WHERE 
            l.seller_id = @seller_id
        ORDER BY 
            l.created_at DESC
        LIMIT 5000
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        leads = []
        for row in results:
            lead = dict(row.items())
            # Konvertieren von datetime-Objekten zu Strings für JSON-Serialisierung
            for key, value in lead.items():
                if hasattr(value, 'isoformat'):
                    lead[key] = value.isoformat()
            leads.append(lead)
            
        return leads
    
    except Exception as e:
        logging.exception(f"Fehler beim Abrufen der Leads aus BigQuery: {e}")
        return []

def get_contracts_for_seller(seller_id):
    """Ruft die Verträge für einen bestimmten Verkäufer aus BigQuery ab."""
    try:
        client = get_bigquery_client()
        
        query = """
        SELECT 
            c._id,
            c.contract_number,
            c.created_at,
            c.start_date,
            c.status,
            c.customer_id,
            c.household_id
        FROM 
            `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` c
        WHERE 
            c.seller_id = @seller_id
        ORDER BY 
            c.created_at DESC
        LIMIT 1000
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        contracts = []
        for row in results:
            contract = dict(row.items())
            # Konvertieren von datetime-Objekten zu Strings für JSON-Serialisierung
            for key, value in contract.items():
                if hasattr(value, 'isoformat'):
                    contract[key] = value.isoformat()
            contracts.append(contract)
            
        return contracts
    
    except Exception as e:
        logging.exception(f"Fehler beim Abrufen der Verträge aus BigQuery: {e}")
        return []

def get_households_for_seller(seller_id):
    """Ruft die Haushalte für einen bestimmten Verkäufer aus BigQuery ab."""
    try:
        client = get_bigquery_client()
        
        query = """
        SELECT 
            h._id,
            h.address,
            h.zip,
            h.city,
            h.created_at,
            h.status
        FROM 
            `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` h
        WHERE 
            h.seller_id = @seller_id
        ORDER BY 
            h.created_at DESC
        LIMIT 1000
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        households = []
        for row in results:
            household = dict(row.items())
            # Konvertieren von datetime-Objekten zu Strings für JSON-Serialisierung
            for key, value in household.items():
                if hasattr(value, 'isoformat'):
                    household[key] = value.isoformat()
            households.append(household)
            
        return households
    
    except Exception as e:
        logging.exception(f"Fehler beim Abrufen der Haushalte aus BigQuery: {e}")
        return []

def calculate_kpis_for_seller(seller_id):
    """Berechnet KPIs für einen bestimmten Verkäufer aus BigQuery-Daten."""
    try:
        client = get_bigquery_client()
        
        query = """
        WITH 
        lead_metrics AS (
            SELECT 
                COUNT(*) AS total_leads,
                COUNTIF(status = 'converted') AS converted_leads,
                COUNTIF(DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS new_leads_30d
            FROM 
                `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads`
            WHERE 
                seller_id = @seller_id
        ),
        contract_metrics AS (
            SELECT 
                COUNT(*) AS total_contracts,
                COUNTIF(DATE(created_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)) AS new_contracts_30d,
                COUNTIF(status = 'active') AS active_contracts
            FROM 
                `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts`
            WHERE 
                seller_id = @seller_id
        ),
        household_metrics AS (
            SELECT 
                COUNT(*) AS total_households
            FROM 
                `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households`
            WHERE 
                seller_id = @seller_id
        )
        
        SELECT 
            l.total_leads,
            l.converted_leads,
            l.new_leads_30d,
            c.total_contracts,
            c.new_contracts_30d,
            c.active_contracts,
            h.total_households,
            SAFE_DIVIDE(c.total_contracts, l.total_leads) AS conversion_rate
        FROM 
            lead_metrics l,
            contract_metrics c,
            household_metrics h
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        # Es sollte nur eine Zeile geben
        for row in results:
            kpis = dict(row.items())
            return kpis
            
        return {}
    
    except Exception as e:
        logging.exception(f"Fehler beim Berechnen der KPIs aus BigQuery: {e}")
        return {}

def get_seller_data(seller_id, data_type=None):
    """
    Holt Verkäuferdaten basierend auf dem angegebenen Datentyp.
    
    Args:
        seller_id (str): Die Verkäufer-ID (_id aus proto_users)
        data_type (str, optional): Der Typ der abzurufenden Daten ('leads', 'contracts', 'households', 'kpis', oder None für alles)
    """
    result = {}
    
    if not seller_id:
        return {"error": "Keine Verkäufer-ID angegeben"}
    
    if data_type == 'leads' or data_type is None:
        result['leads'] = get_leads_for_seller(seller_id)
        
    if data_type == 'contracts' or data_type is None:
        result['contracts'] = get_contracts_for_seller(seller_id)
        
    if data_type == 'households' or data_type is None:
        result['households'] = get_households_for_seller(seller_id)
        
    if data_type == 'kpis' or data_type is None:
        result['kpis'] = calculate_kpis_for_seller(seller_id)
    
    return result

####################################
# EXTRACT INFOS FROM USER QUERY
####################################
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
        {"role": "system", "content": system_prompt},
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


####################################
# Function calling/ Tool Usage
####################################
import json
import logging
from openai import OpenAI

client = OpenAI()  # Annahme: dein API-Key ist in der Umgebung gesetzt

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
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # oder o3-mini, je nach Verfügbarkeit
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1, # Niedrig für konsistente, deterministische Antworten
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

def load_tool_config():
    """Lädt die Tool-Konfiguration aus einer YAML-Datei"""
    TOOL_CONFIG_PATH = "tool_config.yaml"
    try:
        with open(TOOL_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Fehler beim Laden der Tool-Konfiguration: {e}")
        # Einfache leere Konfiguration ohne hartcodierte Regeln
        return {
            "description": "Tool-Konfiguration für LLM-basierte Entscheidungen"
        }

def determine_query_approach(user_message, conversation_history=None):
    """
    First-layer LLM decision to determine if a query requires:
    1. Knowledge base (wissensbasis) for qualitative company/process information
    2. Function calling for customer/quantitative data access
    
    Returns:
        tuple: (approach, confidence, reasoning)
            approach: "wissensbasis" or "function_calling"
            confidence: float between 0-1 indicating confidence
            reasoning: string explaining the decision
    """
    # Create decision prompt
    prompt = f"""
    Analyze this user query and determine the most appropriate approach to answer it.
    
    User query: "{user_message}"
    
    You have three possible approaches:
    
        1. Wissensbasis (Knowledge Base) - Use this for:
        - Questions about how our company works
        - How-to guides and process questions
        - Information about our CRM system
        - General qualitative knowledge about our operations
        - Questions that don't require specific customer data or numbers
        
        2. Function Calling (Database Queries) - Use this for:
        - Questions about specific customers or customer data
        - Numerical/statistical reports (revenue, performance)
        - Contract information for specific customers
        - Care stays, lead data, or ticketing information
        - Any queries requiring real-time data from our database
        
        3. Conversational - Use this for:
        - Simple greetings or chitchat (like "Hallo", "Wie geht's?")
        - Basic calculations or questions not related to your domain
        - Requests to summarize the conversation
        - General questions that don't need specific company knowledge or data
        
        Analyze the query carefully. Determine which approach would provide the best answer.
        
        Return a JSON object with these fields:
        - "approach": Either "wissensbasis", "function_calling", or "conversational"
        - "confidence": A number between 0 and 1 indicating your confidence
        - "reasoning": A brief explanation of your decision
        """
    
    messages = [
        {"role": "system", "content": "You are a query routing assistant for a senior care services company. Respond in JSON format."},
        {"role": "user", "content": prompt}
    ]
    
    # Add relevant conversation history if available
    if conversation_history:
        context_message = "Previous conversation context:\n"
        for i, message in enumerate(conversation_history[-3:]):  # Last 3 messages
            role = message.get("role", "")
            content = message.get("content", "")
            context_message += f"{role}: {content}\n"
        
        messages.insert(1, {"role": "system", "content": context_message})
    
    # Call LLM
    try:
        response = call_llm(messages, "o3-mini")  # Using a smaller, faster model for this decision
        result = json.loads(response)
        
        approach = result.get("approach", "function_calling")  # Default to function_calling if parsing fails
        confidence = float(result.get("confidence", 0.5))
        reasoning = result.get("reasoning", "No reasoning provided")
        
        debug_print("Approach Decision", f"Determined approach: {approach} with confidence {confidence}")
        debug_print("Reasoning", reasoning)
        
        return approach, confidence, reasoning
    except Exception as e:
        logging.error(f"Error in determine_query_approach: {e}")
        # Default to function_calling as fallback
        return "function_calling", 0.3, f"Error in approach determination: {str(e)}"

def determine_function_need(user_message, query_patterns, conversation_history=None):
    """
    Second-layer LLM decision to determine if clarification is needed for function selection
    and what the best function would be.
    
    Returns:
        tuple: (needs_clarification, selected_function, possible_functions, parameters, clarification_message, reasoning)
    """
    # Create descriptions of available functions
    function_descriptions = []
    for name, details in query_patterns.items():
        function_descriptions.append({
            "name": name,
            "description": details.get("description", ""),
            "required_parameters": details.get("required_parameters", []),
            "optional_parameters": details.get("optional_parameters", [])
        })
    
    # Create prompt
    prompt = f"""
    Analyze this user query to determine if we have a clear function match or need clarification.
    
    User query: "{user_message}"
    
    Available functions:
    {json.dumps(function_descriptions, indent=2)}
    
    Your task:
    1. Determine if you can confidently select one of these functions to answer the query
    2. If yes, identify which function and what parameters can be extracted
    3. If no, identify 2-3 possible functions that might be appropriate and explain why clarification is needed
    
    Return JSON with these fields:
    - "needs_clarification": true or false
    - "selected_function": function name (if confident) or null (if clarification needed)
    - "possible_functions": array of function names (if clarification needed)
    - "extracted_parameters": object with parameter names and values that can be extracted
    - "clarification_message": suggested clarification message to user (if needed)
    - "reasoning": your thought process
    """
    
    messages = [
        {"role": "system", "content": "You are a query analysis assistant for a senior care database. Respond only with valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    # Add conversation history if available
    if conversation_history:
        context_message = "Previous conversation context:\n"
        for i, message in enumerate(conversation_history[-3:]):
            role = message.get("role", "")
            content = message.get("content", "")
            context_message += f"{role}: {content}\n"
        
        messages.insert(1, {"role": "system", "content": context_message})
    
    # Call LLM
    try:
        response = call_llm(messages)
        result = json.loads(response)
        
        needs_clarification = result.get("needs_clarification", True)
        selected_function = result.get("selected_function")
        possible_functions = result.get("possible_functions", [])
        parameters = result.get("extracted_parameters", {})
        clarification_message = result.get("clarification_message", "")
        reasoning = result.get("reasoning", "")
        
        debug_print("Function Decision", 
                   f"Needs clarification: {needs_clarification}, " 
                   f"Selected function: {selected_function}")
        
        return needs_clarification, selected_function, possible_functions, parameters, clarification_message, reasoning
    except Exception as e:
        logging.error(f"Error in determine_function_need: {e}")
        return True, None, [], {}, "I'm not sure which query to use. Could you provide more details?", f"Error: {str(e)}"

def handle_conversational_clarification(user_message, previous_clarification_data=None, conversation_history=None):
    """
    Processes a user's response to a clarification request in a conversational manner.
    
    Args:
        user_message: The user's response to the clarification request
        previous_clarification_data: Data from the previous clarification request
        conversation_history: The conversation history for better context
        
    Returns:
        tuple: (is_resolved, function_name, parameters, new_clarification_data)
            is_resolved: Whether the clarification has been resolved
            function_name: The selected function name (if resolved)
            parameters: Parameters for the function (if resolved)
            new_clarification_data: New clarification data (if not resolved)
    """
    if not previous_clarification_data:
        return False, None, {}, None
    
    possible_functions = previous_clarification_data.get("possible_functions", [])
    
    # Add conversation history context if available
    conversation_context = ""
    if conversation_history and len(conversation_history) > 0:
        recent_history = conversation_history[-3:] if len(conversation_history) > 3 else conversation_history
        conversation_context = "Recent conversation history:\n"
        for entry in recent_history:
            if "user" in entry:
                conversation_context += f"User: {entry['user']}\n"
            if "assistant" in entry:
                conversation_context += f"Assistant: {entry['assistant']}\n"
    
    # Create prompt
    prompt = f"""
    The user's original question required clarification. You asked for clarification and received a response.
    
    {conversation_context}
    
    Original question: "{previous_clarification_data.get('original_question', '')}"
    
    Your clarification request: "{previous_clarification_data.get('clarification_message', '')}"
    
    User's response: "{user_message}"
    
    Possible functions:
    {json.dumps(possible_functions, indent=2)}
    
    Given the user's response, determine:
    1. If we now have enough information to select a specific function
    2. Which function should be used (if any)
    3. What parameters can be extracted from the original question AND the clarification response
    4. If we still need more clarification, what should we ask next
    
    Return JSON with these fields:
    - "is_resolved": true or false (do we have enough information now?)
    - "selected_function": function name (if resolved) or null
    - "parameters": object with parameter names and values that can be extracted
    - "needs_further_clarification": true or false
    - "next_clarification_message": what to ask if still need clarification
    - "reasoning": your thought process
    """
    
    messages = [
        {"role": "system", "content": "You are a clarification assistant for a senior care database. Respond only with valid JSON."},
        {"role": "user", "content": prompt}
    ]
    
    # Call LLM
    try:
        response = call_llm(messages)
        result = json.loads(response)
        
        is_resolved = result.get("is_resolved", False)
        selected_function = result.get("selected_function")
        parameters = result.get("parameters", {})
        needs_further_clarification = result.get("needs_further_clarification", True)
        next_clarification = result.get("next_clarification_message", "")
        reasoning = result.get("reasoning", "")
        
        debug_print("Clarification Processing", 
                   f"Resolved: {is_resolved}, Function: {selected_function}, " 
                   f"Needs more: {needs_further_clarification}")
        
        if is_resolved:
            return True, selected_function, parameters, None
        else:
            # Create new clarification data
            new_clarification_data = {
                "original_question": previous_clarification_data.get("original_question", ""),
                "clarification_message": next_clarification,
                "possible_functions": possible_functions,
                "previous_response": user_message
            }
            return False, None, {}, new_clarification_data
            
    except Exception as e:
        logging.error(f"Error in handle_conversational_clarification: {e}")
        return False, None, {}, None

def call_llm(messages, model="o3-mini", conversation_history=None):
    """
    Verbesserte LLM-Aufruf-Funktion mit Konversationshistorie.
    Diese sollte die bestehende call_llm Funktion in app.py ersetzen.
    """
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
    
    # Integration in bestehende OpenAI-Aufrufe
    try:
        response = openai.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.4  # Niedrigere Temperatur für präzisere Antworten
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Fehler beim Aufrufen des LLM: {e}")
        return None

def process_user_query(user_message, session_data):
    """
    Verbesserte Version der process_user_query Funktion mit Konversationshistorie.
    Diese sollte die bestehende process_user_query Funktion in app.py ersetzen.
    """
    
    conversation_history = session_data.get("conversation_history", [])
    
    # Check if there's an ongoing clarification dialog
    if session.get("clarification_in_progress"):
        clarification_data = session.get("clarification_data", {})
        debug_print("Clarification", "Processing response to clarification")
        
        # Check if this is a text-based clarification
        if clarification_data.get("clarification_type") == "text_clarification":
            debug_print("Clarification", "Processing text-based clarification")
            
            # Use our new text-based processing function from query_selector
            original_question = clarification_data.get("original_question", "")
            clarification_context = clarification_data.get("clarification_context", {})
            
            # Import the new function if needed
            from query_selector import process_text_clarification_response
            
            # Process the user's text response - PASS CONVERSATION HISTORY
            function_name, parameters = process_text_clarification_response(
                clarification_context,
                user_message,
                original_question,
                conversation_history  # Pass the conversation history
            )
            
            # Clean up clarification state
            session.pop("clarification_in_progress", None)
            session.pop("clarification_data", None)
            
            # Mark as resolved with the function and parameters from text processing
            is_resolved = True
            new_clarification_data = None
        else:
            # Legacy button-based or conversational clarification
            is_resolved, function_name, parameters, new_clarification_data = handle_conversational_clarification(
                user_message, clarification_data, conversation_history  # Pass conversation history here too
            )
        
        if is_resolved:
            # Clarification resolved, continue with function execution
            debug_print("Clarification", f"Resolved: using function {function_name}")
            session.pop("clarification_in_progress", None)
            session.pop("clarification_data", None)
            
            # Add standard parameters
            if "seller_id" in parameters and "seller_id" in session_data:
                parameters["seller_id"] = session_data.get("seller_id")
            
            # Execute function
            debug_print("Tool", f"Führe Tool aus: {function_name} mit Parametern: {parameters}")
            tool_result = handle_function_call(function_name, parameters)
            
            # SCHRITT 4: Spezialbehandlung für bestimmte Abfragen
            formatted_result = None
            try:
                if function_name == "get_customer_history":
                    formatted_result = format_customer_details(json.loads(tool_result))
                    debug_print("Antwort", "Kunde-Historie formatiert")
            except Exception as format_error:
                debug_print("Antwort", f"Fehler bei der Formatierung: {format_error}")
            
            # SCHRITT 5: Antwort generieren
            try:
                # Wenn bereits eine formatierte Antwort vorliegt, nutze diese
                if formatted_result:
                    # Update conversation history before returning
                    session_data = conversation_manager.update_conversation(
                        session_data, 
                        user_message, 
                        formatted_result, 
                        {"name": function_name, "content": tool_result}
                    )
                    return formatted_result
                
                # Andernfalls erstelle einen angepassten System-Prompt für die LLM-Antwort
                system_prompt = create_enhanced_system_prompt(function_name, conversation_history)
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "function", "name": function_name, "content": tool_result}
                ]
                
                # Use conversation history for better context
                response = openai.chat.completions.create(
                    model="o3-mini",
                    messages=messages,
                    temperature=0.4  # Niedrigere Temperatur für präzisere Antworten
                )
                
                final_response = response.choices[0].message.content
                
                # Update conversation history with this interaction
                session_data = conversation_manager.update_conversation(
                    session_data, 
                    user_message, 
                    final_response, 
                    {"name": function_name, "content": tool_result}
                )
                
                debug_print("Antwort", f"Antwort generiert (gekürzt): {final_response[:100]}...")
                return final_response
            except Exception as e:
                # Fallback antwort
                debug_print("Antwort", f"Fehler bei der Antwortgenerierung: {e}")
                fallback = generate_fallback_response(function_name, tool_result)
                
                # Still update conversation history with fallback
                session_data = conversation_manager.update_conversation(
                    session_data, 
                    user_message, 
                    fallback, 
                    {"name": function_name, "content": tool_result}
                )
                
                return fallback
        else:
            # Need more clarification
            session["clarification_data"] = new_clarification_data
            
            # Update conversation history with this clarification
            session_data = conversation_manager.update_conversation(
                session_data, 
                user_message, 
                new_clarification_data["clarification_message"]
            )
            
            return new_clarification_data["clarification_message"]
    
    # Aktuelles Datum für zeitliche Anfragen
    current_date = datetime.now()
    current_date_str = current_date.strftime("%Y-%m-%d")
    
    # Füge das aktuelle Datum zu Session-Daten hinzu
    session_data["current_date"] = current_date_str
    
    debug_print("Anfrage", f"Verarbeite Anfrage: '{user_message}'")
    
    # STEP 1: Determine if this query requires wissensbasis or function calling
    approach, confidence, reasoning = determine_query_approach(user_message, conversation_history)
    
    # STEP 2: Process based on the determined approach
    if approach == "wissensbasis":
        debug_print("Approach", "Using wissensbasis for this query")
        
        # Only load wissensbasis when needed
        wissensbasis_data = download_wissensbasis()
        
        # Process with wissensbasis
        try:
            # Create wissensbasis prompt
            system_prompt = """
            Du bist ein hilfreicher Assistent für ein Pflegevermittlungsunternehmen. 
            Beantworte die Frage basierend auf der bereitgestellten Wissensbasis.
            Sei klar, präzise und sachlich. Wenn du die Antwort nicht in der Wissensbasis findest, 
            sage ehrlich, dass du es nicht weißt.
            """
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Wissensbasis: {wissensbasis_data}\n\nFrage: {user_message}"}
            ]
            
            response = openai.chat.completions.create(
                model="gpt-4o",  # Using a more capable model for knowledge-based queries
                messages=messages,
                temperature=0.3
            )
            
            final_response = response.choices[0].message.content
            debug_print("Antwort", f"Wissensbasis-Antwort generiert (gekürzt): {final_response[:100]}...")

            session_data = conversation_manager.update_conversation(
                session_data, 
                user_message, 
                final_response
            )
            return final_response
        except Exception as e:
            debug_print("Antwort", f"Fehler bei der Wissensbasis-Antwortgenerierung: {e}")
            return "Es ist ein Fehler bei der Verarbeitung Ihrer Anfrage mit der Wissensbasis aufgetreten. Bitte versuchen Sie es später erneut."
    
    elif approach == "conversational":
        debug_print("Approach", "Using conversational approach for this query")
        
        try:
            # Create a simple conversational prompt
            system_prompt = """
            Du bist Xora, ein freundlicher Assistent für ein Pflegevermittlungsunternehmen.
            Beantworte einfache Fragen klar und präzise.
            Du kannst auf allgemeine Fragen antworten, aber verweise bei spezifischen Fragen zum Unternehmen
            oder zu Kundendaten auf deine Wissensbasis oder Datenbank-Funktionen.
            """
            
            # Prepare conversation context from history
            conversation_context = ""
            if conversation_history and len(conversation_history) > 0:
                recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
                for entry in recent_history:
                    if "user" in entry:
                        conversation_context += f"Benutzer: {entry['user']}\n"
                    if "assistant" in entry:
                        conversation_context += f"Assistent: {entry['assistant']}\n"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"Konversationskontext:\n{conversation_context}"},
                {"role": "user", "content": user_message}
            ]
            
            response = openai.chat.completions.create(
                model="o3-mini",  # Using a smaller model for conversational responses
                messages=messages,
                temperature=0.7  # Slightly higher temperature for more natural responses
            )
            
            final_response = response.choices[0].message.content
            debug_print("Antwort", f"Konversation-Antwort generiert (gekürzt): {final_response[:100]}...")
            
            session_data = conversation_manager.update_conversation(
                session_data, 
                user_message, 
                final_response
            )
            return final_response
        except Exception as e:
            debug_print("Antwort", f"Fehler bei der Konversation-Antwortgenerierung: {e}")
            return "Es tut mir leid, ich konnte deine Frage nicht richtig verarbeiten. Wie kann ich dir sonst helfen?"
    
    else:
        debug_print("Approach", "Using function calling for this query")
        
        # Load query patterns
        query_patterns = {}
        try:
            with open("query_patterns.json", "r", encoding="utf-8") as f:
                content = f.read()
                json_start = content.find('{')
                if json_start >= 0:
                    content = content[json_start:]
                    query_data = json.loads(content)
                    query_patterns = query_data.get("common_queries", {})
        except Exception as e:
            debug_print("Parameter", f"Fehler beim Laden der query_patterns.json: {e}")
        
        # STEP 3: Determine if we need clarification for function selection
        needs_clarification, selected_function, possible_functions, parameters, clarification_message, reasoning = (
            determine_function_need(user_message, query_patterns, conversation_history)
        )
        
        if needs_clarification:
            # Start a conversational clarification process
            debug_print("Clarification", "Starting text-based clarification dialog")
            
            # Prepare options list for context
            function_options = []
            query_mapping = {}
            
            for func_name in possible_functions:
                if func_name in query_patterns:
                    desc = query_patterns[func_name].get("description", func_name)
                    function_options.append({"name": func_name, "description": desc})
                    # Build mapping for text matching later
                    query_mapping[desc.lower()] = func_name
            
            # Prepare context for text-based clarification
            clarification_context = {
                "clarification_type": "query_selection",
                "original_parameters": parameters.copy(),
                "query_mapping": query_mapping
            }
            
            # Store clarification state for conversational context
            clarification_data = {
                "original_question": user_message,
                "clarification_message": clarification_message,
                "clarification_context": clarification_context,
                "clarification_type": "text_clarification"  # Mark as text-based
            }
            
            session["clarification_in_progress"] = True
            session["clarification_data"] = clarification_data
            
            # Format clarification message in a conversation-friendly way
            options_text = []
            for option in function_options:
                options_text.append(f"'{option['description']}'")
                
            # Create a natural language list: 'A', 'B' and 'C'
            if len(options_text) > 1:
                formatted_options = ", ".join(options_text[:-1]) + " oder " + options_text[-1]
            else:
                formatted_options = options_text[0]
                
            clarification_message += f" Möchtest du {formatted_options}?"
            
            return clarification_message
        else:
            # We have a clear function to call
            debug_print("Function Call", f"Selected function: {selected_function}")
            
            # Add standard parameters
            if "seller_id" in parameters and "seller_id" in session_data:
                parameters["seller_id"] = session_data.get("seller_id")
            
            # Fill in missing parameters using existing methods if needed
            if selected_function in query_patterns:
                # Add date parameters for time-based queries
                if selected_function in ["get_monthly_performance", "get_care_stays_by_date_range"] and "monat" in user_message.lower():
                    date_params = extract_enhanced_date_params(user_message)
                    if date_params and "start_date" in date_params and "end_date" in date_params:
                        parameters.update(date_params)
                        if selected_function == "get_care_stays_by_date_range":
                            parameters["filter_type"] = "active"
                
                # Add default values
                defaults = query_patterns[selected_function].get("default_values", {})
                for param, value in defaults.items():
                    if param not in parameters:
                        parameters[param] = value
                
                # Handle missing required parameters
                required_params = query_patterns[selected_function].get("required_parameters", [])
                missing_params = [p for p in required_params if p not in parameters]
                
                if missing_params:
                    # Standard handling for common missing parameters
                    if missing_params == ["seller_id"] and "seller_id" not in parameters:
                        parameters["seller_id"] = "62d00b56a384fd908f7f5a6c"  # Default value
                    elif missing_params == ["start_date", "end_date"] or "start_date" in missing_params or "end_date" in missing_params:
                        # Current month as default timeframe
                        month_start = datetime(current_date.year, current_date.month, 1)
                        if current_date.month == 12:
                            month_end = datetime(current_date.year, 12, 31)
                        else:
                            next_month = datetime(current_date.year, current_date.month + 1, 1)
                            month_end = next_month - timedelta(days=1)
                        
                        parameters["start_date"] = month_start.strftime("%Y-%m-%d")
                        parameters["end_date"] = month_end.strftime("%Y-%m-%d")
                    else:
                        # Try to extract missing parameters with LLM
                        llm_params = extract_parameters_with_llm(user_message, selected_function, missing_params)
                        parameters.update(llm_params)
            
            # Execute function
            debug_print("Tool", f"Führe Tool aus: {selected_function} mit Parametern: {parameters}")
            try:
                tool_result = handle_function_call(selected_function, parameters)
                
                # Try to parse result for better logs
                try:
                    parsed_result = json.loads(tool_result)
                    status = parsed_result.get("status", "unknown")
                    data_count = len(parsed_result.get("data", [])) if "data" in parsed_result else 0
                    debug_print("Tool", f"Tool-Ausführung erfolgreich: Status={status}, Datensätze={data_count}")
                except:
                    debug_print("Tool", "Tool-Ausführung erfolgreich, aber Ergebnis konnte nicht geparst werden")
            except Exception as e:
                debug_print("Tool", f"Fehler bei der Tool-Ausführung: {e}")
                return (f"Bei der Verarbeitung Ihrer Anfrage ist ein Fehler aufgetreten. "
                        f"Bitte versuchen Sie es erneut oder formulieren Sie Ihre Anfrage anders.")
            
            # SCHRITT 4: Spezialbehandlung für bestimmte Abfragen
            formatted_result = None
            try:
                if selected_function == "get_customer_history":
                    formatted_result = format_customer_details(json.loads(tool_result))
                    debug_print("Antwort", "Kunde-Historie formatiert")
            except Exception as format_error:
                debug_print("Antwort", f"Fehler bei der Formatierung: {format_error}")
            
            # SCHRITT 5: Antwort generieren
            try:
                # Wenn bereits eine formatierte Antwort vorliegt, nutze diese
                if formatted_result:
                    # Add this block here
                    session_data = conversation_manager.update_conversation(
                        session_data, 
                        user_message, 
                        formatted_result,
                        {"name": selected_function, "content": tool_result}
                    )
                    return formatted_result
                
                # Andernfalls erstelle einen angepassten System-Prompt für die LLM-Antwort
                system_prompt = create_enhanced_system_prompt(selected_function, conversation_history)
                
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "function", "name": selected_function, "content": tool_result}
                ]
                
                response = openai.chat.completions.create(
                    model="o3-mini",
                    messages=messages,
                    temperature=0.4  # Niedrigere Temperatur für präzisere Antworten
                )
                
                final_response = response.choices[0].message.content
                debug_print("Antwort", f"Antwort generiert (gekürzt): {final_response[:100]}...")
                session_data = conversation_manager.update_conversation(
                    session_data, 
                    user_message, 
                    final_response,
                    {"name": selected_function, "content": tool_result}
                )
                return final_response
            except Exception as e:
                debug_print("Antwort", f"Fehler bei der Antwortgenerierung: {e}")
                fallback_response = generate_fallback_response(selected_function, tool_result)

                # Add this block here
                session_data = conversation_manager.update_conversation(
                    session_data, 
                    user_message, 
                    fallback_response,
                    {"name": selected_function, "content": tool_result}
                )

                return fallback_response
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
    base_prompt = """
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
    
    Heutiges Datum: """ + datetime.now().strftime("%d.%m.%Y")
    
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

def format_simple_results(data_list):
    """Formatiert einfache Ergebnisse für Fallback-Antworten"""
    if not data_list:
        return "Keine Daten"
    
    result = []
    for item in data_list:
        try:
            # Versuche, häufig vorkommende Eigenschaften zu formatieren
            parts = []
            if "first_name" in item and "last_name" in item:
                parts.append(f"{item['first_name']} {item['last_name']}")
            if "agency_name" in item:
                parts.append(f"Agentur: {item['agency_name']}")
            if "bill_start" in item and "bill_end" in item:
                parts.append(f"Zeitraum: {format_date(item['bill_start'])} bis {format_date(item['bill_end'])}")
            if "prov_seller" in item:
                parts.append(f"Provision: {item['prov_seller']}€")
            
            if parts:
                result.append(" | ".join(parts))
            else:
                # Fallback: Zeige die ersten paar Eigenschaften
                simple_parts = []
                count = 0
                for key, value in item.items():
                    if count < 3 and key not in ["_id", "cs_id", "contract_id", "lead_id"]:
                        simple_parts.append(f"{key}: {value}")
                        count += 1
                result.append(" | ".join(simple_parts))
        except:
            # Bei Fehlern: Vereinfacht darstellen
            result.append(str(item)[:100] + "...")
    
    return "\n".join(result)

def create_function_definitions():
    """
    Erstellt die Function-Definitionen für OpenAI's Function-Calling basierend auf 
    den definierten Abfragemustern.
    
    Returns:
        list: Eine Liste von Function-Definitionen im Format, das von OpenAI erwartet wird
    """
    # Lade das JSON-Schema für Abfragemuster
    with open('query_patterns.json', 'r', encoding='utf-8') as f:
        query_patterns = json.load(f)
    
    tools = []
    
    # Erstelle für jedes Abfragemuster eine Funktion
    for query_name, query_info in query_patterns['common_queries'].items():
        function_def = {
            "type": "function",
            "function": {
                "name": query_name,
                "description": query_info['description'],
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": query_info['required_parameters']
                }
            }
        }
        
        # Füge Parameter hinzu
        for param in query_info['required_parameters'] + query_info.get('optional_parameters', []):
            # Bestimme den Typ des Parameters basierend auf Namen (Heuristik)
            param_type = "string"
            if "id" in param:
                param_type = "string"
            elif "limit" in param or "count" in param or "_back" in param:
                param_type = "integer"
            elif "date" in param or "time" in param:
                param_type = "string"  # Datum als String, wird später konvertiert
            elif param == "contacted":
                param_type = "boolean"
            
            # Bestimme die Beschreibung des Parameters
            param_desc = f"Parameter {param} für die Abfrage"
            if param == "seller_id":
                param_desc = "Die ID des Verkäufers, dessen Daten abgefragt werden sollen"
            elif param == "lead_id":
                param_desc = "Die ID des Leads, dessen Daten abgefragt werden sollen"
            elif param == "limit":
                param_desc = "Maximale Anzahl der zurückzugebenden Datensätze"
            
            # Füge Parameter zur Funktionsdefinition hinzu
            function_def["function"]["parameters"]["properties"][param] = {
                "type": param_type,
                "description": param_desc
            }
            
            # Füge Enumerationen für bestimmte Parameter hinzu
            if param == "ticketable_type":
                function_def["function"]["parameters"]["properties"][param]["enum"] = [
                    "Lead", "Contract", "CareStay", "Visor", "Posting"
                ]
        
        tools.append(function_def)
    
    return tools

def stream_text_response(response_text, user_message, session_data):
    """
    Generiert einen Stream für direkte Textantworten (z.B. Wissensbasis-Antworten)
    """
    try:
        # Debug-Events für die Verbindungsdiagnose
        yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream-Start (Text Response)'})}\n\n"
        
        # Stream-Start
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        # Teile die Antwort in Chunks auf für ein natürlicheres Streaming-Gefühl
        chunk_size = 15  # Anzahl der Wörter pro Chunk
        words = response_text.split()
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            yield f"data: {json.dumps({'type': 'text', 'content': chunk + ' '})}\n\n"
            time.sleep(0.05)  # Kleine Verzögerung für natürlichere Ausgabe
        
        # Stream beenden
        yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': response_text})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        logging.exception("Fehler im Text-Stream")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': 'Es ist ein Fehler aufgetreten.'})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

def generate_conversational_clarification_stream(clarification_data):
    """
    Generiert einen Stream für konversationelle Rückfragen ohne Buttons
    """
    try:
        yield f"data: {json.dumps({'type': 'clarification_start'})}\n\n"
        
        # Sende die Rückfrage als normalen Text
        message = clarification_data.get("clarification_message", "Bitte präzisiere deine Anfrage")
        yield f"data: {json.dumps({'type': 'text', 'content': message})}\n\n"
        
        # Wir verwenden keine Button-Optionen mehr, sondern erwarten eine natürliche Antwort
        yield f"data: {json.dumps({'type': 'complete', 'user': clarification_data.get('original_question', ''), 'bot': message})}\n\n"
        yield f"data: {json.dumps({'type': 'conversational_clarification_mode'})}\n\n"
        
        yield f"data: {json.dumps({'type': 'clarification_end'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler bei Rückfrage: {str(e)}'})}\n\n"

def generate_clarification_stream(human_in_loop_data):
    """
    Generiert einen Stream für text-basierte Rückfragen (ohne Buttons)
    """
    try:
        yield f"data: {json.dumps({'type': 'text_clarification_start'})}\n\n"
        
        # Send the clarification question as regular text - no need for buttons
        message = human_in_loop_data.get("message", "Bitte präzisiere deine Anfrage")
        
        # Split the options out of the message if present
        # This ensures the client can directly display the message text
        yield f"data: {json.dumps({'type': 'text', 'content': message})}\n\n"
        
        # Signal that this is the end of this message - client will render it as normal text
        yield f"data: {json.dumps({'type': 'text_clarification_end'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler bei Rückfrage: {str(e)}'})}\n\n"

def stream_response(messages, tools, tool_choice, seller_id, extracted_args, user_message, session_data):
    """Stream the OpenAI response and handle function calls within the stream
    
    Args:
        messages: OpenAI message array
        tools: Available tools/functions
        tool_choice: Which tool to use
        seller_id: The seller's ID
        extracted_args: Any extracted date parameters
        user_message: The original user message
        session_data: A dictionary containing all needed session data
    """
    # Extract session data - this avoids accessing session in the generator
    user_id = session_data["user_id"]
    user_name = session_data["user_name"]
    chat_key = session_data["chat_key"]
    chat_history = session_data["chat_history"]
    
    try:
        # Debug-Events für die Verbindungsdiagnose
        yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream-Start'})}\n\n"
        #yield f"data: {json.dumps({'type': 'text', 'content': 'Test-Content vom Server'})}\n\n"

        debug_print("API Calls", f"Streaming-Anfrage an OpenAI mit Function Calling")
        response = openai.chat.completions.create(
            model="o3-mini",
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            stream=True  # Enable streaming
        )
        
        initial_response = ""
        function_calls_data = []
        has_function_calls = False
        
        # Stream the initial response
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                text_chunk = chunk.choices[0].delta.content
                initial_response += text_chunk
                yield f"data: {json.dumps({'type': 'text', 'content': text_chunk})}\n\n"
            
            # Check if this chunk contains function call info
            if hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                has_function_calls = True
                # Collect function call data
                for tool_call in chunk.choices[0].delta.tool_calls:
                    tool_index = tool_call.index
                    
                    # Initialize the tool call if needed
                    while len(function_calls_data) <= tool_index:
                        function_calls_data.append({"id": str(tool_index), "name": "", "args": ""})
                    
                    if hasattr(tool_call, 'function'):
                        if hasattr(tool_call.function, 'name') and tool_call.function.name:
                            function_calls_data[tool_index]["name"] = tool_call.function.name
                        
                        if hasattr(tool_call.function, 'arguments') and tool_call.function.arguments:
                            function_calls_data[tool_index]["args"] += tool_call.function.arguments
        
        # If function calls detected, execute them
        if has_function_calls:
            yield f"data: {json.dumps({'type': 'function_call_start'})}\n\n"
            yield f"data: {json.dumps({'type': 'debug', 'message': f'Detected {len(function_calls_data)} function calls'})}\n\n"
            
            function_responses = []
            for func_data in function_calls_data:
                if func_data["name"] and func_data["args"]:
                    try:
                        function_name = func_data["name"]
                        function_args = json.loads(func_data["args"])
                        
                        # Add seller_id and extracted date parameters
                        if seller_id:
                            function_args["seller_id"] = seller_id
                        
                        for key, value in extracted_args.items():
                            if key not in function_args or not function_args[key]:
                                function_args[key] = value
                        
                        # Execute the function
                        debug_print("Function", f"Streaming: Executing {function_name} with args {function_args}")
                        yield f"data: {json.dumps({'type': 'debug', 'message': f'Executing function {function_name}'})}\n\n"
                        
                        function_response = handle_function_call(function_name, function_args)
                        
                        # Add to function responses
                        function_responses.append({
                            "role": "tool",
                            "tool_call_id": func_data["id"],
                            "content": function_response
                        })
                        
                        yield f"data: {json.dumps({'type': 'function_result', 'name': function_name})}\n\n"
                        yield f"data: {json.dumps({'type': 'debug', 'message': f'Function executed successfully'})}\n\n"
                        
                    except Exception as e:
                        debug_print("Function", f"Error executing function: {str(e)}")
                        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler bei Funktionsausführung: {str(e)}'})}\n\n"
            
            # Second call to get final response
            if function_responses:
                # Properly format the tool_calls with the required 'type' field
                formatted_tool_calls = []
                for func_data in function_calls_data:
                    formatted_tool_calls.append({
                        "type": "function",  # This is the required field
                        "id": func_data["id"],
                        "function": {
                            "name": func_data["name"],
                            "arguments": func_data["args"]
                        }
                    })
                
                # Create the second messages with properly formatted tool_calls
                second_messages = messages + [{
                    "role": "assistant", 
                    "content": initial_response,
                    "tool_calls": formatted_tool_calls
                }] + function_responses

                # Debug vor dem zweiten API-Call
                yield f"data: {json.dumps({'type': 'debug', 'message': 'Preparing for second API call'})}\n\n"
                
                # WICHTIG: Final response start event - stelle sicher, dass es gesendet wird
                yield f"data: {json.dumps({'type': 'final_response_start'})}\n\n"
                
                # Initiiere den zweiten API-Call
                yield f"data: {json.dumps({'type': 'debug', 'message': 'Starting second API call'})}\n\n"
                
                try:
                    final_response = openai.chat.completions.create(
                        model="o3-mini",
                        messages=second_messages,
                        stream=True
                    )
                    
                    yield f"data: {json.dumps({'type': 'debug', 'message': 'Second API call initiated'})}\n\n"
                    
                    final_text = ""
                    for chunk in final_response:
                        if chunk.choices[0].delta.content:
                            text_chunk = chunk.choices[0].delta.content
                            final_text += text_chunk
                            yield f"data: {json.dumps({'type': 'text', 'content': text_chunk})}\n\n"
                    
                    # Vollständige Antwort zusammenstellen
                    full_response = initial_response + "\n\n" + final_text
                    
                    # Session aktualisieren und Stream beenden
                    yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': full_response})}\n\n"
                    yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream complete with function execution'})}\n\n"
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
                    
                except Exception as e:
                    debug_print("API Calls", f"Error in second call: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler beim zweiten API-Call: {str(e)}'})}\n\n"
                    # Trotz Fehler die Session aktualisieren
                    yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': initial_response})}\n\n"
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
            else:
                # No valid function responses, just save initial response
                yield f"data: {json.dumps({'type': 'debug', 'message': 'Function execution produced no valid responses'})}\n\n"
                yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': initial_response})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
        else:
            # No function calls, just save initial response
            yield f"data: {json.dumps({'type': 'debug', 'message': 'No function calls detected'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': initial_response})}\n\n"
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
    
    except Exception as e:
        logging.exception("Fehler im Stream")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler: {str(e)}'})}\n\n"
        # Auch bei Fehler versuchen, Stream ordnungsgemäß zu beenden
        yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': 'Es ist ein Fehler aufgetreten.'})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"    

@app.route("/clarify", methods=["POST"])
def handle_clarification():
    """
    Verarbeitet die Antwort auf eine Rückfrage - unterstützt sowohl Legacy Button-Modus als auch
    neue konversationelle Rückfragen
    """
    try:
        # Stellen wir sicher, dass eine Benutzer-Session existiert
        if not session.get("user_id"):
            logging.warning("Clarification-Anfrage ohne aktive Benutzer-Session")
            return jsonify({"error": "Keine aktive Benutzer-Session gefunden"}), 400
        
        # Für AJAX-Anfragen
        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
        
        # Debug-Informationen
        logging.info(f"Verarbeite Clarification-Antwort, AJAX: {is_ajax}")
        
        # Prüfen, ob wir im konversationellen oder Button-Modus sind
        conversational_mode = session.get("clarification_in_progress", False)
        
        if conversational_mode:
            # Konversationeller Modus: Antwort als natürlichen Text behandeln
            user_message = request.form.get("message", "").strip()
            
            if not user_message:
                error_msg = "Keine Antwort auf die Rückfrage angegeben"
                logging.error(error_msg)
                if is_ajax:
                    return jsonify({"error": error_msg}), 400
                flash(error_msg, "warning")
                return redirect(url_for("chat"))
            
            # Benutzerantwort wird in der normalen Chat-Route verarbeitet
            # Wir senden eine Erfolgsmeldung zurück, da die Verarbeitung im Chat-Handler erfolgt
            if is_ajax:
                return jsonify({"success": True, "message": "Antwort wird verarbeitet"})
            return redirect(url_for("chat"))
        
        # Legacy Button-Modus
        try:
            # Lese die Option aus dem Formular
            selected_option_index = int(request.form.get("option_index", "0"))
            logging.info(f"Ausgewählter Options-Index: {selected_option_index}")
        except ValueError:
            error_msg = "Ungültiger Options-Index Format (keine Zahl)"
            logging.error(f"Fehler beim Parsen des Options-Index: {request.form.get('option_index')}")
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat"))
            
        # Prüfe, ob die Human-in-Loop-Daten in der Session vorhanden sind
        human_in_loop_data = session.get("human_in_loop_data")
        
        # Logge die vorhandenen Session-Daten für Debugging
        session_keys = list(session.keys())
        logging.debug(f"Verfügbare Session-Keys: {session_keys}")
        
        if not human_in_loop_data:
            error_msg = "Keine Rückfrage-Daten in der Session gefunden"
            logging.error(error_msg)
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat"))
            
        if "options" not in human_in_loop_data:
            error_msg = "Ungültige Rückfrage-Daten: Keine Optionen vorhanden"
            logging.error(f"human_in_loop_data ohne 'options': {human_in_loop_data}")
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat"))
            
        options = human_in_loop_data.get("options", [])
        logging.info(f"Anzahl verfügbarer Optionen: {len(options)}")
        
        # Prüfe, ob der Index gültig ist
        if selected_option_index < 0 or selected_option_index >= len(options):
            error_msg = f"Ungültiger Options-Index: {selected_option_index} (max: {len(options)-1})"
            logging.error(error_msg)
            if is_ajax:
                return jsonify({"error": error_msg}), 400
            flash(error_msg, "danger")
            return redirect(url_for("chat"))
            
        # Hole ausgewählte Option
        selected_option = options[selected_option_index]
        logging.info(f"Ausgewählte Option: {selected_option.get('text')} -> {selected_option.get('query')}")
        
        # Verarbeiten von Parametern, speziell für den Kunden Küll
        params = selected_option.get("params", {})
        if params and "customer_name" in params:
            customer_name = params["customer_name"]
            if customer_name.lower() in ["küll", "kull", "kühl", "kuehl", "kuell"]:
                logging.info("Normalisiere Kunden-Parameter 'Küll'")
                params["customer_name"] = "Küll"
                selected_option["params"] = params

        # Extrahiere die benötigten Informationen
        selected_query = selected_option.get("query")
        selected_params = selected_option.get("params", {})
        
        # Verarbeitung direkt hier für Kundenabfragen
        if selected_query == "get_customer_history" and "customer_name" in selected_params:
            try:
                # Kundenname extrahieren
                customer_name = selected_params.get("customer_name")
                
                # seller_id aus der Session hinzufügen
                if "seller_id" in session:
                    selected_params["seller_id"] = session.get("seller_id")
                
                logging.info(f"Führe direkt get_customer_history für '{customer_name}' aus")
                
                # Funktion direkt aufrufen
                result = handle_function_call(selected_query, selected_params)
                result_data = json.loads(result)
                
                # Ergebnis formatieren und den Chat-Verlauf aktualisieren
                if "data" in result_data and len(result_data["data"]) > 0:
                    formatted_result = format_customer_details(result_data)
                    
                    # Original-Anfrage holen
                    original_request = session.get("human_in_loop_original_request", "")
                    
                    # Chat-History aktualisieren
                    chat_key = f"chat_history_{session.get('user_id')}"
                    chat_history = session.get(chat_key, [])
                    
                    # Benutzeranfrage und Antwort hinzufügen
                    chat_history.append({"role": "user", "content": original_request})
                    chat_history.append({"role": "assistant", "content": formatted_result})
                    session[chat_key] = chat_history
                    
                    # Erfolg zurückgeben
                    if is_ajax:
                        return jsonify({
                            "success": True, 
                            "response": formatted_result,
                            "message": "Kundeninformationen erfolgreich abgerufen."
                        })
                    else:
                        # Bei normaler Anfrage: Flash-Nachricht und Weiterleitung
                        flash("Kundeninformationen erfolgreich abgerufen.", "success")
                        # WICHTIG: Antwort in der Session speichern für die Anzeige
                        session["last_response"] = formatted_result
                        session.modified = True
                        return redirect(url_for("chat"))
                else:
                    # Keine Daten gefunden
                    error_msg = f"Keine Daten für Kunde '{customer_name}' gefunden."
                    if is_ajax:
                        return jsonify({"error": error_msg})
                    flash(error_msg, "warning")
                    return redirect(url_for("chat"))
            
            except Exception as e:
                logging.error(f"Fehler bei direkter Kundenanfrage: {str(e)}")
                if is_ajax:
                    return jsonify({"error": str(e)})
                flash(f"Fehler bei der Verarbeitung: {str(e)}", "danger")
                return redirect(url_for("chat"))
        
        # Für andere Anfragen: in Session speichern für nächsten Request
        session["human_in_loop_clarification_response"] = selected_option
        
        # Speichere den original request für die Kontext-Kontinuität
        if "human_in_loop_original_request" in session:
            original_request = session.get("human_in_loop_original_request")
            session["pending_query"] = original_request
            logging.info(f"Original-Anfrage gespeichert: {original_request}")
        else:
            logging.warning("Keine Original-Anfrage in der Session gefunden")
        
        # Entferne die Human-in-the-Loop-Daten aus der Session
        session.pop("human_in_loop_data", None)
        session.pop("human_in_loop_original_request", None)
        
        # Stelle sicher, dass der Chatverlauf erhalten bleibt
        session.modified = True
        
        # Bei AJAX-Anfragen mehr Informationen zurückgeben für clientseitige Verarbeitung
        if is_ajax:
            logging.info("Sende AJAX-Erfolgsantwort mit Option")
            # Hier nehmen wir an, dass im nächsten Request eine Antwort erstellt wird
            # Daher senden wir ein Signal an die Client-Seite, dass es eine Anfrage gab,
            # die beim nächsten Request beantwortet wird (im GET handler der chat route)
            return jsonify({
                "success": True, 
                "message": "Option ausgewählt",
                "selected_option": selected_option.get("text", ""),
                "query": selected_query,
                "need_followup": True
            })
        
        # Ansonsten wie gehabt weiterleiten
        logging.info("Weiterleitung zur Chat-Seite")
        return redirect(url_for("chat"))
    except Exception as e:
        # Allgemeine Fehlerbehandlung
        error_msg = f"Fehler bei der Verarbeitung der Rückfrage: {str(e)}"
        logging.exception("Unerwarteter Fehler bei der Verarbeitung der Rückfrage")
        
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": error_msg, "success": False}), 500
            
        flash(error_msg, "danger")
        return redirect(url_for("chat"))
        
    except Exception as e:
        logging.error(f"Fehler bei der Verarbeitung der Rückfrage: {e}")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": str(e)}), 500
        flash(f"Ein Fehler ist aufgetreten: {str(e)}", "danger")
        return redirect(url_for("chat"))

@app.route("/", methods=["GET", "POST"])
def chat():
    try:
        user_id = session.get("user_id")
        user_name = session.get("user_name")

        if not user_name:
            return redirect(url_for("google_login"))

        seller_id = session.get("seller_id")
        if not seller_id and session.get("email"):
            seller_id = get_user_id_from_email(session.get("email"))
            if seller_id:
                session["seller_id"] = seller_id
                session.modified = True

        chat_key = f"chat_history_{user_id}"
        if chat_key not in session:
            session[chat_key] = []
        chat_history = session[chat_key]

        # Einfache Anzeige der Chat-History
        display_chat_history = chat_history

        try:
            with open("table_schema.json", "r", encoding="utf-8") as f:
                table_schema = json.load(f)
            with open("query_patterns.json", "r", encoding="utf-8") as f:
                query_patterns = json.load(f)
        except Exception as e:
            logging.error(f"Fehler beim Laden der Schema-Dateien: {e}")
            table_schema = {"tables": {}}
            query_patterns = {"common_queries": {}}

        if request.method == "POST":
            user_message = request.form.get("message", "").strip()
            notfall_aktiv = request.form.get("notfallmodus") == "1"
            notfall_art = request.form.get("notfallart", "").strip()
            
            # Check if this is a streaming request
            stream_mode = request.form.get("stream", "0") == "1"

            if not user_message:
                flash("Bitte geben Sie eine Nachricht ein.", "warning")
                return (
                    jsonify({"error": "Bitte geben Sie eine Nachricht ein."}),
                    400,
                ) if request.headers.get("X-Requested-With") == "XMLHttpRequest" else redirect(
                    url_for("chat")
                )

            wissensbasis = download_wissensbasis()
            if not wissensbasis:
                flash("Die Wissensbasis konnte nicht geladen werden.", "danger")
                return (
                    jsonify({"error": "Die Wissensbasis konnte nicht geladen werden."}),
                    500,
                ) if request.headers.get("X-Requested-With") == "XMLHttpRequest" else redirect(
                    url_for("chat")
                )

            if notfall_aktiv:
                session["notfall_mode"] = True
                user_message = (
                    f"ACHTUNG NOTFALL - Thema 9: Notfälle & Vertragsgefährdungen.\n"
                    f"Ausgewählte Notfalloption(en): {notfall_art}\n\n"
                    + user_message
                )
                log_notfall_event(user_id, notfall_art, user_message)
            else:
                session.pop("notfall_mode", None)

            # Verbesserter System Prompt
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

            # Setup tools and message collections for different approaches
            tools = create_function_definitions()
            debug_print("API Setup", f"System prompt (gekürzt): {system_prompt[:200]}...")
            debug_print("API Setup", f"Anzahl definierter Tools: {len(tools)}")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            # Sammle alle relevanten Session-Daten für den mehrstufigen Prozess
            session_data = {
                "user_id": user_id,
                "user_name": user_name,
                "seller_id": seller_id,
                "email": session.get("email"),
                "chat_key": chat_key,
                "chat_history": list(chat_history) if stream_mode else None  # Nur für Streaming benötigt
            }

            # Debug-Modus: Direkte Erzwingung eines bestimmten Tools
            debug_force = request.args.get("force_function")
            if debug_force:
                debug_print("DEBUG", f"Erzwinge Funktionsaufruf: {debug_force}")
                # Hier verwenden wir die alte Methode der direkten OpenAI-Aufrufe mit erzwungenem Tool
                tool_choice = {"type": "function", "function": {"name": debug_force}}
                use_legacy_approach = True
            else:
                # Für den normalen Betrieb verwenden wir den neuen mehrstufigen Ansatz
                use_legacy_approach = False

            try:
                # Streaming-Modus
                if stream_mode and request.headers.get("Accept") == "text/event-stream":
                    if use_legacy_approach:
                        # Legacy Streaming mit direkter Tool-Auswahl für Debug
                        return Response(
                            stream_response(messages, tools, tool_choice, seller_id, extract_date_params(user_message), user_message, session_data),
                            content_type="text/event-stream"
                        )
                    else:
                        # Vereinfachter Ansatz für die erste Implementierung
                        # Verwende den bestehenden select_optimal_tool_with_reasoning für die erste Version
                        tool_config = load_tool_config()
                        selected_tool, reasoning = select_optimal_tool_with_reasoning(user_message, tools, tool_config)
                        
                        # "Erfassungsbogen" oder ähnliche Anfragen direkt an die Wissensbasis weiterleiten
                        wissensbasis_keywords = ["wissensdatenbank", "wissensbasis", "erfassungsbogen", "handbuch", 
                                               "anleitung", "wie funktioniert", "erklär mir", "was ist", "was sind"]
                        
                        is_wissensbasis_query = False
                        user_message_lower = user_message.lower()
                        
                        for keyword in wissensbasis_keywords:
                            if keyword in user_message_lower:
                                is_wissensbasis_query = True
                                break
                        
                        if is_wissensbasis_query:
                            # Lade Wissensbasis und beantworte direkt
                            wissensbasis_data = download_wissensbasis()
                            
                            system_prompt = """
                            Du bist ein hilfreicher Assistent für ein Pflegevermittlungsunternehmen. 
                            Beantworte die Frage basierend auf der bereitgestellten Wissensbasis.
                            Sei klar, präzise und sachlich. Wenn du die Antwort nicht in der Wissensbasis findest, 
                            sage ehrlich, dass du es nicht weißt.
                            """
                            
                            wissensbasis_messages = [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": f"Wissensbasis: {wissensbasis_data}\n\nFrage: {user_message}"}
                            ]
                            
                            response = openai.chat.completions.create(
                                model="gpt-4o",  # Capabilities for knowledge-based queries
                                messages=wissensbasis_messages,
                                temperature=0.3
                            )
                            
                            wissensbasis_response = response.choices[0].message.content
                            return Response(
                                stream_text_response(wissensbasis_response, user_message, session_data),
                                content_type="text/event-stream"
                            )
                        
                        # Prüfen, ob eine Rückfrage ausgelöst wurde
                        elif selected_tool == "human_in_loop_clarification":
                            # Neue text-basierte Rückfrage ohne Buttons
                            human_in_loop_data = session.get("human_in_loop_data")
                            
                            # Process the data differently based on type
                            if human_in_loop_data and human_in_loop_data.get("type") == "text_clarification":
                                # Process as a text clarification - just stream the message
                                debug_print("Clarification", "Streaming text-based clarification")
                                return Response(
                                    generate_clarification_stream(human_in_loop_data),
                                    content_type="text/event-stream"
                                )
                            else:
                                # Process as a legacy clarification for backward compatibility
                                debug_print("Clarification", "Streaming legacy clarification")
                                return Response(
                                    generate_clarification_stream(human_in_loop_data),
                                    content_type="text/event-stream"
                                )
                        
                        
                        
                        
                        
                        # Korrektes Format für tool_choice erstellen
                        tool_choice = {"type": "function", "function": {"name": selected_tool}} if selected_tool else "auto"
                                                
                        return Response(
                            stream_response(
                                messages, 
                                tools, 
                                tool_choice,  # Statt dem String das korrekt formatierte Objekt übergeben
                                seller_id, 
                                extract_enhanced_date_params(user_message), 
                                user_message, 
                                session_data
                            ),
                            content_type="text/event-stream"
                        )
                           
                        
                
                # Nicht-Streaming-Modus
                if use_legacy_approach:
                    # Legacy-Ansatz (für Debug-Modus)
                    debug_print("API Calls", f"Legacy-Ansatz mit explizitem Function Calling: {debug_force}")
                    response = openai.chat.completions.create(
                        model="o3-mini",
                        messages=messages,
                        tools=tools,
                        tool_choice=tool_choice
                    )
                    
                    assistant_message = response.choices[0].message
                    debug_print("API Response", f"Message type: {type(assistant_message)}")
                    debug_print("API Response", f"Has tool calls: {hasattr(assistant_message, 'tool_calls') and bool(assistant_message.tool_calls)}")

                    # Initialize the antwort variable
                    antwort = None

                    if assistant_message.tool_calls:
                        debug_print("API Calls", f"Function Calls erkannt: {assistant_message.tool_calls}")
                        function_responses = []

                        for tool_call in assistant_message.tool_calls:
                            function_name = tool_call.function.name
                            function_args = json.loads(tool_call.function.arguments)
                            debug_print("Function", f"Name: {function_name}, Argumente vor Modifikation: {function_args}")

                            # Standardargumente hinzufügen und überschreiben
                            if seller_id:
                                function_args["seller_id"] = seller_id
                            
                            # Nur extrahierte Datumswerte hinzufügen, wenn sie nicht bereits gesetzt sind
                            extracted_args = extract_enhanced_date_params(user_message)
                            for key, value in extracted_args.items():
                                if key not in function_args or not function_args[key]:
                                    function_args[key] = value

                            debug_print("Function", f"Argumente nach Modifikation: {function_args}")
                            function_response = handle_function_call(function_name, function_args)
                            
                            # Parsen der Function Response für bessere Logging
                            try:
                                parsed_response = json.loads(function_response)
                                response_status = parsed_response.get("status", "unknown")
                                response_count = len(parsed_response.get("data", [])) if "data" in parsed_response else 0
                                debug_print("Function Response", f"Status: {response_status}, Anzahl Ergebnisse: {response_count}")
                            except:
                                debug_print("Function Response", "Konnte Response nicht parsen")
                            
                            function_responses.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": function_response,
                                }
                            )

                        # Second call to OpenAI with function results
                        second_messages = messages + [assistant_message.model_dump(exclude_unset=True)] + function_responses
                        debug_print("API Calls", f"Zweiter Aufruf an OpenAI mit {len(function_responses)} Funktionsantworten")
                        second_response = openai.chat.completions.create(model="o3-mini", messages=second_messages)
                        final_message = second_response.choices[0].message
                        antwort = final_message.content
                        debug_print("API Calls", f"Finale Antwort: {antwort[:100]}...")

                    else:
                        antwort = assistant_message.content
                        debug_print("API Calls", f"Direkte Antwort (kein Function Call): {antwort[:100]}...")
                        # Warnung ins Log schreiben, wenn keine Funktion aufgerufen wurde
                        if any(term in user_message.lower() for term in ["care", "pflege", "kunden", "verträge", "mai", "monat"]):
                            logging.warning(f"Keine Funktion aufgerufen trotz relevanter Anfrage: '{user_message}'")
                
                else:
                    # Neuer mehrstufiger Ansatz
                    debug_print("API Calls", f"Verwende mehrstufigen Ansatz für: {user_message}")
                    antwort = process_user_query(user_message, session_data)
                    debug_print("API Calls", f"Mehrstufige Antwort: {antwort[:100]}...")

                # Chat-History aktualisieren
                if antwort:  # Check if antwort is defined
                    chat_history.append({"user": user_message, "bot": antwort})
                    session[chat_key] = chat_history
                    store_chatlog(user_name, chat_history)

                    return (
                        jsonify({"response": antwort}),
                        200,
                    ) if request.headers.get("X-Requested-With") == "XMLHttpRequest" else redirect(
                        url_for("chat")
                    )
                else:
                    error_message = "Keine Antwort erhalten."
                    debug_print("API Calls", error_message)
                    return (
                        jsonify({"error": error_message}),
                        500,
                    ) if request.headers.get("X-Requested-With") == "XMLHttpRequest" else redirect(
                        url_for("chat")
                    )
                    
            except Exception as e:
                logging.exception("Fehler beim Verarbeiten der Anfrage")
                error_message = f"Fehler bei der Kommunikation: {str(e)}"
                debug_print("API Calls", error_message)
                flash("Es gab ein Problem bei der Kommunikation mit dem Bot.", "danger")
                return (
                    jsonify({"error": error_message}),
                    500,
                ) if request.headers.get("X-Requested-With") == "XMLHttpRequest" else redirect(
                    url_for("chat")
                )

        stats = calculate_chat_stats()
        
        # Prüfen, ob eine Human-in-Loop Rückfrage angezeigt werden soll
        human_in_loop_data = session.get("human_in_loop_data")
        
        # Prüfen, ob wir eine direkte Antwort haben, die angezeigt werden soll
        last_response = None
        if session.get("last_response"):
            last_response = session.pop("last_response")
            # Wenn wir eine direkte Antwort haben, fügen wir sie der Chat-History hinzu
            if last_response and chat_key in session:
                # Wir haben die Benutzeranfrage schon beim Speichern der Antwort hinzugefügt
                # Jetzt müssen wir nur sicherstellen, dass die Antwort in der History ist
                session.modified = True
        
        # Wenn human_in_loop_data existiert, geben wir die Rückfrage-Optionen mit an das Template
        return render_template("chat.html", 
                              chat_history=display_chat_history, 
                              stats=stats,
                              human_in_loop=human_in_loop_data,
                              last_response=last_response)

    except Exception as e:
        logging.exception("Fehler in chat-Funktion.")
        flash("Ein unerwarteter Fehler ist aufgetreten.", "danger")
        return (
            jsonify({"error": "Interner Serverfehler."}),
            500,
        ) if request.headers.get("X-Requested-With") == "XMLHttpRequest" else "Interner Serverfehler", 500

@app.route('/test_bigquery')
def test_bigquery():
    try:
        service_account_path = '/home/PfS/gcpxbixpflegehilfesenioren-a47c654480a8.json'
        client = bigquery.Client.from_service_account_json(service_account_path)
        
        # E-Mail aus Session holen
        email = session.get('email') or session.get('google_user_email', '')
        
        # Abfrage mit WHERE-Klausel für User-Info
        user_query = """
        SELECT email, _id 
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.proto_users` 
        WHERE email = @email
        LIMIT 10
        """
        
        # Parameter definieren für User-Query
        user_job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        
        # User-Abfrage ausführen
        user_query_job = client.query(user_query, job_config=user_job_config)
        user_results = user_query_job.result()
        
        # HTML-Ausgabe mit Bootstrap für besseres Layout
        output = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>BigQuery Dashboard zum Testen der geladenen Daten</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
            <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
            <style>
                .table-responsive { margin-bottom: 20px; }
                .tab-pane { padding: 15px; }
            </style>
        </head>
        <body>
        <div class="container mt-4">
            <h1>BigQuery Dashboard zum Testen der geladenen Daten</h1>
            <p>Abfrage für E-Mail: """ + email + """</p>
        """
        
        # Seller-ID ermitteln
        seller_id = session.get('seller_id')
        rows_found = False
        
        output += """
        <h2>Benutzerinformationen</h2>
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead><tr><th>E-Mail</th><th>ID</th></tr></thead>
            <tbody>
        """
        
        for row in user_results:
            rows_found = True
            output += f"<tr><td>{row['email']}</td><td>{row['_id']}</td></tr>"
            if not seller_id:  # Wenn keine seller_id in der Session ist, nutze die aus der Abfrage
                seller_id = row['_id']
        
        output += """
            </tbody>
        </table>
        </div>
        """
        
        if not rows_found:
            output += f"<p class='alert alert-warning'>Keine Daten für E-Mail '{email}' gefunden!</p>"
            
        # Wenn wir keine seller_id haben, können wir keine weiteren Abfragen durchführen
        if not seller_id:
            output += "<p class='alert alert-danger'>Keine Seller ID gefunden für weitere Abfragen!</p></div></body></html>"
            return output
            
        output += f"<p>Verwende Seller ID: <strong>{seller_id}</strong> für weitere Abfragen</p>"
        
        # Tabs für verschiedene Datenquellen
        output += """
        <ul class="nav nav-tabs" id="dataTabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link active" id="carestays-tab" data-bs-toggle="tab" data-bs-target="#carestays" type="button" role="tab">Care Stays</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="contracts-tab" data-bs-toggle="tab" data-bs-target="#contracts" type="button" role="tab">Verträge</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="leads-tab" data-bs-toggle="tab" data-bs-target="#leads" type="button" role="tab">Leads</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="caregivers-tab" data-bs-toggle="tab" data-bs-target="#caregivers" type="button" role="tab">Pflegekräfte</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="tickets-tab" data-bs-toggle="tab" data-bs-target="#tickets" type="button" role="tab">Tickets</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="agencies-tab" data-bs-toggle="tab" data-bs-target="#agencies" type="button" role="tab">Agenturen</button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link" id="stats-tab" data-bs-toggle="tab" data-bs-target="#stats" type="button" role="tab">Statistiken</button>
            </li>
        </ul>
        
        <div class="tab-content" id="dataTabsContent">
        """
        
        # ==================== CARE STAYS TAB ====================
        output += """<div class="tab-pane fade show active" id="carestays" role="tabpanel">
            <h3 class="mt-3">Aktive Care Stays</h3>"""
        
        # Care Stays Abfrage
        care_stays_query = """
        SELECT
            cs.bill_start,
            cs.bill_end,
            cs.arrival,
            cs.departure,
            cs.presented_at,
            cs.contract_id,
            cs.created_at,
            cs.stage,
            cs.prov_seller AS seller_prov,
            cs._id AS cs_id,
            cs.care_giver_instance_id,
            TIMESTAMP(cs.bill_end) AS parsed_bill_end,
            TIMESTAMP(cs.bill_start) AS parsed_bill_start,
            DATE_DIFF(
                DATE(TIMESTAMP(cs.bill_end)),
                DATE(TIMESTAMP(cs.bill_start)),
                DAY
            ) AS care_stay_duration_days,
            c.agency_id,
            c.active,
            c.termination_reason,
            l._id AS lead_id,
            l.tracks AS lead_tracks,
            l.created_at AS lead_created_at,
            lead_names.first_name,
            lead_names.last_name,
            agencies.name AS agency_name
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` AS cs
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c ON cs.contract_id = c._id
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_names 
            ON l._id = lead_names._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.agencies` AS agencies
            ON c.agency_id = agencies._id
        WHERE l.seller_id = @seller_id
          AND cs.stage = 'Bestätigt'
          AND DATE(TIMESTAMP(cs.bill_end)) >= CURRENT_DATE()
          AND cs.rejection_reason IS NULL
        ORDER BY cs.bill_start DESC
        LIMIT 100
        """
        
        care_stays_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        # Care Stays-Abfrage ausführen
        care_stays_job = client.query(care_stays_query, job_config=care_stays_config)
        care_stays_results = care_stays_job.result()
        
        # Tabelle für Care Stays ausgeben
        output += """
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>CS ID</th>
                    <th>Lead Name</th>
                    <th>Agency</th>
                    <th>Bill Start</th>
                    <th>Bill End</th>
                    <th>Arrival</th>
                    <th>Departure</th>
                    <th>Status</th>
                    <th>Prov. Verkäufer</th>
                    <th>Dauer (Tage)</th>
                </tr>
            </thead>
            <tbody>
        """
        
        care_stays_found = False
        for row in care_stays_results:
            care_stays_found = True
            lead_id = row['lead_id']
            
            # Zusammensetzen des Kundennamens
            first_name = row.get('first_name', '')
            last_name = row.get('last_name', '')
            lead_name = f"{first_name} {last_name}".strip() if (first_name or last_name) else f"Lead ID: {lead_id}"
            
            # Agency Name
            agency_name = row.get('agency_name', 'N/A')
            
            # Sichere Anzeige der Datumswerte
            bill_start = str(row['bill_start']) if row['bill_start'] else 'N/A'
            bill_end = str(row['bill_end']) if row['bill_end'] else 'N/A'
            arrival = str(row['arrival']) if row.get('arrival') else 'N/A'
            departure = str(row['departure']) if row.get('departure') else 'N/A'
            
            output += f"""
            <tr>
                <td>{row['cs_id']}</td>
                <td>{lead_name}</td>
                <td>{agency_name}</td>
                <td>{bill_start}</td>
                <td>{bill_end}</td>
                <td>{arrival}</td>
                <td>{departure}</td>
                <td>{row['stage']}</td>
                <td>{row['seller_prov']}</td>
                <td>{row['care_stay_duration_days']}</td>
            </tr>"""
        
        output += """
            </tbody>
        </table>
        </div>
        """
        
        if not care_stays_found:
            output += f"<p class='alert alert-warning'>Keine aktiven Care Stays für Seller ID '{seller_id}' gefunden!</p>"
        
        output += "</div>"  # Ende des Care Stays Tab
        
        # ==================== VERTRÄGE TAB ====================
        output += """<div class="tab-pane fade" id="contracts" role="tabpanel">
            <h3 class="mt-3">Verträge</h3>"""
        
        contracts_query = """
        SELECT
            c._id AS contract_id,
            c.active,
            c.termination_reason,
            c.agency_id,
            c.household_id,
            h.lead_id,
            agencies.name AS agency_name,
            lead_names.first_name,
            lead_names.last_name,
            c.created_at
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_names 
            ON l._id = lead_names._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.agencies` AS agencies
            ON c.agency_id = agencies._id
        WHERE l.seller_id = @seller_id
        ORDER BY c.created_at DESC
        LIMIT 100
        """
        
        contracts_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        contracts_job = client.query(contracts_query, job_config=contracts_config)
        contracts_results = contracts_job.result()
        
        output += """
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>Contract ID</th>
                    <th>Lead</th>
                    <th>Agentur</th>
                    <th>Aktiv</th>
                    <th>Kündigungsgrund</th>
                    <th>Erstellt am</th>
                </tr>
            </thead>
            <tbody>
        """
        
        contracts_found = False
        for row in contracts_results:
            contracts_found = True
            first_name = row.get('first_name', '')
            last_name = row.get('last_name', '')
            lead_name = f"{first_name} {last_name}".strip() if (first_name or last_name) else f"Lead ID: {row['lead_id']}"
            
            agency_name = row.get('agency_name', 'N/A')
            created_at = str(row['created_at']) if row['created_at'] else 'N/A'
            active = "Ja" if row['active'] else "Nein"
            
            output += f"""
            <tr>
                <td>{row['contract_id']}</td>
                <td>{lead_name}</td>
                <td>{agency_name}</td>
                <td>{active}</td>
                <td>{row['termination_reason'] or 'N/A'}</td>
                <td>{created_at}</td>
            </tr>"""
        
        output += """
            </tbody>
        </table>
        </div>
        """
        
        if not contracts_found:
            output += f"<p class='alert alert-warning'>Keine Verträge für Seller ID '{seller_id}' gefunden!</p>"
        
        output += "</div>"  # Ende des Verträge Tab
        
        # ==================== LEADS TAB ====================
        output += """<div class="tab-pane fade" id="leads" role="tabpanel">
            <h3 class="mt-3">Leads</h3>"""
        
        leads_query = """
        SELECT
            l._id AS lead_id,
            la.first_name,
            la.last_name,
            l.created_at AS lead_created_at,
            l.source_data
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l
        JOIN `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS la
        ON la._id = l._id
        WHERE l.seller_id = @seller_id
        ORDER BY l.created_at DESC
        LIMIT 100
        """
        
        leads_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        leads_job = client.query(leads_query, job_config=leads_config)
        leads_results = leads_job.result()
        
        output += """
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>Lead ID</th>
                    <th>Vorname</th>
                    <th>Nachname</th>
                    <th>Erstellt am</th>
                </tr>
            </thead>
            <tbody>
        """
        
        leads_found = False
        for row in leads_results:
            leads_found = True
            created_at = str(row['lead_created_at']) if row['lead_created_at'] else 'N/A'
            
            output += f"""
            <tr>
                <td>{row['lead_id']}</td>
                <td>{row.get('first_name', 'N/A')}</td>
                <td>{row.get('last_name', 'N/A')}</td>
                <td>{created_at}</td>
            </tr>"""
        
        output += """
            </tbody>
        </table>
        </div>
        """
        
        if not leads_found:
            output += f"<p class='alert alert-warning'>Keine Leads für Seller ID '{seller_id}' gefunden!</p>"
        
        output += "</div>"  # Ende des Leads Tab
        
        # ==================== PFLEGEKRÄFTE TAB ====================
        output += """<div class="tab-pane fade" id="caregivers" role="tabpanel">
            <h3 class="mt-3">Pflegekräfte</h3>"""
        
        caregivers_query = """
        SELECT
            cgi._id AS care_giver_instance_id,
            cg.first_name AS giver_first_name,
            cg.last_name AS giver_last_name,
            cs._id AS carestay_id,
            c._id AS contract_id,
            h.lead_id,
            lead_names.first_name AS lead_first_name,
            lead_names.last_name AS lead_last_name
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_giver_instances` cgi
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_givers` cg ON cgi.care_giver_id = cg._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON cs.care_giver_instance_id = cgi._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` c ON cs.contract_id = c._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` h ON c.household_id = h._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` l ON h.lead_id = l._id
        LEFT JOIN `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_names 
            ON l._id = lead_names._id
        WHERE l.seller_id = @seller_id
        LIMIT 100
        """
        
        caregivers_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        caregivers_job = client.query(caregivers_query, job_config=caregivers_config)
        caregivers_results = caregivers_job.result()
        
        output += """
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>Pflegekraft</th>
                    <th>Kunde</th>
                    <th>Care Stay ID</th>
                    <th>Instance ID</th>
                </tr>
            </thead>
            <tbody>
        """
        
        caregivers_found = False
        for row in caregivers_results:
            caregivers_found = True
            caregiver_name = f"{row.get('giver_first_name', '')} {row.get('giver_last_name', '')}".strip() or 'N/A'
            lead_name = f"{row.get('lead_first_name', '')} {row.get('lead_last_name', '')}".strip() or 'N/A'
            
            output += f"""
            <tr>
                <td>{caregiver_name}</td>
                <td>{lead_name}</td>
                <td>{row.get('carestay_id', 'N/A')}</td>
                <td>{row['care_giver_instance_id']}</td>
            </tr>"""
        
        output += """
            </tbody>
        </table>
        </div>
        """
        
        if not caregivers_found:
            output += f"<p class='alert alert-warning'>Keine Pflegekräfte für Seller ID '{seller_id}' gefunden!</p>"
        
        output += "</div>"  # Ende des Pflegekräfte Tab
        
        # ==================== TICKETS TAB ====================
        output += """<div class="tab-pane fade" id="tickets" role="tabpanel">
            <h3 class="mt-3">Tickets</h3>"""

        tickets_query = """
        SELECT
            t.subject,
            t.messages,
            t.created_at,
            tc.Datum,
            t.updated_at,
            t._id,
            t.ticketable_id,
            t.ticketable_type,
            tc.seller,
            tc.agency,
            -- Lead-Informationen
            CASE 
                WHEN t.ticketable_type = 'Lead' THEN lead_direct.first_name
                WHEN t.ticketable_type = 'Contract' THEN lead_contract.first_name
                WHEN t.ticketable_type = 'CareStay' THEN lead_carestay.first_name
                WHEN t.ticketable_type = 'Visor' THEN lead_visor.first_name
                ELSE NULL
            END AS lead_first_name,
            CASE 
                WHEN t.ticketable_type = 'Lead' THEN lead_direct.last_name
                WHEN t.ticketable_type = 'Contract' THEN lead_contract.last_name
                WHEN t.ticketable_type = 'CareStay' THEN lead_carestay.last_name
                WHEN t.ticketable_type = 'Visor' THEN lead_visor.last_name
                ELSE NULL
            END AS lead_last_name,
            CASE
                WHEN t.ticketable_type = 'Lead' THEN t.ticketable_id
                WHEN t.ticketable_type = 'Contract' THEN contract_lead.lead_id
                WHEN t.ticketable_type = 'CareStay' THEN carestay_lead.lead_id
                WHEN t.ticketable_type = 'Visor' THEN visor_lead.lead_id
                ELSE NULL
            END AS lead_id
        FROM
            `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.tickets` t
        LEFT JOIN
            `gcpxbixpflegehilfesenioren.dataform_staging.tickets_creation_end` tc
            ON t._id = tc.Ticket_ID

        -- Direkter Lead-Join für Lead-Tickets
        LEFT JOIN
            `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_direct
            ON t.ticketable_type = 'Lead' AND t.ticketable_id = lead_direct._id

        -- Contract-Lead-Join für Contract-Tickets
        LEFT JOIN (
            SELECT
                c._id AS contract_id,
                h.lead_id,
                l._id AS lead_orig_id
            FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` c
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` h ON c.household_id = h._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` l ON h.lead_id = l._id
        ) AS contract_lead
            ON t.ticketable_type = 'Contract' AND t.ticketable_id = contract_lead.contract_id
        LEFT JOIN
            `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_contract
            ON contract_lead.lead_orig_id = lead_contract._id

        -- CareStay-Lead-Join für CareStay-Tickets
        LEFT JOIN (
            SELECT
                cs._id AS carestay_id,
                h.lead_id,
                l._id AS lead_orig_id
            FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` c ON cs.contract_id = c._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` h ON c.household_id = h._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` l ON h.lead_id = l._id
        ) AS carestay_lead
            ON t.ticketable_type = 'CareStay' AND t.ticketable_id = carestay_lead.carestay_id
        LEFT JOIN
            `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_carestay
            ON carestay_lead.lead_orig_id = lead_carestay._id

        -- Visor-Lead-Join für Visor-Tickets
        LEFT JOIN (
            SELECT
                v._id AS visor_id,
                h.lead_id,
                l._id AS lead_orig_id
            FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.visors` v
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.postings` p ON v.posting_id = p._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` h ON p.household_id = h._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` l ON h.lead_id = l._id
        ) AS visor_lead
            ON t.ticketable_type = 'Visor' AND t.ticketable_id = visor_lead.visor_id
        LEFT JOIN
            `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS lead_visor
            ON visor_lead.lead_orig_id = lead_visor._id

        WHERE
            tc.seller = 'Pflegeteam Heer'
        ORDER BY 
            t.created_at DESC
        LIMIT 100
        """

        tickets_job = client.query(tickets_query)
        tickets_results = tickets_job.result()

        output += """
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>Ticket ID</th>
                    <th>Betreff</th>
                    <th>Typ</th>
                    <th>Lead</th>
                    <th>Erstellt am</th>
                    <th>Aktualisiert am</th>
                    <th>Agentur</th>
                </tr>
            </thead>
            <tbody>
        """

        tickets_found = False
        for row in tickets_results:
            tickets_found = True
            created_at = str(row['created_at']) if row['created_at'] else 'N/A'
            updated_at = str(row['updated_at']) if row['updated_at'] else 'N/A'
            
            # Lead-Namen zusammensetzen
            lead_name = "N/A"
            if row.get('lead_first_name') or row.get('lead_last_name'):
                lead_name = f"{row.get('lead_first_name', '')} {row.get('lead_last_name', '')}".strip()
            
            output += f"""
            <tr>
                <td>{row['_id']}</td>
                <td>{row['subject']}</td>
                <td>{row['ticketable_type'] or 'N/A'}</td>
                <td>{lead_name}</td>
                <td>{created_at}</td>
                <td>{updated_at}</td>
                <td>{row['agency'] or 'N/A'}</td>
            </tr>"""

        output += """
            </tbody>
        </table>
        </div>
        """

        if not tickets_found:
            output += f"<p class='alert alert-warning'>Keine Tickets für '{seller_id}' gefunden!</p>"

        output += "</div>"  # Ende des Tickets Tab
        
        # ==================== AGENTUREN TAB ====================
        output += """<div class="tab-pane fade" id="agencies" role="tabpanel">
            <h3 class="mt-3">Agenturen</h3>"""
        
        agencies_query = """
        SELECT
            _id AS agency_id,
            name AS agency_name
        FROM gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.agencies
        ORDER BY name
        LIMIT 100
        """
        
        agencies_job = client.query(agencies_query)
        agencies_results = agencies_job.result()
        
        output += """
        <div class="table-responsive">
        <table class="table table-striped table-bordered">
            <thead>
                <tr>
                    <th>Agentur ID</th>
                    <th>Name</th>
                </tr>
            </thead>
            <tbody>
        """
        
        agencies_found = False
        for row in agencies_results:
            agencies_found = True
            output += f"""
            <tr>
                <td>{row['agency_id']}</td>
                <td>{row['agency_name']}</td>
            </tr>"""
        
        output += """
            </tbody>
        </table>
        </div>
        """
        
        if not agencies_found:
            output += f"<p class='alert alert-warning'>Keine Agenturen gefunden!</p>"
        
        output += "</div>"  # Ende des Agenturen Tab
        
        # ==================== STATISTIKEN TAB ====================
        output += """<div class="tab-pane fade" id="stats" role="tabpanel">
            <h3 class="mt-3">Statistiken</h3>"""
        
        # Care Stay Statistiken
        stats_query = """
        SELECT
            COUNT(DISTINCT cs._id) AS total_care_stays,
            COUNT(DISTINCT c._id) AS total_contracts,
            COUNT(DISTINCT l._id) AS total_leads,
            AVG(DATE_DIFF(
                DATE(TIMESTAMP(cs.bill_end)),
                DATE(TIMESTAMP(cs.bill_start)),
                DAY
            )) AS avg_care_stay_duration,
            SUM(CAST(cs.prov_seller AS FLOAT64)) AS total_prov_seller
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` AS cs
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c ON cs.contract_id = c._id
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
        JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
        WHERE l.seller_id = @seller_id
          AND cs.stage = 'Bestätigt'
        """
        
        stats_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        stats_job = client.query(stats_query, job_config=stats_config)
        stats_results = stats_job.result()
        
        # Monatliche Statistiken
        monthly_stats_query = """
        WITH monthly_data AS (
            SELECT
                FORMAT_DATE('%Y-%m', DATE(TIMESTAMP(cs.bill_start))) AS month,
                COUNT(DISTINCT cs._id) AS new_care_stays,
                SUM(CAST(cs.prov_seller AS FLOAT64)) AS monthly_prov
            FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` AS cs
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c ON cs.contract_id = c._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
            JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
            WHERE l.seller_id = @seller_id
              AND cs.stage = 'Bestätigt'
              AND DATE(TIMESTAMP(cs.bill_start)) >= DATE_SUB(CURRENT_DATE(), INTERVAL 12 MONTH)
            GROUP BY month
            ORDER BY month DESC
        )
        SELECT * FROM monthly_data
        """
        
        monthly_stats_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("seller_id", "STRING", seller_id)
            ]
        )
        
        monthly_stats_job = client.query(monthly_stats_query, job_config=monthly_stats_config)
        monthly_stats_results = monthly_stats_job.result()
        
        # Gesamtstatistiken
        output += """<div class="row">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Gesamtstatistiken</div>
                    <div class="card-body">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Metrik</th>
                                    <th>Wert</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        for row in stats_results:
            output += f"""
                <tr><td>Gesamtzahl Care Stays</td><td>{row['total_care_stays']}</td></tr>
                <tr><td>Gesamtzahl Verträge</td><td>{row['total_contracts']}</td></tr>
                <tr><td>Gesamtzahl Leads</td><td>{row['total_leads']}</td></tr>
                <tr><td>Durchschnittliche Care Stay Dauer (Tage)</td><td>{row['avg_care_stay_duration']:.2f}</td></tr>
                <tr><td>Gesamtprovision</td><td>{row['total_prov_seller']:.2f} €</td></tr>
            """
        
        output += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Monatliche Statistiken</div>
                    <div class="card-body">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Monat</th>
                                    <th>Neue Care Stays</th>
                                    <th>Provision</th>
                                </tr>
                            </thead>
                            <tbody>
        """
        
        monthly_stats_found = False
        for row in monthly_stats_results:
            monthly_stats_found = True
            output += f"""
                <tr>
                    <td>{row['month']}</td>
                    <td>{row['new_care_stays']}</td>
                    <td>{row['monthly_prov']:.2f} €</td>
                </tr>
            """
        
        if not monthly_stats_found:
            output += "<tr><td colspan='3'>Keine monatlichen Daten gefunden</td></tr>"
        
        output += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>"""
        
        output += "</div>"  # Ende des Statistiken Tab
        
        # Abschluss der HTML-Struktur
        output += """
        </div>  <!-- Ende der Tab-Inhalte -->
        </div>  <!-- Ende des Containers -->
        </body>
        </html>
        """
        
        return output
    except Exception as e:
        error_output = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>BigQuery Test - Fehler</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        </head>
        <body>
        <div class="container mt-4">
            <div class="alert alert-danger">
                <h4>Fehler beim Ausführen der BigQuery-Abfragen:</h4>
                <p>{str(e)}</p>
                <pre>{traceback.format_exc()}</pre>
            </div>
        </div>
        </body>
        </html>
        """
        return error_output

def create_system_prompt(table_schema):
    # Bestehendes System-Prompt generieren
    prompt = "Du bist ein hilfreicher KI-Assistent, der bei der Verwaltung von Pflegedaten hilft."
    prompt += "\n\nDu hast Zugriff auf eine Datenbank mit folgenden Tabellen:\n"
    
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

@app.route('/update_stream_chat_history', methods=['POST'])
def update_stream_chat_history():
    """Update chat history in the session from streaming responses"""
    try:
        data = request.json
        user_message = data.get('user_message')
        bot_response = data.get('bot_response')
        
        if not user_message or not bot_response:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
            
        user_id = session.get("user_id")
        user_name = session.get("user_name")
        
        if not user_id or not user_name:
            return jsonify({'success': False, 'error': 'No active session'}), 400
            
        chat_key = f"chat_history_{user_id}"
        
        # Get current chat history or initialize it
        chat_history = session.get(chat_key, [])
        
        # Add the new messages
        chat_history.append({"user": user_message, "bot": bot_response})
        
        # Update the session
        session[chat_key] = chat_history
        session.modified = True
        
        # Store in the persistent storage
        store_chatlog(user_name, chat_history)
        
        return jsonify({'success': True})
        
    except Exception as e:
        logging.exception("Error updating chat history")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/check_login')
def check_login():
    # Alle relevanten Session-Daten anzeigen
    session_data = {
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name'),
        'email': session.get('email'),
        'google_user_email': session.get('google_user_email'),
        'seller_id': session.get('seller_id'),
        'is_logged_via_google': session.get('is_logged_via_google')
    }
    
    output = "<h1>Login-Status</h1>"
    output += "<pre>" + json.dumps(session_data, indent=2) + "</pre>"
    
    # Wenn E-Mail vorhanden ist, teste BigQuery-Abfrage
    email = session.get('email') or session.get('google_user_email')
    if email:
        output += f"<h2>Test der seller_id-Abfrage für {email}</h2>"
        try:
            seller_id = get_user_id_from_email(email)
            output += f"<p>Gefundene seller_id: {seller_id}</p>"
        except Exception as e:
            output += f"<p style='color:red'>Fehler: {str(e)}</p>"
    
    # Link zum Zurücksetzen der Session
    output += "<p><a href='/reset_session'>Session zurücksetzen</a></p>"
    
    return output

@app.route('/reset_session')
def reset_session():
    # Alle Session-Daten löschen, außer user_id
    user_id = session.get('user_id')
    session.clear()
    session['user_id'] = user_id
    session.modified = True
    return redirect('/check_login')

###########################################
# Flask-Routen
###########################################
@app.route('/toggle_notfall_mode', methods=['POST'])
def toggle_notfall_mode():
    try:
        activate = request.form.get('activate', '0')
        if activate == '1':
            session['notfall_mode'] = True
        else:
            session.pop('notfall_mode', None)
        return jsonify({
            'success': True,
            'notfall_mode_active': session.get('notfall_mode', False)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/store_feedback', methods=['POST'])
def store_feedback_route():
    try:
        data = request.get_json()
        feedback_type = data.get("feedback_type", "")
        comment = data.get("comment", "").strip()

        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"success": False, "message": "User nicht erkannt"}), 400

        chat_key = f'chat_history_{user_id}'
        chat_history = session.get(chat_key, [])

        store_feedback(feedback_type, comment, chat_history)
        return jsonify({"success": True}), 200
    except Exception as e:
        logging.exception("Fehler beim Speichern des Feedbacks.")
        return jsonify({"success": False, "error": str(e)}), 500


###########################################
# Neue Routen: Username setzen/auslesen
###########################################
@app.route('/get_username', methods=['GET'])
def get_username():
    try:
        user_name = session.get('user_name')
        return jsonify({'user_name': user_name}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/set_username', methods=['POST'])
def set_username():
    try:
        username = request.form.get('username', '').strip()
        if len(username) < 3:
            return jsonify({'success': False, 'message': 'Name zu kurz'}), 400
        
        session['user_name'] = username
        
        return jsonify({'success': True}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

###########################################
# Chat Route
###########################################

 


@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if password == admin_password:
            session['admin_logged_in'] = True
            flash('Erfolgreich als Administrator eingeloggt.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Falsches Passwort.', 'danger')
            return redirect(url_for('admin_login'))
            
    # Render admin login template
    return render_template('admin_login.html')

###########################################
# CSRF & Session Hooks
###########################################
from flask_wtf.csrf import generate_csrf

@app.context_processor
def inject_csrf_token():
    return {'csrf_token': generate_csrf()}

@app.before_request
def ensure_user_id():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())

###########################################
# Login-Decorator
###########################################

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

###########################################
# AJAX Endpoint für Human-in-the-Loop
###########################################
@app.route('/get_clarification_response', methods=['GET'])
def get_clarification_response():
    """
    AJAX endpoint to get a response after a human-in-loop clarification button was clicked.
    This allows the client to update the UI without a page refresh.
    """
    try:
        # Ensure user is authenticated
        user_id = session.get("user_id")
        if not user_id:
            return jsonify({"error": "Nicht angemeldet"}), 403
            
        # Check if we have a pending clarification response
        if "human_in_loop_clarification_response" in session:
            clarification_response = session.pop("human_in_loop_clarification_response")
            pending_query = session.get("pending_query", "")
            session.pop("pending_query", None)
            
            # Process the clarification response
            logging.info(f"Processing clarification response via AJAX: {clarification_response.get('text', '')}")
            
            # Extract the selected query and parameters
            selected_query = clarification_response.get("query")
            selected_params = clarification_response.get("params", {})
            
            # Add standard parameters
            if "seller_id" in selected_params and "seller_id" in session:
                selected_params["seller_id"] = session.get("seller_id")
            
            # Execute function call
            try:
                tool_result = handle_function_call(selected_query, selected_params)
                
                # Check for empty results
                result_data = json.loads(tool_result)
                if "data" in result_data and len(result_data["data"]) == 0:
                    # No data found, return a proper error
                    logging.warning(f"No data found for query {selected_query} with params {selected_params}")
                    return jsonify({
                        "success": False,
                        "error": f"Keine Daten für diese Anfrage gefunden."
                    }), 404
                    
            except Exception as e:
                logging.error(f"Error executing function call: {str(e)}")
                return jsonify({
                    "success": False,
                    "error": f"Fehler bei der Ausführung: {str(e)}"
                }), 500
            
            # Create enhanced system prompt for LLM response generation
            system_prompt = create_enhanced_system_prompt(selected_query)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": pending_query},
                {"role": "function", "name": selected_query, "content": tool_result}
            ]
            
            # Generate response with LLM
            # o3-mini doesn't support function role, so we'll convert the function message to a user message
            adjusted_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User question: {pending_query}\n\nQuery result: {tool_result}"}
            ]
            
            response = openai.chat.completions.create(
                model="o3-mini",
                messages=adjusted_messages,
                temperature=0.4
            )
            
            final_response = response.choices[0].message.content
            
            # Update chat history
            chat_key = f"chat_history_{session.get('user_id')}"
            chat_history = session.get(chat_key, [])
            chat_history.append({"role": "user", "content": pending_query})
            chat_history.append({"role": "assistant", "content": final_response})
            session[chat_key] = chat_history
            session.modified = True
            
            # Return the response as JSON
            return jsonify({
                "success": True,
                "response": final_response
            })
        else:
            # No pending clarification response
            return jsonify({
                "success": False,
                "error": "Keine ausstehende Antwort auf Rückfrage gefunden"
            })
    except Exception as e:
        logging.exception(f"Error processing clarification response: {str(e)}")
        return jsonify({
            "success": False,
            "error": f"Fehler bei der Verarbeitung: {str(e)}"
        }), 500

###########################################
# Clear Chat
###########################################
@app.route('/clear_chat_history', methods=['POST'])
def clear_chat_history():
    try:
        user_id = session.get('user_id')
        if not user_id:
            flash('Benutzer nicht erkannt.', 'danger')
            return redirect(url_for('chat'))

        chat_key = f'chat_history_{user_id}'
        if chat_key in session:
            session.pop(chat_key)
            flash('Chatverlauf wurde erfolgreich geleert.', 'success')
        else:
            flash('Es gibt keinen Chatverlauf zu löschen.', 'info')
        return redirect(url_for('chat'))
    except Exception as e:
        logging.exception("Fehler beim Löschen Chatverlaufs.")
        flash('Ein Fehler ist aufgetreten.', 'danger')
        return redirect(url_for('chat'))

###########################################
# Login / Logout
###########################################
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Behalten Sie die bestehende Admin-Login-Logik bei
        password = request.form.get('password', '')
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if password == admin_password:
            session['admin_logged_in'] = True
            flash('Erfolgreich eingeloggt.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Falsches Passwort.', 'danger')
            return redirect(url_for('login'))
            
    # Render login template mit Google-Login-Option
    return render_template('login.html')

@app.route('/logout')
def logout():
    # Check if user is admin and handle accordingly
    if session.get('admin_logged_in'):
        session.pop('admin_logged_in', None)
        flash('Erfolgreich ausgeloggt.', 'success')
        return redirect(url_for('login'))
    
    # Clear specific user session data
    keys_to_remove = [
        'user_name', 'email', 'google_user_email', 
        'seller_id', 'is_logged_via_google'
    ]
    
    for key in keys_to_remove:
        if key in session:
            session.pop(key)
    
    # Keep user_id for tracking purposes
    
    flash('Erfolgreich ausgeloggt.', 'success')
    return redirect(url_for('login'))

###########################################
# Lade Themen
###########################################
@app.route('/lade_themen', methods=['GET'], endpoint='lade_themen')
@login_required
def lade_themen_route():
    themen_dict = lade_themen()
    return jsonify(themen_dict), 200


###########################################
# Admin
###########################################
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    try:
        themen_dict = lade_themen()
        logging.debug("Themen_dict: %s", themen_dict)
        if request.method == 'POST':
            eingabe_text = request.form.get('eingabe_text', '').strip()
            if not eingabe_text:
                flash('Bitte geben Sie einen Wissenseintrag ein.', 'warning')
                return redirect(url_for('admin'))

            ki_aktiviert = (request.form.get('ki_var') == 'on')
            if ki_aktiviert:
                # KI-Extraktion (Beispiel)
                extraktion_messages = [
                    {"role": "user", "content": "Du bist ein Experte, der aus Transkripten Wissen extrahiert..."},
                    {"role": "user", "content": f"Extrahiere ohne Verluste:\n'''{eingabe_text}'''"}
                ]
                extraktion_response = contact_openai(extraktion_messages, model="o3-mini")
                if not extraktion_response:
                    flash("Fehler bei der Wissensextraktion durch die KI.", 'danger')
                    return redirect(url_for('admin'))

                try:
                    extraktion_text = extraktion_response
                    debug_print("Bearbeiten von Einträgen", "Extraktionsergebnis: " + extraktion_text)
                except Exception as e:
                    debug_print("Bearbeiten von Einträgen", f"Fehler: {e}")
                    flash("Fehler bei der Wissensextraktion.", 'danger')
                    return redirect(url_for('admin'))

                # Kategorisierung (Beispiel)
                themen_hierarchie = ''
                if os.path.exists(themen_datei):
                    with open(themen_datei, 'r', encoding='utf-8') as f:
                        themen_hierarchie = f.read()

                kategorisierung_messages = [
                    {"role": "user",
                     "content": "Du bist ein Assistent, der Texte in vorgegebene Themen..."},
                    {"role": "user",
                     "content": f"Hier die Themenhierarchie:\n\n{themen_hierarchie}\n\nText:\n{extraktion_text}"}
                ]
                kategorisierung_response = contact_openai(kategorisierung_messages, model="o3-mini")
                if not kategorisierung_response:
                    flash("Fehler bei der Themenkategorisierung.", 'danger')
                    return redirect(url_for('admin'))

                try:
                    kategorisierung_text = kategorisierung_response
                    json_match = re.search(r'\[\s*{.*}\s*\]', kategorisierung_text, re.DOTALL)
                    if json_match:
                        json_text = json_match.group(0)
                        json_text = re.sub(r'(\d+[a-z]*)\)\)', r'\1)', json_text)
                        kategorisierte_eintraege = json.loads(json_text)
                    else:
                        raise ValueError("Kein gültiger JSON-Inhalt gefunden")

                    for eintrag_kat in kategorisierte_eintraege:
                        thema = eintrag_kat.get('thema')
                        unterthema = eintrag_kat.get('unterthema')
                        beschreibung = eintrag_kat.get('beschreibung', '')
                        inhalt = eintrag_kat.get('inhalt')
                        if thema and unterthema and inhalt:
                            speichere_wissensbasis({
                                "thema": thema,
                                "unterthema": unterthema,
                                "beschreibung": beschreibung,
                                "inhalt": inhalt
                            })
                    flash("Alle Einträge erfolgreich gespeichert.", 'success')
                except Exception as e:
                    debug_print("Bearbeiten von Einträgen", f"Parsing-Fehler: {e}")
                    flash("KI-Antwort konnte nicht geparst werden.", 'danger')
            else:
                # Manuell
                ausgewähltes_thema = request.form.get('thema_var')
                ausgewähltes_unterthema = request.form.get('unterthema_var')
                beschreibung_text = request.form.get('beschreibung_text', '').strip()

                if not ausgewähltes_thema or not ausgewähltes_unterthema:
                    flash("Bitte Thema + Unterthema wählen.", 'warning')
                    return redirect(url_for('admin'))

                verarbeite_eintrag(eingabe_text, ausgewähltes_thema, ausgewähltes_unterthema, beschreibung_text)
                flash("Wissenseintrag gespeichert.", 'success')

            return redirect(url_for('admin'))

        if not themen_dict:
            flash("Bitte fügen Sie zuerst ein Thema hinzu.", 'warning')
            return redirect(url_for('admin'))
        return render_template('admin.html', themen_dict=themen_dict)

    except Exception as e:
        logging.exception("Fehler in admin-Funktion.")
        flash("Ein unerwarteter Fehler ist aufgetreten.", 'danger')
        return render_template('admin.html', themen_dict={})


@app.route('/edit', methods=['GET'])
@login_required
def edit():
    try:
        wissensbasis = download_wissensbasis()
        logging.debug("Wissensbasis geladen: %s", wissensbasis)
        return render_template('edit.html', wissensbasis=wissensbasis)
    except Exception as e:
        logging.exception("Fehler beim Laden der Bearbeitungsseite.")
        return "Interner Serverfehler", 500

@app.route('/get_unterthemen', methods=['POST'])
@login_required
def get_unterthemen():
    thema = request.form.get('thema')
    themen_dict = lade_themen()
    unterthemen_info = {}
    if thema in themen_dict:
        for key, value in themen_dict[thema].items():
            unterthemen_info[key] = {
                'title': value['title'],
                'beschreibung': value.get('beschreibung', '')
            }
    return jsonify({'unterthemen': unterthemen_info})

def verarbeite_eintrag(eingabe_text, ausgewähltes_thema, ausgewähltes_unterthema, beschreibung_text):
    messages = [
        {"role": "user", "content": "Du bist ein Experte, der aus Transkripten Wissen extrahiert..."},
        {"role": "user", "content": f"Extrahiere ohne Verluste:\n'''{eingabe_text}'''"}
    ]
    response = contact_openai(messages, model="o3-mini")
    if not response:
        flash("Fehler bei der Zusammenfassung.", 'danger')
        return
    eintrag = {
        "thema": ausgewähltes_thema,
        "unterthema": ausgewähltes_unterthema,
        "beschreibung": beschreibung_text,
        "inhalt": response
    }
    speichere_wissensbasis(eintrag)

@app.route('/update_entry', methods=['POST'])
@login_required
def update_entry():
    try:
        data = request.get_json()
        thema = data.get('thema', '').strip()
        unterthema = data.get('unterthema', '').strip()
        beschreibung = data.get('beschreibung', '').strip()
        inhalt = data.get('inhalt', '').strip()

        if not thema or not unterthema:
            return jsonify({'success': False, 'message': 'Ungültige Daten.'}), 400

        wissensbasis = download_wissensbasis()
        if thema in wissensbasis and unterthema in wissensbasis[thema]:
            wissensbasis[thema][unterthema]['beschreibung'] = beschreibung
            wissensbasis[thema][unterthema]['inhalt'] = inhalt.split('\n')
            upload_wissensbasis(wissensbasis)
            logging.debug(f"Eintrag '{unterthema}' in Thema '{thema}' aktualisiert.")
            return jsonify({'success': True}), 200
        else:
            wissensbasis.setdefault(thema, {})[unterthema] = {
                'beschreibung': beschreibung,
                'inhalt': inhalt.split('\n')
            }
            upload_wissensbasis(wissensbasis)
            logging.debug(f"Eintrag '{unterthema}' in Thema '{thema}' neu erstellt.")
            return jsonify({'success': True}), 200
    except Exception as e:
        logging.exception("Fehler beim Aktualisieren des Eintrags.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/move_entry', methods=['POST'])
@login_required
def move_entry():
    try:
        data = request.get_json()
        thema = data.get('thema')
        unterthema = data.get('unterthema')
        direction = data.get('direction')
        wissensbasis = download_wissensbasis()

        if thema not in wissensbasis or unterthema not in wissensbasis[thema]:
            return jsonify({'success': False, 'message': 'Eintrag nicht gefunden.'}), 404

        unterthemen = list(wissensbasis[thema].keys())
        idx = unterthemen.index(unterthema)

        if direction == 'up' and idx > 0:
            unterthemen[idx], unterthemen[idx-1] = unterthemen[idx-1], unterthemen[idx]
        elif direction == 'down' and idx < len(unterthemen) - 1:
            unterthemen[idx], unterthemen[idx+1] = unterthemen[idx+1], unterthemen[idx]
        else:
            return jsonify({'success': False, 'message': 'Verschieben nicht möglich.'}), 400

        wissensbasis[thema] = {k: wissensbasis[thema][k] for k in unterthemen}
        upload_wissensbasis(wissensbasis)
        logging.debug(f"Eintrag '{unterthema}' verschoben -> {direction}.")
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.exception("Fehler beim Verschieben.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/delete_entry', methods=['POST'])
@login_required
def delete_entry():
    try:
        data = request.get_json()
        thema = data.get('thema')
        unterthema = data.get('unterthema')
        wissensbasis = download_wissensbasis()

        if thema in wissensbasis and unterthema in wissensbasis[thema]:
            del wissensbasis[thema][unterthema]
            upload_wissensbasis(wissensbasis)
            logging.debug(f"Eintrag '{unterthema}' gelöscht.")
            return jsonify({'success': True}), 200
        else:
            return jsonify({'success': False, 'message': 'Eintrag nicht gefunden.'}), 404
    except Exception as e:
        logging.exception("Fehler beim Löschen.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/sort_entries', methods=['POST'])
@login_required
def sort_entries():
    try:
        wissensbasis = download_wissensbasis()
        def sort_key(k):
            match = re.match(r'(\d+)([a-z]*)', k)
            if match:
                num = int(match.group(1))
                suf = match.group(2)
                return (num, suf)
            return (0, k)

        for thema, unterthemen in wissensbasis.items():
            sorted_keys = sorted(unterthemen.keys(), key=sort_key)
            wissensbasis[thema] = {k: wissensbasis[thema][k] for k in sorted_keys}
        upload_wissensbasis(wissensbasis)
        logging.debug("Wissensbasis sortiert.")
        return jsonify({'success': True}), 200
    except Exception as e:
        logging.exception("Fehler beim Sortieren.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/add_topic', methods=['POST'])
@login_required
def add_topic():
    try:
        data = request.get_json()
        add_type = data.get('type')

        if add_type == 'thema':
            neues_thema = data.get('thema', '').strip()
            if not neues_thema:
                return jsonify({'success': False, 'message': 'Thema darf nicht leer sein.'}), 400
            themen_dict = lade_themen()
            for thema in themen_dict.keys():
                if thema.startswith("Thema"):
                    existing_title = thema.split(':', 1)[1].strip()
                    if existing_title == neues_thema:
                        return jsonify({'success': False, 'message': 'Thema existiert bereits.'}), 400
            next_number = get_next_thema_number(themen_dict)
            thema_key = f'Thema {next_number}: {neues_thema}'
            themen_dict[thema_key] = {}
            aktualisiere_themen(themen_dict)
            flash(f'Hauptthema "{thema_key}" wurde erfolgreich hinzugefügt.', 'success')
            return jsonify({'success': True}), 200

        elif add_type == 'unterthema':
            parent_thema = data.get('parent_thema', '').strip()
            unterthema_nummer = data.get('unterthema_nummer', '').strip()
            unterthema_titel = data.get('unterthema_titel', '').strip()
            unterthema_beschreibung = data.get('unterthema_beschreibung', '').strip()
            if not parent_thema or not unterthema_nummer or not unterthema_titel:
                return jsonify({'success': False, 'message': 'Alle Felder sind erforderlich.'}), 400
            themen_dict = lade_themen()
            if parent_thema not in themen_dict:
                return jsonify({'success': False, 'message': 'Übergeordnetes Hauptthema existiert nicht.'}), 404
            if unterthema_nummer in themen_dict[parent_thema]:
                return jsonify({'success': False, 'message': 'Unterthema mit dieser Nummer existiert bereits.'}), 400
            themen_dict[parent_thema][unterthema_nummer] = {
                "title": unterthema_titel,
                "beschreibung": unterthema_beschreibung
            }
            aktualisiere_themen(themen_dict)
            flash(f'Unterthema "{unterthema_nummer}) {unterthema_titel}" hinzugefügt.', 'success')
            return jsonify({'success': True}), 200

        else:
            return jsonify({'success': False, 'message': 'Ungültiger Typ.'}), 400

    except Exception as e:
        logging.exception("Fehler beim Hinzufügen eines Themas.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/delete_topic', methods=['POST'])
@login_required
def delete_topic():
    try:
        data = request.get_json()
        thema = data.get('thema', '').strip()
        if not thema:
            return jsonify({'success': False, 'message': 'Thema darf nicht leer sein.'}), 400
        themen_dict = lade_themen()
        if thema not in themen_dict:
            return jsonify({'success': False, 'message': 'Thema existiert nicht.'}), 404
        del themen_dict[thema]
        aktualisiere_themen(themen_dict)
        flash(f'Thema "{thema}" wurde erfolgreich entfernt.', 'success')
        return jsonify({'success': True}), 200

    except Exception as e:
        logging.exception("Fehler beim Löschen eines Themas.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/upload_files', methods=['POST'])
@login_required
def upload_files():
    try:
        if 'files' not in request.files:
            return jsonify({'success': False, 'message': 'Keine Dateien in der Anfrage.'}), 400
        files = request.files.getlist('files')
        if not files:
            return jsonify({'success': False, 'message': 'Keine Dateien ausgewählt.'}), 400

        if 'uploaded_files' not in session:
            session['uploaded_files'] = []
        files_status = []
        for file in files:
            filename = secure_filename(file.filename)
            if filename == '':
                continue
            file_id = str(uuid.uuid4())
            temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_id + '_' + filename)
            file.save(temp_filepath)
            file_status = {
                'id': file_id,
                'filename': filename,
                'status': 'Hochgeladen'
            }
            session['uploaded_files'].append(file_status)
            files_status.append(file_status)

        session.modified = True
        return jsonify({'success': True, 'files': files_status}), 200
    except Exception as e:
        logging.exception("Fehler beim Hochladen von Dateien.")
        return jsonify({'success': False, 'message': 'Interner Fehler.'}), 500

@app.route('/process_file_ai', methods=['POST'])
@login_required
def process_file_ai():
    try:
        data = request.get_json()
        file_id = data.get('file_id')
        uploaded_files = session.get('uploaded_files', [])
        file_entry = next((f for f in uploaded_files if f['id'] == file_id), None)

        if not file_entry:
            return jsonify({'success': False, 'message': 'Datei nicht gefunden.'}), 404
        if file_entry['status'] != 'Hochgeladen':
            return jsonify({'success': False, 'message': 'Datei bereits verarbeitet.'}), 400

        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_id + '_' + file_entry['filename'])
        if not os.path.exists(temp_filepath):
            return jsonify({'success': False, 'message': 'Temporäre Datei nicht gefunden.'}), 404

        ext = os.path.splitext(file_entry['filename'])[1].lower()
        extracted_text = ""
        if ext == '.txt':
            with open(temp_filepath, 'r', encoding='utf-8') as f:
                extracted_text = f.read()
        elif ext == '.pdf':
            with open(temp_filepath, 'rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    extracted_text += page.extract_text() + "\n"
        elif ext in ['.doc', '.docx']:
            doc = docx.Document(temp_filepath)
            for para in doc.paragraphs:
                extracted_text += para.text + "\n"
        else:
            return jsonify({'success': False, 'message': 'Unsupported file type.'}), 400

        if not extracted_text.strip():
            file_entry['status'] = 'Fehler: Kein Text extrahiert'
            session.modified = True
            return jsonify({'success': False, 'message': 'Kein Text extrahiert.'}), 400

        themen_hierarchie = ''
        if os.path.exists(themen_datei):
            with open(themen_datei, 'r', encoding='utf-8') as f:
                themen_hierarchie = f.read()

        kategorisierung_messages = [
            {"role": "user", "content": "Du bist ein Assistent, der Texte in vorgegebene Themen..."},
            {"role": "user", "content": f"Hier die Themenhierarchie:\n\n{themen_hierarchie}\n\nText:\n{extracted_text}"}
        ]
        kategorisierung_response = contact_openai(kategorisierung_messages, model="o3-mini")
        if not kategorisierung_response:
            file_entry['status'] = 'Fehler: Kategorisierung fehlgeschlagen'
            session.modified = True
            return jsonify({'success': False, 'message': 'Kategorisierung fehlgeschlagen.'}), 500

        try:
            kategorisierung_text = kategorisierung_response
            json_match = re.search(r'\[\s*{.*}\s*\]', kategorisierung_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(0)
                json_text = re.sub(r'(\d+[a-z]*)\)\)', r'\1)', json_text)
                kategorisierte_eintraege = json.loads(json_text)
            else:
                raise ValueError("Kein gültiger JSON-Inhalt gefunden")

            for eintrag_kat in kategorisierte_eintraege:
                thema = eintrag_kat.get('thema')
                unterthema = eintrag_kat.get('unterthema')
                beschreibung = eintrag_kat.get('beschreibung', '')
                inhalt = eintrag_kat.get('inhalt')
                if thema and unterthema and inhalt:
                    speichere_wissensbasis({
                        "thema": thema,
                        "unterthema": unterthema,
                        "beschreibung": beschreibung,
                        "inhalt": inhalt
                    })

            file_entry['status'] = 'Erfolgreich verarbeitet (KI)'
            session.modified = True
            os.remove(temp_filepath)
            return jsonify({'success': True, 'message': 'Datei erfolgreich verarbeitet.'}), 200
        except (ValueError, json.JSONDecodeError):
            file_entry['status'] = 'Fehler: Parsing-Fehler'
            session.modified = True
            return jsonify({'success': False, 'message': 'Parsing-Fehler bei der Kategorisierung.'}), 500

    except Exception as e:
        logging.exception("Fehler bei der automatischen Verarbeitung der Datei.")
        return jsonify({'success': False, 'message': 'Ein interner Fehler ist aufgetreten.'}), 500

@app.route('/process_file_manual', methods=['POST'])
@login_required
def process_file_manual():
    try:
        data = request.get_json()
        file_id = data.get('file_id')
        selected_thema = data.get('thema')
        selected_unterthema = data.get('unterthema')
        beschreibung = data.get('beschreibung', '').strip()

        uploaded_files = session.get('uploaded_files', [])
        file_entry = next((f for f in uploaded_files if f['id'] == file_id), None)

        if not file_entry:
            return jsonify({'success': False, 'message': 'Datei nicht gefunden.'}), 404
        if file_entry['status'] != 'Hochgeladen':
            return jsonify({'success': False, 'message': 'Datei bereits verarbeitet.'}), 400

        temp_filepath = os.path.join(app.config['UPLOAD_FOLDER'], file_id + '_' + file_entry['filename'])
        if not os.path.exists(temp_filepath):
            return jsonify({'success': False, 'message': 'Temporäre Datei nicht gefunden.'}), 404

        ext = os.path.splitext(file_entry['filename'])[1].lower()
        extracted_text = ""
        if ext == '.txt':
            with open(temp_filepath, 'r', encoding='utf-8') as f:
                extracted_text = f.read()
        elif ext == '.pdf':
            with open(temp_filepath, 'rb') as f:
                reader = PdfReader(f)
                for page in reader.pages:
                    extracted_text += page.extract_text() + "\n"
        elif ext in ['.doc', '.docx']:
            doc = docx.Document(temp_filepath)
            for para in doc.paragraphs:
                extracted_text += para.text + "\n"
        else:
            return jsonify({'success': False, 'message': 'Unsupported file type.'}), 400

        if not extracted_text.strip():
            file_entry['status'] = 'Fehler: Kein Text extrahiert'
            session.modified = True
            return jsonify({'success': False, 'message': 'Kein Text extrahiert.'}), 400

        speichere_wissensbasis({
            "thema": selected_thema,
            "unterthema": selected_unterthema,
            "beschreibung": beschreibung,
            "inhalt": extracted_text
        })

        file_entry['status'] = 'Erfolgreich verarbeitet (Manuell)'
        session.modified = True
        os.remove(temp_filepath)
        return jsonify({'success': True, 'message': 'Datei erfolgreich manuell verarbeitet.'}), 200

    except Exception as e:
        logging.exception("Fehler bei der manuellen Verarbeitung.")
        return jsonify({'success': False, 'message': 'Ein interner Fehler ist aufgetreten.'}), 500


###########################################
# App Start
###########################################
if __name__ == "__main__":
    app.run(debug=True)#