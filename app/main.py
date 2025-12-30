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
import tempfile
import shutil


# Configure custom tracing
# Configure custom tracing
configure_tracing(endpoint="http://localhost:4317")


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

    async def start_research():
        workflow = f"""
        Solve the problem with the following workflow, utilizing your tools:
        1. Check the graph for previous findings
        2. Research literature if the axioms of the graph don't appear to be enough to solve the proof
        3. Decision point: Is the problem simple enough to be solved by you alone? 
            -  If yes, proceed to solve in a message, but do not submit
            -  If no, proceed to use divide and conquer with subagents solving parts of the problem
        4. After a solution proposition is composed, proceed to map the parts of the solution to the graph via Statements and Implications
        5. Try to verify every Implication of the graph with Verifiers (Lean and SymPy/numeric).

        The ultimate goal is solve this problem:
        <problem>
        {request.problem}
        </problem>,
        while maintaining graph scaffolding and verification for hallucination elimination.
        """
        return await assign_researcher(workflow)

    background_tasks.add_task(start_research)

    # TODO; add thing to track progress of the thing in a streamin' way
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
        await ingest_document(result.markdown)

if __name__ == "__main__":
    import uvicorn

    setup_executor() # threadpoolexecutor can't be inside other modules it breaks that
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
