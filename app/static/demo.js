(function () {
  const $ = (id) => document.getElementById(id);
  const lanes = { single: $("lane-single"), split: $("lane-split") };
  const state = {};
  let maxPrompt = 1;
  const fmtTok = (n) => n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n);
  const usd = (v) => "$" + (v < 0.01 ? v.toFixed(4) : v.toFixed(3));
  const totalTok = (e) => e.input_tokens + e.output_tokens + e.cached_tokens;

  fetch("/api/config").then((r) => r.json()).then((c) => {
    $("model").textContent = c.fake_model ? "a scripted fake model" : c.model;
    $("thinking").textContent = c.fake_model ? "" : ` (thinking: ${c.thinking})`;
    $("single-turns").textContent = c.single_max_turns;
    $("split-turns").textContent = c.split_max_turns;
    $("cap").textContent = "$" + c.mode_max_usd.toFixed(2);
    $("outcap").textContent = c.tool_output_chars.toLocaleString("en-US");
    const p = c.prices_per_million;
    $("prices").textContent = `$${p.input} per million input tokens, $${p.output} per million output tokens (thinking included), $${p.cached} per million cached tokens`;
    if (!c.live) { $("go").disabled = true; $("status").textContent = "Live runs are not enabled on this server."; }
    else if (c.fake_model) $("status").textContent = "Test mode: a scripted fake model, not Gemini. Numbers are estimates.";
  }).catch(() => {});

  function reset() {
    maxPrompt = 1;
    for (const m in lanes) {
      const lane = lanes[m];
      lane.querySelector(".tree").innerHTML = "";
      lane.querySelector(".verdict").textContent = "";
      lane.querySelector('[data-k="tokens"]').textContent = "0";
      lane.querySelector('[data-k="cost"]').textContent = "$0";
      lane.querySelector('[data-k="time"]').textContent = "0s";
      lane.querySelector('[data-k="turns"]').textContent = "0";
      state[m] = { nodes: {}, start: performance.now(), done: null, turns: 0 };
    }
    $("compare").hidden = true;
  }

  function getNode(mode, id, parent) {
    const st = state[mode];
    let n = st.nodes[id];
    if (!n) {
      n = document.createElement("li");
      n.className = "node";
      n.innerHTML = '<div class="row"><span class="dot"></span><span class="label"></span></div><div class="detail"></div><div class="bars"></div><ul></ul>';
      st.nodes[id] = n;
      const p = parent && st.nodes[parent];
      (p ? p.querySelector("ul") : lanes[mode].querySelector(".tree")).appendChild(n);
    }
    return n;
  }

  function node(mode, ev) {
    const n = getNode(mode, ev.id, ev.parent);
    n.querySelector(".dot").className = "dot " + ev.state;
    n.querySelector(".label").textContent = ev.label;
    n.querySelector(".detail").textContent = ev.detail || "";
  }

  function sizeBar(bar) {
    const p = +bar.dataset.p, c = +bar.dataset.c;
    bar.style.height = Math.max(2, Math.round(34 * p / maxPrompt)) + "px";
    bar.firstChild.style.height = (p > 0 ? Math.round(100 * c / p) : 0) + "%";
  }

  function turn(mode, ev) {
    const n = getNode(mode, ev.id, "root");
    const arg = ev.arg ? " " + ev.arg : "";
    const cached = ev.cached_tokens ? ` (${fmtTok(ev.cached_tokens)} cached)` : "";
    n.querySelector(".detail").textContent =
      `turn ${ev.turn}/${ev.max_turns}: ${ev.action}${arg} · sent ${fmtTok(ev.prompt_tokens)} tokens${cached}`;
    const bar = document.createElement("i");
    bar.appendChild(document.createElement("b"));
    bar.dataset.p = ev.prompt_tokens;
    bar.dataset.c = ev.cached_tokens || 0;
    bar.title = `turn ${ev.turn}: ${ev.action}${arg}\n${ev.prompt_tokens.toLocaleString("en-US")} prompt tokens sent` +
      (ev.cached_tokens ? `, ${ev.cached_tokens.toLocaleString("en-US")} cached` : "");
    n.querySelector(".bars").appendChild(bar);
    if (ev.prompt_tokens > maxPrompt) {
      maxPrompt = ev.prompt_tokens;
      document.querySelectorAll(".bars i").forEach(sizeBar);
    } else sizeBar(bar);
    state[mode].turns += 1;
    lanes[mode].querySelector('[data-k="turns"]').textContent = state[mode].turns;
  }

  function usage(mode, ev) {
    const lane = lanes[mode];
    lane.querySelector('[data-k="tokens"]').textContent = fmtTok(totalTok(ev));
    lane.querySelector('[data-k="cost"]').textContent = usd(ev.cost_usd);
  }

  let timer = null;
  function tick() {
    for (const m in lanes) {
      const st = state[m];
      if (!st || st.done) continue;
      lanes[m].querySelector('[data-k="time"]').textContent = ((performance.now() - st.start) / 1000).toFixed(1) + "s";
    }
  }

  function done(mode, ev) {
    const lane = lanes[mode];
    state[mode].done = ev;
    usage(mode, ev);
    lane.querySelector('[data-k="time"]').textContent = ev.wall_seconds.toFixed(1) + "s";
    lane.querySelector('[data-k="turns"]').textContent = ev.calls;
    const v = lane.querySelector(".verdict");
    v.className = "verdict " + (ev.green ? "ok" : "no");
    const cap = ev.stop === "budget cap" ? ` · stopped at the $${ev.budget_usd.toFixed(2)} cap` : "";
    v.textContent = (ev.green ? "✓ Green: " : "✗ Still red: ") + `${ev.passed}/${ev.total} tests pass · ${ev.calls} model turn(s)${cap}`;
  }

  function compare() {
    const a = state.single.done, b = state.split.done;
    if (!a || !b || a.error || b.error) return;
    const tile = (k, v, s) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
    // Split as a fraction of single (0.66x = 34% less), the same way the results page reports Duelz vs a baseline.
    const ratio = (single, split, less, more) => {
      if (!(single > 0 && split > 0)) return "n/a";
      const r = split / single, pct = Math.round(Math.abs(1 - r) * 100);
      return `${r.toFixed(2)}x <small>${pct < 3 ? "about even" : `${pct}% ${r < 1 ? less : more}`}</small>`;
    };
    $("cmp-tiles").innerHTML =
      tile("Split cost vs single", ratio(a.cost_usd, b.cost_usd, "less", "more"), `split ${usd(b.cost_usd)} vs single ${usd(a.cost_usd)}`) +
      tile("Split time vs single", ratio(a.wall_seconds, b.wall_seconds, "less", "more"), `split ${b.wall_seconds.toFixed(1)}s vs single ${a.wall_seconds.toFixed(1)}s`) +
      tile("Split tokens vs single", ratio(totalTok(a), totalTok(b), "fewer", "more"), `split ${fmtTok(totalTok(b))} vs single ${fmtTok(totalTok(a))}`) +
      tile("Split largest prompt vs single", ratio(a.max_prompt_tokens, b.max_prompt_tokens, "smaller", "larger"),
        `split ${fmtTok(b.max_prompt_tokens)} vs single ${fmtTok(a.max_prompt_tokens)} tokens in one turn`) +
      tile("Green", `${b.green ? "✓" : "✗"} / ${a.green ? "✓" : "✗"}`, `split / single · ${b.calls} vs ${a.calls} turns`);
    $("cmp-foot").textContent = "One run, so expect noise. " +
      "The single agent's prompt grows every turn because it re-sends the whole conversation; split branches stay short " +
      "and run at the same time. Gemini's implicit cache, when it hits, makes re-sent tokens cheaper and narrows the cost gap.";
    $("compare").hidden = false;
  }

  // Recent live runs, stored in Firestore by the server (GET /api/runs).
  const ago = (t) => {
    if (!t) return "just now";
    const s = Math.max(0, Date.now() / 1000 - t);
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return Math.round(s / 86400) + " d ago";
  };
  const modeCell = (m) => m && !m.error && m.cost_usd != null
    ? `${usd(m.cost_usd)} · ${(+m.wall_seconds).toFixed(0)}s` : "error";
  function loadRuns() {
    fetch("/api/runs").then((r) => r.json()).then((d) => {
      const body = $("hist-rows");
      body.innerHTML = "";
      const runs = d.runs || [];
      if (!runs.length) {
        const tr = body.insertRow(), td = tr.insertCell();
        td.colSpan = 5; td.className = "empty";
        td.textContent = d.stored === false ? "Run history is not stored on this server (local or test mode)."
          : "No stored runs yet. Press “Run both modes” to add one.";
      }
      for (const r of runs) {
        const tr = body.insertRow();
        const ok = r.both_green;
        [ago(r.created), modeCell(r.single), modeCell(r.split), r.cost_label, ok ? "✓" : "✗"].forEach((v, i) => {
          const td = tr.insertCell(); td.textContent = v;
          if (i === 4) td.className = ok ? "ok" : "no";
        });
      }
      const a = d.aggregate || {};
      $("hist-agg").textContent = a.count
        ? `Last ${a.count} stored run(s): median split cost ${a.median_cost_label} vs single; split was cheaper in ` +
          `${a.split_cheaper} of ${a.compared}; both modes green in ${a.both_green} of ${a.count}.`
        : "";
    }).catch(() => { $("hist-rows").innerHTML = '<tr><td colspan="5" class="empty">Run history unavailable.</td></tr>'; });
  }
  loadRuns();

  $("go").addEventListener("click", async () => {
    $("go").disabled = true;
    $("status").textContent = "Starting…";
    reset();
    timer = setInterval(tick, 100);
    try {
      const res = await fetch("/api/run", { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        $("status").innerHTML = '<span class="err"></span>';
        $("status").firstChild.textContent = body.error || "Run refused (" + res.status + ")";
        return;
      }
      $("status").textContent = "Running: both modes in parallel…";
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done: end } = await reader.read();
        if (end) break;
        buf += dec.decode(value, { stream: true });
        let i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
          if (!chunk.startsWith("data: ")) continue;
          const ev = JSON.parse(chunk.slice(6));
          if (ev.kind === "start") { for (const m in state) state[m].start = performance.now(); }
          else if (ev.kind === "node") node(ev.mode, ev);
          else if (ev.kind === "turn") turn(ev.mode, ev);
          else if (ev.kind === "usage") usage(ev.mode, ev);
          else if (ev.kind === "done") { done(ev.mode, ev); compare(); }
          else if (ev.kind === "error") {
            state[ev.mode].done = { error: true };
            const v = lanes[ev.mode].querySelector(".verdict");
            v.className = "verdict no"; v.textContent = "Error: " + ev.message;
          } else if (ev.kind === "end") $("status").textContent = "Done.";
        }
      }
    } catch (e) {
      $("status").innerHTML = '<span class="err"></span>';
      $("status").firstChild.textContent = "Connection lost: " + e.message;
    } finally {
      clearInterval(timer);
      // The server stores the run in the background; give the write a moment, then refresh the table.
      setTimeout(loadRuns, 2500); setTimeout(loadRuns, 10000);
      setTimeout(() => { $("go").disabled = false; }, 60000);
    }
  });
})();
