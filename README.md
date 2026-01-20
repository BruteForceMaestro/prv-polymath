# Private Polymath (prv-polymath)

**Private Polymath** is an advanced multi-agent research and reasoning system designed to solve complex mathematical and scientific problems. It leverages a graph-based architecture, specialized agents (Researcher, Verifiers), and a robust observability stack to ensure accuracy and minimize hallucinations.

## Key Features

- **Multi-Agent Architecture**: Orchestrates specialized agents for research, numeric verification, and formal verification (Lean).
- **Graph-Based Reasoning**: Uses a Neo4j database to structure knowledge and solution steps as a graph, preventing circular reasoning and enabling step-by-step verification.
- **Formal Verification**: Integrates with a Lean 4 server to formally verify mathematical statements.
- **Observability**: Full tracing and logging via Arize Phoenix to debug agent interactions and performance.
- **Document Ingestion**: Capable of ingesting PDF documents using the Datalab SDK/Marker for context-aware problem solving.

## Architecture Overview

- **Frontend/API**: FastAPI application serving as the central orchestration layer.
- **Database**: Neo4j (Graph DB) for storing verification trees and knowledge.
- **AI Models**: Powered by OpenAI's GPT-series models (configurable).
- **Tooling**:
    - **Lean Server**: A dedicated container for running Lean 4 verification.
    - **Phoenix**: For trace visualization and evaluation.

## Prerequisites

- **Python 3.13+**
- **Docker & Docker Compose**
- **Neo4j** (Expected to be running locally or accessible via URL)
- **uv** (Recommended for dependency management)

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/yourusername/prv-polymath.git
    cd prv-polymath
    ```

2.  **Install dependencies**:
    Using `uv` (recommended):
    ```bash
    uv sync
    ```
    Or using standard pip:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Configuration**:
    Create a `.env` file in the root directory (copy from `.env.example` if available, otherwise set these):
    ```env
    OPENAI_API_KEY=sk-...
    POLYMATH_API_KEY=your_key_here
    DATALAB_API_KEY=your_datalab_key
    
    # Defaults
    POLYMATH_SERVER_URL=http://localhost:8080
    PHOENIX_LOG_URL=http://localhost:4317
    PHOENIX_RETRIEVE_URL=http://localhost:6006
    ENVIRONMENT=dev
    LEAN_SERVER_PORT=8081
    ```

## Running the Application

1.  **Start Infrastructure Services**:
    Run Docker Compose to start the Arize Phoenix observability server and the Lean verification server.
    ```bash
    docker-compose up -d
    ```
    - Phoenix UI: [http://localhost:6006](http://localhost:6006)
    - Lean Server: [http://localhost:8081](http://localhost:8081)

2.  **Start the Main Application**:
    ```bash
    uv run python -m app.main
    ```
    *Or with uvicorn directly:*
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
    ```

3.  **Access the API**:
    The API documentation (Swagger UI) is available at:
    [http://localhost:8080/docs](http://localhost:8080/docs)

## Usage

### Submit a Problem
You can submit a research problem using the `/set_problem` endpoint.

```bash
curl -X 'POST' \
  'http://localhost:8080/set_problem' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "problem": "Prove that for all integers n, if n is oven, then n^2 is even.",
  "use_lit_review": false
}'
```

### Check Status
Get the current status of the researcher agent:

```bash
curl -X 'GET' \
  'http://localhost:8080/get_status' \
  -H 'accept: application/json'
```

## Testing

Run the test suite using `pytest`:

```bash
uv run pytest
```
