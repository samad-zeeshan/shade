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
  const cell = (h) => (h < ZERO ? "0 h" : h < 1 ? `${Math.round(h * 60)} min` : `${Number(sig2(h))} h`);
  const words = (h) => (h < ZERO ? "no extra hours" : h < 1 ? `${Math.round(h * 60)} extra minutes`
    : Number(sig2(h)) === 1 ? "1 extra hour" : `${sig2(h)} extra hours`);
  const weather = (src) => (/open-meteo/i.test(src || "") ? "Real weather from Open-Meteo" : `Weather: ${src}`);

  // Thresholds match the planner's pitch: under 90 percent of the heat plan's hours counts as a gain, over 110 percent counts as a loss.
  function verdict(r) {
    const b = r.blind_extra_h, a = r.shade_extra_h;
    if (b < ZERO && a < ZERO) return "The heat plan and the shade plan need no extra hours.";
    if (a < ZERO) return "The shade plan needs no extra hours.";
    if (a > b * 1.1) return "The shade plan needs more extra hours on this day.";
    if (a <= b * 0.5) return "The shade plan needs less than half the extra hours.";
    if (a < b * 0.9) return "The shade plan needs fewer extra hours.";
    return r.morning_rh >= 50 ? "Shade helps little. Humid air sets the limit." : "Shade helps little on this day.";
  }

  function links() {
    document.querySelectorAll("[data-planner]").forEach((a) => { a.href = PLANNER; });
    document.querySelectorAll("[data-repo]").forEach((a) => { a.href = REPO_URL; });
  }

  // Big number, small unit. The number stays a bare text node so the count-up can rewrite it alone.
  function big(el, h) {
    const [num, unit] = cell(h).split(" ");
    const u = document.createElement("small");
    u.textContent = unit;
    el.replaceChildren(num, u);
  }

  // The sub line names the unsafe hours under the ban first. If there are none, it says what shade saves.
  function hero(r) {
    const saved = r.blind_extra_h - r.shade_extra_h;
    $("hero-meta").textContent = `${r.site}, ${r.city} · ${longDate(r.date)} · ${weather(r.source)}`;
    if (r.ban_over_h >= ZERO) $("hero-sub").textContent = "On this day, the midday ban alone does not keep workers safe.";
    else if (saved >= ZERO) $("hero-sub").textContent = "On this day, the shade plan needs fewer extra hours than the heat plan.";
    big($("hs-ban"), r.ban_over_h);
    big($("hs-blind"), r.blind_extra_h);
    big($("hs-shade"), r.shade_extra_h);
    $("hero-strip").hidden = false;
  }

  function pair(r) {
    big($("pair-b"), r.blind_extra_h);
    big($("pair-a"), r.shade_extra_h);
    $("pair-line").textContent = `On ${longDate(r.date)} in ${r.city}, the shade plan needs ${words(r.shade_extra_h)}. `
      + `The heat plan needs ${words(r.blind_extra_h)}. ${verdict(r)}`;
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

  // Keep the pill and the progress line readable when they sit over the orange end block.
  function pill() {
    const p = $("pill"), bar = $("progress");
    new IntersectionObserver(([e]) => {
      p.classList.toggle("flip", e.isIntersecting);
      bar.classList.toggle("flip", e.isIntersecting);
    }, { rootMargin: "0px 0px -94% 0px" }).observe($("end"));
  }

  // Runs before the data arrives, so the hero entrance hides its parts before the first paint.
  // `ready` resolves once runs.json has filled the page, and its `listed` promise once the sources list is in.
  function motion(ready) {
    if (!window.gsap || !window.ScrollTrigger || !window.SplitText) return;
    gsap.registerPlugin(ScrollTrigger, SplitText);
    const mm = gsap.matchMedia();

    mm.add("(prefers-reduced-motion: no-preference)", (ctx) => {
      gsap.defaults({ ease: "power3.out", duration: 0.9 });
      const lenis = window.Lenis ? new Lenis({ lerp: 0.1, smoothWheel: true, anchors: true }) : null;
      const raf = (t) => lenis.raf(t * 1000);
      if (lenis) {
        lenis.on("scroll", ScrollTrigger.update);
        gsap.ticker.add(raf);
        gsap.ticker.lagSmoothing(0);
      }

      // A reverted tween would leave a half-counted number, so cleanup puts the final text back.
      const counted = [];
      const count = (el, vars) => {
        const t = el.firstChild, end = t.nodeValue, dec = (end.split(".")[1] || "").length, box = { v: 0 };
        counted.push([t, end]);
        t.nodeValue = (0).toFixed(dec);
        return gsap.to(box, { v: Number(end), duration: 1.4, ...vars, onUpdate: () => { t.nodeValue = box.v.toFixed(dec); } });
      };
      // autoSplit splits again once the web fonts load, and keeps the progress of the returned tween.
      const split = (el, vars) => SplitText.create(el, {
        type: "lines", mask: "lines", linesClass: "line", autoSplit: true,
        onSplit: (self) => gsap.from(self.lines, { yPercent: 110, stagger: 0.08, ...vars }),
      });
      const list = (el) => el.children.length && gsap.from(el.children, {
        y: 24, opacity: 0, stagger: 0.08, scrollTrigger: { trigger: el, start: "top 85%", once: true },
      });
      const wipe = (el) => gsap.fromTo(el,
        { clipPath: () => (innerWidth > 900 ? "inset(6% 3% 0% 3%)" : "inset(4% 2% 0% 2%)") },
        { clipPath: "inset(0% 0% 0% 0%)", ease: "none", scrollTrigger: { trigger: el, start: "top bottom", end: "top 25%", scrub: true, invalidateOnRefresh: true } });

      // Hero entrance: the line, then the pitch, then the buttons and the map. The numbers come last, once the data is in.
      split(".hero-d", { duration: 1.1, delay: 0.1 });
      const intro = gsap.timeline({ delay: 0.45 })
        .from(["#hero-line", "#hero-sub"], { y: 16, opacity: 0, stagger: 0.08 })
        .from(".hero-cta", { y: 16, opacity: 0 }, "-=0.5")
        .fromTo(".hero-shot a", { clipPath: "inset(14% 0% 0% 0%)" }, { clipPath: "inset(0% 0% 0% 0%)", duration: 1.3 }, "<")
        .from(".hero-shot img", { scale: 1.08, duration: 1.5 }, "<");

      gsap.timeline({ defaults: { ease: "none" }, scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } })
        .to(".hero-shot", { y: -60 }, 0)
        .to(".hero-d", { y: -40, opacity: 0.3 }, 0);

      gsap.utils.toArray("main h2, .voice").forEach((el) => split(el, { scrollTrigger: { trigger: el, start: "top 85%", once: true } }));
      gsap.utils.toArray(".reveal").forEach((el) => gsap.from(el, { y: 32, opacity: 0, scrollTrigger: { trigger: el, start: "top 88%" } }));
      gsap.fromTo(".ruler-bar .ban", { scaleX: 0 }, { scaleX: 1, ease: "none", transformOrigin: "50% 50%", scrollTrigger: { trigger: ".ruler", start: "top 85%", end: "top 50%", scrub: true } });
      document.querySelectorAll(".uses").forEach(list);
      wipe($("end"));
      gsap.fromTo(".word", { yPercent: 40 }, { yPercent: 0, ease: "none", scrollTrigger: { trigger: ".end", start: "top bottom", end: "bottom bottom", scrub: true } });
      gsap.fromTo("#progress i", { scaleX: 0 }, { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: 0.3 } });

      ready.then((d) => ctx.add(() => {
        const strip = $("hero-strip");
        if (!strip.hidden) {
          const s = gsap.timeline()
            .from(strip.children, { "--rule": 0, stagger: 0.1, duration: 1 })
            .from(strip.querySelectorAll("dd, dt"), { y: 12, opacity: 0, stagger: 0.05, duration: 0.7 }, "<0.15")
            .add([...strip.querySelectorAll(".hs-n")].map((n) => count(n)), ">-0.2");
          // Late data finds the intro already gone from the global timeline, so the strip plays on its own.
          if (intro.progress() < 1) intro.add(s, "-=0.4");
        }
        if (!$("results").hidden) {
          wipe($("results"));
          [$("pair-b"), $("pair-a")].forEach((n) => count(n, { scrollTrigger: { trigger: ".pair", start: "top 85%", once: true } }));
          gsap.from("#runs-body tr", { y: 16, opacity: 0, stagger: 0.06, duration: 0.6, scrollTrigger: { trigger: ".runs", start: "top 85%" } });
        }
        ScrollTrigger.refresh();
        if (d) d.listed.then(() => ctx.add(() => { list($("src-list")); ScrollTrigger.refresh(); }));
      }));

      return () => {
        counted.forEach(([t, end]) => { t.nodeValue = end; });
        if (lenis) { gsap.ticker.remove(raf); gsap.ticker.lagSmoothing(500, 33); lenis.destroy(); }
      };
    });

    // The reading guide needs the sticky figure beside it, so wide screens only.
    // Steps and list share the 55% line, so the first step lights as the list goes live and the last stays lit until it leaves.
    mm.add("(min-width: 901px) and (prefers-reduced-motion: no-preference)", () => {
      const steps = document.querySelector(".steps");
      ScrollTrigger.create({ trigger: steps, start: "top 55%", end: "bottom 55%", toggleClass: { targets: steps, className: "live" } });
      steps.querySelectorAll("li").forEach((li) => ScrollTrigger.create({ trigger: li, start: "top 55%", end: "bottom 55%", toggleClass: "on" }));
    });

    document.fonts.ready.then(() => ScrollTrigger.refresh());
    const img = document.querySelector(".hero-shot img");
    if (!img.complete) img.addEventListener("load", () => ScrollTrigger.refresh(), { once: true });
  }

  // Resolves to null when there is no data, so the page stays text only.
  async function load() {
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
      // Wrapped in an object so the hero does not wait for the large run file.
      return { listed: sources(def.file).catch(() => {}) };
    } catch (err) {
      console.warn("story: no run data, showing the text-only page.", err);
      $("results").hidden = true;
      return null;
    } finally {
      document.documentElement.classList.remove("loading");
    }
  }

  links();
  pill();
  motion(load());
})();
