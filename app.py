import os
import json
import re
import time
import logging
import datetime
from functools import wraps
import uuid
import tempfile
import requests  # Added import for requests

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_wtf import CSRFProtect
from flask_session import Session
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account
from google.cloud import bigquery
from werkzeug.utils import secure_filename
import openai
import tiktoken

# Zusätzliche Importe für Dateiverarbeitung
from PyPDF2 import PdfReader
import docx

# Für Datum / Statistik
from datetime import datetime

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
    """
    Speichert das Feedback + gesamten Chat in FEEDBACK_FOLDER.
    feedback_type: "positive" oder "negative"
    comment: user-Kommentar
    chat_history: Liste mit {user, bot}
    """
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

def calculate_chat_stats():
    """
    Liest alle Chatlog-Dateien aus CHATLOG_FOLDER und zählt die Gesamtanzahl an Nachrichten (User-Bot).
    Außerdem: Zählung nur für dieses Jahr, diesen Monat, heute.
    """
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

        # Name_YYYY-mm-dd_HH-MM-SS.txt
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

def get_next_thema_number(themen_dict):
    numbers = []
    for thema in themen_dict.keys():
        match = re.match(r'Thema\s+(\d+):\s+.*', thema)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers)+1 if numbers else 1

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
    else:
        flash("Thema und Unterthema müssen angegeben werden.", 'warning')

def lade_themen():
    return lese_themenhierarchie(themen_datei)

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
        LIMIT 50
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
        LIMIT 50
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
        LIMIT 50
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

def contact_openai(messages, model=None):
    model = 'o1-preview'
    debug_print("API Calls", "contact_openai wurde aufgerufen – fest auf o1-preview gesetzt.")
    try:
        response = openai.chat.completions.create(model=model, messages=messages)
        if response and response.choices:
            antwort_content = response.choices[0].message.content.strip()
            debug_print("API Calls", f"Antwort von OpenAI: {antwort_content}")
            return antwort_content
        else:
            antwort_content = "Keine Antwort erhalten."
            debug_print("API Calls", antwort_content)
            return antwort_content
    except Exception as e:
        debug_print("API Calls", f"Fehler: {e}")
        flash(f"Ein Fehler ist aufgetreten: {e}", 'danger')
        return None

def count_tokens(messages, model=None):
    model = 'o1-preview'
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


@app.route('/test_session')
def test_session():
    # Test-Wert in die Session setzen
    test_value = "Testdaten " + datetime.now().strftime("%H:%M:%S")
    session['test_value'] = test_value
    session['test_email'] = "test@example.com"
    session['test_seller_id'] = "test_id_123"
    
    # Stellen Sie sicher, dass die Änderungen gespeichert werden
    session.modified = True
    
    output = "<h1>Session-Test</h1>"
    output += f"<p>Test-Werte gesetzt: {test_value}</p>"
    
    # Alle Session-Werte anzeigen
    output += "<h2>Alle Session-Werte:</h2><ul>"
    for key, value in session.items():
        output += f"<li><strong>{key}:</strong> {value}</li>"
    output += "</ul>"
    
    return output

@app.route('/test_bigquery')
def test_bigquery():
    try:
        service_account_path = '/home/PfS/gcpxbixpflegehilfesenioren-a47c654480a8.json'
        client = bigquery.Client.from_service_account_json(service_account_path)
        
        # E-Mail aus Session holen
        email = session.get('email') or session.get('google_user_email', '')
        
        # Abfrage mit WHERE-Klausel
        query = """
        SELECT email, _id 
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.proto_users` 
        WHERE email = @email
        LIMIT 10
        """
        
        # Parameter definieren - DAS IST DER WICHTIGE TEIL
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("email", "STRING", email)
            ]
        )
        
        # Abfrage mit Parametern ausführen
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        output = "<h1>BigQuery-Test</h1>"
        output += f"<p>Abfrage für E-Mail: {email}</p>"
        output += "<table border='1'><tr><th>E-Mail</th><th>ID</th></tr>"
        
        rows_found = False
        for row in results:
            rows_found = True
            output += f"<tr><td>{row['email']}</td><td>{row['_id']}</td></tr>"
        
        output += "</table>"
        
        if not rows_found:
            output += f"<p>Keine Daten für E-Mail '{email}' gefunden!</p>"
            
        return output
    except Exception as e:
        return f"Fehler: {str(e)}"

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

@app.route('/check_seller_id')
def check_seller_id():
    """Zeigt Informationen über die aktuelle Benutzer-Session an."""
    session_info = {
        'user_id': session.get('user_id'),
        'user_name': session.get('user_name'),
        'email': session.get('email'),
        'seller_id': session.get('seller_id'),
        'is_admin': session.get('admin_logged_in', False)
    }
    
    # Formatieren als HTML für einfaches Lesen
    output = "<h1>Benutzer-Informationen</h1>"
    output += "<pre>" + json.dumps(session_info, indent=2, ensure_ascii=False) + "</pre>"
    
    # Wenn seller_id vorhanden ist, zeige einige Beispieldaten aus BigQuery
    seller_id = session.get('seller_id')
    if seller_id:
        output += "<h2>BigQuery-Test</h2>"
        try:
            # Versuche, KPIs zu berechnen
            kpis = calculate_kpis_for_seller(seller_id)
            output += "<h3>KPIs:</h3>"
            output += "<pre>" + json.dumps(kpis, indent=2, ensure_ascii=False) + "</pre>"
            
            # Prüfe, ob Leads abgerufen werden können
            leads = get_leads_for_seller(seller_id)
            output += f"<p>Anzahl gefundener Leads: {len(leads)}</p>"
            
            # Prüfe, ob Verträge abgerufen werden können
            contracts = get_contracts_for_seller(seller_id)
            output += f"<p>Anzahl gefundener Verträge: {len(contracts)}</p>"
        except Exception as e:
            output += f"<p style='color: red;'>Fehler beim Abrufen von BigQuery-Daten: {str(e)}</p>"
    
    return output

###########################################
# Neue Route: Toggle Notfall Mode
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

###########################################
# Feedback speichern
###########################################
@app.route('/store_feedback', methods=['POST'])
def store_feedback_route():
    """
    Erwartet:
      - feedback_type (str): "positive" oder "negative"
      - comment (str): Kommentar
    Speichert das Feedback inkl. Chatverlauf in feedback/.
    """
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

@app.route('/', methods=['GET', 'POST'])
def chat():
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        
        # Wenn kein Nutzername, direkt zu Google weiterleiten statt auf die Chat-Seite
        if not user_name:
            return redirect(url_for('google_login'))

        # Verkäufer-ID aus der Session abrufen
        seller_id = session.get('seller_id')
        
        chat_key = f'chat_history_{user_id}'
        if chat_key not in session:
            session[chat_key] = []
        chat_history = session[chat_key]

        if request.method == 'POST':
            user_message = request.form.get('message', '').strip()
            notfall_aktiv = (request.form.get('notfallmodus') == '1')
            notfall_art = request.form.get('notfallart', '').strip()

            if not user_message:
                flash("Bitte geben Sie eine Nachricht ein.", 'warning')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Bitte geben Sie eine Nachricht ein.'}), 400
                return redirect(url_for('chat'))

            wissensbasis = download_wissensbasis()
            if not wissensbasis:
                flash("Die Wissensbasis konnte nicht geladen werden.", 'danger')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Die Wissensbasis konnte nicht geladen werden.'}), 500
                return redirect(url_for('chat'))

            wissens_text = json.dumps(wissensbasis, ensure_ascii=False, indent=2)
            
            # BigQuery-Daten abrufen, wenn Verkäufer-ID vorhanden ist (NEU)
            bigquery_data = {}
            if seller_id:
                # Prüfen, nach welchen Daten der Benutzer gefragt hat
                message_lower = user_message.lower()
                
                # KPIs abfragen
                if any(kw in message_lower for kw in ["kpi", "kennzahl", "leistung", "statistik", "performance"]):
                    bigquery_data = get_seller_data(seller_id, 'kpis')
                
                # Leads abfragen
                elif any(kw in message_lower for kw in ["lead", "kunde", "interessent"]):
                    bigquery_data = get_seller_data(seller_id, 'leads')
                
                # Verträge abfragen
                elif any(kw in message_lower for kw in ["vertrag", "verträge", "contract"]):
                    bigquery_data = get_seller_data(seller_id, 'contracts')
                
                # Haushalte abfragen
                elif any(kw in message_lower for kw in ["haushalt", "wohnung", "adresse"]):
                    bigquery_data = get_seller_data(seller_id, 'households')
                
                # Alle Daten abfragen (für allgemeine Anfragen)
                elif any(kw in message_lower for kw in ["daten", "übersicht", "alles", "zusammenfassung"]):
                    bigquery_data = get_seller_data(seller_id)

            if notfall_aktiv:
                session['notfall_mode'] = True
                user_message = (
                    f"ACHTUNG NOTFALL - Thema 9: Notfälle & Vertragsgefährdungen.\n"
                    f"Ausgewählte Notfalloption(en): {notfall_art}\n\n"
                    + user_message
                )
                log_notfall_event(user_id, notfall_art, user_message)
            else:
                session.pop('notfall_mode', None)

            # Prompt inkl. Name und BigQuery-Daten (NEU)
            prompt_text = (
                f"Der Name deines Gesprächspartners lautet {user_name}.\n"
                "Du bist ein hilfreicher Assistent namens XORA, der Fragen anhand einer Wissensbasis beantwortet. "
                "Deine Antworten sollen gut lesbar durch Absätze sein. Jedoch nicht zu viele Absätze, damit die optische vertikale Streckung nicht zu groß wird. "
                "Beginne deine Antwort nicht mit Leerzeichen, sondern direkt mit dem Inhalt. "
            )
            
            # Verkäufer-ID zur Prompt hinzufügen, wenn vorhanden (NEU)
            if seller_id:
                prompt_text += f"Du sprichst mit einem Vertriebspartner mit der ID {seller_id}. "
                
                # BigQuery-Daten zur Prompt hinzufügen, wenn vorhanden (NEU)
                if bigquery_data:
                    bigquery_text = json.dumps(bigquery_data, ensure_ascii=False, indent=2)
                    prompt_text += f"\n\nHier sind die relevanten Daten aus dem System:\n{bigquery_text}\n\n"
            
            # Prompt vervollständigen
            prompt_text += (
                "Wenn die Antwort nicht in der Wissensbasis enthalten ist, erfindest du nichts, "
                "sondern sagst, dass du es nicht weißt. "
                f"Hier die Frage:\n'''{user_message}'''\n\n"
                f"Dies ist die Wissensbasis:\n{wissens_text}"
            )
            
            messages = [
                {
                    "role": "user",
                    "content": prompt_text
                }
            ]

            token_count = count_tokens(messages, model='o1-preview')
            debug_print("API Calls", f"Anzahl Tokens: {token_count}")

            antwort = contact_openai(messages, model='o1-preview')
            if antwort:
                chat_history.append({'user': user_message, 'bot': antwort})
                session[chat_key] = chat_history
                store_chatlog(user_name, chat_history)

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'response': antwort}), 200

                return redirect(url_for('chat'))
            else:
                flash("Es gab ein Problem bei der Kommunikation mit dem Bot.", 'danger')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Problem bei Kommunikation'}), 500
                return redirect(url_for('chat'))

        stats = calculate_chat_stats()
        return render_template('chat.html', chat_history=chat_history, stats=stats)

    except Exception as e:
        logging.exception("Fehler in chat-Funktion.")
        flash("Ein unerwarteter Fehler ist aufgetreten.", 'danger')
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Interner Serverfehler.'}), 500
        return "Interner Serverfehler", 500


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
                # KI-Extraktion
                extraktion_messages = [
                    {"role": "user", "content": "Du bist ein Experte, der aus Transkripten Wissen extrahiert..."},
                    {"role": "user", "content": f"Extrahiere ohne Verluste:\n'''{eingabe_text}'''"}
                ]
                extraktion_response = contact_openai(extraktion_messages, model="o1")
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

                # Kategorisierung
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
                kategorisierung_response = contact_openai(kategorisierung_messages, model="o1")
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

@app.route('/debug', methods=['GET', 'POST'])
def debug_page():
    if request.method == 'POST':
        for category in DEBUG_CATEGORIES.keys():
            DEBUG_CATEGORIES[category] = request.form.get(category) == 'on'
        flash("Debug-Einstellungen aktualisiert.", 'success')
        return redirect(url_for('admin'))
    return render_template('debug.html', debug_categories=DEBUG_CATEGORIES)

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
    response = contact_openai(messages, model="o1")
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
        index = unterthemen.index(unterthema)

        if direction == 'up' and index > 0:
            unterthemen[index], unterthemen[index-1] = unterthemen[index-1], unterthemen[index]
        elif direction == 'down' and index < len(unterthemen) - 1:
            unterthemen[index], unterthemen[index+1] = unterthemen[index+1], unterthemen[index]
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
        kategorisierung_response = contact_openai(kategorisierung_messages, model="o1")
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

if __name__ == "__main__":
    app.run(debug=True)