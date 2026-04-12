/* StegoForge Web UI - Interactive JavaScript */
'use strict';

let latestCTFReport = null;
let latestCTFText = '';
let platformProfiles = {};

function $(id) {
  return document.getElementById(id);
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function showLoading(msg = 'Processing...') {
  $('loading-text').textContent = msg;
  $('loading-overlay').style.display = 'flex';
}

function hideLoading() {
  $('loading-overlay').style.display = 'none';
}

function activateTab(tabId) {
  document.querySelectorAll('.tab-btn').forEach((b) => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('active'));
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  const panel = $(`tab-${tabId}`);
  if (btn) btn.classList.add('active');
  if (panel) panel.classList.add('active');
}

// Tab navigation
(function initTabs() {
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });
  const initial = document.body.dataset.initialTab || 'encode';
  activateTab(initial);
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
  if (infoEl) infoEl.textContent = `✓ ${file.name} (${sizeStr})`;

  if (dropEl) {
    dropEl.classList.add('has-file');
    const textEl = dropEl.querySelector('.drop-text');
    if (textEl) {
      textEl.innerHTML = `<strong style="color:var(--accent-green)">${file.name}</strong><br><small>${sizeStr}</small>`;
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
      video.style.maxWidth = '220px';
      video.style.marginTop = '8px';
      video.style.borderRadius = '8px';
      video.style.border = '1px solid var(--border-subtle)';
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
].forEach(([drop, input, info]) => setupDropZone($(drop), $(input), $(info)));

function setupPasswordToggle(btnId, inputId) {
  const btn = $(btnId);
  const input = $(inputId);
  if (!btn || !input) return;
  btn.addEventListener('click', () => {
    if (input.type === 'password') {
      input.type = 'text';
      btn.textContent = '🙈';
    } else {
      input.type = 'password';
      btn.textContent = '👁';
    }
  });
}

setupPasswordToggle('enc-key-toggle', 'enc-key');
setupPasswordToggle('dec-key-toggle', 'dec-key');

function toggleCollapse(btnId, contentId) {
  const btn = $(btnId);
  const content = $(contentId);
  if (!btn || !content) return;
  const arrow = btn.querySelector('.collapse-arrow');
  btn.addEventListener('click', () => {
    const isOpen = content.style.display !== 'none';
    content.style.display = isOpen ? 'none' : 'flex';
    if (arrow) arrow.textContent = isOpen ? '▶' : '▼';
  });
}

toggleCollapse('decoy-toggle', 'decoy-content');
toggleCollapse('platform-toggle', 'platform-content');

// Method pill selector
(function initMethodPills() {
  const hidden = $('enc-method');
  const desc = $('method-desc');
  const pills = document.querySelectorAll('#enc-method-pills .method-pill');
  const renderDescription = (pill) => {
    const rating = pill.dataset.rating || '';
    const text = pill.dataset.desc || '';
    desc.textContent = `${text}${rating ? ` Forensic resistance: ${rating}.` : ''}`;
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
    1: 'At depth 1: stealth-first profile.',
    2: 'At depth 2: balanced capacity and stealth.',
    3: 'At depth 3: higher capacity with more detectable artifacts.',
    4: 'At depth 4: maximum capacity and visible distortion risk.',
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
    box.textContent = 'Drop a carrier to compute capacities across methods.';
    return;
  }

  const fd = new FormData();
  fd.append('file', carrier.files[0]);
  if (payload && payload.files && payload.files[0]) fd.append('payload', payload.files[0]);
  fd.append('depth', depth ? depth.value : '1');

  try {
    const resp = await fetch('/api/capacity-matrix', { method: 'POST', body: fd });
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
        <div>${r.method}</div>
        <div>${Number(r.capacity_kb || 0).toFixed(2)} KB${util > 0 ? ` (${util.toFixed(1)}%)` : ''}</div>
        <div class="capacity-bar-wrap"><div class="capacity-bar ${bar}" style="width:${pct}%"></div></div>
      </div>`;
    }).join('');
  } catch (e) {
    box.className = 'capacity-matrix';
    box.textContent = `Live matrix error: ${e.message}`;
  }
}

async function initPlatformProfiles() {
  try {
    const res = await fetch('/api/platform-profiles');
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
    b.textContent = name.toUpperCase();
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
    $('method-desc').textContent = `${chosen.dataset.desc || ''} Forensic resistance: ${chosen.dataset.rating || 'Balanced'}.`;
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
    box.textContent = 'Drop carrier and payload to compute per-method usage.';
    return;
  }

  const formData = new FormData();
  formData.append('file', carrier.files[0]);
  if (payload.files && payload.files[0]) {
    formData.append('payload', payload.files[0]);
  }
  formData.append('depth', depth ? depth.value : '1');

  try {
    const resp = await fetch('/api/capacity-matrix', { method: 'POST', body: formData });
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
          <div>${r.method}</div>
          <div>${Number(r.capacity_kb || 0).toFixed(2)} KB</div>
          <div class="capacity-bar-wrap">
            <div class="capacity-bar ${barClass}" style="width:${pct}%"></div>
          </div>
        </div>`;
      })
      .join('');
  } catch (e) {
    box.className = 'capacity-matrix';
    box.textContent = `Capacity matrix error: ${e.message}`;
  }
}

['cap-file', 'cap-payload', 'cap-depth'].forEach((id) => {
  const el = $(id);
  if (el) el.addEventListener('change', refreshCapacityTabLiveMatrix);
});

function renderSuccess(msg) {
  return `<div class="result-card success">
    <div class="result-title success-title">✓ Success</div>
    <p style="font-size:.9rem;color:var(--text-secondary)">${msg}</p>
  </div>`;
}

function renderError(msg) {
  return `<div class="result-card error">
    <div class="result-title error-title">✗ Error</div>
    <p style="font-size:.9rem;color:var(--accent-red)">${msg}</p>
  </div>`;
}

function renderConfidenceBar(confidence) {
  const pct = Math.round(Number(confidence || 0) * 100);
  const colorClass = pct > 70 ? 'red' : pct > 30 ? 'yellow' : 'green';
  return `<div class="confidence-bar-wrap">
    <div class="confidence-bar-bg">
      <div class="confidence-bar-fill ${colorClass}" style="width:${pct}%"></div>
    </div>
    <div class="confidence-label">${pct}% confidence</div>
  </div>`;
}

function renderDetectorResult(r, idx = 0) {
  const detected = !!r.detected;
  const details = r.details || {};
  const isSkipped = details.skipped === true;

  const statusIcon = isSkipped ? '⏭' : (detected ? '🔴' : '🟢');
  const statusLabel = isSkipped
    ? '<span style="color:var(--text-muted)">SKIPPED</span>'
    : (detected ? '<span style="color:var(--accent-red)">DETECTED</span>' : '<span style="color:var(--accent-green)">CLEAN</span>');

  let extra = '';
  if (details.interpretation) {
    extra += `<div class="result-grid"><div class="result-key">Analysis</div><div class="result-val">${details.interpretation}</div></div>`;
  }

  if (r.method === 'fingerprint' && (details.heatmap_b64 || details.heatmap)) {
    const src = details.heatmap_b64
      ? `data:image/png;base64,${details.heatmap_b64}`
      : `/artifact?path=${encodeURIComponent(details.heatmap)}`;
    extra += `<div style="margin-top:10px"><img src="${src}" alt="Fingerprint heatmap" style="max-width:100%;border-radius:8px;border:1px solid var(--border-subtle)"><div style="font-size:.78rem;color:var(--text-muted);margin-top:6px">Brighter regions indicate anomalous residual noise statistics consistent with pixel modification.</div></div>`;
  }

  if (r.method === 'ml') {
    extra += `<div class="result-grid"><div class="result-key">Verdict</div><div class="result-val">${details.verdict || 'N/A'}</div><div class="result-key">Hints</div><div class="result-val">${(details.hints || []).join('; ') || 'None'}</div></div>`;
  }

  return `<div class="result-card" style="margin-bottom:12px; animation: fadeIn 0.4s cubic-bezier(0.2,0.8,0.2,1) forwards; animation-delay: ${idx * 0.12}s; opacity: 0">
    <div class="result-title accent-title">${statusIcon} ${String(r.method || '').toUpperCase()} ${statusLabel}</div>
    ${renderConfidenceBar(r.confidence)}
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
    showLoading('Streaming encode pipeline...');

    const formData = new FormData(form);
    try {
      const response = await fetch('/api/encode-stream', { method: 'POST', body: formData });
      const logs = [];
      let finalPayload = null;
      await consumeSSE(response, (msg) => {
        if (msg.type === 'info') logs.push(msg.text);
        if (msg.type === 'success') finalPayload = msg;
        if (msg.type === 'error') throw new Error(msg.text);
      });

      if (!finalPayload) {
        throw new Error('Encode stream failed');
      }

      const artifact = finalPayload.artifact;
      const dlName = finalPayload.download_name || 'stego.bin';
      const href = `/artifact?path=${encodeURIComponent(artifact)}`;
      result.innerHTML = `${renderSuccess('Encode completed successfully.')}
        <div class="result-card"><div class="result-title accent-title">Live Log</div><pre class="code-block">${logs.join('\n')}</pre></div>
        <div class="result-card">
          <div class="result-title accent-title">Output Artifact</div>
          <a class="btn btn-primary" href="${href}" download="${dlName}">Download ${dlName}</a>
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
    showLoading('Decoding payload...');

    try {
      const formData = new FormData(form);
      const response = await fetch('/decode', { method: 'POST', body: formData });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.error || 'Decode failed');
      }

      const blob = await response.blob();
      const disposition = response.headers.get('content-disposition') || '';
      const match = disposition.match(/filename="?([^\"]+)"?/);
      const filename = match ? match[1] : 'decoded_payload.bin';

      const url = URL.createObjectURL(blob);
      const textCandidate = await blob.text();
      const isText = blob.size <= 32768 && /^(?:[\x09\x0A\x0D\x20-\x7E]|[\u00A0-\uFFFF])*$/u.test(textCandidate);

      result.innerHTML = `${renderSuccess(`Decoded payload ready: <strong>${filename}</strong>`)}`;
      if (isText) {
        result.innerHTML += `<div class="result-card"><div class="result-title accent-title">Inline Payload Preview</div><textarea class="form-input" rows="10" readonly>${textCandidate.replace(/</g, '&lt;')}</textarea></div>`;
      }
      result.innerHTML += `<div class="result-card"><a class="btn btn-primary" href="${url}" download="${filename}">Download Payload</a></div>`;
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
    showLoading('Streaming detector pipeline...');

    try {
      const formData = new FormData(form);
      const response = await fetch('/api/detect-stream', { method: 'POST', body: formData });
      let finalReport = null;
      const logs = [];

      await consumeSSE(response, (msg) => {
        if (msg.type === 'log') logs.push(msg.text);
        if (msg.type === 'info') logs.push(msg.text);
        if (msg.type === 'success') finalReport = msg.report;
        if (msg.type === 'error') throw new Error(msg.text);
      });

      if (!finalReport) throw new Error('Detection stream did not produce a final report');

      let html = `<div class="result-card"><div class="result-title accent-title">Detector Stream</div><pre class="code-block">${logs.join('\n')}</pre></div>`;
      html += `<h3 style="font-size:1rem;color:var(--accent-cyan);margin-bottom:16px">Results for: <em>${finalReport.file}</em></h3>`;
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

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    result.style.display = 'none';
    showLoading('Running full forensic analysis...');
    latestCTFReport = null;
    latestCTFText = '';

    try {
      const formData = new FormData(form);
      const response = await fetch('/ctf', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      latestCTFReport = data.report_json || data;

      const detected = data.verdict === 'STEGO DETECTED';
      const pct = Math.round(Number(data.confidence || 0) * 100);
      let html = `<div class="ctf-verdict ${detected ? 'detected-bg' : 'clean-bg'}">
        <div class="ctf-verdict-label ${detected ? 'detected' : 'clean'}">${data.verdict}</div>
        <div class="ctf-verdict-pct">Overall confidence: ${pct}%</div>
      </div>`;

      (data.results || []).forEach((r, idx) => {
        html += renderDetectorResult(r, idx);
      });

      if (data.notes && data.notes.length) {
        html += `<div class="result-card"><div class="result-title warn-title">CTF Notes</div><ul class="findings-list">${data.notes.map((n) => `<li class="finding-low">${n}</li>`).join('')}</ul></div>`;
      }

      if (data.has_extracted_payload && data.extracted_payload_b64) {
        const blob = b64toBlob(data.extracted_payload_b64);
        const url = URL.createObjectURL(blob);
        html += `<div class="result-card success"><div class="result-title success-title">Extracted payload ready</div><a class="btn btn-primary" href="${url}" download="extracted_payload.bin">Download Extracted Payload</a></div>`;
      }

      latestCTFText = `Verdict: ${data.verdict}\nConfidence: ${pct}%\n`;
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
      await navigator.clipboard.writeText(latestCTFText);
      copyBtn.textContent = 'Copied';
      setTimeout(() => {
        copyBtn.textContent = 'Copy Report';
      }, 1200);
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
    showLoading('Calculating capacity...');

    try {
      const formData = new FormData(form);
      const response = await fetch('/capacity', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      let extra = '';
      if (data.jnd_safe_dct_capacity) {
        const j = data.jnd_safe_dct_capacity;
        extra += `<div class="result-key">JND-safe DCT</div><div class="result-val">${j.bytes.toLocaleString()} bytes (${j.kb} KB)</div>`;
      }
      if (data.video_context) {
        const v = data.video_context;
        extra += `<div class="result-key">Video context</div><div class="result-val">${v.duration_seconds}s, ${v.frames} frames, ${v.keyframes} keyframes</div>`;
      }

      result.innerHTML = `<div class="result-card success">
        <div class="result-title success-title">Capacity Result</div>
        <div class="result-grid">
          <div class="result-key">File</div><div class="result-val">${data.file}</div>
          <div class="result-key">Method</div><div class="result-val cyan">${data.method}</div>
          <div class="result-key">Depth</div><div class="result-val">${data.depth} bit(s)</div>
          <div class="result-key">Capacity</div><div class="result-val green">${Number(data.capacity_bytes || 0).toLocaleString()} bytes</div>
          <div class="result-key"></div><div class="result-val">${Number(data.capacity_kb || 0).toFixed(2)} KB / ${Number(data.capacity_mb || 0).toFixed(4)} MB</div>
          ${extra}
        </div>
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
    showLoading('Simulating platform pipeline...');

    try {
      const formData = new FormData(form);
      const response = await fetch('/api/survive', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) throw new Error(data.error);

      const st = data.survival_test || {};
      result.innerHTML = `<div class="result-card ${st.survived ? 'success' : 'error'}">
        <div class="result-title ${st.survived ? 'success-title' : 'error-title'}">${st.survived ? 'PASS' : 'FAIL'} - ${st.target || 'target'}</div>
        <div class="result-grid">
          <div class="result-key">Method</div><div class="result-val">${data.method}</div>
          <div class="result-key">Wet paper</div><div class="result-val">${data.wet_paper ? 'Enabled' : 'Disabled'}</div>
          <div class="result-key">Corrected bits</div><div class="result-val">${st.corrected_bits || 0}</div>
          <div class="result-key">Notes</div><div class="result-val">${(data.target_profile && data.target_profile.notes) || ''}</div>
        </div>
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

initPlatformProfiles();
