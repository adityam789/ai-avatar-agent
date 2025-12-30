import os
import requests

try:
    # optional dependency: if python-dotenv is installed, load .env automatically
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv not installed or failed to load; fall back to environment variables
    pass


class LLMClient:
    def __init__(self, model: str = "meta-llama/llama-3.3-70b-instruct:free"):
        """Lightweight client for OpenRouter-compatible chat completions."""
        self.model = model
        self.url = "https://openrouter.ai/api/v1/chat/completions"

    def __call__(self, prompt: str) -> str:
        api_key = os.getenv("OPEN_ROUTER_API_KEY", "")

        headers = {
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json",
        }

        # Optional headers that can be supplied via environment variables
        referer = os.getenv("OPEN_ROUTER_REFERER")
        title = os.getenv("OPEN_ROUTER_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            resp = requests.post(self.url, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"LLM request failed: {e}") from e

        # Try a few common response shapes, fall back to raw text
        data = resp.json()
        # OpenRouter often mirrors OpenAI shape: choices -> message -> content
        if isinstance(data, dict):
            # new OpenRouter may return `choices` list
            choices = data.get("choices")
            if choices and isinstance(choices, list):
                first = choices[0]
                # choice may have message->content or text
                if isinstance(first, dict):
                    msg = first.get("message") or first
                    content = msg.get("content") if isinstance(msg, dict) else None
                    if content:
                        return content

            # fallback common field
            if "response" in data:
                return data["response"]

        # final fallback: return raw text
        return resp.text
