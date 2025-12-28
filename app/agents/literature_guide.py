import json
import arxiv
import requests
import html
import io
from bs4 import BeautifulSoup
from pypdf import PdfReader
from typing import List, Dict, Literal
import asyncio
from pydantic import BaseModel
from ddgs import DDGS

from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.conditions import FunctionCallTermination, TextMentionTermination
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.ui import Console
from app.config import budget_model_client
from app.work import AgentWork
from app.tracing import traced

# --- 1. SEARCH TOOLS ---

def perform_web_search(query: str) -> List[Dict]:
    """
    Searches the web using DuckDuckGo. 
    ENFORCES US-ENGLISH to avoid 'F' license plate issues.
    """
    results = []
    try:
        with DDGS() as ddgs:
            ddgs_gen = ddgs.text(
                query=query
            )
            for r in ddgs_gen:
                results.append({
                    "title": r.get('title', 'No Title'),
                    "link": r.get('href', ''),
                    "snippet": r.get('body', '')
                })
    except Exception as e:
        return [{"error": f"Search failed: {e}"}]
    return results

def search_arxiv_papers(query: str) -> str:
    """Searches ArXiv. Input should be keywords."""
    search_query = f'{query} AND (cat:math.FA OR cat:math.CO OR cat:math.GM)'
    client = arxiv.Client()
    search = arxiv.Search(query=search_query, max_results=5, sort_by=arxiv.SortCriterion.Relevance)

    results = []
    for r in client.results(search):
        results.append({
            "title": r.title,
            "authors": [a.name for a in r.authors][:3],
            "summary": r.summary.replace("\n", " ")[:300] + "...",
            "pdf_url": r.pdf_url
        })
    return json.dumps(results, indent=2)

def search_math_stackexchange(query: str) -> str:
    """Searches Math.StackExchange."""
    params = {
        "order": "desc", "sort": "relevance", "q": query, "site": "math", "filter": "withbody"
    }
    try:
        resp = requests.get("https://api.stackexchange.com/2.3/search/advanced", params=params)
        data = resp.json()
        items = []
        for item in data.get('items', [])[:4]:
            items.append({
                "title": html.unescape(item.get('title', '')),
                "link": item.get('link'),
                "preview": item.get('body', '') + "..."
            })
        return json.dumps(items, indent=2)
    except Exception as e:
        return f"Error: {e}"

PDF_CACHE = {}

def _get_reader(url: str):
    """Helper to fetch or retrieve cached PDF reader."""
    if url in PDF_CACHE:
        return PDF_CACHE[url]
    
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers, timeout=15)
    f = io.BytesIO(response.content)
    reader = PdfReader(f)
    PDF_CACHE[url] = reader
    return reader

# --- TOOLS ---

def read_url_content(url: str) -> str:
    """Fetches text from a URL, such as a website"""
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        content_type = response.headers.get('Content-Type', '').lower()
        
        if 'application/pdf' in content_type or url.endswith('.pdf'):
            with io.BytesIO(response.content) as f:
                reader = PdfReader(f)
                text = "".join([p.extract_text() for p in reader.pages[:3]]) 
                return f"--- PDF START ---\n{text[:6000]}\n--- PDF END ---"
        else:
            soup = BeautifulSoup(response.content, 'html.parser')
            text = soup.get_text(separator='\n')
            return f"--- PAGE START ---\n{text[:6000]}\n--- PAGE END ---"
    except Exception as e:
        return f"Failed: {e}"

def inspect_pdf_outline(url: str) -> str:
    """
    Step 1: Use this to see what is in the book.
    Returns the Table of Contents (if embedded) OR the first 3 pages of text.
    """
    try:
        reader = _get_reader(url)
        meta = reader.metadata
        assert meta
        info = f"Title: {meta.title}\nAuthor: {meta.author}\nTotal Pages: {len(reader.pages)}\n"
        
        # Try to extract embedded outline (bookmarks)
        outline_text = ""
        if reader.outline:
            # Simple recursive function to parse pypdf outline
            def parse_outline(outline_items, depth=0):
                text = ""
                for item in outline_items:
                    if isinstance(item, list):
                        text += parse_outline(item, depth + 1)
                    else:
                        # item.title and item.page (sometimes page is indirect)
                        prefix = "  " * depth
                        try:
                            # Note: Getting page numbers from outlines in pypdf can be tricky/indirect
                            # We'll just stick to titles for safety or catch errors
                            text += f"{prefix}- {item.title}\n" 
                        except:
                            pass
                return text
            
            outline_text = "\n--- TABLE OF CONTENTS (Embedded) ---\n" + parse_outline(reader.outline)
        
        if len(outline_text) < 50: # If outline failed or was empty
            # Fallback: Read first 3 pages where TOC usually is
            content = "\n".join([p.extract_text() for p in reader.pages[:3]])
            return f"{info}\n--- NO EMBEDDED OUTLINE DETECTED ---\nHere are the first 3 pages. Look for a TOC here:\n{content[:4000]}"
        
        return f"{info}{outline_text}"

    except Exception as e:
        return f"Failed to inspect PDF: {e}"

def search_within_pdf(url: str, keyword: str) -> str:
    """
    Step 2: Use this to find specific topics.
    Searches the whole PDF for a keyword and returns snippets with page numbers.
    """
    try:
        reader = _get_reader(url)
        results = []
        
        # Search all pages (limit to first 100 matches to save tokens)
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if keyword.lower() in text.lower():
                # Extract a snippet around the keyword
                idx = text.lower().find(keyword.lower())
                start = max(0, idx - 100)
                end = min(len(text), idx + 200)
                snippet = text[start:end].replace("\n", " ")
                results.append(f"Page {i+1}: ...{snippet}...")
                
                if len(results) >= 5: # Limit to top 5 hits
                    break
        
        if not results:
            return f"No matches found for '{keyword}' in this document."
            
        return "\n".join(results)
    except Exception as e:
        return f"Search failed: {e}"

def read_pdf_page(url: str, page_number: int) -> str:
    """
    Step 3: Use this to read the details.
    Reads a specific page number (1-indexed).
    """
    try:
        reader = _get_reader(url)
        # Convert 1-indexed (human) to 0-indexed (code)
        idx = page_number - 1
        
        if idx < 0 or idx >= len(reader.pages):
            return f"Error: Page {page_number} is out of range (1-{len(reader.pages)})."
            
        text = reader.pages[idx].extract_text()
        return f"--- CONTENT OF PAGE {page_number} ---\n{text}"
    except Exception as e:
        return f"Failed to read page: {e}"

# --- 2. SUB-TEAM ARCHITECTURE ---

class SubTaskResult(BaseModel):
    """The eventual answer submitted by a sub-team."""
    summary: str
    key_findings: str
    relevance_score: int

class Source(BaseModel):
    source_type: Literal['book', 'paper', 'forum', 'other-literature']
    title: str
    authors: list[str]
    date: str
    search_agent: Literal['arXiv', 'ddgs', 'mathexchange']

    what_to_find_from_source: str
    
class ResearchPlan(BaseModel):
    sources_to_find: List[Source]

# --- 3. AGENT FACTORIES ---

def create_reviewer_agent(model_client):
    """
    A generic critic that ensures the worker keeps trying until they get a result
    or exhaust options.
    """
    return AssistantAgent(
        name="Reviewer",
        model_client=model_client,
        system_message=(
            "You are a Research QA Specialist. "
            "1. Review the worker's findings. "
            "2. If the worker returns empty searches or errors, suggest a new keyword or approach. "
            "3. Do not allow the worker to give up immediately. "
            "4. Once useful information is found, direct the worker to call `finish_subtask`."
        )
    )

def create_arxiv_worker(model_client, finish_subtask):
    return AssistantAgent(
        name="PDF_Navigator",
        model_client=model_client,
        system_message="""
        You are a Researcher with access to arXiv API. 
        You will use this API to find and retrieve information from relevant sources to the query.
        
        # Handling PDFS
        When you find a relevant PDF/Book:
        1. Call `inspect_pdf_outline` first to understand the structure or find the TOC.
        2. Based on the TOC, decide which chapters/pages sound relevant.
        3. If no TOC is clear, use `search_within_pdf` to find keywords (e.g., "Theorem 2.1", "Proof").
        4. Finally, use `read_pdf_page` to read the actual content of those specific pages.
        
        Do NOT try to read the whole book at once.

        # Submitting the final report
        After reading enough of the literature to compile comprehensive information, use the 
        `submit_answer` tool to turn in your report.
        """,
        # Register the new tools
        tools=[search_arxiv_papers, inspect_pdf_outline, search_within_pdf, read_pdf_page, finish_subtask] 
    )

def create_web_worker(model_client, finish_subtask):
    return AssistantAgent(
        name="Web_Worker",
        model_client=model_client,
        system_message="""
        # Handling web pages
        Use the `read_url_content` tool.

        # Handling PDFS
        When you find a relevant PDF/Book:
        1. Call `inspect_pdf_outline` first to understand the structure or find the TOC.
        2. Based on the TOC, decide which chapters/pages sound relevant.
        3. If no TOC is clear, use `search_within_pdf` to find keywords (e.g., "Theorem 2.1", "Proof").
        4. Finally, use `read_pdf_page` to read the actual content of those specific pages.
        
        Do NOT try to read the whole book at once.

        # Submitting the final report
        After reading enough of the literature to compile comprehensive information, use the 
        `submit_answer` tool to turn in your report.
        """,
        tools=[perform_web_search, inspect_pdf_outline, search_within_pdf, read_pdf_page, read_url_content, finish_subtask]
    )

def create_forum_worker(model_client, finish_subtask):
    return AssistantAgent(
        name="Forum_Worker",
        model_client=model_client,
        system_message="""
        You are a Researcher with access to StackExchange API. 
        You will use this API to find and retrieve information from relevant sources to the query.
        
        # Submitting the final report
        After reading enough of the literature to compile comprehensive information, use the 
        `submit_answer` tool to turn in your report.
        """,
        tools=[search_math_stackexchange, finish_subtask]
    )

# --- 4. ORCHESTRATOR ---

async def execute_research_plan(plan: ResearchPlan) -> str:
    """
    Orchestrator tool. 
    Call this tool to fan-out, so that each sub agent can work on one source 
    concurrently.
    """
    print(f"\n[ORCHESTRATOR] Received plan with {len(plan.sources_to_find)} tasks. Fanning out...\n")
    
    semaphore = asyncio.Semaphore(5) 

    async def run_sub_team_task(i: int, task) -> str:
        """Helper function to run a single sub-team in isolation."""
        async with semaphore:
            print(f"--> Spawning Sub-Team for Task {i+1}: {task.source_type}")
            
            # Create a localized work container for this specific task
            work = AgentWork()
            
            # 1. Define the Sub-Team Members
            worker = None
            if task.search_agent == "arXiv":
                worker = create_arxiv_worker(budget_model_client, work.submit_answer)
            elif task.search_agent == "ddgs":
                worker = create_web_worker(budget_model_client, work.submit_answer)
            elif task.search_agent == "mathexchange":
                worker = create_forum_worker(budget_model_client, work.submit_answer)
            
            if not worker:
                return f"Error: Unknown agent type {task.search_agent}"

            # 2. Create the Nested Group Chat
            sub_team = RoundRobinGroupChat(
                [worker],
                termination_condition=FunctionCallTermination("submit_answer")
            )

            task_prompt = (
                f"Retrieve this source, and from it, information regarding 'what_to_find_from_source': {task.model_dump_json()}. "
                "If search fails, try variations. "
                "Call `submit_answer` ONLY when you have are done with the task, and further exploration does not seem to bring much benefit.."
            )
            
            # Run the team. Note: Console output will interleave if running locally.
            await Console(sub_team.run_stream(task=task_prompt))
            
            return f"--- RESULT FOR {task.title} ---\n{work.result}\n"

    # Create a list of coroutine objects
    tasks = [
        run_sub_team_task(i, task) 
        for i, task in enumerate(plan.sources_to_find)
    ]

    # Execute all tasks concurrently and wait for all to complete
    results = await asyncio.gather(*tasks)

    # Aggregate all sub-team results for the Lead Researcher
    return f"COMPLETED RESEARCH TASKS.\n\n" + "\n".join(results)

# --- 5. MAIN ENTRY POINT ---

@traced
async def research_literature(task: str):
    
    lead_agent_sys = """
    You are the Principal Investigator.
    Your goal is to answer the user's math problem by gathering literature.

    HOW TO WORK:
    1. Analyze the user's request.
    2. Break it down into specific, REAL sources (books, papers, etc.) to search. 
    3. CALL `execute_research_plan` with this list. 
       (Note: This will spawn sub-teams of agents to do the work).
    4. Synthesize the final answer based on the returned reports.
    5. Submit the final result using `submit_answer`.
    """

    work = AgentWork()

    lead_agent = AssistantAgent(
        name="Lead_Researcher",
        model_client=budget_model_client,
        system_message=lead_agent_sys,
        # The Lead ONLY sees the high-level tools
        tools=[execute_research_plan, work.submit_answer] 
    )

    # Top-Level Team
    team = RoundRobinGroupChat(
        [lead_agent],
        termination_condition=FunctionCallTermination("submit_answer")
    )

    await Console(team.run_stream(task=f"Find theorems and methods for: {task}"))
    
    return work.result