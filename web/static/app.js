/* StegoForge Web UI - Interactive JavaScript */
'use strict';

const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

// ── security helpers ─────────────────────────────────────────────────────────
// Everything that reaches innerHTML and did not come from this file goes through esc():
// detector output is built from the contents of files the user is *analysing*.
function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

const TOKEN_KEY = 'stegoforge.token';

function webToken() {
  try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch (_) { return ''; }
}

// `http://localhost:5000/?token=…` hands the UI its token once; keep it for the tab
// and take it out of the address bar / history.
(function captureToken() {
  const url = new URL(window.location.href);
  const token = url.searchParams.get('token');
  if (!token) return;
  try { sessionStorage.setItem(TOKEN_KEY, token); } catch (_) { /* private mode */ }
  url.searchParams.delete('token');
  window.history.replaceState(null, '', url.pathname + url.search + url.hash);
})();

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = webToken();
  if (token) headers.set('X-Stego-Token', token);
  return fetch(url, { ...options, headers });
}

let latestCTFReport = null;
let latestCTFText = '';
let platformProfiles = {};

// Client-side size guard: refuse an oversize file before anything is uploaded, inline (no alert()).
function showFileError(input, message) {
  const info = input.closest('.form-group') && input.closest('.form-group').querySelector('.file-info');
  if (!info) return;
  info.textContent = message;
  info.classList.add('is-error');
}

document.addEventListener('submit', (e) => {
  const form = e.target;
  if (!form || !form.querySelector) return;
  for (const input of form.querySelectorAll('input[type="file"]')) {
    for (const f of input.files || []) {
      if (f.size > MAX_UPLOAD_BYTES) {
        e.preventDefault();
        e.stopImmediatePropagation();
        showFileError(input, `${f.name} is ${formatBytes(f.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`);
        input.focus();
        return;
      }
    }
  }
}, true);

function artifactHref(payload) {
  // Opaque artifact IDs (server no longer accepts ?path=).
  if (payload && payload.artifact_id) {
    const token = webToken();
    // A plain download link cannot set headers, so it carries the token in the query.
    return `/artifact/${encodeURIComponent(payload.artifact_id)}${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  }
  return null;
}

function $(id) {
  return document.getElementById(id);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function ico(name) {
  return `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

// Non-blocking progress bar. `pct` (0-100) makes it determinate; without it the bar sweeps.
function showLoading(msg = 'Working…', pct = null) {
  $('loading-text').textContent = msg;
  const track = document.querySelector('#loading-overlay .loading-track');
  if (track) {
    track.classList.toggle('determinate', typeof pct === 'number');
    if (typeof pct === 'number') track.style.setProperty('--pct', `${Math.max(2, Math.min(100, pct))}%`);
  }
  $('loading-overlay').style.display = 'block';
  document.body.classList.add('busy');
}

function hideLoading() {
  $('loading-overlay').style.display = 'none';
  document.body.classList.remove('busy');
}

const TAB_IDS = Array.from(document.querySelectorAll('.tab-btn')).map((b) => b.dataset.tab);

function activateTab(tabId, { focus = false, updateHash = true } = {}) {
  if (!TAB_IDS.includes(tabId)) tabId = 'encode';
  document.querySelectorAll('.tab-btn').forEach((b) => {
    const on = b.dataset.tab === tabId;
    b.classList.toggle('active', on);
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
  });
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === `tab-${tabId}`));
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) {
    // Bring the active tab into view inside the (horizontally scrolling) nav, without scrolling the page.
    const nav = btn.parentElement;
    if (nav && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: Math.max(0, btn.offsetLeft - 24) });
    if (focus) btn.focus({ preventScroll: true });
  }
  if (updateHash && window.location.hash !== `#${tabId}`) {
    window.history.replaceState(null, '', `#${tabId}`);
  }
}

// Tab navigation (WAI-ARIA tabs pattern: arrows, Home, End)
(function initTabs() {
  const tabs = Array.from(document.querySelectorAll('.tab-btn'));
  tabs.forEach((btn, i) => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
    btn.addEventListener('keydown', (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      let next = null;
      if (step) next = tabs[(i + step + tabs.length) % tabs.length];
      else if (e.key === 'Home') next = tabs[0];
      else if (e.key === 'End') next = tabs[tabs.length - 1];
      if (next) {
        e.preventDefault();
        activateTab(next.dataset.tab, { focus: true });
      }
    });
  });
  const fromHash = window.location.hash.replace('#', '');
  activateTab(TAB_IDS.includes(fromHash) ? fromHash : (document.body.dataset.initialTab || 'encode'), { updateHash: false });
  window.addEventListener('hashchange', () => {
    const id = window.location.hash.replace('#', '');
    if (TAB_IDS.includes(id)) activateTab(id, { updateHash: false });
  });
})();

function setupDropZone(dropEl, inputEl, infoEl) {
  if (!dropEl || !inputEl) return;

  dropEl.addEventListener('click', (e) => {
    if (e.target !== inputEl) inputEl.click();
  });

  ['dragenter', 'dragover'].forEach((ev) => {
    dropEl.addEventListener(ev, (e) => {
      e.preventDefault();
      dropEl.classList.add('drag-over');
    });
  });
  ['dragleave', 'drop'].forEach((ev) => {
    dropEl.addEventListener(ev, () => {
      dropEl.classList.remove('drag-over');
    });
  });

  dropEl.addEventListener('drop', (e) => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      inputEl.files = dt.files;
      updateFileInfo(inputEl, infoEl, dropEl);
      if (inputEl.id === 'enc-carrier' || inputEl.id === 'enc-payload') {
        refreshCapacityMatrix();
      }
      if (inputEl.id === 'cap-file' || inputEl.id === 'cap-payload') {
        refreshCapacityTabLiveMatrix();
      }
    }
  });

  inputEl.addEventListener('change', () => {
    updateFileInfo(inputEl, infoEl, dropEl);
    if (inputEl.id === 'enc-carrier' || inputEl.id === 'enc-payload') {
      refreshCapacityMatrix();
    }
    if (inputEl.id === 'cap-file' || inputEl.id === 'cap-payload') {
      refreshCapacityTabLiveMatrix();
    }
  });
}

function updateFileInfo(input, infoEl, dropEl) {
  if (!(input.files && input.files[0])) return;
  const file = input.files[0];
  const sizeStr = formatBytes(file.size);
  if (infoEl) {
    infoEl.classList.remove('is-error');
    infoEl.textContent = '';
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    showFileError(input, `${file.name} is ${sizeStr}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`);
    input.value = '';
    if (dropEl) dropEl.classList.remove('has-file');
    return;
  }

  if (dropEl) {
    dropEl.classList.add('has-file');
    const textEl = dropEl.querySelector('.drop-text');
    if (textEl) {
      textEl.innerHTML = `<strong>${esc(file.name)}</strong><br><small>${sizeStr} · click to replace</small>`;
    }

    const oldPreview = dropEl.querySelector('.video-preview');
    if (oldPreview) oldPreview.remove();
    if (file.type.startsWith('video/')) {
      const video = document.createElement('video');
      video.className = 'video-preview';
      video.muted = true;
      video.playsInline = true;
      video.preload = 'metadata';
      video.src = URL.createObjectURL(file);
      dropEl.appendChild(video);
    }
  }
}

[
  ['enc-carrier-drop', 'enc-carrier', 'enc-carrier-info'],
  ['enc-payload-drop', 'enc-payload', 'enc-payload-info'],
  ['enc-decoy-drop', 'enc-decoy', 'enc-decoy-info'],
  ['dec-file-drop', 'dec-file', 'dec-file-info'],
  ['det-file-drop', 'det-file', 'det-file-info'],
  ['ctf-file-drop', 'ctf-file', 'ctf-file-info'],
  ['cap-file-drop', 'cap-file', 'cap-file-info'],
  ['cap-payload-drop', 'cap-payload', 'cap-payload-info'],
  ['survive-carrier-drop', 'survive-carrier', 'survive-carrier-info'],
  ['survive-payload-drop', 'survive-payload', 'survive-payload-info'],
  ['diff-cover-drop', 'diff-cover', 'diff-cover-info'],
  ['diff-stego-drop', 'diff-stego', 'diff-stego-info'],
].forEach(([drop, input, info]) => setupDropZone($(drop), $(input), $(info)));

function setupPasswordToggle(btnId, inputId) {
  const btn = $(btnId);
  const input = $(inputId);
  if (!btn || !input) return;
  btn.addEventListener('click', () => {
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.innerHTML = ico(show ? 'eye-off' : 'eye');
    btn.setAttribute('aria-pressed', String(show));
    btn.setAttribute('aria-label', show ? 'Hide passphrase' : 'Show passphrase');
  });
}

setupPasswordToggle('enc-key-toggle', 'enc-key');
setupPasswordToggle('dec-key-toggle', 'dec-key');

// Method pill selector
(function initMethodPills() {
  const hidden = $('enc-method');
  const desc = $('method-desc');
  const pills = document.querySelectorAll('#enc-method-pills .method-pill');
  const renderDescription = (pill) => {
    const rating = pill.dataset.rating || '';
    const text = pill.dataset.desc || '';
    desc.textContent = `${text}${rating ? ` Relative stealth: ${rating}.` : ''}`;
  };

  pills.forEach((pill) => {
    pill.addEventListener('click', () => {
      pills.forEach((p) => p.classList.remove('selected'));
      pill.classList.add('selected');
      hidden.value = pill.dataset.method || '';
      renderDescription(pill);
    });
  });

  const initial = document.querySelector('#enc-method-pills .method-pill.selected');
  if (initial) {
    hidden.value = initial.dataset.method || '';
    renderDescription(initial);
  }
})();

// Depth sliders
(function initDepth() {
  const depthSlider = $('enc-depth');
  const depthDisplay = $('depth-display');
  const depthInfoText = $('depth-info-text');
  const capDepthSlider = $('cap-depth');
  const capDepthDisplay = $('cap-depth-display');

  const depthDescriptions = {
    1: 'Depth 1: stealth-first.',
    2: 'Depth 2: balances capacity and stealth.',
    3: 'Depth 3: more capacity, more detectable changes.',
    4: 'Depth 4: maximum capacity, with a risk of visible distortion.',
  };

  if (depthSlider) {
    depthSlider.addEventListener('input', () => {
      const v = Number(depthSlider.value);
      if (depthDisplay) depthDisplay.textContent = String(v);
      if (depthInfoText) depthInfoText.textContent = depthDescriptions[v] || '';
      refreshCapacityMatrix();
    });
  }

  if (capDepthSlider && capDepthDisplay) {
    capDepthSlider.addEventListener('input', () => {
      capDepthDisplay.textContent = capDepthSlider.value;
      refreshCapacityTabLiveMatrix();
    });
  }
})();

async function refreshCapacityTabLiveMatrix() {
  const carrier = $('cap-file');
  const payload = $('cap-payload');
  const depth = $('cap-depth');
  const box = $('cap-live-matrix');
  if (!carrier || !box) return;
  if (!(carrier.files && carrier.files[0])) {
    box.className = 'capacity-matrix empty';
    box.textContent = 'Choose a carrier to compare methods.';
    return;
  }

  const fd = new FormData();
  fd.append('file', carrier.files[0]);
  if (payload && payload.files && payload.files[0]) fd.append('payload', payload.files[0]);
  fd.append('depth', depth ? depth.value : '1');

  try {
    const resp = await apiFetch('/api/capacity-matrix', { method: 'POST', body: fd });
    const data = await resp.json();
    if (data.error) {
      box.className = 'capacity-matrix';
      box.textContent = data.error;
      return;
    }

    const rows = (data.rows || []).slice(0, 14);
    box.className = 'capacity-matrix';
    box.innerHTML = rows.map((r) => {
      const util = Number(r.utilization_pct || 0);
      const pct = Math.min(100, util);
      let bar = '';
      if (pct >= 90) bar = 'danger';
      else if (pct >= 65) bar = 'warn';
      return `<div class="capacity-row">
        <div>${esc(r.method)}</div>
        <div>${Number(r.capacity_kb || 0).toFixed(2)} KB${util > 0 ? ` (${util.toFixed(1)}%)` : ''}</div>
        <div class="capacity-bar-wrap"><div class="capacity-bar ${bar}" style="width:${pct}%"></div></div>
      </div>`;
    }).join('');
  } catch (e) {
    box.className = 'capacity-matrix';
    box.textContent = `Could not compute capacities: ${e.message}`;
  }
}

async function initPlatformProfiles() {
  try {
    const res = await apiFetch('/api/platform-profiles');
    const data = await res.json();
    platformProfiles = data.profiles || {};
  } catch (_) {
    platformProfiles = {};
  }

  const wrap = $('platform-pills');
  if (!wrap) return;
  wrap.innerHTML = '';
  Object.keys(platformProfiles).forEach((name) => {
    const p = platformProfiles[name];
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'platform-pill';
    b.textContent = name;
    b.dataset.platform = name;
    b.addEventListener('click', () => selectPlatform(name));
    wrap.appendChild(b);
  });
}

function selectPlatform(name) {
  const p = platformProfiles[name];
  if (!p) return;

  document.querySelectorAll('.platform-pill').forEach((el) => {
    el.classList.toggle('active', el.dataset.platform === name);
  });

  $('enc-target').value = name;
  $('enc-wet-paper').value = p.requires_wet_paper ? '1' : '0';

  const note = $('platform-note');
  note.textContent = `${name}: ${p.notes} Preferred method ${p.preferred_method}${p.requires_wet_paper ? ' with wet-paper protection.' : '.'}`;

  // Auto-select method pill
  const method = p.preferred_method || '';
  const pills = document.querySelectorAll('#enc-method-pills .method-pill');
  let chosen = null;
  pills.forEach((pill) => {
    const pick = pill.dataset.method === method;
    pill.classList.toggle('selected', pick);
    if (pick) chosen = pill;
  });
  $('enc-method').value = method;
  if (chosen) {
    $('method-desc').textContent = `${chosen.dataset.desc || ''} Relative stealth: ${chosen.dataset.rating || 'Balanced'}.`;
  }
}

const testSurvivalCheck = $('enc-test-survival-check');
if (testSurvivalCheck) {
  testSurvivalCheck.addEventListener('change', () => {
    $('enc-test-survival').value = testSurvivalCheck.checked ? '1' : '0';
  });
}

async function refreshCapacityMatrix() {
  const carrier = $('enc-carrier');
  const payload = $('enc-payload');
  const depth = $('enc-depth');
  const box = $('enc-capacity-matrix');
  if (!carrier || !box) return;
  if (!(carrier.files && carrier.files[0])) {
    box.className = 'capacity-matrix empty';
    box.textContent = 'Choose a carrier to see how much each method can hold.';
    return;
  }

  const formData = new FormData();
  formData.append('file', carrier.files[0]);
  if (payload.files && payload.files[0]) {
    formData.append('payload', payload.files[0]);
  }
  formData.append('depth', depth ? depth.value : '1');

  try {
    const resp = await apiFetch('/api/capacity-matrix', { method: 'POST', body: formData });
    const data = await resp.json();
    if (data.error) {
      box.className = 'capacity-matrix';
      box.textContent = data.error;
      return;
    }

    const rows = (data.rows || []).slice(0, 12);
    if (!rows.length) {
      box.className = 'capacity-matrix empty';
      box.textContent = 'No compatible methods found for this carrier.';
      return;
    }

    box.className = 'capacity-matrix';
    box.innerHTML = rows
      .map((r) => {
        const util = Number(r.utilization_pct || 0);
        const pct = Math.min(100, util);
        let barClass = '';
        if (pct >= 90) barClass = 'danger';
        else if (pct >= 65) barClass = 'warn';
        return `<div class="capacity-row">
          <div>${esc(r.method)}</div>
          <div>${Number(r.capacity_kb || 0).toFixed(2)} KB</div>
          <div class="capacity-bar-wrap">
            <div class="capacity-bar ${barClass}" style="width:${pct}%"></div>
          </div>
        </div>`;
      })
      .join('');
  } catch (e) {
    box.className = 'capacity-matrix';
    box.textContent = `Could not compute capacities: ${e.message}`;
  }
}

['cap-file', 'cap-payload', 'cap-depth'].forEach((id) => {
  const el = $(id);
  if (el) el.addEventListener('change', refreshCapacityTabLiveMatrix);
});

// renderSuccess takes *trusted markup*: escape any dynamic part at the call site.
function renderSuccess(msg, title = 'Done') {
  return `<div class="result-card success">
    <div class="result-title success-title">${ico('check')} ${esc(title)}</div>
    <p>${msg}</p>
  </div>`;
}

function renderError(msg) {
  return `<div class="result-card error">
    <div class="result-title error-title">${ico('alert')} Something went wrong</div>
    <p>${esc(msg)}</p>
  </div>`;
}

function renderGrid(rows) {
  const cells = rows
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `<div class="result-key">${esc(key)}</div><div class="result-val">${value}</div>`)
    .join('');
  return `<div class="result-grid">${cells}</div>`;
}

function renderNote(kind, title, body) {
  const icon = { ok: 'check', warn: 'alert', info: 'info' }[kind] || 'info';
  return `<div class="note ${kind}">${ico(icon)}<div>${title ? `<strong>${esc(title)}</strong>` : ''}${body}</div></div>`;
}

function renderConfidenceBar(confidence) {
  const pct = Math.round(Number(confidence || 0) * 100);
  const colorClass = pct > 70 ? 'red' : pct > 30 ? 'yellow' : 'green';
  return `<div class="confidence-bar-wrap">
    <div class="confidence-bar-bg"><div class="confidence-bar-fill ${colorClass}" style="width:${pct}%"></div></div>
    <div class="confidence-label">${pct}% confidence</div>
  </div>`;
}

const DETECTOR_NAMES = {
  chi2: 'Chi-square', rs: 'RS analysis', exif: 'Metadata', blind: 'Blind extractor', ml: 'ML',
  fingerprint: 'Camera fingerprint', binary: 'Binary', 'video-anomaly': 'Video', 'audio-anomaly': 'Audio',
  'pdf-anomaly': 'PDF', 'document-anomaly': 'Document',
};

function renderDetectorResult(r, idx = 0) {
  const details = r.details || {};
  const skipped = details.skipped === true;
  const detected = !!r.detected;
  // A detector that says it cannot tell must not wear the green "clean" chip.
  const inconclusive = !skipped && !detected && (details.reliable === false || details.inconclusive === true);
  let chip;
  let tone = '';
  if (skipped) chip = '<span class="status-chip skipped">SKIPPED</span>';
  else if (detected) { chip = '<span class="status-chip detected">DETECTED</span>'; tone = 'detected'; }
  else if (inconclusive) chip = '<span class="status-chip inconclusive">INCONCLUSIVE</span>';
  else { chip = '<span class="status-chip clean">CLEAN</span>'; tone = 'clean'; }

  let extra = '';
  if (details.interpretation) {
    extra += renderGrid([['Analysis', esc(details.interpretation)]]);
  }
  if (r.method === 'fingerprint' && details.heatmap_b64) {
    const src = `data:image/png;base64,${String(details.heatmap_b64).replace(/[^A-Za-z0-9+/=]/g, '')}`;
    extra += `<div style="margin-top:12px"><img class="result-image" src="${src}" alt="Fingerprint heatmap: brighter regions have noise statistics inconsistent with an untouched photograph"></div>`;
  }
  if (r.method === 'ml') {
    extra += renderGrid([['Verdict', esc(details.verdict || 'N/A')], ['Hints', esc((details.hints || []).join('; ') || 'None')]]);
  }

  return `<div class="result-card ${tone}" style="animation:rise .3s both;animation-delay:${Math.min(idx, 8) * 50}ms">
    <div class="result-title accent-title">${esc(DETECTOR_NAMES[r.method] || String(r.method || '').toUpperCase())} ${chip}</div>
    ${skipped || inconclusive ? '' : renderConfidenceBar(r.confidence)}
    ${extra}
  </div>`;
}

async function consumeSSE(response, onMessage) {
  if (!response.body) {
    const text = await response.text();
    text
      .split('\n\n')
      .filter((x) => x.trim().startsWith('data: '))
      .forEach((ev) => {
        const msg = JSON.parse(ev.replace(/^data:\s*/, ''));
        onMessage(msg);
      });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) !== -1) {
      const chunk = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (!chunk.startsWith('data: ')) continue;
      const msg = JSON.parse(chunk.replace(/^data:\s*/, ''));
      onMessage(msg);
    }
  }
}

function b64toBlob(b64Data, contentType = 'application/octet-stream') {
  const byteChars = atob(b64Data);
  const byteArrays = [];
  for (let offset = 0; offset < byteChars.length; offset += 512) {
    const slice = byteChars.slice(offset, offset + 512);
    const byteNums = new Array(slice.length);
    for (let i = 0; i < slice.length; i += 1) byteNums[i] = slice.charCodeAt(i);
    byteArrays.push(new Uint8Array(byteNums));
  }
  return new Blob(byteArrays, { type: contentType });
}

// Encode via SSE
(function initEncode() {
  const form = $('encode-form');
  const result = $('encode-result');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Validating request…');

    const formData = new FormData(form);
    try {
      const response = await apiFetch('/api/encode-stream', { method: 'POST', body: formData });
      let finalPayload = null;
      await consumeSSE(response, (msg) => {
        if (msg.type === 'info' || msg.type === 'progress') {
          showLoading(msg.text || 'Embedding…', typeof msg.pct === 'number' ? msg.pct : null);
        }
        if (msg.type === 'success') finalPayload = msg;
        if (msg.type === 'error') throw new Error(msg.text);
      });

      const href = finalPayload && artifactHref(finalPayload);
      if (!href) throw new Error('The encode did not produce a file.');

      const dlName = finalPayload.download_name || 'stego.bin';
      const r = finalPayload.result || {};
      const warnings = (r.warnings || []).map((w) => renderNote('warn', '', esc(w))).join('');
      const survival = r.survival_test
        ? `${r.survival_test.survived ? 'Survived' : 'Did not survive'} ${esc(r.survival_test.target || '')}${r.survival_test.error ? ` (${esc(r.survival_test.error)})` : ''}`
        : '';
      result.innerHTML = `<div class="result-card success">
          <div class="result-title success-title">${ico('check')} Payload embedded</div>
          ${renderGrid([
            ['Method', esc(r.method)],
            ['Size', `${formatBytes(Number(r.payload_size || 0))} → ${formatBytes(Number(r.encrypted_size || 0))} after encryption`],
            ['Capacity', formatBytes(Number(r.capacity || 0))],
            ['Bit depth', r.depth ? esc(r.depth) : ''],
            ['Survival test', survival],
            ['Decoy', r.decoy_mode ? 'second payload embedded' : ''],
          ])}
        </div>
        ${warnings}
        <div class="form-actions">
          <a class="btn btn-primary" href="${esc(href)}" download="${esc(dlName)}">${ico('download')} Download ${esc(dlName)}</a>
        </div>`;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
})();

// Decode
(function initDecode() {
  const form = $('decode-form');
  const result = $('decode-result');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Extracting…');

    try {
      const formData = new FormData(form);
      const response = await apiFetch('/decode', { method: 'POST', body: formData });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Decode failed');
      }

      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const match = disposition.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : 'decoded_payload.bin';
      const contentType = response.headers.get('content-type') || 'application/octet-stream';
      const sfrgHint = response.headers.get('x-stegoforge-hint') || '';
      const url = URL.createObjectURL(blob);

      let html = `<div class="result-card success">
        <div class="result-title success-title">${ico('check')} Payload extracted</div>
        ${renderGrid([['File', esc(filename)], ['Size', formatBytes(blob.size)], ['Type', esc(contentType)]])}
      </div>`;

      // Inline preview based on MIME type
      if (contentType.startsWith('image/')) {
        html += `<div class="result-card"><div class="result-title accent-title">Preview</div><img class="result-image" src="${url}" alt="Decoded image"></div>`;
      } else if (contentType.startsWith('audio/')) {
        html += `<div class="result-card"><div class="result-title accent-title">Preview</div><audio class="result-audio" controls src="${url}"></audio></div>`;
      } else if (blob.size <= 32768) {
        const text = await blob.text();
        const isText = contentType === 'text/plain' || /^(?:[\x09\x0A\x0D\x20-\x7E]|[ -￿])*$/u.test(text);
        if (isText) {
          html += `<div class="result-card"><div class="result-title accent-title">Preview</div><textarea class="form-input result-text" rows="10" readonly>${esc(text)}</textarea></div>`;
        }
      }
      if (sfrgHint) {
        html += renderNote('warn', 'This payload is another encrypted blob', esc(sfrgHint));
      }
      html += `<div class="form-actions"><a class="btn btn-primary" href="${url}" download="${esc(filename)}">${ico('download')} Download ${esc(filename)}</a></div>`;
      result.innerHTML = html;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
})();

// Detect via SSE
(function initDetect() {
  const form = $('detect-form');
  const result = $('detect-result');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Running detectors…');

    try {
      const formData = new FormData(form);
      const response = await apiFetch('/api/detect-stream', { method: 'POST', body: formData });
      let finalReport = null;

      await consumeSSE(response, (msg) => {
        if (msg.type === 'log' || msg.type === 'info') showLoading(msg.text);
        if (msg.type === 'success') finalReport = msg.report;
        if (msg.type === 'error') throw new Error(msg.text);
      });

      if (!finalReport) throw new Error('The detectors did not produce a report.');

      let html = `<p class="panel-subtitle" style="margin-bottom:16px">Results for <strong>${esc(finalReport.file)}</strong></p>`;
      (finalReport.results || []).forEach((r, idx) => {
        html += renderDetectorResult(r, idx);
      });
      result.innerHTML = html;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
})();

// CTF
(function initCTF() {
  const form = $('ctf-form');
  const result = $('ctf-result');
  const copyBtn = $('ctf-copy-report');
  const exportBtn = $('ctf-export-json');
  if (!form) return;

  const noteFor = (n) => {
    const text = String(n);
    if (text.includes('SFRG magic') || text.includes('AES-256-GCM')) {
      return renderNote('warn', 'Encrypted StegoForge payload extracted',
        `<p>The data was extracted from the carrier, but it is an encrypted <code>.sfrg</code> blob.</p>
         <ol><li>Download the extracted file below.</li><li>Open the <strong>Decode</strong> tab and choose it as the stego file.</li><li>Enter the passphrase.</li></ol>`);
    }
    if (text.includes('✔')) return renderNote('ok', 'Payload extracted without a key', `<p>${esc(text.replace('✔ ', ''))}</p>`);
    if (text.includes('ℹ')) return renderNote('info', '', `<p>${esc(text.replace('ℹ ', ''))}</p>`);
    return renderNote('info', '', `<p>${esc(text.replace(/^⚠\s*/, ''))}</p>`);
  };

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Running every detector…');
    latestCTFReport = null;
    latestCTFText = '';

    try {
      const formData = new FormData(form);
      const response = await apiFetch('/ctf', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      latestCTFReport = data.report_json || data;

      const detected = data.verdict === 'STEGO DETECTED';
      const pct = Math.round(Number(data.confidence || 0) * 100);
      let html = `<div class="ctf-verdict">
        <div class="ctf-verdict-label ${detected ? 'detected' : 'clean'}">${esc(data.verdict)}</div>
        <div class="ctf-verdict-pct">Strongest detector signal ${pct}%</div>
      </div>`;

      (data.results || []).forEach((r, idx) => {
        html += renderDetectorResult(r, idx);
      });

      if (data.notes && data.notes.length) {
        html += `<div style="margin-top:20px">${data.notes.map(noteFor).join('')}</div>`;
      }

      if (data.has_extracted_payload && data.extracted_payload_b64) {
        const extractedMime = data.extracted_payload_mime || 'application/octet-stream';
        const extractedExt = data.extracted_payload_ext || '.bin';
        const blob = b64toBlob(data.extracted_payload_b64, extractedMime);
        const url = URL.createObjectURL(blob);
        const dlName = `extracted_payload${extractedExt}`;
        let preview = '';
        if (extractedMime.startsWith('image/')) {
          preview = `<img class="result-image" src="${url}" alt="Extracted image payload">`;
        } else if (extractedMime.startsWith('audio/')) {
          preview = `<audio class="result-audio" controls src="${url}"></audio>`;
        } else if (blob.size <= 32768) {
          const text = await blob.text();
          if (extractedMime === 'text/plain' || /^(?:[\x09\x0A\x0D\x20-\x7E]|[ -￿])*$/u.test(text)) {
            preview = `<textarea class="form-input result-text" rows="8" readonly>${esc(text)}</textarea>`;
          }
        }
        html += `<div class="result-card success">
          <div class="result-title success-title">${ico('check')} Extracted payload · <code>${esc(dlName)}</code></div>
          ${preview}
          <div class="form-actions"><a class="btn btn-primary" href="${url}" download="${esc(dlName)}">${ico('download')} Download ${esc(dlName)}</a></div>
        </div>`;
      }

      latestCTFText = `Verdict: ${data.verdict}\nStrongest detector signal: ${pct}%\n`;
      (data.results || []).forEach((r) => {
        latestCTFText += `${r.method}: ${r.detected ? 'DETECTED' : 'CLEAN'} (${Math.round(Number(r.confidence || 0) * 100)}%)\n`;
      });

      result.innerHTML = html;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });

  if (copyBtn) {
    copyBtn.addEventListener('click', async () => {
      if (!latestCTFText) return;
      try {
        await navigator.clipboard.writeText(latestCTFText);
        copyBtn.textContent = 'Copied';
      } catch (_) {
        copyBtn.textContent = 'Copy failed';
      }
      setTimeout(() => { copyBtn.textContent = 'Copy report'; }, 1400);
    });
  }

  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      if (!latestCTFReport) return;
      const blob = new Blob([JSON.stringify(latestCTFReport, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ctf_report.json';
      a.click();
      URL.revokeObjectURL(url);
    });
  }
})();

// Capacity
(function initCapacity() {
  const form = $('capacity-form');
  const result = $('capacity-result');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Calculating capacity…');

    try {
      const formData = new FormData(form);
      const response = await apiFetch('/capacity', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      const rows = [
        ['File', esc(data.file)],
        ['Method', `<span class="result-val cyan">${esc(data.method)}</span>`],
        ['Bit depth', `${esc(data.depth)}`],
        ['Capacity', `<span class="result-val green">${Number(data.capacity_bytes || 0).toLocaleString()} bytes</span> (${Number(data.capacity_kb || 0).toFixed(2)} KB)`],
      ];
      if (data.stealth_score !== undefined) {
        rows.push(['Stealth score', `${Number(data.stealth_score)}/100`]);
      }
      if (data.jnd_safe_dct_capacity) {
        const j = data.jnd_safe_dct_capacity;
        rows.push(['Perceptually safe (DCT)', `${Number(j.bytes).toLocaleString()} bytes (${Number(j.kb)} KB)`]);
      }
      if (data.video_context) {
        const v = data.video_context;
        rows.push(['Video', `${Number(v.duration_seconds)}s, ${Number(v.frames)} frames, ${Number(v.usable_frames ?? v.keyframes)} usable`]);
        if (v.capacity_note) rows.push(['Note', esc(v.capacity_note)]);
      }
      result.innerHTML = `<div class="result-card success">
        <div class="result-title success-title">${ico('ruler')} Capacity</div>
        ${renderGrid(rows)}
      </div>`;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
})();

// Survive
(function initSurvive() {
  const form = $('survive-form');
  const result = $('survive-result');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Simulating the platform pipeline…');

    try {
      const formData = new FormData(form);
      const response = await apiFetch('/api/survive', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      const st = data.survival_test || {};
      const ok = !!st.survived;
      result.innerHTML = `<div class="result-card ${ok ? 'success' : 'error'}">
        <div class="result-title ${ok ? 'success-title' : 'error-title'}">${ico(ok ? 'check' : 'x')} ${ok ? 'Payload survived' : 'Payload did not survive'} · ${esc(st.target || 'target')}</div>
        ${renderGrid([
          ['Method', esc(data.method)],
          ['Wet paper', data.wet_paper ? 'enabled' : 'disabled'],
          ['Corrected bits', Number(st.corrected_bits || 0).toLocaleString()],
          ['Platform notes', esc((data.target_profile && data.target_profile.notes) || '')],
          ['Detail', esc(st.error || '')],
        ])}
      </div>`;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
})();

// Diff
(function initDiff() {
  const form = $('diff-form');
  const result = $('diff-result');
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Comparing the files…');

    try {
      const formData = new FormData(form);
      const response = await apiFetch('/diff', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      let rows;
      if (data.type === 'image') {
        rows = [
          ['Type', 'image'],
          ['Pixels changed', `${Number(data.changed_pixels || 0).toLocaleString()} (${esc(data.changed_percent)}%)`],
          ['Max delta', esc(data.max_delta)],
          ['Mean delta', Number(data.mean_delta || 0).toFixed(4)],
        ];
      } else {
        const changedBytes = data.differing_bytes ?? data.changed_bytes ?? 0;
        const changedPercent = data.differing_percent ?? data.changed_percent ?? 0;
        rows = [['Type', esc(data.type)], ['Bytes changed', `${Number(changedBytes).toLocaleString()} (${esc(changedPercent)}%)`]];
      }

      result.innerHTML = `<div class="result-card success">
        <div class="result-title success-title">${ico('diff')} Comparison complete</div>
        ${renderGrid(rows)}
        ${data.notes ? `<p style="margin-top:12px">${esc(data.notes)}</p>` : ''}
      </div>
      ${data.heatmap_b64 ? `<div class="result-card"><div class="result-title accent-title">Changed pixels</div><img class="result-image" src="${esc(data.heatmap_b64)}" alt="Heatmap of the pixels that differ between the two images"></div>` : ''}`;
      result.style.display = 'block';
    } catch (err) {
      result.innerHTML = renderError(err.message);
      result.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
})();

initPlatformProfiles();

// ── Passphrase strength (advisory only; the server enforces the real policy) ──
function calcKeyStrength(pw) {
  if (!pw) return 0;
  const len = pw.length;
  let variety = 0;
  if (/[a-z]/.test(pw)) variety += 1;
  if (/[A-Z]/.test(pw)) variety += 1;
  if (/[0-9]/.test(pw)) variety += 1;
  if (/[^a-zA-Z0-9]/.test(pw)) variety += 1;
  const freq = {};
  for (const ch of pw) freq[ch] = (freq[ch] || 0) + 1;
  let entropy = 0;
  for (const n of Object.values(freq)) {
    const p = n / len;
    entropy -= p * Math.log2(p);
  }
  const lenScore = Math.min(len / 20, 1) * 40;
  const varScore = (variety / 4) * 30;
  const entScore = Math.min(entropy / 4, 1) * 30;
  return Math.round(lenScore + varScore + entScore);
}

function setupKeyStrengthMeter(inputId, meterId) {
  const input = $(inputId);
  const meter = $(meterId);
  if (!input || !meter) return;
  function update() {
    if (!input.value) { meter.innerHTML = ''; return; }
    const score = calcKeyStrength(input.value);
    const [label, tone] = score >= 75 ? ['Strong', 'var(--ok)']
      : score >= 50 ? ['Fair', 'var(--accent)']
        : score >= 25 ? ['Weak', 'var(--bad)'] : ['Very weak', 'var(--bad)'];
    meter.innerHTML = `<div class="strength" style="--w:${score}%;--tone:${tone}">
      <span class="strength-track"><span class="strength-fill"></span></span>
      <span class="strength-label">${label}</span>
    </div>`;
  }
  input.addEventListener('input', update);
  update();
}

setupKeyStrengthMeter('enc-key', 'enc-key-strength');

// ── Carrier preview (encode) ──────────────────────────────────────────────────
(function initCarrierPreview() {
  const carrierInput = $('enc-carrier');
  const previewBox = $('enc-carrier-preview');
  if (!carrierInput || !previewBox) return;
  carrierInput.addEventListener('change', () => {
    const file = carrierInput.files && carrierInput.files[0];
    if (!file || !file.type.startsWith('image/')) { previewBox.style.display = 'none'; return; }
    previewBox.innerHTML = `<img class="carrier-preview" src="${URL.createObjectURL(file)}" alt="Preview of the chosen carrier">`;
    previewBox.style.display = 'block';
  });
})();
