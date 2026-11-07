"""Entry point for the browser build (GitHub Pages), where this package runs inside
Pyodide - Python compiled to WebAssembly. JavaScript calls these functions directly;
JSON strings keep the boundary between the two languages simple.
"""

from __future__ import annotations

import json
import os

from .service import UserError, run_analysis


def analyze_json(job_text: str, resume_text: str = "", filename: str | None = None, path: str | None = None) -> str:
    """Analyze and return {"ok": true, "report": {...}} or {"ok": false, "error": "..."}.

    An uploaded file is written by JavaScript into Pyodide's in-memory file system
    at `path`; it is read and deleted here, so nothing outlives the request.
    """
    data = None
    if path:
        with open(path, "rb") as fh:
            data = fh.read()
        os.remove(path)
    try:
        report = run_analysis(job_text or "", resume_text or "", filename or None, data)
    except UserError as exc:
        return json.dumps({"ok": False, "error": str(exc)})
    return json.dumps({"ok": True, "report": report})
