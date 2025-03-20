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

original_lines = content.count('\n')
print(f"Original file has {original_lines} lines")

# Patterns to match and remove (regular expressions)
patterns = [
    # Test routes (except test_bigquery)
    r'@app\.route\([\'"]/test_session[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]/test_date_extraction[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]/test_function_call[\'"].*?\n.*?(?=@app\.route)',
    
    # Debug routes
    r'[ \t]*@app\.route\([\'"]/debug_oauth[\'"].*?\n.*?(?=[ \t]*@app\.route)',
    r'@app\.route\([\'"]/debug_function_call[\'"].*?\n.*?(?=@app\.route)',
    r'@app\.route\([\'"]\/debug[\'"].*?\n.*?(?=@app\.route)',
    
    # Redundant update_chat_history
    r'@app\.route\([\'"]/update_chat_history[\'"].*?\n.*?(?=@app\.route)',
    
    # check_seller_id function
    r'@app\.route\([\'"]/check_seller_id[\'"].*?\n.*?(?=@app\.route)',
]

# Remove the patterns
print("Removing test and debug routes...")
for pattern in patterns:
    content = re.sub(pattern, '', content, flags=re.DOTALL)

# Remove DEBUG_CATEGORIES
print("Removing DEBUG_CATEGORIES...")
content = re.sub(r'DEBUG_CATEGORIES = \{[^}]*\}', '', content, flags=re.DOTALL)

# Remove debug_print function
print("Removing debug_print function...")
content = re.sub(r'def debug_print\(.*?\):[^def]*', '', content, flags=re.DOTALL)

# Count debug_print calls
debug_print_calls = len(re.findall(r'debug_print\(', content))
print(f"Found {debug_print_calls} debug_print calls")

# Remove all debug_print calls
print("Removing debug_print calls...")
content = re.sub(r'[ \t]*debug_print\([^)]*\)[^\n]*\n', '', content)

# Fix duplicate imports
print("Fixing duplicate import of logging...")
content = re.sub(r'import logging\nimport logging', 'import logging', content)

# Simplify legacy approach code
print("Simplifying legacy approach code...")
content = re.sub(r'use_legacy_approach = True', 'use_legacy_approach = False', content)
content = re.sub(r'if use_legacy_approach:.*?else:', '', content, flags=re.DOTALL)

# Write the modified content to the output file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Count lines in the cleaned file
cleaned_lines = content.count('\n')
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
   - /debug_oauth
   - /debug_function_call
   - /debug (debug page)
   
3. Debug utilities:
   - DEBUG_CATEGORIES variable
   - debug_print function (removed {debug_print_calls} calls)
   
4. Redundant code:
   - Duplicate update_chat_history route (kept update_stream_chat_history)
   - check_seller_id debugging function
   - Duplicate import of logging
   
5. Simplified code:
   - Legacy approach code paths (always using the newer approach)

## Preserved Components
- /test_bigquery route (kept as requested)

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
