/*
 * Fill the story page from runs.json and add the scroll reveals.
 *
 * The page reads fine with no data and no motion, so each step can fail on its own.
 */
(() => {
  const PLANNER = "plan.html";
  const REPO_URL = "https://github.com/samad-zeeshan/shade";
  const $ = (id) => document.getElementById(id);
  const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const ZERO = 0.01;

  // Same rounding as the planner: two significant figures.
  function sig2(x) {
    if (x === 0) return "0";
    const d = Math.max(0, 1 - Math.floor(Math.log10(Math.abs(x))));
    return (Math.round(x * 10 ** d) / 10 ** d).toFixed(d);
  }
  const ymd = (iso) => iso.split("-").map(Number);
  const longDate = (iso) => { const [y, m, d] = ymd(iso); return `${d} ${MONTHS[m - 1]} ${y}`; };
  const shortDate = (iso) => { const [y, m, d] = ymd(iso); return `${d} ${MONTHS[m - 1].slice(0, 3)} ${y}`; };
  const cell = (h) => (h < ZERO ? "0 h" : h < 1 ? `${Math.round(h * 60)} min` : `${sig2(h)} h`);
  const words = (h) => (h < ZERO ? "no extra hours" : h < 1 ? `${Math.round(h * 60)} extra minutes`
    : sig2(h) === "1" ? "1 extra hour" : `${sig2(h)} extra hours`);
  const weather = (src) => (/open-meteo/i.test(src || "") ? "Real weather from Open-Meteo" : `Weather: ${src}`);

  // Thresholds match the planner's pitch: under 90 percent of the old hours counts as a gain.
  function verdict(r) {
    const b = r.blind_extra_h, a = r.shade_extra_h;
    if (b < ZERO && a < ZERO) return "Heat limits cost no overtime on this day.";
    if (a < ZERO) return "Shade removes all of the overtime.";
    if (a <= b * 0.5) return "Shade saves most of the overtime.";
    if (a < b * 0.9) return "Shade saves some of the overtime.";
    return r.morning_rh >= 50 ? "Shade changes little. Humid air sets the limit." : "Shade changes little on this day.";
  }

  function links() {
    document.querySelectorAll("[data-planner]").forEach((a) => { a.href = PLANNER; });
    document.querySelectorAll("[data-repo]").forEach((a) => { a.href = REPO_URL; });
  }

  // The hero number is the unsafe hours under the ban. If there are none, it falls back to the hours shade saves.
  function hero(r) {
    const saved = r.blind_extra_h - r.shade_extra_h;
    let n = 0, lab = "", line = "";
    if (r.ban_over_h >= ZERO) {
      n = r.ban_over_h;
      lab = "Crew hours over the heat limit with the midday ban alone";
      line = "Crews that follow only the midday work ban still spend hours in heat above the safe limit.";
    } else if (saved >= ZERO) {
      n = saved;
      lab = "Overtime hours saved by planning around shade";
      line = "Planning work around building shade cuts overtime on a hot day.";
    }
    $("hero-meta").textContent = `${r.site}, ${r.city} · ${longDate(r.date)} · ${weather(r.source)}`;
    if (!n) return;
    $("stat-n").textContent = sig2(n);
    $("stat-lab").textContent = lab;
    $("hero-line").textContent = line;
    document.documentElement.classList.add("has-stat");
  }

  function pair(r) {
    // Big number, small unit, as in the hero.
    const big = (el, h) => { const [num, unit] = cell(h).split(" "); const u = document.createElement("small"); u.textContent = unit; el.replaceChildren(num, u); };
    big($("pair-b"), r.blind_extra_h);
    big($("pair-a"), r.shade_extra_h);
    $("pair-line").textContent = `On ${longDate(r.date)} in ${r.city}, a plan that follows the shade needs ${words(r.shade_extra_h)}. `
      + `A plan that uses one site temperature needs ${words(r.blind_extra_h)}. ${verdict(r)}`;
  }

  function table(runs) {
    const heads = [...$("runs-head").children].map((th) => th.textContent);
    const body = $("runs-body");
    for (const r of runs) {
      const tr = document.createElement("tr");
      const vals = [null, shortDate(r.date), `${Math.round(r.morning_ta)} °C, ${r.morning_rh}% humidity`,
        cell(r.ban_over_h), cell(r.blind_extra_h), cell(r.shade_extra_h), verdict(r)];
      vals.forEach((v, i) => {
        const td = document.createElement("td");
        td.dataset.label = heads[i];
        if (i === 0) {
          const a = document.createElement("a");
          a.href = `${PLANNER}?run=${encodeURIComponent(r.id)}`;
          a.textContent = r.city;
          a.title = `Open ${r.site}, ${longDate(r.date)} in the planner`;
          td.append(a);
        } else td.textContent = v;
        if (i >= 1 && i <= 5) td.className = "n";
        tr.append(td);
      });
      body.append(tr);
    }
  }

  async function sources(file) {
    const res = await fetch(file);
    if (!res.ok) return;
    const list = $("src-list");
    for (const s of (await res.json()).meta.sources || []) {
      const li = document.createElement("li");
      const who = document.createElement("span"), yr = document.createElement("span");
      who.className = "who"; yr.className = "yr";
      who.textContent = s.short;
      who.title = s.citation;
      yr.textContent = (s.citation.match(/\((\d{4})\)/) || [])[1] || "";
      li.append(who, yr);
      list.append(li);
    }
    list.hidden = !list.children.length;
  }

  // Keep the pill readable when it sits over the orange end block.
  function pill() {
    const p = $("pill");
    new IntersectionObserver(([e]) => p.classList.toggle("flip", e.isIntersecting), { rootMargin: "0px 0px -94% 0px" }).observe($("end"));
  }

  function motion() {
    if (!window.gsap || !window.ScrollTrigger) return;
    gsap.registerPlugin(ScrollTrigger);
    gsap.matchMedia().add("(prefers-reduced-motion: no-preference)", () => {
      gsap.defaults({ ease: "power3.out", duration: 0.9 });
      const n = $("stat-n"), end = n.textContent;
      if (end) {
        const box = { v: 0 };
        gsap.to(box, { v: Number(end), duration: 1.6, ease: "power2.out", onUpdate: () => { n.textContent = String(Math.round(box.v)); }, onComplete: () => { n.textContent = end; } });
      }
      gsap.from(".dim i", { scaleX: 0, transformOrigin: (i) => (i ? "right" : "left"), duration: 1.4, delay: 0.2 });
      gsap.utils.toArray("main h2, .voice, .reveal, .steps .idx, .uses .idx").forEach((el) => {
        gsap.from(el, { y: 32, opacity: 0, scrollTrigger: { trigger: el, start: "top 88%" } });
      });
      if ($("runs-body").children.length) {
        gsap.from("#runs-body tr", { y: 16, opacity: 0, stagger: 0.06, duration: 0.6, scrollTrigger: { trigger: ".runs", start: "top 85%" } });
      }
    });
    document.fonts.ready.then(() => ScrollTrigger.refresh());
  }

  async function main() {
    links();
    pill();
    try {
      const res = await fetch("runs.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(`runs.json ${res.status}`);
      const idx = await res.json();
      const runs = idx.runs || [];
      const def = runs.find((r) => r.id === idx.default) || runs[0];
      if (!def) throw new Error("runs.json has no runs");
      hero(def);
      pair(def);
      table(runs);
      sources(def.file).catch(() => {});
    } catch (err) {
      console.warn("story: no run data, showing the text-only page.", err);
      $("results").hidden = true;
    }
    document.documentElement.classList.remove("loading");
    motion();
  }

  main();
})();
