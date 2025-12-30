"""Repository-level launcher.

Run this from the repo root with:

    python run.py

This avoids modifying package import paths inside library code and keeps
`app/` as a regular package.
"""
from app.orchestrator import run


if __name__ == "__main__":
    out = run("OpenAI")
    print("Generated:", out)
