# app/main.py
from fastapi import FastAPI, Query, WebSocket
from app.api.v1.routers import api_router
from app.core.config import settings
import logging
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.services.agents.agents import general_agent
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


def start_agent_session(session_id, is_audio=True):
    """Starts an agent session"""

    # Create a Session
    session = session_service.create_session(
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


async def agent_to_client_messaging(
    websocket: WebSocket, live_events: AsyncIterable[Event | None]
):
    """Agent to client communication"""
    while True:
        async for event in live_events:
            if event is None:
                continue

            # If the turn complete or interrupted, send it
            if event.turn_complete or event.interrupted:
                message = {
                    "turn_complete": event.turn_complete,
                    "interrupted": event.interrupted,
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: {message}")
                continue

            # Read the Content and its first Part
            part = event.content and event.content.parts and event.content.parts[0]
            if not part:
                continue

            # Make sure we have a valid Part
            if not isinstance(part, types.Part):
                continue

            # Only send text if it's a partial response (streaming)
            # Skip the final complete message to avoid duplication
            if part.text and event.partial:
                message = {
                    "mime_type": "text/plain",
                    "data": part.text,
                    "role": "model",
                }
                await websocket.send_text(json.dumps(message))
                print(f"[AGENT TO CLIENT]: text/plain: {part.text}")

            # If it's audio, send Base64 encoded audio data
            is_audio = (
                part.inline_data
                and part.inline_data.mime_type
                and part.inline_data.mime_type.startswith("audio/pcm")
            )
            if is_audio:
                audio_data = part.inline_data and part.inline_data.data
                if audio_data:
                    message = {
                        "mime_type": "audio/pcm",
                        "data": base64.b64encode(audio_data).decode("ascii"),
                        "role": "model",
                    }
                    await websocket.send_text(json.dumps(message))
                    print(f"[AGENT TO CLIENT]: audio/pcm: {len(audio_data)} bytes.")


async def client_to_agent_messaging(
    websocket: WebSocket, live_request_queue: LiveRequestQueue
):
    """Client to agent communication"""
    while True:
        # Decode JSON message
        message_json = await websocket.receive_text()
        message = json.loads(message_json)
        mime_type = message["mime_type"]
        data = message["data"]
        role = message.get("role", "user")  # Default to 'user' if role is not provided

        # Send the message to the agent
        if mime_type == "text/plain":
            # Send a text message
            content = types.Content(role=role, parts=[types.Part.from_text(text=data)])
            live_request_queue.send_content(content=content)
            print(f"[CLIENT TO AGENT PRINT]: {data}")
        elif mime_type == "audio/pcm":
            # Send audio data
            decoded_data = base64.b64decode(data)
            # print(f"[CLIENT TO AGENT PRINT]:> {decoded_data}")
            # Send the audio data - note that ActivityStart/End and transcription
            # handling is done automatically by the ADK when input_audio_transcription
            # is enabled in the config
            live_request_queue.send_realtime(
                types.Blob(data=decoded_data, mime_type=mime_type)
            )
            # print(f"[CLIENT TO AGENT]: audio/pcm: {len(decoded_data)} bytes")

        else:
            raise ValueError(f"Mime type not supported: {mime_type}")


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
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    is_audio: str = Query(...),
):
    """Client websocket endpoint"""

    # Wait for client connection
    await websocket.accept()
    print(f"Client #{session_id} connected, audio mode: {is_audio}")

    # Start agent session
    live_events, live_request_queue = start_agent_session(
        session_id  # to be toggled
    )
    print("Agent session started!!")
    # Start tasks
    agent_to_client_task = asyncio.create_task(
        agent_to_client_messaging(websocket, live_events)
    )
    client_to_agent_task = asyncio.create_task(
        client_to_agent_messaging(websocket, live_request_queue)
    )
    await asyncio.gather(agent_to_client_task, client_to_agent_task)

    # Disconnected
    print(f"Client #{session_id} disconnected")
