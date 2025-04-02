#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PythonAnywhere Manager - Ein Werkzeug zur Fernverwaltung der PythonAnywhere-Umgebung

Dieses Skript ermöglicht:
- Ausführen von Git Pull auf dem Server
- Neustart des Webservers
- Anzeigen der Logdateien für Fehlerdiagnose
"""

import requests
import time
import os
import argparse
import sys
import datetime
import re

# Konstanten für die API
USERNAME = "PfS"  # Anpassen an deinen PythonAnywhere Benutzernamen
WEBAPP_DOMAIN = "staging-pfs.pythonanywhere.com"
PROJECT_PATH = "/home/PfS/staging"
HOST = "www.pythonanywhere.com"
ERROR_LOG_PATH = "/var/log/staging-pfs.pythonanywhere.com.error.log"
API_TOKEN = "b32d07cf8fcc4d7259aa19c305cadd44727f612c"
CONSOLE_ID = "39048079"  # ID der zu verwendenden Konsole

def get_token():
    """
    Gibt das API-Token zurück.
    """
    return API_TOKEN

def run_git_pull(token):
    """
    Führt git pull auf dem Server aus.
    """
    print("Git Pull wird ausgeführt...")
    
    # Befehl über die vorhandene Konsole ausführen
    response = requests.post(
        f'https://{HOST}/api/v0/user/{USERNAME}/consoles/{CONSOLE_ID}/send_input/',
        headers={'Authorization': f'Token {token}'},
        data={"input": f"cd {PROJECT_PATH} && git pull\n"}
    )
    
    if response.status_code != 200:
        print(f"Fehler beim Ausführen von git pull: {response.status_code} - {response.text}")
        return False
    
    print(f"Git Pull-Befehl gesendet. Warte auf Ergebnis...")
    
    # Längere Wartezeit für die Ausführung
    time.sleep(10)
    
    # Ausgabe abrufen
    output_response = requests.get(
        f'https://{HOST}/api/v0/user/{USERNAME}/consoles/{CONSOLE_ID}/get_latest_output/',
        headers={'Authorization': f'Token {token}'}
    )
    
    if output_response.status_code == 200:
        output = output_response.json().get('output', '')
        print("\nGit Pull Ergebnis:")
        print(output)
        
        if "Already up to date" in output:
            print("Repository ist bereits aktuell.")
        elif "error:" in output.lower() or "fatal:" in output.lower():
            print("FEHLER beim Git Pull!")
            return False
        else:
            print("Git Pull erfolgreich abgeschlossen.")
        
        return True
    else:
        print(f"Fehler beim Abrufen des Git Pull Ergebnisses: {output_response.status_code}")
        # Trotzdem weitermachen
        return True

def restart_webapp(token):
    """
    Startet die Web-Anwendung auf PythonAnywhere neu.
    """
    print("\nWeb-Server wird neu gestartet...")
    
    response = requests.post(
        f'https://{HOST}/api/v0/user/{USERNAME}/webapps/{WEBAPP_DOMAIN}/reload/',
        headers={'Authorization': f'Token {token}'}
    )
    
    if response.status_code == 200:
        print("Web-Server erfolgreich neu gestartet!")
        return True
    else:
        print(f"Fehler beim Neustarten des Web-Servers: {response.status_code} - {response.text}")
        return False

def get_error_logs(token, lines=20):
    """
    Zeigt die letzten Zeilen des Fehler-Logs und prüft, ob sie aktuell sind.
    """
    print(f"\nLetzte {lines} Zeilen des Fehler-Logs werden abgerufen...")
    
    response = requests.get(
        f'https://{HOST}/api/v0/user/{USERNAME}/files/path{ERROR_LOG_PATH}',
        headers={'Authorization': f'Token {token}'}
    )
    
    if response.status_code == 200:
        log_lines = response.text.split('\n')
        relevant_logs = log_lines[-lines:]
        
        # Zeitvalidierung - prüfe, ob die neuesten Logs aktuell sind
        current_time = datetime.datetime.now()
        # Server-Zeit ist 2 Stunden früher als lokale Zeit
        server_time = current_time - datetime.timedelta(hours=2)
        server_time_str = server_time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Suche nach Zeitstempeln in den Logs
        newest_log_time = None
        for line in relevant_logs:
            if line.strip():
                try:
                    # Verwende einen regulären Ausdruck, um den Zeitstempel zu extrahieren
                    # Format: YYYY-MM-DD HH:MM:SS,mmm
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}:', line)
                    if timestamp_match:
                        timestamp_str = timestamp_match.group(1)
                        log_time = datetime.datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                        if newest_log_time is None or log_time > newest_log_time:
                            newest_log_time = log_time
                except (ValueError, IndexError) as e:
                    # DEBUG: Temporär die fehlerhafte Zeile ausgeben
                    # print(f"Fehler beim Parsen des Zeitstempels in Zeile: {line[:50]}... - {str(e)}")
                    continue
        
        print("\n--- BEGINN DES FEHLER-LOGS ---")
        print('\n'.join(relevant_logs))
        print("--- ENDE DES FEHLER-LOGS ---")
        
        # Hinweis zur Aktualität der Logs
        if newest_log_time:
            time_diff = server_time - newest_log_time
            minutes_diff = time_diff.total_seconds() / 60
            
            if minutes_diff <= 5:
                print(f"\nHinweis: Die neuesten Logs sind von {newest_log_time.strftime('%Y-%m-%d %H:%M:%S')} "
                      f"(aktuell: {server_time_str}, vor ca. {int(minutes_diff)} Minuten) - AKTUELL")
            else:
                print(f"\nACHTUNG: Die neuesten Logs sind von {newest_log_time.strftime('%Y-%m-%d %H:%M:%S')} "
                      f"(aktuell: {server_time_str}, vor ca. {int(minutes_diff)} Minuten) - MÖGLICHERWEISE VERALTET")
                print("Die Logs sind möglicherweise nicht aktuell. Es kann sein, dass neuere Fehler noch nicht erfasst wurden.")
        else:
            print("\nHinweis: Zeitstempel in den Logs konnte nicht ausgewertet werden. Bitte prüfe die Log-Formatierung.")
            # DEBUG: Ausgabe von Beispielzeilen zur Diagnose
            print(f"Beispiel-Logzeilen zum Debuggen:")
            for i, line in enumerate(relevant_logs[:3]):
                if line.strip():
                    print(f"Zeile {i+1}: {line[:50]}...")
        
        return True
    else:
        print(f"Fehler beim Abrufen des Fehler-Logs: {response.status_code} - {response.text}")
        return False

def trigger_website_for_logs():
    """
    Ruft die Website auf, um sicherzustellen, dass die Logs aktualisiert werden.
    """
    url = "https://staging-pfs.pythonanywhere.com/"
    print(f"\nRufe die Website auf, um aktuelle Logs zu generieren: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        status = response.status_code
        print(f"Website-Aufruf abgeschlossen (Status: {status})")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Fehler beim Aufruf der Website: {str(e)}")
        return False

def watch_logs(token, interval=5, lines=10):
    """
    Überwacht kontinuierlich die Fehler-Logs mit regelmäßigen Updates.
    """
    print(f"Log-Überwachung gestartet (Aktualisierung alle {interval} Sekunden, Ctrl+C zum Beenden)...")
    
    last_content = ""
    try:
        while True:
            response = requests.get(
                f'https://{HOST}/api/v0/user/{USERNAME}/files/path{ERROR_LOG_PATH}',
                headers={'Authorization': f'Token {token}'}
            )
            
            if response.status_code == 200:
                log_lines = response.text.split('\n')
                current_content = '\n'.join(log_lines[-lines:])
                
                if current_content != last_content:
                    print("\n--- NEUE LOG-EINTRÄGE ---")
                    print(current_content)
                    print("--- ENDE NEUE LOG-EINTRÄGE ---")
                    last_content = current_content
            else:
                print(f"Fehler beim Abrufen des Logs: {response.status_code}")
            
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nLog-Überwachung beendet.")

def deploy():
    """
    Führt den vollständigen Deployment-Workflow aus:
    1. Git Pull
    2. Server-Neustart
    3. Log-Anzeige
    """
    token = get_token()
    
    if run_git_pull(token):
        # Kurze Wartezeit nach Git Pull
        time.sleep(2)
        
        if restart_webapp(token):
            # Längere Wartezeit für den Neustart des Servers
            print("Warte 25 Sekunden, bis der Server neu gestartet ist...")
            time.sleep(25)
            
            # Website aufrufen, um Logs zu aktualisieren
            trigger_website_for_logs()
            
            # Längere Wartezeit, damit die Logs geschrieben werden
            print("Warte 15 Sekunden, damit die Fehlerlogs aktualisiert werden...")
            time.sleep(15)
            
            # Logs nach dem Neustart anzeigen
            get_error_logs(token, lines=30)
            
            print("\nDeployment abgeschlossen!")
        else:
            print("Deployment teilweise fehlgeschlagen: Server-Neustart fehlgeschlagen")
    else:
        print("Deployment fehlgeschlagen: Git Pull fehlgeschlagen")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PythonAnywhere Manager - Fernsteuerung für die PythonAnywhere-Umgebung")
    parser.add_argument("--pull", action="store_true", help="Führt nur Git Pull aus")
    parser.add_argument("--restart", action="store_true", help="Startet nur den Webserver neu")
    parser.add_argument("--logs", action="store_true", help="Zeigt nur die Fehler-Logs an")
    parser.add_argument("--watch", action="store_true", help="Überwacht kontinuierlich die Fehler-Logs")
    parser.add_argument("--lines", type=int, default=20, help="Anzahl der anzuzeigenden Log-Zeilen (Standard: 20)")
    
    args = parser.parse_args()
    token = get_token()
    
    # Wenn keine spezifischen Flags gesetzt sind, führe deploy() aus
    if not (args.pull or args.restart or args.logs or args.watch):
        deploy()
    else:
        # Einzelne Aktionen ausführen
        if args.pull:
            run_git_pull(token)
        
        if args.restart:
            restart_webapp(token)
        
        if args.logs:
            get_error_logs(token, args.lines)
        
        if args.watch:
            watch_logs(token)
