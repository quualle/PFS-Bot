# Code Blocks That Can Be Removed From app.py

## Test Routes
These routes are only used for testing and debugging, not for the main application:

1. **Test Session Route** (`/test_session`)
   - Purpose: Tests session functionality
   - Line numbers: Approximately 3386-3405
   - Can be safely removed as it's only for testing session storage

2. **Test BigQuery Route** (`/test_bigquery`)
   - Purpose: Tests BigQuery connection and queries
   - Line numbers: Approximately 3408-3435
   - Can be safely removed as it's only for testing database connections

3. **Test Date Extraction Route** (`/test_date_extraction`)
   - Purpose: Tests the date extraction functionality directly
   - Line numbers: Approximately 4346-4379
   - Only used during development to verify date extraction works

4. **Test Function Call Route** (`/test_function_call`)
   - Purpose: Tests direct function calling
   - Line numbers: Approximately 4380-4418
   - Can be removed as it's only a development tool

## Debug Routes
These routes are only used for debugging:

5. **Debug OAuth Route** (`/debug_oauth`)
   - Purpose: Diagnostics for OAuth configuration
   - Line numbers: Around 193-213
   - Only needed during development/debugging

6. **Debug Function Call Route** (`/debug_function_call`)
   - Purpose: Similar to test_function_call but for debugging
   - Line numbers: Approximately 4435-4465
   - Redundant with test_function_call and only for debugging

7. **Debug Page Route** (`/debug`)
   - Purpose: Manages debug categories
   - Line numbers: Approximately 4821-4829
   - Only useful during development

## Debug Utilities
These utilities are used only for debugging:

8. **DEBUG_CATEGORIES Variable**
   - Purpose: Controls which debug messages are printed
   - Line numbers: Approximately 293-300
   - Only used during development

9. **debug_print Function**
   - Purpose: Prints debug messages based on categories
   - Line numbers: Approximately 302-304
   - Only used during development

## Redundant Code

10. **Duplicate Imports**
    - Redundant import: `import logging` appears twice
    - Line numbers: 5-6
    - One can be removed

11. **Commented Code Blocks**
    - There may be various commented code blocks throughout the file
    - These can be removed after confirming they're not needed documentation

## Update_stream_chat_history and Update_chat_history
These appear to be redundant:

12. **Redundant update_chat_history Route**
    - Line numbers: Approximately 4225-4262
    - Appears to be duplicated by update_stream_chat_history at lines 4294-4331

## Other Potential Removals

13. **get_session_info Route**
    - Purpose: Displays all session information 
    - Line numbers: Approximately 4466-4488
    - May only be needed for debugging

14. **Any references to DEBUG_CATEGORIES and debug_print**
    - These are scattered throughout the file and can be removed along with their parent functions
    
IMPORTANT: This is a preliminary list. Carefully review each item before removal and make sure there are no dependencies or references to these functions elsewhere in the application.

## Legacy Approach Code
There are references to a `use_legacy_approach` variable that suggests there might be legacy code paths that could be removed:

15. **Legacy Code Paths**
    - Line numbers: Around 3154-3165
    - Related to legacy streaming approach which may be obsolete
    
16. **Legacy Variable and Conditions**
    - Purpose: Toggles between legacy and current approaches
    - Line numbers: 3154, 3157, 3162, 3245
    - If the legacy approach is no longer needed, these can be simplified

## Impact Summary
Removing these code elements would significantly reduce the size of app.py:

- Current size:     5235 lines
- Estimated reduction: 300-500 lines (approximately 10-15% of the file)
- Improved readability and maintainability
- Reduced cognitive load when working with the codebase
- Faster loading and parsing of the file

## Implementation Strategy
For a safe cleanup process, I recommend the following approach:

1. Start with the most obvious test/debug routes that have no dependencies
2. Then remove the debug utilities after removing all their references
3. Be cautious with removing duplicated functions - make sure one implementation fully replaces the other
4. Save the legacy code cleanup for last, as it might be more integrated with the main codebase

For each removal:
1. Comment out the code first
2. Run tests to ensure nothing breaks
3. If all is well, permanently remove the code
4. Commit changes incrementally to make reverting easier if needed
