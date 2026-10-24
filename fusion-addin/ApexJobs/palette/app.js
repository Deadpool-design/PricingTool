/* Apex Orders panel. Talks to ApexJobs.py through adsk.fusionSendData (JS -> Python)
   and window.fusionJavaScriptHandler (Python -> JS). All validation lives in Python
   (orders.py) so manual and Shopify orders follow the same rules. */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const ICONS = {
  award: '<svg viewBox="0 0 48 32"><rect x="6" y="4" width="36" height="24" rx="3" fill="none" stroke="currentColor" stroke-width="3.6"/><path d="M13 21 h22" stroke="currentColor" stroke-width="3.4" stroke-linecap="round"/></svg>',
  birth: '<svg viewBox="0 0 48 32"><path d="M13 29 L24 3 L35 29 M17.5 19 H30.5" fill="none" stroke="currentColor" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"/></svg>',
};
const STATUS_LABEL = { pending: 'To build', building: 'Building…', review: 'To review', approved: 'Approved', rejected: 'Rejected', failed: 'Failed' };
const TYPE_LABEL = { award: 'Oscar Award', birth: 'Baby Birth Letter' };

const state = {
  boot: null, type: null, editingId: null, touched: new Set(), submitted: false,
  errors: {}, letter: null, loadedLetter: null, orders: [], filter: null, detail: null,
  birth: { colour: null, animal: null },
};

/* ---------------------------------------------------------------- bridge */
async function call(action, data = {}) {
  const raw = await window.adsk.fusionSendData(action, JSON.stringify(data));
  const r = JSON.parse(raw || '{}');
  if (!r.ok) { console.error(r.trace); throw new Error(r.error || 'Unknown error'); }
  return r;
}

window.fusionJavaScriptHandler = {
  handle(action, data) {
    try {
      if (action === 'orderUpdated') onOrderUpdated(JSON.parse(data));
    } catch (e) { console.error(e); }
    return 'OK';
  },
};

function toast(text, kind = '') {
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = text;
  const box = $('#toasts');
  while (box.children.length >= 2) box.firstChild.remove();
  box.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

/* ---------------------------------------------------------------- views */
function showView(name) {
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.view === name));
  $('#view-new').hidden = name !== 'new';
  $('#view-queue').hidden = name !== 'queue';
  if (name === 'queue') renderQueue();
}

function pickType(type) {
  state.type = type;
  state.touched.clear(); state.submitted = false;
  $$('.pick').forEach(p => { p.classList.toggle('selected', p.dataset.type === type); p.setAttribute('aria-checked', p.dataset.type === type); });
  $('#form-award').hidden = type !== 'award';
  $('#form-birth').hidden = type !== 'birth';
  $('#empty-pick').hidden = !!type;
  $('#form-actions').hidden = !type;
  validateSoon();
}

/* ---------------------------------------------------------------- collect */
function collect() {
  if (state.type === 'award') {
    const f = $('#form-award');
    return {
      type: 'award',
      fields: {
        lines: $$('[data-line]', f).map(i => i.value),
        job_name: f.elements.job_name.value,
        small_h_mm: f.elements.small_h_mm.value, name_h_mm: f.elements.name_h_mm.value,
      },
    };
  }
  const f = $('#form-birth');
  const fields = { colour: state.birth.colour || '', animal: state.birth.animal || '' };
  ['baby_name', 'time', 'date', 'weight', 'height', 'letter', 'letter_height_mm', 'letter_thickness_mm', 'min_overlap']
    .forEach(n => { fields[n] = f.elements[n].value; });
  return { type: 'birth', fields, overrides: collectOverrides() };
}

function collectOverrides() {
  const out = {};
  $$('#layout-rows [data-key]').forEach(row => {
    const v = $$('input', row).map(i => i.value.trim());
    if (v.some(Boolean)) (out.LAYOUT ||= {})[row.dataset.key] = v;
  });
  $$('#size-rows [data-key]').forEach(row => {
    const v = $('input', row).value.trim();
    if (v) (out.SIZE ||= {})[row.dataset.key] = v;
  });
  return out;
}

/* ---------------------------------------------------------------- validation */
let vTimer = null, vSeq = 0;
function validateSoon() { clearTimeout(vTimer); vTimer = setTimeout(validate, 220); renderPreview(); }

async function validate() {
  if (!state.type) return;
  const seq = ++vSeq;
  let r;
  try { r = await call('validate', collect()); } catch (e) { return toast(e.message, 'err'); }
  if (seq !== vSeq) return;
  state.errors = r.errors || {};
  renderFeedback(r);
  if (state.type === 'birth' && r.letter !== state.letter) {
    state.letter = r.letter;
    loadLetterOverrides(r.letter);
    renderPreview();
  }
}

function renderFeedback(r) {
  const form = state.type === 'award' ? $('#form-award') : $('#form-birth');
  $$('.field', form).forEach(f => { f.classList.remove('has-error'); $('.err-msg', f)?.remove(); });
  for (const [k, msg] of Object.entries(state.errors)) {
    const field = $(`.field[data-field="${k}"]`, form);
    if (!field || !(state.submitted || state.touched.has(k))) continue;
    field.classList.add('has-error');
    field.insertAdjacentHTML('beforeend', `<div class="err-msg">${esc(msg)}</div>`);
  }
  const fb = $('#feedback');
  fb.innerHTML = [
    ...(r.info || []).map(m => `<div class="msg info"><b>ℹ</b><span>${esc(m)}</span></div>`),
    ...(r.warnings || []).map(m => `<div class="msg warn"><b>!</b><span>${esc(m)}</span></div>`),
  ].join('');
  const bad = Object.keys(state.errors).length > 0;
  $('#btn-build').disabled = bad;
  $('#btn-queue').disabled = bad;
}

/* ---------------------------------------------------------------- previews */
const measureCtx = document.createElement('canvas').getContext('2d');
// award-text plaque rules (Script A): Fusion text height = capital height; lines fit 46 mm;
// small lines Franklin Gothic Medium Cond 5.1 mm, the name (last line) Demi Cond up to 6.45 mm,
// switching to Medium Cond below 6 mm; block fits 27 mm with 3.6 mm gaps; under 4 mm is refused.
const PLAQUE = { w: 50, h: 34, maxLen: 46, gap: 3.6, vMargin: 3.5, minH: 4.0, nameMinH: 6.0, capRatio: 0.7 };
const FONT_SMALL = '"Franklin Gothic Medium Cond", "Arial Narrow", sans-serif';
const FONT_NAME = '"Franklin Gothic Demi Cond", "Arial Narrow", sans-serif';
function textWidthMm(text, hMm, font, weight) {
  measureCtx.font = `${weight} 100px ${font}`;
  return measureCtx.measureText(text).width / 100 * (hMm / PLAQUE.capRatio);
}

// Same fit rule as award_text.py. Fusion measures the real glyphs, so this is an estimate.
function plaqueFit(lines, smallH, nameH) {
  const n = lines.length;
  const out = lines.map((s, i) => {
    const isName = i === n - 1;
    let font = isName ? FONT_NAME : FONT_SMALL, weight = isName ? 700 : 500;
    const hmax = isName ? nameH : smallH;
    for (let attempt = 0; attempt < 2; attempt++) {
      const w = textWidthMm(s, hmax, font, weight);
      let h = w <= PLAQUE.maxLen ? hmax : hmax * PLAQUE.maxLen / w;
      if (isName && n > 1 && font === FONT_NAME && h < PLAQUE.nameMinH && attempt === 0) { font = FONT_SMALL; weight = 500; continue; }
      return { text: s, h: Math.floor(h * 20) / 20, font, weight, light: isName && font === FONT_SMALL };
    }
  });
  const usable = PLAQUE.h - 2 * PLAQUE.vMargin;
  let block = out.reduce((a, l) => a + l.h, 0) + PLAQUE.gap * (n - 1);
  if (block > usable) {
    const k = (usable - PLAQUE.gap * (n - 1)) / out.reduce((a, l) => a + l.h, 0);
    out.forEach(l => { l.h = Math.floor(l.h * k * 20) / 20; });
    block = out.reduce((a, l) => a + l.h, 0) + PLAQUE.gap * (n - 1);
  }
  return { lines: out, block };
}

function renderPreview() {
  if (state.type === 'award') {
    const f = $('#form-award');
    const inputs = $$('[data-line]', f);
    const filled = inputs.filter(i => i.value.trim());
    const nameInput = filled[filled.length - 1];
    inputs.forEach(i => {
      const isName = i === nameInput && filled.length > 1;
      const c = i.parentElement.querySelector('.counter');
      const n = i.value.trim().length, fit = isName || filled.length === 1 ? 11 : 14;
      c.textContent = n ? `${n}/${fit}` : '';
      c.classList.toggle('over', n > fit);
      i.closest('.field').querySelector('.tag').hidden = !(i === nameInput);
    });
    const g = $('#plaque-text');
    const size = $('#plaque-size');
    const lines = filled.map(i => i.value.trim());
    if (!lines.length) {
      g.innerHTML = `<text x="25" y="18.6" font-size="5" fill="rgba(0,0,0,.3)" style="font-family:${esc(FONT_NAME)}">Winner name</text>`;
      size.hidden = true;
      return;
    }
    const num = (el, d) => { const v = parseFloat(String(el.value).replace(',', '.')); return v > 0 ? v : d; };
    const fit = plaqueFit(lines, num(f.elements.small_h_mm, 5.1), num(f.elements.name_h_mm, 6.45));
    let y = PLAQUE.h / 2 - fit.block / 2;
    g.innerHTML = fit.lines.map(l => {
      y += l.h;
      const t = `<text x="25" y="${y.toFixed(2)}" font-size="${(l.h / PLAQUE.capRatio).toFixed(2)}" style="font-family:${esc(l.font)};font-weight:${l.weight}">${esc(l.text)}</text>`;
      y += PLAQUE.gap;
      return t;
    }).join('');
    const minH = Math.min(...fit.lines.map(l => l.h));
    const nameH = fit.lines[fit.lines.length - 1].h;
    size.hidden = false;
    size.textContent = minH < PLAQUE.minH ? `≈ ${minH.toFixed(1)} mm · too small` : `≈ name ${nameH.toFixed(1)} mm`;
    size.className = 'pill' + (minH < PLAQUE.minH ? ' err' : fit.lines.some(l => l.light) ? ' warn' : '');
    size.title = minH < PLAQUE.minH ? 'The build will refuse letters under 4 mm. Shorten a line or move a word.'
      : fit.lines.some(l => l.light) ? 'The name shrinks under 6 mm, so it switches to the lighter font.' : '';
    return;
  }
  if (state.type === 'birth') {
    const f = $('#form-birth').elements;
    const name = f.baby_name.value.trim();
    const letter = (f.letter.value.trim() || name[0] || 'A').toUpperCase();
    $('#bp-letter').textContent = letter;
    $('#bp-name').textContent = name || 'Baby name';
    $('#bp-name').classList.toggle('placeholder', !name);
    $('#birth-preview').classList.toggle('pink', state.birth.colour === 'pink');
    $$('#form-birth .unit').forEach(u => u.classList.toggle('has-unit', /[a-z]/i.test($('input', u).value)));
    const stats = [
      f.time.value.trim() && '🕐 ' + f.time.value.trim(),
      f.date.value.trim() && '📅 ' + f.date.value.trim(),
      f.weight.value.trim() && '⚖ ' + f.weight.value.trim() + (/^[\d.,\s]+$/.test(f.weight.value) ? ' g' : ''),
      f.height.value.trim() && '📏 ' + f.height.value.trim() + (/^[\d.,\s]+$/.test(f.height.value) ? ' cm' : ''),
      state.birth.animal && cap(state.birth.animal),
    ].filter(Boolean);
    $('#bp-stats').innerHTML = stats.map(s => `<span>${esc(s)}</span>`).join('');
  }
}
const cap = s => s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

/* ---------------------------------------------------------------- birth form widgets */
function buildBirthWidgets() {
  const b = state.boot;
  $('#colours').innerHTML = b.colours.map(c =>
    `<button type="button" class="swatch" data-colour="${c}"><i style="background:var(--${c})"></i>${cap(c)}</button>`).join('');
  $('#animals').innerHTML = b.animals.map(a =>
    `<button type="button" class="chip" data-animal="${a}">${cap(a)}</button>`).join('');
  $$('#colours .swatch').forEach(s => s.onclick = () => setChoice('colour', s.dataset.colour));
  $$('#animals .chip').forEach(s => s.onclick = () => setChoice('animal', s.dataset.animal));
  buildOverrideRows();
}

function setChoice(kind, val) {
  state.birth[kind] = val;
  state.touched.add(kind);
  $$(kind === 'colour' ? '#colours .swatch' : '#animals .chip').forEach(el =>
    el.classList.toggle('selected', el.dataset[kind] === val));
  validateSoon();
}

function buildOverrideRows() {
  const d = state.boot.birthDefaults || { LAYOUT: {}, SIZE: {} };
  const note = $('#layout-note');
  if (d.error) {
    note.hidden = false;
    note.textContent = `Couldn't read birth_letter.py, so override keys are unknown: ${d.error}. Fix the path in Settings.`;
  } else if (!Object.keys(d.LAYOUT).length && !Object.keys(d.SIZE).length) {
    note.hidden = false;
    note.textContent = 'birth_letter.py has no LAYOUT or SIZE tables to override.';
  } else note.hidden = true;
  const L = Object.entries(d.LAYOUT);
  $('#layout-rows').innerHTML = L.length ? '<div class="ov-head">Insert spot</div><div class="ov-head">x</div><div class="ov-head">y</div>' +
    L.map(([k, v]) => `<div class="ov-key">${esc(cap(k))}</div><div style="display:contents" data-key="${esc(k)}">${
      v.slice(0, 2).map(x => `<input placeholder="${x}" inputmode="decimal">`).join('')}</div>`).join('') : '';
  const S = Object.entries(d.SIZE);
  $('#size-rows').innerHTML = S.length ? '<div class="ov-head">Size</div><div class="ov-head">value</div><div></div>' +
    S.map(([k, v]) => `<div class="ov-key">${esc(cap(k))}</div><div style="display:contents" data-key="${esc(k)}"><input placeholder="${Array.isArray(v) ? v.join(', ') : v}" inputmode="decimal"></div><div></div>`).join('') : '';
  $$('#layout-card .ov-table input').forEach(i => i.addEventListener('input', () => { i.classList.toggle('set', !!i.value.trim()); state.touched.add('overrides'); validateSoon(); }));
}

function fillOverrides(ov) {
  $$('#layout-card .ov-table input').forEach(i => { i.value = ''; i.classList.remove('set'); });
  for (const [k, v] of Object.entries(ov?.LAYOUT || {})) {
    const row = $(`#layout-rows [data-key="${CSS.escape(k)}"]`);
    if (row) $$('input', row).forEach((i, n) => { i.value = v[n] ?? ''; i.classList.toggle('set', !!i.value); });
  }
  for (const [k, v] of Object.entries(ov?.SIZE || {})) {
    const i = $(`#size-rows [data-key="${CSS.escape(k)}"] input`);
    if (i) { i.value = v; i.classList.add('set'); }
  }
}

async function loadLetterOverrides(letter) {
  const note = $('#layout-note');
  const hint = $('#layout-hint');
  if (!letter) return;
  const hasOwn = Object.keys(collectOverrides()).length > 0;
  if (hasOwn && state.loadedLetter === null) return;          // user typed their own - leave them
  const r = await call('letterOverrides', { letter }).catch(() => ({}));
  if (r.overrides) {
    fillOverrides(r.overrides);
    state.loadedLetter = letter;
    note.hidden = false;
    note.textContent = `Loaded the approved layout for letter ${letter}. Clear it to use the script's defaults.`;
    hint.textContent = `saved layout for ${letter}`;
    $('#layout-card').open = true;
  } else if (state.loadedLetter) {
    fillOverrides(null);
    state.loadedLetter = null;
    if (!state.boot.birthDefaults?.error) note.hidden = true;
    hint.textContent = 'move or resize inserts';
  }
  validateSoon();
}

/* ---------------------------------------------------------------- submit */
async function submit(buildNow) {
  state.submitted = true;
  await validate();
  if (Object.keys(state.errors).length) { toast('Fix the highlighted fields first', 'err'); return; }
  const payload = { ...collect(), buildNow, id: state.editingId || undefined };
  const btns = [$('#btn-build'), $('#btn-queue')];
  btns.forEach(b => b.disabled = true);
  try {
    const r = await call('save', payload);
    if (r.errors) { state.errors = r.errors; renderFeedback({}); return; }
    upsert(r.order);
    toast(buildNow ? `Building ${r.order.title}…` : `Added ${r.order.title} to the queue`, 'ok');
    resetForm();
    if (buildNow) { state.filter = 'todo'; }
    showView('queue');
  } catch (e) { toast(e.message, 'err'); }
  finally { btns.forEach(b => b.disabled = false); }
}

function resetForm() {
  $('#form-award').reset(); $('#form-birth').reset();
  state.birth = { colour: null, animal: null };
  $$('.swatch, .chip').forEach(el => el.classList.remove('selected'));
  fillOverrides(null);
  state.editingId = null; state.letter = null; state.loadedLetter = null;
  $('#editing-banner').hidden = true;
  $('#layout-hint').textContent = 'move or resize inserts';
  $('#feedback').innerHTML = '';
  pickType(null);
}

async function editOrder(id) {
  const { order } = await call('get', { id });
  resetForm();
  pickType(order.type);
  state.editingId = id;
  $('#editing-banner').hidden = false;
  $('#editing-title').textContent = TYPE_LABEL[order.type] + ' · ' + (order.ref?.shopify_order ? 'Shopify ' + order.ref.shopify_order : 'manual');
  const f = order.fields || {};
  if (order.type === 'award') {
    const lines = Array.isArray(f.lines) ? f.lines : String(f.lines || '').split('\n');
    $$('#form-award [data-line]').forEach((i, n) => i.value = lines[n] || '');
    const fa = $('#form-award');
    ['job_name', 'small_h_mm', 'name_h_mm'].forEach(k => fa.elements[k].value = f[k] ?? '');
  } else {
    const fb = $('#form-birth');
    ['baby_name', 'time', 'date', 'letter', 'letter_height_mm', 'letter_thickness_mm', 'min_overlap'].forEach(k => fb.elements[k].value = f[k] ?? '');
    fb.elements.weight.value = f.weight ?? f.weight_g ?? '';
    fb.elements.height.value = f.height ?? f.height_cm ?? '';
    if (f.colour || f.color) setChoice('colour', String(f.colour || f.color).toLowerCase());
    if (f.animal) setChoice('animal', String(f.animal).toLowerCase());
    fillOverrides(order.overrides);
    if (Object.keys(order.overrides || {}).length) $('#layout-card').open = true;
  }
  state.submitted = true;
  showView('new');
  validateSoon();
}

/* ---------------------------------------------------------------- queue */
const FILTERS = {
  todo: o => ['pending', 'building', 'failed', 'rejected'].includes(o.status),
  review: o => o.status === 'review',
  approved: o => o.status === 'approved',
  all: () => true,
};

function upsert(o) {
  const i = state.orders.findIndex(x => x.id === o.id);
  if (i >= 0) state.orders[i] = o; else state.orders.unshift(o);
  updateCounts();
}

function updateCounts() {
  const need = state.orders.filter(o => FILTERS.todo(o) || FILTERS.review(o)).length;
  const c = $('#queue-count');
  c.hidden = !need; c.textContent = need;
}

function ago(iso) {
  if (!iso) return '';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return 'just now';
  if (s < 3600) return Math.floor(s / 60) + ' min ago';
  if (s < 86400) return Math.floor(s / 3600) + ' h ago';
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function renderQueue() {
  if (!state.filter) state.filter = state.orders.some(FILTERS.review) ? 'review' : 'todo';
  $$('.fpill').forEach(p => {
    const n = state.orders.filter(FILTERS[p.dataset.f]).length;
    p.classList.toggle('active', p.dataset.f === state.filter);
    p.innerHTML = `${{ todo: 'To build', review: 'To review', approved: 'Approved', all: 'All' }[p.dataset.f]}<span class="n">${n}</span>`;
  });
  const list = state.orders.filter(FILTERS[state.filter]);
  const buildable = list.filter(o => o.status === 'pending' || o.status === 'failed');
  $('#batch').hidden = state.filter !== 'todo' || buildable.length < 2;
  $('#btn-build-all').textContent = `Build all ${buildable.length}`;
  const el = $('#queue-list');
  if (!list.length) {
    el.innerHTML = `<div class="empty"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12h8M8 8h8M8 16h5"/></svg><div>${
      { todo: 'Nothing to build.', review: 'Nothing waiting for review.', approved: 'No approved orders yet.', all: 'No orders yet.' }[state.filter]}</div></div>`;
    return;
  }
  el.innerHTML = list.map(o => {
    const src = o.source === 'shopify'
      ? `<span class="src shopify">Shopify ${esc(o.ref.shopify_order || '')}</span>` : `<span class="src">Manual</span>`;
    const acts = {
      pending: `<button class="btn primary small" data-act="build">Build</button><button class="btn ghost small" data-act="edit">Edit</button>`,
      failed: `<button class="btn ghost small" data-act="open">Details</button><button class="btn ghost small" data-act="edit">Edit</button>`,
      rejected: `<button class="btn ghost small" data-act="edit">Edit</button><button class="btn danger small" data-act="delete">Delete</button>`,
      building: `<div class="spinner"></div>`,
      review: `<button class="btn primary small" data-act="open">Review</button>`,
      approved: `<button class="btn ghost small" data-act="folder">STLs</button>`,
    }[o.status] || '';
    const clickable = ['review', 'approved', 'failed'].includes(o.status);
    return `<div class="order${clickable ? ' clickable' : ''}" data-id="${esc(o.id)}">
      <div class="otype ${o.type}">${ICONS[o.type] || ''}</div>
      <div style="min-width:0">
        <div class="otitle">${esc(o.title)}</div>
        <div class="ometa">${src}<span class="status ${o.status}">${STATUS_LABEL[o.status] || o.status}</span>${
          o.warnings ? `<span class="wcount">⚠ ${o.warnings}</span>` : ''}<span>${ago(o.updated || o.created)}</span></div>
      </div>
      <div class="oacts">${acts}</div></div>`;
  }).join('');
  $$('.order', el).forEach(row => {
    const id = row.dataset.id;
    row.addEventListener('click', e => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act) { e.stopPropagation(); return orderAction(act, id); }
      if (row.classList.contains('clickable')) openDetail(id);
    });
  });
}

async function orderAction(act, id) {
  try {
    if (act === 'build') { await call('build', { ids: [id], closeAfter: false }); markBuilding([id]); }
    if (act === 'edit') await editOrder(id);
    if (act === 'open') await openDetail(id);
    if (act === 'folder') await call('openFolder', { id });
    if (act === 'delete') {
      if (!confirm('Delete this order and its screenshots? STL files are kept.')) return;
      await call('delete', { id });
      state.orders = state.orders.filter(o => o.id !== id);
      updateCounts(); renderQueue();
    }
  } catch (e) { toast(e.message, 'err'); }
}

function markBuilding(ids) {
  ids.forEach(id => { const o = state.orders.find(x => x.id === id); if (o) o.status = 'building'; });
  renderQueue();
}

function onOrderUpdated(o) {
  const prev = state.orders.find(x => x.id === o.id);
  upsert(o);
  if (prev?.status === 'building' || o.status !== prev?.status) {
    if (o.status === 'review') toast(`${o.title} built - ready to review`, 'ok');
    if (o.status === 'failed') toast(`${o.title} failed: ${o.error || ''}`.slice(0, 140), 'err');
  }
  if (!$('#view-queue').hidden) renderQueue();
  if (state.detail?.id === o.id && o.status !== 'building') openDetail(o.id);
}

/* ---------------------------------------------------------------- review sheet */
async function openDetail(id) {
  let order;
  try { ({ order } = await call('get', { id })); } catch (e) { return toast(e.message, 'err'); }
  state.detail = order;
  const r = order.result || {};
  const sheet = $('#sheet-detail');
  $('#d-title').textContent = TYPE_LABEL[order.type] + ' · ' + (order.type === 'award'
    ? (order.fields.lines || []).filter(Boolean).join(' / ') : order.fields.baby_name);
  $('#d-meta').textContent = (order.source === 'shopify' ? `Shopify ${order.ref?.shopify_order || ''}${order.ref?.customer ? ' · ' + order.ref.customer : ''}` : 'Manual order') + ' · ' + ago(order.updated);
  const st = $('#d-status'); st.className = 'status ' + order.status; st.textContent = STATUS_LABEL[order.status];

  const f = order.clean || order.fields;
  const spec = order.type === 'award'
    ? [['Lines', (f.lines || []).filter(Boolean).map(esc).join('<br>')], ['Name', esc((f.lines || []).filter(Boolean).slice(-1)[0] || '')], ['Job', esc(f.job_name || '—')]]
    : [['Name', esc(f.baby_name)], ['Time', esc(f.time)], ['Date', esc(f.date)],
       ['Weight', esc(f.weight_g ? f.weight_g + ' g' : f.weight)], ['Height', esc(f.height_cm ? f.height_cm + ' cm' : f.height)],
       ['Animal', esc(cap(f.animal || ''))], ['Colour', esc(cap(f.colour || ''))]];
  const ov = order.overrides || {};
  const ovText = ['LAYOUT', 'SIZE'].flatMap(g => Object.entries(ov[g] || {}).map(([k, v]) => `${cap(k)}: ${[].concat(v).join(', ')}`));
  if (ovText.length) spec.push(['Overrides', esc(ovText.join(' · '))]);

  const imgs = r.images || [];
  let html = '';
  if (imgs.length) {
    html += `<img class="gallery-main" id="g-main" src="${imgs[0].src}" alt="${esc(imgs[0].name)}">
      <div class="thumbs">${imgs.map((im, i) => `<button data-i="${i}" class="${i ? '' : 'active'}"><img src="${im.src}" alt=""><span>${esc(im.name.replace('.png', '').replace('-', ' '))}</span></button>`).join('')}</div>`;
  }
  if (r.error) html += `<div class="msg err" style="margin-bottom:10px"><b>✕</b><span>${esc(r.error)}</span></div>`;
  html += `<div class="feedback" style="margin-bottom:10px">${
    (r.notes || []).map(m => `<div class="msg info"><b>ℹ</b><span>${esc(m)}</span></div>`).join('')}${
    (r.warnings || []).map(m => `<div class="msg warn"><b>!</b><span>${esc(m)}</span></div>`).join('')}</div>`;
  html += `<section class="card"><h3>Order</h3><dl class="kv">${spec.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${
    order.notes ? `<p class="muted small" style="margin:8px 0 0">${esc(order.notes)}</p>` : ''}</section>`;
  if (order.status === 'review') {
    html += `<section class="card checklist"><h3>Check before approving</h3>${
      order.checks.map((c, i) => `<label><input type="checkbox" data-check="${i}"><span>${esc(c)}</span></label>`).join('')}</section>`;
  }
  if (r.output) html += `<details class="card collapsible"><summary>Script output</summary><pre class="log">${esc(r.output)}</pre></details>`;
  if (r.trace) html += `<details class="card collapsible"><summary>Error details</summary><pre class="log">${esc(r.trace)}</pre></details>`;
  $('#d-body').innerHTML = html;

  $$('.thumbs button').forEach(b => b.onclick = () => {
    $$('.thumbs button').forEach(x => x.classList.toggle('active', x === b));
    $('#g-main').src = imgs[b.dataset.i].src;
  });
  $('#g-main')?.addEventListener('click', e => { const lb = $('#lightbox'); $('img', lb).src = e.target.src; lb.hidden = false; });

  const acts = $('#d-actions');
  if (order.status === 'review') {
    acts.innerHTML = `<button class="btn ghost" data-a="folder">STL folder</button><button class="btn danger" data-a="reject">Reject</button><button class="btn ok" data-a="approve" disabled>Approve</button>`;
    const boxes = $$('[data-check]');
    const sync = () => { $('[data-a="approve"]').disabled = !boxes.every(b => b.checked); };
    boxes.forEach(b => b.onchange = sync);
  } else if (order.status === 'failed' || order.status === 'rejected') {
    const invalid = /^Order is invalid/.test(r.error || '');   // rebuilding cannot help - it needs an edit
    acts.innerHTML = `<button class="btn ${invalid ? 'primary' : 'ghost'}" data-a="edit">Edit order</button>${invalid ? '' : '<button class="btn primary" data-a="build">Build again</button>'}`;
  } else if (order.status === 'approved') {
    acts.innerHTML = `<button class="btn ghost" data-a="reopen">Back to review</button><button class="btn primary" data-a="folder">Open STL folder</button>`;
  } else acts.innerHTML = '';
  $$('[data-a]', acts).forEach(b => b.onclick = () => detailAction(b.dataset.a, order));
  sheet.hidden = false;
}

async function detailAction(a, order) {
  try {
    if (a === 'folder') return void await call('openFolder', { id: order.id });
    if (a === 'edit') { closeSheets(); return void await editOrder(order.id); }
    if (a === 'build') { await call('build', { ids: [order.id], closeAfter: false }); markBuilding([order.id]); closeSheets(); return; }
    const status = { approve: 'approved', reject: 'rejected', reopen: 'review' }[a];
    const r = await call('setStatus', { id: order.id, status });
    upsert(r.order);
    toast(a === 'approve' ? 'Approved - ready to print' : a === 'reject' ? 'Rejected - edit and build again' : 'Moved back to review', a === 'approve' ? 'ok' : '');
    closeSheets(); renderQueue();
  } catch (e) { toast(e.message, 'err'); }
}

function closeSheets() { $$('.sheet').forEach(s => s.hidden = true); state.detail = null; }

/* ---------------------------------------------------------------- settings */
function openSettings() {
  $('#s-script').value = state.boot.settings.birth_letter_script;
  $('#s-orders').value = state.boot.settings.orders_folder;
  const d = state.boot.birthDefaults;
  const s = $('#s-status');
  s.className = 'note';
  s.textContent = d?.error ? `birth_letter.py: ${d.error}` : `birth_letter.py loaded: ${Object.keys(d?.LAYOUT || {}).length} layout spots, ${Object.keys(d?.SIZE || {}).length} sizes.`;
  $('#sheet-settings').hidden = false;
}

async function saveSettings() {
  try {
    const r = await call('saveSettings', { birth_letter_script: $('#s-script').value, orders_folder: $('#s-orders').value });
    state.boot.birthDefaults = r.birthDefaults;
    state.boot.settings = { birth_letter_script: $('#s-script').value.trim(), orders_folder: $('#s-orders').value.trim() };
    buildOverrideRows();
    const list = await call('list');
    state.orders = list.orders; updateCounts();
    toast('Settings saved', 'ok');
    closeSheets();
  } catch (e) { toast(e.message, 'err'); }
}

/* ---------------------------------------------------------------- boot */
function wire() {
  $$('.tab').forEach(t => t.onclick = () => showView(t.dataset.view));
  $$('.pick').forEach(p => p.onclick = () => { if (state.type !== p.dataset.type) pickType(p.dataset.type); });
  for (const form of [$('#form-award'), $('#form-birth')]) {
    form.addEventListener('submit', e => e.preventDefault());
    form.addEventListener('input', e => {
      const t = e.target;
      if (t.dataset.line !== undefined) state.touched.add('lines');
      else if (t.name) state.touched.add(t.name);
      validateSoon();
    });
  }
  $('#btn-build').onclick = () => submit(true);
  $('#btn-queue').onclick = () => submit(false);
  $('#btn-cancel-edit').onclick = resetForm;
  $('#btn-clear-ov').onclick = () => { fillOverrides(null); state.loadedLetter = null; $('#layout-hint').textContent = 'move or resize inserts'; validateSoon(); };
  $$('.fpill').forEach(p => p.onclick = () => { state.filter = p.dataset.f; renderQueue(); });
  $('#btn-build-all').onclick = async () => {
    const ids = state.orders.filter(FILTERS.todo).filter(o => o.status === 'pending' || o.status === 'failed').map(o => o.id);
    try { await call('build', { ids, closeAfter: $('#close-after').checked }); markBuilding(ids); toast(`Building ${ids.length} orders…`); }
    catch (e) { toast(e.message, 'err'); }
  };
  $('#btn-settings').onclick = openSettings;
  $('#btn-save-settings').onclick = saveSettings;
  $$('[data-close]').forEach(b => b.onclick = closeSheets);
  $('#lightbox').onclick = () => { $('#lightbox').hidden = true; };
  document.addEventListener('keydown', e => { if (e.key === 'Escape') { if (!$('#lightbox').hidden) $('#lightbox').hidden = true; else closeSheets(); } });
}

async function boot() {
  try {
    state.boot = await call('init');
  } catch (e) {
    $('#connecting').innerHTML = `<div class="msg err"><b>✕</b><span>${esc(e.message)}</span></div>`;
    return;
  }
  state.orders = state.boot.orders;
  $('#connecting').hidden = true;
  buildBirthWidgets();
  wire();
  updateCounts();
  const waiting = state.orders.some(o => FILTERS.review(o) || o.status === 'pending');
  showView(waiting ? 'queue' : 'new');
}

document.addEventListener('DOMContentLoaded', () => {
  const wait = setInterval(() => {
    if (window.adsk && window.adsk.fusionSendData) { clearInterval(wait); boot(); }
  }, 100);
});
