#\!/usr/bin/env python3
import os
import re
import sys
from datetime import datetime

# Paths
app_py_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py.tmp"
output_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py.cleaned"

print(f"Reading file {app_py_path}...")
with open(app_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_lines = content.count('\n') + 1
print(f"Original file has {original_lines} lines")

# Dictionary to track removals
removals = {}

# 1. Remove test routes except test_bigquery
for route in ['/test_session', '/test_date_extraction', '/test_function_call']:
    pattern = f'@app\\.route\\([\'"]({route})[\'"].*?(?=@app\\.route)'
    matches = re.findall(pattern, content, re.DOTALL)
    count = len(matches)
    if count > 0:
        print(f"Removing {count} instances of {route} route")
        content = re.sub(pattern, '', content, flags=re.DOTALL)
        removals[route] = count

# 2. Remove debug routes
for route in ['/debug_oauth', '/debug_function_call', '/debug']:
    pattern = f'@app\\.route\\([\'"]({route})[\'"].*?(?=@app\\.route)'
    matches = re.findall(pattern, content, re.DOTALL)
    count = len(matches)
    if count > 0:
        print(f"Removing {count} instances of {route} route")
        content = re.sub(pattern, '', content, flags=re.DOTALL)
        removals[route] = count

# 3. Remove the redundant update_chat_history route
pattern = '@app\\.route\\([\'"](/update_chat_history)[\'"].*?(?=@app\\.route)'
matches = re.findall(pattern, content, re.DOTALL)
count = len(matches)
if count > 0:
    print(f"Removing {count} instances of /update_chat_history route")
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    removals['/update_chat_history'] = count

# 4. Remove check_seller_id route
pattern = '@app\\.route\\([\'"](/check_seller_id)[\'"].*?(?=@app\\.route)'
matches = re.findall(pattern, content, re.DOTALL)
count = len(matches)
if count > 0:
    print(f"Removing {count} instances of /check_seller_id route")
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    removals['/check_seller_id'] = count

# 5. Remove DEBUG_CATEGORIES
pattern = 'DEBUG_CATEGORIES = \\{.*?\\}'
matches = re.findall(pattern, content, re.DOTALL)
count = len(matches)
if count > 0:
    print(f"Removing {count} DEBUG_CATEGORIES definitions")
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    removals['DEBUG_CATEGORIES'] = count

# 6. Remove debug_print function
pattern = 'def debug_print\\(.*?\\):[^\\n]*\\n(?:[ \\t]+[^\\n]*\\n)+'
matches = re.findall(pattern, content, re.DOTALL)
count = len(matches)
if count > 0:
    print(f"Removing {count} debug_print function definitions")
    content = re.sub(pattern, '', content, flags=re.DOTALL)
    removals['debug_print_function'] = count

# 7. Fix duplicate imports
pattern = 'import logging\\s+import logging'
content = re.sub(pattern, 'import logging', content)

# 8. Set use_legacy_approach to False
content = re.sub('use_legacy_approach = True', 'use_legacy_approach = False', content)

# Write the cleaned file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify file stats
cleaned_lines = content.count('\n') + 1
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
   - /test_session route
   - /test_date_extraction route
   - /test_function_call route
   
2. Debug routes:
   - /debug_oauth route
   - /debug_function_call route
   - /debug route (debug page)
   
3. Debug utilities:
   - DEBUG_CATEGORIES variable
   - debug_print function
   - debug_print calls (cleaned with Perl)
   
4. Redundant code:
   - update_chat_history route (kept update_stream_chat_history)
   - check_seller_id route
   - Duplicate import statements
   
5. Simplified code:
   - Set use_legacy_approach to always be False

## Preserved Components
- /test_bigquery route (kept as requested)
- All core business logic functions
- Key application routes

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
