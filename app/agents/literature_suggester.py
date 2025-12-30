from app.tracing import traced
from typing import List, Dict, Literal
from ddgs import DDGS
import arxiv
import json
from pydantic import BaseModel
from app.work import AgentWork
from autogen_agentchat.agents import AssistantAgent
from app.groupchats.nudge import NudgeGroupChat
from app.agents.deterministic_nudger import DeterministicNudgeAgent
from autogen_agentchat.conditions import FunctionCallTermination
from app.config import budget_model_client
from autogen_agentchat.ui import Console


def perform_web_search(query: str) -> List[Dict]:
    """
    Searches the web using DuckDuckGo.
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
    """Searches ArXiv."""
    search_query = f'{query} AND (cat:math.FA OR cat:math.CO OR cat:math.GM)'
    client = arxiv.Client()
    search = arxiv.Search(query=search_query, max_results=5, sort_by=arxiv.SortCriterion.Relevance)

    results = []
    for r in client.results(search):
        results.append({
            "title": r.title,
            "authors": [a.name for a in r.authors][:3],
            "summary": r.summary.replace("\n", " "),
            "pdf_url": r.pdf_url
        })
    return json.dumps(results, indent=2)


class Source(BaseModel):
    src_type: Literal['book', 'paper', 'other']
    title: str
    author: list[str]
    pdf_link: str
    relevance_to_research: str

class LiteratureSuggesterWork(AgentWork):
    def submit_lit_suggestions(self, suggested_sources: list[Source]):
        """Suggest to the user the sources to review regarding the topic, that could help them with their research."""
        res_str = "Suggested sources: \n"
        for i, src in enumerate(suggested_sources):
            res_str += f"\nSource {i+1}: {src.model_dump_json()}"
        self.result = res_str

literature_suggester_sys = """
# Identity
You are a literature suggester. In a response to a query, if a research topic is given, 
your task is to suggest possible sources or literature that could be useful in solving 
a certain problem.

# Tools
Importantly, you don't actually have access to reading papers or opening websites,
only the arXiv abstract or the web snippets.
## Search
Search tools are crucial to find literature to suggest.
1. `perform_web_search`: this queries the Duck Duck Go engine to search a query that you input.
2. `search_arxiv_papers`: to find the academic literature on the topic, uses arXiv API.
## Submission
To submit your helpful literature suggestions to the user, use the `submit_lit_suggestions` tool. 

"""

@traced
async def suggest_literature(task: str):
    work = LiteratureSuggesterWork()

    agent = AssistantAgent(
        name="Literature_Suggester",
        model_client=budget_model_client,
        tools=[search_arxiv_papers, perform_web_search, work.submit_lit_suggestions],
        system_message=literature_suggester_sys
    )

    nudge = DeterministicNudgeAgent(
        name="NudgeBot",
        message_content="You seem to be looping. Please evaluate your progress and use the 'submit_lit_suggestions' tool if you are finished."
    )

    team = NudgeGroupChat(
        [agent, nudge],
        termination_condition=FunctionCallTermination("submit_lit_suggestions")
    )

    await Console(team.run_stream(task=f"Suggest literature sources, that could be useful in solving this problem: {task}"))

    return work.result