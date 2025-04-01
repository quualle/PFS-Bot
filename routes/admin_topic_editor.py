# routes/admin_topic_editor.py

import os
import re
import json
import logging
import traceback
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from functools import wraps
from routes.utils import login_required, debug_print
from routes.openai_utils import contact_openai
from routes.kb_utils import (
    download_wissensbasis, upload_wissensbasis, 
    lade_themen, aktualisiere_themen, get_next_thema_number, 
    speichere_wissensbasis, themen_datei
)



# Variables that need to be imported or configured
# themen_datei is now imported from kb_utils

# Blueprint definition
admin_topic_editor_bp = Blueprint('admin_topic_editor', __name__, url_prefix='/admin')


# Routes moved from app.py

@admin_topic_editor_bp.route('/', methods=['GET', 'POST'])
@login_required
def admin():
    """
    Main admin page for managing the knowledge base (Wissensbasis).
    Allows adding new entries either manually or with AI assistance.
    """
    try:
        themen_dict = lade_themen()
        logging.debug("Themen_dict: %s", themen_dict)

        if request.method == 'POST':
            eingabe_text = request.form.get('eingabe_text', '').strip()
            if not eingabe_text:
                flash('Bitte geben Sie einen Wissenseintrag ein.', 'warning')
                return redirect(url_for('admin_topic_editor.admin'))

            ki_aktiviert = (request.form.get('ki_var') == 'on')
            
            if ki_aktiviert:
                # KI-Extraktion (Beispiel)
                extraktion_messages = [
                    {"role": "user", "content": "Du bist ein Experte, der aus Transkripten Wissen extrahiert..."},
                    {"role": "user", "content": f"Extrahiere ohne Verluste:\n'''{eingabe_text}'''"}
                ]
                extraktion_response = contact_openai(extraktion_messages, model="gpt-4o")
                if not extraktion_response:
                    flash("Fehler bei der Wissensextraktion durch die KI.", 'danger')
                    return redirect(url_for('admin_topic_editor.admin'))

                try:
                    extraktion_text = extraktion_response
                    debug_print("Bearbeiten von Einträgen", "Extraktionsergebnis: " + extraktion_text)
                except Exception as e:
                    debug_print("Bearbeiten von Einträgen", f"Fehler: {e}")
                    flash("Fehler bei der Wissensextraktion.", 'danger')
                    return redirect(url_for('admin_topic_editor.admin'))

                # Kategorisierung (Beispiel)
                themen_hierarchie = ''
                if os.path.exists(themen_datei):
                    with open(themen_datei, 'r', encoding='utf-8') as f:
                        themen_hierarchie = f.read()

                kategorisierung_messages = [
                    {"role": "user", "content": "Du bist ein Assistent, der Texte in vorgegebene Themen..."},
                    {"role": "user", "content": f"Hier die Themenhierarchie:\n\n{themen_hierarchie}\n\nText:\n{extraktion_text}"}
                ]
                kategorisierung_response = contact_openai(kategorisierung_messages, model="gpt-4o")
                if not kategorisierung_response:
                    flash("Fehler bei der Themenkategorisierung.", 'danger')
                    return redirect(url_for('admin_topic_editor.admin'))

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
                    return redirect(url_for('admin_topic_editor.admin'))

                verarbeite_eintrag(eingabe_text, ausgewähltes_thema, ausgewähltes_unterthema, beschreibung_text)
                flash("Wissenseintrag gespeichert.", 'success')

            return redirect(url_for('admin_topic_editor.admin'))

        if not themen_dict:
            flash("Bitte fügen Sie zuerst ein Thema hinzu.", 'warning')
            return redirect(url_for('admin_topic_editor.admin'))
            
        return render_template('admin.html', themen_dict=themen_dict)

    except Exception as e:
        logging.exception("Fehler in admin-Funktion.")
        flash("Ein unerwarteter Fehler ist aufgetreten.", 'danger')
        return render_template('admin.html', themen_dict={})


@admin_topic_editor_bp.route('/edit', methods=['GET'])
@login_required
def edit():
    """Page for editing the knowledge base entries."""
    try:
        wissensbasis = download_wissensbasis()
        logging.debug("Wissensbasis geladen: %s", wissensbasis)
        return render_template('edit.html', wissensbasis=wissensbasis)
    except Exception as e:
        logging.exception("Fehler beim Laden der Bearbeitungsseite.")
        return "Interner Serverfehler", 500


@admin_topic_editor_bp.route('/get_unterthemen', methods=['POST'])
@login_required
def get_unterthemen():
    """AJAX endpoint to get subtopics for a selected main topic."""
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
    """Process an entry and save it to the knowledge base."""
    messages = [
        {"role": "user", "content": "Du bist ein Experte, der aus Transkripten Wissen extrahiert..."},
        {"role": "user", "content": f"Extrahiere ohne Verluste:\n'''{eingabe_text}'''"}
    ]
    response = contact_openai(messages, model="gpt-4o")
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


@admin_topic_editor_bp.route('/update_entry', methods=['POST'])
@login_required
def update_entry():
    """AJAX endpoint to update an existing knowledge base entry."""
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


@admin_topic_editor_bp.route('/move_entry', methods=['POST'])
@login_required
def move_entry():
    """AJAX endpoint to move an entry up or down within its topic."""
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


@admin_topic_editor_bp.route('/delete_entry', methods=['POST'])
@login_required
def delete_entry():
    """AJAX endpoint to delete an entry from the knowledge base."""
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


@admin_topic_editor_bp.route('/sort_entries', methods=['POST'])
@login_required
def sort_entries():
    """AJAX endpoint to sort all entries within their topics."""
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


@admin_topic_editor_bp.route('/add_topic', methods=['POST'])
@login_required
def add_topic():
    """AJAX endpoint to add a new main topic or subtopic."""
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


@admin_topic_editor_bp.route('/delete_topic', methods=['POST'])
@login_required
def delete_topic():
    """AJAX endpoint to delete a topic."""
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
