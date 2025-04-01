# routes/kpi.py

from flask import Blueprint, jsonify, request, session, current_app
import logging

# Placeholder for dependencies (to be imported/moved later)
# from .. import db # Example
# from ..utils import login_required # Assuming login_required decorator exists
# from ..bigquery_functions import handle_function_call 

# --- Placeholder Decorator --- 
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session: # Basic check, improve as needed
             logging.warning("Access denied: User not logged in.")
             return jsonify({"error": "Authentication required", "status": "error"}), 401
        return f(*args, **kwargs)
    return decorated_function

# --- Placeholder Function (Replace with actual import) ---
def handle_function_call(query_name, parameters):
    print(f"WARN: Dummy handle_function_call called in kpi.py for {query_name}")
    # Simulate BQ results based on query_name and params
    if query_name == "get_cvr_lead_contract":
        # Simulate returning lead count and contract count for the period
        # You'll need to adapt this based on the actual return structure of your BQ function
        return [{'net_leads': 50, 'total_contracts': 10}] # Example data
    return [] # Default empty


# --- Blueprint Definition ---
kpi_bp = Blueprint('kpi', __name__)


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
        
        # Execute the BigQuery query using the handler function (placeholder)
        results = handle_function_call(query_name, parameters)

        # --- Process the results ---
        # Adapt this based on the ACTUAL structure returned by your handle_function_call
        if results and isinstance(results, list) and len(results) > 0:
            data = results[0] # Assuming the first item contains the relevant counts
            
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
