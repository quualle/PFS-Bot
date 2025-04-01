"""
A simplified script to comment out routes that have been migrated to blueprints.
This script will read app.py and search for specified route decorators to comment out.
"""

import os
import sys
from pathlib import Path

def main():
    # Ensure we're working with the app.py file
    app_path = Path('app.py')
    if not app_path.exists():
        print("Error: app.py not found in the current directory")
        sys.exit(1)
    
    # Define the routes to look for
    routes_to_comment = [
        "/",  # Main chat route
        "/clarify",
        "/update_stream_chat_history",
        "/get_clarification_response",
        "/clear_chat_history",
        "/get_active_care_stays_now",
        "/get_dashboard_data",
        "/debug_dashboard", 
        "/get_username",
        "/set_username",
        "/check_login",
        "/reset_session",
        "/toggle_notfall_mode",
        "/logout",
        "/admin_login",
        "/store_feedback"
    ]
    
    # Create a backup of app.py
    backup_path = Path('app_routes_backup.py')
    if not backup_path.exists():
        with open(app_path, 'r', encoding='utf-8') as f:
            original_content = f.read()
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original_content)
        print(f"Created backup at {backup_path}")
    else:
        print(f"Backup already exists at {backup_path}")
    
    # Read the file line by line and comment out route decorators
    with open(app_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified_lines = []
    route_found = False
    comment_block = False
    routes_commented = 0
    
    for line in lines:
        if any(f"@app.route('{route}'" in line or f'@app.route("{route}"' in line for route in routes_to_comment):
            # Found a route to comment out
            route_found = True
            comment_block = True
            modified_lines.append(f"# {line}")
            routes_commented += 1
            print(f"Found route to comment: {line.strip()}")
        elif comment_block:
            # We're in a block to comment
            if line.strip() == "" or line.strip().startswith("#"):
                # Empty line or already a comment
                modified_lines.append(line)
            elif line.strip().startswith("@"):
                # Another decorator - might be a method decorator
                modified_lines.append(f"# {line}")
            elif line.strip().startswith("def "):
                # Function definition
                modified_lines.append(f"# {line}")
            elif line.lstrip().startswith("@app.route"):
                # New route decorator, stop commenting
                comment_block = False
                modified_lines.append(line)
            else:
                # Regular line in the function
                modified_lines.append(f"# {line}")
        else:
            # Regular line
            modified_lines.append(line)
    
    if route_found:
        # Write the modified content back to app.py
        with open(app_path, 'w', encoding='utf-8') as f:
            f.writelines(modified_lines)
        
        print(f"Successfully commented out {routes_commented} route references in app.py")
        print("The original file was backed up to app_routes_backup.py")
    else:
        print("No matching routes found to comment out")

if __name__ == "__main__":
    main()
