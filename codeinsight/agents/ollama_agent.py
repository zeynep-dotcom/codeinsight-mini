import requests

class OllamaAgent:
    """provides .generate(prompt) so step_llm_refactor can call it"""

    def __init__(self, model: str = "llama3.1:8b-instruct", host: str = "http://localhost:11434"):
        self.model = model
        self.url = f"{host}/api/generate"

    def generate(self, prompt: str) -> str:
        try:
            resp = requests.post(
                self.url,
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "").strip()
        except Exception as e:
            return f"LLM error: {e}"

    def log(self, msg: str) -> None:
        # no-op just for compatibility
        print(f"[OllamaAgent] {msg}")