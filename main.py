"""Root-level entry point for Render deployment.

Render runs `uvicorn main:app` from the repo root. This shim adds the
aletheia-mneme directory to sys.path so all internal imports resolve,
then re-exports the FastAPI app object.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "aletheia-mneme"))

from main import app  # noqa: E402, F401
