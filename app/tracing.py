import functools
import inspect
import json
from typing import Any, Callable, TypeVar, Union, overload, Awaitable
try:
    from typing import ParamSpec # Python 3.10+
except ImportError:
    from typing_extensions import ParamSpec # type: ignore

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from openinference.instrumentation.openai import OpenAIInstrumentor
from app.config import PHOENIX_LOG_URL

# Initialize global tracer provider
tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

P = ParamSpec("P")
R = TypeVar("R")

def configure_tracing():
    """
    Configures the Global Tracer Provider with OTLP exporter and 
    instruments OpenAI specifically.
    """
    span_exporter = OTLPSpanExporter(endpoint=PHOENIX_LOG_URL)
    span_processor = BatchSpanProcessor(span_exporter)
    tracer_provider.add_span_processor(span_processor)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider) # type:ignore
    print(f"Tracing configured with endpoint: {PHOENIX_LOG_URL}")

