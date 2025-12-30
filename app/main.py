from typing import Optional
from app.agents.verifier_numeric import setup_executor
from app.agents.doc_ingester import ingest_document
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException
from typing import Annotated
from pydantic import BaseModel
from app.agents.researcher import assign_researcher
from fastapi.middleware.cors import CORSMiddleware
from app.tracing import configure_tracing
from app.config import marker_client, px_client
from app.tracing import configure_tracing, tracer, build_trace_tree, reconstruct_polymath_tree
from opentelemetry import trace, context
import tempfile
import shutil
import numpy as np

configure_tracing()


app = FastAPI()
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,            # Or use ["*"] for total anarchy (local dev only)
    allow_credentials=True,
    allow_methods=["*"],              # Allows POST, GET, OPTIONS, etc.
    allow_headers=["*"],              # Allows Content-Type, Authorization, etc.
)

class ProblemRequest(BaseModel):
    problem: str
    use_lit_review: bool

@app.post("/set_problem")
async def set_problem(request: ProblemRequest, background_tasks: BackgroundTasks):
    span = tracer.start_span("researcher.set_problem")
    ctx = trace.set_span_in_context(span)
    trace_id = f"{span.get_span_context().trace_id:032x}"

    async def start_research():
        token = context.attach(ctx)
        try:
            workflow = f"""
        Solve the problem:
        <problem>
        {request.problem}
        </problem>
        The recommended approach is to first formulate a sketch of the solution and proceed
        to verify your solution step by step using the graph as scaffolding, and the Lean and SymPy
        verifiers, to avoid hallucination.
        """
            return await assign_researcher(workflow)
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise e
        finally:
            span.end()
            context.detach(token)

    background_tasks.add_task(start_research)
    
    return {"status": "ok", "trace_id": trace_id}

@app.post("/upload_doc")
async def upload_document(
    file: UploadFile = File(...)
):
    """Upload a document into the shared graph (not stored on the backend)"""
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_path:
        shutil.copyfileobj(file.file, tmp_path)
        tmp_path.flush()

        result = await marker_client.convert(tmp_path.name)
        assert result.markdown
        await ingest_document(result.markdown)

@app.get("/trace/{trace_id}")
async def get_trace_tree(trace_id: str):
    try:
        
        df = px_client.spans.get_spans_dataframe()
        if df.empty:
            raise HTTPException(status_code=404, detail="Phoenix storage is empty.")

        # 2. Filter by Trace ID
        # Your schema uses 'context.trace_id'
        trace_df = df[df['context.trace_id'] == trace_id].copy()

        if trace_df.empty:
            raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found.")

        # 3. Clean Data for JSON Serialization
        # Pandas NaNs break FastAPI JSON response, replace with None
        trace_df = trace_df.replace({np.nan: None})

        # 4. Map Dataframe Rows to Clean Dicts
        clean_spans = []
        
        # We iterate over the filtered dataframe
        for _, row in trace_df.iterrows():
            
            # Collect all 'attributes.*' columns into a nested dictionary
            # This keeps your main node clean but preserves all agent data (inputs/outputs/tokens)
            attributes = {}
            for col in trace_df.columns:
                if col.startswith("attributes."):
                    # Remove prefix for cleaner JSON keys: 'attributes.input.value' -> 'input.value'
                    key = col.replace("attributes.", "")
                    val = row[col]
                    if val is not None:
                        attributes[key] = val

            span_obj = {
                # Core Identity
                "span_id": row.get("context.span_id"),
                "parent_id": row.get("parent_id"),
                "trace_id": row.get("context.trace_id"),
                "name": row.get("name"),
                
                # Timing (Convert timestamps to string if they are datetime objects)
                "start_time": str(row.get("start_time")),
                "end_time": str(row.get("end_time")),
                
                # Status
                "status_code": row.get("status_code"),
                "status_message": row.get("status_message"),
                
                # The Payload (Your AutoGen messages, LLM inputs, etc.)
                "attributes": attributes
            }
            clean_spans.append(span_obj)

        # 5. Build Tree
        tree = build_trace_tree(clean_spans)

        # 6. clean up to get the semantic tree
        clean_tree = reconstruct_polymath_tree(tree)
        
        return clean_tree

    except Exception as e:
        # In production, log this error
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    setup_executor() # threadpoolexecutor can't be inside other modules it breaks that
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
