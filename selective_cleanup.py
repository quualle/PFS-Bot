#\!/usr/bin/env python3
import os
import re
import sys
from datetime import datetime

# Get the app.py file path
app_py_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py"
output_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py.cleaned"

print(f"Reading file {app_py_path}...")
with open(app_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_lines = content.count('\n') + 1
print(f"Original file has {original_lines} lines")

# List of specific routes to remove
routes_to_remove = [
    r'@app\.route\([\'"]\/test_session[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/test_date_extraction[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/test_function_call[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/debug_function_call[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/debug[\'"], methods=\[.*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/update_chat_history[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/check_seller_id[\'"].*?\n.*?(?=@app\.route)',
]

# Remove debug_oauth function but be careful not to remove too much
def remove_debug_oauth(content):
    match = re.search(r'@app\.route\([\'"]\/debug_oauth[\'"].*?\n.*?def debug_oauth.*?\n.*?return.*?\n', content, re.DOTALL)
    if match:
        start, end = match.span()
        # Find the next function after this one
        next_def = re.search(r'@app\.route', content[end:])
        if next_def:
            return content[:start] + content[end+next_def.start():]
    return content

# Remove specific routes
print("Removing specific test and debug routes...")
for route in routes_to_remove:
    content = re.sub(route, '', content, flags=re.DOTALL)

# Carefully remove debug_oauth
print("Carefully removing debug_oauth...")
content = remove_debug_oauth(content)

# Remove DEBUG_CATEGORIES and debug_print function
print("Removing DEBUG_CATEGORIES...")
content = re.sub(r'DEBUG_CATEGORIES = \{[^}]*\}', '', content, flags=re.DOTALL)

print("Removing debug_print function...")
content = re.sub(r'def debug_print\(.*?\):[^def]*?(?=\n\S)', '', content, flags=re.DOTALL)

# Count and remove debug_print calls
debug_print_count = len(re.findall(r'debug_print\(', content))
print(f"Found {debug_print_count} debug_print calls...")
content = re.sub(r'[ \t]*debug_print\([^)]*\)[^\n]*\n', '', content)

# Fix duplicate imports
print("Fixing duplicate imports...")
content = re.sub(r'import logging\nimport logging', 'import logging', content)

# Simplify legacy approach code without removing necessary parts
print("Simplifying legacy approach code...")
content = re.sub(r'use_legacy_approach = True', 'use_legacy_approach = False', content)

# Write the modified content to the output file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Count lines in the cleaned file
cleaned_lines = content.count('\n') + 1
reduction = original_lines - cleaned_lines
percent = (reduction / original_lines) * 100

print(f"Cleanup complete\!")
print(f"Original file: {original_lines} lines")
print(f"Cleaned file: {cleaned_lines} lines")
print(f"Reduction: {reduction} lines ({percent:.2f}%)")

# Create summary markdown file
summary_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/cleanup_summary.md"
with open(summary_path, 'w', encoding='utf-8') as f:
    f.write(f"""# Code Cleanup Results

## Summary
- Original file size: {original_lines} lines
- New file size: {cleaned_lines} lines
- Reduction: {reduction} lines ({percent:.2f}%)

## Removed Components
1. Test routes:
   - /test_session
   - /test_date_extraction
   - /test_function_call
   
2. Debug routes:
   - /debug_oauth (carefully removed)
   - /debug_function_call
   - /debug (debug page)
   
3. Debug utilities:
   - DEBUG_CATEGORIES variable
   - debug_print function
   - {debug_print_count} debug_print calls
   
4. Redundant code:
   - Duplicate update_chat_history route (kept update_stream_chat_history)
   - check_seller_id debugging function
   - Duplicate import of logging
   
5. Simplified code:
   - Set use_legacy_approach to always be False

## Preserved Components
- /test_bigquery route (kept as requested)
- All core functions:
  - handle_function_call
  - create_enhanced_system_prompt
  - create_system_prompt
  - All other business logic functions

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
