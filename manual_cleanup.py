#!=/usr/bin/env python3
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

original_line_count = len(lines)
print(f"Original file has {original_line_count} lines")

# Dictionary to track changes
changes = {
    "test_session_route": 0,
    "test_date_extraction_route": 0,
    "test_function_call_route": 0,
    "debug_function_call_route": 0,
    "debug_route": 0,
    "update_chat_history_route": 0,
    "check_seller_id_route": 0,
    "debug_print_calls": 0,
    "debug_categories": 0,
    "debug_print_func": 0,
    "duplicate_imports": 0,
    "legacy_approach": 0
}

# 1. Remove specific routes while preserving others
def find_route_boundaries(lines, route_pattern):
    start_line = -1
    end_line = -1
    
    for i, line in enumerate(lines):
        if re.search(route_pattern, line):
            start_line = i
            # Find the next route or the end of file
            for j in range(i + 1, len(lines)):
                if re.search(r'^@app\.route', lines[j]):
                    end_line = j
                    break
            if end_line == -1:  # If no next route found, use end of file
                end_line = len(lines)
            break
            
    return start_line, end_line

# 2. Process DEBUG_CATEGORIES and debug_print
def find_debug_utilities(lines):
    debug_categories_start = -1
    debug_categories_end = -1
    debug_print_start = -1
    debug_print_end = -1
    
    for i, line in enumerate(lines):
        if line.strip().startswith('DEBUG_CATEGORIES = {'):
            debug_categories_start = i
            # Find the closing brace
            for j in range(i + 1, len(lines)):
                if lines[j].strip() == '}':
                    debug_categories_end = j
                    break
        
        if line.strip().startswith('def debug_print('):
            debug_print_start = i
            # Find the end of the function (next line that's not indented)
            for j in range(i + 1, len(lines)):
                if lines[j].strip() and not (lines[j].startswith(' ') or lines[j].startswith('\t')):
                    debug_print_end = j - 1
                    break
    
    return debug_categories_start, debug_categories_end, debug_print_start, debug_print_end

# Find and remove test_session route
test_session_start, test_session_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/test_session[\'"]')
if test_session_start !== -1 and test_session_end !== -1:
    changes["test_session_route"] = test_session_end - test_session_start
    print(f"Found test_session route: lines {test_session_start+1}-{test_session_end}")
    lines = lines[:test_session_start] + lines[test_session_end:]

# Find and remove test_date_extraction route
test_date_extraction_start, test_date_extraction_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/test_date_extraction[\'"]')
if test_date_extraction_start !== -1 and test_date_extraction_end !== -1:
    changes["test_date_extraction_route"] = test_date_extraction_end - test_date_extraction_start
    print(f"Found test_date_extraction route: lines {test_date_extraction_start+1}-{test_date_extraction_end}")
    lines = lines[:test_date_extraction_start] + lines[test_date_extraction_end:]

# Find and remove test_function_call route
test_function_call_start, test_function_call_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/test_function_call[\'"]')
if test_function_call_start !== -1 and test_function_call_end !== -1:
    changes["test_function_call_route"] = test_function_call_end - test_function_call_start
    print(f"Found test_function_call route: lines {test_function_call_start+1}-{test_function_call_end}")
    lines = lines[:test_function_call_start] + lines[test_function_call_end:]

# Find and remove debug_function_call route
debug_function_call_start, debug_function_call_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/debug_function_call[\'"]')
if debug_function_call_start !== -1 and debug_function_call_end !== -1:
    changes["debug_function_call_route"] = debug_function_call_end - debug_function_call_start
    print(f"Found debug_function_call route: lines {debug_function_call_start+1}-{debug_function_call_end}")
    lines = lines[:debug_function_call_start] + lines[debug_function_call_end:]

# Find and remove debug route
debug_route_start, debug_route_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/debug[\'"]')
if debug_route_start !== -1 and debug_route_end !== -1:
    changes["debug_route"] = debug_route_end - debug_route_start
    print(f"Found debug route: lines {debug_route_start+1}-{debug_route_end}")
    lines = lines[:debug_route_start] + lines[debug_route_end:]

# Find and remove update_chat_history route (redundant with update_stream_chat_history)
update_chat_history_start, update_chat_history_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/update_chat_history[\'"]')
if update_chat_history_start !== -1 and update_chat_history_end !== -1:
    changes["update_chat_history_route"] = update_chat_history_end - update_chat_history_start
    print(f"Found update_chat_history route: lines {update_chat_history_start+1}-{update_chat_history_end}")
    lines = lines[:update_chat_history_start] + lines[update_chat_history_end:]

# Find and remove check_seller_id route
check_seller_id_start, check_seller_id_end = find_route_boundaries(lines, r'^@app\.route\([\'"]\/check_seller_id[\'"]')
if check_seller_id_start !== -1 and check_seller_id_end !== -1:
    changes["check_seller_id_route"] = check_seller_id_end - check_seller_id_start
    print(f"Found check_seller_id route: lines {check_seller_id_start+1}-{check_seller_id_end}")
    lines = lines[:check_seller_id_start] + lines[check_seller_id_end:]

# Find and remove DEBUG_CATEGORIES and debug_print function
debug_categories_start, debug_categories_end, debug_print_start, debug_print_end = find_debug_utilities(lines)

if debug_categories_start !== -1 and debug_categories_end !== -1:
    changes["debug_categories"] = debug_categories_end - debug_categories_start + 1
    print(f"Found DEBUG_CATEGORIES: lines {debug_categories_start+1}-{debug_categories_end+1}")
    lines = lines[:debug_categories_start] + lines[debug_categories_end+1:]
    # Adjust indices for debug_print after removing debug_categories
    if debug_print_start > debug_categories_end:
        debug_print_start -= (debug_categories_end - debug_categories_start + 1)
        if debug_print_end !== -1:
            debug_print_end -= (debug_categories_end - debug_categories_start + 1)

if debug_print_start !== -1 and debug_print_end !== -1:
    changes["debug_print_func"] = debug_print_end - debug_print_start + 1
    print(f"Found debug_print function: lines {debug_print_start+1}-{debug_print_end+1}")
    lines = lines[:debug_print_start] + lines[debug_print_end+1:]

# Remove all debug_print calls
new_lines = []
for line in lines:
    if "debug_print(" in line:
        changes["debug_print_calls"] += 1
    else:
        new_lines.append(line)

print(f"Removed {changes['debug_print_calls']} debug_print calls")

# Fix duplicate imports
fixed_lines = []
seen_import_logging = False
for line in new_lines:
    if line.strip() == 'import logging':
        if seen_import_logging:
            changes["duplicate_imports"] += 1
            continue
        seen_import_logging = True
    fixed_lines.append(line)

if changes["duplicate_imports"] > 0:
    print(f"Removed {changes['duplicate_imports']} duplicate import statements")

# Change legacy approach to always be false
final_lines = []
for line in fixed_lines:
    if 'use_legacy_approach = True' in line:
        changes["legacy_approach"] += 1
        final_lines.append(line.replace('use_legacy_approach = True', 'use_legacy_approach = False'))
    else:
        final_lines.append(line)

if changes["legacy_approach"] > 0:
    print(f"Changed {changes['legacy_approach']} instances of legacy approach to False")

# Write the modified content to the output file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

# Count lines in the cleaned file
cleaned_line_count = len(final_lines)
reduction = original_line_count - cleaned_line_count
percent = (reduction / original_line_count) * 100

print(f"Cleanup complete!=")
print(f"Original file: {original_line_count} lines")
print(f"Cleaned file: {cleaned_line_count} lines")
print(f"Reduction: {reduction} lines ({percent:.2f}%)")

# Create summary markdown file
summary_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/cleanup_summary.md"
with open(summary_path, 'w', encoding='utf-8') as f:
    f.write(f"""# Code Cleanup Results

## Summary
- Original file size: {original_line_count} lines
- New file size: {cleaned_line_count} lines
- Reduction: {reduction} lines ({percent:.2f}%)

## Removed Components
1. Test routes:
   - /test_session route ({changes["test_session_route"]} lines)
   - /test_date_extraction route ({changes["test_date_extraction_route"]} lines)
   - /test_function_call route ({changes["test_function_call_route"]} lines)
   
2. Debug routes:
   - /debug_function_call route ({changes["debug_function_call_route"]} lines)
   - /debug route (debug page) ({changes["debug_route"]} lines)
   
3. Debug utilities:
   - DEBUG_CATEGORIES variable ({changes["debug_categories"]} lines)
   - debug_print function ({changes["debug_print_func"]} lines)
   - {changes["debug_print_calls"]} debug_print calls
   
4. Redundant code:
   - update_chat_history route ({changes["update_chat_history_route"]} lines)
   - check_seller_id route ({changes["check_seller_id_route"]} lines)
   - {changes["duplicate_imports"]} duplicate import statements
   
5. Simplified code:
   - Changed {changes["legacy_approach"]} instances of legacy approach to False

## Preserved Components
- /test_bigquery route (kept as requested)
- All core business logic functions
- Key application routes

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
