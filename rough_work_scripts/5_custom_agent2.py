# agent.py # Full runnable code for the DYNAMIC StoryFlowAgent example
import logging
import asyncio
import json
from typing import AsyncGenerator, Dict
from typing_extensions import override

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent, SequentialAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event

# --- Constants & Logging ---
APP_NAME = "story_app"
USER_ID = "12345"
SESSION_ID = "123344"
GEMINI_2_FLASH = "gemini-2.0-flash"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- THE DYNAMIC CUSTOM AGENT ---
class CreativeWriterAgent(BaseAgent):
    """
    A custom agent that DYNAMICALLY selects a writer agent (story, poem, etc.)
    based on a router's decision, then orchestrates a refinement workflow.
    """
    # _CHANGED_: Removed critic, reviser, etc. They are no longer direct attributes
    # of this agent. They are implementation details of the loop/sequential agents.
    style_router: LlmAgent
    loop_agent: LoopAgent
    sequential_agent: SequentialAgent
    writer_agents: Dict[str, LlmAgent]

    model_config = {"arbitrary_types_allowed": True}

    # _CHANGED_: The __init__ signature remains the same, as we need these objects
    # to construct the internal agents.
    def __init__(self, name: str, style_router: LlmAgent, writer_agents: Dict[str, LlmAgent], critic: LlmAgent, reviser: LlmAgent, grammar_check: LlmAgent, tone_check: LlmAgent):
        # These internal agents take ownership of their respective sub-agents.
        loop_agent = LoopAgent(name="CriticReviserLoop", sub_agents=[critic, reviser], max_iterations=2)
        sequential_agent = SequentialAgent(name="PostProcessing", sub_agents=[grammar_check, tone_check])

        # _CHANGED_: The sub_agents list now correctly reflects the agents that
        # this class DIRECTLY orchestrates in its _run_async_impl method.
        sub_agents_list = [style_router, loop_agent, sequential_agent] + list(writer_agents.values())

        super().__init__(
            name=name,
            style_router=style_router,
            writer_agents=writer_agents,
            # _CHANGED_: Removed critic, reviser, grammar_check, and tone_check
            # from the super().__init__ call to prevent the parentage conflict.
            loop_agent=loop_agent,
            sequential_agent=sequential_agent,
            sub_agents=sub_agents_list,
        )

    @override
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        logger.info(f"[{self.name}] Starting creative writing workflow.")

        # --- DYNAMIC AGENT SELECTION ---
        logger.info(f"[{self.name}] Running StyleRouter to select a writer...")
        async for event in self.style_router.run_async(ctx):
            yield event

        selected_agent_name = ctx.session.state.get("selected_agent")
        if not selected_agent_name:
            logger.error(f"[{self.name}] Router failed to select an agent. Aborting.")
            return

        writer_to_run = self.writer_agents.get(selected_agent_name.strip())
        if not writer_to_run:
            logger.error(f"[{self.name}] Invalid agent name '{selected_agent_name}' provided by router. Aborting.")
            return

        logger.info(f"[{self.name}] Dynamically selected agent: [{writer_to_run.name}]. Running it now...")
        async for event in writer_to_run.run_async(ctx):
            yield event
        # --- END OF DYNAMIC SELECTION ---

        if ("current_story" not in ctx.session.state or not ctx.session.state["current_story"]):
            logger.error(f"[{self.name}] The selected writer failed to generate content. Aborting workflow.")
            return

        logger.info(f"[{self.name}] Content after generator: {ctx.session.state.get('current_story')[:80]}...")

        # The rest of the workflow calls the top-level agents.
        logger.info(f"[{self.name}] Running CriticReviserLoop...")
        async for event in self.loop_agent.run_async(ctx):
            yield event

        logger.info(f"[{self.name}] Running PostProcessing...")
        async for event in self.sequential_agent.run_async(ctx):
            yield event

        logger.info(f"[{self.name}] Workflow finished.")
        
# --- Define ALL the individual agents ---
story_generator = LlmAgent(name="StoryGenerator", model=GEMINI_2_FLASH, instruction="You are a story writer. Write a short story (around 100 words) based on the topic provided in session state with key 'topic'", output_key="current_story")
poem_generator = LlmAgent(name="PoemGenerator", model=GEMINI_2_FLASH, instruction="You are a poet. Write a short, evocative poem (around 8 lines) based on the topic provided in session state with key 'topic'", output_key="current_story")
screenplay_generator = LlmAgent(name="ScreenplayGenerator", model=GEMINI_2_FLASH, instruction="You are a screenwriter. Write a brief scene (standard screenplay format) based on the topic provided in session state with key 'topic'", output_key="current_story")
style_router_agent = LlmAgent(name="StyleRouter", model=GEMINI_2_FLASH, instruction="You are a routing agent. Read the user's request in the 'topic' state. If the user wants a story, output 'story_generator'. If a poem, output 'poem_generator'. If a screenplay, output 'screenplay_generator'. Default to 'story_generator'. Output ONLY the name.", output_key="selected_agent")
critic = LlmAgent(name="Critic", model=GEMINI_2_FLASH, instruction="You are a critic. Review the text in 'current_story'. Provide 1-2 sentences of constructive criticism.", output_key="criticism")
reviser = LlmAgent(name="Reviser", model=GEMINI_2_FLASH, instruction="You are a reviser. Revise the text in 'current_story' based on the 'criticism'. Output only the revised text.", output_key="current_story")
grammar_check = LlmAgent(name="GrammarCheck", model=GEMINI_2_FLASH, instruction="You are a grammar checker. Check the grammar of the text in 'current_story'. Output only the suggested corrections as a list, or output 'Grammar is good!'.", output_key="grammar_suggestions")
tone_check = LlmAgent(name="ToneCheck", model=GEMINI_2_FLASH, instruction="You are a tone analyzer. Analyze the tone of the text in 'current_story'. Output only one word: 'positive', 'negative', or 'neutral'.", output_key="tone_check_result")


# --- Main execution block ---
async def call_agent(runner: Runner, session_service: InMemorySessionService, user_input_topic: str):
    current_session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    if not current_session:
        logger.error("Session not found!"); return

    # The user's full request now goes into the 'topic' key for the router to read
    current_session.state["topic"] = user_input_topic
    logger.info(f"Updated session state topic to: {user_input_topic}")

    content = types.Content(role="user", parts=[types.Part(text=user_input_topic)])
    final_response = "No final response captured."
    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            logger.info(f"Potential final response from [{event.author}]: {event.content.parts[0].text}")
            final_response = event.content.parts[0].text

    print("\n--- Agent Interaction Result ---")
    print("Agent Final Response: ", final_response)
    final_session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    print("Final Session State:")
    print(json.dumps(final_session.state, indent=2))
    print("-------------------------------\n")

async def main():
    # Create a dictionary of our writer agents. This is crucial for the dynamic lookup.
    writer_agents_dict = {
        "story_generator": story_generator,
        "poem_generator": poem_generator,
        "screenplay_generator": screenplay_generator,
    }

    # Create the custom agent instance, passing in the router and the dictionary
    creative_writer_agent = CreativeWriterAgent(
        name="CreativeWriterAgent",
        style_router=style_router_agent,
        writer_agents=writer_agents_dict, # Pass the dictionary here
        critic=critic,
        reviser=reviser,
        grammar_check=grammar_check,
        tone_check=tone_check,
    )

    session_service = InMemorySessionService()
    # The initial state can be empty now, as the user input will populate it.
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, state={})
    runner = Runner(agent=creative_writer_agent, app_name=APP_NAME, session_service=session_service)

    # --- RUN THE DEMO ---
    # We can now make different kinds of requests!
    await call_agent(runner, session_service, "Write a short poem about a lonely robot finding a friend in a junkyard")
    await call_agent(runner, session_service, "Can you write a screenplay scene where a brave kitten explores a haunted house?")


if __name__ == "__main__":
    asyncio.run(main())