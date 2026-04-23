"""Allow ``python -m window_translation`` to launch the app."""

from window_translation.app import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
