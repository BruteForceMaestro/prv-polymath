from app.agents.researcher import ResearcherWork
from app.work import AgentWork
from typing import Optional
from app.agents.verifier_numeric import setup_executor
from app.agents.doc_ingester import ingest_document
from fastapi import FastAPI, BackgroundTasks, UploadFile, File, Form, HTTPException
from typing import Annotated
from pydantic import BaseModel
from app.agents.researcher import assign_researcher
from fastapi.middleware.cors import CORSMiddleware
from app.tracing import configure_tracing
from app.config import marker_client
from app.tracing import configure_tracing
from app.graphtools import make_graph_request
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

@app.get("/graph")
def get_graph():
    return make_graph_request(
        "/graph/query",
        body="MATCH (n) RETURN n;"
    )

current_work = ResearcherWork()

@app.post("/set_problem")
async def set_problem(request: ProblemRequest, background_tasks: BackgroundTasks):
    async def start_research():
        global current_work
        current_work = ResearcherWork() # NOTE: there is only one instance active at a time i can't be bothered with multiple instances for now.
  
        workflow = f"""
        Solve the problem:
        <problem>
        {request.problem}
        </problem>
        The recommended approach is to first formulate a sketch of the solution and proceed
        to verify your solution step by step using the graph as scaffolding, and the Lean and SymPy
        verifiers, to avoid hallucination.
        """
        
        return await assign_researcher(workflow, current_work)

    background_tasks.add_task(start_research)
    
    return {"status": "ok"}

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

        work = AgentWork()
        return await ingest_document(result.markdown, work)

@app.get("/get_status")
async def get_trace_tree():
    return current_work


if __name__ == "__main__":
    import uvicorn

    setup_executor() # threadpoolexecutor can't be inside other modules it breaks that
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
