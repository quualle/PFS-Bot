import re
import logging

def extract_customer_name(user_message):
    """
    Extrahiert einen Kundennamen aus einer Benutzeranfrage
    
    Sucht nach typischen Mustern wie "Kunde XYZ", "Herr XYZ", "Frau XYZ" oder 
    "über XYZ" in verschiedenen Variationen. Unterstützt auch Namen mit Klammern, 
    Zahlen und Sonderzeichen.
    
    Args:
        user_message: Die Nachricht des Benutzers
        
    Returns:
        str or None: Der extrahierte Kundenname oder None
    """
    user_message = user_message.lower()
    
    # Direkte Extraktion für Muster wie "Ramm (I)" oder "Müller-Schmidt"
    # Diese Regex unterstützt Klammern, römische Ziffern, Bindestriche, etc.
    direct_name_patterns = [
        r'kunden?\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)\s*[\(\[]?([ivx]+)[\)\]]?',
        r'herr\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)\s*[\(\[]?([ivx]+)[\)\]]?',
        r'frau\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)\s*[\(\[]?([ivx]+)[\)\]]?',
        r'über\s+([a-zäöüß]+(?:[\-\s]?[a-zäöüß]+)?)\s*[\(\[]?([ivx]+)[\)\]]?',
        r'\b([a-zäöüß]+)\s*[\(\[]([ivx]+)[\)\]]'
    ]
    
    # Zuerst versuchen, spezifische Muster mit römischen Ziffern zu erkennen
    for pattern in direct_name_patterns:
        match = re.search(pattern, user_message)
        if match:
            if len(match.groups()) == 2:
                base_name = match.group(1)
                roman_numeral = match.group(2)
                customer_name = f"{base_name} ({roman_numeral.upper()})"
                logging.info(f"Erkannter Name mit römischer Ziffer: {customer_name}")
                return customer_name
    
    # Nach Mustern suchen wie "Kunde XYZ", "Herr XYZ", "Frau XYZ", "über XYZ"
    # Erweiterte Regex, die auch Klammern, Zahlen und Sonderzeichen erlaubt
    customer_patterns = [
        r'kunde[n]?[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'kunden[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'herr[n]?[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'frau[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'familie[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'über[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'von[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'für[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'bei[:\s]+([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)',
        r'zum kunden ([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]+?)(?:\s+sagen|\?|\.|\,|$)'
    ]
    
    for pattern in customer_patterns:
        match = re.search(pattern, user_message)
        if match:
            # Bereinigen des extrahierten Textes
            customer_name = match.group(1).strip()
            # Entfernen von Stoppwörtern am Ende
            customer_name = re.sub(r'\b(der|die|das|und|oder|als|wie)\s*$', '', customer_name).strip()
            
            # Prüfen auf übliche Abkürzungen oder unerwünschte Teile
            if len(customer_name) > 2 and not customer_name.startswith(('der ', 'die ', 'das ')):
                logging.info(f"Erkannter Kundenname: {customer_name}")
                return customer_name
    
    # Nach alleinstehenden Namen suchen, wenn sie in Anführungszeichen stehen
    quotes_pattern = r'["\']([a-zäöüß0-9\s\(\)\[\]\{\}\-\.]{3,})["\']'
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
        "Was gibt es Neues zu Herrn Dr. Franz"
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
