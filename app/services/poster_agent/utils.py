from google.adk.tools import load_artifacts
from google.adk.tools import ToolContext
from google.genai import Client
import logging,traceback
from app.core.config import settings
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)



client = Client(api_key=settings.GOOGLE_API_KEY)

async def generate_image(prompt: str, tool_context: ToolContext):
  """Generates an image based on the prompt."""
  try:
    logger.info(f"Generating image with prompt: '{prompt[:70]}...'")
    response = client.models.generate_images(
        model= settings.IMAGE_GEN_GEMINI_MODEL, #'imagen-3.0-generate-002', # Using a powerful image model
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
