from google.adk.agents.llm_agent import Agent
from google.adk.planners import BuiltInPlanner
from google.genai import types as genai_types

from .prompts import BASE_SYSTEM_PROMPT

root_agent = Agent(
    model='gemini-3.1-flash-lite-preview',
    name='collection_analysis_agent',
    description='Collection operations analyst. Analyzes field visits, payments, DPD aging, PTP fulfillment, and branch performance from collection_db using SQL queries. Provides insights for collection teams.',
    instruction=BASE_SYSTEM_PROMPT,
    planner=BuiltInPlanner(
        thinking_config=genai_types.ThinkingConfig(
            thinking_level=genai_types.ThinkingLevel.LOW,
            # include_thoughts=True
        )
    ),
    generate_content_config=genai_types.GenerateContentConfig(
        http_options=genai_types.HttpOptions(
            retry_options=genai_types.HttpRetryOptions(
                initial_delay=2,
                attempts=4
            )
        )
    ),
)
