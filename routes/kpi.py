# routes/kpi.py

from flask import Blueprint, jsonify, request, session, current_app
import logging
import os
import json
from routes.utils import login_required
from functools import wraps
from bigquery_functions import handle_function_call, execute_bigquery_query

# --- Blueprint Definition ---
kpi_bp = Blueprint('kpi', __name__)

# Hilfsfunktion zum Laden der Query-Patterns
def load_query_patterns():
    try:
        query_patterns_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'query_patterns.json')
        with open(query_patterns_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Fehler beim Laden der query_patterns.json: {e}")
        return {"common_queries": {}}

# --- API Route ---

@kpi_bp.route('/get_kpi_data', methods=['GET'])
@login_required # Apply the login check decorator
def get_kpi_data_route():
    """
    Fetches Key Performance Indicator (KPI) data based on a date range.
    Currently focuses on the Lead -> Contract Closing Rate (Abschlussquote).
    Requires 'start_date' and 'end_date' query parameters (YYYY-MM-DD).
    """
    if not handle_function_call:
         logging.error("KPI Route: handle_function_call function is not available.")
         return jsonify({"error": "Backend configuration error."}), 500
         
    # Use seller_id from session, consistent with data_api.py
    seller_id = session.get('seller_id') 
    if not seller_id:
         # This case might be covered by @login_required if seller_id is set upon login
         logging.warning("KPI Route: seller_id not found in session.")
         return jsonify({"error": "User seller ID not found. Please ensure you are logged in correctly."}), 400

    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    # Validate required parameters
    if not start_date_str or not end_date_str:
        return jsonify({"error": "Missing required query parameters: start_date, end_date"}), 400
        
    # Optional: Add date validation logic here (e.g., check format YYYY-MM-DD)

    try:
        # Prepare parameters for the BigQuery function call
        # Assuming the BQ function for CVR needs seller_id, start_date, end_date
        query_name = "get_cvr_lead_contract" 
        parameters = {
            "seller_id": seller_id,
            "start_date": start_date_str,
            "end_date": end_date_str
        }
        
        logging.info(f"Fetching KPI '{query_name}' for seller {seller_id} ({start_date_str} to {end_date_str})")
        
        # Lade die Query-Patterns
        query_patterns = load_query_patterns()
        
        if query_name in query_patterns['common_queries']:
            query_pattern = query_patterns['common_queries'][query_name]
            
            # Execute the query
            result = execute_bigquery_query(
                query_pattern['sql_template'],
                parameters,
                query_pattern.get('default_values', {})
            )
        else:
            result = handle_function_call(query_name, parameters)

        # --- Process the results ---
        # Adapt this based on the ACTUAL structure returned by your handle_function_call
        if result and isinstance(result, list) and len(result) > 0:
            data = result[0] # Assuming the first item contains the relevant counts
            
            # Safely get counts, defaulting to 0
            net_leads = data.get('net_leads', 0)
            total_contracts = data.get('total_contracts', 0)
            
            # Ensure they are integers
            try:
                net_leads = int(net_leads)
            except (ValueError, TypeError): net_leads = 0
            try:
                total_contracts = int(total_contracts)
            except (ValueError, TypeError): total_contracts = 0

            # Calculate closing rate
            closing_rate = (total_contracts / net_leads * 100) if net_leads > 0 else 0
            
            kpi_data = {
                "closing_rate": round(closing_rate, 2),
                "lead_count": net_leads,
                "contract_count": total_contracts
            }
            logging.info(f"KPI data for seller {seller_id}: {kpi_data}")
            return jsonify(kpi_data)
        else:
            # Log if no data is returned from BQ function
            logging.warning(f"No data returned from '{query_name}' for seller {seller_id} ({start_date_str} to {end_date_str}).")
            # Return default zero values and a message
            return jsonify({
                "closing_rate": 0,
                "lead_count": 0,
                "contract_count": 0,
                "message": "No data found for the selected period." 
            })

    except Exception as e:
        logging.error(f"Error in /get_kpi_data for seller {seller_id}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred while fetching KPI data."}), 500
