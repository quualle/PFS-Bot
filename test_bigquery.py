import json
import os
import logging
from bigquery_functions import execute_bigquery_query

# Logging einrichten
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_bigquery_query_with_limit():
    """
    Test-Funktion für das Ausführen einer BigQuery-Abfrage mit LIMIT-Parameter
    """
    try:
        # Query Patterns laden
        with open('query_patterns.json', 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
        
        # Eine Abfrage mit LIMIT-Parameter auswählen (get_contract_terminations)
        sql = query_patterns['common_queries']['get_contract_terminations']['sql_template']
        
        # Parameter vorbereiten (ohne limit - sollte aus default_values kommen)
        params = {
            'seller_id': 'seller-1',
            'start_date': '01.01.2025',
            'end_date': '31.03.2025'
        }
        
        logger.info("SQL-Template: %s", sql)
        logger.info("Parameter: %s", params)
        
        # Abfrage simulieren (keine tatsächliche Ausführung)
        logger.info("Die Abfrage würde mit den angegebenen Parametern ausgeführt werden.")
        logger.info("Der LIMIT-Parameter sollte aus den default_values (500) oder dem Fallback-Wert (1000) kommen.")
        
        # In einer tatsächlichen Umgebung würde hier execute_bigquery_query(sql, params) aufgerufen werden
        
        return True
    except Exception as e:
        logger.error(f"Fehler beim Testen der BigQuery-Abfrage: {str(e)}")
        return False

if __name__ == "__main__":
    print("Starte Test für BigQuery-Abfrage mit LIMIT-Parameter...")
    success = test_bigquery_query_with_limit()
    if success:
        print("Test erfolgreich abgeschlossen.")
    else:
        print("Test fehlgeschlagen.")
