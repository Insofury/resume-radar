// The analysis "engine" behind the UI. Two interchangeable implementations:
//
//  ServerEngine  - the FastAPI version: sends the resume to /api/analyze.
//  BrowserEngine - the GitHub Pages version: loads Pyodide (Python compiled to
//                  WebAssembly) and runs the very same Python analysis code inside
//                  the visitor's browser. The resume never leaves their device.
//
// createEngine() picks one: the Pages build ships a browser-mode.json file, the
// server does not.

async function apiError(res) {
  try {
    const body = await res.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join("; ");
  } catch {
    /* not JSON */
  }
  return `Something went wrong (HTTP ${res.status}).`;
}

class ServerEngine {
  constructor() {
    this.mode = "server";
    this.onStatus = () => {};
  }

  async config() {
    const res = await fetch("api/config");
    if (!res.ok) throw new Error(await apiError(res));
    return { ...(await res.json()), mode: "server" };
  }

  warmUp() {
    return Promise.resolve();
  }

  async sample() {
    const res = await fetch("api/sample");
    if (!res.ok) throw new Error(await apiError(res));
    return res.json();
  }

  async analyze({ file, resumeText, jobText }) {
    const form = new FormData();
    form.append("job_text", jobText);
    if (file) form.append("resume_file", file);
    else form.append("resume_text", resumeText);
    const res = await fetch("api/analyze", { method: "POST", body: form });
    if (!res.ok) throw new Error(await apiError(res));
    return res.json();
  }

  async coach(payload) {
    const res = await fetch("api/coach", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await apiError(res));
    return res.json();
  }
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Couldn't load ${src}`));
    document.head.appendChild(script);
  });
}

// Give the browser a moment to paint the "Analyzing…" state. A timer (not
// requestAnimationFrame) so it still resolves if the tab is in the background.
const yieldToBrowser = () => new Promise((resolve) => setTimeout(resolve, 30));

class BrowserEngine {
  constructor(cfg) {
    this.mode = "browser";
    this.cfg = cfg;
    this.loading = null;
    this.api = null;
    this.py = null;
    this.onStatus = () => {};
  }

  async config() {
    return { version: this.cfg.version, coach_enabled: false, max_upload_mb: 5, mode: "browser" };
  }

  /** Start loading Python in the background (cached by the browser after the first visit). */
  warmUp() {
    if (!this.loading) {
      this.loading = this._load().catch((err) => {
        this.loading = null;
        this.onStatus("error", "Couldn't load the Python engine - check your connection and reload the page.");
        throw err;
      });
    }
    return this.loading;
  }

  async _load() {
    const base = `https://cdn.jsdelivr.net/pyodide/v${this.cfg.pyodide_version}/full/`;
    this.onStatus("loading", "Loading the Python engine (first visit only)…");
    await loadScript(`${base}pyodide.js`);
    const py = await window.loadPyodide({ indexURL: base });

    this.onStatus("loading", "Installing the PDF reader…");
    await py.loadPackage("micropip");
    const micropip = py.pyimport("micropip");
    for (const pkg of this.cfg.packages) await micropip.install(pkg);

    this.onStatus("loading", "Loading ResumeRadar…");
    py.FS.mkdirTree("/home/pyodide/app");
    await Promise.all(
      this.cfg.modules.map(async (name) => {
        const res = await fetch(`py/app/${name}`);
        if (!res.ok) throw new Error(`Missing module ${name}`);
        py.FS.writeFile(`/home/pyodide/app/${name}`, await res.text());
      }),
    );
    py.runPython("import sys\nsys.path.insert(0, '/home/pyodide')");
    this.api = py.pyimport("app.browser");
    this.py = py;
    this.onStatus("ready", "Python engine ready - your resume never leaves this device.");
  }

  async sample() {
    const res = await fetch("sample.json");
    return res.json();
  }

  async analyze({ file, resumeText, jobText }) {
    await this.warmUp();
    let path = null;
    let filename = null;
    if (file) {
      if (file.size > 5 * 1024 * 1024) throw new Error("Files must be under 5 MB.");
      path = "/tmp/upload.bin";
      filename = file.name;
      this.py.FS.writeFile(path, new Uint8Array(await file.arrayBuffer()));
    }
    await yieldToBrowser();
    const out = JSON.parse(this.api.analyze_json(jobText, resumeText || "", filename, path));
    if (!out.ok) throw new Error(out.error);
    return out.report;
  }

  async coach() {
    throw new Error("The AI coach needs the server version (it uses a private API key).");
  }
}

export async function createEngine() {
  try {
    const res = await fetch("browser-mode.json", { cache: "no-cache" });
    if (res.ok) {
      const cfg = await res.json();
      if (cfg.mode === "browser") return new BrowserEngine(cfg);
    }
  } catch {
    /* fall through to the server engine */
  }
  return new ServerEngine();
}
