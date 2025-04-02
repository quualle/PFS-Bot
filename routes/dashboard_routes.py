from flask import Blueprint, render_template, request, jsonify, session, current_app
import logging
import json
from datetime import datetime, timedelta
import pandas as pd

# Blueprint Definition
dashboard_bp = Blueprint('dashboard', __name__)

# Import necessary functions from bigquery_functions.py instead of app.py
from bigquery_functions import (
    get_bigquery_client, execute_bigquery_query, format_simple_results
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
        query_type = request.args.get('type', 'overview')
        date_range = request.args.get('range', '7d')  # Default: 7 Tage
        seller_id = session.get('seller_id')
        
        if not seller_id:
            return jsonify({'error': 'Keine Verkäufer-ID in der Session'}), 400
            
        # BigQuery Client
        client = get_bigquery_client()
        
        # Zeitraum berechnen
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
            
        # Abfrage basierend auf dem Typ
        if query_type == 'overview':
            # Überblick: Gesamtzahl der Anfragen im Zeitraum
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
        elif query_type == 'customers':
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
        if query_type == 'overview':
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
            
        else:
            # Für andere Abfragetypen: Direkt konvertieren
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
            
    except Exception as e:
        logging.error(f"Fehler bei Abfrage der Dashboard-Daten: {str(e)}")
        return jsonify({'error': str(e)}), 500

@dashboard_bp.route('/debug_dashboard', methods=['GET'])
def debug_dashboard():
    """
    Debug-Route für das Dashboard, die alle relevanten Informationen zurückgibt
    und in der Session gespeicherte Daten anzeigt.
    """
    try:
        # Alle verfügbaren Session-Daten sammeln
        session_data = {key: session.get(key) for key in session.keys()}
        
        # Sensible Daten filtern
        filtered_session = {}
        for key, value in session_data.items():
            # Chat-Verläufe, Passwörter und andere sensible Daten ausschließen
            if 'chat_history' in key:
                filtered_session[key] = f"[Chat-Verlauf mit {len(value)} Nachrichten]"
            elif 'password' in key.lower() or 'token' in key.lower() or 'secret' in key.lower():
                filtered_session[key] = "[Sensible Daten ausgeblendet]"
            else:
                filtered_session[key] = value
                
        # Systeminformationen zusammenstellen
        system_info = {
            'app_config': {k: v for k, v in current_app.config.items() 
                          if not ('SECRET' in k or 'KEY' in k or 'PASSWORD' in k)},
            'session_age': session.get('_creation_time', None),
            'debug_mode': current_app.debug,
            'environment': current_app.env
        }
        
        return render_template('debug.html', 
                              session_data=filtered_session,
                              system_info=system_info)
                              
    except Exception as e:
        logging.error(f"Fehler bei Debug-Dashboard: {str(e)}")
        return jsonify({'error': str(e)}), 500
