import re
import logging

def extract_customer_name(user_message):
    """
    Extrahiert einen Kundennamen aus einer Benutzeranfrage
    
    Sucht nach typischen Mustern wie "Kunde XYZ", "Herr XYZ", "Frau XYZ" oder 
    "über XYZ" in verschiedenen Variationen.
    
    Args:
        user_message: Die Nachricht des Benutzers
        
    Returns:
        str or None: Der extrahierte Kundenname oder None
    """
    user_message = user_message.lower()
    
    # Spezifische Muster für Namen mit römischen Ziffern in Klammern
    roman_patterns = [
        r'kunden?\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'herr\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'frau\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'über\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?'
    ]
    
    for pattern in roman_patterns:
        match = re.search(pattern, user_message)
        if match and len(match.groups()) >= 2:
            base_name = match.group(1).strip()
            roman_numeral = match.group(2).strip().upper()
            if base_name and roman_numeral:
                customer_name = f"{base_name} ({roman_numeral})"
                logging.info(f"Erkannter Name mit römischer Ziffer: {customer_name}")
                return customer_name
    
    # Nach Mustern suchen wie "Kunde XYZ", "Herr XYZ", "Frau XYZ", "über XYZ"
    customer_patterns = [
        r'kunde[n]?[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'kunden[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'herr[n]?[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'frau[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'familie[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'über[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'von[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'für[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'bei[:\s]+([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)',
        r'zum kunden ([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[](?:[ivx]+|[0-9]+)[\)\]])?)'
    ]
    
    for pattern in customer_patterns:
        match = re.search(pattern, user_message)
        if match:
            customer_name = match.group(1).strip()
            if len(customer_name) > 2 and not customer_name.startswith(('der ', 'die ', 'das ')):
                logging.info(f"Erkannter Kundenname (Muster): {customer_name}")
                return customer_name
    
    # Direkte Suche nach "Name (römische Zahl)" ohne Einleitungswörter
    direct_pattern = r'\b([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]'
    match = re.search(direct_pattern, user_message)
    if match:
        base_name = match.group(1).strip()
        roman_numeral = match.group(2).strip().upper()
        customer_name = f"{base_name} ({roman_numeral})"
        logging.info(f"Direkt erkannter Name mit römischer Ziffer: {customer_name}")
        return customer_name
    
    # Nach alleinstehenden Namen suchen, wenn sie in Anführungszeichen stehen
    quotes_pattern = r'["\']([a-zäöüß]+(?:[\-\s][a-zäöüß]+)*(?:\s*[\(\[][ivx]+[\)\]])?)["\']'
    match = re.search(quotes_pattern, user_message)
    if match:
        customer_name = match.group(1).strip()
        logging.info(f"Kundenname in Anführungszeichen erkannt: {customer_name}")
        return customer_name
    
    return None

# Test function
def test_extract_customer_name():
    test_cases = [
        "Was kannst du mir über den Kunden Ramm(I) sagen?",
        "Was kannst du mir über den Kunden Ramm (I) sagen?",
        "Zeige Informationen für Herrn Müller-Schmidt",
        "Info über Familie Meier",
        "Kunde Jansen, Verträge",
        "Suche nach Frau Schmidt (65)",
        "Was weiß ich über Küll?",
        "Was gibt es Neues zu Herrn Dr. Franz",
        "Informationen zum Kunden Gerhard Ramm (I)",
        "Informationen zum Kunden Gerhard Ramm(I)",
    ]
    
    print("Testing name extraction:")
    for test in test_cases:
        result = extract_customer_name(test)
        print(f"Input: '{test}' → Extracted: '{result}'")

# Run the test if executed directly
if __name__ == "__main__":
    # Konfiguriere Logging für Tests
    logging.basicConfig(level=logging.INFO)
    test_extract_customer_name()
