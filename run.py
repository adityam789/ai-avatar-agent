"""Back-compat shim: ``python run.py ...`` == ``ai-avatar ...``."""

from ai_avatar.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
