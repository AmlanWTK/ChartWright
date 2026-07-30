"""Reference 'hello' service.

Exists solely to exercise the Python CI lane (ruff, mypy, pytest, coverage) with a
minimal, real FastAPI app that has health and readiness probes — the same shape every
Chartwright service will follow from CP06 onward. It contains no business logic.
"""

from hello.main import app

__all__ = ["app"]
__version__ = "0.1.0"
