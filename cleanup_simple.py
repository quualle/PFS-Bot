#\!/usr/bin/env python3
import os
import re
import sys
from datetime import datetime

# Paths
app_py_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py"
output_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py.cleaned"

print(f"Reading file {app_py_path}...")
with open(app_py_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

original_lines = len(lines)
print(f"Original file has {original_lines} lines")

# Find and remove specific blocks of code
def remove_section_between_patterns(lines, start_pattern, end_pattern, name):
    """Remove lines between start_pattern and end_pattern"""
    new_lines = []
    skip = False
    removed_count = 0
    
    for line in lines:
        if not skip and re.search(start_pattern, line):
            skip = True
            removed_count += 1
            continue
            
        if skip and re.search(end_pattern, line):
            skip = False
            continue
            
        if skip:
            removed_count += 1
        else:
            new_lines.append(line)
    
    if removed_count > 0:
        print(f"Removed {removed_count} lines for {name}")
    else:
        print(f"No matches found for {name}")
        
    return new_lines, removed_count

# Function to remove lines that match a pattern
def remove_matching_lines(lines, pattern, name):
    """Remove lines that match the pattern"""
    new_lines = []
    removed_count = 0
    
    for line in lines:
        if re.search(pattern, line):
            removed_count += 1
        else:
            new_lines.append(line)
    
    if removed_count > 0:
        print(f"Removed {removed_count} lines matching {name}")
    else:
        print(f"No matches found for {name}")
        
    return new_lines, removed_count

# Replace specific patterns
def replace_pattern(lines, pattern, replacement, name):
    """Replace pattern with replacement"""
    new_lines = []
    replaced_count = 0
    
    for line in lines:
        if re.search(pattern, line):
            new_lines.append(re.sub(pattern, replacement, line))
            replaced_count += 1
        else:
            new_lines.append(line)
    
    if replaced_count > 0:
        print(f"Replaced {replaced_count} instances of {name}")
    else:
        print(f"No matches found for {name}")
        
    return new_lines, replaced_count

# Dictionary to track removals
removals = {}

# 1. Remove test_session route
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/test_session'\)",
    r"@app\.route",
    "test_session route"
)
lines = tmp_lines
removals["test_session_route"] = count

# 2. Remove test_date_extraction route 
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/test_date_extraction'\)",
    r"@app\.route",
    "test_date_extraction route"
)
lines = tmp_lines
removals["test_date_extraction_route"] = count

# 3. Remove test_function_call route
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/test_function_call'\)",
    r"@app\.route",
    "test_function_call route"
)
lines = tmp_lines
removals["test_function_call_route"] = count

# 4. Remove debug_function_call route
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/debug_function_call'\)",
    r"@app\.route",
    "debug_function_call route"
)
lines = tmp_lines
removals["debug_function_call_route"] = count

# 5. Remove /debug route
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/debug', methods=",
    r"@app\.route",
    "debug route"
)
lines = tmp_lines
removals["debug_route"] = count

# 6. Remove update_chat_history route (redundant with update_stream_chat_history)
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/update_chat_history', methods=",
    r"@app\.route",
    "update_chat_history route"
)
lines = tmp_lines
removals["update_chat_history_route"] = count

# 7. Remove check_seller_id route
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"@app\.route\('/check_seller_id'\)",
    r"@app\.route",
    "check_seller_id route"
)
lines = tmp_lines
removals["check_seller_id_route"] = count

# 8. Remove DEBUG_CATEGORIES
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"DEBUG_CATEGORIES = {",
    r"^}$",
    "DEBUG_CATEGORIES"
)
lines = tmp_lines
removals["debug_categories"] = count

# 9. Remove debug_print function
tmp_lines, count = remove_section_between_patterns(
    lines, 
    r"def debug_print\(category, message\):",
    r"^[^ \t]",
    "debug_print function"
)
lines = tmp_lines
removals["debug_print_function"] = count

# 10. Remove debug_print calls
tmp_lines, count = remove_matching_lines(
    lines,
    r"[ \t]*debug_print\(",
    "debug_print calls"
)
lines = tmp_lines
removals["debug_print_calls"] = count

# 11. Fix duplicate import logging
tmp_lines, count = replace_pattern(
    lines,
    r"import logging\nimport logging",
    "import logging",
    "duplicate logging import"
)
lines = tmp_lines
removals["duplicate_import"] = count

# 12. Change use_legacy_approach = True to False
tmp_lines, count = replace_pattern(
    lines,
    r"use_legacy_approach = True",
    "use_legacy_approach = False",
    "legacy_approach = True"
)
lines = tmp_lines
removals["legacy_approach"] = count

# Write the cleaned file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

# Verify file stats
cleaned_lines = len(lines)
reduction = original_lines - cleaned_lines
percent = (reduction / original_lines) * 100

print(f"Cleanup complete\!")
print(f"Original file: {original_lines} lines")
print(f"Cleaned file: {cleaned_lines} lines")
print(f"Reduction: {reduction} lines ({percent:.2f}%)")

# Create a summary in Markdown
summary_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/cleanup_summary.md"
with open(summary_path, 'w', encoding='utf-8') as f:
    f.write(f"""# Code Cleanup Results

## Summary
- Original file size: {original_lines} lines
- New file size: {cleaned_lines} lines
- Reduction: {reduction} lines ({percent:.2f}%)

## Removed Components
1. Test routes:
   - /test_session route ({removals["test_session_route"]} lines)
   - /test_date_extraction route ({removals["test_date_extraction_route"]} lines)
   - /test_function_call route ({removals["test_function_call_route"]} lines)
   
2. Debug routes:
   - /debug_function_call route ({removals["debug_function_call_route"]} lines)
   - /debug route (debug page) ({removals["debug_route"]} lines)
   
3. Debug utilities:
   - DEBUG_CATEGORIES variable ({removals["debug_categories"]} lines)
   - debug_print function ({removals["debug_print_function"]} lines)
   - {removals["debug_print_calls"]} debug_print calls
   
4. Redundant code:
   - update_chat_history route ({removals["update_chat_history_route"]} lines)
   - check_seller_id route ({removals["check_seller_id_route"]} lines)
   - {removals["duplicate_import"]} duplicate import statements replaced
   
5. Simplified code:
   - Changed {removals["legacy_approach"]} instances of legacy approach to False

## Preserved Components
- /test_bigquery route (kept as requested)
- All core business logic functions
- Key application routes

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
