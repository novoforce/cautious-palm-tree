import asyncio
import uuid
import os
import json
from typing import Dict, Any
import logging
import traceback

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.adk.tools import load_artifacts
from google.adk.tools import ToolContext
from google.genai import Client
from google.genai.types import Content, Part
from google.genai import types
from dotenv import load_dotenv
from app.services.visualization_agent.agent import _artifact_service
# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Constants ---
APP_NAME = "poster_app"
USER_ID = "dev_user_01"
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash-001"

# ==============================================================================
# POSTER AGENT AND TOOL DEFINITIONS (Your provided code)
# ==============================================================================

# Initialize the GenAI client once
# Ensure you have your GOOGLE_API_KEY in a .env file or set as an environment variable
load_dotenv()
client = Client()

async def generate_image(prompt: str, tool_context: ToolContext):
  """Generates an image based on the prompt."""
  try:
    logger.info(f"Generating image with prompt: '{prompt[:70]}...'")
    response = client.models.generate_images(
        model='imagen-3.0-generate-002', # Using a powerful image model
        prompt=prompt,
        config={'number_of_images': 1},
    )
    if not response.generated_images:
      logger.error("Image generation failed, no images returned.")
      return {'status': 'failed', 'detail': 'The model did not return any images.'}
      
    image_bytes = response.generated_images[0].image.image_bytes
    
    filename = 'generated_image.png'
    await tool_context.save_artifact(
        filename,
        types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
    )
    logger.info(f"Successfully saved image as artifact: '{filename}'")
    return {
        'status': 'success',
        'detail': f'Image generated successfully and stored in artifact: {filename}',
        'filename': filename,
    }
  except Exception as e:
      error_message = f"Error generating image: {e}\n{traceback.format_exc()}"
      logger.error(error_message)
      return {"status": "error", "detail": error_message}

image_generator_agent = LlmAgent(
    model=MODEL_GEMINI_2_0_FLASH,
    name='image_generator_agent',
    description="An agent that generates images based on user prompts.",
    instruction="""You are an agent whose job is to generate an image based on the user's prompt.
When the user asks you to create an image, you MUST call the `generate_image` tool with a detailed, descriptive prompt to create the best possible image.
""",
    tools=[generate_image, load_artifacts],
    output_key="image_generation_summary" # Added for clarity in session state
)


# ==============================================================================
# AGENT EXECUTION WRAPPER
# ==============================================================================

# Instantiate services once on import
_session_service = InMemorySessionService()
# _artifact_service = InMemoryArtifactService()

async def execute_poster_pipeline(user_prompt: str) -> Dict[str, Any]:
    """
    Executes the poster agent pipeline to generate an image artifact.

    Args:
        user_prompt (str): The user's natural language request for an image.

    Returns:
        dict: A dictionary containing the session ID and information about the generated artifact.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY environment variable not found."}

    try:
        current_session_id = str(uuid.uuid4())
        print(f"▶️  Running Poster pipeline for prompt: '{user_prompt[:50]}...'")

        await _session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=current_session_id,
            state={}, # Initial state can be empty
        )

        # The Runner is initialized with the services.
        runner = Runner(
            agent=image_generator_agent,
            app_name=APP_NAME,
            session_service=_session_service,
            artifact_service=_artifact_service,
        )

        initial_message = Content(role="user", parts=[Part(text=user_prompt)])

        # Run the agent until it completes its task
        async for _ in runner.run_async(
            user_id=USER_ID, session_id=current_session_id, new_message=initial_message
        ):
            pass

        # Verify the artifact was saved by trying to load it
        generated_filename = "generated_image.png"
        final_artifact = await _artifact_service.load_artifact(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id, filename=generated_filename
        )

        print("✅ Poster pipeline completed successfully.")
        return {
            "session_id": current_session_id,
            "artifact_saved": generated_filename if final_artifact else "No",
            "artifact_size_bytes": len(final_artifact.inline_data.data) if final_artifact else 0,
        }

    except Exception as e:
        print(f"❌ Pipeline failed with an error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

# --- Example Usage ---
async def main():
    """Main function to demonstrate running the poster agent pipeline."""
    print("--- Running Poster Generation Agent ---")

    # Example prompt for the poster agent
    user_input = "Create a photorealistic image of a futuristic city skyline at sunset, with flying cars and holographic advertisements."
    
    result = await execute_poster_pipeline(user_input)

    print("\n--- POSTER PIPELINE RESULTS ---")
    if result.get("error"):
        print(f"Error: {result['error']}")
    else:
        # Pretty print the results
        print(json.dumps(result, indent=2))
        
    print("------------------------------------")
    
    # Save the generated artifact to disk to view it
    if not result.get("error") and result.get("artifact_saved") != "No":
        print("\nAttempting to save artifact to disk...")
        try:
            session_id = result["session_id"]
            filename_to_load = result["artifact_saved"]

            # Load the artifact from the service using the session_id
            final_artifact = await _artifact_service.load_artifact(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=session_id,
                filename=filename_to_load,
            )

            if final_artifact and final_artifact.inline_data:
                output_filename = "output_image.png"
                # Open a file in binary write mode ('wb') and save the data
                with open(output_filename, "wb") as f:
                    f.write(final_artifact.inline_data.data)
                print(f"✅ Success! Image saved to '{output_filename}'")
            else:
                print("⚠️ Could not retrieve the artifact from the service.")
        except Exception as e:
            print(f"❌ Failed to save artifact to disk. Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())