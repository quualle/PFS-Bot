# PFS-Bot Usage Guidelines

## Setup & Running
- Install dependencies: `pip install -r requirements.txt`
- Run application: `python app.py`
- Debug mode: `python app.py --debug`

## Code Style & Standards
- **Imports**: Group standard library, third-party, and local imports
- **Naming**: Use snake_case for functions/variables, PascalCase for classes
- **Documentation**: All functions need docstrings with description and params
- **Error Handling**: Use try/except blocks with specific exceptions
- **Type Hints**: Include type hints for parameters and return values

## Project Structure
- app.py: Main Flask application
- bigquery_functions.py: Database interaction logic
- query_patterns.json: SQL query templates
- tool_config.yaml: Tool selection configuration

## Database
- Uses Google BigQuery for data storage
- Refer to table_schema.json for database structure