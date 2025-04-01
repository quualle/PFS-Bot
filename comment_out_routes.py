"""
Script to comment out routes that have been migrated to blueprints.
This script will read app.py, identify routes that have been outsourced to blueprints,
and comment them out while preserving the rest of the file.
"""

import re
import os
import sys
from pathlib import Path

# Define the routes that have been outsourced to blueprints
OUTSOURCED_ROUTES = [
    # chat_routes.py
    r"@app\.route\(\"/clarify\"",
    r"@app\.route\(\"/\"",
    r"@app\.route\(\"/update_stream_chat_history\"",
    r"@app\.route\(\"/get_clarification_response\"",
    r"@app\.route\(\"/clear_chat_history\"",
    
    # dashboard_routes.py
    r"@app\.route\(\"/get_active_care_stays_now\"",
    r"@app\.route\(\"/get_dashboard_data\"",
    r"@app\.route\(\"/debug_dashboard\"",
    
    # user_management.py
    r"@app\.route\(\"/get_username\"",
    r"@app\.route\(\"/set_username\"",
    r"@app\.route\(\"/check_login\"",
    r"@app\.route\(\"/reset_session\"",
    r"@app\.route\(\"/toggle_notfall_mode\"",
    r"@app\.route\(\"/logout\"",
    r"@app\.route\(\"/admin_login\"",
    
    # feedback_routes.py
    r"@app\.route\(\"/store_feedback\"",
]

def find_route_blocks(content, route_patterns):
    """Find blocks of code that define the routes specified in route_patterns."""
    blocks = []
    
    # First, split the content into lines
    lines = content.split('\n')
    
    for i, line in enumerate(lines):
        # Check if the line contains a route decorator that matches any of our patterns
        for pattern in route_patterns:
            if re.search(pattern, line):
                # Found a route decorator, now find the end of the function
                start_line = i
                
                # Find the function definition line (the line after the decorator)
                func_def_line = i + 1
                while func_def_line < len(lines) and not re.match(r'def\s+\w+', lines[func_def_line]):
                    func_def_line += 1
                
                if func_def_line >= len(lines):
                    print(f"Warning: Could not find function definition for route starting at line {i+1}")
                    continue
                
                # Extract the function name
                func_name_match = re.match(r'def\s+(\w+)', lines[func_def_line])
                if not func_name_match:
                    print(f"Warning: Could not extract function name from line {func_def_line+1}")
                    continue
                
                func_name = func_name_match.group(1)
                
                # Find the end of this function (next function or route decorator)
                end_line = func_def_line + 1
                indent_level = len(lines[func_def_line]) - len(lines[func_def_line].lstrip())
                
                # Keep going until we find a line with the same indent level that starts with 'def' or '@'
                while end_line < len(lines):
                    if (lines[end_line].strip() and 
                        len(lines[end_line]) - len(lines[end_line].lstrip()) <= indent_level and 
                        (lines[end_line].lstrip().startswith('def') or 
                         lines[end_line].lstrip().startswith('@'))):
                        break
                    end_line += 1
                
                blocks.append({
                    'start': start_line,
                    'end': end_line,
                    'route_pattern': pattern,
                    'function_name': func_name
                })
                break  # Found a match, no need to check other patterns
    
    return blocks

def comment_out_blocks(content, blocks):
    """Comment out blocks of code in the content."""
    lines = content.split('\n')
    commented_lines = []
    
    for i, line in enumerate(lines):
        # Check if this line is part of a block to comment out
        in_block = False
        for block in blocks:
            if block['start'] <= i < block['end']:
                in_block = True
                break
        
        if in_block:
            # If the line is not already a comment, add a comment character
            if not line.strip().startswith('#'):
                commented_lines.append(f"# {line}")
            else:
                commented_lines.append(line)
        else:
            commented_lines.append(line)
    
    return '\n'.join(commented_lines)

def main():
    # Ensure we're working with the app.py file
    app_path = Path('app.py')
    if not app_path.exists():
        print("Error: app.py not found in the current directory")
        sys.exit(1)
    
    # Create a backup of app.py
    backup_path = app_path.with_suffix('.py.bak')
    if not backup_path.exists():
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Created backup at {backup_path}")
    else:
        print(f"Backup already exists at {backup_path}")
        with open(app_path, 'r', encoding='utf-8') as f:
            content = f.read()
    
    # Find route blocks that match our patterns
    blocks = find_route_blocks(content, OUTSOURCED_ROUTES)
    
    if not blocks:
        print("No matching routes found to comment out")
        return
    
    print(f"Found {len(blocks)} route blocks to comment out:")
    for block in blocks:
        print(f"  - {block['function_name']} (lines {block['start']+1}-{block['end']})")
    
    # Comment out the blocks
    modified_content = comment_out_blocks(content, blocks)
    
    # Write the modified content back to app.py
    with open(app_path, 'w', encoding='utf-8') as f:
        f.write(modified_content)
    
    print(f"Successfully commented out {len(blocks)} route blocks in app.py")
    print("A backup of the original file was saved as app.py.bak")

if __name__ == "__main__":
    main()
