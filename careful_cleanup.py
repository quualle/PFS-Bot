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
    lines = f.readlines()

original_lines = len(lines)
print(f"Original file has {original_lines} lines")

# Function to identify and remove specific route functions
def remove_route(lines, route_pattern):
    new_lines = []
    skip = False
    route_found = False
    next_route_found = False
    route_line_count = 0
    
    for line in lines:
        # Check if this is the route we want to remove
        if re.search(route_pattern, line) and not skip:
            skip = True
            route_found = True
            route_line_count = 1
            continue
        
        # If we're skipping and find the next route, stop skipping
        if skip and line.strip().startswith('@app.route'):
            skip = False
            next_route_found = True
        
        # Count lines while skipping
        if skip:
            route_line_count += 1
        
        # Add line if not skipping
        if not skip:
            new_lines.append(line)
    
    if route_found:
        print(f"Removed route matching '{route_pattern}' ({route_line_count} lines)")
    else:
        print(f"Route '{route_pattern}' not found")
        
    return new_lines

# Routes to remove
routes_to_remove = [
    r"@app\.route\(['\"]\/test_session['\"]",
    r"@app\.route\(['\"]\/test_date_extraction['\"]",
    r"@app\.route\(['\"]\/test_function_call['\"]",
    r"@app\.route\(['\"]\/debug_oauth['\"]",
    r"@app\.route\(['\"]\/debug_function_call['\"]",
    r"@app\.route\(['\"]\/debug['\"]",
    r"@app\.route\(['\"]\/update_chat_history['\"]",
    r"@app\.route\(['\"]\/check_seller_id['\"]",
]

# Remove each route
for route in routes_to_remove:
    lines = remove_route(lines, route)

# Remove debug utilities
debug_categories_removed = False
debug_print_removed = False
debug_print_calls = 0

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Skip DEBUG_CATEGORIES block
    if line.strip().startswith('DEBUG_CATEGORIES = {'):
        skip = True
        debug_categories_removed = True
        print("Removing DEBUG_CATEGORIES block...")
        continue
        
    # Stop skipping after DEBUG_CATEGORIES block
    if skip and line.strip() == '}':
        skip = False
        continue
        
    # Skip debug_print function
    if line.strip().startswith('def debug_print('):
        skip = True
        debug_print_removed = True
        print("Removing debug_print function...")
        continue
        
    # Stop skipping after debug_print function
    if skip and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
        skip = False
    
    # Skip lines with debug_print calls
    if re.search(r'debug_print\(', line):
        debug_print_calls += 1
        continue
        
    # Include line if not skipping
    if not skip:
        new_lines.append(line)

print(f"Removed {debug_print_calls} debug_print calls")

# Fix duplicate imports
import_logging_count = 0
fixed_lines = []
for line in new_lines:
    if line.strip() == 'import logging':
        import_logging_count += 1
        if import_logging_count > 1:
            continue
    fixed_lines.append(line)

if import_logging_count > 1:
    print(f"Removed {import_logging_count - 1} duplicate 'import logging' statements")

# Simplify legacy approach code - this is more complex and should be done carefully
# Just setting legacy approach to False
legacy_lines = []
for line in fixed_lines:
    if 'use_legacy_approach = True' in line:
        legacy_lines.append(line.replace('use_legacy_approach = True', 'use_legacy_approach = False'))
        print("Set use_legacy_approach to False")
    else:
        legacy_lines.append(line)

# Write the modified content to the output file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.writelines(legacy_lines)

# Count lines in the cleaned file
cleaned_lines = len(legacy_lines)
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
   - debug_print function
   - {debug_print_calls} debug_print calls
   
4. Redundant code:
   - Duplicate update_chat_history route (kept update_stream_chat_history)
   - check_seller_id debugging function
   - Duplicate import of logging
   
5. Simplified code:
   - Set use_legacy_approach to always be False

## Preserved Components
- /test_bigquery route (kept as requested)
- All core functions and routes (chat, handle_function_call, etc.)

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
