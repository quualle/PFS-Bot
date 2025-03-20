# Manual Cleanup Guide for app.py

We've attempted several automated approaches to clean up app.py, but encountered syntax issues. Here's a guide for manual cleanup that will be safer:

## 1. Test Routes to Remove
Remove these routes that are only used for testing:
- `/test_session` (around lines 3386-3405)
- `/test_date_extraction` (around lines 4346-4379)
- `/test_function_call` (around lines 4380-4418)

## 2. Debug Routes to Remove
Remove these debug-only routes:
- `/debug_function_call` (around lines 4435-4465)
- `/debug` route (around lines 4821-4829)

## 3. Redundant Code to Remove
- `update_chat_history` route (around lines 4225-4262) - duplicated by update_stream_chat_history
- `check_seller_id` route (around lines 4471-4505) - debugging utility

## 4. Code to Modify
- Change `use_legacy_approach = True` to `use_legacy_approach = False`
- Fix duplicate `import logging` statements

## 5. Optional Further Cleanups (After Testing)
- Remove DEBUG_CATEGORIES variable (around lines 293-300)
- Remove debug_print function (around line 302-304)
- Carefully remove debug_print calls throughout the code

## Safety Guidelines
1. Make each change in isolation and test after each major removal
2. Keep the `/test_bigquery` route as requested
3. Be careful not to disrupt indentation when removing code blocks
4. Check for syntax errors after each change

## Using the Backup
If anything goes wrong, you can restore from the backup at:
`/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot/backups_20250319/app.py.bak`

The most important routes and functions to preserve are:
- `/chat` route
- `handle_function_call` function
- `create_enhanced_system_prompt` function 
- `create_system_prompt` function
- `get_accurate_time` function
- `update_stream_chat_history` function
