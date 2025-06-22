import asyncio
import uuid
import os
import json
from typing import Dict, Any
import logging
import traceback

from google.adk.agents import LlmAgent
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.tools import load_artifacts
from google.adk.tools import ToolContext
from google.genai.types import Content, Part
from app.core.config import settings
from .prompt import IMAGE_GENERATOR_INSTRUCTION
from .utils import generate_image

from app.services.visualization_agent.agent import _artifact_service #shared artifact service for visualization agent
# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Constants ---
APP_NAME = "poster_app"
USER_ID = "dev_user_01"

poster_generator_agent = LlmAgent(
    model=settings.POSTER_AGENT_GEMINI_MODEL,
    name='image_generator_agent',
    description="An agent that generates images based on user prompts.",
    instruction=IMAGE_GENERATOR_INSTRUCTION,
    tools=[generate_image, load_artifacts],
    output_key="image_generation_summary" # Added for clarity in session state
)

# Instantiate services once on import
_session_service = InMemorySessionService()

async def call_poster_agent(user_prompt: str,tool_context: ToolContext) -> Dict[str, Any]:
    """
    Executes the poster agent pipeline to generate an image artifact.

    Args:
        user_prompt (str): The user's natural language request for an image.

    Returns:
        dict: A dictionary containing the session ID and information about the generated artifact.
    """
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
            agent=poster_generator_agent,
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
            "app_name": APP_NAME,
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
    
    result = await call_poster_agent(user_input)

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

# main_agent.py

# import asyncio
# import uuid
# import os
# import json
# from typing import Dict, Any
# import logging
# import traceback

# from google.adk.agents import LlmAgent
# from google.adk.sessions import InMemorySessionService
# from google.adk.artifacts import InMemoryArtifactService
# from google.adk.runners import Runner
# from google.adk.tools import load_artifacts
# from google.adk.tools import ToolContext
# from google.genai.types import Content, Part
# from app.core.config import settings
# from .prompt import IMAGE_GENERATOR_INSTRUCTION
# from .utils import generate_image

# # --- Basic Setup ---
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# logger = logging.getLogger(__name__)

# # --- Constants ---
# APP_NAME = "poster_app"
# USER_ID = "dev_user_01"

# poster_generator_agent = LlmAgent(
#     model=settings.POSTER_AGENT_GEMINI_MODEL,
#     name='image_generator_agent',
#     description="An agent that generates images based on user prompts.",
#     instruction=IMAGE_GENERATOR_INSTRUCTION,
#     tools=[generate_image, load_artifacts],
#     output_key="image_generation_summary" # Added for clarity in session state
# )

# # Instantiate services once on import
# _session_service = InMemorySessionService()
# _artifact_service = InMemoryArtifactService()

# async def execute_poster_pipeline(user_prompt: str, tool_context: ToolContext) -> Dict[str, Any]:
#     """
#     Executes the poster agent pipeline to generate an image artifact.

#     Args:
#         user_prompt (str): The user's natural language request for an image.

#     Returns:
#         dict: A dictionary containing the session ID and information about the generated artifact.
#     """
#     try:
#         current_session_id = str(uuid.uuid4())
#         print(f"▶️  Running Poster pipeline for prompt: '{user_prompt[:50]}...'")

#         await _session_service.create_session(
#             app_name=APP_NAME,
#             user_id=USER_ID,
#             session_id=current_session_id,
#             state={}, # Initial state can be empty
#         )

#         # The Runner is initialized with the services.
#         runner = Runner(
#             agent=poster_generator_agent,
#             app_name=APP_NAME,
#             session_service=_session_service,
#             artifact_service=_artifact_service,
#         )

#         initial_message = Content(role="user", parts=[Part(text=user_prompt)])

#         # Run the agent until it completes its task
#         async for _ in runner.run_async(
#             user_id=USER_ID, session_id=current_session_id, new_message=initial_message
#         ):
#             pass

#         # Verify the artifact was saved by trying to load it
#         generated_filename = "generated_image.png"
#         final_artifact = await _artifact_service.load_artifact(
#             app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id, filename=generated_filename
#         )

#         print("✅ Poster pipeline completed successfully.")
#         return {
#             "session_id": current_session_id,
#             "app_name": APP_NAME,
#             "artifact_saved": generated_filename if final_artifact else "No",
#             "artifact_size_bytes": len(final_artifact.inline_data.data) if final_artifact else 0,
#         }

#     except Exception as e:
#         print(f"❌ Pipeline failed with an error: {e}")
#         traceback.print_exc()
#         return {"error": str(e)}

# # --- Example Usage ---
# async def main():
#     """Main function to demonstrate running the poster agent pipeline."""
#     print("--- Running Poster Generation Agent ---")

#     # Example prompt for the poster agent
#     user_input = "Create a photorealistic image of a futuristic city skyline at sunset, with flying cars and holographic advertisements."
    
#     result = await execute_poster_pipeline(user_input, ToolContext())

#     print("\n--- POSTER PIPELINE RESULTS ---")
#     if result.get("error"):
#         print(f"Error: {result['error']}")
#     else:
#         # Pretty print the results
#         print(json.dumps(result, indent=2))
        
#     print("------------------------------------")
    
#     # Save the generated artifact to disk to view it
#     if not result.get("error") and result.get("artifact_saved") != "No":
#         print("\nAttempting to save artifact to disk...")
#         try:
#             session_id = result["session_id"]
#             filename_to_load = result["artifact_saved"]

#             # Load the artifact from the service using the session_id
#             final_artifact = await _artifact_service.load_artifact(
#                 app_name=APP_NAME,
#                 user_id=USER_ID,
#                 session_id=session_id,
#                 filename=filename_to_load,
#             )

#             if final_artifact and final_artifact.inline_data:
#                 output_filename = "output_image.png"
#                 # Open a file in binary write mode ('wb') and save the data
#                 with open(output_filename, "wb") as f:
#                     f.write(final_artifact.inline_data.data)
#                 print(f"✅ Success! Image saved to '{output_filename}'")
#             else:
#                 print("⚠️ Could not retrieve the artifact from the service.")
#         except Exception as e:
#             print(f"❌ Failed to save artifact to disk. Error: {e}")


# if __name__ == "__main__":
#     asyncio.run(main())
