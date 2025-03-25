import json
import logging
import traceback
import datetime
from typing import Dict, List, Any, Optional, Union
from flask import session
from google.cloud import bigquery
from sql_query_helper import apply_query_enhancements
import os

# Logging einrichten
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pfad zur Service-Account-Datei
SERVICE_ACCOUNT_PATH = '/home/PfS/gcpxbixpflegehilfesenioren-a47c654480a8.json'

def handle_function_call(function_name: str, function_args: Dict[str, Any]) -> str:
    """
    Hauptfunktion zum Handling von Function-Calls vom LLM.
    """
    try:
        logger.info(f"Function call received: {function_name} with args: {function_args}")
        
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
        
        # Wende SQL-Verbesserungen an
        query_pattern, function_args = apply_query_enhancements(function_name, query_pattern, function_args)
        
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
                
        # Spezieller Fall für Datums-Parameter: Fülle fehlende start_date und end_date
        if 'start_date' in query_pattern.get('required_parameters', []) and 'start_date' not in function_args:
            # Wenn kein Start-Datum angegeben, einen Standardwert setzen
            function_args['start_date'] = "DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
            logger.info(f"Kein Start-Datum angegeben, verwende Standard: {function_args['start_date']}")
            
        if 'end_date' in query_pattern.get('required_parameters', []) and 'end_date' not in function_args:
            # Wenn kein End-Datum angegeben, das aktuelle Datum verwenden
            function_args['end_date'] = "CURRENT_DATE()"
            logger.info(f"Kein End-Datum angegeben, verwende aktuelles Datum: {function_args['end_date']}")
        
        # Konvertiere Parameter zu den richtigen Typen
        param_types = query_pattern.get('parameter_types', {})
        for param, value in list(function_args.items()):
            if param == 'limit' and isinstance(value, str):
                try:
                    function_args[param] = int(value)
                except (ValueError, TypeError):
                    function_args[param] = 100  # Default fallback
                    
            # Konvertiere weitere Parameter nach Bedarf
            if param in param_types:
                if param_types[param] == 'int' and not isinstance(value, int):
                    try:
                        function_args[param] = int(value)
                    except (ValueError, TypeError):
                        pass
                elif param_types[param] == 'float' and not isinstance(value, float):
                    try:
                        function_args[param] = float(value)
                    except (ValueError, TypeError):
                        pass
        
        logger.info(f"Executing query with parameters (after type conversion): {function_args}")
        
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
        if query_name == 'get_active_care_stays_now':
            summary = f"Du hast aktuell {count} Kunden mit aktiven Care Stays. "
            
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
            
        elif query_name == 'get_active_care_stays':
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
            
        elif query_name == 'get_customers_on_pause':
            if count == 0:
                return "Aktuell sind keine Kunden in Betreuungspause."
            
            # Wenn total_paused_customers im ersten Element verfügbar ist
            total_paused = result_data[0].get('total_paused_customers', count) if result_data else count
            
            summary = f"Du hast aktuell {total_paused} Kunden in Betreuungspause. "
            
            if count <= 5:  # Detaillierte Info für wenige Ergebnisse
                details = []
                for item in result_data:
                    customer_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
                    days_on_pause = item.get('days_on_pause', 'unbekannt')
                    agency = item.get('agency_name', 'unbekannter Agentur')
                    details.append(f"{customer_name} ({days_on_pause} Tage, {agency})")
                
                if details:
                    summary += "Details: " + "; ".join(details)
            
            return summary
            
        elif query_name == 'get_cvr_lead_contract':
            if count == 0 or not result_data:
                return "Im angegebenen Zeitraum konnten keine Daten zur Berechnung der Abschlussquote gefunden werden."
            
            # Daten aus dem Ergebnis extrahieren
            total_leads = result_data[0].get('total_leads', 0) if result_data else 0
            net_leads = result_data[0].get('net_leads', 0) if result_data else 0
            total_contracts = result_data[0].get('total_contracts', 0) if result_data else 0
            agency_switches = result_data[0].get('agency_switches', 0) if result_data else 0
            conversion_rate = result_data[0].get('conversion_rate', 0) if result_data else 0
            
            # Zeitraum für die Antwort extrahieren (aus den Parametern)
            time_range = ""
            if 'start_date' in data.get('parameters', {}) and 'end_date' in data.get('parameters', {}):
                start_date = data.get('parameters', {}).get('start_date')
                end_date = data.get('parameters', {}).get('end_date')
                
                if start_date and end_date:
                    try:
                        # Formatiere die Datumsangaben
                        start_formatted = format_date(start_date) 
                        end_formatted = format_date(end_date)
                        time_range = f" im Zeitraum {start_formatted} bis {end_formatted}"
                    except:
                        # Bei Fehler in der Datumsformatierung
                        time_range = " im angegebenen Zeitraum"
            else:
                time_range = " im angegebenen Zeitraum"
            
            if net_leads == 0:
                summary = f"Du hast{time_range} keine Netto-Leads (nach Abzug von Rückforderungen), daher kann keine Abschlussquote berechnet werden."
            else:
                summary = f"Deine Abschlussquote{time_range} beträgt {conversion_rate}%. Von {total_leads} gekauften Leads (davon {net_leads} Netto-Leads nach Abzug von Rückforderungen) hast du {total_contracts} Verträge abgeschlossen. Zusätzlich wurden {agency_switches} Agenturwechsel registriert."
            
            return summary
            
        elif query_name == 'get_leads_count':
            if count == 0 or not result_data:
                return "Im angegebenen Zeitraum wurden keine Leads gefunden."
            
            # Die Anzahl der Leads aus dem Ergebnis extrahieren
            leads_count = result_data[0].get('leads_count', 0) if result_data else 0
            
            # Zeitraum für die Antwort extrahieren (aus den Parametern)
            time_range = ""
            if 'start_date' in data.get('parameters', {}) and 'end_date' in data.get('parameters', {}):
                start_date = data.get('parameters', {}).get('start_date')
                end_date = data.get('parameters', {}).get('end_date')
                
                if start_date and end_date:
                    try:
                        # Formatiere die Datumsangaben
                        start_formatted = format_date(start_date) 
                        end_formatted = format_date(end_date)
                        time_range = f" im Zeitraum {start_formatted} bis {end_formatted}"
                    except:
                        # Bei Fehler in der Datumsformatierung
                        time_range = " im angegebenen Zeitraum"
            else:
                time_range = " im angegebenen Zeitraum"
            
            summary = f"Du hast{time_range} insgesamt {leads_count} Leads gekauft/erhalten."
            
            return summary
            
        elif query_name == 'get_leads':
            if count == 0:
                return "Im angegebenen Zeitraum wurden keine Leads gefunden."
            
            # Gesamtzahl der Leads aus dem ersten Ergebnis extrahieren
            total_leads = result_data[0].get('total_leads_in_selected_period', count) if result_data else count
            
            # Zeitraum bestimmen (wenn verfügbar)
            first_created = min(item.get('created_at', '') for item in result_data if item.get('created_at'))
            last_created = max(item.get('created_at', '') for item in result_data if item.get('created_at'))
            
            # Format für Zeitraumanzeige
            time_range = ""
            if first_created and last_created:
                first_date = format_date(first_created)
                last_date = format_date(last_created)
                if first_date != last_date:
                    time_range = f" im Zeitraum {first_date} bis {last_date}"
                else:
                    time_range = f" am {first_date}"
            
            summary = f"Hier ist eine detaillierte Liste deiner{time_range} gekauften/erhaltenen Leads (insgesamt {total_leads}):"
            
            if count <= 10:  # Detaillierte Information bei wenigen Leads (max. 10)
                details = []
                for i, item in enumerate(result_data):
                    lead_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
                    lead_date = format_date(item.get('created_at', ''))
                    email = item.get('email', 'keine E-Mail')
                    details.append(f"{i+1}. {lead_name} ({lead_date}, {email})")
                
                if details:
                    summary += "\n\n" + "\n".join(details)
            else:
                # Bei mehr als 10 Leads nur die ersten 10 anzeigen
                details = []
                for i, item in enumerate(result_data[:10]):
                    lead_name = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
                    lead_date = format_date(item.get('created_at', ''))
                    email = item.get('email', 'keine E-Mail')
                    details.append(f"{i+1}. {lead_name} ({lead_date}, {email})")
                
                if details:
                    summary += "\n\n" + "\n".join(details)
                    summary += f"\n\n...und {count - 10} weitere Leads."
            
            return summary
            
        elif query_name == 'get_contract_count':
            if not result_data or len(result_data) < 2:
                return "Für den angegebenen Zeitraum konnten keine Daten zu neuen Verträgen gefunden werden."
            
            # Wir erwarten zwei Ergebniszeilen: aktive Verträge und alle Verträge
            active_contracts = None
            all_contracts = None
            
            for row in result_data:
                if row.get('query_type') == 'neue Verträge noch aktiv':
                    active_contracts = row
                elif row.get('query_type') == 'Alle neuen Verträge':
                    all_contracts = row
            
            if not all_contracts:
                return "Es konnten keine Daten zu neuen Verträgen gefunden werden."
            
            # Gesamtzahl der neuen Verträge
            total_contracts = all_contracts.get('total_contracts', 0)
            
            # Anzahl der noch aktiven Verträge
            active_count = active_contracts.get('total_active_contracts', 0) if active_contracts else 0
            
            # Zeitraum für die Antwort extrahieren (aus den Parametern)
            time_range = ""
            if 'start_date' in data.get('parameters', {}) and 'end_date' in data.get('parameters', {}):
                start_date = data.get('parameters', {}).get('start_date')
                end_date = data.get('parameters', {}).get('end_date')
                
                if start_date and end_date:
                    try:
                        # Formatiere die Datumsangaben
                        start_formatted = format_date(start_date) 
                        end_formatted = format_date(end_date)
                        time_range = f" im Zeitraum {start_formatted} bis {end_formatted}"
                    except:
                        # Bei Fehler in der Datumsformatierung
                        time_range = " im angegebenen Zeitraum"
            else:
                time_range = " im angegebenen Zeitraum"
            
            # Antwort zusammenstellen
            summary = f"Du hast{time_range} {total_contracts} neue Verträge abgeschlossen und davon sind {active_count} noch aktiv."
            
            return summary
            
        elif query_name == 'get_contract_details':
            if count == 0:
                return "Für den angegebenen Zeitraum wurden keine Vertragsdetails gefunden."
            
            # Wir holen uns die Gesamtzahl der Neuabschlüsse aus dem ersten Datensatz
            total_contracts = result_data[0].get('Neuabschlüsse_gesamt', 0) if result_data else 0
            agency_switches = result_data[0].get('Agenturwechsel', 0) if result_data else 0
            
            # Zeitraum für die Antwort extrahieren (aus den Parametern)
            time_range = ""
            if 'start_date' in data.get('parameters', {}) and 'end_date' in data.get('parameters', {}):
                start_date = data.get('parameters', {}).get('start_date')
                end_date = data.get('parameters', {}).get('end_date')
                
                if start_date and end_date:
                    try:
                        # Formatiere die Datumsangaben
                        start_formatted = format_date(start_date) 
                        end_formatted = format_date(end_date)
                        time_range = f" im Zeitraum {start_formatted} bis {end_formatted}"
                    except:
                        # Bei Fehler in der Datumsformatierung
                        time_range = " im angegebenen Zeitraum"
            else:
                time_range = " im angegebenen Zeitraum"
            
            # Basisinformation
            summary = f"Hier ist eine detaillierte Liste deiner{time_range} abgeschlossenen Verträge ({total_contracts} insgesamt, davon {agency_switches} Agenturwechsel):\n\n"
            
            # Für jeden Vertrag Details formatieren
            contract_details = []
            for i, contract in enumerate(result_data[:10]):  # Maximal 10 Verträge anzeigen
                name = f"{contract.get('first_name', '')} {contract.get('last_name', '')}".strip()
                date = format_date(contract.get('contract_created_at', ''))
                provision = contract.get('prov_seller', 0)
                
                contract_details.append(f"{i+1}. {name} (Abschluss: {date}, Provision: {provision}€)")
            
            # Detaillierte Ausgabe nur für die ersten 10 Verträge
            if contract_details:
                summary += "\n".join(contract_details)
                
                # Hinweis, wenn es mehr als 10 Verträge gibt
                if count > 10:
                    summary += f"\n\n...und {count - 10} weitere Verträge."
            
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

def get_bigquery_client():
    """Erstellt und gibt einen BigQuery-Client zurück."""
    service_account_path = SERVICE_ACCOUNT_PATH
    if not os.path.exists(service_account_path):
        logger.error(f"Service Account Datei nicht gefunden: {service_account_path}")
        return None
    return bigquery.Client.from_service_account_json(service_account_path)

# Seller bezogene Funktionen
def get_leads_for_seller(seller_id):
    """Ruft die Leads für einen bestimmten Verkäufer aus BigQuery ab."""
    try:
        client = get_bigquery_client()
        if client is None:
            return []
        
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
        LIMIT 5000
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
            
        logger.info(f"Leads für Seller {seller_id} abgerufen: {len(leads)} Ergebnisse")
        return leads
    
    except Exception as e:
        logger.exception(f"Fehler beim Abrufen der Leads aus BigQuery: {e}")
        return []

def get_contracts_for_seller(seller_id):
    """Ruft die Verträge für einen bestimmten Verkäufer aus BigQuery ab."""
    try:
        client = get_bigquery_client()
        if client is None:
            return []
        
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
        LIMIT 1000
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
            
        logger.info(f"Verträge für Seller {seller_id} abgerufen: {len(contracts)} Ergebnisse")
        return contracts
    
    except Exception as e:
        logger.exception(f"Fehler beim Abrufen der Verträge aus BigQuery: {e}")
        return []

def get_households_for_seller(seller_id):
    """Ruft die Haushalte für einen bestimmten Verkäufer aus BigQuery ab."""
    try:
        client = get_bigquery_client()
        if client is None:
            return []
        
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
        LIMIT 1000
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
            
        logger.info(f"Haushalte für Seller {seller_id} abgerufen: {len(households)} Ergebnisse")
        return households
    
    except Exception as e:
        logger.exception(f"Fehler beim Abrufen der Haushalte aus BigQuery: {e}")
        return []

def calculate_kpis_for_seller(seller_id):
    """Berechnet KPIs für einen bestimmten Verkäufer aus BigQuery-Daten."""
    try:
        client = get_bigquery_client()
        if client is None:
            return {}
        
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
            logger.info(f"KPIs für Seller {seller_id} berechnet")
            return kpis
            
        logger.warning(f"Keine KPI-Daten für Seller {seller_id} gefunden")
        return {}
    
    except Exception as e:
        logger.exception(f"Fehler beim Berechnen der KPIs aus BigQuery: {e}")
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
        logger.warning("Keine Verkäufer-ID für get_seller_data angegeben")
        return {"error": "Keine Verkäufer-ID angegeben"}
    
    logger.info(f"Seller-Daten werden abgerufen für ID {seller_id}, Typ: {data_type or 'all'}")
    
    if data_type == 'leads' or data_type is None:
        result['leads'] = get_leads_for_seller(seller_id)
        
    if data_type == 'contracts' or data_type is None:
        result['contracts'] = get_contracts_for_seller(seller_id)
        
    if data_type == 'households' or data_type is None:
        result['households'] = get_households_for_seller(seller_id)
        
    if data_type == 'kpis' or data_type is None:
        result['kpis'] = calculate_kpis_for_seller(seller_id)
    
    return result