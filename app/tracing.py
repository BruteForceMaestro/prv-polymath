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


from typing import List, Dict, Any, Optional

def build_trace_tree(spans: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Converts a flat list of OpenTelemetry spans into a hierarchical tree.
    
    Args:
        spans: A list of dictionaries, where each dict is a span 
               containing at least 'span_id', 'parent_id', and 'name'.
    """
    span_map = {span['span_id']: span for span in spans}
    root = None
    
    # Initialize 'children' list for every span
    for span in spans:
        span['children'] = []

    for span in spans:
        parent_id = span.get('parent_id')
        
        # If parent exists in our map, append this span to its children
        if parent_id and parent_id in span_map:
            span_map[parent_id]['children'].append(span)
        else:
            # If no parent_id, or parent not in this batch, it's the root
            # (In distributed traces, there might be multiple roots if incomplete, 
            # but usually one for a single request)
            root = span

    # Sort children by start_time to ensure the sequence of agent thoughts is correct
    for span in spans:
        span['children'].sort(key=lambda x: x.get('start_time', 0))

    return root if root else {}


def reconstruct_polymath_tree(raw_trace_root: Dict[str, Any]) -> List[Dict]:
    """
    Takes the full, noisy OpenTelemetry trace and reconstructs a clean
    LLM/Tool hierarchy based on nesting depth.
    """

    # --- Step 1: Flatten and Extract Interesting Nodes with Depth ---
    interesting_nodes = []

    def traverse(span: Dict[str, Any], depth: int):
        name = span.get("name", "")
        attributes = span.get("attributes", {})
        
        # Define what constitutes a "Signal" node
        is_llm = name == "ChatCompletion"
        is_tool = name.startswith("execute_tool")
        is_workflow = name in ["researcher.set_problem", "assign_researcher"]

        if is_llm or is_tool or is_workflow:
            
            # --- Data Extraction Logic ---
            node_data = {
                "id": span.get("span_id"),
                "children": [], # Initialize empty
                "depth": depth, # CRITICAL: Store the original level
                "name": name,
                "type": "unknown",
                "content": None,
                "metadata": {}
            }

            if is_llm:
                node_data["type"] = "llm"
                node_data["metadata"]["model"] = attributes.get("llm.model_name")
                # Parse the double-encoded JSON output from LLM
                raw_output = attributes.get("output.value")
                try:
                    node_data["content"] = json.loads(raw_output) if raw_output else None
                except:
                    node_data["content"] = raw_output

            elif is_tool:
                node_data["type"] = "tool"
                # Clean up tool name (remove 'execute_tool ' prefix if present)
                node_data["name"] = attributes.get("tool.name", name.replace("execute_tool ", ""))
                # Extract input args
                node_data["content"] = attributes.get("gen_ai", {}).get("tool", {}).get("call")

            elif is_workflow:
                node_data["type"] = "workflow"
                node_data["content"] = attributes.get("function", {}).get("args")

            interesting_nodes.append(node_data)

        # Recurse, increasing depth
        for child in span.get("children", []):
            traverse(child, depth + 1)

    # Run the traversal
    traverse(raw_trace_root, depth=0)

    # --- Step 2: Reconstruct Hierarchy using a Stack ---
    # We maintain a stack of nodes that are potential parents.
    
    root_nodes = []
    stack = [] # List of node objects

    for node in interesting_nodes:
        node_depth = node.pop("depth") # Remove depth from final object, we only use it here
        
        # 1. Pop the stack until we find a parent that is strictly "higher" (lower depth number)
        #    than the current node.
        while stack and stack[-1]["_temp_depth"] >= node_depth:
            stack.pop()

        # 2. Assign Parent
        if stack:
            parent = stack[-1]["node"]
            parent["children"].append(node)
        else:
            # If stack is empty, this is a top-level root
            root_nodes.append(node)

        # 3. Push current node to stack as a potential parent for future nodes
        stack.append({"node": node, "_temp_depth": node_depth})

    return root_nodes