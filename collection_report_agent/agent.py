import os
import pathlib

from google.adk.agents.llm_agent import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.toolbox_toolset import ToolboxToolset
from google.genai import types as genai_types

from .prompts import REPORT_SYSTEM_PROMPT

_SKILLS_DIR = pathlib.Path(__file__).parent / "skills"

toolbox = ToolboxToolset(
    server_url=os.getenv("TOOLBOX_URL", "http://127.0.0.1:5002"),
)

skill_toolset = SkillToolset(
    skills=[
        load_skill_from_dir(_SKILLS_DIR / "collection-report"),
        load_skill_from_dir(_SKILLS_DIR / "visit-activity"),
        load_skill_from_dir(_SKILLS_DIR / "payment"),
        load_skill_from_dir(_SKILLS_DIR / "adhoc"),
    ],
    additional_tools=[toolbox],
)

root_agent = Agent(
    model="gemini-3.1-flash-lite-preview",
    name="collection_report_agent",
    description=(
        "Collection operations analyst with skill-guided discovery. "
        "Uses SkillToolset for domain instructions and ToolboxToolset for execution."
    ),
    instruction=REPORT_SYSTEM_PROMPT,
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
