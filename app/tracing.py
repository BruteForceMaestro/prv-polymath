import functools
import inspect
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

# Initialize global tracer provider
tracer_provider = TracerProvider()
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer(__name__)

P = ParamSpec("P")
R = TypeVar("R")

def configure_tracing(endpoint: str = "http://localhost:4317"):
    """
    Configures the Global Tracer Provider with OTLP exporter and 
    instruments OpenAI specifically.
    """
    span_exporter = OTLPSpanExporter(endpoint=endpoint)
    span_processor = BatchSpanProcessor(span_exporter)
    tracer_provider.add_span_processor(span_processor)
    OpenAIInstrumentor().instrument(tracer_provider=tracer_provider) # type:ignore
    print(f"Tracing configured with endpoint: {endpoint}")

from typing import Any, Callable, TypeVar, overload, Awaitable

# F represents any callable (sync or async)
F = TypeVar("F", bound=Callable[..., Any])

@overload
def traced(
    func: None = None, 
    *, 
    name: str | None = None, 
    kind: trace.SpanKind = trace.SpanKind.INTERNAL
) -> Callable[[F], F]: ...

@overload
def traced(
    func: F, 
    *, 
    name: str | None = None, 
    kind: trace.SpanKind = trace.SpanKind.INTERNAL
) -> F: ...

def traced(
    func: Any = None, 
    *, 
    name: str | None = None, 
    kind: trace.SpanKind = trace.SpanKind.INTERNAL
) -> Any:
    """
    Decorator to trace a function execution. 
    Preserves signature via TypeVar 'F' to satisfy linters like Pyrefly.
    """
    if func is None:
        return functools.partial(traced, name=name, kind=kind)

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        span_name = name or func.__name__
        with tracer.start_as_current_span(span_name, kind=kind) as span:
            span.set_attribute("function.name", func.__name__)
            span.set_attribute("function.args", str(args))
            span.set_attribute("function.kwargs", str(kwargs))
            try:
                result = await func(*args, **kwargs)
                span.set_attribute("function.result", str(result))
                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise e

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        span_name = name or func.__name__
        with tracer.start_as_current_span(span_name, kind=kind) as span:
            span.set_attribute("function.name", func.__name__)
            span.set_attribute("function.args", str(args))
            span.set_attribute("function.kwargs", str(kwargs))
            try:
                result = func(*args, **kwargs)
                span.set_attribute("function.result", str(result))
                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR))
                raise e

    # Runtime dispatch based on inspect
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper