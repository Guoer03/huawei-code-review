"""Allow ``python -m scripts`` to invoke the checker."""

from .check import main


if __name__ == "__main__":  # pragma: no cover - exercised through subprocess
    raise SystemExit(main())

