# Private Polymath (prv-polymath)

**Private Polymath** is an advanced multi-agent research and reasoning system designed to solve complex mathematical and scientific problems. It leverages a graph-based architecture, specialized agents (Researcher, Verifiers), and a robust observability stack to ensure accuracy and minimize hallucinations.

It is an implementation of an AI agent to test human-AI collaboration capabilities scaffolded on the graph of Polymath Server, with all of its protocols.

## Prerequisites
- **Python 3.13+**
- **Docker & Docker Compose**
- **Neo4j** (Expected to be running locally or accessible via URL)
- **uv** (Recommended for dependency management)
- [polymath-server](https://github.com/BruteForceMaestro/polymath-server) installed and running, typically via Docker.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/BruteForceMaestro/prv-polymath.git
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
    Create a `.env` file in the root directory (copy from `.env.example`)

## Running the Application

0. **Have Polymath Server up**
    If not installed already, clone [polymath-server](https://github.com/BruteForceMaestro/polymath-server) repo, and use `docker compose up` to run the polymath server, which contains the graph database and so forth. However, soon this step may be unnecessary as I may host the polymath server globally.

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
The GUI interface for this agent can be found at [polymath-ui](https://github.com/BruteForceMaestro/polymath-ui). Otherwise, one can use curl and/or test setups in the tests folder. 
