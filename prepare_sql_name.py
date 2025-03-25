import re
import logging

def prepare_customer_name_for_sql(customer_name):
    """
    Bereitet einen Kundennamen für die SQL-Suche vor und behält dabei wichtige 
    Identifikatoren wie (I) für Verkäufer bei.
    
    Args:
        customer_name (str): Der ursprüngliche Kundenname
        
    Returns:
        str: Der Name für die SQL-Suche sowie ein erweiterter Suchbegriff
    """
    if not customer_name:
        return customer_name, None
    
    original_name = customer_name.lower().strip()
    
    # Pattern, um Klammer-Identifikatoren wie (I), (B), etc. zu erkennen
    identifier_pattern = r'(\w+)\s*[\(\[]([a-zA-Z])[\)\]]'
    match = re.search(identifier_pattern, original_name)
    
    # Wenn wir einen Klammer-Identifikator finden
    if match:
        base_name = match.group(1).strip()
        identifier = match.group(2).upper()
        formatted_name = f"{base_name} ({identifier})"
        
        # Original-Name für die primäre Suche
        search_name = formatted_name
        
        # Für die SQL-Suche geben wir auch den Basis-Namen ohne Klammer zurück
        # als sekundären Suchbegriff
        secondary_name = base_name
        
        logging.info(f"Identifier erkannt: '{original_name}' -> Primär: '{search_name}', Sekundär: '{secondary_name}'")
        return search_name, secondary_name
    
    # Wenn kein spezieller Klammer-Identifikator gefunden wurde
    logging.info(f"Kein Spezial-Identifikator in '{original_name}' gefunden")
    return original_name, None


if __name__ == "__main__":
    # Test-Cases
    test_cases = [
        "Ramm (I)",
        "Ramm(I)",
        "Gerhard Ramm (I)",
        "Müller-Schmidt",
        "Schmidt (B)",
        "Küll",
        "Dr. Franz"
    ]
    
    print("Testing name preparation for SQL:")
    for test in test_cases:
        primary, secondary = prepare_customer_name_for_sql(test)
        print(f"Input: '{test}' → Primary: '{primary}', Secondary: '{secondary}'")
