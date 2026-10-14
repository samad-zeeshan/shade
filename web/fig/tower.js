/**
 * Tower: a tapering tower at the far corner of a square plot, and eight pegs
 * standing on the plot. The pointer is the sun: its x sets the hour from 06:00
 * to 18:00, and the tower's shadow, a dim plate on the ground, swings across
 * the plot on a spring. Pegs inside the shadow stand up; pegs in the sun lean
 * over, staggered outwards from the shadow's edge. The slider is the tower's
 * height, in metres.
 *
 * The pattern: one continuous value (the hour) drives a field, and each peg
 * makes a discrete choice from it. Pegs never move their feet, and the choice
 * reads the springs' targets, so a moving shadow cannot flip it.
 */
const {
  Cam, clamp, facing, fit, hull, lerp, open, poly, prism, proj, rad, ringAt, rings, rrect, run, circ,
  spring, stepS, tween, tset, tval, tdone, disposer, mk, pointer, put, register, solid,
} = HL;

const PL = 124, PB = 6, TC = 19, BH = 13, TH = 7, CAP = 9, CAPZ = 4, ZK = 1.5;
const PR = 3, PH = 18, HR = 4.3, HZ = 3.5, LEAN = 58, REST = 8, STEP = 45;
// Feet are fixed: three sit in the 08:00 shadow, one waits for the long evening one.
const PEGS = [[44, 28, -40], [57, 31, -55], [70, 37, -35], [28, 56, -60], [62, 63, -45], [96, 52, -30], [44, 92, -50], [88, 94, -40]];

/** Sun elevation in degrees: a sine over the day, 85 at its peak at 12:30. */
const elev = (t) => Math.max(4, 85 * Math.sin((Math.PI * (t - 6)) / 13));
/** Which way the shadow runs on the ground: +x in the morning, swinging to +y by evening. */
const dirOf = (t) => { const a = rad(lerp(6, 84, (t - 6) / 12)); return [Math.cos(a), Math.sin(a)]; };
/** The shadow's reach from the tower's centre, clamped so its far end stays on the plot (rule 03). */
function reach(t, Z) {
  const [dx, dy] = dirOf(t), lim = PL - 5 - CAP - TC;
  return Math.min((Z + CAPZ) / Math.tan(rad(elev(t))), lim / dx, lim / dy);
}
/** How far a point is inside the shadow (positive) or outside it (negative), in world units. */
function inside(px, py, t, Z) {
  const [dx, dy] = dirOf(t), L = reach(t, Z), qx = px - TC, qy = py - TC;
  const s = qx * dx + qy * dy, l = Math.abs(qx * dy - qy * dx);
  const w = lerp(BH, CAP, clamp(s / L, 0, 1));
  return Math.min(w - l, s + BH, L + CAP - s);
}

function mount({ stage, svg, read }, value) {
  const bag = disposer();
  const C = Cam(45, 0.5, 1.5);
  fit(C, [[0, 0, -PB], [PL, PL, -PB], [PL, 0, -PB], [0, PL, -PB], [TC, TC, 44 * ZK + CAPZ]], 200, 172);
  const P = proj(C), front = facing(C);
  const hour = spring(REST), zs = spring(value * ZK);
  let drawn = "", act = null;

  const g = mk("g", {}, svg);
  const [pr, pi] = rings(0, 0, PL, PL, 9, 2.2);
  put(solid(g), prism(P, front, pr, pi, -PB, 0));
  // The shadow lies on the plot, so it is painted before everything that stands on it.
  const shade = mk("path", {}, g);
  const foot = rrect(TC - BH, TC - BH, TC + BH, TC + BH, 4, 4), top = rrect(TC - TH, TC - TH, TC + TH, TC + TH, 2.5, 4);
  const inner = rrect(TC - TH + 1.2, TC - TH + 1.2, TC + TH - 1.2, TC + TH - 1.2, 1.5, 4);
  const [capR, capI] = rings(TC - CAP, TC - CAP, TC + CAP, TC + CAP, 3, 1.4);
  const shaft = solid(g), cap = solid(g);

  // Pegs after the tower: every foot is nearer the viewer than the tower's back corner.
  const pegs = PEGS.map(([x, y, la]) => ({ x, y, ld: [Math.cos(rad(la)), Math.sin(rad(la))] }))
    .sort((a, b) => a.x + a.y - (b.x + b.y));
  for (const p of pegs) {
    p.post = solid(g); p.head = solid(g);
    p.lean = tween(inside(p.x, p.y, REST, value * ZK) > 0 ? 0 : LEAN);
    p.at = NaN;
  }
  const postR = circ(PR, 16), headR = circ(HR, 16), headI = circ(HR - 1.2, 16);

  /** A ring of the peg tilted th degrees about its foot, towards its lean direction, at local height z. */
  function tilt(p, ring, z, th) {
    const c = Math.cos(rad(th)), s = Math.sin(rad(th)), [lx, ly] = p.ld;
    return ring.map((q) => {
      const a = q.u * lx + q.v * ly, b = -q.u * ly + q.v * lx, a2 = a * c + z * s;
      return P(p.x + a2 * lx - b * ly, p.y + a2 * ly + b * lx, Math.max(0, z * c - a * s));
    });
  }
  function drawPeg(p, th) {
    if (th === p.at) return;
    p.at = th;
    put(p.post, { sil: poly(hull(tilt(p, postR, 0, th).concat(tilt(p, postR, PH, th)))), crease: "" });
    put(p.head, {
      sil: poly(hull(tilt(p, headR, PH, th).concat(tilt(p, headR, PH + HZ, th)))),
      crease: open(tilt(p, run(headI, front), PH + HZ, th)),
    });
  }
  function drawWorld() {
    const t = hour.x, Z = zs.x, key = t.toFixed(3) + "|" + Z.toFixed(2);
    if (key === drawn) return;
    drawn = key;
    const [dx, dy] = dirOf(t), L = reach(t, Z);
    shade.setAttribute("d", poly(hull(ringAt(P, foot, 0).concat(capR.map((q) => P(q.u + L * dx, q.v + L * dy, 0))))));
    put(shaft, { sil: poly(hull(ringAt(P, foot, 0).concat(ringAt(P, top, Z)))), crease: open(ringAt(P, run(inner, front), Z)) });
    put(cap, prism(P, front, capR, capI, Z, Z + CAPZ));
  }

  const B = register(stage, (dt, now) => {
    let m = stepS(hour, dt);
    if (stepS(zs, dt)) m = true;
    drawWorld();
    for (const p of pegs) { drawPeg(p, tval(p.lean, now)); if (!tdone(p.lean, now)) m = true; }
    return m;
  });
  bag.add(B.unregister);

  /** Re-reads every peg against the targets, never the shadow on screen. The lean spreads out from the shadow's edge. */
  function retarget() {
    const now = performance.now(), t = hour.t, Z = zs.t;
    let best = null;
    for (const p of pegs) {
      const e = inside(p.x, p.y, t, Z);
      tset(p.lean, e > 0 ? 0 : LEAN, now, Math.min(Math.abs(e) / 9, 6) * STEP);
      if (e > 0 && (!best || p.x + p.y < best.x + best.y)) best = p;
    }
    if (best !== act) {
      for (const p of pegs) { p.post.sil.classList.toggle("hi", p === best); p.head.sil.classList.toggle("hi", p === best); }
      act = best;
    }
    B.wake();
  }

  bag.add(pointer(stage, {
    move: ([x]) => {
      const t = Math.round(lerp(6, 18, clamp((x - 40) / 320, 0, 1)) * 12) / 12;
      hour.t = t;
      const h = Math.floor(t), m = Math.round((t - h) * 60);
      read.textContent = String(h).padStart(2, "0") + "·" + String(m).padStart(2, "0");
      retarget();
    },
    leave: () => { hour.t = REST; read.textContent = "rest"; retarget(); },
  }));
  bag.add(() => svg.replaceChildren());
  retarget();

  return {
    set: (v) => { zs.t = v * ZK; retarget(); },
    destroy: bag.dispose,
  };
}

hairline({
  name: "tower",
  means: "A tower's shadow sweeps a plot as the sun moves: pegs in the shade stand and work, pegs in the sun lean over and rest.",
  rules: [1, 2, 3, 8],
  range: [18, 30, 44],
  tour: [[53, 160], [120, 160], [227, 160], [320, 160], null],
  mount,
});
