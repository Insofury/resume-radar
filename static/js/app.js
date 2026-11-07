// ResumeRadar front-end controller: input handling, API calls, results and the AI coach.

import { esc, renderReport } from "./render.js";
import { reportToMarkdown } from "./report.js";

const $ = (id) => document.getElementById(id);
const state = { mode: "file", file: null, config: null, report: null, coach: null, coachLoading: false };

// ------------------------------------------------------------ helpers
function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (el.hidden = true), 2600);
}

function showError(message) {
  const el = $("formError");
  el.textContent = message;
  el.hidden = !message;
}

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

function formatSize(bytes) {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

function countWords(text) {
  return (text.trim().match(/\S+/g) || []).length;
}

async function copy(text, button) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  if (button) {
    const original = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => (button.textContent = original), 1300);
  }
}

// ------------------------------------------------------------ theme
function currentTheme() {
  const attr = document.documentElement.getAttribute("data-theme");
  if (attr) return attr;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

$("themeBtn").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem("resumeradar:theme", next);
  } catch {
    /* ignore */
  }
});

// ------------------------------------------------------------ inputs
function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t.dataset.mode === mode)));
  $("dropzone").hidden = mode !== "file" || Boolean(state.file);
  $("fileChip").hidden = mode !== "file" || !state.file;
  $("resumeText").hidden = mode !== "text";
  if (mode === "text") $("resumeText").focus();
}

function setFile(file) {
  if (!file) {
    state.file = null;
    $("fileInput").value = "";
    setMode("file");
    return;
  }
  const ok = /\.(pdf|docx|txt|md)$/i.test(file.name);
  if (!ok) {
    showError("Please choose a PDF, DOCX or TXT file.");
    return;
  }
  const maxMb = state.config?.max_upload_mb ?? 5;
  if (file.size > maxMb * 1024 * 1024) {
    showError(`That file is ${formatSize(file.size)} - the limit is ${maxMb} MB.`);
    return;
  }
  showError("");
  state.file = file;
  $("fileName").textContent = file.name;
  $("fileSize").textContent = formatSize(file.size);
  setMode("file");
}

document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));
$("fileInput").addEventListener("change", (e) => setFile(e.target.files[0]));
$("removeFile").addEventListener("click", () => setFile(null));

const dz = $("dropzone");
["dragenter", "dragover"].forEach((type) =>
  dz.addEventListener(type, (e) => {
    e.preventDefault();
    dz.classList.add("dragging");
  }),
);
["dragleave", "drop"].forEach((type) => dz.addEventListener(type, () => dz.classList.remove("dragging")));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer?.files?.length) setFile(e.dataTransfer.files[0]);
});

const updateJobCount = () => {
  $("jobCount").textContent = `${countWords($("jobText").value)} words`;
};
$("jobText").addEventListener("input", updateJobCount);

$("sampleBtn").addEventListener("click", async () => {
  try {
    const res = await fetch("/api/sample");
    const sample = await res.json();
    state.file = null;
    $("resumeText").value = sample.resume;
    $("jobText").value = sample.job;
    updateJobCount();
    setMode("text");
    $("analyzeForm").requestSubmit();
  } catch {
    showError("Couldn't load the sample. Is the server running?");
  }
});

// ------------------------------------------------------------ analyze
$("analyzeForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  showError("");
  const job = $("jobText").value.trim();
  const resumeText = $("resumeText").value.trim();

  if (state.mode === "file" && !state.file) return showError("Upload your resume (or switch to 'Paste text').");
  if (state.mode === "text" && countWords(resumeText) < 10) return showError("Paste your resume text first.");
  if (countWords(job) < 10) return showError("Paste the job description you're applying for.");

  const form = new FormData();
  form.append("job_text", job);
  if (state.mode === "file") form.append("resume_file", state.file);
  else form.append("resume_text", resumeText);

  const btn = $("analyzeBtn");
  btn.disabled = true;
  btn.classList.add("loading");
  btn.querySelector(".btn-label").textContent = "Analyzing…";
  try {
    const res = await fetch("/api/analyze", { method: "POST", body: form });
    if (!res.ok) throw new Error(await apiError(res));
    state.report = await res.json();
    state.coach = null;
    $("results").hidden = false;
    renderReport(state.report);
    renderCoach();
    $("results").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    showError(err.message || "Network error - please try again.");
  } finally {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.querySelector(".btn-label").textContent = "Analyze match";
  }
});

// ------------------------------------------------------------ AI coach
function renderCoach(errorMessage = "") {
  const card = $("coachCard");
  const enabled = state.config?.coach_enabled;
  const sparkle = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8Z"/></svg>';

  let head = `<div class="coach-head"><div>
      <h3>${sparkle} AI resume coach</h3>
      <p>${
        enabled
          ? "Let Claude rewrite your weakest bullets for this job and draft a tailored summary. It never invents experience."
          : "The AI coach is off on this server. Add an ANTHROPIC_API_KEY to unlock Claude-written bullet rewrites and a tailored summary."
      }</p></div>`;
  if (enabled && !state.coach && !state.coachLoading) head += '<button type="button" class="btn primary" id="coachBtn">Rewrite with AI</button>';
  head += "</div>";

  let body = "";
  if (state.coachLoading) {
    body = '<div class="coach-body coach-loading"><span class="spinner"></span>Claude is tailoring your resume - this takes about 20-40 seconds…</div>';
  } else if (errorMessage) {
    body = `<p class="form-error">${esc(errorMessage)}</p>`;
  } else if (state.coach) {
    const c = state.coach;
    body = `<div class="coach-body">
      <div class="coach-label">Tailored summary <button type="button" class="copy-btn" data-copy="summary">Copy</button></div>
      <div class="coach-summary">${esc(c.tailored_summary)}</div>
      <div class="coach-label">Bullet rewrites</div>
      ${c.bullet_rewrites
        .map(
          (w, i) => `<div class="rewrite">
            <p class="rewrite-old">${esc(w.original)}</p>
            <p class="rewrite-new"><span>${esc(w.improved)}</span><button type="button" class="copy-btn" data-copy="${i}">Copy</button></p>
            <p class="rewrite-why">${esc(w.why)}</p>
          </div>`,
        )
        .join("")}
      <div class="coach-label">Tips for this job</div>
      <ul class="coach-tips">${c.top_tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
    </div>`;
  }
  card.innerHTML = head + body;

  card.querySelector("#coachBtn")?.addEventListener("click", runCoach);
  card.querySelectorAll("[data-copy]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const key = btn.dataset.copy;
      copy(key === "summary" ? state.coach.tailored_summary : state.coach.bullet_rewrites[Number(key)].improved, btn);
    }),
  );
}

async function runCoach() {
  const report = state.report;
  if (!report) return;
  state.coachLoading = true;
  renderCoach();
  try {
    const res = await fetch("/api/coach", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resume_text: report.resume_text,
        job_text: $("jobText").value.trim(),
        missing_skills: report.skills.missing.map((s) => s.name),
        weak_bullets: report.bullets.map((b) => b.text),
      }),
    });
    if (!res.ok) throw new Error(await apiError(res));
    state.coach = await res.json();
    state.coachLoading = false;
    renderCoach();
  } catch (err) {
    state.coachLoading = false;
    renderCoach(err.message || "The AI coach failed - please try again.");
  }
}

// ------------------------------------------------------------ export
$("downloadBtn").addEventListener("click", () => {
  if (!state.report) return;
  const blob = new Blob([reportToMarkdown(state.report, state.coach)], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `resumeradar-report-${new Date().toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Report downloaded");
});
$("printBtn").addEventListener("click", () => window.print());

// ------------------------------------------------------------ init
(async function init() {
  try {
    const res = await fetch("/api/config");
    state.config = await res.json();
  } catch {
    state.config = { coach_enabled: false, max_upload_mb: 5 };
  }
  updateJobCount();
})();
