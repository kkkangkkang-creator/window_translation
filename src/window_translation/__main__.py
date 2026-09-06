"""Allow ``python -m window_translation`` to launch the app."""

from window_translation.launcher import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
