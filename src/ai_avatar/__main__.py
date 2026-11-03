"""``python -m ai_avatar TOPIC`` (the full CLI arrives in Task 05)."""

import sys

from ai_avatar.pipeline import run


def main() -> None:
    topic = " ".join(sys.argv[1:]) or "OpenAI"
    print("Generated:", run(topic))


if __name__ == "__main__":
    main()
