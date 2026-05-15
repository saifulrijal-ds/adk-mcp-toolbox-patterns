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
from google.adk.planners import BuiltInPlanner
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google.adk.tools.toolbox_toolset import ToolboxToolset
from google.genai import types as genai_types

from .prompts import SKILL_SYSTEM_PROMPT

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
