import os
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from openinference.instrumentation.google_adk import GoogleADKInstrumentor

import mlflow

# --- MLflow config ---
# Set up the experiment
MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
mlflow.set_tracking_uri(MLFLOW_URI)
experiment = mlflow.set_experiment("adk-sql-agent")
EXPERIMENT_ID = experiment.experiment_id

mlflow_exporter = OTLPSpanExporter(
    endpoint= f"{MLFLOW_URI.rstrip('/')}/v1/traces",
    headers={'x-mlflow-experiment-id': EXPERIMENT_ID}
)

# # --- Phoenix Cloud config ---
# PHOENIX_API_KEY=os.environ.get("PHOENIX_API_KEY")
# PHOENIX_COLLECTOR_ENDPOINT=os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")

# phenix_exporter = OTLPSpanExporter(
#     endpoint=PHOENIX_COLLECTOR_ENDPOINT,
#     headers={"api_key": PHOENIX_API_KEY}
# )


# --- Single provider, two processor ---
provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(mlflow_exporter))
# provider.add_span_processor(BatchSpanProcessor(phenix_exporter))

trace.set_tracer_provider(provider)

GoogleADKInstrumentor().instrument(tracer_provider=provider)

import os
import pathlib

from google.adk.agents.llm_agent import Agent
from google.adk.agents.invocation_context import EventsCompactionConfig
from google.adk.apps import App
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.toolbox_toolset import ToolboxToolset
from google.genai import types as genai_types

from .prompts import SKILL_SYSTEM_PROMPT
from collection_analysis_agent.planners import TaskToDoPlanner
from shared.memory_tools import (
    remember_query_correction,
    remember_preference,
    remember_schema_discovery,
    remember_term,
    remember_failed_pattern,
    recall_corrections,
)
from shared.callbacks import memory_extraction_callback

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
    model="gemini-3.1-flash-lite",
    name="collection_skill_agent",
    description=(
        "Collection operations analyst with skill-guided discovery. "
        "Uses SkillToolset for domain instructions and ToolboxToolset for execution."
    ),
    instruction=SKILL_SYSTEM_PROMPT,
    tools=[
        skill_toolset,
        remember_query_correction,
        remember_preference,
        remember_schema_discovery,
        remember_term,
        remember_failed_pattern,
        recall_corrections,
    ],
    after_agent_callback=memory_extraction_callback,
    planner=TaskToDoPlanner(
        thinking_config=genai_types.ThinkingConfig(
            include_thoughts=True,
            thinking_level="low",
        ),
        domain_hint="collection operations with skill-guided discovery",
    ),
    generate_content_config=genai_types.GenerateContentConfig(
        thinking_config=None,  # Set to None when use planner
        http_options=genai_types.HttpOptions(
            retry_options=genai_types.HttpRetryOptions(
                initial_delay=2,
                attempts=4
            )
        )
    ),
)

app = App(
    name="collection_skill_agent",
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=10,    # Compact every 10 turns
        overlap_size=2,            # Keep last 2 turns before compacting
        token_threshold=4000,      # Trigger at 4k tokens
        event_retention_size=1000, # Retain up to 1000 events
    ),
)
