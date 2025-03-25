#\!/usr/bin/env python3

# Paths
app_py_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py"
output_path = "/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/app.py.cleaned"

print(f"Reading file {app_py_path}...")
with open(app_py_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

original_line_count = len(lines)
print(f"Original file has {original_line_count} lines")

# Lines to remove by line number
# Format: (start_line, end_line, description)
# Remember that Python is 0-indexed but line numbers start at 1
sections_to_remove = [
    (3386-1, 3405-1, "test_session route"),
    (4346-1, 4379-1, "test_date_extraction route"),
    (4380-1, 4418-1, "test_function_call route"),
    (4435-1, 4465-1, "debug_function_call route"),
    (4821-1, 4829-1, "debug route"),
    (4225-1, 4262-1, "update_chat_history route"),
    (4471-1, 4505-1, "check_seller_id route"),
]

# Mark lines to keep
keep_lines = [True] * len(lines)
for start, end, desc in sections_to_remove:
    for i in range(start, end + 1):
        if i < len(keep_lines):
            keep_lines[i] = False
            
    print(f"Marked lines {start+1}-{end+1} for removal ({desc})")

# Keep only marked lines
cleaned_lines = [line for i, line in enumerate(lines) if keep_lines[i]]

# Replace use_legacy_approach = True with False
for i, line in enumerate(cleaned_lines):
    if 'use_legacy_approach = True' in line:
        cleaned_lines[i] = line.replace('use_legacy_approach = True', 'use_legacy_approach = False')
        print("Set use_legacy_approach to False")

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
   
4. Modified:
   - Set use_legacy_approach to False

## Preserved Components
- /test_bigquery route (kept as requested)
- DEBUG_CATEGORIES and debug_print function
- All core business logic functions
- Key application routes

## Future Cleanup Suggestions
For additional cleanup (with more careful examination):
1. Remove DEBUG_CATEGORIES variable
2. Remove debug_print function
3. Remove debug_print calls
4. Fix duplicate imports

## Backup Location
Full backups are available at:
/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_{datetime.now().strftime('%Y%m%d')}/
""")

print(f"Summary written to {summary_path}")
