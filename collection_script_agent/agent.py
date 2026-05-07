import pathlib

from google.adk import Agent
from google.adk.code_executors.unsafe_local_code_executor import UnsafeLocalCodeExecutor
from google.adk.planners import BuiltInPlanner
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types as genai_types

from .prompts import SCRIPT_SYSTEM_PROMPT

_SKILLS_DIR = pathlib.Path(__file__).parent / "skills"

skill_toolset = SkillToolset(
    skills=[
        load_skill_from_dir(_SKILLS_DIR / "collection-report"),
        load_skill_from_dir(_SKILLS_DIR / "visit-activity"),
        load_skill_from_dir(_SKILLS_DIR / "payment"),
        load_skill_from_dir(_SKILLS_DIR / "adhoc"),
    ],
    code_executor=UnsafeLocalCodeExecutor(),
)

root_agent = Agent(
    model="gemini-3.1-flash-lite-preview",
    name="collection_script_agent",
    description=(
        "Collection operations analyst that runs skill scripts "
        "to query collection_db via MCP Toolbox."
    ),
    instruction=SCRIPT_SYSTEM_PROMPT,
    tools=[skill_toolset],
    planner=BuiltInPlanner(
        thinking_config=genai_types.ThinkingConfig(
            thinking_level=genai_types.ThinkingLevel.MINIMAL,
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
