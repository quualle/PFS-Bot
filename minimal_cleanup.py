#\!/usr/bin/env python3
import re

# Paths
app_py_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py"
output_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py.cleaned"

print(f"Reading file {app_py_path}...")
with open(app_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

original_line_count = content.count('\n') + 1
print(f"Original file has {original_line_count} lines")

# Define function to remove a route by pattern
def remove_route(content, route_name, route_pattern):
    # Use regex to safely remove the route
    match = re.search(route_pattern, content)
    if match:
        start, end = match.span()
        print(f"Found {route_name} at position {start}-{end}")
        # Remove the matched text
        content = content[:start] + content[end:]
        return content, True
    else:
        print(f"Could not find {route_name}")
        return content, False

# Routes to remove
routes = [
    ("test_session", r'@app\.route\([\'"]\/test_session[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
    ("test_date_extraction", r'@app\.route\([\'"]\/test_date_extraction[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
    ("test_function_call", r'@app\.route\([\'"]\/test_function_call[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
    ("debug_function_call", r'@app\.route\([\'"]\/debug_function_call[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
    ("debug", r'@app\.route\([\'"]\/debug[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
    ("update_chat_history", r'@app\.route\([\'"]\/update_chat_history[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
    ("check_seller_id", r'@app\.route\([\'"]\/check_seller_id[\'"]\)[^\n]*\n(?:(?\!@app\.route)[^\n]*\n)*'),
]

# Track removals
removals = {}

# Remove each route
for route_name, route_pattern in routes:
    content, removed = remove_route(content, route_name, route_pattern)
    if removed:
        removals[route_name] = True

# Replace use_legacy_approach = True with False
legacy_count = content.count('use_legacy_approach = True')
content = content.replace('use_legacy_approach = True', 'use_legacy_approach = False')
print(f"Replaced {legacy_count} occurrences of use_legacy_approach = True")

# Remove duplicate import logging
import_count = content.count('import logging')
if import_count > 1:
    content = content.replace('import logging\nimport logging', 'import logging')
    print(f"Fixed duplicate import logging statements")

# Write out the cleaned file
print(f"Writing cleaned file to {output_path}...")
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Count lines in the cleaned file
cleaned_line_count = content.count('\n') + 1
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
   - /test_session route: {"Removed" if "test_session" in removals else "Not found"}
   - /test_date_extraction route: {"Removed" if "test_date_extraction" in removals else "Not found"}
   - /test_function_call route: {"Removed" if "test_function_call" in removals else "Not found"}
   
2. Debug routes:
   - /debug_function_call route: {"Removed" if "debug_function_call" in removals else "Not found"}
   - /debug route (debug page): {"Removed" if "debug" in removals else "Not found"}
   
3. Redundant code:
   - update_chat_history route: {"Removed" if "update_chat_history" in removals else "Not found"}
   - check_seller_id route: {"Removed" if "check_seller_id" in removals else "Not found"}
   - Fixed duplicate import of logging statements
   
4. Modified:
   - Changed {legacy_count} occurrences of use_legacy_approach = True to False

## Preserved Components
- /test_bigquery route (kept as requested)
- DEBUG_CATEGORIES and debug_print function
- All core business logic functions
- Key application routes

## Future Cleanup Suggestions
For additional cleanup (with more careful examination):
1. Remove DEBUG_CATEGORIES variable
2. Remove debug_print function
3. Remove debug_print calls (carefully, ensuring no syntax issues)

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
