"""Back-compat shim: ``python run.py`` == ``python -m ai_avatar``."""
from ai_avatar.__main__ import main

if __name__ == "__main__":
    main()
