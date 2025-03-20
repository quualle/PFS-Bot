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

original_line_count = len(lines)
print(f"Original file has {original_line_count} lines")

# Remove specific routes by line numbers
to_remove = {
    # Test routes (except test_bigquery)
    "test_session": (3386, 3405),
    "test_date_extraction": (4346, 4379),
    "test_function_call": (4380, 4418),
    
    # Debug routes
    "debug_function_call": (4435, 4465),
    "debug_route": (4821, 4829),
    
    # Redundant routes
    "update_chat_history": (4225, 4262),
    "check_seller_id": (4471, 4505),
    
    # Debug utilities (comment out these lines if you want to keep them)
    # "debug_categories": (293, 300),
    # "debug_print": (302, 304)
}

# Create a set of lines to skip
skip_lines = set()
for section, (start, end) in to_remove.items():
    for i in range(start - 1, end):  # -1 because Python is 0-indexed but line numbers start at 1
        skip_lines.add(i)
    print(f"Marked {section} route (lines {start}-{end}) for removal")

# Filter the lines
cleaned_lines = [line for i, line in enumerate(lines) if i not in skip_lines]

# Replace use_legacy_approach = True with False
for i, line in enumerate(cleaned_lines):
    if 'use_legacy_approach = True' in line:
        cleaned_lines[i] = line.replace('use_legacy_approach = True', 'use_legacy_approach = False')
        print("Set use_legacy_approach to False")

# Remove duplicate import logging
seen_import_logging = False
for i, line in enumerate(cleaned_lines):
    if line.strip() == 'import logging':
        if seen_import_logging:
            cleaned_lines[i] = ''  # Remove duplicate
            print("Removed duplicate 'import logging'")
        seen_import_logging = True

# Write out the cleaned file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.writelines(cleaned_lines)

# Count lines in the cleaned file
cleaned_line_count = len(cleaned_lines)
reduction = original_line_count - cleaned_line_count
percent = (reduction / original_line_count) * 100

print(f"Cleanup complete\!")
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
   - /test_session route (lines 3386-3405)
   - /test_date_extraction route (lines 4346-4379)
   - /test_function_call route (lines 4380-4418)
   
2. Debug routes:
   - /debug_function_call route (lines 4435-4465)
   - /debug route (debug page) (lines 4821-4829)
   
3. Redundant code:
   - update_chat_history route (lines 4225-4262)
   - check_seller_id route (lines 4471-4505)
   - Duplicate import of logging
   
4. Modified:
   - Set use_legacy_approach to False

## Preserved Components
- /test_bigquery route (kept as requested)
- DEBUG_CATEGORIES and debug_print function (kept to maintain code structure)
- All core business logic functions
- Key application routes

## Next Cleanup Steps
For further cleanup (if needed):
1. Remove DEBUG_CATEGORIES variable
2. Remove debug_print function
3. Remove debug_print calls (carefully, ensuring no syntax issues)

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
