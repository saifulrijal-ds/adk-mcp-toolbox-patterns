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
from google.adk.agents.llm_agent import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.tools.toolbox_toolset import ToolboxToolset
from google.genai import types as genai_types

from .prompts import BASE_SYSTEM_PROMPT

toolbox = ToolboxToolset(
    server_url=os.getenv("TOOLBOX_URL", "http://127.0.0.1:5002"),
)

root_agent = Agent(
    model='gemini-3.1-flash-lite',
    name='collection_analysis_agent',
    description='Collection operations analyst. Analyzes field visits, payments, DPD aging, PTP fulfillment, and branch performance from collection_db using SQL queries. Provides insights for collection teams.',
    instruction=BASE_SYSTEM_PROMPT,
    tools=[toolbox],
    planner=BuiltInPlanner(
        thinking_config=genai_types.ThinkingConfig(
            thinking_level=genai_types.ThinkingLevel.LOW,
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
