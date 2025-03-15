# How to Integrate the LLM Query Selector

To test the improved query selector implementation, follow these steps:

## 1. Pull the changes from the staging branch

Make sure you have the latest code by running:
```bash
git pull origin staging
```

This will add two new files to your project:
- `query_selector.py` - The implementation of the LLM-based query selector
- `updates/app_updates.md` - Documentation with all the changes needed

## 2. Download the complete updated implementation

1. Download the updated implementation file from the following URL:
   ```
   https://raw.githubusercontent.com/quualle/PFS-Bot/staging/updated_app.py
   ```

2. Or, you can find it locally in this repository at:
   ```
   /path/to/PFS-Bot/updated_app.py
   ```

3. Replace your existing app.py with this file:
   ```bash
   mv updated_app.py app.py
   ```

   Or if you want to be safe:
   ```bash
   cp app.py app.py.backup
   cp updated_app.py app.py
   ```

## 3. Reload your PythonAnywhere environment

After replacing the file, reload your Python Anywhere web app to apply the changes.

## 4. Test the implementation with these queries

These queries will test different aspects of the LLM-based query selector:

### Simple queries
- "Zeige mir meine aktiven Care Stays"
- "Wieviel Umsatz habe ich im Mai gemacht?"
- "Welche Kunden haben gekündigt?"

### Complex queries
- "Zeige alle Leads vom letzten Monat, die zu Kunden konvertiert wurden"
- "Wie war meine Performance im letzten Quartal?"
- "Welche Agenturen bringen mir den meisten Umsatz?"

### Edge cases
- "Ich möchte über Pflegeversicherung sprechen"
- "Zeige mir Kunden ohne klare Zeitangabe"

## 5. Check the logs for feedback

The implementation will log feedback about query selections to a file named `query_selection_feedback.jsonl`. You can check this file to see how the LLM is performing with query selection.