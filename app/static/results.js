(async function () {
  const res = await fetch("/static/bench-results.json", { cache: "no-store" });
  const d = await res.json();
  const $ = (id) => document.getElementById(id);
  const usd = (v) => "$" + (v < 1 ? v.toFixed(2) : v.toFixed(2));
  const min = (s) => (s / 60).toFixed(1) + " min";
  const tile = (k, v, s) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s || ""}</div></div>`;
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  if (d.stopped) $("prov").textContent = `Benchmark: ${d.gemini.paired_tasks} multi-bug tasks, Duelz vs Gemini CLI on ${d.gemini.model}`;
  else if (!d.provisional) $("prov").textContent = "Numbers generated " + d.generated_at;
  else $("prov").textContent = `Provisional: Gemini run in progress (${d.gemini.paired_tasks} of ${d.gemini.planned_tasks} tasks paired). Generated ${d.generated_at}.`;
  $("gen").textContent = "Data generated " + d.generated_at + ".";

  // (a) Gemini CLI vs Duelz
  const g = d.gemini, s = g.summary;
  $("gem-sub").textContent = `Both on ${g.model}. ${g.paired_tasks} multi-bug coding tasks${d.stopped ? "" : ` paired so far (of ${g.planned_tasks})`}. One run per task per side.`;
  $("gem-tiles").innerHTML =
    tile("Cheaper", s.cheaper_x + "x", `${usd(s.duelz.mean_cost)} vs ${usd(s.baseline.mean_cost)} per task`) +
    tile("Faster", s.faster_x + "x", `${min(s.duelz.mean_seconds)} vs ${min(s.baseline.mean_seconds)} per task`) +
    tile("Solved, Duelz", `${s.duelz.solved}/${s.duelz.n}`, "tasks fully passing") +
    tile("Solved, Gemini CLI", `${s.baseline.solved}/${s.baseline.n}`, "tasks fully passing");
  const short = (t) => t.split("-")[0].replace("scikit", "sklearn");
  const A = "var(--accent)", B = "var(--baseline)";
  groupedBars($("gem-cost"), g.tasks.map((t) => ({
    label: short(t.task),
    bars: [
      { v: t.duelz.cost, color: A, tip: `${t.task}\nDuelz: ${usd(t.duelz.cost)}` },
      { v: t.baseline.cost, color: B, tip: `${t.task}\nGemini CLI: ${usd(t.baseline.cost)}` },
    ],
  })), (v) => "$" + v.toFixed(2));
  groupedBars($("gem-time"), g.tasks.map((t) => ({
    label: short(t.task),
    bars: [
      { v: t.duelz.seconds / 60, color: A, tip: `${t.task}\nDuelz: ${min(t.duelz.seconds)}` },
      { v: t.baseline.seconds / 60, color: B, tip: `${t.task}\nGemini CLI: ${min(t.baseline.seconds)}` },
    ],
  })), (v) => v.toFixed(0));
  const mark = (ok) => ok ? '<span class="ok">✓ solved</span>' : '<span class="no">✗ not solved</span>';
  $("gem-table").innerHTML =
    "<tr><th>Task</th><th>Duelz cost</th><th>Gemini CLI cost</th><th>Duelz time</th><th>Gemini CLI time</th><th>Duelz</th><th>Gemini CLI</th></tr>" +
    g.tasks.map((t) => `<tr><td class="task">${esc(t.task)}</td><td>${usd(t.duelz.cost)}</td><td>${usd(t.baseline.cost)}</td>` +
      `<td>${min(t.duelz.seconds)}</td><td>${min(t.baseline.seconds)}</td><td>${mark(t.duelz.solved)}</td><td>${mark(t.baseline.solved)}</td></tr>`).join("") +
    `<tr><th>Total</th><th>${usd(s.duelz.total_cost)}</th><th>${usd(s.baseline.total_cost)}</th><th>${min(s.duelz.mean_seconds)} avg</th><th>${min(s.baseline.mean_seconds)} avg</th><th>${s.duelz.solved}/${s.duelz.n}</th><th>${s.baseline.solved}/${s.baseline.n}</th></tr>`;
  const ex = g.excluded.map((e) => `${esc(e.task)}: ${esc(e.reason)}`).join("; ");
  $("gem-foot").innerHTML = `${esc(g.note)} ` +
    (ex ? `Excluded from the paired comparison: ${ex}. ` : "") +
    (g.pending_tasks > 0 ? `${g.pending_tasks} task(s) still running; these numbers will be regenerated.` : "");

  // Real runs
  const runs = d.real_runs || [];
  $("real").hidden = !runs.length;
  const bar = (v, max, color) => `<span class="rbar"><i style="width:${Math.max(2, 100 * v / max)}%;background:${color}"></i></span>`;
  $("real-runs").innerHTML = runs.map((r) => {
    const mc = Math.max(r.duelz.cost, r.baseline.cost), ms = Math.max(r.duelz.seconds, r.baseline.seconds);
    const branches = Array.from({ length: r.branches }, (_, i) => `<i class="pip g" title="branch ${i + 1}"></i>`).join("");
    return `<div class="run">
      <div class="run-h"><b>${esc(r.project)}</b><span>${r.bugs.length} bugs</span></div>
      <ol class="bugs">${r.bugs.map((b) => `<li>${esc(b.what)} <span class="bid">${esc(b.id)}</span></li>`).join("")}</ol>
      <div class="run-split"><span class="pip"></span><span class="arrow">→</span>${branches}<small>${r.branches} parallel branches</small></div>
      <div class="run-row"><span class="k">Cost</span>
        <div><div>${bar(r.duelz.cost, mc, A)} Duelz ${usd(r.duelz.cost)}</div><div>${bar(r.baseline.cost, mc, B)} Gemini CLI ${usd(r.baseline.cost)}</div></div></div>
      <div class="run-row"><span class="k">Time</span>
        <div><div>${bar(r.duelz.seconds, ms, A)} Duelz ${min(r.duelz.seconds)}</div><div>${bar(r.baseline.seconds, ms, B)} Gemini CLI ${min(r.baseline.seconds)}</div></div></div>
      <div class="run-x"><b>${(r.duelz.cost / r.baseline.cost).toFixed(2)}x</b> the cost · <b>${(r.duelz.seconds / r.baseline.seconds).toFixed(2)}x</b> the time
        · ${r.duelz.solved && r.baseline.solved ? "both solved" : `Duelz ${r.duelz.solved ? "solved" : "not solved"}, Gemini CLI ${r.baseline.solved ? "solved" : "not solved"}`}</div>
    </div>`;
  }).join("");

  // (b) Claude Code
  const c = d.claude_code;
  $("cc-tiles").innerHTML =
    tile("Model cost", c.model_cost_ratio, "Duelz vs Claude Code") +
    tile("Solved", `${c.solved.duelz_pct}% vs ${c.solved.claude_code_pct}%`, "Duelz vs Claude Code") +
    tile("Wall time", c.time_ratio + "x", "Duelz vs Claude Code");
  $("cc-foot").textContent = c.source;

  // (c) babel
  const b = d.babel;
  $("babel-tiles").innerHTML =
    tile("Duelz", "All passing", `${b.tests.toLocaleString()} tests · ${usd(b.duelz.cost)}`) +
    tile("Claude Code", `${b.claude_code.failing} failing`, `${b.tests.toLocaleString()} tests · ${usd(b.claude_code.cost)}`) +
    tile("Cost", (b.claude_code.cost / b.duelz.cost).toFixed(1) + "x", "cheaper with Duelz");
  hBars($("babel-cost"), [
    { name: "Duelz", v: b.duelz.cost, color: A, text: usd(b.duelz.cost) },
    { name: "Claude Code", v: b.claude_code.cost, color: B, text: usd(b.claude_code.cost) },
  ]);
  $("babel-foot").textContent = b.source;
})();
