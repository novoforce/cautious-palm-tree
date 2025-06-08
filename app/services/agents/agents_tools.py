# to be defined later
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma
from google.adk.tools.tool_context import ToolContext
from typing import Optional

from app.services.a2a_integration.agent_connector import AgentConnector # New import
from app.core.config import settings # New import
import uuid # For session_id if needed, or pass from ADK context

embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-exp-03-07")
vector_store = Chroma(
    collection_name="StyleHubMetadataDB",  # Name of the collection in Chroma
    embedding_function=embeddings,
    persist_directory="./chroma_db",  # Where to save data locally, remove if not necessary
)


def say_hello(name: Optional[str] = None) -> str:
    """Provides a simple greeting. If a name is provided, it will be used.

    Args:
        name (str, optional): The name of the person to greet. Defaults to a generic greeting if not provided.

    Returns:
        str: A friendly greeting message.
    """
    if name:
        greeting = f"Hello, {name}!"
        print(f"--- Tool: say_hello called with name: {name} ---")
    else:
        greeting = "Hello there!" # Default greeting if name is None or not explicitly passed
        print(f"--- Tool: say_hello called without a specific name (name_arg_value: {name}) ---")
    return greeting

def say_goodbye() -> str:
    """Provides a simple farewell message to conclude the conversation."""
    print(f"--- Tool: say_goodbye called ---")
    return "Goodbye! Have a great day."


def exit_loop(tool_context: ToolContext):
    """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
    print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
    tool_context.actions.escalate = True
    # Return empty dict as tools should typically return JSON-serializable output
    return {}

def get_similar_tables_tool(user_query:str):
    """
    Function to get similar tables based on user query.
    Uses vector store to find relevant tables.
    
    Args:
        user_query (str): The user's query to search for similar tables.
        
    Returns:
        list: A list of tuples containing the table name and similarity score.
    """
    results = vector_store.similarity_search_with_score(user_query, k=5)
    return [(res.page_content, score) for res, score in results]

# --- A2A Integration Tools ---
async def call_external_tell_time_agent(message: str, tool_context: Optional[ToolContext] = None) -> str:
    """
    Calls the external A2A TellTimeAgent to get the current time.
    Args:
        message (str): The query for the TellTimeAgent (e.g., "What is the current time?").
        tool_context (ToolContext, optional): ADK tool context to get session_id.
    Returns:
        str: The response from the TellTimeAgent.
    """
    print(f"--- Tool: call_external_tell_time_agent called with message: {message} ---")
    connector = AgentConnector(name="ExternalTellTimeAgent", base_url=settings.A2A_TELL_TIME_AGENT_URL)

    # Get session_id. The ADK's ToolContext usually provides access to session info.
    # If tool_context.session_id is not directly available, you might need to
    # manage a session_id within the tool or pass it from the agent.
    # For now, let's generate a new one or assume it can be retrieved.
    # The session_id from the WebSocket (passed to runner.run_live) should be accessible.
    # Let's assume you can get it from tool_context or it's implicitly handled by the runner's session.
    # For simplicity in this first pass, we might use a fixed or new one for the A2A call,
    # but ideally, it should be the same session_id from the Serena WebSocket.

    # How you get session_id here is crucial. The `tool_context` in ADK is the way.
    # Let's assume the session_id from the websocket is available via tool_context.state
    # or some other attribute if the ADK populates it.
    # If not, the agent invoking this tool needs to pass it.
    # For now, let's see if we can get it from the WebSocket's session_id
    # In a real ADK tool, you'd use tool_context.session.id or similar.
    # Since this is a simple function tool, we might need the main agent to provide it.
    # Let's assume for now the ADK handles session propagation or the agent provides it.

    # Simplification: The AgentConnector expects a session_id.
    # We need to ensure the main SERENA agent passes its session_id to this tool.
    # Let's modify the tool to accept it, or the calling agent prepares it.
    # For now, let's use a dummy one, and refine later.
    # A better way is for the agent's main invoke/run method to manage this.
    # The LiveRequestQueue and Runner in main.py manage the session.
    # The tool context SHOULD give us this.
    current_session_id = str(uuid.uuid4().hex) # Placeholder - THIS NEEDS REFINEMENT
    current_session_id = tool_context._invocation_context.session.id
    if tool_context and hasattr(tool_context, 'state') and "session_id" in tool_context.state:
         current_session_id = tool_context.state["session_id"]
    elif tool_context and hasattr(tool_context, 'session_id'): # Ideal if ADK provides this
         current_session_id = tool_context.session_id
    
    print(f"Using session_id for A2A call: {current_session_id}")


    try:
        task_result = await connector.send_task(message, session_id=current_session_id)
        if task_result.history and task_result.history[-1].parts:
            return task_result.history[-1].parts[0].text
        return "No response from TellTimeAgent."
    except Exception as e:
        print(f"Error calling TellTimeAgent: {e}")
        return f"Error: Could not connect to TellTimeAgent. {e}"


async def call_external_greeting_agent(message: str, tool_context: Optional[ToolContext] = None) -> str:
    """
    Calls the external A2A GreetingAgent.
    Args:
        message (str): The query for the GreetingAgent (e.g., "Greet me").
        tool_context (ToolContext, optional): ADK tool context.
    Returns:
        str: The response from the GreetingAgent.
    """
    print(f"--- Tool: call_external_greeting_agent called with message: {message} ---")
    connector = AgentConnector(name="ExternalGreetingAgent", base_url=settings.A2A_GREETING_AGENT_URL)
    
    current_session_id = str(uuid.uuid4().hex) # Placeholder - THIS NEEDS REFINEMENT
    current_session_id= tool_context._invocation_context.session.id
    if tool_context and hasattr(tool_context, 'state') and "session_id" in tool_context.state:
         current_session_id = tool_context.state["session_id"]
    elif tool_context and hasattr(tool_context, 'session_id'):
         current_session_id = tool_context.session_id
    
    print(f"Using session_id for A2A call: {current_session_id}")

    try:
        task_result = await connector.send_task(message, session_id=current_session_id)
        if task_result.history and task_result.history[-1].parts:
            return task_result.history[-1].parts[0].text
        return "No response from GreetingAgent."
    except Exception as e:
        print(f"Error calling GreetingAgent: {e}")
        return f"Error: Could not connect to GreetingAgent. {e}"

# IMPORTANT: The session_id propagation needs careful handling.
# The ADK `Runner` in your `main.py` creates a session.
# When a tool is called, the `ToolContext` *should* provide access to this session or its ID.
# If `tool_context.state` is used by ADK to pass session-specific data, you can retrieve it there.
# Or, the `LlmAgent` definition allows tools to be instances of classes that can hold state,
# or the tool functions themselves are passed the context.

# For now, the placeholder `uuid.uuid4().hex` is for testing connection.
# You will need to ensure the correct `session_id` from SERENA's main WebSocket session
# is passed to these A2A calls. This might involve modifying how `general_greeting_agent`
# calls these tools or how `ToolContext` is used.
# A common pattern is `tool_context.state["session_id"] = websocket_session_id`
# when the runner is initiated if the ADK doesn't do it automatically.
# Given you use LiveRequestQueue, the session is managed by the Runner.
# The tools defined in LlmAgent are usually passed a ToolContext.
# Check `google.adk.tools.tool_context.ToolContext` for how to access session ID.
# Often, it's `tool_context.session.id`.
# Let's assume the agent definition will use `FunctionTool` which passes `ToolContext`.