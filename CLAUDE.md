# XORA PFS-Bot Commands & Style Guide

## Core Commands
- Run application: `python app.py`
- Install dependencies: `pip install -r requirements.txt`
- Update dependencies: `pip freeze > requirements.txt`
- Run linting: `pylint *.py`
- Run type checking: `mypy --ignore-missing-imports *.py`
- Run tests: `pytest tests/`
- Run single test: `pytest tests/test_file.py::test_function -v`

## Code Style Guidelines
- Follow PEP 8 conventions for Python
- Use type annotations for function parameters and return values
- Organize imports: standard library, third-party, local (alphabetically within each group)
- Naming: snake_case for variables/functions, PascalCase for classes
- Document functions with docstrings (purpose, parameters, return values)
- Handle errors with try/except blocks and proper logging
- Prefer immutable data structures when possible
- Keep functions focused (single responsibility)
- Comment complex logic but avoid redundant comments
- Use f-strings for string formatting

## Project Structure
- Flask web application with BigQuery database integration
- Natural language processing using Claude/OpenAI for query translation
- Frontend: HTML templates in `/templates`, static assets in `/static`