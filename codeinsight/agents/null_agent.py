class NullAgent:
    def __init__(self, reason: str = ""):
        self.reason = reason

    def log(self, message: str):
        pass

    def generate(self, prompt: str) -> str:
        # keep behavior deterministic when AI is off
        return "LLM disabled; showing static, rule-based suggestions only."