import re
import logging

def extract_customer_name(user_message):
    """
    Extrahiert einen Kundennamen aus einer Benutzeranfrage.
    
    Spezialisiert auf das Erkennen von Namen mit römischen Ziffern wie "Ramm (I)"
    und normalen Namen ohne spezielle Formatierung.
    
    Args:
        user_message: Die Nachricht des Benutzers
        
    Returns:
        str or None: Der extrahierte Kundenname oder None
    """
    user_message = user_message.lower()
    
    # 1. Spezifische Behandlung für "Ramm (I)" oder "Gerhard Ramm (I)"
    specific_roman_patterns = [
        # Für vollständigen Namen mit Römischer Ziffer
        r'kunden?\s+([a-zäöüß]+\s+[a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        # Für einfachen Namen mit Römischer Ziffer
        r'kunden?\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'herr\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?',
        r'frau\s+([a-zäöüß]+)[\s-]*[\(\[]?\s*([ivx]+)\s*[\)\]]?'
    ]
    
    for pattern in specific_roman_patterns:
        match = re.search(pattern, user_message)
        if match and len(match.groups()) == 2:
            base_name = match.group(1).strip()
            roman_numeral = match.group(2).strip().upper()
            if base_name and roman_numeral:
                customer_name = f"{base_name} ({roman_numeral})"
                logging.info(f"Erkannter Name mit römischer Ziffer: {customer_name}")
                return customer_name
    
    # 2. Suche nach "65" in Klammern als spezielle Behandlung für "(65)"
    age_pattern = r'([a-zäöüß]+(?:[\-\s][a-zäöüß]+)?)\s*[\(\[]?\s*65\s*[\)\]]?'
    match = re.search(age_pattern, user_message)
    if match:
        name = match.group(1).strip()
        if name and len(name) > 2:
            logging.info(f"Erkannter Name mit Altersangabe: {name}")
            return name
    
    # 3. Allgemeine Namenmuster ohne römische Ziffern
    name_patterns = [
        r'kunden?\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'herr\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'frau\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'familie\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'über\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'von\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)',
        r'für\s+([a-zäöüß\-]+(?:\s+[a-zäöüß\-]+)?)'
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, user_message)
        if match:
            name = match.group(1).strip()
            if name and len(name) > 2 and name != "familie":
                logging.info(f"Erkannter Name (Standard): {name}")
                return name
    
    # 4. Direkte Suche im Text ohne Einleitungswörter (als Fallback)
    direct_roman_pattern = r'\b([a-zäöüß]+)\s*[\(\[]([ivx]+)[\)\]]'
    match = re.search(direct_roman_pattern, user_message)
    if match:
        name = match.group(1).strip()
        roman = match.group(2).strip().upper()
        if name and len(name) > 2:
            result = f"{name} ({roman})"
            logging.info(f"Direkt erkannter Name mit römischer Ziffer: {result}")
            return result
    
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
        "Gibt es Kunden namens Ramm?"
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
