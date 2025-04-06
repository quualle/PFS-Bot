import json
import logging
from google.cloud import bigquery
from google.oauth2 import service_account

# Logging konfigurieren
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_bigquery_client():
    """Erstellt einen BigQuery-Client mit Anmeldedaten aus einer Dienstkonto-Schlüsseldatei."""
    try:
        # Dienstkonto-Authentifizierung (normaler Fall)
        credentials = service_account.Credentials.from_service_account_file(
            'pfs-test-df0dc5e0f4d1.json'  # Anpassen an tatsächlichen Pfad
        )
        return bigquery.Client(credentials=credentials, project=credentials.project_id)
    except Exception as e:
        logging.error(f"Fehler beim Erstellen des BigQuery-Clients: {str(e)}")
        # Fallback zur Standardauthentifizierung
        return bigquery.Client()

def execute_bigquery_query(query, parameters=None):
    """Führt eine BigQuery-Abfrage aus und gibt die Ergebnisse als Dictionary zurück."""
    client = get_bigquery_client()
    
    # Parameter vorbereiten
    query_params = []
    if parameters:
        for name, value in parameters.items():
            param_type = 'STRING'  # Standardtyp
            if isinstance(value, int):
                param_type = 'INT64'
            elif isinstance(value, float):
                param_type = 'FLOAT64'
            query_params.append(bigquery.ScalarQueryParameter(name, param_type, value))
    
    job_config = bigquery.QueryJobConfig(query_parameters=query_params)
    
    try:
        # Abfrage ausführen
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        # Ergebnisse in ein Dictionary konvertieren
        rows = list(results)
        columns = [field.name for field in results.schema]
        
        result_dict = {
            "columns": columns,
            "rows": [dict(row.items()) for row in rows]
        }
        
        return result_dict
    
    except Exception as e:
        logging.error(f"Fehler bei der BigQuery-Ausführung: {str(e)}")
        raise

def test_paused_customers():
    seller_id = "62d00b56a384fd908f7f5a6c"  # Marco's Seller ID (gemäß Code)
    
    # Lade die Abfragemuster
    with open('query_patterns.json', 'r', encoding='utf-8') as f:
        query_patterns = json.load(f)
    
    # Abfrage für Kunden in Pause
    query_name = "get_customers_on_pause"
    if query_name in query_patterns['common_queries']:
        query_pattern = query_patterns['common_queries'][query_name]
        logging.info(f"SQL Template geladen: {query_pattern['sql_template'][:100]}...")
        
        # Parameter vorbereiten
        parameters = {'seller_id': seller_id}
        logging.info(f"Parameter: {parameters}")
        
        try:
            # Führe die Abfrage aus
            logging.info("Führe BigQuery-Abfrage aus")
            result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            # Ausgabe der Ergebnisse
            if result and 'rows' in result:
                row_count = len(result['rows']) if result['rows'] else 0
                logging.info(f"{row_count} Zeilen gefunden")
                
                # Zeige die ersten paar Ergebnisse
                if row_count > 0:
                    for i, row in enumerate(result['rows'][:3]):
                        logging.info(f"Beispiel {i+1}: {row}")
                
                # Zeige die total_paused_customers-Werte
                if row_count > 0 and 'total_paused_customers' in result['rows'][0]:
                    logging.info(f"Gesamtanzahl paused ist {result['rows'][0]['total_paused_customers']}")
                else:
                    logging.info("Kein total_paused_customers Wert gefunden!")
                    
                    if row_count > 0:
                        logging.info(f"Verfügbare Spalten: {list(result['rows'][0].keys())}")
            else:
                logging.warning("Keine Ergebnisse oder keine 'rows' in der Antwort!")
                if result:
                    logging.warning(f"Antwortstruktur: {result.keys()}")
                    
        except Exception as e:
            logging.error(f"Fehler bei der Ausführung: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
    else:
        logging.error(f"Abfrage {query_name} nicht in query_patterns gefunden!")

    # Vereinfachte Abfrage nur für die Anzahl
    direct_count_query = """
    WITH active_contracts AS (
      SELECT c._id AS contract_id
      FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.contracts` AS c
      JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.households` AS h ON c.household_id = h._id
      JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l ON h.lead_id = l._id
      WHERE l.seller_id = @seller_id AND c.archived = 'false'
    ),
    has_previous_care_stays AS (
      SELECT c.contract_id
      FROM active_contracts c
      JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
      WHERE cs.stage = 'Bestätigt' AND DATE(TIMESTAMP(cs.arrival)) < CURRENT_DATE()
    ),
    current_care_stays AS (
      SELECT c.contract_id
      FROM active_contracts c
      JOIN `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.care_stays` cs ON c.contract_id = cs.contract_id
      WHERE cs.stage = 'Bestätigt' AND DATE(TIMESTAMP(cs.arrival)) <= CURRENT_DATE() AND DATE(TIMESTAMP(cs.departure)) >= CURRENT_DATE()
    )
    SELECT COUNT(*) AS total_paused
    FROM has_previous_care_stays hpcs
    WHERE hpcs.contract_id NOT IN (SELECT contract_id FROM current_care_stays)
    """
    
    try:
        logging.info("Versuche direkte Zählung mit vereinfachter Abfrage")
        count_result = execute_bigquery_query(direct_count_query, {'seller_id': seller_id})
        
        if count_result and 'rows' in count_result and count_result['rows']:
            total_paused = count_result['rows'][0].get('total_paused', 0)
            logging.info(f"Direkte Zählung ergab {total_paused} Kunden in Pause")
        else:
            logging.warning("Auch direkte Zählung ergab keine Ergebnisse")
    except Exception as e:
        logging.error(f"Fehler bei direkter Zählung: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    test_paused_customers() 