# PythonAnywhere Deployment Guide

Follow these steps in the PythonAnywhere bash console to deploy the redesigned XORA chatbot.

## 1. Clone or Update Repository

If you haven't cloned the repository yet:
```bash
git clone https://github.com/your-repo/PFS-Bot.git
cd PFS-Bot
```

If you already have the repository, update it and switch to the new branch:
```bash
cd PFS-Bot
git fetch
git checkout new_design
```

## 2. Set Up Python Environment

First, create a virtual environment if you don't have one:
```bash
python3 -m venv venv
source venv/bin/activate
```

Then install the Python dependencies:
```bash
pip install -r backend/requirements.txt
```

## 3. Install Node.js and npm

PythonAnywhere should already have Node.js installed. Check the version:
```bash
node -v
npm -v
```

If not, you can set it up using nvm (Node Version Manager):
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh | bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm install 16  # Install Node.js v16
```

## 4. Build the React Frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

## 5. Configure the Web App

Go to the Web tab in the PythonAnywhere dashboard and:

1. Create a new web app or modify your existing one
2. Choose "Manual Configuration" (not "Flask")
3. Set the Python version to match your venv (3.9+ recommended)

Edit your WSGI configuration file to point to the backend app:

```python
import sys
import os

# Add the project directory to the Python path
path = '/home/your_username/PFS-Bot'
if path not in sys.path:
    sys.path.append(path)

# Add the backend directory
backend_path = os.path.join(path, 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

# Point to the Flask app
from backend.app import app as application
```

## 6. Configure Static Files

In the Web tab, add a static files mapping:
- URL: `/static/`
- Directory: `/home/your_username/PFS-Bot/frontend/build/static/`

Add another mapping for the React build files:
- URL: `/`
- Directory: `/home/your_username/PFS-Bot/frontend/build/`

## 7. Update Application Settings

Modify the backend/app.py file to ensure it works with PythonAnywhere:

```bash
cd /home/your_username/PFS-Bot
```

Edit the app.py file to update paths:
```python
# Edit the static folder and template folder paths
app = Flask(__name__, 
    static_folder='../frontend/build/static', 
    template_folder='../frontend/build')
```

## 8. Environment Variables

Set up any required environment variables in the PythonAnywhere dashboard's "Web" tab under "Environment variables":

```
SECRET_KEY=your_secret_key_here
FLASK_ENV=production
```

## 9. Reload the Web App

Click the "Reload" button in the Web tab of the PythonAnywhere dashboard.

## 10. Troubleshooting

Check the error logs if the app doesn't work:
- Go to the Web tab
- Click on the "Error log" link

Common issues:
- Path problems (check your WSGI file)
- Missing dependencies
- Static file configurations
- WSGI configuration errors
- File permissions

Your redesigned XORA chatbot should now be deployed and accessible via your PythonAnywhere URL.