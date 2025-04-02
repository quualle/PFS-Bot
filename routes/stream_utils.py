"""
Stream-Utility-Funktionen für die XORA-Anwendung.
Diese Datei enthält Funktionen zum Streaming von Antworten an den Client.
"""
import json
import time
import logging
import openai
from routes.utils import debug_print
from routes.openai_utils import contact_openai

def stream_text_response(response_text, user_message, session_data):
    """
    Generiert einen Stream für direkte Textantworten (z.B. Wissensbasis-Antworten)
    """
    try:
        # Debug-Events für die Verbindungsdiagnose
        yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream-Start (Text Response)'})}\n\n"
        
        # Stream-Start
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        # Teile die Antwort in Chunks auf für ein natürlicheres Streaming-Gefühl
        chunk_size = 15  # Anzahl der Wörter pro Chunk
        words = response_text.split()
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            yield f"data: {json.dumps({'type': 'text', 'content': chunk + ' '})}\n\n"
            time.sleep(0.05)  # Kleine Verzögerung für natürlichere Ausgabe
        
        # Stream beenden
        yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': response_text})}\n\n"
        yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream complete with function execution'})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        logging.exception("Fehler im Text-Stream")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': 'Es ist ein Fehler aufgetreten.'})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

def stream_response(messages, tools, tool_choice, seller_id, extracted_args, user_message, session_data, handle_function_call=None):
    """Stream the OpenAI response and handle function calls within the stream
    
    Args:
        messages: OpenAI message array
        tools: Available tools/functions
        tool_choice: Which tool to use
        seller_id: The seller's ID
        extracted_args: Any extracted date parameters
        user_message: The original user message
        session_data: A dictionary containing all needed session data
        handle_function_call: Callback-Funktion zur Verarbeitung von Funktionsaufrufen
    """
    # Behandlung von None für extracted_args
    if extracted_args is None:
        extracted_args = {}
        
    # Extract session data - this avoids accessing session in the generator
    user_id = session_data.get("user_id", "")
    user_name = session_data.get("user_name", "")
    chat_key = session_data.get("chat_key", "")
    chat_history = session_data.get("chat_history", [])
    
    try:
        # Debug-Events für die Verbindungsdiagnose
        yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream-Start'})}\n\n"
        #yield f"data: {json.dumps({'type': 'text', 'content': 'Test-Content vom Server'})}\n\n"

        debug_print("API Calls", f"Streaming-Anfrage an OpenAI mit Function Calling")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            stream=True  # Enable streaming
        )
        
        initial_response = ""
        function_calls_data = []
        has_function_calls = False
        
        # Stream the initial response
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        for chunk in response:
            if chunk.choices[0].delta.content:
                text_chunk = chunk.choices[0].delta.content
                initial_response += text_chunk
                yield f"data: {json.dumps({'type': 'text', 'content': text_chunk})}\n\n"
            
            # Check if this chunk contains function call info
            if hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                has_function_calls = True
                # Collect function call data
                for tool_call in chunk.choices[0].delta.tool_calls:
                    tool_index = tool_call.index
                    
                    # Initialize the tool call if needed
                    while len(function_calls_data) <= tool_index:
                        function_calls_data.append({"id": str(tool_index), "name": "", "args": ""})
                    
                    if hasattr(tool_call, 'function'):
                        if hasattr(tool_call.function, 'name') and tool_call.function.name:
                            function_calls_data[tool_index]["name"] = tool_call.function.name
                        
                        if hasattr(tool_call.function, 'arguments') and tool_call.function.arguments:
                            function_calls_data[tool_index]["args"] += tool_call.function.arguments
        
        # If function calls detected, execute them
        if has_function_calls and handle_function_call is not None:
            yield f"data: {json.dumps({'type': 'function_call_start'})}\n\n"
            yield f"data: {json.dumps({'type': 'debug', 'message': f'Detected {len(function_calls_data)} function calls'})}\n\n"
            
            function_responses = []
            for func_data in function_calls_data:
                if func_data["name"] and func_data["args"]:
                    try:
                        function_name = func_data["name"]
                        function_args = json.loads(func_data["args"])
                        
                        # Add seller_id and extracted date parameters
                        if seller_id:
                            function_args["seller_id"] = seller_id
                        
                        for key, value in extracted_args.items():
                            if key not in function_args or not function_args[key]:
                                function_args[key] = value
                        
                        # Execute the function
                        debug_print("Function", f"Streaming: Executing {function_name} with args {function_args}")
                        yield f"data: {json.dumps({'type': 'debug', 'message': f'Executing function {function_name}'})}\n\n"
                        
                        function_response = handle_function_call(function_name, function_args)
                        
                        # Add to function responses
                        function_responses.append({
                            "role": "tool",
                            "tool_call_id": func_data["id"],
                            "content": function_response
                        })
                        
                        yield f"data: {json.dumps({'type': 'function_result', 'name': function_name})}\n\n"
                        yield f"data: {json.dumps({'type': 'debug', 'message': f'Function executed successfully'})}\n\n"
                        
                    except Exception as e:
                        debug_print("Function", f"Error executing function: {str(e)}")
                        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler bei Funktionsausführung: {str(e)}'})}\n\n"
            
            # Second call to get final response
            if function_responses:
                # Properly format the tool_calls with the required 'type' field
                formatted_tool_calls = []
                for func_data in function_calls_data:
                    formatted_tool_calls.append({
                        "type": "function",  # This is the required field
                        "id": func_data["id"],
                        "function": {
                            "name": func_data["name"],
                            "arguments": func_data["args"]
                        }
                    })
                
                # Create the second messages with properly formatted tool_calls
                second_messages = messages + [{
                    "role": "assistant", 
                    "content": initial_response,
                    "tool_calls": formatted_tool_calls
                }] + function_responses

                # Debug vor dem zweiten API-Call
                yield f"data: {json.dumps({'type': 'debug', 'message': 'Preparing for second API call'})}\n\n"
                
                # WICHTIG: Final response start event - stelle sicher, dass es gesendet wird
                yield f"data: {json.dumps({'type': 'final_response_start'})}\n\n"
                
                # Initiiere den zweiten API-Call
                yield f"data: {json.dumps({'type': 'debug', 'message': 'Starting second API call'})}\n\n"
                
                try:
                    final_response = openai.chat.completions.create(
                        model="gpt-4o",
                        messages=second_messages,
                        stream=True
                    )
                    
                    yield f"data: {json.dumps({'type': 'debug', 'message': 'Second API call initiated'})}\n\n"
                    
                    final_text = ""
                    for chunk in final_response:
                        if chunk.choices[0].delta.content:
                            text_chunk = chunk.choices[0].delta.content
                            final_text += text_chunk
                            yield f"data: {json.dumps({'type': 'text', 'content': text_chunk})}\n\n"
                    
                    # Vollständige Antwort zusammenstellen
                    full_response = initial_response + "\n\n" + final_text
                    
                    # Session aktualisieren und Stream beenden
                    yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': full_response})}\n\n"
                    yield f"data: {json.dumps({'type': 'debug', 'message': 'Stream complete with function execution'})}\n\n"
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
                    
                except Exception as e:
                    debug_print("API Calls", f"Error in second call: {str(e)}")
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler beim zweiten API-Call: {str(e)}'})}\n\n"
                    # Trotz Fehler die Session aktualisieren
                    yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': initial_response})}\n\n"
                    yield f"data: {json.dumps({'type': 'end'})}\n\n"
            else:
                # No valid function responses, just save initial response
                yield f"data: {json.dumps({'type': 'debug', 'message': 'Function execution produced no valid responses'})}\n\n"
                yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': initial_response})}\n\n"
                yield f"data: {json.dumps({'type': 'end'})}\n\n"
        else:
            # No function calls, just save initial response
            yield f"data: {json.dumps({'type': 'debug', 'message': 'No function calls detected'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': initial_response})}\n\n"
            yield f"data: {json.dumps({'type': 'end'})}\n\n"
    
    except Exception as e:
        logging.exception("Fehler im Stream")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler: {str(e)}'})}\n\n"
        # Auch bei Fehler versuchen, Stream ordnungsgemäß zu beenden
        yield f"data: {json.dumps({'type': 'complete', 'user': user_message, 'bot': 'Es ist ein Fehler aufgetreten.'})}\n\n"

def generate_clarification_stream(human_in_loop_data):
    """
    Generiert einen Stream für text-basierte Rückfragen (ohne Buttons)
    """
    try:
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        # Generiere Rückfrage
        clarification_text = human_in_loop_data.get('question', 'Ich benötige weitere Informationen')
        chunk_size = 15  # Anzahl der Wörter pro Chunk
        words = clarification_text.split()
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            yield f"data: {json.dumps({'type': 'text', 'content': chunk + ' '})}\n\n"
            time.sleep(0.1)  # Kleine Verzögerung für natürlichere Ausgabe
        
        # "human_in_loop" Event sendet die Metadaten
        human_in_loop_data_json = json.dumps({
            'type': 'human_in_loop',
            'mode': 'clarification',
            'data': human_in_loop_data
        })
        yield f"data: {human_in_loop_data_json}\n\n"
        
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        logging.exception("Fehler beim Generieren der Rückfrage")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"

def generate_conversational_clarification_stream(clarification_data):
    """
    Generiert einen Stream für konversationelle Rückfragen ohne Buttons
    """
    try:
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        
        # Generiere Rückfrage
        clarification_text = clarification_data.get('message', 'Ich benötige weitere Informationen')
        chunk_size = 15  # Anzahl der Wörter pro Chunk
        words = clarification_text.split()
        
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            yield f"data: {json.dumps({'type': 'text', 'content': chunk + ' '})}\n\n"
            time.sleep(0.1)  # Kleine Verzögerung für natürlichere Ausgabe
        
        # "human_in_loop" Event sendet die Metadaten
        yield f"data: {json.dumps({
            'type': 'conversational_clarification',
            'data': clarification_data
        })}\n\n"
        
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
    except Exception as e:
        logging.exception("Fehler beim Generieren der konversationellen Rückfrage")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Fehler: {str(e)}'})}\n\n"
        yield f"data: {json.dumps({'type': 'end'})}\n\n"
