from __future__ import annotations
import os
from typing import Optional

class OpenAIAgent:
    """
    Minimal OpenAI wrapper with .generate(prompt) compatible with your flow.
    - Reads OPENAI_API_KEY (and optional OPENAI_BASE_URL)
    - Uses Chat Completions API
    """

    def __init__(self, model: Optional[str] = None, system: Optional[str] = None):
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.system = system or "You are a senior Python reviewer."

        # Lazy import to keep your app fast & optional
        try:
            from openai import OpenAI  # fka openai>=1.x
        except Exception:
            self._client = None
            self._err = "openai SDK not installed"
            return

        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL")  # optional; leave empty for api.openai.com

        if not api_key:
            self._client = None
            self._err = "OPENAI_API_KEY is not set"
            return

        # Create client
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._err = None

    def log(self, message: str):
        # no-op hook for your flow’s logging
        pass

    def generate(self, prompt: str) -> str:
        """
        Return a short suggestion text string.
        On any configuration/API error, return a safe fallback string.
        """
        if not self._client:
            # keep the pipeline alive when the key or SDK is missing
            return "LLM unavailable; showing static suggestions."

        try:
            # Chat Completions API (stable & documented)
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            # never crash the UI
            return f"OpenAI error: {e}"