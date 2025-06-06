# app/main.py
from fastapi import FastAPI, Query, WebSocket
from typing import AsyncIterable, Dict, Any
from app.api.v1.routers import api_router
from app.core.config import settings
import logging
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.agents.agents import general_agent, root_weather_agent
import os, json, base64, asyncio
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events.event import Event
from google.genai import types
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from typing import AsyncIterable


# Configure basic logging for the FastAPI app
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("fastapi_app")


APP_NAME = "Serena Agent"
session_service = InMemorySessionService()


# 1. Make this function async
async def start_agent_session(session_id: str, is_audio: bool = True): # Added type hint for session_id, changed is_audio type
    """Starts an agent session"""

    # Create a Session
    # 2. Await the call to create_session
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id,
    )

    # Create a Runner
    runner = Runner(
        app_name=APP_NAME,
        agent=general_agent,
        session_service=session_service,
    )

    # Set response modality
    modality = "AUDIO" if is_audio else "TEXT"

    # Create speech config with voice settings
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            # Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, and Zephyr
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
        )
    )

    # Create run config with basic settings
    config = {"response_modalities": [modality], "speech_config": speech_config}

    # Add output_audio_transcription when audio is enabled to get both audio and text
    if is_audio:
        config["output_audio_transcription"] = {}
        config["input_audio_transcription"] = {}

    run_config = RunConfig(**config)

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()

    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue


#<<<<<<<<<<<<<<<<<<<<<<<<<<<<< ASHISH working version new >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
async def agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None]
):
    """Agent to client communication. Processes events from ADK and sends to WebSocket client."""
    logger.info(f"Task agent_to_client_messaging started for websocket: {websocket.client}")
    try:
        async for event in live_events:
            if event is None:
                continue

            # --- Optional: Enable for very detailed raw ADK event logging ---
            # logger.debug(f"[ADK_RAW_EVENT]: {event}") 

            # 1. Handle Turn Completion or Interruption
            if event.turn_complete or event.interrupted:
                message: Dict[str, Any] = { 
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                logger.info(f"[AGENT_TO_CLIENT_SEND - TURN_STATUS]: {message}")
                await websocket.send_text(json.dumps(message))
                continue # Move to next event

            # 2. Handle Function Calls
            calls = event.get_function_calls()
            if calls:
                for call in calls:
                    tool_name = call.name
                    arguments = call.args
                    message: Dict[str, Any] = {
                        "mime_type": "text/plain", 
                        "data": f"Tool Call: {tool_name}, Args: {arguments}",
                        "role": "system", 
                    }
                    logger.info(f"[AGENT_TO_CLIENT_SEND - TOOL_CALL]: {message}")
                    await websocket.send_text(json.dumps(message))
                # If a function call event is also a final response or has other content,
                # it will be processed further. If not, we might want to `continue` here
                # depending on ADK event structure for tool calls. For now, let it pass through.
            
            # 3. Handle Content Parts (Text from User/Model, Audio from Model)
            if event.content and event.content.parts:
                event_content_role = event.content.role 
                # logger.debug(f"[ADK_EVENT_CONTENT_OBJECT] Role: '{event_content_role}', Partial: {event.partial}, #Parts: {len(event.content.parts)}")
                
                for i, part in enumerate(event.content.parts):
                    # Log details of each part for debugging
                    logger.info(f"[ADK_EVENT_PART_{i}] EventContentRole: '{event_content_role}', PartType: {type(part)}, PartDetails: {part}")

                    if not isinstance(part, types.Part):
                        logger.warning(f"Part {i} is not an instance of types.Part. Skipping.")
                        continue

                    text_message_to_send: Dict[str, Any] | None = None
                    audio_message_to_send: Dict[str, Any] | None = None

                    # A. Check for Text in the part
                    if part.text:
                        if event_content_role == "user": # Transcription of user's speech
                            text_message_to_send = {
                                "mime_type": "text/plain",
                                "data": part.text,
                                "role": "user_transcription",
                            }
                        # --- MODIFIED: Handle model text even if EventContentRole is None ---
                        elif event_content_role == "model" or event_content_role is None:
                            # If it has text and isn't user_transcription, assume it's model's response.
                            # This catches intermediate text chunks with EventContentRole: 'None'.
                            text_message_to_send = {
                                "mime_type": "text/plain",
                                "data": part.text,
                                "role": "model", # Send with role 'model' for client handling
                            }
                        # --- END OF MODIFICATION ---
                    
                    # B. Check for Inline Audio Data (expected for model's audio output)
                    if part.inline_data and \
                       part.inline_data.mime_type and \
                       part.inline_data.mime_type.startswith("audio/pcm"):
                        
                        # Assume PCM audio from this stream is model's output
                        audio_data_bytes = part.inline_data.data
                        if audio_data_bytes:
                            audio_message_to_send = {
                                "mime_type": "audio/pcm",
                                "data": base64.b64encode(audio_data_bytes).decode("ascii"),
                                "role": "model", 
                            }
                            logger.info(f"Prepared audio message (role: model) from part {i} with EventContentRole: '{event_content_role}'")
                        else:
                            logger.warning(f"Part {i} (assumed model audio) has empty audio data. EventContentRole: '{event_content_role}'")


                    # C. Send any messages derived from this part
                    if text_message_to_send:
                        logger.info(f"[AGENT_TO_CLIENT_SEND - TEXT_PART]: Role '{text_message_to_send['role']}', Data: '{text_message_to_send['data'][:50]}...'")
                        await websocket.send_text(json.dumps(text_message_to_send))
                    
                    if audio_message_to_send:
                        logger.info(f"[AGENT_TO_CLIENT_SEND - AUDIO_PART]: Role '{audio_message_to_send['role']}', Mime: '{audio_message_to_send['mime_type']}'") 
                        await websocket.send_text(json.dumps(audio_message_to_send))
            # else:
            #     logger.debug(f"Event received with no content or parts to process for messaging. Author: {getattr(event, 'author', 'N/A')}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected in agent_to_client_messaging: {websocket.client}")
    except asyncio.CancelledError:
        logger.info(f"Task agent_to_client_messaging cancelled for websocket: {websocket.client}")
    except Exception as e:
        logger.error(f"Critical error in agent_to_client_messaging for {websocket.client}: {e}", exc_info=True)
        try:
            # Attempt to send an error message to the client
            await websocket.send_text(json.dumps({"error": str(e), "role": "system"}))
        except Exception as send_err:
            logger.error(f"Failed to send error to client {websocket.client}: {send_err}")
    finally:
        logger.info(f"Task agent_to_client_messaging finished for websocket: {websocket.client}")

async def client_to_agent_messaging(
    websocket: WebSocket, live_request_queue: LiveRequestQueue
):
    """Client to agent communication"""
    while True:
        try: # Added try-except to handle potential disconnects gracefully
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            mime_type = message["mime_type"]
            data = message["data"]
            role = message.get("role", "user")

            if mime_type == "text/plain":
                content = types.Content(role=role, parts=[types.Part.from_text(text=data)])
                live_request_queue.send_content(content=content)
            elif mime_type == "audio/pcm":
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(
                    types.Blob(data=decoded_data, mime_type=mime_type)
                )
            else:
                logger.error(f"Mime type not supported: {mime_type}")
                # Optionally send error back to client
                await websocket.send_text(json.dumps({"error": f"Mime type not supported: {mime_type}", "role": "system"}))

        except asyncio.CancelledError:
            logger.info("client_to_agent_messaging task cancelled.")
            break
        except WebSocketDisconnect: # Specific exception for WebSocket disconnects
            logger.info("Client disconnected from client_to_agent_messaging.")
            break
        except Exception as e:
            logger.error(f"Error in client_to_agent_messaging: {e}")
            # Optionally, try to send an error message to the client
            try:
                await websocket.send_text(json.dumps({"error": str(e), "role": "system"}))
            except: # If sending fails, the connection is likely already gone
                pass
            break # Exit loop on error


def create_app() -> FastAPI:
    app = FastAPI(
        title="Project Serena",
        description="Serena agent powered by Gemini",
        version="0.1.0",
    )

    app.include_router(api_router, prefix="/v1")

    @app.on_event("startup")
    async def startup_event():
        logger.info("FastAPI application starting up...")
        try:
            from app.core.dependencies import get_bigquery_reader

            get_bigquery_reader()
            logger.info("BigQuery client initialized successfully on startup.")
        except Exception as e:
            logger.error(f"Failed to initialize BigQuery client on startup: {e}")

    @app.on_event("shutdown")
    async def shutdown_event():
        logger.info("FastAPI application shutting down...")

    return app


app = create_app()
STATIC_DIR = Path("app/static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serves the index.html"""
    print("index path:> ",os.path.join(STATIC_DIR, "index.html"))
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...), # is_audio comes as a string "true" or "false"
):
    """Client websocket endpoint"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{session_id} connected, audio mode: {is_audio}")

    # 4. Convert is_audio string to boolean
    is_audio_bool = is_audio.lower() == "true"

    try:
        # Start agent session
        # 3. Await the call to start_agent_session and pass the correct is_audio
        live_events, live_request_queue = await start_agent_session(
            session_id,
            is_audio=is_audio_bool # Pass the boolean value
        )
        print("Agent session started!!")
        # Start tasks
        agent_to_client_task = asyncio.create_task(
            agent_to_client_messaging(websocket, live_events)
        )
        client_to_agent_task = asyncio.create_task(
            client_to_agent_messaging(websocket, live_request_queue)
        )
        # Wait for either task to complete (e.g., due to error or disconnect)
        done, pending = await asyncio.wait(
            [agent_to_client_task, client_to_agent_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel any pending tasks to ensure they clean up
        for task in pending:
            task.cancel()

        # Await the cancelled tasks to allow them to finish their cancellation logic
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        # Check if any of the completed tasks raised an exception
        for task in done:
            if task.exception():
                logger.error(f"Task {task.get_name()} raised an exception: {task.exception()}")


    except Exception as e:
        logger.error(f"Error in websocket_endpoint for client #{session_id}: {e}")
        # Attempt to close the websocket gracefully if an error occurs before tasks are set up
        # or if start_agent_session fails.
        try:
            await websocket.close(code=1011) # Internal error
        except RuntimeError: # If already closed
            pass
    finally:
        # Disconnected
        print(f"Client #{session_id} disconnected")

# Add WebSocketDisconnect to imports if not already there:
from fastapi import WebSocketDisconnect # Make sure this is imported