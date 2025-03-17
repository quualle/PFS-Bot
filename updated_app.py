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

# Import the LLM-based query selector
try:
    from query_selector import select_query_with_llm, update_selection_feedback
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
        # Fallback-Konfiguration
        return {
            "tool_categories": {
                "time_query": {
                    "patterns": ["care stays", "carestays", "einsätze", "monat", "monatlich", "jahr", "jährlich", 
                               "januar", "februar", "märz", "april", "mai", "juni", "juli", "august", 
                               "september", "oktober", "november", "dezember"],
                    "default_tool": "get_care_stays_by_date_range"
                },
                "contract_query": {
                    "patterns": ["vertrag", "verträge", "contract", "contracts"],
                    "default_tool": "get_active_contracts"
                },
                "lead_query": {
                    "patterns": ["lead", "leads", "kunde", "kunden"],
                    "default_tool": "get_recent_leads"
                },
                "statistics_query": {
                    "patterns": ["statistik", "statistics", "performance", "umsatz", "revenue"],
                    "default_tool": "get_user_statistics"
                }
            },
            "fallback_tool": "get_care_stays_by_date_range",
            "force_tool_patterns": {
                "get_care_stays_by_date_range": ["im monat", "im jahr", "in 2025", "im mai", "im april", "im märz"]
            }
        }


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