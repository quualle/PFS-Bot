import sys
import os

# add your project directory to the sys.path
project_home = '/home/PfS/staging'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Make sure we're using the root app.py, not backend/app.py
try:
    # Try to import directly first
    from app import app as application
except ImportError:
    # If that fails, be explicit about the file path
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", os.path.join(project_home, "app.py"))
    app_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_module)
    application = app_module.app