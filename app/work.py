
class AgentWork:
    def __init__(self):
        self.result = None
    
    def submit_answer(self, report: str) -> str:
        """Use this tool to submit your final answer."""
        self.result = report
        return "Submitted."
