(async function () {
  const data = await (await fetch("/static/replays.json", { cache: "no-store" })).json();
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const usd = (v) => "$" + v.toFixed(2);
  let pick = 0, raf = null;

  $("pick").innerHTML = data.runs.map((r, i) =>
    `<button role="tab" data-i="${i}">${esc(r.project)}</button>`).join("");
  $("pick").onclick = (e) => { const b = e.target.closest("button"); if (b) { pick = +b.dataset.i; reset(); } };

  // Each lane is a list of timed steps; a step is "work" between start and end, then its end state.
  function plan(r) {
    const d = r.duelz, steps = [];
    const n = d.branches.length;
    const splitAt = Math.min(...d.branches.map((b) => b.start));
    const lastBranch = Math.max(...d.branches.map((b) => b.end));
    steps.push({ id: "t0", label: `Run the tests: ${r.failing_start} failing`, start: 0, end: d.first_check, done: "red" });
    steps.push({ id: "split", label: `Split by cause into ${n} branches`, start: d.first_check, end: splitAt, done: "green" });
    d.branches.forEach((b, i) => {
      const bug = b.bug != null ? r.bugs[b.bug] : null;
      steps.push({ id: "b" + i, parent: "split", start: b.start, end: b.end, done: "green", cost: b.cost, bug: true,
        label: bug ? bug.what : `Branch ${i + 1}`, detail: b.files.join(", ") });
    });
    steps.push({ id: "verify", label: "Merge, re-run the whole suite", start: lastBranch, end: d.final_check, done: "green" });
    steps.push({ id: "grade", label: d.solved ? "Hidden grader: solved" : "Hidden grader: not solved", start: d.final_check,
      end: d.wall, done: d.solved ? "green" : "fail" });
    const c = r.cli;
    const cli = [
      { id: "one", label: `One agent, all ${r.bugs.length} bugs`, start: 0, end: c.wall, done: "green", detail: "reads, edits and re-tests in one conversation" },
      { id: "grade", label: c.solved ? "Hidden grader: solved" : "Hidden grader: not solved", start: c.wall, end: c.wall, done: c.solved ? "green" : "fail" },
    ];
    return { duelz: { steps, wall: d.wall, cost: d.cost, bugs: r.bugs.length },
             cli: { steps: cli, wall: c.wall, cost: c.cost, bugs: r.bugs.length } };
  }

  function draw(lane, p, t) {
    const el = $("lane-" + lane), tree = el.querySelector(".tree");
    const html = {};
    let cost = 0, fixed = 0;
    for (const s of p.steps) {
      if (t < s.start) continue;
      const state = t >= s.end ? s.done : "work";
      if (s.bug && t >= s.end) fixed++;
      const li = `<li class="node"><div class="row"><span class="dot ${state}"></span><span class="label">${esc(s.label)}</span></div>` +
        (s.detail ? `<div class="detail">${esc(s.detail)}${s.cost != null && t >= s.end ? " · " + usd(s.cost) : ""}</div>` : "") +
        `<ul data-for="${s.id}"></ul></li>`;
      (html[s.parent || ""] = html[s.parent || ""] || []).push(li);
    }
    tree.innerHTML = (html[""] || []).join("");
    for (const k in html) if (k) { const ul = tree.querySelector(`ul[data-for="${k}"]`); if (ul) ul.innerHTML = html[k].join(""); }
    const tt = Math.min(t, p.wall);
    if (lane === "duelz") {
      const bs = p.steps.filter((s) => s.bug);
      const spent = bs.reduce((a, s) => a + s.cost * Math.max(0, Math.min(1, (tt - s.start) / (s.end - s.start || 1))), 0);
      const share = bs.reduce((a, s) => a + s.cost, 0);
      cost = spent + (p.cost - share) * (tt / p.wall);
    } else {
      cost = p.cost * (tt / p.wall);
      fixed = t >= p.wall ? p.bugs : 0;
    }
    el.querySelector('[data-k="cost"]').textContent = usd(cost);
    el.querySelector('[data-k="time"]').textContent = clock(tt);
    el.querySelector('[data-k="bugs"]').textContent = `${fixed}/${p.bugs}`;
    el.querySelector(".verdict").textContent = t >= p.wall ? `Done in ${clock(p.wall)} for ${usd(p.cost)}` : "";
  }

  function reset() {
    cancelAnimationFrame(raf);
    const r = data.runs[pick];
    [...$("pick").children].forEach((b, i) => b.setAttribute("aria-selected", i === pick));
    $("bugs").innerHTML = r.bugs.map((b) => `<li>${esc(b.what)} <span class="bid">${esc(b.id)}</span></li>`).join("");
    const p = plan(r);
    draw("cli", p.cli, 0); draw("duelz", p.duelz, 0);
    $("go").textContent = "Play";
    $("foot").textContent = `${r.project}: Duelz ${clock(r.duelz.wall)} for ${usd(r.duelz.cost)}; Gemini CLI ${clock(r.cli.wall)} for ${usd(r.cli.cost)}` +
      (r.cli.rate_limit_wait ? ` (its ${r.cli.rate_limit_wait}s of rate-limit retry waits removed; raw ${clock(r.cli.wall_raw)})` : "") +
      `. Duelz branch costs are split from the run's total by each branch's model time.`;
  }

  $("go").onclick = () => {
    cancelAnimationFrame(raf);
    const p = plan(data.runs[pick]), speed = +$("speed").value, t0 = performance.now();
    const end = Math.max(p.cli.wall, p.duelz.wall);
    $("go").textContent = "Replay";
    const tick = () => {
      const t = (performance.now() - t0) / 1000 * speed;
      draw("cli", p.cli, t); draw("duelz", p.duelz, t);
      if (t < end) raf = requestAnimationFrame(tick);
    };
    tick();
  };
  reset();
})();
