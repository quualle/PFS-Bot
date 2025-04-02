"""
Chat-Utility-Funktionen für die XORA-Anwendung.
Diese Datei enthält Funktionen für das Chat-Management, Konversationsmanagement und die Verwaltung 
von Nutzerdialogen.
"""
import json
import time
import logging
import datetime
import os
from flask import session
from routes.utils import debug_print
from routes.kb_utils import download_wissensbasis

def conversation_manager(user_message, conversation_data=None):
    """
    Verwaltet die Konversationshistorie und -logik für Chat-Anfragen
    und bereitet alles für den Aufruf an OpenAI vor.
    
    Args:
        user_message: Die aktuelle Benutzernachricht
        conversation_data: Optional, zusätzliche Daten für die Konversation
        
    Returns:
        Ein Dict mit allen nötigen Daten für die Weiterverarbeitung
    """
    # Implementation hier kopieren...
    pass

def extract_date_params(text):
    """
    Extrahiert Datums- und Zeitparameter aus einem Text.
    Unterstützt verschiedene Formate und relative Angaben.
    
    Args:
        text: Der zu analysierende Text
        
    Returns:
        Ein Dict mit extrahierten Datums- und Zeitparametern
    """
    # Implementation hier kopieren...
    pass

def select_optimal_tool_with_reasoning(messages, available_tools):
    """
    Wählt das optimale Tool basierend auf der Benutzernachricht aus
    und liefert eine Begründung für die Auswahl.
    
    Args:
        messages: Die Konversationshistorie
        available_tools: Die verfügbaren Tools
        
    Returns:
        Das ausgewählte Tool und die Begründung für die Auswahl
    """
    # Implementation hier kopieren...
    pass

def load_tool_config():
    """
    Lädt die Tool-Konfiguration aus einer Datei.
    
    Returns:
        Die geladene Tool-Konfiguration
    """
    # Implementation hier kopieren...
    pass

def calculate_chat_stats():
    """
    Berechnet Statistiken über Chat-Interaktionen.
    
    Returns:
        Ein Dict mit den berechneten Statistiken
    """
    total_count = 0
    year_count = 0
    month_count = 0
    day_count = 0

    now = datetime.datetime.now()
    current_year = now.year
    current_month = now.month
    current_day = now.day

    CHATLOG_FOLDER = 'chatlogs'
    
    if not os.path.exists(CHATLOG_FOLDER):
        return {
            'total': 0,
            'year': 0,
            'month': 0,
            'today': 0
        }

    for filename in os.listdir(CHATLOG_FOLDER):
        if not filename.endswith(".txt"):
            continue
        
        filepath = os.path.join(CHATLOG_FOLDER, filename)
        try:
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
        except Exception as e:
            # Fehler beim Lesen der Datei überspringen
            continue

    return {
        'total': total_count,
        'year': year_count,
        'month': month_count,
        'today': day_count
    }

def store_chatlog(user_name, chat_history):
    """
    Speichert den Chatverlauf als Textdatei.
    
    Args:
        user_name: Der Name des Benutzers
        chat_history: Die zu speichernde Chat-Historie
    """
    if not user_name:
        user_name = "Unbekannt"
    
    # Make sure the directory exists
    CHATLOG_FOLDER = 'chatlogs'
    os.makedirs(CHATLOG_FOLDER, exist_ok=True)
    
    # Use just the date for the filename (not time) to group all chats from same day
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    session_id = session.get('user_id', 'unknown')
    
    # Create a unique filename based on user, date and session ID
    filename = f"{user_name}_{date_str}_{session_id}.txt"
    filepath = os.path.join(CHATLOG_FOLDER, filename)
    
    # Write the complete chat history to the file (overwrite existing)
    with open(filepath, 'w', encoding='utf-8') as f:
        # Add a timestamp for this update
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Add a header
        f.write(f"=== CHAT LOG: {user_name} ===\n")
        f.write(f"=== UPDATED: {date_str} {current_time} ===\n\n")
        
        # Write each message in the chat history
        for message in chat_history:
            role = message.get('role', 'unknown')
            content = message.get('content', '')
            
            # Skip system messages
            if role == 'system':
                continue
                
            # Format the message
            if role == 'user':
                f.write(f"USER: {content}\n\n")
            elif role == 'assistant':
                f.write(f"BOT: {content}\n\n")
            else:
                f.write(f"{role.upper()}: {content}\n\n")
        
        f.write("="*50 + "\n")
    
    return filepath
