.PHONY: install test lint format demo doctor

install:  ## core + dev tools (no torch)
	pip install -e ".[dev]"

test:
	pytest --cov=ai_avatar

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

doctor:
	ai-avatar doctor

demo:  ## offline end-to-end run: fixtures + fake LLM/TTS/avatar, real ffmpeg
	ai-avatar run "OpenAI" --offline
