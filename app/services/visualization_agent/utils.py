# utils.py

import logging
import traceback
import plotly.graph_objects as go
import plotly.io as pio
from google.adk.tools import ToolContext
from google.genai import types

logger = logging.getLogger(__name__)

async def execute_plotly_code_and_get_image_bytes(plotly_code_str: str, tool_context: ToolContext):
    """
    Executes a string of Plotly Python code to generate and save a chart image.
    The code string must define a variable `fig` holding the Plotly Figure object.
    The data for the chart is retrieved from the session state key 'query_execution_output'.
    """
    try:
        logger.info("Executing generated Plotly code...")
        
        # Retrieve data from the context instead of as a parameter
        data = tool_context.state.get("query_execution_output")
        if not data:
            raise ValueError("Data not found in session state under key 'query_execution_output'.")

        # Prepare the execution environment with the data
        execution_globals = {'go': go, 'data': data}
        local_vars = {}

        # Execute the code string in the prepared environment
        exec(plotly_code_str, execution_globals, local_vars)

        fig = local_vars.get('fig')
        if fig is None or not isinstance(fig, go.Figure):
            raise ValueError("Plotly code must define a Figure object named 'fig'.")

        logger.info("Generating PNG image from Plotly figure.")
        image_bytes = pio.to_image(fig, format='png')
        
        artifact_filename = "plot.png"
        await tool_context.save_artifact(
            artifact_filename,
            types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
        )
        logger.info(f"Successfully saved chart as artifact: '{artifact_filename}'")
        
        return {
            "status": "success",
            "detail": f"Image generated successfully and stored as artifact '{artifact_filename}'.",
            "filename": artifact_filename,
        }
    except Exception as e:
        error_message = f"Error executing Plotly code: {e}\n{traceback.format_exc()}"
        logger.error(error_message)
        return {"status": "error", "detail": error_message}
