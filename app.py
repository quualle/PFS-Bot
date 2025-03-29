@app.route('/get_dashboard_data', methods=['GET'])
def get_dashboard_data():
    """
    Liefert Daten für das Dashboard, basierend auf dem angegebenen Abfragetyp.
    Diese Route wird beim Öffnen des Dashboards aufgerufen.
    """
    try:
        # Seller ID aus der Session holen
        seller_id = session.get('seller_id')
        logging.info(f"Dashboard: Seller ID aus Session: {seller_id}")
        
        if not seller_id:
            logging.error("Dashboard: Keine Seller ID in der Session gefunden")
            return jsonify({
                "error": "Keine Seller ID in der Session gefunden",
                "status": "error"
            }), 401
        
        # Lade die Abfragemuster
        logging.info("Dashboard: Lade Abfragemuster")
        with open('query_patterns.json', 'r', encoding='utf-8') as f:
            query_patterns = json.load(f)
        
        # Dashboard-Daten sammeln
        dashboard_result = {}
        
        # 1. Aktive Kunden (get_active_care_stays_now)
        query_name = "get_active_care_stays_now"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Parameter für die Abfrage vorbereiten
            parameters = {'seller_id': seller_id, 'limit': 100}
            logging.info(f"Dashboard: Parameter: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage aus")
            result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            logging.info(f"Dashboard: Abfrage abgeschlossen, {len(result)} Ergebnisse")
            
            # Formatiere das Ergebnis
            formatted_result = format_query_result(result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Ergebnis formatiert, {len(formatted_result)} Einträge")
            
            # Speichern für die Antwort
            dashboard_result['active_customers'] = {
                "data": formatted_result,
                "count": len(formatted_result)
            }
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['active_customers'] = {"data": [], "count": 0}
        
        # 2. Abschlussquote (get_cvr_lead_contract)
        query_name = "get_cvr_lead_contract"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Zeitraum: Letzte 30 Tage
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=30)).isoformat()
            parameters = {'seller_id': seller_id, 'start_date': start_date, 'end_date': end_date}
            logging.info(f"Dashboard: Parameter für Abschlussquote: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage für Abschlussquote aus")
            cvr_result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            # Formatiere das Ergebnis
            formatted_cvr = format_query_result(cvr_result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Abschlussquotenabfrage abgeschlossen")
            
            # Speichern für die Antwort
            dashboard_result['conversion_rate'] = formatted_cvr[0] if formatted_cvr else {}
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['conversion_rate'] = {}
        
        # 3. Neue Verträge der letzten 14 Tage (get_contract_count)
        query_name = "get_contract_count"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Zeitraum: Letzte 14 Tage
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=14)).isoformat()
            parameters = {'seller_id': seller_id, 'start_date': start_date, 'end_date': end_date}
            logging.info(f"Dashboard: Parameter für Neue Verträge: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage für Neue Verträge aus")
            contracts_result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            # Formatiere das Ergebnis
            formatted_contracts = format_query_result(contracts_result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Neue Verträge Abfrage abgeschlossen")
            
            # Speichern für die Antwort
            dashboard_result['new_contracts'] = formatted_contracts[0] if formatted_contracts else {}
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['new_contracts'] = {}
        
        # 4. Kündigungen (get_contract_terminations)
        query_name = "get_contract_terminations"
        logging.info(f"Dashboard: Verwende Abfrage {query_name}")
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Zeitraum: Letzte 30 Tage
            end_date = date.today().isoformat()
            start_date = (date.today() - timedelta(days=30)).isoformat()
            parameters = {'seller_id': seller_id, 'start_date': start_date, 'end_date': end_date}
            logging.info(f"Dashboard: Parameter für Kündigungen: {parameters}")
            
            # Führe die Abfrage aus
            logging.info("Dashboard: Führe BigQuery-Abfrage für Kündigungen aus")
            terminations_result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters
            )
            
            # Formatiere das Ergebnis
            formatted_terminations = format_query_result(terminations_result, query_pattern.get('result_structure'))
            logging.info(f"Dashboard: Kündigungen Abfrage abgeschlossen")
            
            # Extrahiere die relevanten Kennzahlen - bei der ersten Zeile stehen die Gesamtzahlen
            if formatted_terminations and len(formatted_terminations) > 0:
                terminations_data = {
                    'serious_terminations_count': formatted_terminations[0].get('serious_terminations_count', 0),
                    'agency_switch_count': formatted_terminations[0].get('agency_switch_count', 0),
                    'total_terminations_count': formatted_terminations[0].get('total_terminations_count', 0)
                }
            else:
                terminations_data = {
                    'serious_terminations_count': 0,
                    'agency_switch_count': 0,
                    'total_terminations_count': 0
                }
            
            # Speichern für die Antwort
            dashboard_result['terminations'] = terminations_data
        else:
            logging.error(f"Dashboard: Abfrage {query_name} nicht gefunden")
            dashboard_result['terminations'] = {'serious_terminations_count': 0, 'agency_switch_count': 0, 'total_terminations_count': 0}
        
        # Gesamte Antwort zusammenstellen
        response = {
            "data": dashboard_result['active_customers']['data'],
            "count": dashboard_result['active_customers']['count'],
            "conversion_rate": dashboard_result['conversion_rate'],
            "new_contracts": dashboard_result['new_contracts'],
            "terminations": dashboard_result['terminations'],
            "status": "success"
        }
        
        logging.info("Dashboard: Sende Antwort")
        return jsonify(response)
        
    except Exception as e:
        logging.error(f"Dashboard-Fehler: {str(e)}")
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500