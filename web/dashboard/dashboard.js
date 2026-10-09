/* TellTale dashboard: plain JS, no build step, no framework.
   Reads sites/index.json, sites/<site>/{site,series,forecast}.json and overlay PNGs
   from the data root (default "sites"; override with ?root=demo-data/public/sites). */
(function () {
  "use strict";
  const qs = new URLSearchParams(location.search);
  const ROOT = (qs.get("root") || "sites").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const fmt = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x)) ? "–" : Number(x).toFixed(d);

  // ---- theme
  const applyTheme = (t) => { if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; };
  applyTheme(localStorage.getItem("telltale-theme"));
  $("theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme;
    const next = cur === "dark" ? "light" : cur === "light" ? "" : "dark";
    applyTheme(next); localStorage.setItem("telltale-theme", next);
    if (lastData) render(lastData);
  });

  async function getJSON(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }

  let lastData = null;

  async function loadSite(site) {
    const base = `${ROOT}/${site}`;
    const [cfg, series, fc] = await Promise.all([
      getJSON(`${base}/site.json`), getJSON(`${base}/series.json`), getJSON(`${base}/forecast.json`)]);
    lastData = { site, base, cfg, series, fc };
    render(lastData);
  }

  function render({ site, base, cfg, series, fc }) {
    const zoneName = Object.keys(fc.zones)[0];
    const z = zoneName ? fc.zones[zoneName] : null;
    const recs = series.records;
    const last = recs[recs.length - 1];
    const lastUsable = [...recs].reverse().find(r => r.usable && r.zones && r.zones[zoneName] && r.zones[zoneName].n_valid > 0) || last;
    const state = fc.state || "QUIET";
    const chip = $("state-chip");
    chip.textContent = fc.state_display || state;
    chip.className = "chip chip-" + state.toLowerCase();
    $("cool-badge").hidden = !(fc.runtime && fc.runtime.cool);

    // status sentence
    const mm = cfg.mm_per_px || 1;
    let line;
    if (!z) line = `No measurements yet for ${site}.`;
    else if (state === "QUIET") line = `No significant movement in zone ${zoneName} over ${recs.length} epochs.`;
    else if (state === "MOVING") line = `Zone ${zoneName} is creeping steadily at ${fmt(lastV(z) * mm, 3)} mm per time unit; no acceleration detected.`;
    else if (state === "ACCELERATING") line = `Zone ${zoneName} is accelerating since t = ${fmt(z.ooa_time, 1)}. Forecast failure window t = ${fmt(z.t_lo, 1)} to ${fmt(z.t_hi, 1)} (fit R² ${fmt(z.r2, 2)}).`;
    else line = `CRITICAL: zone ${zoneName} forecast to fail between t = ${fmt(z.t_lo, 1)} and ${fmt(z.t_hi, 1)}, horizon ${fmt(z.horizon, 1)}. Human approval required before any public alert.`;
    if (last && !last.usable) line += ` Last epoch unusable (${last.reason}).`;
    $("status-line").textContent = line;

    renderApproval(fc.approval, base);

    $("overlay").src = lastUsable && lastUsable.overlay ? `${base}/${lastUsable.overlay}` : "";
    $("overlay-cap").textContent = lastUsable ? `Epoch t = ${fmt(lastUsable.t, 2)}; colour = displacement magnitude since the reference epoch, arrows = direction (scaled).` : "";

    const lz = lastUsable && lastUsable.zones ? lastUsable.zones[zoneName] : null;
    $("f-disp").textContent = lz ? `${fmt(lz.magnitude, 3)} px ± ${fmt(lz.sigma, 3)}  (${fmt(lz.magnitude * mm, 2)} mm)` : "–";
    $("f-vel").textContent = z ? `${fmt(lastV(z), 4)} px per time unit` : "–";
    $("f-ooa").textContent = z && z.ooa_time !== null && z.ooa_time !== undefined ? `t = ${fmt(z.ooa_time, 2)}` : "not detected";
    $("f-window").textContent = z && z.tf !== null && z.tf !== undefined ? `t = ${fmt(z.t_lo, 2)} to ${fmt(z.t_hi, 2)} (median ${fmt(z.tf, 2)})` : "none";
    $("f-r2").textContent = z && z.r2 !== null && z.r2 !== undefined ? fmt(z.r2, 3) : "–";
    $("f-epochs").textContent = `${recs.length} (${fc.n_unusable || 0})`;

    // health
    const covs = recs.filter(r => r.field).map(r => r.field.coverage);
    const inls = recs.filter(r => r.stabilize).map(r => r.stabilize.n_inliers);
    const times = recs.map(r => r.timing && r.timing.total_s).filter(x => x);
    $("h-cov").textContent = covs.length ? `${fmt(100 * covs[covs.length - 1], 0)} % (median ${fmt(100 * median(covs), 0)} %)` : "–";
    $("h-inl").textContent = inls.length ? `${inls[inls.length - 1]} (median ${median(inls)})` : "–";
    $("h-model").textContent = last && last.stabilize ? `${last.stabilize.refine_model || "coarse"}; residual ${fmt(Math.hypot(...(last.stabilize.residual || [0, 0])), 3)} px; scatter ${fmt(last.stabilize.scatter, 3)} px` : "–";
    $("h-time").textContent = times.length ? `${fmt(median(times), 2)} s median, ${fmt(Math.max(...times), 2)} s max` : "–";
    const rt = fc.runtime || {};
    $("h-cv").innerHTML = `<code>OpenCV ${rt.opencv_version || "?"} · ${rt.cv2_file || "?"} · build ${rt.build_hash || "?"}</code>`;
    $("h-inst").textContent = `${rt.instance_type || "local"} · ${rt.machine || ""} · AMI ${rt.ami_id || "n/a"} · ${rt.threads || "?"} threads`;

    // epoch table
    const tb = $("epochs").querySelector("tbody");
    tb.innerHTML = "";
    for (const r of [...recs].reverse()) {
      const zz = r.zones ? r.zones[zoneName] : null;
      const tr = document.createElement("tr");
      if (!r.usable) tr.className = "unusable";
      tr.innerHTML = `<td>${fmt(r.t, 2)}</td><td>${r.usable ? "yes" : "no"}</td><td>${r.reason || ""}</td>` +
        `<td>${zz ? fmt(zz.magnitude, 3) : ""}</td><td>${zz ? fmt(zz.sigma, 3) : ""}</td>` +
        `<td>${r.field ? fmt(100 * r.field.coverage, 0) + " %" : ""}</td>` +
        `<td>${r.stabilize ? r.stabilize.verdict + (r.stabilize.refine_model ? " / " + r.stabilize.refine_model : "") : ""}</td>` +
        `<td>${r.timing ? fmt(r.timing.total_s, 2) : ""}</td>`;
      tb.appendChild(tr);
    }

    drawDisp($("chart-disp"), z, mm);
    drawIV($("chart-iv"), z);
    renderAgent(base);
  }

  async function renderAgent(base) {
    const box = $("agent-events"), empty = $("agent-empty");
    box.innerHTML = "";
    let log;
    try { log = await getJSON(`${base}/agentlog.json`); } catch (e) { empty.hidden = false; return; }
    if (!log.events || !log.events.length) { empty.hidden = false; return; }
    empty.hidden = true;
    for (const e of [...log.events].reverse().slice(0, 8)) {
      const d = document.createElement("details");
      d.className = "agent-event";
      const verdictCls = e.verdict === "CONFIRMED" ? "chip-critical" : e.verdict === "FALSE_ALARM" ? "chip-quiet" : "chip-accelerating";
      d.innerHTML = `<summary><span class="chip ${verdictCls}">${e.verdict}</span> ${e.event} at t = ${fmt(e.t, 2)} · ${e.policy} policy · ${e.n_tool_calls} OpenCV tool calls · ${e.paged_human ? "human paged" : "no page"} · ${fmt(e.seconds, 1)} s</summary><p class="agent-summary">${(e.summary || "").replace(/</g, "&lt;")}</p><div class="trace">loading trace…</div>`;
      box.appendChild(d);
      d.addEventListener("toggle", async () => {
        if (!d.open || d.dataset.loaded) return;
        d.dataset.loaded = "1";
        try {
          const tr = await getJSON(`${base}/agent/${Number(e.t)}.json`);
          const ol = document.createElement("ol");
          for (const c of tr.calls) {
            const li = document.createElement("li");
            const res = JSON.stringify(c.result);
            li.innerHTML = `<b>${c.tool}</b>(${Object.entries(c.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ")}) → <code>${res.length > 400 ? res.slice(0, 400) + "…" : res}</code>`;
            ol.appendChild(li);
          }
          d.querySelector(".trace").replaceChildren(ol);
        } catch (err) { d.querySelector(".trace").textContent = "trace unavailable"; }
      });
    }
  }

  async function renderApproval(ap, base) {
    const box = $("approval");
    if (!ap || !ap.required) { box.hidden = true; return; }
    box.hidden = false;
    const txt = $("approval-text"), act = $("approval-actions"), list = $("decisions");
    act.innerHTML = ""; list.innerHTML = "";
    if (ap.status === "pending") {
      txt.textContent = `Human decision required for the CRITICAL episode that began at t = ${fmt(ap.episode_start, 2)}. Nothing has been sent to the public.`;
      if (ap.links && ap.links.approve) {
        for (const [name, cls] of [["approve", "btn-approve"], ["dismiss", "btn-dismiss"]]) {
          const a = document.createElement("a");
          a.href = ap.links[name]; a.target = "_blank"; a.rel = "noopener";
          a.className = "btn " + cls; a.textContent = name === "approve" ? "Approve public alert" : "Dismiss (false alarm)";
          act.appendChild(a);
        }
      } else {
        const s = document.createElement("span"); s.className = "hint";
        s.textContent = "Approval links are issued by the deployed stack (e-mail and SNS); not available in the offline demo.";
        act.appendChild(s);
      }
    } else {
      txt.textContent = `Episode decision: ${ap.status} at ${ap.decided_at} (for epoch t = ${fmt(ap.decided_t, 2)}).`;
    }
    try {
      const dec = await getJSON(`${base}/decisions.json`);
      // A decision recorded after the worker's last run applies immediately.
      const applicable = dec.decisions.filter(d => d.t >= ap.episode_start).sort((a, b) => a.at < b.at ? 1 : -1);
      if (ap.status === "pending" && applicable.length) {
        const d = applicable[0];
        txt.textContent = `Episode decision: ${d.action === "approve" ? "approved" : "dismissed"} at ${d.at} (for epoch t = ${fmt(d.t, 2)}). ${d.action === "approve" ? "The public alert may be issued." : "No public alert for this episode; measurement continues."}`;
        act.innerHTML = "";
      }
      for (const d of [...dec.decisions].reverse().slice(0, 10)) {
        const li = document.createElement("li");
        li.textContent = `${d.at}: ${d.action} for epoch t = ${fmt(d.t, 2)}${d.source ? " from " + d.source : ""}`;
        list.appendChild(li);
      }
    } catch (e) { /* no decisions yet */ }
  }

  const median = (a) => { const s = [...a].sort((x, y) => x - y); const m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const lastV = (z) => z.series && z.series.v_sma.length ? z.series.v_sma[z.series.v_sma.length - 1] : NaN;

  // ---- tiny SVG chart helpers
  const NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function scales(svg, xs, ys, pad = { l: 52, r: 16, t: 22, b: 34 }) {
    const W = 640, H = 260;
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (x1 === x0) x1 = x0 + 1;
    if (y1 === y0) y1 = y0 + 1;
    const py = (y1 - y0) * 0.08; y0 -= py; y1 += py;
    const sx = (x) => pad.l + (x - x0) / (x1 - x0) * (W - pad.l - pad.r);
    const sy = (y) => H - pad.b - (y - y0) / (y1 - y0) * (H - pad.t - pad.b);
    return { sx, sy, x0, x1, y0, y1, W, H, pad };
  }
  function axes(svg, s, xlabel, ylabel, yfmt = (v) => fmt(v, 2)) {
    const { sx, sy, x0, x1, y0, y1, W, H, pad } = s;
    svg.appendChild(el("line", { x1: pad.l, y1: H - pad.b, x2: W - pad.r, y2: H - pad.b, class: "axis" }));
    svg.appendChild(el("line", { x1: pad.l, y1: pad.t, x2: pad.l, y2: H - pad.b, class: "axis" }));
    for (let i = 0; i <= 4; i++) {
      const xv = x0 + (x1 - x0) * i / 4, yv = y0 + (y1 - y0) * i / 4;
      svg.appendChild(el("line", { x1: sx(xv), y1: pad.t, x2: sx(xv), y2: H - pad.b, class: "grid" }));
      svg.appendChild(el("text", { x: sx(xv), y: H - pad.b + 14, "text-anchor": "middle" }, fmt(xv, 1)));
      svg.appendChild(el("line", { x1: pad.l, y1: sy(yv), x2: W - pad.r, y2: sy(yv), class: "grid" }));
      svg.appendChild(el("text", { x: pad.l - 6, y: sy(yv) + 4, "text-anchor": "end" }, yfmt(yv)));
    }
    svg.appendChild(el("text", { x: (pad.l + W - pad.r) / 2, y: H - 4, "text-anchor": "middle" }, xlabel));
    svg.appendChild(el("text", { x: pad.l, y: pad.t - 8, "text-anchor": "start" }, ylabel));
  }
  function drawDisp(svg, z, mm) {
    svg.innerHTML = "";
    if (!z || !z.series || !z.series.t.length) return;
    const t = z.series.t, d = z.series.disp_px, sg = z.series.sigma_px.map(x => x || 0);
    const s = scales(svg, t, d.map((v, i) => v + sg[i]).concat(d.map((v, i) => v - sg[i])).concat([0]));
    axes(svg, s, "time (epoch units)", "displacement, px");
    const band = t.map((x, i) => `${s.sx(x)},${s.sy(d[i] + sg[i])}`).concat(t.map((x, i) => `${s.sx(x)},${s.sy(d[i] - sg[i])}`).reverse()).join(" ");
    svg.appendChild(el("polygon", { points: band, class: "band" }));
    svg.appendChild(el("polyline", { points: t.map((x, i) => `${s.sx(x)},${s.sy(d[i])}`).join(" "), class: "line" }));
    t.forEach((x, i) => svg.appendChild(el("circle", { cx: s.sx(x), cy: s.sy(d[i]), r: 2.5, class: "pt" })));
    if (z.ooa_time !== null && z.ooa_time !== undefined) {
      svg.appendChild(el("line", { x1: s.sx(z.ooa_time), y1: s.pad.t, x2: s.sx(z.ooa_time), y2: s.H - s.pad.b, class: "marker" }));
      svg.appendChild(el("text", { x: s.sx(z.ooa_time) + 4, y: s.pad.t + 12, class: "label" }, "onset of acceleration"));
    }
    svg.appendChild(el("text", { x: s.W - s.pad.r, y: s.pad.t - 8, "text-anchor": "end" }, `1 px = ${fmt(mm, 2)} mm`));
  }
  function drawIV(svg, z) {
    svg.innerHTML = "";
    const empty = $("iv-empty");
    if (!z || !z.inverse_velocity || !z.inverse_velocity.t.length) { empty.hidden = false; return; }
    empty.hidden = true;
    const t = z.inverse_velocity.t, iv = z.inverse_velocity.inv_v;
    const xs = [...t]; if (z.t_hi) xs.push(z.t_hi + (z.t_hi - t[0]) * 0.05);
    const s = scales(svg, xs, [...iv, 0]);
    axes(svg, s, "time (epoch units)", "1 / velocity", (v) => fmt(v, 1));
    if (z.t_lo !== null && z.t_hi !== null && z.t_lo !== undefined) {
      svg.appendChild(el("rect", { x: s.sx(z.t_lo), y: s.pad.t, width: Math.max(2, s.sx(z.t_hi) - s.sx(z.t_lo)), height: s.H - s.pad.t - s.pad.b, class: "window" }));
    }
    if (z.fit_line) {
      const f = (x) => z.fit_line.slope * x + z.fit_line.intercept;
      const xe = -z.fit_line.intercept / z.fit_line.slope;
      svg.appendChild(el("line", { x1: s.sx(t[0]), y1: s.sy(f(t[0])), x2: s.sx(xe), y2: s.sy(0), class: "fit" }));
      svg.appendChild(el("line", { x1: s.sx(xe), y1: s.pad.t, x2: s.sx(xe), y2: s.H - s.pad.b, class: "marker" }));
      svg.appendChild(el("text", { x: s.sx(xe) - 4, y: s.pad.t + 12, "text-anchor": "end", class: "label" }, `forecast t = ${fmt(xe, 1)}`));
    }
    t.forEach((x, i) => svg.appendChild(el("circle", { cx: s.sx(x), cy: s.sy(iv[i]), r: 3, class: "pt" })));
  }

  // ---- boot
  (async function boot() {
    try {
      const index = await getJSON(`${ROOT}/index.json`);
      const sel = $("site");
      sel.innerHTML = "";
      for (const s of index) { const o = document.createElement("option"); o.value = s.site; o.textContent = `${s.site} (${s.state})`; sel.appendChild(o); }
      const want = qs.get("site") || (index[0] && index[0].site);
      if (!want) { $("status-line").textContent = "No sites yet. Seed one with infra/scripts/seed_demo.py."; return; }
      sel.value = want;
      sel.addEventListener("change", () => loadSite(sel.value));
      await loadSite(want);
      setInterval(() => loadSite(sel.value).catch(() => {}), 15000);
    } catch (e) {
      $("status-line").textContent = `Could not load data from "${ROOT}": ${e.message}. For an offline demo open index.html?root=demo-data/public/sites after running seed_demo.py --local web/dashboard/demo-data.`;
      $("state-chip").textContent = "no data";
    }
  })();
})();
