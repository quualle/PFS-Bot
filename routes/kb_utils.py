"""
Knowledge Base utility functions for the XORA application.
This module contains functions for managing the knowledge base (Wissensbasis).
"""

import os
import json
import logging
import traceback
from datetime import datetime
from routes.utils import debug_print
from routes.openai_utils import contact_openai

# Global variables
themen_datei = '/home/PfS/themen.txt'  # Path to the topics file
service_account_path = '/home/PfS/service_account_key.json'

def download_wissensbasis(max_retries=5, backoff_factor=1):
    """
    Downloads the knowledge base from Google Cloud Storage.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Factor for exponential backoff
        
    Returns:
        dict: The downloaded knowledge base
    """
    debug_print("KB Utils", "Dummy download_wissensbasis function called")
    # Implement the actual download logic here
    # This is just a placeholder
    return {}

def upload_wissensbasis(wissensbasis, max_retries=5, backoff_factor=1):
    """
    Uploads the knowledge base to Google Cloud Storage.
    
    Args:
        wissensbasis: The knowledge base to upload
        max_retries: Maximum number of retry attempts
        backoff_factor: Factor for exponential backoff
        
    Returns:
        bool: Success status
    """
    debug_print("KB Utils", "Dummy upload_wissensbasis function called")
    # Implement the actual upload logic here
    # This is just a placeholder
    return True

def lese_themenhierarchie(dateipfad):
    """
    Reads the topic hierarchy from a file.
    
    Args:
        dateipfad: Path to the topics file
        
    Returns:
        dict: The topic hierarchy
    """
    themen_dict = {}
    try:
        with open(dateipfad, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('|')
                if len(parts) >= 2:
                    thema_nummer = parts[0].strip()
                    thema_name = parts[1].strip()
                    
                    # Check if this is a main topic or subtopic
                    if '.' not in thema_nummer:
                        # Main topic
                        themen_dict[thema_nummer] = {
                            'name': thema_name,
                            'unterthemen': {}
                        }
                    else:
                        # Subtopic
                        hauptthema_nummer = thema_nummer.split('.')[0]
                        if hauptthema_nummer in themen_dict:
                            themen_dict[hauptthema_nummer]['unterthemen'][thema_nummer] = thema_name
    except Exception as e:
        debug_print("KB Utils", f"Fehler beim Lesen der Themenhierarchie: {e}")
    
    return themen_dict

def lade_themen():
    """
    Loads the topics from the topics file.
    
    Returns:
        dict: The topic hierarchy
    """
    return lese_themenhierarchie(themen_datei)

def get_next_thema_number(themen_dict):
    """
    Gets the next available topic number.
    
    Args:
        themen_dict: The topic hierarchy
        
    Returns:
        str: The next available topic number
    """
    if not themen_dict:
        return "1"
    
    # Find the highest main topic number
    highest_num = 0
    for key in themen_dict.keys():
        try:
            num = int(key)
            highest_num = max(highest_num, num)
        except ValueError:
            pass
    
    return str(highest_num + 1)

def aktualisiere_themen(themen_dict):
    """
    Updates the topics file with the given topic hierarchy.
    
    Args:
        themen_dict: The topic hierarchy to write
        
    Returns:
        bool: Success status
    """
    try:
        with open(themen_datei, 'w', encoding='utf-8') as f:
            # Write main topics and their subtopics
            for hauptthema_num, hauptthema_info in themen_dict.items():
                hauptthema_name = hauptthema_info['name']
                f.write(f"{hauptthema_num}|{hauptthema_name}\n")
                
                # Write subtopics
                unterthemen = hauptthema_info['unterthemen']
                for unterthema_num, unterthema_name in unterthemen.items():
                    f.write(f"{unterthema_num}|{unterthema_name}\n")
        
        return True
    except Exception as e:
        debug_print("KB Utils", f"Fehler beim Aktualisieren der Themen: {e}")
        return False

def speichere_wissensbasis(eintrag):
    """
    Saves an entry to the knowledge base.
    
    Args:
        eintrag: The entry to save
        
    Returns:
        bool: Success status
    """
    debug_print("KB Utils", "Dummy speichere_wissensbasis function called")
    # Implement the actual logic here
    # This is just a placeholder
    return True
