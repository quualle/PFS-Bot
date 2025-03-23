"""
Conversation Manager für XORA Chatbot.
Verwaltet die Konversationshistorie und stellt Funktionen für Kontext-Handling bereit.
"""
import logging
import re
from typing import Dict, List, Any, Optional

# Setup logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s %(levelname)s:%(name)s:%(message)s', 
                   datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

class ConversationManager:
    """Verwaltet Konversationskontext und -historie für die Chatbot-Interaktionen."""
    
    def __init__(self, max_history: int = 10):
        """
        Initialisiert den ConversationManager.
        
        Args:
            max_history: Maximale Anzahl der zu speichernden Konversationsnachrichten
        """
        self.max_history = max_history
        
    def get_conversation_context(self, session_data: Dict) -> List[Dict]:
        """
        Extrahiert relevante Konversationshistorie aus den Session-Daten.
        
        Args:
            session_data: Die Session-Daten des Benutzers
            
        Returns:
            Liste mit relevanten Konversationsnachrichten
        """
        history = session_data.get("conversation_history", [])
        return history[-self.max_history:] if history else []
        
    def update_conversation(self, 
                           session_data: Dict, 
                           user_message: str, 
                           response: str, 
                           function_calls: Optional[Dict] = None) -> Dict:
        """
        Aktualisiert die Konversationshistorie mit neuen Nachrichten.
        
        Args:
            session_data: Die Session-Daten des Benutzers
            user_message: Die letzte Nachricht des Benutzers
            response: Die Antwort des Assistenten
            function_calls: Optional, Informationen über ausgeführte Funktionsaufrufe
            
        Returns:
            Aktualisierte Session-Daten
        """
        history = session_data.get("conversation_history", [])
        
        # Benutzer-Nachricht hinzufügen
        history.append({"role": "user", "content": user_message})
        
        # Funktionsaufrufe hinzufügen, falls vorhanden
        if function_calls:
            history.append({
                "role": "function", 
                "name": function_calls.get("name", "unknown_function"), 
                "content": function_calls.get("content", "{}")
            })
        
        # Assistenten-Antwort hinzufügen
        history.append({"role": "assistant", "content": response})
        
        # Historie bei Bedarf kürzen
        if len(history) > self.max_history * 2:
            history = history[-self.max_history:]
            
        session_data["conversation_history"] = history
        return session_data
    
    def extract_conversation_topic(self, session_data: Dict) -> str:
        """
        Extrahiert das Hauptthema der Konversation basierend auf der Historie.
        Nützlich für Kontext-Zusammenfassungen in Prompts.
        
        Args:
            session_data: Die Session-Daten des Benutzers
            
        Returns:
            Extrahiertes Thema oder leerer String
        """
        history = self.get_conversation_context(session_data)
        if not history:
            return ""
        
        # Für einfache Implementierung, nehmen wir die letzte Benutzeranfrage
        for msg in reversed(history):
            if msg.get("role") == "user":
                return msg.get("content", "")
        
        return ""

    @staticmethod
    def is_affirmative_response(response: str) -> bool:
        """
        Prüft, ob eine Antwort eine einfache Bestätigung ist.
        
        Args:
            response: Die zu prüfende Antwort
            
        Returns:
            True, wenn die Antwort als Bestätigung erkannt wird
        """
        affirmative_patterns = [
            r'^ja(\s|$|\.)',
            r'^ja,?\s*bitte',
            r'^ja\s*gerne',
            r'^stimmt',
            r'^korrekt',
            r'^genau',
            r'^ok(ay)?',
            r'^yes',
            r'👍'
        ]
        
        response = response.strip().lower()
        return any(re.match(pattern, response) for pattern in affirmative_patterns)
    
    def create_context_aware_system_prompt(self, 
                                         base_prompt: str, 
                                         session_data: Dict) -> str:
        """
        Erstellt einen kontextbewussten System-Prompt basierend auf der Konversationshistorie.
        
        Args:
            base_prompt: Der Basis-Prompt
            session_data: Die Session-Daten des Benutzers
            
        Returns:
            Erweiterter System-Prompt mit Kontext
        """
        topic = self.extract_conversation_topic(session_data)
        
        context_note = """
WICHTIG: Achte auf den Konversationskontext und die Kontinuität.

Wenn ein Benutzer auf eine Rückfrage mit einer einfachen Bestätigung wie 'ja' oder 'ja bitte' 
antwortet, wechsle NICHT das Thema oder starte eine neue Abfrage. 
Führe stattdessen die zuvor besprochene Aktion aus.
"""
        
        if topic:
            context_note += f"\nDie aktuelle Konversation zeigt, dass der Benutzer sich für folgendes interessiert: {topic}"
        
        return base_prompt + context_note
