// Renders a ResumeRadar report (the JSON from /api/analyze) into the results section.
// All user/derived text goes through esc() before it touches innerHTML.

export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function tone(score) {
  if (score === null || score === undefined) return "na";
  if (score >= 80) return "good";
  if (score >= 65) return "ok";
  if (score >= 50) return "warn";
  return "bad";
}

const TONE_COLOR = { good: "var(--good)", ok: "var(--accent)", warn: "var(--warn)", bad: "var(--bad)", na: "var(--muted)" };
const STATUS_ICON = { pass: "✓", warn: "!", fail: "✕", na: "–" };
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------- score
function animateNumber(el, target) {
  const start = performance.now();
  const duration = 900;
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = String(Math.round(target * eased));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function renderScore(report) {
  const t = tone(report.score);
  const gauge = $("gauge");
  gauge.style.setProperty("--score-color", TONE_COLOR[t]);
  const circumference = 2 * Math.PI * 52;
  const fill = $("gaugeFill");
  fill.style.strokeDashoffset = String(circumference);
  requestAnimationFrame(() => {
    fill.style.strokeDashoffset = String(circumference * (1 - report.score / 100));
  });
  animateNumber($("scoreValue"), report.score);

  const label = $("scoreLabel");
  label.textContent = report.label;
  label.className = `score-label tone-${t}`;
  $("scoreSummary").textContent = report.summary;

  $("breakdown").innerHTML = report.breakdown
    .map((part) => {
      const pt = tone(part.score);
      const value = part.score === null ? '<span class="bd-value na">n/a</span>' : `<span class="bd-value">${part.score}</span>`;
      return `
        <div class="bd-row">
          <div class="bd-label">${esc(part.label)}<small>${esc(part.detail)} · ${part.weight}% of score</small></div>
          <div class="bd-bar"><span style="--bar-color:${TONE_COLOR[pt]}" data-width="${part.score ?? 0}"></span></div>
          ${value}
        </div>`;
    })
    .join("");
  requestAnimationFrame(() => {
    document.querySelectorAll(".bd-bar span").forEach((bar) => {
      bar.style.width = `${bar.dataset.width}%`;
    });
  });
}

// ------------------------------------------------------------- skills
function chip(text, cls, title = "") {
  return `<span class="chip ${cls}"${title ? ` title="${esc(title)}"` : ""}>${text}</span>`;
}

function chipGroup(title, items, render, emptyText) {
  if (!items.length && !emptyText) return "";
  const body = items.length ? `<div class="chips">${items.map(render).join("")}</div>` : `<p class="empty-note">${esc(emptyText)}</p>`;
  return `<div class="chip-group"><p class="group-title">${esc(title)} <span class="count">${items.length}</span></p>${body}</div>`;
}

function renderSkills(skills) {
  const softCls = (s) => (s.soft ? " soft" : "");
  const missingRequired = skills.missing.filter((s) => s.importance === "required");
  const missingPreferred = skills.missing.filter((s) => s.importance === "preferred");
  let html = "";
  html += chipGroup("Missing must-haves", missingRequired, (s) => chip(`✕ ${esc(s.name)}`, `bad${softCls(s)}`, s.category));
  html += chipGroup("Related experience (half credit)", skills.partial, (s) =>
    chip(`~ ${esc(s.name)} <small>via ${esc(s.via)}</small>`, `partial${softCls(s)}`, `You show ${s.via}; the job asks for ${s.name}`),
  );
  html += chipGroup("Missing nice-to-haves", missingPreferred, (s) => chip(esc(s.name), `outline${softCls(s)}`, s.category));
  html += chipGroup(
    "Matched",
    skills.matched,
    (s) => chip(`✓ ${esc(s.name)}`, `good${softCls(s)}`, `${s.category} · ${s.importance}`),
    "None of the job's skills were found yet.",
  );
  if (skills.extra.length) {
    html += `<details class="extra"><summary>Other skills on your resume (${skills.extra.length})</summary>
      <div class="chips">${skills.extra.map((s) => chip(esc(s.name), "neutral", s.category)).join("")}</div></details>`;
  }
  if (!html) html = '<p class="empty-note">No well-known skills were found in this job post.</p>';
  $("skills").innerHTML = html + '<p class="empty-note" style="margin-top:12px;font-size:12px">Dashed outline = soft skill (counts half).</p>';
}

// ------------------------------------------------------- requirements
function reqRow(status, title, detail) {
  return `<div class="req-row"><span class="status-dot ${status}">${STATUS_ICON[status]}</span>
    <div><div class="req-title">${esc(title)}</div><div class="req-detail">${esc(detail)}</div></div></div>`;
}

function renderRequirements(report) {
  const r = report.requirements;
  let html = "";
  if (r.years_required) {
    const found = r.years_found ? `${r.years_found} years found on your resume` : "No dated experience found";
    html += reqRow(r.years_met ? "pass" : "fail", `${r.years_required}+ years of experience`, found);
  } else {
    html += reqRow("na", "Years of experience", r.years_found ? `No requirement stated · ${r.years_found} years on your resume` : "No requirement stated");
  }
  if (r.degree_required) {
    html += reqRow(r.degree_met ? "pass" : "fail", `${r.degree_required} degree`, r.degree_found ? `Found: ${r.degree_found}` : "No degree found on your resume");
  } else {
    html += reqRow("na", "Education", r.degree_found ? `No requirement stated · you list a ${r.degree_found}` : "No requirement stated");
  }
  const kw = report.keywords;
  html += `<div class="keywords">
    ${chipGroup("Key terms you use", kw.matched, (k) => chip(`✓ ${esc(k)}`, "good"), "")}
    ${chipGroup("Key terms you could add", kw.missing, (k) => chip(esc(k), "outline"), "")}
  </div>`;
  $("requirements").innerHTML = html;
}

// ------------------------------------------------- recs, checks, bullets
function renderRecommendations(recs) {
  $("recs").innerHTML = recs.length
    ? recs.map((r) => `<li>${esc(r)}</li>`).join("")
    : "<li>Great work - nothing major to fix. Tailor your summary to the company and apply!</li>";
}

function renderChecks(checks) {
  const order = { fail: 0, warn: 1, pass: 2 };
  $("checks").innerHTML = [...checks]
    .sort((a, b) => order[a.status] - order[b.status])
    .map(
      (c) => `<li><span class="status-dot ${c.status}">${STATUS_ICON[c.status]}</span><div>
        <div class="check-title">${esc(c.title)}</div>
        <div class="check-detail">${esc(c.detail)}</div>
        ${c.status !== "pass" ? `<div class="check-tip">${esc(c.tip)}</div>` : ""}
      </div></li>`,
    )
    .join("");
}

function renderBullets(bullets) {
  $("bullets").innerHTML = bullets.length
    ? bullets
        .map(
          (b) => `<div class="bullet">
            <p class="bullet-text">${esc(b.text)}</p>
            <div class="chips">${b.issues.map((i) => chip(esc(i), "bad")).join("")}</div>
            <ul>${b.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>
          </div>`,
        )
        .join("")
    : '<p class="empty-note">Your bullets look strong - action verbs and numbers throughout. 👏</p>';
}

export function renderReport(report) {
  renderScore(report);
  renderSkills(report.skills);
  renderRequirements(report);
  renderRecommendations(report.recommendations);
  renderChecks(report.checks);
  renderBullets(report.bullets);
}
