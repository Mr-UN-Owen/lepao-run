/* run-sim · 北邮校园跑（网页版）
 * 结构：1) 工具  2) RunMap 地图  3) 状态  4) 视图渲染  5) 交互
 */
'use strict';

/* ============================================================ 1. 工具 */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const el = (tag, cls, txt) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt !== undefined) n.textContent = txt;
  return n;
};
const fmtPace = (sec) => {
  sec = Math.max(0, Math.round(sec || 0));
  return `${Math.floor(sec / 60)}'${String(sec % 60).padStart(2, '0')}"`;
};
const fmtDur = (sec) => {
  sec = Math.max(0, Math.round(sec || 0));
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
           : `${m}:${String(s).padStart(2, '0')}`;
};
const fmtClock = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
};
const fmtDate = (ts) => {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`;
};

async function api(path, body) {
  const opt = body === undefined
    ? { method: 'GET' }
    : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const j = await r.json().catch(() => ({ ok: false, error: `HTTP ${r.status}` }));
  if (!r.ok || j.ok === false) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}

let toastTimer = 0;
function toast(msg, kind) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'show' + (kind === 'err' ? ' err' : kind === 'warn' ? ' warn' : '');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = ''; }, kind === 'err' ? 4200 : 2600);
}

/* ============================================================ 2. RunMap */
const SPEED_STOPS = [[0.0, '#3b82f6'], [1.6, '#4cc9f0'], [2.6, '#2ee07f'], [3.6, '#a3e635'], [4.6, '#e3b341']];
function speedColor(v) {
  v = Math.max(0, Math.min(SPEED_STOPS[SPEED_STOPS.length - 1][0], v || 0));
  for (let i = 1; i < SPEED_STOPS.length; i++) {
    const [v0, c0] = SPEED_STOPS[i - 1], [v1, c1] = SPEED_STOPS[i];
    if (v <= v1) {
      const t = (v - v0) / (v1 - v0 || 1);
      const p = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
      const [r0, g0, b0] = p(c0), [r1, g1, b1] = p(c1);
      return `rgb(${Math.round(r0 + (r1 - r0) * t)},${Math.round(g0 + (g1 - g0) * t)},${Math.round(b0 + (b1 - b0) * t)})`;
    }
  }
  return SPEED_STOPS[SPEED_STOPS.length - 1][1];
}

class RunMap {
  constructor(canvas) {
    this.c = canvas;
    this.ctx = canvas.getContext('2d');
    this.data = { campus: null, route: null, track: [], checkpoints: [] };
    this.lat0 = 39.96;
    this.lng0 = 116.35;
    this.view = { s: 1, cx: 0, cy: 0, ready: false };
    this.play = { on: false, t: 0, raf: 0, speed: 60 };
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    this._bind();
    this.resize();
  }

  project(lat, lng) {
    const kx = 111320 * Math.cos((this.lat0 * Math.PI) / 180);
    return { x: (lng - this.lng0) * kx, y: (lat - this.lat0) * 111320 };
  }
  screen(lat, lng) {
    const p = this.project(lat, lng);
    const W = this.c.clientWidth, H = this.c.clientHeight;
    return { x: (p.x - this.view.cx) * this.view.s + W / 2,
             y: -(p.y - this.view.cy) * this.view.s + H / 2 };
  }

  _bind() {
    const c = this.c;
    let drag = null;
    c.addEventListener('pointerdown', (e) => {
      drag = { x: e.clientX, y: e.clientY, cx: this.view.cx, cy: this.view.cy };
      c.classList.add('drag');
      try { c.setPointerCapture(e.pointerId); } catch (_) {}
    });
    c.addEventListener('pointermove', (e) => {
      if (!drag) return;
      this.view.cx = drag.cx - (e.clientX - drag.x) / this.view.s;
      this.view.cy = drag.cy + (e.clientY - drag.y) / this.view.s;
      this.draw();
    });
    const end = () => { drag = null; c.classList.remove('drag'); };
    c.addEventListener('pointerup', end);
    c.addEventListener('pointercancel', end);
    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = c.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const W = c.clientWidth, H = c.clientHeight;
      const wx = this.view.cx + (mx - W / 2) / this.view.s;
      const wy = this.view.cy - (my - H / 2) / this.view.s;
      this.view.s = Math.max(0.02, Math.min(40, this.view.s * Math.exp(-e.deltaY * 0.0016)));
      this.view.cx = wx - (mx - W / 2) / this.view.s;
      this.view.cy = wy + (my - H / 2) / this.view.s;
      this.draw();
    }, { passive: false });
    window.addEventListener('resize', () => this.resize());
  }

  resize() {
    const c = this.c;
    const w = c.clientWidth || 480, h = c.clientHeight || 216;
    this.dpr = Math.max(1, window.devicePixelRatio || 1);
    c.width = Math.round(w * this.dpr);
    c.height = Math.round(h * this.dpr);
    if (!this.view.ready) this.fit(); else this.draw();
  }

  setData(campus, route, track, checkpoints) {
    this.data = { campus, route, track: track || [], checkpoints: checkpoints || [] };
    this.lat0 = campus?.center?.[0] ?? 39.96;
    this.lng0 = campus?.center?.[1] ?? 116.35;
    this.view.ready = false;
    this.fit();
  }

  fit() {
    const { campus, track } = this.data;
    const pts = [];
    (campus?.boundary || []).forEach((p) => pts.push(p));
    (campus?.roads || []).forEach((l) => l.forEach((p) => pts.push(p)));
    track.forEach((p) => pts.push([p.a, p.o]));
    if (!pts.length) { this.draw(); return; }
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    pts.forEach(([a, o]) => {
      const p = this.project(a, o);
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    });
    const W = this.c.clientWidth || 480, H = this.c.clientHeight || 216;
    const spanX = Math.max(20, maxX - minX), spanY = Math.max(20, maxY - minY);
    const s = Math.min((W - 46) / spanX, (H - 38) / spanY);
    this.view = { s: Math.max(0.02, s), cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, ready: true };
    this.draw();
  }

  draw() {
    const ctx = this.ctx, W = this.c.clientWidth, H = this.c.clientHeight;
    if (!W || !H) return;
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const g = ctx.createLinearGradient(0, 0, W, H);
    g.addColorStop(0, '#060b10'); g.addColorStop(1, '#070d13');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    this._grid(ctx, W, H);

    const { campus, track, checkpoints } = this.data;
    if (campus) {
      this._poly(ctx, campus.boundary, true, 'rgba(46,224,127,.04)', 'rgba(46,224,127,.2)', 1.1, [5, 4]);
      (campus.roads || []).forEach((line) => {
        this._poly(ctx, line, false, null, 'rgba(120,145,170,.11)', Math.max(3, Math.min(10, this.view.s * 10)), []);
      });
    }
    checkpoints.forEach((cp) => {
      const p = this.screen(cp.lat, cp.lng);
      const rr = Math.max(5, Math.min(70, 40 * this.view.s));
      ctx.beginPath(); ctx.arc(p.x, p.y, rr, 0, Math.PI * 2);
      ctx.fillStyle = cp.hit === false ? 'rgba(255,107,107,.06)' : 'rgba(46,224,127,.05)';
      ctx.fill();
      ctx.strokeStyle = cp.hit === false ? 'rgba(255,107,107,.32)' : 'rgba(46,224,127,.28)';
      ctx.setLineDash([3, 4]); ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
    });
    if (track.length) this._track(ctx, track);
    checkpoints.forEach((cp, i) => {
      const p = this.screen(cp.lat, cp.lng);
      ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2);
      ctx.fillStyle = cp.hit === false ? '#ff6b6b' : '#2ee07f';
      ctx.fill();
      ctx.strokeStyle = 'rgba(4,12,9,.9)'; ctx.lineWidth = 1.5; ctx.stroke();
      ctx.font = '600 9px ui-monospace,Menlo,Consolas,monospace';
      ctx.fillStyle = 'rgba(210,232,222,.9)';
      ctx.fillText(String(i + 1), p.x + 6, p.y - 5);
    });
    if (track.length) {
      this._marker(ctx, track[0], '#4cc9f0', '起');
      this._marker(ctx, track[track.length - 1], '#e3b341', '终');
      if (this.play.on) this._marker(ctx, this._head(), '#ffffff', '', true);
    }
    this._scalebar(ctx, W, H);
  }

  _grid(ctx, W, H) {
    ctx.save();
    ctx.strokeStyle = 'rgba(140,170,200,.04)';
    for (let x = 0; x < W; x += 40) { ctx.beginPath(); ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, H); ctx.stroke(); }
    for (let y = 0; y < H; y += 40) { ctx.beginPath(); ctx.moveTo(0, y + .5); ctx.lineTo(W, y + .5); ctx.stroke(); }
    ctx.restore();
  }

  _poly(ctx, coords, close, fill, stroke, lw, dash) {
    if (!coords || coords.length < 2) return;
    ctx.beginPath();
    coords.forEach(([a, o], i) => {
      const p = this.screen(a, o);
      i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
    });
    if (close) ctx.closePath();
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) {
      ctx.strokeStyle = stroke; ctx.lineWidth = lw;
      ctx.setLineDash(dash || []); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  _track(ctx, track) {
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath();
    track.forEach((p, i) => {
      const s = this.screen(p.a, p.o);
      i ? ctx.lineTo(s.x, s.y) : ctx.moveTo(s.x, s.y);
    });
    ctx.strokeStyle = 'rgba(46,224,127,.12)'; ctx.lineWidth = 8; ctx.stroke();
    ctx.lineWidth = 2.2;
    for (let i = 1; i < track.length; i++) {
      const a = this.screen(track[i - 1].a, track[i - 1].o);
      const b = this.screen(track[i].a, track[i].o);
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = speedColor(track[i].s ?? track[i - 1].s ?? 0);
      ctx.stroke();
    }
    if (this.play.on) {
      const idx = this._headIndex();
      ctx.beginPath();
      for (let i = 0; i <= idx; i++) {
        const s = this.screen(track[i].a, track[i].o);
        i ? ctx.lineTo(s.x, s.y) : ctx.moveTo(s.x, s.y);
      }
      ctx.strokeStyle = 'rgba(255,255,255,.5)'; ctx.lineWidth = 1.1;
      ctx.setLineDash([2, 3]); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  _marker(ctx, p, color, label, pulse) {
    if (!p) return;
    const s = this.screen(p.a, p.o);
    if (pulse) {
      ctx.beginPath(); ctx.arc(s.x, s.y, 10, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(255,255,255,.15)'; ctx.fill();
    }
    ctx.beginPath(); ctx.arc(s.x, s.y, 5.5, 0, Math.PI * 2);
    ctx.fillStyle = color; ctx.fill();
    ctx.strokeStyle = 'rgba(4,10,14,.95)'; ctx.lineWidth = 2; ctx.stroke();
    if (label) {
      ctx.font = '600 9px ui-monospace,Menlo,Consolas,monospace';
      ctx.fillStyle = 'rgba(226,240,248,.88)';
      ctx.fillText(label, s.x + 8, s.y + 11);
    }
  }

  _scalebar(ctx, W, H) {
    const cands = [10, 20, 50, 100, 200, 500, 1000, 2000];
    let pick = cands[cands.length - 1];
    for (const m of cands) { if (m * this.view.s >= 46) { pick = m; break; } }
    const px = pick * this.view.s;
    const x0 = 10, y0 = H - 12;
    ctx.strokeStyle = 'rgba(150,175,200,.45)'; ctx.lineWidth = 1.3;
    ctx.beginPath(); ctx.moveTo(x0, y0 - 3); ctx.lineTo(x0, y0); ctx.lineTo(x0 + px, y0); ctx.lineTo(x0 + px, y0 - 3); ctx.stroke();
    ctx.font = '9px ui-monospace,Menlo,Consolas,monospace';
    ctx.fillStyle = 'rgba(150,175,200,.7)';
    ctx.fillText(pick >= 1000 ? `${pick / 1000} km` : `${pick} m`, x0 + 2, y0 - 6);
  }

  _headIndex() {
    const track = this.data.track;
    if (!track.length) return 0;
    const total = track[track.length - 1].t || 1;
    const target = this.play.t * total;
    let i = 0;
    while (i < track.length - 1 && (track[i].t || 0) < target) i++;
    return i;
  }
  _head() { return this.data.track[this._headIndex()] || null; }

  playFrom(onTick) {
    const track = this.data.track;
    if (!track.length) return;
    this.stop(true);
    this.play.on = true; this.play.t = 0;
    const total = track[track.length - 1].t || 60;
    const dur = (total * 1000) / this.play.speed;
    const t0 = performance.now();
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur);
      this.play.t = k;
      this.draw();
      onTick && onTick(track[this._headIndex()], total);
      if (k < 1) this.play.raf = requestAnimationFrame(step);
      else this.stop(false);
    };
    this.play.raf = requestAnimationFrame(step);
    window.onPlayState && window.onPlayState(true);
  }

  stop(keepProgress) {
    if (this.play.raf) cancelAnimationFrame(this.play.raf);
    this.play.raf = 0;
    this.play.on = false;
    this.play.t = keepProgress ? this.play.t : 0;
    window.onPlayState && window.onPlayState(false);
    this.draw();
  }
}

/* ============================================================ 3. 状态 */
const S = {
  boot: null, campus: null, route: null, draft: null, savedId: null,
  dash: null, sync: null, cred: null, adapter: 'auto', filter: 'all',
  stage: 'idle', map: null, busy: false,
};

const curCampus = () => (S.boot?.campuses || []).find((c) => c.id === S.campus) || null;
const curRoute = () => curCampus()?.routes.find((r) => r.id === S.route) || null;

/* ============================================================ 4. 渲染 */
function renderCampusChips() {
  const box = $('#campusChips');
  box.innerHTML = '';
  (S.boot.campuses || []).forEach((c) => {
    const b = el('button', 'chip' + (c.id === S.campus ? ' on' : ''), c.short || c.name);
    b.onclick = () => {
      S.campus = c.id;
      S.route = c.routes[0]?.id || null;
      resetDraft();
      renderCampusChips(); renderRouteChips(); syncMap(); renderCheckpoints();
    };
    box.appendChild(b);
  });
}

function renderRouteChips() {
  const box = $('#routeChips');
  box.innerHTML = '';
  (curCampus()?.routes || []).forEach((r) => {
    const b = el('button', 'chip' + (r.id === S.route ? ' on' : ''),
      `${r.name} · ${r.hint_km.toFixed(2)}km/圈`);
    b.onclick = () => {
      S.route = r.id;
      resetDraft();
      renderRouteChips(); syncMap(); renderCheckpoints();
    };
    box.appendChild(b);
  });
  const c = curCampus(), r = curRoute();
  $('#abSub').textContent = c && r ? `${c.name} · ${r.name}` : '—';
  renderCoverHint();
}

function renderCoverHint() {
  const r = curRoute();
  const d = parseFloat($('#distNum').value || '0');
  const box = $('#coverHint');
  if (!r) { box.textContent = ''; return; }
  const cover = r.min_cover_km || 0;
  if (d + 0.001 < cover) {
    box.className = 'hint warnline';
    box.textContent = `⚠ 覆盖全部 ${r.checkpoints.length} 个打卡点需 ≥ ${cover.toFixed(2)} km，当前会漏点`;
  } else {
    box.className = 'hint';
    box.textContent = `本跑区 ${r.hint_km.toFixed(2)} km/圈 · 覆盖 ${r.checkpoints.length} 点需 ≥ ${cover.toFixed(2)} km`;
  }
}

function syncMap() {
  const c = curCampus(), r = curRoute();
  if (!c || !r) return;
  const cps = (S.draft?.checkins || r.checkpoints).map((x, i) => ({
    lat: x.lat ?? x.latitude ?? 0, lng: x.lng ?? x.longitude ?? 0,
    hit: x.hit !== false, label: x.label || r.checkpoints[i]?.label,
  }));
  S.map.setData(c, r, S.draft?.track || [], cps);
}

function renderCheckpoints() {
  const box = $('#cpList');
  const r = curRoute();
  if (!r) { box.innerHTML = '<div class="empty">选择跑区后显示打卡点</div>'; return; }
  const checkins = S.draft?.checkins || [];
  box.innerHTML = '';
  r.checkpoints.forEach((cp, i) => {
    const c = checkins[i] || null;
    const row = el('div', 'cp' + (c ? (c.hit ? ' hit' : ' miss') : ''));
    const distTxt = c ? `首通过偏差 ${c.closest_m.toFixed(0)} m` : `半径 ${S.boot.policy.checkin_radius_m} m`;
    const stateTxt = c ? (c.hit ? '已打卡' : '未命中') : '待打卡';
    row.innerHTML = `<div class="idx">${i + 1}</div>
      <div class="who"><div class="nm">${cp.label || cp.point_id}</div>
        <div class="ds">${cp.point_id} · ${distTxt}</div></div>
      <div class="st">${stateTxt}</div>`;
    box.appendChild(row);
  });
  $('#cpMode').textContent = `${r.checkpoints.length} 点 · 自由打卡`;
}

function renderRules(v) {
  const box = $('#ruleList');
  if (!v) {
    box.innerHTML = '<div class="empty">生成轨迹后自动跑 7 条本地规则</div>';
    $('#verdictTag').textContent = '—';
    return;
  }
  box.innerHTML = '';
  const icon = { pass: '✓', warn: '!', fail: '✕' };
  v.items.forEach((it) => {
    const row = el('div', 'cp');
    row.innerHTML = `<div class="idx" style="${it.level === 'fail' ? 'color:#ff6b6b;border-color:#5c2626' : it.level === 'warn' ? 'color:#e3b341;border-color:#4a3d18' : 'color:#2ee07f;border-color:#2a6b4f'}">${icon[it.level]}</div>
      <div class="who"><div class="nm">${it.title}</div><div class="ds">${it.detail}</div></div>`;
    box.appendChild(row);
  });
  const map = { pass: '通过', warn: '需关注', fail: '不通过' };
  $('#verdictTag').textContent = `${map[v.verdict] || v.verdict} · ${v.passed}/${v.total}`;
}

function renderMetrics(live) {
  const d = S.draft;
  if (!live) {
    if (!d) {
      $('#mPace').innerHTML = '--\'--"';
      $('#mTime').textContent = '0:00';
      $('#mDist').innerHTML = '0.00<small>km</small>';
      return;
    }
    $('#mPace').innerHTML = `${fmtPace(d.metrics.avg_pace)}`;
    $('#mTime').textContent = fmtDur(d.metrics.duration_s);
    $('#mDist').innerHTML = `${d.metrics.distance_km.toFixed(2)}<small>km</small>`;
    return;
  }
  // live: 按当前进度算配速/用时/距离
  const track = d?.track || [];
  const total = track.length ? track[track.length - 1].t : 0;
  const t = total * (S.map?.play.t || 0);
  let dist = 0, idx = 0;
  for (let i = 1; i < track.length; i++) {
    const a = track[i - 1], b = track[i];
    const dx = (b.a - a.a) * 111320;
    const dy = (b.o - a.o) * 111320 * Math.cos((a.a * Math.PI) / 180);
    const seg = Math.hypot(dx, dy);
    if ((b.t || 0) <= t) dist += seg; else { idx = i; break; }
  }
  const km = dist / 1000;
  $('#mDist').innerHTML = `${km.toFixed(2)}<small>km</small>`;
  $('#mTime').textContent = fmtDur(t);
  $('#mPace').innerHTML = km > 0.01 ? fmtPace(t / km) : `--'--"`;
}

function renderRecords() {
  const dash = S.dash || { records: [], stats: {} };
  const st = dash.stats || {};
  $('#recTotal').innerHTML = `${(st.total_km || 0).toFixed(2)}<small>km</small>`;
  $('#recCount').textContent = st.count || 0;
  $('#recWeek').innerHTML = `${(st.week_km || 0).toFixed(2)}<small>km</small>`;
  $('#progText').textContent = `${(st.total_km || 0).toFixed(2)} / ${(st.target_km || 0).toFixed(0)} km`;
  $('#progFill').style.width = `${Math.min(100, (st.ratio || 0) * 100).toFixed(1)}%`;
  const sy = dash.sync || {};
  $('#syncFoot').textContent = sy.synced_at
    ? `上次同步 ${fmtClock(sy.synced_at)} · ${sy.source === 'lepao' ? '平台真实' : '演示数据'}`
    : '尚未同步';

  const rows = (dash.records || []).filter((r) => {
    if (S.filter === 'ok') return r.valid === true;
    if (S.filter === 'bad') return r.valid === false;
    if (S.filter === 'local') return r.origin === 'local';
    return true;
  });
  const box = $('#recList');
  $('#recHint').textContent = `${rows.length} 条`;
  if (!rows.length) { box.innerHTML = '<div class="empty">没有符合条件的记录</div>'; return; }
  box.innerHTML = '';
  rows.slice(0, 80).forEach((r) => {
    const tagCls = r.valid === true ? 'ok' : r.valid === false ? 'bad' : 'pending';
    const tagTxt = r.valid === true ? '有效' : r.valid === false ? '无效' : '仅本地';
    const row = el('div', 'rec');
    row.innerHTML = `<div class="rd">
        <div class="rt">${fmtDate(r.start_time)} · ${r.status_text || ''}</div>
        <div class="rs">${fmtClock(r.start_time)} · 用时 ${fmtDur(r.used_time)} · 配速 ${fmtPace(r.pace)}/km</div>
      </div>
      <div class="rk">${(r.distance_km || 0).toFixed(2)}<small>km</small></div>
      <span class="tag ${tagCls}">${tagTxt}</span>`;
    box.appendChild(row);
  });
}

function renderSyncSeg() {
  const seg = $('#syncSeg');
  seg.innerHTML = '';
  (S.boot?.syncers || []).forEach((s) => {
    const b = el('button', s.name === S.adapter ? 'on' : '', s.label);
    b.onclick = () => {
      S.adapter = s.name;
      $$('#syncSeg button').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
      toast(`数据源切到「${s.label}」${s.live ? '（真实拉取）' : ''}`);
    };
    seg.appendChild(b);
  });
}

function renderSync() {
  const sy = S.sync || {};
  const dash = S.dash || { records: [] };
  const plat = (dash.records || []).filter((r) => r.origin !== 'local').length;
  const loc = (dash.records || []).filter((r) => r.origin === 'local').length;
  const matched = (dash.records || []).filter((r) => r.origin === 'platform+local').length;
  $('#syncPlat').textContent = `${plat} 条`;
  $('#syncLocal').textContent = `${loc + matched} 条`;
  $('#syncMatched').textContent = `${matched} 条`;
  $('#syncAt').textContent = sy.synced_at ? `${fmtDate(sy.synced_at)} ${fmtClock(sy.synced_at)}` : '—';
  $('#syncTag').textContent = sy.synced_at ? (sy.live ? '真实数据' : '演示数据') : '未同步';
  $('#syncTag').style.color = sy.live ? '#2ee07f' : (sy.synced_at ? '#e3b341' : '');

  const btn = $('#btnQuickSync');
  btn.className = 'syncbtn' + (S.busy ? ' busy' : sy.synced_at ? (sy.live ? ' live' : ' demo') : '');
  $('#syncLabel').textContent = S.busy ? '同步中' : sy.synced_at ? (sy.live ? '已同步' : '演示') : '同步';

  // 账号
  const c = S.cred || {};
  if (document.activeElement !== $('#cNum')) $('#cNum').value = c.student_num || '';
  if (document.activeElement !== $('#cUid')) $('#cUid').value = c.uid || '';
  if (document.activeElement !== $('#cHost')) $('#cHost').value = c.api_host || '';
  if (document.activeElement !== $('#cProxy')) $('#cProxy').value = c.proxy || '';
  $('#cTokenMask').textContent = c.token_set ? `已配置 ${c.token_mask}` : '未配置';
  $('#cTokenMask').style.color = c.token_set ? '#2ee07f' : '';
}

function renderPolicy() {
  const p = S.boot.policy;
  const rows = [
    ['单次有效里程', `${p.dist_lo_km} ~ ${p.dist_hi_km} km`],
    ['配速区间', `${fmtPace(p.pace_lo)} ~ ${fmtPace(p.pace_hi)} /km`],
    ['打卡半径', `${p.checkin_radius_m} m`],
    ['每日上限', `${p.max_per_day} 次`],
    ['开放时段', `${p.allowed_hours[0]}:00 ~ ${p.allowed_hours[1]}`],
  ];
  $('#policyList').innerHTML = rows.map(([k, v]) => `<div class="kv"><span>${k}</span><b>${v}</b></div>`).join('');
}

function renderProfile() {
  const p = S.dash?.profile || {};
  if (document.activeElement !== $('#pName')) $('#pName').value = p.name || '';
  if (document.activeElement !== $('#pTarget')) $('#pTarget').value = p.target_km || '';
  $$('#genderSeg button').forEach((b) => b.classList.toggle('on', b.dataset.v === (p.gender || 'male')));
}

/* ============================================================ 5. 流程 */
function resetDraft() {
  S.draft = null; S.savedId = null; S.stage = 'idle';
  S.map.stop(true);
  $('#btnMain').textContent = '开始跑步';
  $('#btnPlay').hidden = true;
  $('#saveBadge').textContent = '未保存';
  ['#btnGpx', '#btnJson', '#btnProto', '#btnDryrun', '#btnSave'].forEach((q) => { $(q).disabled = true; });
  renderMetrics(false); renderRules(null); renderCheckpoints();
  syncMap();
}

async function doGenerate() {
  if (S.busy) return;
  S.busy = true;
  const btn = $('#btnMain');
  btn.disabled = true; btn.textContent = '生成中…';
  try {
    const d = await api('/api/generate', {
      campus_id: S.campus, route_id: S.route,
      distance_km: parseFloat($('#distNum').value || '3'),
      pace_sec: parseInt($('#paceNum').value || '330', 10),
      start_at: $('#startAt').value,
      seed: $('#seedInput').value.trim() || null,
      engine: $('#engineSel').value,
    });
    S.draft = d; S.savedId = null; S.stage = 'ready';
    renderMetrics(false); renderRules(d.validation); renderCheckpoints(); syncMap();
    $('#btnMain').textContent = '结束并保存';
    $('#btnPlay').hidden = false;
    $('#saveBadge').textContent = '未保存';
    $('#btnSave').disabled = false;
    $('#btnVerify').disabled = false;
    $('#btnDryrun').disabled = false;
    ['#btnGpx', '#btnJson', '#btnProto'].forEach((q) => { $(q).disabled = true; });
    toast(`已生成 ${d.metrics.distance_km.toFixed(2)} km · ${fmtPace(d.metrics.avg_pace)}/km`);
    startPlayback();
  } catch (e) {
    toast(e.message, 'err');
    S.stage = 'idle';
    btn.textContent = '开始跑步';
  } finally {
    S.busy = false;
    btn.disabled = false;
  }
}

function startPlayback() {
  S.map.playFrom((pt) => renderMetrics(true));
  $('#btnPlay').textContent = '暂停';
}
function stopPlayback() {
  S.map.stop(true);
  $('#btnPlay').textContent = '回放';
  renderMetrics(false);
}

async function saveDraft() {
  if (!S.draft) return;
  try {
    const j = await api('/api/records', { draft: S.draft });
    S.savedId = j.record.id;
    S.stage = 'saved';
    $('#saveBadge').textContent = `已保存 ${j.record.id}`;
    $('#btnSave').disabled = true;
    ['#btnGpx', '#btnJson', '#btnProto'].forEach((q) => { $(q).disabled = false; });
    $('#btnMain').textContent = '再跑一次';
    await refreshDashboard();
    toast('已保存到本地记录库');
  } catch (e) { toast(e.message, 'err'); }
}

async function refreshDashboard() {
  const j = await api('/api/dashboard');
  S.dash = j;
  S.sync = j.sync;
  renderRecords(); renderSync(); renderProfile();
}

async function doSync(silent) {
  if (S.busy) return;
  S.busy = true;
  renderSync();
  const log = (m) => { $('#syncLog').textContent = m; };
  log(`→ 适配器 ${S.adapter} …`);
  try {
    const j = await api('/api/sync', { adapter: S.adapter });
    S.dash = j.dashboard;
    S.sync = j.sync;
    renderRecords(); renderSync(); renderProfile();
    log([`✓ ${j.note}`,
         `新增 ${j.added} · 更新 ${j.updated} · 共 ${j.total} 条`,
         `耗时 ${j.elapsed_ms}ms · 源=${j.source}${j.live ? '（真实）' : '（演示）'}`,
         `同步时间 ${new Date().toLocaleTimeString()}`].join('\n'));
    if (!silent) toast(`同步完成：${j.total} 条记录`);
  } catch (e) {
    log(`✗ ${e.message}`);
    toast(e.message, 'err');
    try { S.sync = (await api('/api/sync/status')).sync; renderSync(); } catch (_) {}
  } finally {
    S.busy = false;
    renderSync();
  }
}

/* ============================================================ 6. 绑定 */
function switchView(name) {
  $$('.tabbar button').forEach((b) => b.classList.toggle('on', b.dataset.view === name));
  $$('.view').forEach((v) => v.classList.toggle('on', v.id === `view-${name}`));
  $('#actionbar').hidden = name !== 'run';
  if (name === 'run') setTimeout(() => S.map.resize(), 30);
}

function bind() {
  $$('.tabbar button').forEach((b) => { b.onclick = () => switchView(b.dataset.view); });

  // 距离/配速联动
  $('#distRange').oninput = () => { $('#distNum').value = $('#distRange').value; syncDist(); };
  $('#distNum').oninput = syncDist;
  $('#paceRange').oninput = () => { $('#paceNum').value = $('#paceRange').value; syncPace(); };
  $('#paceNum').oninput = syncPace;
  $('#seedInput').oninput = () => { $('#abSub').dataset.seed = $('#seedInput').value; };
  $('#btnDice').onclick = () => { $('#seedInput').value = String(Math.floor(Math.random() * 1e6)); };

  // 主操作
  $('#btnMain').onclick = () => {
    if (S.stage === 'idle') doGenerate();
    else if (S.stage === 'ready') saveDraft();
    else if (S.stage === 'saved') resetDraft();
  };
  $('#btnPlay').onclick = () => {
    if (!S.draft) return;
    if (S.map.play.on) { stopPlayback(); } else { startPlayback(); }
  };
  $('#btnFit').onclick = () => S.map.fit();

  // 同步
  $('#btnSync').onclick = () => doSync(false);
  $('#btnSync2').onclick = () => { switchView('sync'); doSync(false); };
  $('#btnQuickSync').onclick = () => { switchView('sync'); doSync(false); };

  // 数据源按钮在 boot 里渲染（需要 S.boot）
  // 账号
  $('#btnCredSave').onclick = async () => {
    try {
      const j = await api('/api/credentials', {
        student_num: $('#cNum').value.trim(),
        uid: $('#cUid').value.trim(),
        token: $('#cToken').value.trim(),
        api_host: $('#cHost').value.trim(),
        proxy: $('#cProxy').value.trim(),
      });
      S.cred = j.credentials;
      $('#cToken').value = '';
      renderSync();
      toast('账号已保存（仅本机）');
    } catch (e) { toast(e.message, 'err'); }
  };
  $('#btnCredClear').onclick = async () => {
    try {
      const j = await api('/api/credentials/clear-token', {});
      S.cred = j.credentials;
      renderSync();
      toast('token 已清除');
    } catch (e) { toast(e.message, 'err'); }
  };

  // 档案
  $('#btnProfSave').onclick = async () => {
    try {
      await api('/api/profile', {
        name: $('#pName').value.trim(),
        gender: ($('#genderSeg button.on') || {}).dataset?.v || 'male',
        target_km: $('#pTarget').value.trim() || null,
      });
      await refreshDashboard();
      toast('档案已保存');
    } catch (e) { toast(e.message, 'err'); }
  };
  $$('#genderSeg button').forEach((b) => {
    b.onclick = async () => {
      $$('#genderSeg button').forEach((x) => x.classList.remove('on'));
      b.classList.add('on');
      const sem = S.boot.policy.semester || {};
      $('#pTarget').value = sem[b.dataset.v] || '';
      try {
        await api('/api/profile', { gender: b.dataset.v, target_km: $('#pTarget').value });
        await refreshDashboard();
      } catch (e) { toast(e.message, 'err'); }
    };
  });

  // 记录筛选
  $$('#recFilter .chip').forEach((c) => {
    c.onclick = () => {
      S.filter = c.dataset.f;
      $$('#recFilter .chip').forEach((x) => x.classList.toggle('on', x === c));
      renderRecords();
    };
  });

  // 导出 / 预检 / 预演
  $('#btnSave').onclick = saveDraft;
  $('#btnVerify').onclick = async () => {
    if (!S.draft) return;
    try {
      const j = await api('/api/verify', { draft: S.draft });
      renderRules(j.validation);
      toast(`预检 ${j.validation.verdict.toUpperCase()} · ${j.validation.passed}/${j.validation.total}`);
    } catch (e) { toast(e.message, 'err'); }
  };
  const exp = (fmt) => {
    if (!S.savedId) { toast('先保存再导出', 'warn'); return; }
    window.open(`/api/records/${S.savedId}/export/${fmt}`, '_blank');
  };
  $('#btnGpx').onclick = () => exp('gpx');
  $('#btnJson').onclick = () => exp('json');
  $('#btnProto').onclick = () => exp('protocol');
  $('#btnDryrun').onclick = async () => {
    if (!S.draft) return;
    try {
      const j = await api('/api/submit', { draft: S.draft });
      const done = j.steps.filter((s) => s.state === 'pass').length;
      toast(`离线预演 ${j.steps.length} 步：${done} 步就绪 / ${j.steps.length - done} 步待接入`);
    } catch (e) { toast(e.message, 'err'); }
  };

  window.onPlayState = (on) => {
    $('#btnPlay').textContent = on ? '暂停' : '回放';
    if (!on) renderMetrics(false);
  };
}

function syncDist() {
  const v = parseFloat($('#distNum').value || '3');
  $('#distRange').value = Math.max(1, Math.min(10, v));
  $('#vDist').textContent = `${v.toFixed(2)} km`;
  renderCoverHint();
}
function syncPace() {
  const v = Math.max(120, Math.min(900, parseFloat($('#paceNum').value || '330')));
  $('#paceRange').value = Math.max(180, Math.min(540, v));
  $('#vPace').textContent = `${fmtPace(v)}/km`;
}

/* ============================================================ 7. 启动 */
async function boot() {
  S.map = new RunMap($('#map'));
  let j;
  try {
    j = await api('/api/bootstrap');
  } catch (e) {
    toast(`连不上本地服务：${e.message}`, 'err');
    return;
  }
  S.boot = j;
  S.dash = j.dashboard;
  S.sync = j.sync;
  S.cred = j.credentials;
  S.adapter = 'auto';
  S.campus = j.campuses[0]?.id || null;
  S.route = j.campuses[0]?.routes[0]?.id || null;

  // 引擎下拉
  const sel = $('#engineSel');
  sel.innerHTML = '';
  j.engines.forEach((e) => {
    const o = el('option', '', `${e.label}${e.available ? '' : '（不可用）'}`);
    o.value = e.name; o.disabled = !e.available;
    sel.appendChild(o);
  });
  const first = j.engines.find((e) => e.available);
  if (first) sel.value = first.name;

  // 默认出发时间
  const now = new Date();
  now.setMinutes(Math.floor(now.getMinutes() / 5) * 5, 0, 0);
  const pad = (n) => String(n).padStart(2, '0');
  $('#startAt').value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;

  renderCampusChips(); renderRouteChips(); renderCheckpoints();
  renderSyncSeg(); renderPolicy(); renderRecords(); renderSync(); renderProfile(); renderRules(null);
  syncMap(); resetDraft(); syncDist(); syncPace();

  if (!S.dash?.sync?.synced_at) {
    // 首次打开自动同步一次（演示/真实由适配器决定），让界面立刻有数据
    doSync(true);
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  bind();
  await boot();
});
