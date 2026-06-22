"""Enable ``python -m citevahti`` (mirrors the ``citevahti`` console script)."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
