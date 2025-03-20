import re
import json
import logging
from prepare_sql_name import prepare_customer_name_for_sql

def enhance_customer_query(query_data, params):
    """
    Verbessert SQL-Abfragen für Kundennamen, indem sowohl der originale Name
    (z.B. mit Verkäufer-Identifier wie "(I)") als auch ein bereinigter Name
    berücksichtigt werden.
    
    Args:
        query_data (dict): Die Query-Daten aus query_patterns.json
        params (dict): Die Parameter für die Abfrage
        
    Returns:
        Tuple[dict, dict]: Aktualisierte query_data und params
    """
    # Nur für Abfragen mit Kundennamen relevant
    if "customer_name" not in params:
        return query_data, params
    
    customer_name = params["customer_name"]
    logging.info(f"Verarbeite Kundenanfrage für: '{customer_name}'")
    
    # Bereite den Kundennamen für die SQL-Suche vor
    primary_name, secondary_name = prepare_customer_name_for_sql(customer_name)
    
    # Aktualisiere den primären Namen in den Parametern
    params["customer_name"] = primary_name
    
    # Wenn wir einen sekundären Namen haben (z.B. "Ramm" für "Ramm (I)")
    if secondary_name:
        logging.info(f"Zusätzlicher Suchname gefunden: '{secondary_name}'")
        
        # Hole das SQL-Template
        sql_template = query_data.get("sql_template", "")
        
        # Es gibt zwei Möglichkeiten:
        # 1. Wir fügen einen neuen Parameter hinzu und modifizieren die Abfrage
        # 2. Wir erstellen eine komplexere Abfrage mit ODER-Bedingungen
        
        # Option 1: Füge sekundären Namen als Parameter hinzu
        params["secondary_name"] = secondary_name
        
        # Suche nach der WHERE-Bedingung für Kundennamen
        name_condition_pattern = r'(LOWER\(la\.first_name\) LIKE CONCAT\(\'%\', LOWER\(@customer_name\), \'%\'\) OR LOWER\(la\.last_name\) LIKE CONCAT\(\'%\', LOWER\(@customer_name\), \'%\'\))'
        
        if re.search(name_condition_pattern, sql_template):
            # Erstelle die neue Bedingung mit beiden Namen
            new_condition = (
                "(" + 
                "LOWER(la.first_name) LIKE CONCAT('%', LOWER(@customer_name), '%') OR " +
                "LOWER(la.last_name) LIKE CONCAT('%', LOWER(@customer_name), '%') OR " +
                "LOWER(la.first_name) LIKE CONCAT('%', LOWER(@secondary_name), '%') OR " +
                "LOWER(la.last_name) LIKE CONCAT('%', LOWER(@secondary_name), '%')" +
                ")"
            )
            
            # Ersetze die alte Bedingung mit der neuen
            modified_sql = re.sub(name_condition_pattern, new_condition, sql_template)
            
            if modified_sql != sql_template:
                logging.info("SQL-Abfrage für mehrere Namensvarianten modifiziert")
                query_data["sql_template"] = modified_sql
            else:
                logging.warning("Konnte die SQL-Abfrage nicht modifizieren")
    
    return query_data, params

def apply_query_enhancements(function_name, query_data, params):
    """
    Wendet verschiedene Verbesserungen auf SQL-Abfragen an, basierend auf dem Funktionsnamen
    und den Parametern.
    
    Args:
        function_name (str): Name der Funktion/Abfrage
        query_data (dict): Die Query-Daten aus query_patterns.json
        params (dict): Die Parameter für die Abfrage
        
    Returns:
        Tuple[dict, dict]: Aktualisierte query_data und params
    """
    # Verbesserungen für kundenspezifische Abfragen
    if function_name in ["get_customer_history", "get_care_givers_for_customer"]:
        query_data, params = enhance_customer_query(query_data, params)
    
    # Hier könnten weitere abfragespezifische Verbesserungen hinzugefügt werden
    
    return query_data, params
