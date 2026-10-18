// Minimal SVG charts: grouped vertical bars and horizontal bars, with hover tips.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const tip = () => document.getElementById("tip");
  function el(name, attrs, parent) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function hover(node, text) {
    node.addEventListener("mousemove", (e) => {
      const t = tip(); t.textContent = text; t.style.opacity = 1;
      t.style.left = Math.min(e.clientX + 12, window.innerWidth - 270) + "px";
      t.style.top = (e.clientY + 12) + "px";
    });
    node.addEventListener("mouseleave", () => { tip().style.opacity = 0; });
  }
  // Returns [max, tickCount] with round tick steps.
  function niceMax(v) {
    const p = Math.pow(10, Math.floor(Math.log10(v || 1)));
    for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return [m * p, m === 2 ? 4 : 5];
    return [10 * p, 5];
  }
  // Bar path with 4px rounded top, square at baseline.
  function barPath(x, y, w, h, r) {
    r = Math.min(r, w / 2, h);
    return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
  }
  // groups: [{label, bars:[{v, color, tip}]}]
  window.groupedBars = function (host, groups, fmtAxis) {
    const W = 560, H = 240, L = 44, R = 8, T = 10, B = 28;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img" });
    const [max, ticks] = niceMax(Math.max(...groups.flatMap((g) => g.bars.map((b) => b.v || 0))));
    const ih = H - T - B, iw = W - L - R;
    for (let i = 0; i <= ticks; i++) {
      const y = T + ih - (ih * i) / ticks;
      el("line", { x1: L, x2: W - R, y1: y, y2: y, stroke: "var(--grid)", "stroke-width": 1 }, svg);
      el("text", { x: L - 6, y: y + 4, "text-anchor": "end", "font-size": 11, fill: "var(--muted)" }, svg)
        .textContent = fmtAxis((max * i) / ticks);
    }
    const gw = iw / groups.length, n = groups[0].bars.length;
    const bw = Math.min(18, (gw - 8) / n - 2);
    groups.forEach((g, gi) => {
      const x0 = L + gi * gw + (gw - (bw * n + 2 * (n - 1))) / 2;
      g.bars.forEach((b, bi) => {
        const h = ((b.v || 0) / max) * ih;
        const x = x0 + bi * (bw + 2);
        const p = el("path", { d: barPath(x, T + ih - h, bw, Math.max(h, 0.5), 4), fill: b.color }, svg);
        const hit = el("rect", { x: x - 1, y: T, width: bw + 2, height: ih, fill: "transparent" }, svg);
        hover(hit, b.tip); hover(p, b.tip);
      });
      el("text", { x: L + gi * gw + gw / 2, y: H - 10, "text-anchor": "middle", "font-size": 11, fill: "var(--text-2)" }, svg)
        .textContent = g.label;
    });
    el("line", { x1: L, x2: W - R, y1: T + ih, y2: T + ih, stroke: "var(--border)", "stroke-width": 1 }, svg);
    host.innerHTML = ""; host.appendChild(svg);
  };
  // rows: [{name, v, color, text}]
  window.hBars = function (host, rows) {
    const W = 560, rowH = 34, L = 110, R = 70;
    const H = rows.length * rowH + 6;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, width: "100%", role: "img" });
    const max = Math.max(...rows.map((r) => r.v)) || 1;
    rows.forEach((r, i) => {
      const y = 4 + i * rowH, w = ((W - L - R) * r.v) / max;
      el("text", { x: L - 10, y: y + 17, "text-anchor": "end", "font-size": 13, fill: "var(--text-2)" }, svg).textContent = r.name;
      const p = el("path", { d: `M${L},${y + 4}H${L + w - 4}Q${L + w},${y + 4} ${L + w},${y + 8}V${y + 20}Q${L + w},${y + 24} ${L + w - 4},${y + 24}H${L}Z`, fill: r.color }, svg);
      hover(p, `${r.name}: ${r.text}`);
      el("text", { x: L + w + 8, y: y + 18, "font-size": 13, "font-weight": 600, fill: "var(--text)" }, svg).textContent = r.text;
    });
    host.innerHTML = ""; host.appendChild(svg);
  };
})();
