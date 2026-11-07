// Builds a Markdown version of the report for the "Download report" button.

export function reportToMarkdown(report, coach) {
  const lines = [];
  const date = new Date().toLocaleDateString();
  lines.push(`# ResumeRadar match report`, "", `_Generated ${date}_`, "");
  lines.push(`## Overall: ${report.score}/100 - ${report.label}`, "", report.summary, "");

  lines.push("| Part | Score | Weight | Detail |", "|---|---|---|---|");
  for (const p of report.breakdown) {
    lines.push(`| ${p.label} | ${p.score ?? "n/a"} | ${p.weight}% | ${p.detail} |`);
  }
  lines.push("");

  const s = report.skills;
  const names = (list) => list.map((x) => x.name).join(", ") || "-";
  lines.push("## Skills", "");
  lines.push(`- **Matched:** ${names(s.matched)}`);
  if (s.partial.length) lines.push(`- **Related (half credit):** ${s.partial.map((x) => `${x.name} (via ${x.via})`).join(", ")}`);
  lines.push(`- **Missing must-haves:** ${names(s.missing.filter((x) => x.importance === "required"))}`);
  lines.push(`- **Missing nice-to-haves:** ${names(s.missing.filter((x) => x.importance === "preferred"))}`, "");

  const r = report.requirements;
  lines.push("## Requirements", "");
  lines.push(`- Experience: ${r.years_required ? `${r.years_required}+ years required` : "not specified"} · ${r.years_found ?? "?"} years found`);
  lines.push(`- Education: ${r.degree_required ?? "not specified"} · found: ${r.degree_found ?? "none"}`, "");

  lines.push("## Keywords", "");
  lines.push(`- Present: ${report.keywords.matched.join(", ") || "-"}`);
  lines.push(`- Missing: ${report.keywords.missing.join(", ") || "-"}`, "");

  lines.push("## Top recommendations", "");
  report.recommendations.forEach((rec, i) => lines.push(`${i + 1}. ${rec}`));
  lines.push("");

  lines.push("## Resume checks", "");
  const mark = { pass: "✅", warn: "⚠️", fail: "❌" };
  for (const c of report.checks) lines.push(`- ${mark[c.status]} **${c.title}** - ${c.detail}${c.status !== "pass" ? ` _Tip: ${c.tip}_` : ""}`);
  lines.push("");

  if (report.bullets.length) {
    lines.push("## Bullets to strengthen", "");
    for (const b of report.bullets) lines.push(`- "${b.text}" - ${b.issues.join("; ")}`);
    lines.push("");
  }

  if (coach) {
    lines.push("## AI coach suggestions", "", "**Tailored summary**", "", coach.tailored_summary, "");
    for (const w of coach.bullet_rewrites) lines.push(`- ~~${w.original}~~`, `  - **${w.improved}** _(${w.why})_`);
    lines.push("", "**Tips**", "");
    coach.top_tips.forEach((t) => lines.push(`- ${t}`));
    lines.push("");
  }
  return lines.join("\n");
}
