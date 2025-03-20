import re
import logging

def extract_customer_name(user_message):
    """
    Extrahiert einen Kundennamen aus einer Benutzeranfrage.
    
    Sucht nach typischen Mustern wie "Kunde XYZ", "Herr XYZ", "Frau XYZ" etc.
    Unterstützt auch Namen mit römischen Ziffern in Klammern wie "Ramm (I)".
    
    Args:
        user_message: Die Nachricht des Benutzers
        
    Returns:
        str or None: Der extrahierte Kundenname oder None
    """
    user_message = user_message.lower()
    
    # Muster für volle Namen mit römischen Ziffern wie "Gerhard Ramm (I)"
    full_name_roman_pattern = r'kunden?\s+([a-zäöüß]+\s+[a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?'
    match = re.search(full_name_roman_pattern, user_message)
    if match:
        base_name = match.group(1).strip()
        roman_numeral = match.group(2).strip().upper()
        customer_name = f"{base_name} ({roman_numeral})"
        logging.info(f"Erkannter vollständiger Name mit römischer Ziffer: {customer_name}")
        return customer_name
    
    # Muster für "Ramm (I)" oder ähnliche Formate
    name_roman_patterns = [
        r'kunden?\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'herr\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'frau\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'über\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'für\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'vom?\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'zum?\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?'
    ]
    
    for pattern in name_roman_patterns:
        match = re.search(pattern, user_message)
        if match and len(match.groups()) >= 2:
            base_name = match.group(1).strip()
            roman_numeral = match.group(2).strip().upper()
            if base_name and roman_numeral and len(base_name) > 2:
                customer_name = f"{base_name} ({roman_numeral})"
                logging.info(f"Erkannter Name mit römischer Ziffer: {customer_name}")
                return customer_name
    
    # Normale Namen mit Einleitungswörtern
    normal_name_patterns = [
        r'kunde[n]?\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'herr[n]?\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'frau\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'familie\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'über\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'von\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'für\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)'
    ]
    
    for pattern in normal_name_patterns:
        match = re.search(pattern, user_message)
        if match:
            customer_name = match.group(1).strip()
            # Nur zurückgeben, wenn es ein vernünftiger Name ist
            if len(customer_name) > 2 and not customer_name.startswith(('der ', 'die ', 'das ')):
                logging.info(f"Erkannter normaler Kundenname: {customer_name}")
                return customer_name
    
    # Direkte Suche nach "Name (römische Zahl)" ohne Einleitungswörter
    direct_roman_pattern = r'\b([a-zäöüß]+)\s*[\(\[]([ivx]+)[\)\]]'
    match = re.search(direct_roman_pattern, user_message)
    if match:
        base_name = match.group(1).strip()
        roman_numeral = match.group(2).strip().upper()
        if len(base_name) > 2:  # Nur zurückgeben, wenn es ein vernünftiger Name ist
            customer_name = f"{base_name} ({roman_numeral})"
            logging.info(f"Direkt erkannter Name mit römischer Ziffer: {customer_name}")
            return customer_name
    
    # Nach Namen in Anführungszeichen suchen
    quotes_pattern = r'["\'„]([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)["\'"]'
    match = re.search(quotes_pattern, user_message)
    if match:
        customer_name = match.group(1).strip()
        if len(customer_name) > 2:  # Nur zurückgeben, wenn es ein vernünftiger Name ist
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
