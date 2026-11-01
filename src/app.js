// x=arcsin y. One audio element outlives every page; pages swap around it.
(() => {
  const INK = "#0d0d0d", FUTURE = "#dcdcdc", AXIS = "#ededed";
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } } };

  const tracks = JSON.parse($("#tracks").textContent).map(([n, slug, title, hook, duration]) => ({ n, slug, title, hook, duration }));
  const bySlug = Object.fromEntries(tracks.map(t => [t.slug, t]));
  const cache = new Map();

  function loadData(slug) {
    if (!cache.has(slug)) {
      cache.set(slug, fetch(`/data/${slug}.json`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(d => {
        const bytes = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
        d.envB = bytes(d.env); d.bassB = bytes(d.bass);
        return d;
      }).catch(e => { cache.delete(slug); throw e; }));
    }
    return cache.get(slug);
  }
  const fmt = s => { s = Math.max(0, s | 0); return `${s / 60 | 0}:${String(s % 60).padStart(2, "0")}`; };
  const sample = (arr, fps, t) => { const x = t * fps, i = Math.floor(x); if (i < 0 || i >= arr.length) return 0; const a = arr[i], b = arr[Math.min(i + 1, arr.length - 1)]; return (a + (b - a) * (x - i)) / 255; };

  // ---------------------------------------------------------------- player
  const audio = new Audio();
  audio.preload = "none";
  const bar = $("#player"), seek = $("#seek"), nowTitle = $("#now-title"), nowSub = $("#now-sub"), timeEl = $("#time");
  const P = { cur: null, data: null, queue: tracks.map(t => t.slug), pending: null };

  async function play(slug, opts = {}) {
    const same = P.cur === slug;
    if (same && opts.at == null) { audio.paused ? audio.play().catch(() => {}) : audio.pause(); return sync(); }
    const t = bySlug[slug]; if (!t) return;
    const at = opts.at != null ? opts.at : opts.from === "hook" ? t.hook : same ? audio.currentTime : 0;
    P.cur = slug; P.data = null;
    if (!same) { P.pending = at; audio.src = `/audio/${slug}.mp3`; }
    else audio.currentTime = at;
    // play() stays inside the tap so mobile browsers allow it
    audio.play().catch(() => sync());
    document.body.classList.add("has-player"); bar.classList.add("on");
    nowTitle.textContent = t.title; nowTitle.href = `/tracks/${slug}/`;
    nowSub.textContent = `f(t) · ${t.n} / 35`;
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({ title: t.title, artist: "x=arcsin y", album: "f(t)", artwork: [{ src: "/assets/img/cover-f-t-600.jpg", sizes: "600x600", type: "image/jpeg" }] });
    }
    sync();
    try { const d = await loadData(slug); if (P.cur === slug) { P.data = d; drawSeek(true); } } catch { /* the sound still plays without its curves */ }
  }
  audio.addEventListener("loadedmetadata", () => { if (P.pending) { audio.currentTime = P.pending; } P.pending = null; drawSeek(true); });
  audio.addEventListener("ended", () => step(1));
  audio.addEventListener("timeupdate", () => drawSeek()); // hidden tabs get no animation frames
  ["play", "pause", "playing"].forEach(ev => audio.addEventListener(ev, () => { sync(); kick(); }));
  audio.addEventListener("error", () => { if (audio.src && P.cur) { timeEl.textContent = "Cannot play"; } });
  function step(d) { const i = P.queue.indexOf(P.cur); const nx = P.queue[(i + d + P.queue.length) % P.queue.length]; if (nx) play(nx, { at: 0 }); }
  $("#prev").onclick = () => (audio.currentTime > 3 ? (audio.currentTime = 0) : step(-1));
  $("#next").onclick = () => step(1);
  $("#toggle").onclick = () => { if (P.cur) play(P.cur); else play(tracks[0].slug, { at: 0 }); };
  if ("mediaSession" in navigator) {
    const ms = navigator.mediaSession;
    ms.setActionHandler("play", () => audio.play());
    ms.setActionHandler("pause", () => audio.pause());
    ms.setActionHandler("previoustrack", () => step(-1));
    ms.setActionHandler("nexttrack", () => step(1));
    try { ms.setActionHandler("seekto", e => { audio.currentTime = e.seekTime; }); } catch { /* older Safari */ }
  }

  function sync() {
    const playing = !audio.paused && !audio.ended && !!P.cur;
    bar.classList.toggle("playing", playing);
    $("#toggle").setAttribute("aria-label", playing ? "Pause" : "Play");
    $$("[data-play]").forEach(el => {
      const mine = el.dataset.play === P.cur;
      el.classList.toggle("is-playing", mine && playing);
      el.classList.toggle("on", mine);
      const row = el.closest(".row"); if (row) row.classList.toggle("is-current", mine);
    });
    const hero = $(".hero");
    if (hero) {
      hero.classList.toggle("is-live", !!P.cur);
      if (P.cur) fillStage();
    }
    if (playing) kick();
  }

  // ---------------------------------------------------------------- seek line: the whole track as one graph
  function setupCanvas(c) {
    const r = c.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 2);
    const w = Math.round(r.width * dpr), h = Math.round(r.height * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const g = c.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
    return [g, r.width, r.height];
  }
  function drawSeek() {
    if (!P.cur || !seek.getClientRects().length) return;
    const [g, W, H] = setupCanvas(seek); g.clearRect(0, 0, W, H);
    const dur = audio.duration || bySlug[P.cur].duration, t = audio.currentTime || 0, px = W * Math.min(t / dur, 1);
    const base = H - 8, top = 6;
    g.strokeStyle = AXIS; g.lineWidth = 1; g.beginPath(); g.moveTo(0, base + .5); g.lineTo(W, base + .5); g.stroke();
    const d = P.data;
    if (d) {
      const v = d.wave, n = v.length;
      const line = (x0, x1, col, lw) => {
        g.strokeStyle = col; g.lineWidth = lw; g.lineJoin = "round"; g.beginPath();
        const steps = Math.max(2, Math.ceil(x1 - x0));
        for (let k = 0; k <= steps; k++) { const x = x0 + (x1 - x0) * k / steps, y = base - Math.pow(v[Math.min(n - 1, Math.floor(x / W * n))], 2) * (base - top); k ? g.lineTo(x, y) : g.moveTo(x, y); }
        g.stroke();
      };
      line(px, W, FUTURE, 1); if (px > 1) line(0, px, INK, 1.25);
      const y = base - Math.pow(v[Math.min(n - 1, Math.floor(px / W * n))], 2) * (base - top);
      const b = d.bassB ? sample(d.bassB, d.fps, t) : 0;
      g.fillStyle = INK; g.beginPath(); g.arc(px, y, 3 + 3 * b, 0, 7); g.fill();
    } else { g.fillStyle = INK; g.fillRect(0, base - .5, px, 2); }
    timeEl.textContent = `${fmt(t)} / ${fmt(dur)}`;
    seek.setAttribute("aria-valuemax", dur | 0); seek.setAttribute("aria-valuenow", t | 0); seek.setAttribute("aria-valuetext", timeEl.textContent);
  }
  (() => {
    let down = false;
    const to = e => { const r = seek.getBoundingClientRect(); const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); if (P.cur) { audio.currentTime = f * (audio.duration || bySlug[P.cur].duration); drawSeek(); paintAll(); } };
    seek.addEventListener("pointerdown", e => { down = true; seek.setPointerCapture(e.pointerId); to(e); });
    seek.addEventListener("pointermove", e => { if (down) to(e); });
    seek.addEventListener("pointerup", () => { down = false; });
    seek.addEventListener("pointercancel", () => { down = false; });
  })();

  // ---------------------------------------------------------------- scope: the loudness of the next seconds, as in the shorts
  function drawScope(c, d, t, live) {
    const [g, W, H] = setupCanvas(c); g.clearRect(0, 0, W, H);
    const base = H - 3, amp = H - 22, span = W < 640 ? 4 : 7, headX = W * .382, pxs = W / span;
    g.strokeStyle = AXIS; g.lineWidth = 1; g.beginPath(); g.moveTo(0, base + .5); g.lineTo(W, base + .5); g.stroke();
    const y = tt => base - Math.pow(sample(d.envB, d.fps, tt), 1.8) * amp;
    if (d.bars) {
      g.fillStyle = "#cfcfcf";
      for (const b of d.bars) { const x = headX + (b - t) * pxs; if (x > 0 && x < W) g.fillRect(x, base - 5, 1, 6); }
    }
    const trace = (x0, x1, col, lw) => {
      g.strokeStyle = col; g.lineWidth = lw; g.lineJoin = "round"; g.lineCap = "round"; g.beginPath();
      for (let x = x0; x <= x1; x += 2) { const yy = y(t + (x - headX) / pxs); x === x0 ? g.moveTo(x, yy) : g.lineTo(x, yy); }
      g.stroke();
    };
    trace(Math.ceil(headX), W, FUTURE, 2);
    trace(0, Math.ceil(headX), INK, 2.25);
    const b = sample(d.bassB, d.fps, t);
    g.fillStyle = INK; g.beginPath(); g.arc(headX, y(t), 6 + (live ? 11 * b * b : 0), 0, 7); g.fill();
  }
  function drawIdleScope(c, now) {
    const [g, W, H] = setupCanvas(c); g.clearRect(0, 0, W, H);
    const mid = H * .58, amp = H * .3, k = 2 * Math.PI / (W * .618), ph = now / 1400, headX = W * .382;
    g.strokeStyle = AXIS; g.lineWidth = 1; g.beginPath(); g.moveTo(0, mid + .5); g.lineTo(W, mid + .5); g.stroke();
    const yy = x => mid - Math.sin((x - headX) * k + ph) * amp;
    const trace = (a, b, col, lw) => { g.strokeStyle = col; g.lineWidth = lw; g.beginPath(); for (let x = a; x <= b; x += 3) x === a ? g.moveTo(x, yy(x)) : g.lineTo(x, yy(x)); g.stroke(); };
    trace(Math.ceil(headX), W, FUTURE, 2); trace(0, Math.ceil(headX), INK, 2);
    g.fillStyle = INK; g.beginPath(); g.arc(headX, yy(headX), 6, 0, 7); g.fill();
  }

  // ---------------------------------------------------------------- per-frame painting
  let page = {}, raf = 0;
  function paintAll(now = performance.now()) {
    drawSeek();
    const t = audio.currentTime || 0, d = P.data;
    if (page.heroScope) {
      if (d && P.cur) drawScope(page.heroScope, d, t, !audio.paused); else if (!P.cur) drawIdleScope(page.heroScope, now);
      if (page.rain && (!reduced || !page.rainDone)) { page.rain(now, d ? sample(d.bassB, d.fps, t) : 0, !!d && !audio.paused); page.rainDone = true; }
    }
    if (page.trackScope && page.trackData) {
      const here = P.cur === page.slug;
      drawScope(page.trackScope, page.trackData, here ? t : page.trackData.rest, here && !audio.paused);
    }
    if (page.rider && P.cur === page.slug && page.trackData) {
      const bars = page.trackData.bars; let lo = 0, hi = bars.length - 1;
      while (lo < hi - 1) { const m = lo + hi >> 1; bars[m] <= t ? lo = m : hi = m; }
      const f = (t - bars[lo]) / ((bars[lo + 1] - bars[lo]) || 1);
      const p = page.riderPath.getPointAtLength(page.riderLen * f);
      page.rider.setAttribute("cx", p.x); page.rider.setAttribute("cy", p.y);
      page.rider.setAttribute("r", 10 + 14 * sample(page.trackData.bassB, page.trackData.fps, t));
    }
    if (page.score && P.cur === page.slug) page.score(t);
  }
  function tick(now) {
    raf = 0; // a paint that throws must not leave the loop marked as running
    paintAll(now);
    const idleHero = page.heroScope && !reduced && document.visibilityState === "visible";
    raf = (!audio.paused && P.cur) || idleHero ? requestAnimationFrame(tick) : 0;
  }
  function kick() { if (!raf) raf = requestAnimationFrame(tick); }
  addEventListener("resize", () => { fitAll(); kick(); paintAll(); });

  // ---------------------------------------------------------------- fit: a title fills its line and never breaks it
  function fit(el, max) {
    el.style.setProperty("--fit", `${max}px`);
    const ps = getComputedStyle(el.parentElement);
    const room = (el.parentElement.clientWidth - parseFloat(ps.paddingLeft) - parseFloat(ps.paddingRight)) * .995;
    const w = el.scrollWidth;
    if (w > room) el.style.setProperty("--fit", `${Math.max(22, max * room / w)}px`);
  }
  function fitAll() { const t = $(".track-title"); if (t) { t.style.display = "inline-block"; const max = t.classList.contains("score-title") ? Math.max(32, Math.min(72, innerWidth * .05)) : Math.max(44, Math.min(156, innerWidth * .11)); fit(t, max); } const s = $(".stage-title"); if (s && P.cur) fit(s, Math.max(44, Math.min(120, innerWidth * .09))); }

  function fillStage() {
    const t = bySlug[P.cur], a = $(`.field a[data-play="${P.cur}"]`), title = $(".stage-title"), what = $(".stage-what"), score = $(".stage-score");
    if (!title) return;
    if (title.dataset.slug !== P.cur) {
      title.dataset.slug = P.cur; title.textContent = t.title; title.href = `/tracks/${t.slug}/`;
      what.textContent = a ? a.dataset.what : ""; score.href = `/scores/${t.slug}/`; fit(title, Math.max(44, Math.min(120, innerWidth * .09)));
    }
  }

  // ---------------------------------------------------------------- home: equations falling behind the page, quiet until touched
  const RAIN = { cell: 21, cellSmall: 17, headAlpha: .2, tailMin: 10, tailMax: 26, fps: 30, speedMin: 3, speedMax: 9, centerCalm: .82 };
  const CONSTANTS = ["3.14159265358979", "2.71828182845904", "1.61803398874989", "1.41421356237309", "0.14285714285714", "1.20205690315959", "0.57721566490153", "4.66920160910299"];
  function seeded(s) { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return () => { h ^= h << 13; h ^= h >>> 17; h ^= h << 5; return (h >>> 0) / 4294967296; }; }
  function initRain() {
    const c = $(".rain"), field = $(".field"), hero = $(".hero"); if (!c) return;
    field.classList.add("placed");
    const rnd = seeded("x=arcsin y");
    let cols = [], cw = 0, lh = 0, W = 0, H = 0, last = 0, drawn = 0, hover = -1;
    const layout = () => {
      W = hero.clientWidth; H = hero.clientHeight;
      cw = W < 640 ? RAIN.cellSmall : RAIN.cell; lh = cw * 1.12;
      const n = Math.ceil(W / cw), rows = Math.ceil(H / lh);
      const deck = tracks.map(t => t).sort(() => rnd() - .5);
      cols = Array.from({ length: n }, (_, i) => {
        const t = deck[i % deck.length]; let text = "";
        while (text.length < rows * 3) text += t.title.replace(/\s+/g, "") + " " + CONSTANTS[Math.floor(rnd() * CONSTANTS.length)].slice(0, 6 + Math.floor(rnd() * 11)) + " ";
        const tail = RAIN.tailMin + Math.floor(rnd() * (RAIN.tailMax - RAIN.tailMin));
        return { slug: t.slug, text, tail, speed: RAIN.speedMin + rnd() * (RAIN.speedMax - RAIN.speedMin), off: Math.floor(rnd() * 100), y: [rnd() * (rows + tail), rnd() * (rows + tail) - rows] };
      });
    };
    layout();
    const calm = (x, y) => 1 - RAIN.centerCalm * Math.exp(-(((x - W / 2) / (W * .36)) ** 2 + ((y - H * .43) / (H * .27)) ** 2));
    const draw = (now, bass, live) => {
      const dt = Math.min(.1, (now - last) / 1000 || 0); last = now;
      const rows = Math.ceil(H / lh) + 1, push = 1 + (live ? 2.4 * bass : 0);
      for (const col of cols) col.y = col.y.map(y => { const v = y + col.speed * push * dt; return v - col.tail > rows ? -Math.floor(rnd() * rows * .6) : v; });
      if (now - drawn < 1000 / RAIN.fps) return; drawn = now;
      const [g] = setupCanvas(c); g.clearRect(0, 0, W, H);
      g.font = `500 ${Math.round(cw * .72)}px ${getComputedStyle(document.body).fontFamily}`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = INK;
      const lift = 1 + (live ? .9 * bass : 0);
      cols.forEach((col, i) => {
        const mine = col.slug === P.cur, weight = (i === hover ? 2.8 : mine ? 2.6 : P.cur ? .75 : 1) * lift;
        const x = (i + .5) * cw;
        for (const y of col.y) {
          const head = Math.floor(y);
          for (let k = 0; k < col.tail; k++) {
            const row = head - k; if (row < 0 || row >= rows) continue;
            const ch = col.text[(row + col.off) % col.text.length]; if (ch === " ") continue;
            const py = (row + .5) * lh, fade = (1 - k / col.tail) ** 1.4;
            g.globalAlpha = Math.min(.75, RAIN.headAlpha * fade * weight * calm(x, py));
            g.fillText(ch, x, py);
          }
        }
      });
      g.globalAlpha = 1;
    };
    page.rain = draw;
    let lastW = W;
    const ro = new ResizeObserver(() => { if (hero.clientWidth !== lastW || hero.clientHeight !== H) { lastW = hero.clientWidth; layout(); drawn = 0; kick(); } });
    ro.observe(hero); page.cleanup = () => ro.disconnect();
    const colAt = e => Math.floor((e.clientX - hero.getBoundingClientRect().left) / cw);
    hero.addEventListener("pointermove", e => { hover = e.pointerType === "mouse" ? colAt(e) : -1; });
    hero.addEventListener("pointerleave", () => { hover = -1; });
    hero.addEventListener("click", e => {
      if (e.target.closest("a, button")) return;
      const col = cols[colAt(e)]; if (col) play(col.slug, { from: "hook" });
    });
    page.heroScope = $(".scope"); kick();
    if (P.cur) fillStage();
  }

  // ---------------------------------------------------------------- library
  function initLibrary() {
    const box = $(".rows"); if (!box) return;
    const rows = $$(".row", box), search = $(".search"), empty = $(".empty");
    const apply = () => {
      const q = (search.value || "").trim().toLowerCase(); let shown = 0;
      rows.forEach(r => { const hit = !q || r.dataset.q.includes(q); r.hidden = !hit; if (hit) shown++; });
      empty.hidden = shown > 0;
    };
    search.addEventListener("input", apply);
    $$(".sort button").forEach(b => b.addEventListener("click", () => {
      $$(".sort button").forEach(x => x.classList.toggle("on", x === b));
      const k = b.dataset.sort, dir = k === "bpmd" ? -1 : 1, key = k === "bpmd" ? "bpm" : k;
      const out = rows.slice().sort((x, y) => key === "title" ? x.dataset.title.localeCompare(y.dataset.title) : (x.dataset[key] - y.dataset[key]) * dir);
      out.forEach(r => box.append(r));
      P.queue = out.map(r => r.dataset.slug);
    }));
    $$(".views button").forEach(b => b.addEventListener("click", () => {
      $$(".views button").forEach(x => x.classList.toggle("on", x === b));
      box.classList.toggle("as-grid", b.dataset.view === "grid"); store.set("view", b.dataset.view);
    }));
    if (store.get("view") === "grid") { const b = $('.views button[data-view="grid"]'); if (b) b.click(); }
  }

  // ---------------------------------------------------------------- track page
  async function initTrack() {
    const c = $(".track-scope"); if (!c) return;
    const me = page;
    page.slug = c.dataset.slug; page.trackScope = c;
    const fig = $(".figure svg"), main = fig && fig.querySelector(".main");
    if (main) {
      const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot.setAttribute("class", "rider"); dot.setAttribute("r", 0); fig.append(dot);
      page.rider = dot; page.riderPath = main; page.riderLen = main.getTotalLength();
    }
    fitAll();
    try {
      const d = await loadData(page.slug);
      d.rest = bySlug[page.slug].hook;
      if (page === me) { page.trackData = d; paintAll(); }
    } catch { /* the page reads fine without its curve */ }
  }

  // ---------------------------------------------------------------- score page
  async function initScore() {
    const sheet = $(".sheet"); if (!sheet) return;
    const me = page;
    page.slug = sheet.dataset.slug;
    const lines = $$(".line", sheet);
    let d; try { d = await loadData(page.slug); } catch { return; }
    if (page !== me) return;
    page.trackData = d;
    const barLine = new Map(); // bar index -> [line element, bar offset in line, xrange]
    d.lines.forEach((l, i) => { for (let b = l.b0; b < l.b1; b++) barLine.set(b, [lines[i], b - l.b0, l.x[b - l.b0]]); });
    const follow = $(".follow input"); let curLine = null, curBar = -1, userAt = 0;
    const pick = t => { let lo = 0, hi = d.bars.length - 1; while (lo < hi - 1) { const m = lo + hi >> 1; d.bars[m] <= t ? lo = m : hi = m; } return lo; };
    const onUser = () => { userAt = performance.now(); };
    addEventListener("wheel", onUser, { passive: true }); addEventListener("touchmove", onUser, { passive: true });
    page.cleanup = () => { removeEventListener("wheel", onUser); removeEventListener("touchmove", onUser); };
    page.score = t => {
      const b = pick(t), info = barLine.get(b); if (!info) return;
      const [el, , xr] = info;
      if (!el || !xr) return;
      const f = Math.min(1, Math.max(0, (t - d.bars[b]) / ((d.bars[b + 1] - d.bars[b]) || 1)));
      const x = xr[0] + (xr[1] - xr[0]) * f;
      if (el !== curLine) {
        if (curLine) curLine.classList.remove("now");
        el.classList.add("now"); curLine = el;
        if (follow.checked && !audio.paused && performance.now() - userAt > 2500) el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
      }
      const head = $(".head", el), tint = $(".tint", el);
      head.style.left = `${x * 100}%`;
      head.style.setProperty("--dot", `${9 + 11 * sample(d.bassB, d.fps, t)}px`);
      if (b !== curBar) { curBar = b; tint.style.left = `${xr[0] * 100}%`; tint.style.width = `${(xr[1] - xr[0]) * 100}%`; }
      if (sheet.scrollWidth > sheet.clientWidth && follow.checked && performance.now() - userAt > 2500) {
        const target = el.offsetLeft + el.offsetWidth * x - sheet.clientWidth * .38;
        sheet.scrollLeft += (target - sheet.scrollLeft) * .12;
      }
    };
    sheet.addEventListener("click", e => {
      const el = e.target.closest(".line"); if (!el) return;
      const i = lines.indexOf(el), l = d.lines[i]; if (!l || !l.x.length) return;
      const r = el.getBoundingClientRect(), fx = (e.clientX - r.left) / r.width;
      let k = l.x.findIndex(xr => fx <= xr[1]); if (k < 0) k = l.x.length - 1;
      const xr = l.x[k], f = Math.min(1, Math.max(0, (fx - xr[0]) / ((xr[1] - xr[0]) || 1))), bar0 = l.b0 + k;
      play(page.slug, { at: d.bars[bar0] + f * (d.bars[bar0 + 1] - d.bars[bar0]) }); paintAll();
    });
    if (P.cur === page.slug) paintAll();
  }

  // ---------------------------------------------------------------- pages without full reloads, so the sound keeps going
  function initPage() {
    if (page.cleanup) page.cleanup();
    page = {};
    initRain(); initLibrary(); initTrack(); initScore(); fitAll(); sync(); kick();
    if (P.cur) paintAll();
  }
  document.addEventListener("click", e => {
    const pick = e.target.closest("[data-random]");
    if (pick) { const pool = tracks.filter(t => t.slug !== P.cur), t = pool[Math.floor(Math.random() * pool.length)]; play(t.slug, { from: "hook" }); return; }
    const playEl = e.target.closest("[data-play]");
    if (playEl) { e.preventDefault(); play(playEl.dataset.play, { from: playEl.dataset.from, at: playEl.dataset.at != null ? +playEl.dataset.at : undefined }); return; }
    const a = e.target.closest("a");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || a.target || a.hasAttribute("download")) return;
    const url = new URL(a.href, location);
    if (url.origin !== location.origin || !/\/$|\/[^./]*$/.test(url.pathname)) return;
    if (url.pathname === location.pathname && url.hash) return;
    e.preventDefault(); go(url.href, true);
  });
  async function go(href, push) {
    try {
      const r = await fetch(href); if (!r.ok && r.status !== 404) throw new Error(r.status);
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      $("main").replaceWith(doc.querySelector("main"));
      document.title = doc.title;
      for (const sel of ['meta[name="description"]', 'link[rel="canonical"]']) {
        const cur = $(sel), nx = doc.querySelector(sel);
        if (cur && nx) { for (const at of ["content", "href"]) if (nx.hasAttribute(at)) cur.setAttribute(at, nx.getAttribute(at)); }
      }
      $$(".nav a").forEach(a => { const n = doc.querySelector(`.nav a[href="${a.getAttribute("href")}"]`); if (n) n.hasAttribute("aria-current") ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"); });
      if (push) { history.replaceState({ y: scrollY }, ""); history.pushState({}, "", href); }
      initPage();
      scrollTo(0, push ? 0 : (history.state && history.state.y) || 0);
      const main = $("main"); main.tabIndex = -1; main.focus({ preventScroll: true });
    } catch { location.href = href; }
  }
  addEventListener("popstate", () => go(location.href, false));
  addEventListener("keydown", e => {
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.code === "Space" && P.cur && e.target.tagName !== "BUTTON" && e.target.tagName !== "A") { e.preventDefault(); play(P.cur); }
    if (e.key === "ArrowRight" && P.cur) audio.currentTime += 5;
    if (e.key === "ArrowLeft" && P.cur) audio.currentTime -= 5;
  });
  history.scrollRestoration = "manual";
  document.addEventListener("visibilitychange", kick);
  initPage();
})();
