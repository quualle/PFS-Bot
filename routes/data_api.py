# routes/data_api.py

import os
import json
import logging
import traceback
import calendar
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, current_app
from functools import wraps
from routes.utils import login_required

# Absolute Importe statt relative Importe
from bigquery_functions import execute_bigquery_query, format_query_result
# Wissensbasis-Manager importieren
from routes.kb_utils import lade_themen

# --- Blueprint Definition ---
data_api_bp = Blueprint('data_api', __name__)


# --- API Routes ---

@data_api_bp.route('/get_dashboard_data', methods=['GET'])
@login_required
def get_dashboard_data_route():
    """API endpoint to fetch dashboard metrics for the logged-in user."""
    try:
        seller_id = session.get('seller_id')
        if not seller_id:
            logging.warning("Dashboard: No seller_id found in session.")
            return jsonify({"error": "Seller ID not found", "status": "error"}), 400

        # Load query patterns (Need robust path handling)
        try:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            query_path = os.path.join(base_path, 'query_patterns.json')
            with open(query_path, 'r', encoding='utf-8') as f:
                query_patterns = json.load(f)
        except Exception as e:
            logging.error(f"Dashboard: Error loading query_patterns.json: {e}")
            return jsonify({"error": "Failed to load query configuration", "status": "error"}), 500

        dashboard_result = {}
        default_start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        default_end_date = datetime.now().strftime('%Y-%m-%d')

        # 1. Active Customers (Hardcoded query name from original app.py)
        query_name_active = "get_active_care_stays_now"
        if query_name_active in query_patterns['common_queries']:
            pattern_active = query_patterns['common_queries'][query_name_active]
            result_active = execute_bigquery_query(pattern_active['sql_template'], {'seller_id': seller_id})
            formatted_active = format_query_result(result_active, pattern_active.get('result_structure'))
            # Assuming the structure provides 'active_customers_count'
            dashboard_result['active_customers'] = {
                'data': formatted_active, # Keep raw formatted data if needed
                'count': formatted_active[0]['active_customers_count'] if formatted_active else 0
            }
        else:
            logging.error(f"Dashboard: Query '{query_name_active}' not found.")
            dashboard_result['active_customers'] = {'data': [], 'count': 0}

        # 2. Conversion Rate (Hardcoded query name)
        query_name_cvr = "get_cvr_lead_contract"
        if query_name_cvr in query_patterns['common_queries']:
             pattern_cvr = query_patterns['common_queries'][query_name_cvr]
             # Assuming CVR query doesn't need date range, only seller_id
             result_cvr = execute_bigquery_query(pattern_cvr['sql_template'], {'seller_id': seller_id})
             formatted_cvr = format_query_result(result_cvr, pattern_cvr.get('result_structure'))
             dashboard_result['conversion_rate'] = formatted_cvr[0]['conversion_rate'] if formatted_cvr else 0
        else:
             logging.error(f"Dashboard: Query '{query_name_cvr}' not found.")
             dashboard_result['conversion_rate'] = 0

        # 3. New Contracts (Hardcoded query name, uses default date range)
        query_name_new = "get_contract_count"
        if query_name_new in query_patterns['common_queries']:
            pattern_new = query_patterns['common_queries'][query_name_new]
            params_new = {'seller_id': seller_id, 'start_date': default_start_date, 'end_date': default_end_date}
            result_new = execute_bigquery_query(pattern_new['sql_template'], params_new)
            formatted_new = format_query_result(result_new, pattern_new.get('result_structure'))
            dashboard_result['new_contracts'] = formatted_new[0]['new_contracts_count'] if formatted_new else 0
        else:
            logging.error(f"Dashboard: Query '{query_name_new}' not found.")
            dashboard_result['new_contracts'] = 0

        # 4. Terminations (Hardcoded query name, uses default date range)
        query_name_term = "get_contract_terminations"
        if query_name_term in query_patterns['common_queries']:
            pattern_term = query_patterns['common_queries'][query_name_term]
            params_term = {'seller_id': seller_id, 'start_date': default_start_date, 'end_date': default_end_date}
            result_term = execute_bigquery_query(pattern_term['sql_template'], params_term)
            formatted_term = format_query_result(result_term, pattern_term.get('result_structure'))
            # Structure assumes two counts: serious and agency
            serious_count = formatted_term[0]['serious_terminations_count'] if formatted_term else 0
            agency_count = formatted_term[0]['agency_switch_count'] if formatted_term else 0
            dashboard_result['terminations'] = {
                'serious_terminations_count': serious_count,
                'agency_switch_count': agency_count,
                'total_terminations_count': serious_count + agency_count
            }
        else:
             logging.error(f"Dashboard: Query '{query_name_term}' not found.")
             dashboard_result['terminations'] = {'serious_terminations_count': 0, 'agency_switch_count': 0, 'total_terminations_count': 0}

        # 5. Pro-Rata Revenue (Current Month)
        query_name_revenue = "get_revenue_current_month_pro_rata"
        if query_name_revenue in query_patterns['common_queries']:
            pattern_revenue = query_patterns['common_queries'][query_name_revenue]
            today = datetime.now().date()
            start_of_month = today.replace(day=1)
            _, days_in_month = calendar.monthrange(today.year, today.month)
            # End date for pro-rata is today
            params_revenue = {
                'seller_id': seller_id,
                'start_of_month': start_of_month.isoformat(),
                'end_of_month': today.isoformat(),
                'days_in_month': days_in_month # Needed if query calculates daily avg first
            }
            result_revenue = execute_bigquery_query(pattern_revenue['sql_template'], params_revenue)
            formatted_revenue = format_query_result(result_revenue, pattern_revenue.get('result_structure'))
            dashboard_result['pro_rata_revenue'] = formatted_revenue[0]['total_monthly_pro_rata_revenue'] if formatted_revenue else 0
        else:
            logging.error(f"Dashboard: Query '{query_name_revenue}' not found.")
            dashboard_result['pro_rata_revenue'] = 0

        # Construct the final response
        response = {
            "data": dashboard_result.get('active_customers', {}).get('data', []), # Or just send counts?
            "count": dashboard_result.get('active_customers', {}).get('count', 0),
            "conversion_rate": dashboard_result.get('conversion_rate', 0),
            "new_contracts": dashboard_result.get('new_contracts', 0),
            "terminations": dashboard_result.get('terminations', {}),
            "pro_rata_revenue": dashboard_result.get('pro_rata_revenue', 0),
            "status": "success"
        }
        return jsonify(response)

    except Exception as e:
        error_trace = traceback.format_exc()
        logging.error(f"Error in get_dashboard_data_route: {str(e)}\n{error_trace}")
        return jsonify({
            "error": str(e),
            "trace": error_trace,
            "status": "error"
        }), 500

@data_api_bp.route('/lade_themen', methods=['GET'])
@login_required
def lade_themen_route():
    """API endpoint to load chat topics."""
    try:
        themen_dict = lade_themen() # Uses placeholder
        return jsonify(themen_dict), 200
    except Exception as e:
        logging.error(f"Error loading topics: {e}", exc_info=True)
        return jsonify({"error": "Could not load topics"}), 500

@data_api_bp.route('/toggle_notfall_mode', methods=['POST'])
@login_required
def toggle_notfall_mode_route():
    """API endpoint to toggle emergency mode in the session."""
    try:
        # Check if data sent as JSON or form
        if request.is_json:
            activate = request.json.get('activate', False) # Expect boolean from JSON
        else:
            activate = request.form.get('activate', '0') == '1' # Expect '1' or '0' from form
            
        if activate:
            session['notfall_mode'] = True
            logging.info(f"User {session.get('user_id')} activated emergency mode.")
        else:
            session.pop('notfall_mode', None)
            logging.info(f"User {session.get('user_id')} deactivated emergency mode.")
            
        session.modified = True
        return jsonify({
            'success': True,
            'notfall_mode_active': session.get('notfall_mode', False)
        })
    except Exception as e:
        logging.error(f"Error toggling emergency mode: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# Add /get_seller_stats here if/when it's implemented
