import os

def get_agent_from_env():
    """
    Return an agent with a .generate(prompt) method based on CODEINSIGHT_AGENT.
    Supported values: "ollama", "openai", "none".
    """
    mode = (os.getenv("CODEINSIGHT_AGENT") or "ollama").lower()

    if mode == "openai":
        try:
            from .openai_agent import OpenAIAgent
            return OpenAIAgent()
        except Exception:
            from .null_agent import NullAgent
            return NullAgent(reason="OpenAI agent not available")

    if mode == "none":
        from .null_agent import NullAgent
        return NullAgent(reason="LLM disabled")

    # default: ollama (if you don’t have an Ollama agent yet, this falls back to NullAgent)
    try:
        from .ollama_agent import OllamaAgent  # optional; if you already have it
        return OllamaAgent()
    except Exception:
        from .null_agent import NullAgent
        return NullAgent(reason="Ollama agent not available; falling back")