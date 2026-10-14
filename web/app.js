/*
 * Play back the precomputed shade schedule: map, KPI tiles, worker timeline and scrubber, all driven by one slot index.
 */
(function () {
  "use strict";

  const INK = "#1a1a18";
  const HEAT = "#e4572e";
  const SHADE = "#2c6e9b";
  // The dot and strip ramp runs white to orange over 26..36 °C. Below 26 every class may work all hour,
  // above about 33 nobody may work at all, so this range spends the whole ramp on the part that matters.
  const RAMP_LO = 26, RAMP_HI = 36;
  const STEP_MS = 350;
  const BASEMAP = "https://tiles.openfreemap.org/styles/positron";
  const SCEN_ORDER = ["ban_only", "sun_blind", "shade_aware"];
  const TRADE_ORDER = ["steel", "concrete", "general", "electrical"];
  // 16 desaturated inks, one per task. Red, blue and orange hues are left out so bars never read as heat or shade.
  const TASK_INKS = [
    "#6b7a3a", "#7d5f7f", "#3f6b55", "#9a7b46", "#5c5470", "#8b6a55", "#4f6b3f", "#a08a5f",
    "#6f4f5e", "#5a7466", "#837a50", "#6e6488", "#3d5a48", "#9b7f86", "#5f5a3c", "#7a8f74",
  ];

  // Every visible string lives here so the wording can be reviewed in one place.
  function copy() {
    const hrs = (h) => (h === 0 ? "no" : h < 0.5 ? "less than one" : String(Math.round(h)));
    const cls = { light: "Light work", moderate: "Moderate work", heavy: "Heavy work", very_heavy: "Very heavy work" };
    const prose = { ban_only: "a blanket ban", sun_blind: "heat limits and one site temperature", shade_aware: "heat limits and per-spot shade" };
    return {
      title: "shade",
      site: (m) => `${m.site}, ${m.city}, ${longDate(m.date)}`,
      loadFail: "The schedule file could not be loaded, so there is nothing to show yet.",
      fallback: "The street map could not load, so only the buildings are drawn.",
      plotLabel: "Plot 7",
      play: "Play the day", pause: "Pause",
      tbTime: "Time", tbSun: "Sun height", tbAir: "Air temperature", tbHeat: "Average heat index on site",
      sunVal: (el) => (el <= 1 ? "below horizon" : `${Math.round(el)}°`),
      deg: (v) => `${v.toFixed(1)} °C`,
      mapKeyShadow: "Blue areas lie in the shadow of a building at the time shown.",
      mapKeyDots: "Each dot is a work spot. A more orange dot has a higher heat index (WBGT), which adds up air temperature, humidity, sun and wind. A thick ring means a crew works there now.",
      rampLo: `${RAMP_LO} °C`, rampHi: `${RAMP_HI} °C`,
      stripNote: "Each cell shows the average heat index on site for 15 minutes. More orange is hotter.",
      tlTitle: "Each row is one worker's day in 15-minute steps.",
      keyBan: "Midday ban", keyOvertime: "Overtime", keyViolation: "Over the heat limit",
      trade: { steel: "Steel fixers", concrete: "Concrete crew", general: "General labour", electrical: "Electricians" },
      cls,
      tipClass: "Type of work", tipHeat: "Heat index", tipShade: "In shade", tipWho: "Worker", tipWhen: "Time",
      tipOver: "This worker was over the heat limit here.",
      scenKey: (i) => String(i + 1),
      pitch: (M) => {
        const b = M.ban_only, s = M.sun_blind, a = M.shade_aware;
        const out = [];
        out.push(`With ${prose.ban_only}, crews spent ${hrs(b.violation_hours)} worker-hours over the heat limit.`);
        let sb = `With ${prose.sun_blind}, crews needed ${hrs(s.overtime_hours)} hours of overtime`;
        sb += s.unscheduled_hours > 0 ? ` and left ${hrs(s.unscheduled_hours)} hours of work undone.` : ".";
        out.push(sb);
        let sa = `With ${prose.shade_aware}, crews needed ${hrs(a.overtime_hours)} hours of overtime`;
        sa += a.violation_hours === 0 ? " and nobody went over the limit." : `, but ${hrs(a.violation_hours)} worker-hours were over the limit.`;
        out.push(sa);
        const before = s.overtime_hours + s.unscheduled_hours, after = a.overtime_hours + a.unscheduled_hours;
        if (before > 0 && after < before * 0.9) out.push(`Using the shade cuts late or unfinished work by ${sig2(100 * (1 - after / before))}%, which is a clear gain.`);
        else if (before > 0) out.push("Using the shade barely changes late or unfinished work here, so the gain is small.");
        return out;
      },
      kpi: {
        overtime: { lab: "Overtime after 17:00", unit: "h",
          say: (m) => m.overtime_hours === 0 ? "Every crew finished inside the shift, so there is no extra cost."
            : m.overtime_hours < 8 ? "Some crews stayed past the end of the shift, which adds a little cost."
            : "Crews stayed long past the end of the shift, which is costly." },
        violation: { lab: "Over the heat limit", unit: "h",
          say: (m) => m.violation_hours === 0 ? "Nobody worked past the heat limit. That is safe."
            : m.violation_hours < 4 ? "A few crews briefly worked past the heat limit. That is not safe."
            : "Crews worked past the heat limit for many hours. That is unsafe." },
        done: { lab: "Tasks done by 17:00", unit: (n) => `of ${n}`,
          say: (m, n) => m.tasks_done_by_17 === n ? "Every task was finished before the shift ended. That is on plan."
            : m.unscheduled_hours > 0 ? "Some work never fit into the day, so the job falls behind."
            : "Some tasks ran past the end of the shift, so they finished late." },
        peak: { lab: "Hottest spot worked", unit: "°C",
          say: (m) => m.peak_wbgt_worked > 32.5 ? "Someone worked in heat where every task should stop. That is unsafe."
            : "All work stayed below the heat where every task must stop. That is safe." },
      },
    };
  }

  // ---------- helpers ----------
  function sig2(x) {
    if (x === 0) return "0";
    const d = Math.max(0, 1 - Math.floor(Math.log10(Math.abs(x))));
    return (Math.round(x * 10 ** d) / 10 ** d).toFixed(d);
  }
  function longDate(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    const names = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    return `${d} ${names[m - 1]} ${y}`;
  }
  function clock(slot, slotMin, first) {
    const [h0, m0] = first.split(":").map(Number);
    const t = h0 * 60 + m0 + slot * slotMin;
    return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
  }
  function heatColor(v) {
    const f = Math.min(1, Math.max(0, (v - RAMP_LO) / (RAMP_HI - RAMP_LO)));
    const mix = (a, b) => Math.round(a + (b - a) * f);
    return `rgb(${mix(255, 0xe4)},${mix(255, 0x57)},${mix(255, 0x2e)})`;
  }
  const svgNS = "http://www.w3.org/2000/svg";
  function el(tag, attrs, parent) {
    const n = document.createElementNS(svgNS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function fillTip(tip, title, rows, note) {
    tip.replaceChildren();
    const b = document.createElement("b");
    b.textContent = title;
    tip.appendChild(b);
    for (const [k, v] of rows) {
      const r = document.createElement("div");
      r.className = "row";
      const a = document.createElement("span"), c = document.createElement("span");
      a.textContent = k; c.textContent = v;
      r.append(a, c);
      tip.appendChild(r);
    }
    if (note) {
      const p = document.createElement("div");
      p.style.cssText = `margin-top:6px;color:${HEAT}`;
      p.textContent = note;
      tip.appendChild(p);
    }
    tip.hidden = false;
  }
  function placeTip(tip, box, x, y) {
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${x + 14 + w > box.width ? x - w - 14 : x + 14}px`;
    tip.style.top = `${y + 14 + h > box.height ? y - h - 14 : y + 14}px`;
  }

  // ---------- state ----------
  const C = copy();
  let D, N, map, tasksById, taskIdx;
  let slot = 8, scen = "ban_only", playing = false, focusTask = null;
  const derived = {};

  async function main() {
    for (const n of document.querySelectorAll("[data-copy]")) n.textContent = C[n.dataset.copy];
    try {
      const r = await fetch("data.json");
      if (!r.ok) throw new Error(r.status);
      D = await r.json();
    } catch (e) {
      document.getElementById("pitch").textContent = C.loadFail;
      return;
    }
    N = D.meta.n_slots;
    tasksById = Object.fromEntries(D.tasks.map((t) => [t.id, t]));
    taskIdx = Object.fromEntries(D.tasks.map((t, i) => [t.id, i]));
    document.getElementById("site").textContent = C.site(D.meta);
    for (const k of SCEN_ORDER) derived[k] = derive(D.scenarios[k]);

    buildHeader();
    buildPitch();
    buildKpis();
    buildScrubber();
    buildTimeline();
    // Watch the timeline box itself, not the window, because the KPI row above can change its height.
    let tlSize = "";
    new ResizeObserver(debounce(() => {
      const h = document.getElementById("tl"), k = `${h.clientWidth}x${h.clientHeight}`;
      if (k !== tlSize) { tlSize = k; buildTimeline(); }
    }, 80)).observe(document.getElementById("tl"));
    bindKeys();
    await buildMap();
    setSlot(slot, true);
  }

  function debounce(fn, ms) {
    let t;
    return () => { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  // Precompute per scenario which worker-slots break the heat rule and which tasks are worked in each slot.
  // Same rule as the backend metric: a 4-slot window over 48 load units flags every worked slot in it.
  // A null load means the heat is past the 25% column, so one slot alone already breaks the budget.
  function derive(sc) {
    const viol = sc.assign.map(() => new Uint8Array(N));
    const workedBySlot = Array.from({ length: N }, () => new Set());
    sc.assign.forEach((row, wi) => {
      row.forEach((tid, s) => { if (tid) workedBySlot[s].add(tid); });
      for (let s0 = 0; s0 + 4 <= N; s0++) {
        let tot = 0;
        for (let s = s0; s < s0 + 4; s++) {
          const tid = row[s];
          if (tid) { const ld = tasksById[tid].load[s]; tot += ld == null ? 49 : ld; }
        }
        if (tot > 48) for (let s = s0; s < s0 + 4; s++) if (row[s]) viol[wi][s] = 1;
      }
    });
    return { viol, workedBySlot };
  }

  // ---------- header and KPIs ----------
  function buildHeader() {
    const seg = document.getElementById("scenarios");
    SCEN_ORDER.forEach((k, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("role", "radio");
      b.dataset.k = k;
      const key = document.createElement("span");
      key.className = "k";
      key.textContent = C.scenKey(i);
      const lab = document.createElement("span");
      lab.textContent = D.scenarios[k].label;
      b.append(key, lab);
      b.addEventListener("click", () => setScenario(k));
      seg.appendChild(b);
    });
    markScenario();
  }
  function markScenario() {
    for (const b of document.querySelectorAll("#scenarios button")) b.setAttribute("aria-checked", String(b.dataset.k === scen));
  }

  function buildPitch() {
    const M = Object.fromEntries(SCEN_ORDER.map((k) => [k, D.scenarios[k].metrics]));
    document.getElementById("pitch").textContent = C.pitch(M).join(" ");
  }

  const kpiState = {};
  function buildKpis() {
    const box = document.getElementById("kpis");
    for (const key of ["overtime", "violation", "done", "peak"]) {
      const d = document.createElement("div");
      d.className = "kpi";
      d.innerHTML = '<div class="lab"></div><div class="val"><span class="n"></span><small></small></div><p class="say"></p>';
      d.querySelector(".lab").textContent = C.kpi[key].lab;
      box.appendChild(d);
      kpiState[key] = { node: d, cur: 0 };
    }
    renderKpis(false);
  }
  function kpiValue(key, m) {
    return { overtime: m.overtime_hours, violation: m.violation_hours, done: m.tasks_done_by_17, peak: m.peak_wbgt_worked }[key];
  }
  function kpiFormat(key, v) {
    if (key === "done") return String(Math.round(v));
    if (key === "peak") return v.toFixed(1);
    return sig2(v);
  }
  // Count-up over 400 ms with an ease-out so the eye lands on the final value, not the motion.
  function renderKpis(animate) {
    const m = D.scenarios[scen].metrics, n = D.tasks.length;
    for (const key in kpiState) {
      const st = kpiState[key], spec = C.kpi[key];
      const to = kpiValue(key, m), from = st.cur;
      const num = st.node.querySelector(".n");
      st.node.querySelector("small").textContent = typeof spec.unit === "function" ? spec.unit(n) : spec.unit;
      st.node.querySelector(".say").textContent = spec.say(m, n);
      st.node.querySelector(".val").classList.toggle("bad", key === "violation" && to > 0);
      st.cur = to;
      if (!animate) { num.textContent = kpiFormat(key, to); continue; }
      const t0 = performance.now();
      const tick = (now) => {
        const f = Math.min(1, (now - t0) / 400), e = 1 - (1 - f) ** 3;
        num.textContent = kpiFormat(key, f === 1 ? to : from + (to - from) * e);
        if (f < 1 && st.cur === to) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }

  // ---------- timeline ----------
  let tl = {};
  function workerRows() {
    const rows = [];
    TRADE_ORDER.forEach((tr) => D.workers.forEach((w, wi) => { if (w.trades[0] === tr) rows.push({ w, wi, tr }); }));
    D.workers.forEach((w, wi) => { if (!TRADE_ORDER.includes(w.trades[0])) rows.push({ w, wi, tr: w.trades[0] }); });
    return rows;
  }

  function buildTimeline() {
    const host = document.getElementById("tl");
    host.replaceChildren();
    host.style.minHeight = "";
    const W = host.clientWidth, H = host.clientHeight;
    const rows = workerRows();
    const groups = [...new Set(rows.map((r) => r.tr))];
    const L = 76, T = 20, GAP = 18;
    const colW = (W - L - 2) / N;
    const rowH = Math.max(16, Math.min(24, (H - T - 4 - GAP * groups.length) / rows.length));
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" }, host);
    const defs = el("defs", {}, svg);
    // Overtime hatch: thin 45 degree strokes in muted ink, wide spacing so bars on top still read.
    const pat = el("pattern", { id: "hatch", width: 5, height: 5, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
    el("line", { x1: 0, y1: 0, x2: 0, y2: 5, stroke: "#b3b1a9", "stroke-width": 0.7 }, pat);

    let y = T;
    const yOf = new Map();
    let prevTr = null;
    const heads = [];
    for (const r of rows) {
      if (r.tr !== prevTr) { y += GAP; heads.push({ y, tr: r.tr }); }
      yOf.set(r.wi, y);
      prevTr = r.tr;
      y += rowH;
    }
    const bottom = y;
    // On short screens the rows keep a readable minimum height and the panel scrolls instead of squashing them.
    const SH = Math.max(H, bottom + 4);
    svg.setAttribute("viewBox", `0 0 ${W} ${SH}`);
    svg.style.height = `${SH}px`;
    host.style.minHeight = `${SH}px`;
    const x = (s) => L + s * colW;
    const [b0, b1] = D.meta.ban_slots, se = D.meta.shift_end_slot;

    const bg = el("g", {}, svg);
    el("rect", { x: x(b0), y: T - 4, width: (b1 + 1 - b0) * colW, height: bottom - T + 4, fill: "#ebeae5" }, bg);
    el("rect", { x: x(se), y: T - 4, width: (N - se) * colW, height: bottom - T + 4, fill: "url(#hatch)" }, bg);
    for (let s = 0; s <= N; s += 12) {
      el("line", { x1: x(s), x2: x(s), y1: T - 4, y2: bottom, stroke: s === se ? "#8b8b84" : "#e9e8e2", "stroke-width": 1 }, bg);
      const t = el("text", { x: x(s), y: 10, "text-anchor": s === 0 ? "start" : s === N ? "end" : "middle" }, bg);
      t.textContent = clock(s, D.meta.slot_minutes, D.meta.first_slot);
    }
    // Each trade group gets a small heading and a hairline in the gap above it, like a drawing schedule.
    for (const h of heads) {
      const t = el("text", { x: 0, y: h.y - 5, class: "grp" }, bg);
      t.textContent = (C.trade[h.tr] || h.tr).toUpperCase();
      el("line", { x1: Math.max(L, t.getComputedTextLength() + 8), x2: W, y1: h.y - 8.5, y2: h.y - 8.5, stroke: "#d6d4cc", "stroke-width": 1, "shape-rendering": "crispEdges" }, bg);
    }
    for (const r of rows) {
      const name = el("text", { x: 0, y: yOf.get(r.wi) + rowH / 2 + 3.5, class: "wname" }, bg);
      name.textContent = r.w.name;
    }

    const layerHost = el("g", {}, svg);
    const play = el("line", { y1: T - 6, y2: bottom + 2, stroke: INK, "stroke-width": 1, "shape-rendering": "crispEdges" }, svg);
    const tip = document.createElement("div");
    tip.className = "tip";
    tip.hidden = true;
    host.appendChild(tip);

    tl = { svg, layerHost, play, tip, x, colW, rowH, yOf, layer: null, host };
    drawLayer(false);
    movePlayhead();

    svg.addEventListener("mousemove", onBarHover);
    svg.addEventListener("mouseleave", () => { tip.hidden = true; highlightDot(null); });
  }

  // One layer per scenario. On switch the new layer fades in over the old one, then the old one is removed.
  function drawLayer(fade) {
    const sc = D.scenarios[scen], dv = derived[scen];
    const g = el("g", { class: "layer bar-g" }, null);
    if (fade) g.style.opacity = 0;
    const { x, colW, rowH, yOf } = tl;
    const bh = rowH - 7;
    sc.assign.forEach((row, wi) => {
      const ry = yOf.get(wi) + 3.5;
      let runStart = 0;
      for (let s = 0; s <= N; s++) {
        const tid = row[s];
        if (tid) {
          // A 1 px gap only where the task changes, so a run reads as one block and a switch stays visible.
          const join = row[s + 1] === tid ? 0.5 : -1;
          el("rect", { x: x(s) + 0.5, y: ry, width: Math.max(1, colW + join), height: bh, fill: TASK_INKS[taskIdx[tid] % 16], "data-t": tid, "data-w": wi, "data-s": s }, g);
          if (dv.viol[wi][s]) el("line", { x1: x(s) + 0.5, x2: x(s) + colW - 0.5, y1: ry + bh + 1.5, y2: ry + bh + 1.5, stroke: HEAT, "stroke-width": 1.25 }, g);
        }
        if (s === N || row[s] !== row[runStart]) {
          const id = row[runStart], len = s - runStart;
          if (id && len * colW >= 40) {
            const t = el("text", { x: x(runStart) + (len * colW) / 2, y: ry + bh / 2 + 3, "text-anchor": "middle", class: "runlab", "data-t": id }, g);
            t.textContent = id;
          }
          runStart = s;
        }
      }
    });
    tl.layerHost.appendChild(g);
    const old = tl.layer;
    tl.layer = g;
    applyFocus();
    if (fade) {
      g.getBoundingClientRect(); // commit opacity 0 so the transition has a start value
      g.style.opacity = 1;
      if (old) { old.style.opacity = 0; setTimeout(() => old.remove(), 320); }
    } else if (old) old.remove();
  }

  // Playhead sits at the centre of the current slot column. The scrubber thumb uses the same (s + 0.5) / N
  // rule, so the two lines up across the page.
  function movePlayhead() {
    if (!tl.play) return;
    const px = tl.x(slot) + tl.colW / 2;
    tl.play.setAttribute("x1", px);
    tl.play.setAttribute("x2", px);
  }

  function onBarHover(e) {
    const t = e.target;
    const tid = t.getAttribute && t.getAttribute("data-t");
    if (!tid || t.tagName !== "rect") { tl.tip.hidden = true; highlightDot(null); return; }
    const task = tasksById[tid], s = +t.dataset.s, wi = +t.dataset.w;
    fillTip(tl.tip, task.name, [
      [C.tipWho, D.workers[wi].name],
      [C.tipWhen, `${clock(s, D.meta.slot_minutes, D.meta.first_slot)} to ${clock(s + 1, D.meta.slot_minutes, D.meta.first_slot)}`],
      [C.tipHeat, C.deg(task.wbgt[s])],
      [C.tipShade, `${Math.round(task.shade[s] * 100)}%`],
    ], derived[scen].viol[wi][s] ? C.tipOver : null);
    const box = tl.host.getBoundingClientRect();
    placeTip(tl.tip, box, e.clientX - box.left, e.clientY - box.top);
    highlightDot(tid);
  }

  function applyFocus() {
    if (!tl.layer) return;
    tl.host.classList.toggle("focus", !!focusTask);
    for (const n of tl.layer.querySelectorAll("[data-t]")) n.classList.toggle("on", n.getAttribute("data-t") === focusTask);
  }

  // ---------- scrubber ----------
  let thumb, clockEl, track;
  function buildScrubber() {
    thumb = document.getElementById("thumb");
    clockEl = document.getElementById("clock");
    track = document.getElementById("track");
    const ticks = document.getElementById("ticks");
    for (let s = 0; s <= N; s += 4) {
      const sp = document.createElement("span");
      sp.style.left = `${(s / N) * 100}%`;
      sp.textContent = clock(s, D.meta.slot_minutes, D.meta.first_slot).slice(0, 2);
      if (s === 0 || s === N) sp.textContent = clock(s, D.meta.slot_minutes, D.meta.first_slot);
      if (s === 4 || s === N - 4) continue; // the full end labels need this room
      ticks.appendChild(sp);
    }
    const strip = document.getElementById("strip");
    for (let s = 0; s < N; s++) {
      let sum = 0;
      for (const t of D.tasks) sum += t.wbgt[s];
      const i = document.createElement("i");
      i.style.background = heatColor(sum / D.tasks.length);
      strip.appendChild(i);
    }
    const fromX = (cx) => {
      const r = track.getBoundingClientRect();
      return Math.max(0, Math.min(N - 1, Math.floor(((cx - r.left) / r.width) * N)));
    };
    track.addEventListener("pointerdown", (e) => {
      track.setPointerCapture(e.pointerId);
      stop();
      setSlot(fromX(e.clientX));
    });
    track.addEventListener("pointermove", (e) => { if (track.hasPointerCapture(e.pointerId)) setSlot(fromX(e.clientX)); });
    document.getElementById("play").addEventListener("click", toggle);
    setPlayIcon();
  }
  function setPlayIcon() {
    const b = document.getElementById("play");
    b.setAttribute("aria-label", playing ? C.pause : C.play);
    b.title = playing ? C.pause : C.play;
    b.innerHTML = playing
      ? '<svg viewBox="0 0 12 12"><rect x="1.5" y="1" width="3" height="10"/><rect x="7.5" y="1" width="3" height="10"/></svg>'
      : '<svg viewBox="0 0 12 12"><path d="M2 1 L11 6 L2 11 Z"/></svg>';
  }

  // ---------- play loop ----------
  let last = 0, acc = 0, frames = [];
  function toggle() { playing ? stop() : start(); }
  function start() {
    if (slot >= N - 1) setSlot(0);
    playing = true;
    last = performance.now();
    acc = 0;
    frames = [];
    setPlayIcon();
    requestAnimationFrame(loop);
  }
  function stop() {
    if (!playing) return;
    playing = false;
    setPlayIcon();
    reportFrames();
  }
  function loop(now) {
    if (!playing) return;
    const dt = now - last;
    last = now;
    frames.push(dt);
    acc += dt;
    if (acc >= STEP_MS) {
      acc -= STEP_MS;
      if (slot >= N - 1) { stop(); return; }
      setSlot(slot + 1);
    }
    requestAnimationFrame(loop);
  }
  // Frame pacing is logged on pause so playback smoothness can be checked from the console.
  function reportFrames() {
    if (frames.length < 3) return;
    const f = frames.slice(1).sort((a, b) => a - b);
    const mean = f.reduce((a, b) => a + b, 0) / f.length;
    const p95 = f[Math.floor(f.length * 0.95)], worst = f[f.length - 1];
    window.__shadeFrames = { n: f.length, mean, p95, worst };
    console.info(`[shade] frames=${f.length} mean=${mean.toFixed(2)}ms p95=${p95.toFixed(2)}ms worst=${worst.toFixed(2)}ms`);
  }

  // ---------- keyboard ----------
  function bindKeys() {
    window.addEventListener("keydown", (e) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.code === "Space") { e.preventDefault(); toggle(); }
      else if (e.key === "ArrowRight") { e.preventDefault(); stop(); setSlot(Math.min(N - 1, slot + 1)); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); stop(); setSlot(Math.max(0, slot - 1)); }
      else if (e.key >= "1" && e.key <= "3") setScenario(SCEN_ORDER[+e.key - 1]);
    });
  }

  // ---------- slot and scenario ----------
  function setSlot(s, force) {
    if (s === slot && !force) return;
    slot = s;
    const t = clock(s, D.meta.slot_minutes, D.meta.first_slot);
    clockEl.textContent = t;
    thumb.style.left = `${((s + 0.5) / N) * 100}%`;
    track.setAttribute("aria-valuenow", s);
    track.setAttribute("aria-valuetext", t);
    movePlayhead();
    const sun = D.sun[s], w = D.weather[s];
    let mean = 0;
    for (const tk of D.tasks) mean += tk.wbgt[s];
    mean /= D.tasks.length;
    document.getElementById("tb-time").textContent = t;
    document.getElementById("tb-sun").textContent = C.sunVal(sun.elevation);
    document.getElementById("tb-air").textContent = C.deg(w.ta);
    document.getElementById("tb-heat").textContent = C.deg(mean);
    updateMap();
  }

  function setScenario(k) {
    if (!k || k === scen) return;
    scen = k;
    markScenario();
    renderKpis(true);
    drawLayer(true);
    updateMap();
  }

  // ---------- map ----------
  const FALLBACK_STYLE = {
    version: 8, sources: {},
    layers: [{ id: "ground", type: "background", paint: { "background-color": "#f1f0eb" } }],
  };
  let night = null, plotCenter;

  async function loadStyle() {
    // Fetch the basemap style ourselves with a timeout. If it fails the demo still runs on a plain ground colour.
    try {
      const ctl = new AbortController();
      const to = setTimeout(() => ctl.abort(), 5000);
      const r = await fetch(BASEMAP, { signal: ctl.signal });
      clearTimeout(to);
      if (!r.ok) throw new Error(r.status);
      return { style: await r.json(), ok: true };
    } catch (e) {
      return { style: FALLBACK_STYLE, ok: false };
    }
  }

  async function buildMap() {
    if (!window.maplibregl) return;
    const lon = D.tasks.reduce((a, t) => a + t.lon, 0) / D.tasks.length;
    const lat = D.tasks.reduce((a, t) => a + t.lat, 0) / D.tasks.length;
    plotCenter = [lon, lat];
    const d = 0.02;
    // At night the whole site counts as shade, so the shadow layer gets one large square instead of nothing.
    night = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]] } };

    const { style, ok } = await loadStyle();
    if (!ok) {
      const n = document.createElement("div");
      n.className = "fallback-note";
      n.textContent = C.fallback;
      document.querySelector(".mapwrap").appendChild(n);
    }
    map = new maplibregl.Map({
      container: "map", style, center: plotCenter, zoom: 16.9, pitch: 55, bearing: -20,
      attributionControl: { compact: true }, antialias: true, fadeDuration: 0,
    });
    // Tile errors from the basemap are expected offline. Handling them here keeps them out of the console.
    map.on("error", () => {});
    await new Promise((res) => map.once("load", res));
    // Compact attribution opens by default and would cover the title block. It stays one click away.
    const attrib = document.querySelector(".maplibregl-ctrl-attrib");
    if (attrib) attrib.classList.remove("maplibregl-compact-show");

    for (const l of map.getStyle().layers) {
      // Labels and the basemap's own buildings would fight the drawing, so they are hidden.
      if (l.type === "symbol" || l["source-layer"] === "building") map.setLayoutProperty(l.id, "visibility", "none");
    }
    map.addSource("shadow", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
    map.addSource("bld", { type: "geojson", data: D.buildings });
    map.addSource("tasks", { type: "geojson", data: taskFC() });
    // The plot is painted in paper colour so the road interchange under the site disappears.
    // It sits below the shadow layer so shadows still fall across it.
    const plot = plotPolygon(18);
    map.addSource("plot", { type: "geojson", data: plot });
    map.addLayer({ id: "plot-fill", type: "fill", source: "plot", paint: { "fill-color": "#fafaf7", "fill-opacity": 1 } });
    map.addLayer({ id: "plot-line", type: "line", source: "plot", paint: { "line-color": INK, "line-width": 1, "line-dasharray": [4, 3] } });
    // An HTML marker avoids needing a glyph server, which the offline fallback style lacks.
    const north = plot.geometry.coordinates[0].reduce((a, c) => (c[1] > a[1] ? c : a));
    const lab = document.createElement("div");
    lab.className = "plot-label mono";
    lab.textContent = C.plotLabel;
    new maplibregl.Marker({ element: lab, anchor: "bottom" }).setLngLat(north).addTo(map);
    map.addLayer({ id: "shadow", type: "fill", source: "shadow", paint: { "fill-color": SHADE, "fill-opacity": 0.22, "fill-antialias": false } });
    map.addLayer({ id: "bld-3d", type: "fill-extrusion", source: "bld", paint: {
      "fill-extrusion-color": "#efeee9", "fill-extrusion-height": ["get", "height"], "fill-extrusion-base": 0, "fill-extrusion-opacity": 0.94,
    } });
    map.addLayer({ id: "bld-line", type: "line", source: "bld", paint: { "line-color": INK, "line-width": 0.6, "line-opacity": 0.55 } });
    map.addLayer({ id: "tasks", type: "circle", source: "tasks", paint: {
      "circle-radius": 7,
      "circle-color": ["interpolate", ["linear"], ["get", "wbgt"], RAMP_LO, "#ffffff", RAMP_HI, HEAT],
      "circle-stroke-color": INK,
      "circle-stroke-width": ["case", ["get", "worked"], 3, 1],
      "circle-pitch-alignment": "map",
    } });

    const tip = document.getElementById("tip");
    const wrap = document.querySelector(".mapwrap");
    map.on("mousemove", "tasks", (e) => {
      map.getCanvas().style.cursor = "pointer";
      const t = tasksById[e.features[0].properties.id];
      fillTip(tip, t.name, [
        [C.tipClass, C.cls[t.cls] || t.cls],
        [C.tipHeat, C.deg(t.wbgt[slot])],
        [C.tipShade, `${Math.round(t.shade[slot] * 100)}%`],
      ]);
      placeTip(tip, wrap.getBoundingClientRect(), e.point.x, e.point.y);
    });
    map.on("mouseleave", "tasks", () => { map.getCanvas().style.cursor = ""; tip.hidden = true; });
    map.on("click", (e) => {
      const f = map.queryRenderedFeatures(e.point, { layers: ["tasks"] })[0];
      focusTask = f && f.properties.id !== focusTask ? f.properties.id : null;
      highlightDot(focusTask);
      applyFocus();
    });
    map.on("rotate", updateCompass);
  }

  // Convex hull of the task points, grown by `buf` metres. Work is done in local metres around the
  // plot centre, which is accurate to well under a metre at site scale. Growing each hull corner into a
  // ring of points and taking the hull again gives a buffer with rounded corners.
  function plotPolygon(buf) {
    const [lon0, lat0] = plotCenter;
    const mx = 111320 * Math.cos((lat0 * Math.PI) / 180), my = 110540;
    const hull = (pts) => {
      pts = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
      const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
      const half = (list) => {
        const h = [];
        for (const p of list) {
          while (h.length >= 2 && cross(h[h.length - 2], h[h.length - 1], p) <= 0) h.pop();
          h.push(p);
        }
        h.pop();
        return h;
      };
      return half(pts).concat(half(pts.reverse()));
    };
    const core = hull(D.tasks.map((t) => [(t.lon - lon0) * mx, (t.lat - lat0) * my]));
    const ring = [];
    for (const [x, y] of core) for (let k = 0; k < 24; k++) {
      const a = (k / 24) * 2 * Math.PI;
      ring.push([x + buf * Math.cos(a), y + buf * Math.sin(a)]);
    }
    const out = hull(ring).map(([x, y]) => [lon0 + x / mx, lat0 + y / my]);
    out.push(out[0]);
    return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [out] } };
  }

  function taskFC() {
    const worked = derived[scen].workedBySlot[slot];
    return {
      type: "FeatureCollection",
      features: D.tasks.map((t) => ({
        type: "Feature", properties: { id: t.id, wbgt: t.wbgt[slot], worked: worked.has(t.id) },
        geometry: { type: "Point", coordinates: [t.lon, t.lat] },
      })),
    };
  }

  // Slot changes only swap source data and paint values. Layers are created once in buildMap,
  // because re-adding layers on each step would re-upload buffers and stutter during play.
  function updateMap() {
    if (!map || !map.getSource("shadow")) return;
    const sh = D.shadows[slot];
    map.getSource("shadow").setData(sh.night || !sh.geometry ? night : { type: "Feature", properties: {}, geometry: sh.geometry });
    map.getSource("tasks").setData(taskFC());
    const sun = D.sun[slot];
    // Light follows the sun so the lit faces of the towers turn through the day.
    map.setLight({ anchor: "map", position: [1.5, sun.azimuth, Math.min(89, Math.max(5, 90 - sun.elevation))], intensity: 0.28, color: "#ffffff" });
    updateCompass();
  }

  function updateCompass() {
    if (!map) return;
    const rose = document.getElementById("compass-rose");
    rose.setAttribute("transform", `rotate(${-map.getBearing()})`);
    const sun = D.sun[slot];
    document.getElementById("sun-tick").setAttribute("transform", `rotate(${sun.azimuth})`);
    document.getElementById("compass").classList.toggle("night", sun.elevation <= 1);
  }

  function highlightDot(id) {
    if (!map || !map.getLayer("tasks")) return;
    const target = id || focusTask;
    const v = target ? ["case", ["==", ["get", "id"], target], 1, 0.2] : 1;
    map.setPaintProperty("tasks", "circle-opacity", v);
    map.setPaintProperty("tasks", "circle-stroke-opacity", v);
  }

  main();
})();
