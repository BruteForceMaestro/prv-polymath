from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from app.agents.researcher import assign_researcher
from fastapi.middleware.cors import CORSMiddleware
from phoenix.otel import register

# This one line handles the TracerProvider, Exporter, and Auto-instrumentation
tracer_provider = register(
    project_name="autogen-research-agent",
    endpoint="http://localhost:4317", # Points to your docker container
    auto_instrument=True
)


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

@app.post("/set_problem")
async def set_problem(request: ProblemRequest, background_tasks: BackgroundTasks):

    async def start_research():
        return await assign_researcher(request.problem)

    background_tasks.add_task(start_research)
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=True)
