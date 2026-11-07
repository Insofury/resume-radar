"""Build the static GitHub Pages version of ResumeRadar into ./_site

GitHub Pages can only host static files, so this build ships the front-end plus the
pure-Python analysis modules. In the browser, Pyodide (Python compiled to
WebAssembly) loads those modules and runs the exact same analysis code the server
uses. The AI coach is left out because it needs a secret API key.

    python scripts/build_pages.py            # writes ./_site
    python -m http.server -d _site 8020      # preview at http://localhost:8020
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PYODIDE_VERSION = "0.26.4"  # Python 3.12 in the browser
BROWSER_PACKAGES = ["pypdf==7.0.0"]  # pure-Python wheels installed with micropip
BROWSER_MODULES = [
    "__init__.py",
    "analyzer.py",
    "browser.py",
    "checks.py",
    "experience.py",
    "job.py",
    "parsing.py",
    "resume.py",
    "samples.py",
    "service.py",
    "skills.py",
    "textutils.py",
]


def build(out: Path = ROOT / "_site") -> Path:
    from app import __version__
    from app.samples import SAMPLE_JOB, SAMPLE_RESUME

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "static", out / "static")
    shutil.copy2(ROOT / "static" / "index.html", out / "index.html")
    shutil.copy2(ROOT / "static" / "favicon.svg", out / "favicon.ico")

    modules_dir = out / "py" / "app"
    modules_dir.mkdir(parents=True)
    for name in BROWSER_MODULES:
        shutil.copy2(ROOT / "app" / name, modules_dir / name)

    config = {
        "mode": "browser",
        "version": __version__,
        "pyodide_version": PYODIDE_VERSION,
        "packages": BROWSER_PACKAGES,
        "modules": BROWSER_MODULES,
    }
    (out / "browser-mode.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (out / "sample.json").write_text(json.dumps({"resume": SAMPLE_RESUME, "job": SAMPLE_JOB}), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")  # serve files as-is (no Jekyll processing)
    return out


if __name__ == "__main__":
    site = build()
    files = sorted(p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file())
    print(f"Built {len(files)} files into {site}")
