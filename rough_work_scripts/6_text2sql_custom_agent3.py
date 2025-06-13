import logging
import asyncio
import json
import sqlite3
from typing import AsyncGenerator, Dict, Any

from google.adk.agents import LlmAgent, BaseAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.adk.events import Event, EventActions

# --- Constants & Logging ---
APP_NAME = "text2sql_app"
USER_ID = "user_sql"
GEMINI_2_FLASH = "gemini-2.0-flash"
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- 1. Database Setup ---
def setup_database():
    """Creates an in-memory SQLite DB, populates it, and returns the schema string."""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT NOT NULL);")
    cursor.execute("CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT NOT NULL, department_id INTEGER, FOREIGN KEY (department_id) REFERENCES departments (id));")
    cursor.execute("INSERT INTO departments (id, name) VALUES (1, 'Engineering'), (2, 'Human Resources');")
    cursor.execute("INSERT INTO employees (name, department_id) VALUES ('Alice', 1), ('Bob', 1), ('Charlie', 2);")
    conn.commit()
    schema = "\n".join([row[0] for row in cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';").fetchall()])
    logger.info(f"Database setup complete. Schema:\n{schema}")
    return conn, schema


# --- 2. Core Text-to-SQL Agents ---
sql_generator_agent = LlmAgent(
    name="SqlGenerator", model=GEMINI_2_FLASH,
    instruction="""You are an expert SQL writer. Based on the provided database schema and user question, write an SQL query. You MUST also provide a brief, step-by-step reasoning. If you are given feedback on a previous attempt, use it to correct your query.
DATABASE SCHEMA: {db_schema}
USER QUESTION: {user_question}
PREVIOUS ATTEMPT FEEDBACK (if any): {feedback}
Your output MUST be a JSON object with two keys: "sql" and "reasoning".
Example: {"sql": "SELECT * FROM employees;", "reasoning": "Selected all columns from the employees table."}""",
    output_key="generated_sql_and_reasoning",
)

sql_reviewer_agent = LlmAgent(
    name="SqlReviewer", model=GEMINI_2_FLASH,
    instruction="""You are an expert SQL reviewer. Your task is to validate an SQL query against a user's question and the database schema.
DATABASE SCHEMA: {db_schema}
USER QUESTION: {user_question}
GENERATED OBJECT TO REVIEW: {generated_sql_and_reasoning}
Review the 'sql' key within the generated object. If the query is correct and accurately answers the question, respond with a JSON object: {"verdict": "correct", "feedback": "The query is correct."}
If incorrect, respond with a JSON object containing a "verdict" of "incorrect" and "feedback" explaining the error and suggesting a fix.
Example Incorrect: {"verdict": "incorrect", "feedback": "The query uses a non-existent column 'emp_name'. It should be 'name'."}""",
    output_key="review_result",
)


# --- 3. Loop-Stopping and Tool Agents ---
class SqlReviewStopChecker(BaseAgent):
    """Checks the reviewer's verdict and escalates to stop the loop if correct."""
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        review_str = ctx.session.state.get("review_result", "{}")
        try:
            review = json.loads(review_str)
            verdict = review.get("verdict", "incorrect")
            should_stop = (verdict == "correct")
            logger.info(f"[{self.name}] Verdict is '{verdict}'. Escalating to stop loop: {should_stop}")
            yield Event(author=self.name, actions=EventActions(escalate=should_stop))
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"[{self.name}] Could not parse review result. Not stopping loop.")
            yield Event(author=self.name, actions=EventActions(escalate=False))

class SqlExecutorAgent(BaseAgent):
    """A custom agent to execute SQL queries against the database."""
    db_connection: Any
    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        final_obj = json.loads(ctx.session.state.get("generated_sql_and_reasoning", "{}"))
        sql_to_run = final_obj.get("sql")
        logger.info(f"[{self.name}] Executing SQL: {sql_to_run}")
        try:
            cursor = self.db_connection.cursor()
            results = cursor.execute(sql_to_run).fetchall()
            col_names = [description[0] for description in cursor.description]
            ctx.session.state["query_execution_result"] = [dict(zip(col_names, row)) for row in results]
            logger.info(f"[{self.name}] Execution successful.")
        except Exception as e:
            ctx.session.state["query_execution_result"] = f"SQL execution failed: {e}"
            logger.error(f"[{self.name}] {ctx.session.state['query_execution_result']}")
        if False:
            yield


# --- 4. The Text-to-SQL Orchestrator ---
class TextToSqlAgent(BaseAgent):
    """Orchestrates the generate-review loop and final execution."""
    refinement_loop: LoopAgent
    sql_executor: SqlExecutorAgent
    model_config = {"arbitrary_types_allowed": True}

    def __init__(self, name: str, sql_generator: LlmAgent, sql_reviewer: LlmAgent, sql_executor: SqlExecutorAgent, **_kwargs):
        refinement_loop = LoopAgent(
            name="SqlRefinementLoop",
            max_iterations=3,
            sub_agents=[
                sql_generator,
                sql_reviewer,
                SqlReviewStopChecker(name="StopChecker")
            ]
        )
        super().__init__(
            name=name,
            refinement_loop=refinement_loop,
            sql_executor=sql_executor,
            sub_agents=[refinement_loop, sql_executor]
        )

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        ctx.session.state["feedback"] = "No feedback yet. This is the first attempt."
        async for event in self.refinement_loop.run_async(ctx):
            yield event

        final_review = json.loads(ctx.session.state.get("review_result", "{}"))
        if final_review.get("verdict") != "correct":
            yield Event.final_response(self.name, "I could not generate a correct SQL query after several attempts.")
            return

        async for event in self.sql_executor.run_async(ctx):
            yield event

        final_obj = json.loads(ctx.session.state.get("generated_sql_and_reasoning", "{}"))
        final_result = (
            f"Here is the result for your query:\n\n"
            f"**Query Result:**\n```json\n{json.dumps(ctx.session.state.get('query_execution_result'), indent=2)}\n```\n\n"
            f"**Generated SQL:**\n```sql\n{final_obj.get('sql')}\n```\n\n"
            f"**Reasoning:**\n{final_obj.get('reasoning')}"
        )
        yield Event.final_response(self.name, final_result)


# --- 5. The Top-Level Router ---
class MainRouterAgent(BaseAgent):
    """Determines user intent and routes to the correct sub-agent."""
    intent_router: LlmAgent
    text_to_sql_agent: TextToSqlAgent
    chat_agent: LlmAgent
    model_config = {"arbitrary_types_allowed": True}

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        async for event in self.intent_router.run_async(ctx): yield event
        intent = ctx.session.state.get("intent")
        agent_to_run = self.text_to_sql_agent if intent == "sql_query" else self.chat_agent
        logger.info(f"[{self.name}] Intent is '{intent}'. Routing to {agent_to_run.name}.")
        async for event in agent_to_run.run_async(ctx): yield event


# --- Main execution block (CORRECTED) ---
# CORRECTED: Function signature now accepts db_schema
async def call_agent(runner: Runner, session_service: InMemorySessionService, user_input: str, db_schema: str):
    session_id = f"session_{hash(user_input)}"
    # CORRECTED: db_schema is now passed into the state of each new session.
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=session_id,
        state={"user_question": user_input, "db_schema": db_schema}
    )

    logger.info(f"\n--- Calling Agent with Input: '{user_input}' ---")
    content = types.Content(role="user", parts=[types.Part(text=user_input)])
    async for event in runner.run_async(user_id=USER_ID, session_id=session_id, new_message=content):
        if event.is_final_response():
            print("\n--- Agent Final Response ---")
            print(event.content.parts[0].text.strip())
            print("--------------------------\n")

async def main():
    db_conn, db_schema = setup_database()
    intent_router = LlmAgent(name="IntentRouter", model=GEMINI_2_FLASH, instruction="You are an intent router. Read the user question. If it's about querying data, getting counts, or asking about the database, output 'sql_query'. Otherwise, output 'general_chat'. User question: {user_question}", output_key="intent")
    chat_agent = LlmAgent(name="ChatAgent", model=GEMINI_2_FLASH, instruction="You are a helpful assistant. Respond to the user's question: {user_question}")

    text_to_sql_flow = TextToSqlAgent(
        name="TextToSqlAgent",
        sql_generator=sql_generator_agent,
        sql_reviewer=sql_reviewer_agent,
        sql_executor=SqlExecutorAgent(name="SqlExecutor", db_connection=db_conn)
    )

    main_router = MainRouterAgent(name="MainRouter", intent_router=intent_router, text_to_sql_agent=text_to_sql_flow, chat_agent=chat_agent, sub_agents=[intent_router, text_to_sql_flow, chat_agent])

    session_service = InMemorySessionService()
    # REMOVED: The incorrect update_app_state call is gone.
    runner = Runner(agent=main_router, app_name=APP_NAME, session_service=session_service)

    # CORRECTED: Pass db_schema to each call_agent invocation.
    await call_agent(runner, session_service, "How many employees are in the Engineering department?", db_schema)
    await call_agent(runner, session_service, "Hi, who are you?", db_schema)
    await call_agent(runner, session_service, "List all department names.", db_schema)

    db_conn.close()

if __name__ == "__main__":
    asyncio.run(main())