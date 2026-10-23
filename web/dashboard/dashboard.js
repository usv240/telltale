/* TellTale dashboard: plain JS, no build step, no framework.
   Reads sites/index.json, sites/<site>/{site,series,forecast,agentlog,decisions}.json and overlay
   PNGs from the data root (default "sites"; override with ?root=demo-data/public/sites). */
(function () {
  "use strict";
  const qs = new URLSearchParams(location.search);
  const ROOT = (qs.get("root") || "sites").replace(/\/$/, "");
  const $ = (id) => document.getElementById(id);
  const isNum = (x) => x !== null && x !== undefined && !Number.isNaN(Number(x));
  const fmt = (x, d = 2) => isNum(x) ? Number(x).toFixed(d) : "–";
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // Python's %g (6 significant digits, trailing zeros stripped): artifact folders are named with it.
  const gfmt = (x) => { const n = Number(x); if (n === 0) return "0"; let s = n.toPrecision(6); if (s.includes("e")) return String(n); if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, ""); return s; };
  const median = (a) => { const s = [...a].sort((x, y) => x - y); const m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
  const lastV = (z) => z && z.series && z.series.v_sma.length ? z.series.v_sma[z.series.v_sma.length - 1] : NaN;

  const STATE = {
    QUIET: ["Quiet", "pill-neutral"], MOVING: ["Moving", "pill-neutral"],
    ACCELERATING: ["Accelerating", "pill-warning"], CRITICAL: ["Critical", "pill-negative"],
  };
  const REASON = {
    OK: ["Measured", "pill-neutral"], REFERENCE: ["Reference", "pill-neutral"], REVIEW: ["Review", "pill-warning"],
    BLIND: ["Blind", "pill-warning"], BLURRED: ["Blurred", "pill-warning"], CAMERA_EVENT: ["Camera event", "pill-warning"],
    LOW_INLIERS: ["Low inliers", "pill-warning"], UNSTABLE: ["Unstable", "pill-warning"],
  };
  const VERDICT = { CONFIRMED: ["Confirmed", "pill-negative"], FALSE_ALARM: ["False alarm", "pill-neutral"], INCONCLUSIVE: ["Inconclusive", "pill-warning"] };
  const EVENT = { E_ANOMALY: "Acceleration", E_JUMP: "Sudden step", E_CAMERA: "Camera event", E_QUALITY: "Quality drop" };
  const pill = (pair, fallback) => { const [t, c] = pair || [fallback, "pill-neutral"]; return `<span class="pill ${c}">${esc(t)}</span>`; };

  // ---- theme: system -> light -> dark
  const THEMES = ["", "light", "dark"];
  const applyTheme = (t) => {
    if (t) document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme;
    $("theme").setAttribute("aria-label", `Colour theme: ${t || "system"}`);
    $("theme").dataset.tip = `Theme: ${t || "system"}`;
  };
  applyTheme(qs.get("theme") || localStorage.getItem("telltale-theme") || "");
  $("theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || "";
    const next = THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length];
    applyTheme(next); localStorage.setItem("telltale-theme", next);
  });

  async function getJSON(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }

  let lastData = null;
  let replayIndex = null;   // null = live; otherwise index into series.records
  let playTimer = null;
  let showAllAgent = false, showAllEpochs = false;
  // ?event=<t> (or latest) opens that investigation with its evidence, e.g. from the duty page.
  let deepEvent = qs.get("event");

  // Time context per site: Mukilteo epochs are days since a known date (in site.json notes).
  function timeContext(cfg) {
    const m = /days since (\d{4}-\d{2}-\d{2})/.exec(cfg.notes || "");
    if (!m) return { unit: "time units", unitShort: "", date: null };
    const start = new Date(m[1] + "T00:00:00Z");
    return { unit: "days", unitShort: " d", date: (t) => new Date(start.getTime() + Math.round(t) * 864e5).toISOString().slice(0, 10) };
  }

  async function loadSite(site) {
    const base = `${ROOT}/${site}`;
    const [cfg, series, fc] = await Promise.all([
      getJSON(`${base}/site.json`), getJSON(`${base}/series.json`), getJSON(`${base}/forecast.json`)]);
    let agentlog = { events: [] }, decisions = { decisions: [] };
    try { agentlog = await getJSON(`${base}/agentlog.json`); } catch (e) { /* none yet */ }
    try { decisions = await getJSON(`${base}/decisions.json`); } catch (e) { /* none yet */ }
    lastData = { site, base, cfg, series, fc, agentlog, decisions };
    setupReplay(lastData);
    if (replayIndex === null) render(lastData);
  }

  function setupReplay(d) {
    const box = $("replay"), s = $("scrub");
    const n = d.series.records.length;
    if (n < 2) { box.hidden = true; return; }
    box.hidden = false;
    s.max = String(n - 1);
    if (replayIndex === null) { s.value = String(n - 1); $("scrub-label").textContent = `Live · ${n} epochs`; }
  }

  async function showEpoch(i) {
    const d = lastData;
    if (!d) return;
    const recs = d.series.records;
    i = Math.max(0, Math.min(recs.length - 1, i));
    const r = recs[i];
    let fc;
    try { fc = await getJSON(`${d.base}/epochs/${gfmt(r.t)}/forecast.json`); } catch (e) { fc = d.fc; }
    const series = { records: recs.slice(0, i + 1) };
    const ctx = timeContext(d.cfg);
    $("scrub-label").textContent = `Epoch ${i + 1} of ${recs.length} · t = ${fmt(r.t, 1)}${ctx.date ? " · " + ctx.date(r.t) : ""}`;
    const agentlog = { events: (d.agentlog.events || []).filter((e) => e.t <= r.t) };
    render({ ...d, series, fc, agentlog, replay: true });
  }

  $("scrub").addEventListener("input", (ev) => {
    const i = Number(ev.target.value);
    const live = i === lastData.series.records.length - 1;
    replayIndex = live ? null : i;
    if (live) { $("scrub-label").textContent = `Live · ${lastData.series.records.length} epochs`; render(lastData); }
    else showEpoch(i);
  });
  $("scrub-live").addEventListener("click", () => {
    if (playTimer) { clearInterval(playTimer); playTimer = null; $("scrub-play").textContent = "Play"; }
    replayIndex = null;
    $("scrub").value = String(lastData.series.records.length - 1);
    $("scrub-label").textContent = `Live · ${lastData.series.records.length} epochs`;
    render(lastData);
  });
  $("scrub-play").addEventListener("click", () => {
    if (playTimer) { clearInterval(playTimer); playTimer = null; $("scrub-play").textContent = "Play"; return; }
    let i = 0;
    replayIndex = 0;
    $("scrub-play").textContent = "Pause";
    const n0 = lastData.series.records.length;
    const step = n0 > 120 ? Math.ceil(n0 / 120) : 1;      // long records play in about a minute
    playTimer = setInterval(async () => {
      const n = lastData.series.records.length;
      if (i >= n) { clearInterval(playTimer); playTimer = null; $("scrub-play").textContent = "Play"; replayIndex = null; render(lastData); return; }
      $("scrub").value = String(i);
      replayIndex = i === n - 1 ? null : i;
      await showEpoch(i);
      i += step;
    }, 450);
  });
  $("agent-more").addEventListener("click", () => { showAllAgent = !showAllAgent; if (lastData) render(lastData); });
  $("epochs-more").addEventListener("click", () => { showAllEpochs = !showAllEpochs; if (lastData) render(lastData); });

  // ------------------------------------------------------------------ render
  function render(d) {
    const { site, base, cfg, series, fc } = d;
    const ctx = timeContext(cfg);
    const zoneName = Object.keys(fc.zones || {})[0];
    const z = zoneName ? fc.zones[zoneName] : null;
    const recs = series.records;
    const last = recs[recs.length - 1];
    const lastUsable = [...recs].reverse().find((r) => r.usable && r.zones && r.zones[zoneName] && r.zones[zoneName].n_valid > 0) || null;
    const state = fc.state || "QUIET";
    const mm = cfg.mm_per_px || 1;
    const metric = mm !== 1;
    const lz = lastUsable ? lastUsable.zones[zoneName] : null;
    const tNow = last ? last.t : null;
    const hasForecast = z && isNum(z.tf);

    // title row
    $("site-title").textContent = site;
    const sp = $("state-pill");
    const [stText, stCls] = STATE[state] || [state, "pill-neutral"];
    sp.className = `pill ${stCls}`;
    sp.textContent = stText + (last && !last.usable ? ` · last epoch ${(REASON[last.reason] || [last.reason])[0].toLowerCase()}` : "");
    $("cool-badge").hidden = !(fc.runtime && fc.runtime.cool);
    $("status-line").innerHTML = finding(state, z, zoneName, lz, recs, ctx, mm, metric);
    const usableN = recs.filter((r) => r.usable).length;
    $("scope-line").textContent = [
      `Zone ${zoneName || "–"}`, `${cfg.reference_mode === "chained" ? "Chained" : "Fixed"} reference`,
      metric ? `1 px = ${fmt(mm, 2)} mm` : "Scale not surveyed (pixels)",
      `${recs.length} epochs, ${usableN} usable`, ctx.date && last ? `last ${ctx.date(last.t)}` : null,
      d.replay ? "Replaying" : null].filter(Boolean).join(" · ");

    renderApproval(fc.approval, d);

    // KPIs
    setKpi("k-window", hasForecast ? `${fmt(z.t_lo, 1)}–${fmt(z.t_hi, 1)}` : "–", !hasForecast,
      hasForecast ? `median t = ${fmt(z.tf, 1)}${ctx.date ? " (" + ctx.date(z.tf) + ")" : ""} · fit R² ${fmt(z.r2, 2)}` : "No sustained acceleration");
    setKpi("k-horizon", hasForecast ? `${fmt(z.horizon, 1)}<span class="unit">${ctx.unit}</span>` : "–", !hasForecast,
      hasForecast ? `from t = ${fmt(tNow, 1)}, the last epoch` : "Appears with a forecast");
    const dispV = lz ? (metric ? lz.magnitude * mm : lz.magnitude) : null;
    const dispS = lz ? (metric ? lz.sigma * mm : lz.sigma) : null;
    setKpi("k-disp", lz ? `${fmt(dispV, 2)}<span class="unit">${metric ? "mm" : "px"}</span>` : "–", !lz,
      lz ? `± ${fmt(dispS, 2)} ${metric ? "mm" : "px"} since the reference` : "No usable epoch yet");
    const v = lastV(z);
    setKpi("k-vel", isNum(v) ? `${fmt(Math.abs(v) * (metric ? mm : 1), 3)}<span class="unit">${metric ? "mm" : "px"} / ${ctx.unit === "days" ? "day" : "unit"}</span>` : "–", !isNum(v),
      "3-epoch moving average");
    const ooa = z && isNum(z.ooa_time);
    setKpi("k-ooa", ooa ? `t = ${fmt(z.ooa_time, 1)}` : "Not detected", !ooa,
      ooa ? (ctx.date ? ctx.date(z.ooa_time) : "acceleration gates passed") : "Both onset gates must pass");
    const reasons = {};
    for (const r of recs) if (!r.usable) reasons[r.reason] = (reasons[r.reason] || 0) + 1;
    setKpi("k-epochs", `${usableN}<span class="unit">of ${recs.length}</span>`, false,
      Object.keys(reasons).length ? Object.entries(reasons).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${n} ${(REASON[k] || [k])[0].toLowerCase()}`).join(" · ") : "None unusable");

    // panel meta
    $("iv-meta").textContent = hasForecast ? `fit R² ${fmt(z.r2, 3)} · ${z.methods ? Object.keys(z.methods).length : 1} methods` : "No forecast: no sustained acceleration";
    $("disp-meta").textContent = metric ? `1 px = ${fmt(mm, 2)} mm` : "pixels";
    $("cam-meta").textContent = lastUsable ? `t = ${fmt(lastUsable.t, 1)}${ctx.date ? " · " + ctx.date(lastUsable.t) : ""}` : "";

    // camera
    const img = $("overlay");
    const src = lastUsable && lastUsable.overlay ? `${base}/${lastUsable.overlay}` : "";
    if (img.getAttribute("src") !== src) img.setAttribute("src", src);
    $("overlay-cap").textContent = lastUsable
      ? `Grey is no motion; deeper blue is more, up to ${fmt(lz.magnitude, 2)} px in the zone. Arrows show direction, enlarged.`
      : "No usable epoch to show yet.";

    // health
    const covs = recs.filter((r) => r.field).map((r) => r.field.coverage);
    const times = recs.map((r) => r.timing && r.timing.total_s).filter((x) => x);
    const stab = last && last.stabilize ? last.stabilize : (lastUsable && lastUsable.stabilize) || null;
    $("h-cov").textContent = covs.length ? `${fmt(100 * covs[covs.length - 1], 0)} % now, ${fmt(100 * median(covs), 0)} % median` : "–";
    $("h-model").textContent = stab ? `${stab.refine_model || "coarse"} · residual ${fmt(Math.hypot(...(stab.residual || [0, 0]).map(Number)), 3)} px · scatter ${fmt(stab.scatter, 3)} px` : "–";
    $("h-time").textContent = times.length ? `${fmt(median(times), 2)} median · ${fmt(Math.max(...times), 2)} max` : "–";
    const rt = fc.runtime || {};
    $("h-inst").textContent = `${rt.instance_type || "local run"} · ${rt.machine || "–"} · ${rt.threads || "–"} threads${rt.ami_id ? " · " + rt.ami_id : ""}`;
    $("h-cv").textContent = `${rt.opencv_version || "?"} · ${rt.cv2_file || "?"} · ${rt.build_hash || "?"}`;
    $("health-meta").textContent = `${usableN} of ${recs.length} epochs usable`;

    // epoch table, newest first, capped
    const tb = $("epochs").querySelector("tbody");
    const rows = [...recs].reverse();
    const shown = showAllEpochs ? rows : rows.slice(0, 6);
    tb.innerHTML = shown.map((r) => {
      const zz = r.zones ? r.zones[zoneName] : null;
      const has = zz && isNum(zz.magnitude) && r.usable;
      const disp = has ? (metric ? `${fmt(zz.magnitude * mm, 2)} mm` : `${fmt(zz.magnitude, 3)} px`) : "–";
      const sig = has ? (metric ? fmt(zz.sigma * mm, 2) : fmt(zz.sigma, 3)) : "–";
      return `<tr class="${r.usable ? "" : "unusable"}"><td>${fmt(r.t, 1)}${ctx.date ? ` <span class="hint">${ctx.date(r.t)}</span>` : ""}</td>` +
        `<td>${pill(REASON[r.reason], r.reason)}</td><td class="num">${disp}</td><td class="num">${sig}</td>` +
        `<td class="num">${r.field ? fmt(100 * r.field.coverage, 0) + " %" : "–"}</td>` +
        `<td>${r.stabilize && r.stabilize.refine_model ? esc(r.stabilize.refine_model) : "–"}</td>` +
        `<td class="num">${r.timing ? fmt(r.timing.total_s, 2) : "–"}</td></tr>`;
    }).join("");
    const em = $("epochs-more");
    em.hidden = rows.length <= 6;
    em.textContent = showAllEpochs ? "Show the latest 6" : `Show all ${rows.length} epochs`;

    const hasIV = z && z.inverse_velocity && z.inverse_velocity.t.length;
    $("h-iv").textContent = hasIV ? "Failure forecast" : "Daily motion";
    if (hasIV) drawIV($("chart-iv"), z, tNow, ctx);
    else drawDaily($("chart-iv"), z, d.agentlog, metric ? mm : 1, metric, ctx);
    drawDisp($("chart-disp"), z, mm, metric, ctx);
    renderAgent(d, ctx);
  }

  function setKpi(id, html, empty, sub) {
    const el = $(id);
    el.innerHTML = html;
    el.classList.toggle("is-empty", !!empty);
    $(id + "-sub").textContent = sub || "";
  }

  function finding(state, z, zoneName, lz, recs, ctx, mm, metric) {
    if (!z) return "No measurements yet for this site.";
    const unit = ctx.unit;
    const amount = lz ? (metric ? `${fmt(lz.magnitude * mm, 1)} mm` : `${fmt(lz.magnitude, 2)} px`) : "–";
    if (state === "CRITICAL") return `<strong>Zone ${esc(zoneName)} is forecast to fail between t = ${fmt(z.t_lo, 1)} and ${fmt(z.t_hi, 1)}, ${fmt(z.horizon, 1)} ${unit} from the last epoch.</strong> Nothing has been sent to the public; a person decides.`;
    if (state === "ACCELERATING") return isNum(z.tf)
      ? `<strong>Zone ${esc(zoneName)} has been accelerating since t = ${fmt(z.ooa_time, 1)}.</strong> Forecast window t = ${fmt(z.t_lo, 1)} to ${fmt(z.t_hi, 1)}, fit R² ${fmt(z.r2, 2)}.`
      : `<strong>Zone ${esc(zoneName)} has been accelerating since t = ${fmt(z.ooa_time, 1)}.</strong> Too few accelerating epochs for a forecast yet.`;
    if (state === "MOVING") return `<strong>Zone ${esc(zoneName)} has moved ${amount} since the reference</strong>${recs[0] && recs[0].t !== undefined ? "" : ""}, with no sustained acceleration.`;
    return `<strong>No significant movement in zone ${esc(zoneName)}</strong> over ${recs.length} epochs.`;
  }

  function renderApproval(ap, d) {
    const act = $("approval-actions"), note = $("decision-note");
    act.innerHTML = ""; note.hidden = true;
    if (!ap || !ap.required) return;
    const decided = (d.decisions.decisions || []).filter((x) => x.t >= ap.episode_start).sort((a, b) => (a.at < b.at ? 1 : -1))[0];
    if (decided || ap.status !== "pending") {
      const action = decided ? decided.action : ap.status;
      const at = decided ? decided.at : ap.decided_at;
      note.hidden = false;
      note.textContent = `Decision recorded: ${action === "approve" || action === "approved" ? "public alert approved" : "dismissed as a false alarm"} at ${String(at).replace("T", " ").replace("Z", " UTC")}${decided && decided.source ? " from " + decided.source : ""}.`;
      return;
    }
    if (ap.links && ap.links.approve) {
      act.innerHTML = `<a class="btn btn-primary" href="${esc(ap.links.approve)}" target="_blank" rel="noopener">Approve public alert</a>` +
        `<a class="btn btn-secondary" href="${esc(ap.links.dismiss)}" target="_blank" rel="noopener">Dismiss</a>`;
    } else {
      act.innerHTML = `<button class="btn btn-primary" type="button" disabled title="Signed links are issued by the deployed stack">Approve public alert</button>`;
      note.hidden = false;
      note.textContent = "Offline demo: the deployed stack e-mails signed approve and dismiss links to the duty contact.";
    }
  }

  function renderAgent(d, ctx) {
    const list = $("agent-events"), empty = $("agent-empty"), more = $("agent-more");
    const events = [...(d.agentlog.events || [])].reverse();
    empty.hidden = events.length > 0;
    const counts = {};
    for (const e of events) counts[e.verdict] = (counts[e.verdict] || 0) + 1;
    $("agent-meta").textContent = events.length
      ? Object.entries(counts).map(([k, n]) => `${n} ${(VERDICT[k] || [k])[0].toLowerCase()}`).join(" · ")
      : "";
    let target = null;
    if (deepEvent && events.length) {
      target = deepEvent === "latest" ? events[0] : events.find((e) => Math.abs(e.t - Number(deepEvent)) < 1e-3) || null;
      if (target && events.indexOf(target) >= 4) showAllAgent = true;
    }
    const shown = showAllAgent ? events : events.slice(0, 4);
    const openKeys = new Set([...list.querySelectorAll("details[open]")].map((x) => x.dataset.t));
    list.innerHTML = "";
    for (const e of shown) {
      const li = document.createElement("li");
      const det = document.createElement("details");
      det.dataset.t = String(e.t);
      const when = `t = ${fmt(e.t, 1)}${ctx.date ? " · " + ctx.date(e.t) : ""}`;
      det.innerHTML = `<summary>${pill(VERDICT[e.verdict], e.verdict)}<span class="event-title">${esc(EVENT[e.event] || e.event)} at ${esc(when)}</span>` +
        `<span class="event-meta">${e.n_tool_calls} calls · ${e.paged_human ? "person paged" : "no page"} · ${fmt(e.seconds, 0)} s</span></summary>` +
        `<div class="event-body"><p class="event-summary">${esc((e.summary || "").replace(/\*\*/g, ""))}</p><div class="evidence" hidden></div><details class="calls"><summary>Every tool call, with its arguments and result</summary><ol class="trace"><li>Loading the trace…</li></ol></details></div>`;
      det.addEventListener("toggle", async () => {
        if (!det.open || det.dataset.loaded) return;
        det.dataset.loaded = "1";
        const ol = det.querySelector(".trace");
        try {
          const tr = await getJSON(`${d.base}/agent/${gfmt(e.t)}.json`);
          // The fields the agent re-measured, as images: the evidence behind the verdict.
          const ev = tr.calls.filter((c) => c.tool === "remeasure" && c.result && c.result.evidence_png);
          const box = det.querySelector(".evidence");
          if (ev.length) {
            box.innerHTML = `<p class="evidence-title">What the agent measured again</p><div class="evidence-row">` + ev.map((c) => {
              const r = c.result;
              const against = r.reference === "previous" ? `the previous epoch (t = ${fmt(r.reference_t, 1)})`
                : r.reference === "reference" ? "the site reference" : esc(r.reference);
              const z = Object.values(r.zones || {})[0] || {};
              const coh = z.coherence != null ? `, coherence ${fmt(z.coherence, 2)}` : "";
              return `<figure><img src="${d.base}/${esc(r.evidence_png)}" alt="Displacement field of epoch ${fmt(r.t, 1)} measured against ${against}" loading="lazy">` +
                `<figcaption>Against ${against}: <b>${fmt(z.magnitude, 2)} px</b>${coh}</figcaption></figure>`;
            }).join("") + `</div>`;
            box.hidden = false;
          }
          ol.innerHTML = tr.calls.map((c) => {
            const res = JSON.stringify(c.result);
            const args = Object.entries(c.args).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(", ");
            return `<li><b>${esc(c.tool)}</b>(${esc(args)}) <code>${esc(res.length > 360 ? res.slice(0, 360) + "…" : res)}</code></li>`;
          }).join("");
        } catch (err) { ol.innerHTML = "<li>Trace unavailable.</li>"; }
      });
      if (openKeys.has(String(e.t)) || e === target) det.open = true;
      if (e === target) {
        deepEvent = null;
        setTimeout(() => list.closest(".panel").scrollIntoView({ block: "start" }), 300);
      }
      li.appendChild(det);
      list.appendChild(li);
    }
    more.hidden = events.length <= 4;
    more.textContent = showAllAgent ? "Show the latest 4" : `Show all ${events.length} investigations`;
  }

  // ------------------------------------------------------------------ charts (SVG, ink chrome, one data hue)
  const NS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function niceTicks(lo, hi, n = 4) {
    const span = hi - lo || 1;
    const raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function frame(svg, xs, ys, yLabel, opts = {}) {
    const vb = svg.viewBox.baseVal, W = vb.width, H = vb.height;
    const pad = { l: 44, r: 12, t: 22, b: 26 };
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (x1 === x0) x1 = x0 + 1;
    if (y1 === y0) y1 = y0 + 1;
    if (opts.zeroY) y0 = Math.min(0, y0);
    y1 += (y1 - y0) * 0.06;
    const sx = (x) => pad.l + (x - x0) / (x1 - x0) * (W - pad.l - pad.r);
    const sy = (y) => H - pad.b - (y - y0) / (y1 - y0) * (H - pad.t - pad.b);
    for (const v of niceTicks(y0, y1, 4)) {
      svg.appendChild(el("line", { x1: pad.l, y1: sy(v), x2: W - pad.r, y2: sy(v), class: v === 0 ? "axis-line" : "grid-line" }));
      svg.appendChild(el("text", { x: pad.l - 6, y: sy(v) + 4, "text-anchor": "end" }, Math.abs(v) >= 100 ? v.toFixed(0) : String(+v.toFixed(2))));
    }
    for (const v of niceTicks(x0, x1, 5)) {
      svg.appendChild(el("text", { x: sx(v), y: H - 8, "text-anchor": "middle" }, String(+v.toFixed(1))));
    }
    svg.appendChild(el("text", { x: pad.l, y: 12, "text-anchor": "start" }, yLabel));
    return { sx, sy, W, H, pad, x0, x1 };
  }
  function drawDisp(svg, z, mm, metric, ctx) {
    svg.innerHTML = "";
    if (!z || !z.series || !z.series.t.length) return;
    const k = metric ? mm : 1;
    const t = z.series.t, d = z.series.disp_px.map((v) => v * k), sg = z.series.sigma_px.map((x) => (x || 0) * k);
    const s = frame(svg, t, d.map((v, i) => v + sg[i]).concat(d.map((v, i) => v - sg[i])), `displacement, ${metric ? "mm" : "px"} · t in ${ctx.unit}`, { zeroY: true });
    const band = t.map((x, i) => `${s.sx(x)},${s.sy(d[i] + sg[i])}`).concat(t.map((x, i) => `${s.sx(x)},${s.sy(d[i] - sg[i])}`).reverse()).join(" ");
    svg.appendChild(el("polygon", { points: band, class: "band" }));
    if (isNum(z.ooa_time)) {
      svg.appendChild(el("line", { x1: s.sx(z.ooa_time), y1: s.pad.t, x2: s.sx(z.ooa_time), y2: s.H - s.pad.b, class: "marker-soft" }));
      const flip = s.sx(z.ooa_time) > s.W * 0.6;
      svg.appendChild(el("text", { x: s.sx(z.ooa_time) + (flip ? -5 : 5), y: s.pad.t + 10, "text-anchor": flip ? "end" : "start", class: "label" }, "onset of acceleration"));
    }
    svg.appendChild(el("polyline", { points: t.map((x, i) => `${s.sx(x)},${s.sy(d[i])}`).join(" "), class: "series" }));
    if (t.length <= 60) t.forEach((x, i) => svg.appendChild(el("circle", { cx: s.sx(x), cy: s.sy(d[i]), r: 2.2, class: "dot" })));
  }
  function drawIV(svg, z, tNow, ctx) {
    svg.innerHTML = "";
    const empty = $("iv-empty");
    if (!z || !z.inverse_velocity || !z.inverse_velocity.t.length) { empty.hidden = false; svg.style.display = "none"; return; }
    empty.hidden = true; svg.style.display = "";
    const t = z.inverse_velocity.t, iv = z.inverse_velocity.inv_v;
    const xs = [...t];
    if (isNum(z.t_hi)) xs.push(z.t_hi);
    if (isNum(z.t_lo)) xs.push(z.t_lo);
    const s = frame(svg, xs, [...iv, 0], `1 / velocity · t in ${ctx.unit}`, { zeroY: true });
    if (isNum(z.t_lo) && isNum(z.t_hi)) {
      svg.appendChild(el("rect", { x: s.sx(z.t_lo), y: s.pad.t, width: Math.max(2, s.sx(z.t_hi) - s.sx(z.t_lo)), height: s.H - s.pad.t - s.pad.b, class: "window" }));
    }
    if (z.fit_line) {
      const f = (x) => z.fit_line.slope * x + z.fit_line.intercept;
      const xe = -z.fit_line.intercept / z.fit_line.slope;
      svg.appendChild(el("line", { x1: s.sx(t[0]), y1: s.sy(f(t[0])), x2: s.sx(xe), y2: s.sy(0), class: "fit" }));
    }
    if (isNum(z.tf)) {
      svg.appendChild(el("line", { x1: s.sx(z.tf), y1: s.pad.t, x2: s.sx(z.tf), y2: s.H - s.pad.b, class: "marker" }));
      const right = s.sx(z.tf) > s.W * 0.7;
      svg.appendChild(el("text", { x: s.sx(z.tf) + (right ? -6 : 6), y: s.pad.t + 12, "text-anchor": right ? "end" : "start", class: "label-hue" },
        `failure t = ${fmt(z.t_lo, 1)}–${fmt(z.t_hi, 1)}`));
    }
    t.forEach((x, i) => svg.appendChild(el("circle", { cx: s.sx(x), cy: s.sy(iv[i]), r: 2.8, class: "dot" })));
  }

  // When there is no forecast, the panel shows what the instrument did measure: each epoch's
  // step in the zone, with the steps the agent confirmed in the data hue.
  function drawDaily(svg, z, agentlog, k, metric, ctx) {
    svg.innerHTML = "";
    const empty = $("iv-empty");
    if (!z || !z.series || z.series.t.length < 3) { empty.hidden = false; svg.style.display = "none"; return; }
    empty.hidden = true; svg.style.display = "";
    const t = z.series.t, d = z.series.disp_px;
    const steps = [];
    for (let i = 1; i < t.length; i++) steps.push({ t: t[i], v: Math.abs(d[i] - d[i - 1]) * k });
    const confirmed = new Set((agentlog.events || []).filter((e) => e.verdict === "CONFIRMED").map((e) => Math.round(e.t * 1000)));
    const s = frame(svg, [t[0], t[t.length - 1]], [0, ...steps.map((p) => p.v)], `step per epoch, ${metric ? "mm" : "px"} · t in ${ctx.unit}`, { zeroY: true });
    const bw = Math.max(1.5, (s.W - s.pad.l - s.pad.r) / Math.max(steps.length, 1) * 0.7);
    for (const p of steps) {
      const hit = confirmed.has(Math.round(p.t * 1000));
      svg.appendChild(el("rect", { x: s.sx(p.t) - bw / 2, y: s.sy(p.v), width: bw, height: Math.max(0.5, s.sy(0) - s.sy(p.v)), class: hit ? "bar-hit" : "bar" }));
    }
    const n = steps.filter((p) => confirmed.has(Math.round(p.t * 1000))).length;
    svg.appendChild(el("text", { x: s.W - s.pad.r, y: 12, "text-anchor": "end", class: "label-hue" }, `${n} steps confirmed by the agent`));
  }

  // ------------------------------------------------------------------ boot
  (async function boot() {
    try {
      const index = await getJSON(`${ROOT}/index.json`);
      const sel = $("site");
      sel.innerHTML = "";
      for (const s of index) {
        const o = document.createElement("option");
        o.value = s.site;
        o.textContent = `${s.site} · ${(STATE[s.state] || [s.state])[0].toLowerCase()}`;
        sel.appendChild(o);
      }
      const want = qs.get("site") || (index[0] && index[0].site);
      if (!want) { $("status-line").textContent = "No sites yet. Seed one with infra/scripts/seed_demo.py."; return; }
      sel.value = want;
      sel.addEventListener("change", () => {
        replayIndex = null; showAllAgent = false; showAllEpochs = false;
        const u = new URL(location.href); u.searchParams.set("site", sel.value); history.replaceState(null, "", u);
        loadSite(sel.value);
      });
      await loadSite(want);
      setInterval(() => { if (replayIndex === null && !playTimer) loadSite(sel.value).catch(() => {}); }, 15000);
    } catch (e) {
      $("status-line").textContent = `Could not load data from "${ROOT}": ${e.message}. For an offline demo, open index.html?root=demo-data/public/sites after running seed_demo.py --local web/dashboard/demo-data.`;
      $("state-pill").textContent = "No data";
    }
  })();
})();
