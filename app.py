import os
import json
import re
import time
import logging
import datetime
from functools import wraps
import uuid
import tempfile

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_wtf import CSRFProtect
from flask_session import Session
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account
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

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your_default_secret_key')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# Sicherheitskonfiguration der Session
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

Session(app)

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

def store_chatlog(user_id, chat_history):
    """
    Speichert den Chatverlauf als Textdatei in CHATLOG_FOLDER.
    Dateiname enthält Datum + Uhrzeit, damit man es leicht zuordnen kann.
    """
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp_str}_user-{user_id}.txt"
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
    timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp_str}_feedback.txt"
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

        # Datum aus dem Dateinamen parsen: "YYYY-mm-dd_HH-MM-SS_user-xxxx.txt"
        try:
            date_str = filename.split("_")[0]  # "YYYY-mm-dd"
            y, m, d = date_str.split("-")
            y, m, d = int(y), int(m), int(d)
        except:
            # Falls das nicht parsebar ist, zählen wir die Datei nicht in year/month/day
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
        # 4 tokens pro Nachricht (siehe OpenAI Doku)
        token_count += 4
    # zusätzlich 2 tokens für das System
    token_count += 2
    return token_count

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
# Chat Route
###########################################
@app.route('/', methods=['GET', 'POST'])
def chat():
    try:
        user_id = session.get('user_id')
        if not user_id:
            flash("Bitte loggen Sie sich ein.", 'danger')
            return redirect(url_for('login'))

        chat_key = f'chat_history_{user_id}'
        if chat_key not in session:
            session[chat_key] = []
        chat_history = session[chat_key]

        if request.method == 'POST':
            user_message = request.form.get('message', '').strip()
            notfall_aktiv = (request.form.get('notfallmodus') == '1')
            notfall_art = request.form.get('notfallart', '').strip()  # ggf. kommaseparierte Liste

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

            # Notfallmodus: Format laut Anforderung
            if notfall_aktiv:
                session['notfall_mode'] = True
                original_user_msg = user_message
                user_message = (
                    f"Notfall vom User gemeldet: {original_user_msg}\n"
                    f"Antworte mithilfe der Inhalte aus Kapitel 9, Thema {notfall_art}"
                )
                log_notfall_event(user_id, notfall_art, original_user_msg)
            else:
                session.pop('notfall_mode', None)

            # Prompt
            messages = [
                {
                    "role": "user",
                    "content": (
                        "Du bist ein hilfreicher Assistent, der Fragen anhand einer Wissensbasis beantwortet. "
                        "Deine Antworten sollen gut lesbar durch absätze sein. Jedoch nicht zu viele Absätze, damit die optische vertikale Streckung nicht zu groß wird. "
                        "Beginne deine Antwort nicht mit Leerzeichen, sondern direkt mit dem Inhalt. "
                        "Wenn die Antwort nicht in der Wissensbasis enthalten ist, erfindest du nichts, "
                        "sondern sagst, dass du es nicht weißt. "
                        f"Hier die Frage:\n'''{user_message}'''\n\n"
                        f"Dies ist die Wissensbasis:\n{wissens_text}"
                    )
                }
            ]

            token_count = count_tokens(messages, model='o1-preview')
            debug_print("API Calls", f"Anzahl Tokens: {token_count}")

            antwort = contact_openai(messages, model='o1-preview')
            if antwort:
                session[chat_key].append({'user': user_message, 'bot': antwort})
                store_chatlog(user_id, session[chat_key])

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'response': antwort}), 200

                return redirect(url_for('chat'))
            else:
                flash("Es gab ein Problem bei der Kommunikation mit dem Bot.", 'danger')
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({'error': 'Problem bei Kommunikation'}), 500
                return redirect(url_for('chat'))

        # Statistik abrufen und an Template übergeben
        stats = calculate_chat_stats()
        return render_template('chat.html', chat_history=chat_history, stats=stats)

    except Exception as e:
        logging.exception("Fehler in chat-Funktion.")
        flash("Ein unerwarteter Fehler ist aufgetreten.", 'danger')
        if request.headers.get('X-Requested-With'):
            return jsonify({'error': 'Interner Serverfehler.'}), 500
        return "Interner Serverfehler", 500

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
            return redirect(url_for('login'))
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
        password = request.form.get('password', '')
        admin_password = os.getenv('ADMIN_PASSWORD', '')
        if password == admin_password:
            session['admin_logged_in'] = True
            flash('Erfolgreich eingeloggt.', 'success')
            return redirect(url_for('admin'))
        else:
            flash('Falsches Passwort.', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('admin_logged_in', None)
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
