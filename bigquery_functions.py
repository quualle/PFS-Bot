import json
import logging
import traceback
import datetime
from typing import Dict, List, Any, Optional, Union
from flask import session
from google.cloud import bigquery

# Logging einrichten
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pfad zur Service-Account-Datei
SERVICE_ACCOUNT_PATH = '/home/PfS/gcpxbixpflegehilfesenioren-a47c654480a8.json'

def handle_function_call(function_name: str, function_args: Dict[str, Any]) -> str:
    """
    Hauptfunktion zum Handling von Function-Calls vom LLM.
    
    Args:
        function_name (str): Name der aufgerufenen Funktion
        function_args (dict): Argumente der Funktion
        
    Returns:
        str: JSON-formatierte Ergebnisse der Abfrage oder Fehlermeldung
    """
    try:
        # Lade die Abfragemuster
        with open('query_patterns.json', 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
        
        # Prüfe, ob die Funktion existiert
        if function_name not in query_patterns['common_queries']:
            return json.dumps({
                "error": f"Funktion {function_name} nicht gefunden",
                "status": "error"
            })
        
        # Hole das Abfragemuster
        query_pattern = query_patterns['common_queries'][function_name]
        
        # Füge seller_id aus der Session hinzu, wenn nicht vorhanden
        if 'seller_id' in query_pattern.get('required_parameters', []) and 'seller_id' not in function_args:
            function_args['seller_id'] = session.get('seller_id')
            if not function_args['seller_id']:
                return json.dumps({
                    "error": "Keine seller_id in der Anfrage oder Session gefunden",
                    "status": "error"
                })
        
        # Fülle fehlende optionale Parameter mit Standardwerten
        for param in query_pattern.get('optional_parameters', []):
            if param not in function_args and param in query_pattern.get('default_values', {}):
                function_args[param] = query_pattern['default_values'][param]
        
        # Führe die Abfrage aus
        result = execute_bigquery_query(
            query_pattern['sql_template'],
            function_args
        )
        
        # Formatiere das Ergebnis
        formatted_result = format_query_result(result, query_pattern.get('result_structure'))
        
        return json.dumps({
            "data": formatted_result,
            "count": len(formatted_result),
            "status": "success"
        })
    
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Fehler in handle_function_call: {str(e)}\n{error_trace}")
        return json.dumps({
            "error": str(e),
            "trace": error_trace,
            "status": "error"
        })


def execute_bigquery_query(sql_template: str, parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Führt eine BigQuery-Abfrage mit den angegebenen Parametern aus.
    
    Args:
        sql_template (str): SQL-Abfragetemplate mit Platzhaltern
        parameters (dict): Parameter für die Abfrage
        
    Returns:
        list: Liste von Dictionaries mit den Abfrageergebnisse
    """
    import re
    try:
        # Initialisiere BigQuery-Client
        client = bigquery.Client.from_service_account_json(SERVICE_ACCOUNT_PATH)
        
        # Erstelle QueryJobConfig mit Parametern
        job_config = bigquery.QueryJobConfig()
        query_parameters = []
        
        # WICHTIG: Suche alle in der SQL-Abfrage verwendeten Parameter
        used_params = set(re.findall(r'@(\w+)', sql_template))
        
        # Stellen Sie sicher, dass alle verwendeten Parameter übergeben werden
        for param_name in used_params:
            param_value = parameters.get(param_name)
            
            # Parameter-Typ bestimmen
            if isinstance(param_value, int):
                param_type = "INT64"
            elif isinstance(param_value, float):
                param_type = "FLOAT64"
            elif isinstance(param_value, bool):
                param_type = "BOOL"
            elif isinstance(param_value, datetime.date):
                param_type = "DATE"
            else:
                param_type = "STRING"
                
            # Auch NULL-Werte müssen korrekt typisiert werden
            query_parameters.append(
                bigquery.ScalarQueryParameter(param_name, param_type, param_value)
            )
            
        job_config.query_parameters = query_parameters
        
        # Führe die Abfrage aus
        query_job = client.query(sql_template, job_config=job_config)
        results = query_job.result()
        
        # Konvertiere die Ergebnisse in eine Liste von Dictionaries
        rows = []
        for row in results:
            row_dict = {}
            for key, value in row.items():
                # Konvertiere nicht-serialisierbare Werte
                if isinstance(value, (datetime.datetime, datetime.date)):
                    row_dict[key] = value.isoformat()
                else:
                    row_dict[key] = value
            rows.append(row_dict)
        
        return rows
    
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error executing BigQuery query: {e}\n{error_trace}")
        raise

def format_query_result(result: List[Dict[str, Any]], result_structure: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    Formatiert das Abfrageergebnis für die Rückgabe an das LLM.
    Kann die Feldnamen anpassen oder Daten transformieren.
    
    Args:
        result (list): Liste von Dictionaries mit den Abfrageergebnissen
        result_structure (dict, optional): Struktur mit Feldbeschreibungen
        
    Returns:
        list: Formatierte Liste von Dictionaries
    """
    if not result_structure:
        return result
    
    # Feldnamen gemäß der Ergebnisstruktur optimieren
    formatted_result = []
    for row in result:
        formatted_row = {}
        for key, value in row.items():
            # Nur Felder behalten, die in der Ergebnisstruktur definiert sind
            if key in result_structure:
                formatted_row[key] = value
        formatted_result.append(formatted_row)
    
    return formatted_result


def summarize_query_result(result: str, query_name: str) -> str:
    """
    Erstellt eine natürlichsprachliche Zusammenfassung der Abfrageergebnisse.
    
    Args:
        result (str): JSON-Ergebnis einer Abfrage
        query_name (str): Name der ausgeführten Abfrage
        
    Returns:
        str: Natürlichsprachliche Zusammenfassung
    """
    try:
        data = json.loads(result)
        
        if data.get('status') == 'error':
            return f"Bei der Abfrage ist ein Fehler aufgetreten: {data.get('error', 'Unbekannter Fehler')}"
        
        result_data = data.get('data', [])
        count = data.get('count', 0)
        
        if count == 0:
            return "Es wurden keine Daten gefunden, die deiner Anfrage entsprechen."
        
        # Verschiedene Zusammenfassungen je nach Abfragetyp
        if query_name == 'get_active_care_stays':
            summary = f"Es wurden {count} aktive Care Stays gefunden. "
            
            if count <= 3:  # Detaillierte Zusammenfassung für wenige Ergebnisse
                details = []
                for item in result_data:
                    customer_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
                    details.append(
                        f"Care Stay für {customer_name} von {format_date(item.get('bill_start', 'N/A'))} " +
                        f"bis {format_date(item.get('bill_end', 'N/A'))} bei Agentur {item.get('agency_name', 'N/A')}"
                    )
                summary += "Details: " + "; ".join(details)
            else:
                # Zusammenfassende Statistiken für viele Ergebnisse
                agencies = set(item.get('agency_name', 'Unbekannt') for item in result_data if item.get('agency_name'))
                summary += f"Diese verteilen sich auf {len(agencies)} verschiedene Agenturen."
            
            return summary
            
        elif query_name == 'get_past_care_stays':
            summary = f"Es wurden {count} vergangene Care Stays gefunden. "
            
            if count > 0:
                # Berechne Durchschnittsdauer
                durations = [item.get('care_stay_duration_days', 0) for item in result_data if item.get('care_stay_duration_days') is not None]
                if durations:
                    avg_duration = sum(durations) / len(durations)
                    summary += f"Die durchschnittliche Dauer betrug {avg_duration:.1f} Tage."
            
            return summary
            
        elif query_name.startswith('get_care_stays_'):
            summary = f"Es wurden {count} Care Stays im angegebenen Zeitraum gefunden. "
            
            if count > 0:
                # Finde den längsten und kürzesten Care Stay
                longest = max((item.get('care_stay_duration_days', 0) for item in result_data if item.get('care_stay_duration_days') is not None), default=0)
                shortest = min((item.get('care_stay_duration_days', 0) for item in result_data if item.get('care_stay_duration_days') is not None), default=0)
                
                if longest > 0:
                    summary += f"Der längste Care Stay dauerte {longest} Tage, der kürzeste {shortest} Tage."
            
            return summary
            
        elif query_name == 'get_active_contracts':
            summary = f"Es wurden {count} aktive Verträge gefunden. "
            
            if count <= 5:  # Detaillierte Zusammenfassung für wenige Ergebnisse
                details = []
                for item in result_data:
                    customer_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
                    agency_name = item.get('agency_name', 'N/A')
                    details.append(f"Vertrag mit {customer_name} bei Agentur {agency_name}")
                summary += "Details: " + "; ".join(details)
            
            return summary
            
        elif query_name.startswith('get_leads_'):
            summary = f"Es wurden {count} Leads gefunden. "
            
            if count <= 5:
                details = []
                for item in result_data:
                    lead_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or "Unbenannter Lead"
                    created_at = format_date(item.get('lead_created_at', 'N/A'))
                    details.append(f"{lead_name} (erstellt am {created_at})")
                summary += "Details: " + "; ".join(details)
            
            return summary
            
        elif query_name == 'get_care_givers_for_customer':
            summary = f"Es wurden {count} Pflegekräfte für diesen Kunden gefunden. "
            
            if count <= 3:
                details = []
                for item in result_data:
                    caregiver_name = f"{item.get('giver_first_name', '')} {item.get('giver_last_name', '')}".strip() or "Unbenannte Pflegekraft"
                    details.append(caregiver_name)
                summary += "Pflegekräfte: " + ", ".join(details)
            
            return summary
            
        elif query_name.startswith('get_tickets_'):
            summary = f"Es wurden {count} Tickets gefunden. "
            
            if count > 0:
                # Gruppiere Tickets nach Typ
                ticket_types = {}
                for item in result_data:
                    ticket_type = item.get('ticketable_type', 'Unbekannt')
                    ticket_types[ticket_type] = ticket_types.get(ticket_type, 0) + 1
                
                type_summary = ", ".join([f"{count} {type}" for type, count in ticket_types.items()])
                summary += f"Aufgeschlüsselt nach Typ: {type_summary}."
            
            return summary
            
        elif query_name == 'get_user_statistics':
            if count == 0 or not result_data:
                return "Es konnten keine Statistiken gefunden werden."
            
            item = result_data[0]  # Sollte nur ein Datensatz sein
            
            summary = "Statistik-Übersicht: "
            stats = []
            
            total_care_stays = item.get('total_care_stays')
            if total_care_stays is not None:
                stats.append(f"{total_care_stays} Care Stays insgesamt")
            
            total_contracts = item.get('total_contracts')
            if total_contracts is not None:
                stats.append(f"{total_contracts} Verträge insgesamt")
            
            total_leads = item.get('total_leads')
            if total_leads is not None:
                stats.append(f"{total_leads} Leads insgesamt")
            
            avg_care_stay_duration = item.get('avg_care_stay_duration')
            if avg_care_stay_duration is not None:
                stats.append(f"durchschnittliche Care-Stay-Dauer: {avg_care_stay_duration:.1f} Tage")
            
            total_prov_seller = item.get('total_prov_seller')
            if total_prov_seller is not None:
                stats.append(f"Gesamtprovision: {total_prov_seller:.2f} €")
            
            summary += ", ".join(stats)
            return summary
            
        elif query_name == 'get_monthly_performance':
            if count == 0:
                return "Es konnten keine monatlichen Leistungsdaten gefunden werden."
            
            summary = f"Monatliche Leistungsdaten für {count} Monate gefunden. "
            
            # Gesamtzahlen berechnen
            total_care_stays = sum(item.get('new_care_stays', 0) for item in result_data)
            total_revenue = sum(item.get('monthly_prov', 0) for item in result_data)
            
            # Beste und schlechteste Monate finden
            best_month = max(result_data, key=lambda x: x.get('monthly_prov', 0), default=None)
            worst_month = min(result_data, key=lambda x: x.get('monthly_prov', 0), default=None)
            
            summary += f"Insgesamt {total_care_stays} Care Stays mit einer Gesamtprovision von {total_revenue:.2f} €. "
            
            if best_month and worst_month:
                summary += f"Der beste Monat war {best_month.get('month')} mit {best_month.get('monthly_prov', 0):.2f} €, "
                summary += f"der schlechteste Monat war {worst_month.get('month')} mit {worst_month.get('monthly_prov', 0):.2f} €."
            
            return summary
            
        elif query_name == 'get_agency_performance':
            if count == 0 or not result_data:
                return "Es konnten keine Leistungsdaten für diese Agentur gefunden werden."
            
            item = result_data[0]  # Sollte nur ein Datensatz sein
            agency_name = item.get('agency_name', 'Unbekannte Agentur')
            
            summary = f"Leistungsdaten für Agentur '{agency_name}': "
            stats = []
            
            total_care_stays = item.get('total_care_stays')
            if total_care_stays is not None:
                stats.append(f"{total_care_stays} Care Stays")
            
            total_contracts = item.get('total_contracts')
            if total_contracts is not None:
                stats.append(f"{total_contracts} Verträge")
            
            avg_care_stay_duration = item.get('avg_care_stay_duration')
            if avg_care_stay_duration is not None:
                stats.append(f"durchschnittliche Care-Stay-Dauer: {avg_care_stay_duration:.1f} Tage")
            
            total_care_givers = item.get('total_care_givers')
            if total_care_givers is not None:
                stats.append(f"{total_care_givers} Pflegekräfte")
            
            summary += ", ".join(stats)
            return summary
            
        elif query_name == 'get_customer_care_details':
            if count == 0 or not result_data:
                return "Es konnten keine Pflegedetails für diesen Kunden gefunden werden."
            
            item = result_data[0]  # Erster Datensatz
            customer_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip() or "Unbekannter Kunde"
            
            summary = f"Pflegedetails für {customer_name}: "
            details = []
            
            age = item.get('age')
            if age:
                details.append(f"{age} Jahre alt")
            
            gender = item.get('gender')
            if gender:
                gender_map = {"m": "männlich", "f": "weiblich", "d": "divers"}
                details.append(gender_map.get(gender, gender))
            
            care_level = item.get('care_level')
            if care_level:
                details.append(f"Pflegegrad {care_level}")
            
            location = item.get('location')
            zip_code = item.get('zip_code')
            if location and zip_code:
                details.append(f"wohnhaft in {zip_code} {location}")
            
            summary += ", ".join(details)
            
            # Zweiter Absatz mit Pflegedetails
            care_details = []
            
            if item.get('bed_bound') == True:
                care_details.append("bettlägerig")
            
            if item.get('night_service') == True:
                care_details.append("benötigt Nachtpflege")
            
            if item.get('mobility_assist') == True:
                care_details.append("benötigt Mobilitätshilfe")
            
            if item.get('intim_care') == True:
                care_details.append("benötigt Intimhygiene")
            
            if care_details:
                summary += " Patient ist " + ", ".join(care_details) + "."
            
            return summary
            
        elif query_name == 'get_revenue_by_agency':
            summary = f"Umsatzdaten für {count} Agenturen gefunden. "
            
            if count > 0:
                # Gesamtumsatz berechnen
                total_revenue = sum(item.get('total_revenue', 0) for item in result_data)
                
                # Top-Agentur identifizieren
                top_agency = max(result_data, key=lambda x: x.get('total_revenue', 0), default=None)
                
                if top_agency:
                    top_name = top_agency.get('agency_name', 'Unbekannt')
                    top_revenue = top_agency.get('total_revenue', 0)
                    summary += f"Gesamtumsatz: {total_revenue:.2f} €. Top-Performer ist Agentur '{top_name}' mit {top_revenue:.2f} € Umsatz."
            
            return summary
            
        # Generische Zusammenfassung für unbekannte Abfragetypen
        return f"Die Abfrage hat {count} Ergebnisse zurückgegeben."
    
    except Exception as e:
        logger.error(f"Fehler bei der Zusammenfassung der Ergebnisse: {e}")
        return f"Fehler bei der Zusammenfassung der Ergebnisse: {str(e)}"


def format_date(date_str: str) -> str:
    """Formatiert ein Datum von ISO-Format zu 'DD.MM.YYYY'"""
    if not date_str or date_str == 'N/A':
        return 'N/A'
    try:
        date_obj = datetime.datetime.fromisoformat(date_str.split('T')[0])
        return date_obj.strftime('%d.%m.%Y')
    except:
        return date_str


# Zusätzliche hilfreiche Funktionen

def get_user_id_from_email(email: str) -> Optional[str]:
    """
    Ruft die _id eines Benutzers aus BigQuery basierend auf seiner E-Mail-Adresse ab.
    """
    if not email:
        logger.warning("Keine E-Mail-Adresse angegeben")
        return None
        
    try:
        # SQL-Abfrage mit Parameter
        query = """
        SELECT _id
        FROM `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.proto_users`
        WHERE email = @email
        LIMIT 1
        """
        
        # Parameter für die Abfrage
        parameters = {"email": email}
        
        # Abfrage ausführen
        result = execute_bigquery_query(query, parameters)
        
        # Ergebnis verarbeiten
        if result and len(result) > 0:
            return result[0].get('_id')
            
        logger.info(f"Keine Seller-ID für E-Mail {email} gefunden")
        return None
    
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der seller_id: {str(e)}")
        return None


def get_lead_details(lead_id: str) -> Optional[Dict[str, Any]]:
    """
    Ruft detaillierte Informationen zu einem bestimmten Lead ab.
    """
    if not lead_id:
        logger.warning("Keine Lead-ID angegeben")
        return None
        
    try:
        # SQL-Abfrage mit Parameter
        query = """
        SELECT 
            l._id,
            la.first_name,
            la.last_name,
            la.email,
            la.phone,
            l.created_at,
            l.updated_at,
            l.source_data,
            l.contacted,
            l.seller_id
        FROM 
            `gcpxbixpflegehilfesenioren.PflegehilfeSeniore_BI.leads` AS l
        JOIN 
            `gcpxbixpflegehilfesenioren.dataform_staging.leads_and_seller_and_source_with_address` AS la
        ON 
            la._id = l._id
        WHERE 
            l._id = @lead_id
        LIMIT 1
        """
        
        # Parameter für die Abfrage
        parameters = {"lead_id": lead_id}
        
        # Abfrage ausführen
        result = execute_bigquery_query(query, parameters)
        
        # Ergebnis verarbeiten
        if result and len(result) > 0:
            return result[0]
            
        logger.info(f"Kein Lead mit ID {lead_id} gefunden")
        return None
    
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Lead-Details: {str(e)}")
        return None