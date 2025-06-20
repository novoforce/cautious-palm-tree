import asyncio
import uuid
import os
import json
from typing import Dict, Any, List

from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.sessions import InMemorySessionService
from google.adk.artifacts import InMemoryArtifactService
from google.adk.runners import Runner
from google.genai.types import Content, Part
from dotenv import load_dotenv
import logging
import traceback

# Import Plotly for the tool
import plotly.graph_objects as go
import plotly.io as pio
# Import ADK tool-related classes
from google.adk.tools import ToolContext
from google.genai import types

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# --- Constants ---
APP_NAME = "visualization_app"
USER_ID = "dev_user_01"
MODEL_GEMINI_2_0_FLASH = "gemini-2.0-flash-001"

# ==============================================================================
# AGENT AND TOOL DEFINITIONS
# ==============================================================================

# Agent 1: Predicts the best chart type (Unchanged)
chart_type_agent = LlmAgent(
    name="chart_type_predictor_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    description="Predicts the chart type and design based on the user query and provided data.",
    instruction=(
        """You are an expert data visualization AI. Your task is to predict the most effective chart type
        based on a user's query and the data they provide.

        Analyze the structure of the data (column names, number of rows) and the user's goal.
        Recommend a chart type (e.g., 'bar', 'line', 'pie', 'scatter') and provide a brief justification.

        User Query: "{user_query}"
        Data (first 5 rows): ```{query_execution_output}```

        Output your prediction as a JSON object with keys "chart_type" and "justification".
        """
    ),
    output_key="chart_type_output",
)

# Agent 2: Generates Plotly code (Unchanged)
plotly_code_agent = LlmAgent(
    name="plotly_code_generator_agent",
    model=MODEL_GEMINI_2_0_FLASH,
    description="Generates Python Plotly code for the predicted chart type and data.",
    instruction=(
        """You are a Python Plotly expert. Your task is to write Plotly code to generate a chart.

        - The data is available in a variable named `data`, which is a list of dictionaries.
        - The chart specification is provided below.
        - The generated Python code must create a Plotly Figure object and assign it to a variable named `fig`.
        - Do not include any `import` statements or data loading code. Assume `data` is pre-loaded.
        - Ensure the chart has clear titles and axis labels.

        Chart Specification: ```{chart_type_output}```
        Data for Charting: ```{query_execution_output}```

        Output ONLY the raw Python code required to generate the figure.
        """
    ),
    output_key="plotly_code_output",
)


# ==============================================================================
# CORRECTED TOOL AND EXECUTOR AGENT
# ==============================================================================

# Tool: Executes Plotly code. The signature is now simplified.
async def execute_plotly_code_and_get_image_bytes(
    plotly_code_str: str, tool_context: ToolContext
):
    """
    Executes a string of Plotly Python code to generate and save a chart image.
    The code string must define a variable `fig` holding the Plotly Figure object.
    The data for the chart is retrieved from the session state key 'query_execution_output'.
    """
    try:
        logger.info("Executing generated Plotly code...")
        
        # FIX: Retrieve data from the context instead of as a parameter
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


# Agent 3: Executes the code using the tool. Instruction is now simplified.
plotly_code_executor_agent = LlmAgent(
    model=MODEL_GEMINI_2_0_FLASH,
    name='plotly_code_executor_agent',
    description="An agent that executes Plotly code to generate an image.",
    # FIX: Simplified instruction, as data is no longer a direct parameter
    instruction="""You are a code execution agent.
    Your task is to execute the provided Plotly code using the `execute_plotly_code_and_get_image_bytes` tool.

    The code to execute is:
    ```{plotly_code_output}```

    Call the tool with the `plotly_code_str` argument. The data is available to the tool automatically.
    """,
    tools=[execute_plotly_code_and_get_image_bytes],
    output_key="execution_summary"
)

# ==============================================================================
# SEQUENTIAL AGENT AND EXECUTION WRAPPER
# ==============================================================================

# The complete sequential visualization pipeline (Unchanged)
visualization_agent = SequentialAgent(
    name="VisualizationPipelineAgent",
    sub_agents=[chart_type_agent, plotly_code_agent, plotly_code_executor_agent],
    description="Generates a chart from data by predicting type, writing code, and executing it.",
)

# Instantiate services once on import
_session_service = InMemorySessionService()
_artifact_service = InMemoryArtifactService()

# The main execution function
async def execute_visualization_pipeline(user_query: str, query_data: List[Dict[str, Any]], tool_context: ToolContext) -> Dict[str, Any]:
    """
    Executes the visualization pipeline to generate a chart image artifact.

    Args:
        user_query (str): The user's natural language request for a visualization.
        query_data (List[Dict[str, Any]]): The data returned from the SQL query pipeline.

    Returns:
        dict: A dictionary containing results from each stage and the final artifact info.
    """
    tool_context.actions.skip_summarization = True
    logger.info("Set skip_summarization=True for visualization pipeline.")

    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY environment variable not found."}

    try:
        current_session_id = str(uuid.uuid4())
        print(f"▶️  Running Visualization pipeline for query: '{user_query[:50]}...'")

        # Set the initial state with the data from the previous (SQL) pipeline
        initial_state = {"query_execution_output": query_data, "user_query": user_query}

        await _session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=current_session_id,
            state=initial_state,
        )

        # The Runner is initialized with the artifact_service.
        runner = Runner(
            agent=visualization_agent,
            app_name=APP_NAME,
            session_service=_session_service,
            artifact_service=_artifact_service,
        )

        initial_message = Content(role="user", parts=[Part(text=user_query)])

        async for _ in runner.run_async(
            user_id=USER_ID, session_id=current_session_id, new_message=initial_message
        ):
            pass

        session_state_data = await _session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id
        )

        # Extract outputs from each step
        chart_type_info = session_state_data.state.get("chart_type_output")
        plotly_code = session_state_data.state.get("plotly_code_output")
        execution_summary = session_state_data.state.get("execution_summary")
        
        # Verify the artifact was saved
        final_artifact = await _artifact_service.load_artifact(
            app_name=APP_NAME, user_id=USER_ID, session_id=current_session_id, filename="plot.png"
        )

        print("✅ Visualization pipeline completed successfully.")
        return {
            "session_id": current_session_id,
            "chart_type_info": chart_type_info or "Not generated.",
            "generated_plotly_code": plotly_code or "Not generated.",
            "execution_summary": execution_summary or "Not executed.",
            "artifact_saved": "plot.png" if final_artifact else "No",
            "artifact_size_bytes": len(final_artifact.inline_data.data) if final_artifact else 0,
        }

    except Exception as e:
        print(f"❌ Pipeline failed with an error: {e}")
        traceback.print_exc()
        return {"error": str(e)}

# --- Example Usage ---
async def main():
    """Main function to demonstrate running the visualization pipeline."""
    print("--- Running Visualization Pipeline Agent ---")

    # Mock data representing the output of a prior SQL pipeline
    mock_sql_result = [
        {'product_name': 'T-Shirt', 'total_sold': 150},
        {'product_name': 'Jeans', 'total_sold': 120},
        {'product_name': 'Jacket', 'total_sold': 90},
        {'product_name': 'Socks', 'total_sold': 200},
        {'product_name': 'Hat', 'total_sold': 75},
    ]
    
    user_input = "Show me a bar chart of the top selling products"
    
    result = await execute_visualization_pipeline(user_input, mock_sql_result)

    print("\n--- VISUALIZATION PIPELINE RESULTS ---")
    if result.get("error"):
        print(f"Error: {result['error']}")
    else:
        # Pretty print the results
        for key, value in result.items():
            print(f"\n--- {key.replace('_', ' ').upper()} ---")
            if key == "generated_plotly_code":
                print(value)
            elif isinstance(value, (dict, list)):
                print(json.dumps(value, indent=2))
            else:
                print(value)
    print("------------------------------------")
    # You could also save the artifact to disk here to view it
    if not result.get("error") and result.get("artifact_saved") == "plot.png":
        print("\nAttempting to save artifact to disk...")
        try:
            session_id = result["session_id"]
            filename_to_load = "plot.png"

            # Load the artifact from the service using the session_id
            final_artifact = await _artifact_service.load_artifact(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=session_id,
                filename=filename_to_load,
            )

            if final_artifact and final_artifact.inline_data:
                output_filename = "output_chart.png"
                # Open a file in binary write mode ('wb') and save the data
                with open(output_filename, "wb") as f:
                    f.write(final_artifact.inline_data.data)
                print(f"✅ Success! Chart saved to '{output_filename}'")
            else:
                print("⚠️ Could not retrieve the artifact from the service.")
        except Exception as e:
            print(f"❌ Failed to save artifact to disk. Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())