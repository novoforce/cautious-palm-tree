# app/main.py
from fastapi import FastAPI, Query, WebSocket,Response, status
from typing import AsyncIterable, Dict, Any
from app.api.v1.routers import api_router
from app.core.config import settings
import logging
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.root_agent.agent import supervisor
import os, json, base64, asyncio
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.events.event import Event
from google.genai import types
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from typing import AsyncIterable
from app.services.visualization_agent.agent import _artifact_service, _session_service as _vis_session_service
from dotenv import load_dotenv
load_dotenv(override=True) # Load environment variables from .env file, overriding existing ones

# Configure basic logging for the FastAPI app
logging.basicConfig(
    level=logging.ERROR, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("fastapi_app")

import os

for key, value in os.environ.items():
    print(f'ENV_VAR:> {key}: {value}')

APP_NAME = "Serena Agent"
session_service = InMemorySessionService()
artifact_service = _artifact_service # Placeholder for artifact service, if needed later

async def start_agent_session(
    session_id: str,
    user_sends_audio: bool, # True if user input can be audio
    client_wants_agent_audio_output: bool # True if client wants audio output from agent
):
    """Starts an agent session"""
    logger.info(
        f"Starting agent session {session_id}. User sends audio: {user_sends_audio}, Client wants agent audio: {client_wants_agent_audio_output}"
    )
    # Create a Session
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=session_id,
        session_id=session_id
    )
    # Create a Runner
    runner = Runner(
        app_name=APP_NAME,
        agent=supervisor,
        session_service=session_service,
        artifact_service=artifact_service
    )

    # Create run config with basic settings
    config: Dict[str, Any] = {}
    response_modalities = []

    if client_wants_agent_audio_output:
        response_modalities.append("AUDIO")
        # Create speech config with voice settings only if agent audio output is desired
        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
            )
        )
        config["speech_config"] = speech_config
        # If client wants agent audio, ADK can provide transcription of that audio
        config["output_audio_transcription"] = {}
        logger.info("Agent configured for AUDIO output with transcription.")
    else:
        # If client does not want agent audio, agent should only respond with text
        response_modalities.append("TEXT")
        logger.info("Agent configured for TEXT output only.")
    
    config["response_modalities"] = response_modalities

    # Configure input audio transcription if the user is sending audio
    if user_sends_audio:
        config["input_audio_transcription"] = {}
        logger.info("Agent configured for input audio transcription.")
    else:
        logger.info("Agent not configured for input audio transcription (user sends text).")

    run_config = RunConfig(**config)
    logger.debug(f"RunConfig: {run_config}")

    # Create a LiveRequestQueue for this session
    live_request_queue = LiveRequestQueue()
    # Start agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    return live_events, live_request_queue


async def agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None]
):
    """Agent to client communication. Processes events from ADK and sends to WebSocket client."""
    logger.info(f"Task agent_to_client_messaging started for websocket: {websocket.client}")
    try:
        async for event in live_events:
            if event is None:
                continue

            # 1. Handle Turn Completion or Interruption
            if event.turn_complete or event.interrupted:
                message: Dict[str, Any] = { 
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                logger.info(f"[AGENT_TO_CLIENT_SEND - TURN_STATUS]: {message}")
                await websocket.send_text(json.dumps(message))
                continue # Move to next event

            function_responses = event.get_function_responses()
            if function_responses:
                for response in function_responses:
                    try:
                        result_data = response.response
                        if isinstance(result_data, str):
                            result_data = json.loads(result_data)

                        # GENERIC CHECK: Does this tool response contain artifact info?
                        is_artifact_response = (
                            isinstance(result_data, dict) and
                            result_data.get("artifact_saved") and 
                            result_data.get("artifact_saved") != "No" and
                            result_data.get("session_id") and
                            result_data.get("app_name") # Check for the new key
                        )

                        if is_artifact_response:
                            logger.info(f"Detected tool output with artifact from: {response.name}")
                            
                            app_name = result_data["app_name"]
                            artifact_session_id = result_data["session_id"]
                            artifact_filename = result_data["artifact_saved"]
                            
                            # Construct the NEW, generalized URL to the artifact endpoint
                            image_url = f"/artifacts/{app_name}/{artifact_session_id}/{artifact_filename}"
                            
                            # Send a special message to the client with the image URL
                            artifact_message = {
                                "role": "model",
                                "mime_type": "image/png", # Assuming all artifacts are images for now
                                "data": image_url,
                                "caption": "Here is the content you requested:"
                            }
                            logger.info(f"[AGENT_TO_CLIENT_SEND - ARTIFACT]: {artifact_message}")
                            await websocket.send_text(json.dumps(artifact_message))

                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logger.error(f"Error parsing tool output from '{response.name}': {e}. Output was: {response.response}")

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
            # 3. Handle Content Parts (Text from User/Model, Audio from Model)
            if event.content and event.content.parts:
                event_content_role = event.content.role 
                # logger.debug(f"[ADK_EVENT_CONTENT_OBJECT] Role: '{event_content_role}', Partial: {event.partial}, #Parts: {len(event.content.parts)}")
                
                for i, part in enumerate(event.content.parts):
                    # Log details of each part for debugging
                    # logger.info(f"[ADK_EVENT_PART_{i}] EventContentRole: '{event_content_role}', PartType: {type(part)}, PartDetails: {part}")

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
                        elif event_content_role == "model" or event_content_role is None:
                            # If it has text and isn't user_transcription, assume it's model's response.
                            # This catches intermediate text chunks with EventContentRole: 'None'.
                            text_message_to_send = {
                                "mime_type": "text/plain",
                                "data": part.text,
                                "role": "model", # Send with role 'model' for client handling
                            }
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
        try: 
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
                await websocket.send_text(json.dumps({"error": f"Mime type not supported: {mime_type}", "role": "system"}))

        except asyncio.CancelledError:
            logger.info("client_to_agent_messaging task cancelled.")
            break
        except WebSocketDisconnect:
            logger.info("Client disconnected from client_to_agent_messaging.")
            break
        except Exception as e:
            logger.error(f"Error in client_to_agent_messaging: {e}")
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

from app.services.visualization_agent.agent import USER_ID as VIS_USER_ID
from app.services.poster_agent.agent import USER_ID as POSTER_USER_ID

USER_ID_MAP = {
    "visualization_app": VIS_USER_ID,
    "poster_app": POSTER_USER_ID,
}

@app.get("/artifacts/{app_name}/{session_id}/{filename}")
async def get_artifact(app_name: str, session_id: str, filename: str):
    """
    Retrieves an artifact from the in-memory artifact service based on its app, session, and filename.
    """
    logger.info(f"Request for artifact '{filename}' from app '{app_name}' and session '{session_id}'")
    try:
        user_id = USER_ID_MAP.get(app_name)
        if not user_id:
            logger.error(f"No user_id mapping found for app_name: '{app_name}'")
            return Response(status_code=status.HTTP_404_NOT_FOUND, content="Artifact app not found")

        artifact = await _artifact_service.load_artifact(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            filename=filename,
        )

        if artifact and artifact.inline_data:
            image_bytes = artifact.inline_data.data
            mime_type = artifact.inline_data.mime_type
            return Response(content=image_bytes, media_type=mime_type)
        else:
            logger.warning(f"Artifact not found: app='{app_name}', session='{session_id}', file='{filename}'")
            return Response(status_code=status.HTTP_404_NOT_FOUND, content="Artifact not found")

    except Exception as e:
        logger.error(f"Error retrieving artifact: {e}", exc_info=True)
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content="Error retrieving artifact")


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    user_sends_audio_str: str = Query(..., alias="is_audio"), # User input mode: "true" or "false"
    agent_wants_audio_output_str: str = Query("true", alias="agent_wants_audio_output") # Agent output mode
):
    """Client websocket endpoint"""
    await websocket.accept()
    logger.info(
        f"Client #{session_id} connected. User sends audio: '{user_sends_audio_str}'. Agent audio output: '{agent_wants_audio_output_str}'"
    )

    user_sends_audio_bool = user_sends_audio_str.lower() == "true"
    agent_wants_audio_output_bool = agent_wants_audio_output_str.lower() == "true"

    try:
        live_events, live_request_queue = await start_agent_session(
            session_id,
            user_sends_audio=user_sends_audio_bool,
            client_wants_agent_audio_output=agent_wants_audio_output_bool
        )
        logger.info(f"Agent session started for client #{session_id}")

        agent_to_client_task = asyncio.create_task(
            agent_to_client_messaging(websocket, live_events)
        )
        client_to_agent_task = asyncio.create_task(
            client_to_agent_messaging(websocket, live_request_queue)
        )

        done, pending = await asyncio.wait(
            [agent_to_client_task, client_to_agent_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            logger.info(f"Cancelling pending task: {task.get_name()}")
            task.cancel()
        
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            logger.info("Pending tasks gathered after cancellation.")

        for task in done:
            if task.exception():
                logger.error(f"Task {task.get_name()} raised an exception: {task.exception()}", exc_info=task.exception())
            else:
                logger.info(f"Task {task.get_name()} completed.")


    except Exception as e:
        logger.error(f"Error in websocket_endpoint for client #{session_id}: {e}", exc_info=True)
        try:
            await websocket.close(code=1011) # Internal error
        except RuntimeError: # If already closed
            pass
    finally:
        logger.info(f"Client #{session_id} disconnected")

# Add WebSocketDisconnect to imports if not already there:
from fastapi import WebSocketDisconnect # Make sure this is imported