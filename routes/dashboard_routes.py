from flask import Blueprint, render_template, request, jsonify, session, current_app
import logging
import json
from datetime import datetime, timedelta
import pandas as pd

# Blueprint Definition
dashboard_bp = Blueprint('dashboard', __name__)

# Import necessary functions from bigquery_functions.py instead of app.py
from bigquery_functions import (
    get_bigquery_client, execute_bigquery_query, format_simple_results, format_query_result
)

@dashboard_bp.route('/get_active_care_stays_now', methods=['GET'])
def get_active_care_stays_now():
    """
    Liefert die aktiven Care Stays für den Verkäufer als JSON
    """
    try:
        # Seller ID aus der Session holen
        seller_id = session.get('seller_id')
        if not seller_id:
            return jsonify({'error': 'Keine Verkäufer-ID in der Session'}), 400
            
        # BigQuery Client
        client = get_bigquery_client()
        
        # Abfrage für aktive Aufenthalte zum aktuellen Zeitpunkt
        query = f"""
        SELECT 
            c.id as care_stay_id,
            c.customer_id,
            c.from_date,
            c.to_date,
            cu.first_name,
            cu.last_name,
            cu.name_prefix,
            cu.name_suffix
        FROM 
            `{current_app.config['BIGQUERY_TABLE_PREFIX']}.care_stays` c
        JOIN 
            `{current_app.config['BIGQUERY_TABLE_PREFIX']}.customers` cu
        ON 
            c.customer_id = cu.id
        WHERE 
            c.seller_id = @seller_id
            AND c.from_date <= CURRENT_TIMESTAMP()
            AND c.to_date >= CURRENT_TIMESTAMP()
        ORDER BY 
            c.from_date DESC
        """
        
        # Abfrage ausführen
        parameters = {"seller_id": seller_id}
        results = execute_bigquery_query(query, parameters)
        
        # Ergebnisse formatieren
        formatted_results = []
        for row in results:
            formatted_results.append({
                'care_stay_id': row.care_stay_id,
                'customer_id': row.customer_id,
                'customer_name': f"{row.name_prefix or ''} {row.first_name or ''} {row.last_name or ''} {row.name_suffix or ''}".strip(),
                'from_date': row.from_date.strftime("%Y-%m-%d"),
                'to_date': row.to_date.strftime("%Y-%m-%d")
            })
            
        return jsonify(formatted_results)
        
    except Exception as e:
        logging.error(f"Fehler bei Abfrage der aktiven Aufenthalte: {str(e)}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/get_dashboard_data', methods=['GET'])
def get_dashboard_data():
    """
    Liefert Daten für das Dashboard, basierend auf dem angegebenen Abfragetyp.
    Diese Route wird beim Öffnen des Dashboards aufgerufen.
    """
    try:
        # 0. Debug-Log für Dashboard-Anfragen
        logging.info("==== DASHBOARD DEBUGGING START ====")
        logging.info(f"Dashboard: Anfrage von User {session.get('user_id')}")
        # Auch im Server-Log protokollieren für Debugging
        print(f"==== DASHBOARD DEBUGGING START - User: {session.get('user_id')} ====")
        
        # 1. Grundlegende Daten vorbereiten
        dashboard_result = {
            'active_customers': 0,
            'conversion_rate': 0,
            'new_contracts': 0,
            'pro_rata_revenue': 0
        }
        
        seller_id = session.get('user_id')
        if not seller_id:
            logging.error("Dashboard: Kein User in Session")
            print("DASHBOARD DEBUG ERROR: Kein User in Session")
            return jsonify({'error': 'Nicht eingeloggt', 'status': 'error'}), 401
        
        # Query patterns laden
        query_patterns = load_query_patterns()
        if not query_patterns:
            logging.error("Dashboard: Konnte query_patterns nicht laden")
            print("DASHBOARD DEBUG ERROR: Konnte query_patterns nicht laden")
            return jsonify({'error': 'Serverfehler', 'status': 'error'}), 500
        
        # Zeitraum berechnen für die Standardabfragen
        today = datetime.now().date()
        
        if date_range == '7d':
            start_date = today - timedelta(days=6)  # 7 Tage inkl. heute
            group_by = 'date'
            date_format = '%Y-%m-%d'
        elif date_range == '30d':
            start_date = today - timedelta(days=29)  # 30 Tage inkl. heute
            group_by = 'date'
            date_format = '%Y-%m-%d'
        elif date_range == '90d':
            start_date = today - timedelta(days=89)  # 90 Tage inkl. heute
            group_by = 'week'
            date_format = '%Y-W%W'
        elif date_range == '1y':
            start_date = today.replace(year=today.year-1, day=1)
            group_by = 'month'
            date_format = '%Y-%m'
        else:
            # Fallback auf 7 Tage
            start_date = today - timedelta(days=6)
            group_by = 'date'
            date_format = '%Y-%m-%d'
            
        # Dashboard-Daten sammeln
        dashboard_result = {}
        
        # Wenn ein spezifischer Abfragetyp angefordert wurde und nicht 'overview'
        if query_type != 'overview':
            # Chat-Statistik-Abfragen bearbeiten
            if query_type == 'customers':
                # Top-Kunden im Zeitraum
                query = f"""
                SELECT 
                    customer_name,
                    COUNT(*) as count
                FROM 
                    `{current_app.config['BIGQUERY_TABLE_PREFIX']}.chatlog`
                WHERE 
                    seller_id = @seller_id
                    AND DATE(timestamp) >= @start_date
                    AND DATE(timestamp) <= @today
                    AND customer_name IS NOT NULL
                    AND customer_name != ''
                GROUP BY 
                    customer_name
                ORDER BY 
                    count DESC
                LIMIT 10
                """
                parameters = {"seller_id": seller_id, "start_date": start_date.isoformat(), "today": today.isoformat()}
            elif query_type == 'topics':
                # Häufigste Themen im Zeitraum
                query = f"""
                SELECT 
                    topic,
                    COUNT(*) as count
                FROM 
                    `{current_app.config['BIGQUERY_TABLE_PREFIX']}.chatlog`,
                    UNNEST(topics) as topic
                WHERE 
                    seller_id = @seller_id
                    AND DATE(timestamp) >= @start_date
                    AND DATE(timestamp) <= @today
                GROUP BY 
                    topic
                ORDER BY 
                    count DESC
                LIMIT 10
                """
                parameters = {"seller_id": seller_id, "start_date": start_date.isoformat(), "today": today.isoformat()}
            elif query_type == 'functions':
                # Häufigste Funktionsaufrufe im Zeitraum
                query = f"""
                SELECT 
                    function_name,
                    COUNT(*) as count
                FROM 
                    `{current_app.config['BIGQUERY_TABLE_PREFIX']}.function_calls`
                WHERE 
                    seller_id = @seller_id
                    AND DATE(timestamp) >= @start_date
                    AND DATE(timestamp) <= @today
                GROUP BY 
                    function_name
                ORDER BY 
                    count DESC
                LIMIT 10
                """
                parameters = {"seller_id": seller_id, "start_date": start_date.isoformat(), "today": today.isoformat()}
            else:
                return jsonify({'error': f'Unbekannter Abfragetyp: {query_type}'}), 400
                
            # Abfrage ausführen
            results = execute_bigquery_query(query, parameters)
            
            # Ergebnisse in ein DataFrame konvertieren für einfachere Verarbeitung
            df = pd.DataFrame(results)
            
            # Ergebnisse formatieren
            formatted_results = []
            if not df.empty:
                formatted_results = df.to_dict(orient='records')
            
            return jsonify({
                'success': True,
                'data': formatted_results,
                'query_type': query_type,
                'date_range': date_range,
                'start_date': start_date.isoformat(),
                'end_date': today.isoformat()
            })
        
        # OVERVIEW-MODUS: Hole alle Dashboard-KPIs 
        
        # 1. Chat-Statistik (original Funktionalität)
        query = f"""
        SELECT 
            FORMAT_TIMESTAMP('{date_format}', timestamp) as time_period,
            COUNT(*) as count
        FROM 
            `{current_app.config['BIGQUERY_TABLE_PREFIX']}.chatlog`
        WHERE 
            seller_id = @seller_id
            AND DATE(timestamp) >= @start_date
            AND DATE(timestamp) <= @today
        GROUP BY 
            time_period
        ORDER BY 
            time_period
        """
        parameters = {"seller_id": seller_id, "start_date": start_date.isoformat(), "today": today.isoformat()}
        chat_results = execute_bigquery_query(query, parameters)
        
        # Ergebnisse in ein DataFrame konvertieren für einfachere Verarbeitung
        df = pd.DataFrame(chat_results)
        
        # Für Zeitreihen: Kontinuierliche Zeitachse sicherstellen
        # Alle Tage/Wochen/Monate im Zeitraum erzeugen
        time_periods = []
        
        if group_by == 'date':
            current = start_date
            while current <= today:
                time_periods.append(current.strftime(date_format))
                current += timedelta(days=1)
        elif group_by == 'week':
            # Wöchentlich
            current = start_date
            while current <= today:
                time_periods.append(current.strftime(date_format))
                current += timedelta(days=7)
        elif group_by == 'month':
            # Monatlich
            current = start_date
            while current <= today:
                time_periods.append(current.strftime(date_format))
                if current.month == 12:
                    current = current.replace(year=current.year+1, month=1)
                else:
                    current = current.replace(month=current.month+1)
        
        # DataFrame mit allen Zeitperioden erstellen
        full_range = pd.DataFrame({'time_period': time_periods})
        
        # Mit den tatsächlichen Daten zusammenführen (left join)
        if not df.empty:
            merged = pd.merge(full_range, df, on='time_period', how='left')
            merged['count'] = merged['count'].fillna(0).astype(int)
        else:
            merged = full_range.copy()
            merged['count'] = 0
            
        # In JSON konvertieren
        formatted_results = merged.to_dict(orient='records')
        dashboard_result['data'] = formatted_results
        
        # 2. Aktive Kunden (get_active_care_stays_now)
        query_name = "get_active_care_stays_now"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Parameter nur für diese Abfrage (aktive Kunden)
            parameters = {
                'seller_id': seller_id,
                'limit': 100  # Standardlimit wieder hinzufügen
            }
            logging.info(f"Dashboard: Parameter für {query_name}: {parameters}")
            
            result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            formatted_result = format_query_result(result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Aktive Kunden Abfrage abgeschlossen")
            print(f"DASHBOARD DEBUG: Aktive Kunden - {formatted_result}")
            
            dashboard_result['active_customers'] = formatted_result
            dashboard_result['count'] = len(formatted_result)
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['active_customers'] = []
            dashboard_result['count'] = 0
        
        # 3. Abschlussquote (get_cvr_lead_contract)
        query_name = "get_cvr_lead_contract"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Zeitraum: Letzte 30 Tage
            end_date = datetime.now().date().isoformat()
            start_date_30d = (datetime.now().date() - timedelta(days=30)).isoformat()
            parameters = {'seller_id': seller_id, 'start_date': start_date_30d, 'end_date': end_date}
            logging.info(f"Dashboard: Parameter für Abschlussquote: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage für Abschlussquote aus")
            cvr_result = execute_bigquery_query(
                query_pattern['sql_template'], 
                parameters,
                query_pattern.get('default_values', {})
            )
            
            # Formatiere das Ergebnis
            formatted_cvr = format_query_result(cvr_result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Abschlussquotenabfrage abgeschlossen: {formatted_cvr}")
            print(f"DASHBOARD DEBUG: Abschlussquotenabfrage - {formatted_cvr}")
            
            # Speichern für die Antwort (Schlüssel korrigiert: conversion_rate statt closing_rate)
            dashboard_result['conversion_rate'] = formatted_cvr[0]['conversion_rate'] if formatted_cvr and 'conversion_rate' in formatted_cvr[0] else 0
            logging.info(f"Dashboard: Conversion Rate gesetzt: {dashboard_result['conversion_rate']}")
            print(f"DASHBOARD DEBUG: Conversion Rate gesetzt: {dashboard_result['conversion_rate']}")
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['conversion_rate'] = 0
        
        # 4. Neue Verträge der letzten 14 Tage (get_contract_count)
        query_name = "get_contract_count"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Zeitraum: Letzte 14 Tage
            end_date = datetime.now().date().isoformat()
            start_date_14d = (datetime.now().date() - timedelta(days=14)).isoformat()
            parameters = {'seller_id': seller_id, 'start_date': start_date_14d, 'end_date': end_date}
            logging.info(f"Dashboard: Parameter für Neue Verträge: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage für Neue Verträge aus")
            contracts_result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            # Formatiere das Ergebnis
            formatted_contracts = format_query_result(contracts_result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Neue Verträge Abfrage abgeschlossen: {formatted_contracts}")
            print(f"DASHBOARD DEBUG: Neue Verträge - {formatted_contracts}")
            
            # Speichern für die Antwort (Schlüssel korrigiert: total_contracts/normal_contracts_count statt count)
            # Wir verwenden den 'Alle neuen Verträge' Eintrag (Index 1) und den normal_contracts_count Wert
            dashboard_result['new_contracts'] = formatted_contracts[1]['normal_contracts_count'] if formatted_contracts and len(formatted_contracts) > 1 and 'normal_contracts_count' in formatted_contracts[1] else 0
            logging.info(f"Dashboard: Neue Verträge gesetzt: {dashboard_result['new_contracts']}")
            print(f"DASHBOARD DEBUG: Neue Verträge gesetzt: {dashboard_result['new_contracts']}")
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['new_contracts'] = 0
        
        # 5. Pro-Rata-Umsatz (get_revenue_current_month_pro_rata)
        query_name = "get_revenue_current_month_pro_rata"  # Korrekter Name aus query_patterns.json
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Zeitraum: Aktueller Monat mit korrekten Parametern
            today_date = datetime.now().date()
            start_of_month = datetime(today_date.year, today_date.month, 1).date().isoformat()
            # Letzter Tag des aktuellen Monats
            if today_date.month == 12:
                end_of_month = datetime(today_date.year, 12, 31).date().isoformat()
            else:
                end_of_month = (datetime(today_date.year, today_date.month + 1, 1) - timedelta(days=1)).date().isoformat()
            
            # Tage im Monat berechnen
            days_in_month = (datetime.strptime(end_of_month, "%Y-%m-%d") - datetime.strptime(start_of_month, "%Y-%m-%d")).days + 1
            
            parameters = {
                'seller_id': seller_id, 
                'start_of_month': start_of_month, 
                'end_of_month': end_of_month,
                'days_in_month': days_in_month
            }
            logging.info(f"Dashboard: Parameter für Pro-Rata-Umsatz: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage für Pro-Rata-Umsatz aus")
            revenue_result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            # Formatiere das Ergebnis
            formatted_revenue = format_query_result(revenue_result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Pro-Rata-Umsatz Abfrage abgeschlossen: {formatted_revenue}")
            print(f"DASHBOARD DEBUG: Pro-Rata-Umsatz - {formatted_revenue}")
            
            # Speichern für die Antwort (Schlüssel korrigiert: total_monthly_pro_rata_revenue statt revenue)
            dashboard_result['pro_rata_revenue'] = formatted_revenue[0]['total_monthly_pro_rata_revenue'] if formatted_revenue and 'total_monthly_pro_rata_revenue' in formatted_revenue[0] else 0
            logging.info(f"Dashboard: Pro-Rata-Umsatz gesetzt: {dashboard_result['pro_rata_revenue']}")
            print(f"DASHBOARD DEBUG: Pro-Rata-Umsatz gesetzt: {dashboard_result['pro_rata_revenue']}")
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['pro_rata_revenue'] = 0
        
        # Status hinzufügen
        dashboard_result['status'] = 'success'
        logging.info(f"Dashboard: Erfolgreiche Antwort: {dashboard_result}")
        print(f"==== DASHBOARD DEBUGGING ENDE - Erfolgreiche Antwort: {dashboard_result} ====")
        
        return jsonify(dashboard_result)
            
    except Exception as e:
        logging.error(f"Fehler in get_dashboard_data: {e}")
        print(f"DASHBOARD DEBUG ERROR: Fehler in get_dashboard_data: {e}")
        return jsonify({'error': str(e), 'status': 'error'}), 500
