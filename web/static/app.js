/* StegoForge Web UI — Interactive JavaScript */
'use strict';

// ── Tab navigation ────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tabId = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + tabId).classList.add('active');
  });
});

// ── Drop zone setup ───────────────────────────────────────────────────────────
function setupDropZone(dropEl, inputEl, infoEl) {
  if (!dropEl || !inputEl) return;

  dropEl.addEventListener('click', e => {
    if (e.target !== inputEl) inputEl.click();
  });

  ['dragenter', 'dragover'].forEach(ev => {
    dropEl.addEventListener(ev, e => {
      e.preventDefault();
      dropEl.classList.add('drag-over');
    });
  });
  ['dragleave', 'drop'].forEach(ev => {
    dropEl.addEventListener(ev, e => {
      dropEl.classList.remove('drag-over');
    });
  });
  dropEl.addEventListener('drop', e => {
    e.preventDefault();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const dt = new DataTransfer();
      dt.items.add(files[0]);
      inputEl.files = dt.files;
      updateFileInfo(inputEl, infoEl, dropEl);
    }
  });
  inputEl.addEventListener('change', () => updateFileInfo(inputEl, infoEl, dropEl));
}

function updateFileInfo(input, infoEl, dropEl) {
  if (input.files && input.files[0]) {
    const file = input.files[0];
    const sizeStr = formatBytes(file.size);
    if (infoEl) {
      infoEl.textContent = `✓ ${file.name}  (${sizeStr})`;
    }
    if (dropEl) {
      dropEl.classList.add('has-file');
      const textEl = dropEl.querySelector('.drop-text');
      if (textEl) textEl.innerHTML = `<strong style="color:var(--accent-green)">${file.name}</strong><br><small>${sizeStr}</small>`;
    }
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// Setup all drop zones
setupDropZone(
  document.getElementById('enc-carrier-drop'),
  document.getElementById('enc-carrier'),
  document.getElementById('enc-carrier-info')
);
setupDropZone(
  document.getElementById('enc-payload-drop'),
  document.getElementById('enc-payload'),
  document.getElementById('enc-payload-info')
);
setupDropZone(
  document.getElementById('enc-decoy-drop'),
  document.getElementById('enc-decoy'),
  document.getElementById('enc-decoy-info')
);
setupDropZone(
  document.getElementById('dec-file-drop'),
  document.getElementById('dec-file'),
  document.getElementById('dec-file-info')
);
setupDropZone(
  document.getElementById('det-file-drop'),
  document.getElementById('det-file'),
  document.getElementById('det-file-info')
);
setupDropZone(
  document.getElementById('ctf-file-drop'),
  document.getElementById('ctf-file'),
  document.getElementById('ctf-file-info')
);
setupDropZone(
  document.getElementById('cap-file-drop'),
  document.getElementById('cap-file'),
  document.getElementById('cap-file-info')
);

// ── Password toggles ──────────────────────────────────────────────────────────
function setupPasswordToggle(btnId, inputId) {
  const btn = document.getElementById(btnId);
  const input = document.getElementById(inputId);
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

// ── Method description ────────────────────────────────────────────────────────
const methodSelect = document.getElementById('enc-method');
const methodDesc = document.getElementById('method-desc');
if (methodSelect && methodDesc) {
  methodSelect.addEventListener('change', () => {
    const selected = methodSelect.options[methodSelect.selectedIndex];
    const desc = selected.dataset.desc || '';
    methodDesc.textContent = desc;
    methodDesc.style.display = desc ? 'block' : 'none';
  });
}

// ── Depth slider ──────────────────────────────────────────────────────────────
const depthSlider = document.getElementById('enc-depth');
const depthDisplay = document.getElementById('depth-display');
const depthInfoText = document.getElementById('depth-info-text');
const depthDescriptions = {
  1: 'At depth 1: ~1 bit per pixel channel — completely invisible, maximum stealth.',
  2: 'At depth 2: ~2 bits per channel — 2× capacity, still invisible to naked eye.',
  3: 'At depth 3: ~3 bits per channel — 3× capacity, minor color shift on close inspection.',
  4: 'At depth 4: ~4 bits per channel — 4× capacity, visible color distortion in some images.',
};
if (depthSlider) {
  depthSlider.addEventListener('input', () => {
    const val = depthSlider.value;
    if (depthDisplay) depthDisplay.textContent = val;
    if (depthInfoText) depthInfoText.textContent = depthDescriptions[val] || '';
  });
}

const capDepthSlider = document.getElementById('cap-depth');
const capDepthDisplay = document.getElementById('cap-depth-display');
if (capDepthSlider && capDepthDisplay) {
  capDepthSlider.addEventListener('input', () => { capDepthDisplay.textContent = capDepthSlider.value; });
}

// ── Decoy collapse ────────────────────────────────────────────────────────────
const decoyToggle = document.getElementById('decoy-toggle');
const decoyContent = document.getElementById('decoy-content');
const decoyArrow = document.querySelector('#decoy-toggle .collapse-arrow');
if (decoyToggle && decoyContent) {
  decoyToggle.addEventListener('click', () => {
    const visible = decoyContent.style.display !== 'none';
    decoyContent.style.display = visible ? 'none' : 'flex';
    if (decoyArrow) decoyArrow.textContent = visible ? '▶' : '▼';
  });
}

// ── Loading overlay ───────────────────────────────────────────────────────────
function showLoading(msg = 'Processing…') {
  document.getElementById('loading-text').textContent = msg;
  document.getElementById('loading-overlay').style.display = 'flex';
}
function hideLoading() {
  document.getElementById('loading-overlay').style.display = 'none';
}

// ── Form submission helpers ───────────────────────────────────────────────────
async function submitForm(formId, endpoint, resultId, loadingMsg, onSuccess) {
  const form = document.getElementById(formId);
  const resultArea = document.getElementById(resultId);
  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    resultArea.style.display = 'none';
    showLoading(loadingMsg);

    try {
      const formData = new FormData(form);
      const response = await fetch(endpoint, { method: 'POST', body: formData });

      if (response.ok && response.headers.get('content-type')?.includes('application/octet-stream')) {
        // File download
        const blob = await response.blob();
        const disposition = response.headers.get('content-disposition') || '';
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : 'result.bin';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename; a.click();
        URL.revokeObjectURL(url);
        resultArea.innerHTML = renderSuccess(`✓ File downloaded as <strong>${filename}</strong>`);
        resultArea.style.display = 'block';
      } else {
        const data = await response.json();
        if (!response.ok || data.error) {
          resultArea.innerHTML = renderError(data.error || 'Unknown error');
        } else {
          resultArea.innerHTML = onSuccess(data);
        }
        resultArea.style.display = 'block';
      }
    } catch (err) {
      resultArea.innerHTML = renderError(`Network error: ${err.message}`);
      resultArea.style.display = 'block';
    } finally {
      hideLoading();
    }
  });
}

// ── Result renderers ──────────────────────────────────────────────────────────
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
  const pct = Math.round(confidence * 100);
  const colorClass = pct > 70 ? 'red' : pct > 30 ? 'yellow' : 'green';
  return `
    <div class="confidence-bar-wrap">
      <div class="confidence-bar-bg">
        <div class="confidence-bar-fill ${colorClass}" style="width:${pct}%"></div>
      </div>
      <div class="confidence-label">${pct}% confidence</div>
    </div>`;
}

function renderDetectorResult(r) {
  const detected = r.detected;
  const details = r.details || {};
  const isSkipped = details.skipped === true;

  const statusIcon = isSkipped ? '⏭' : (detected ? '🔴' : '🟢');
  const statusLabel = isSkipped ? '<span style="color:var(--text-muted)">SKIPPED</span>' : (detected ? '<span style="color:var(--accent-red)">DETECTED</span>' : '<span style="color:var(--accent-green)">CLEAN</span>');
  const cardClass = isSkipped ? 'clean' : (detected ? 'detected' : '');

  let extraHtml = '';

  if (isSkipped) {
    extraHtml += `<div class="result-grid">
      <div class="result-key">Analysis</div><div class="result-val">${details.interpretation || 'Format not supported'}</div>
    </div>`;
  } else if (r.method === 'chi2') {
    extraHtml += `<div class="result-grid">
      <div class="result-key">p-value</div><div class="result-val">${(details.p_value || 0).toFixed(4)}</div>
      <div class="result-key">χ² stat</div><div class="result-val">${(details.chi2_statistic || 0).toFixed(2)}</div>
      <div class="result-key">Notes</div><div class="result-val">${details.interpretation || ''}</div>
    </div>`;
  } else if (r.method === 'rs') {
    const pct = Math.round((details.estimated_payload_fraction || 0) * 100);
    extraHtml += `<div class="result-grid">
      <div class="result-key">Est. hidden</div><div class="result-val">~${pct}% of pixels</div>
      <div class="result-key">Groups</div><div class="result-val">R=${details.regular_groups || 0}, S=${details.singular_groups || 0} / ${details.total_groups || 0}</div>
    </div>`;
  } else if (r.method === 'exif') {
    const findings = r.findings || [];
    if (findings.length > 0) {
      extraHtml += '<ul class="findings-list">';
      findings.slice(0, 8).forEach(f => {
        const cls = `finding-${f.suspicion || 'low'}`;
        const icon = f.suspicion === 'high' ? '❗' : f.suspicion === 'medium' ? '⚠' : 'ℹ';
        extraHtml += `<li class="${cls}">
          <span class="finding-field">${f.field || ''}</span>
          <span>${icon} ${f.description || ''}</span>
        </li>`;
      });
      extraHtml += '</ul>';
    }
  } else if (r.method === 'blind') {
    const candidates = details.candidates || [];
    if (candidates.length > 0) {
      extraHtml += `<div style="font-size:.8rem;color:var(--text-muted);margin-bottom:8px">Found ${details.candidates_found || 0} candidate(s) in ${details.elapsed_seconds || 0}s</div>`;
      extraHtml += '<div class="candidates-wrap">';
      candidates.slice(0, 5).forEach((c, i) => {
        extraHtml += `<div class="candidate-item">
          <strong>#${i + 1}</strong> Ch=${c.channel}, depth=${c.depth}, order=${c.row_order}
          — ${c.payload_bytes} bytes — <em>${c.payload_type || '?'}</em>
          (score: ${(c.score * 100).toFixed(0)}%)
        </div>`;
      });
      extraHtml += '</div>';
    } else {
      extraHtml += `<p style="font-size:.83rem;color:var(--text-muted)">No plausible payload candidates found.</p>`;
    }
  }

  return `<div class="result-card ${cardClass}" style="margin-bottom:12px">
    <div class="result-title accent-title">${statusIcon} ${r.method.toUpperCase()} &nbsp; ${statusLabel}</div>
    ${renderConfidenceBar(r.confidence)}
    ${extraHtml}
  </div>`;
}

// ── Encode form ───────────────────────────────────────────────────────────────
submitForm('encode-form', '/encode', 'encode-result',
  'Encrypting and embedding payload…',
  (data) => '' // File download handled above
);

// ── Decode form ───────────────────────────────────────────────────────────────
submitForm('decode-form', '/decode', 'decode-result',
  'Extracting and decrypting payload…',
  (data) => ''
);

// ── Detect form ───────────────────────────────────────────────────────────────
(function() {
  const form = document.getElementById('detect-form');
  const resultArea = document.getElementById('detect-result');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    resultArea.style.display = 'none';
    showLoading('Running detection engines…');
    try {
      const formData = new FormData(form);
      const response = await fetch('/detect', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) {
        resultArea.innerHTML = renderError(data.error);
      } else {
        let html = `<h3 style="font-size:1rem;color:var(--accent-cyan);margin-bottom:16px">Results for: <em>${data.file}</em></h3>`;
        (data.results || []).forEach(r => { html += renderDetectorResult(r); });
        resultArea.innerHTML = html;
      }
      resultArea.style.display = 'block';
    } catch (err) {
      resultArea.innerHTML = renderError(err.message);
      resultArea.style.display = 'block';
    } finally { hideLoading(); }
  });
})();

// ── CTF form ──────────────────────────────────────────────────────────────────
(function() {
  const form = document.getElementById('ctf-form');
  const resultArea = document.getElementById('ctf-result');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    resultArea.style.display = 'none';
    showLoading('Running full forensic analysis…');
    try {
      const formData = new FormData(form);
      const response = await fetch('/ctf', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) {
        resultArea.innerHTML = renderError(data.error);
      } else {
        const detected = data.verdict === 'STEGO DETECTED';
        const pct = Math.round((data.confidence || 0) * 100);
        let html = `<div class="ctf-verdict ${detected ? 'detected-bg' : 'clean-bg'}">
          <div class="ctf-verdict-label ${detected ? 'detected' : 'clean'}">${data.verdict}</div>
          <div class="ctf-verdict-pct">Overall confidence: ${pct}%</div>
        </div>`;
        (data.results || []).forEach(r => { html += renderDetectorResult(r); });
        if (data.has_extracted_payload && data.extracted_payload_b64) {
          const blob = b64toBlob(data.extracted_payload_b64);
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url; a.download = 'extracted_payload.bin';
          document.body.appendChild(a); a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
          html += `<div class="result-card success" style="margin-top:12px">
            <div class="result-title success-title">📥 Extracted payload downloaded as <code>extracted_payload.bin</code></div>
          </div>`;
        }
        resultArea.innerHTML = html;
      }
      resultArea.style.display = 'block';
    } catch (err) {
      resultArea.innerHTML = renderError(err.message);
      resultArea.style.display = 'block';
    } finally { hideLoading(); }
  });
})();

// ── Capacity form ─────────────────────────────────────────────────────────────
(function() {
  const form = document.getElementById('capacity-form');
  const resultArea = document.getElementById('capacity-result');
  if (!form) return;
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    resultArea.style.display = 'none';
    showLoading('Calculating capacity…');
    try {
      const formData = new FormData(form);
      const response = await fetch('/capacity', { method: 'POST', body: formData });
      const data = await response.json();
      if (data.error) {
        resultArea.innerHTML = renderError(data.error);
      } else {
        resultArea.innerHTML = `<div class="result-card success">
          <div class="result-title success-title">📏 Capacity Result</div>
          <div class="result-grid">
            <div class="result-key">File</div><div class="result-val">${data.file}</div>
            <div class="result-key">Method</div><div class="result-val cyan">${data.method}</div>
            <div class="result-key">Depth</div><div class="result-val">${data.depth} bit(s)</div>
            <div class="result-key">Capacity</div><div class="result-val green">${data.capacity_bytes.toLocaleString()} bytes</div>
            <div class="result-key"></div><div class="result-val">${data.capacity_kb.toFixed(2)} KB / ${data.capacity_mb.toFixed(4)} MB</div>
          </div>
        </div>`;
      }
      resultArea.style.display = 'block';
    } catch (err) {
      resultArea.innerHTML = renderError(err.message);
      resultArea.style.display = 'block';
    } finally { hideLoading(); }
  });
})();

// ── Helpers ───────────────────────────────────────────────────────────────────
function b64toBlob(b64Data, contentType = 'application/octet-stream') {
  const byteChars = atob(b64Data);
  const byteArrays = [];
  for (let offset = 0; offset < byteChars.length; offset += 512) {
    const slice = byteChars.slice(offset, offset + 512);
    const byteNums = new Array(slice.length);
    for (let i = 0; i < slice.length; i++) byteNums[i] = slice.charCodeAt(i);
    byteArrays.push(new Uint8Array(byteNums));
  }
  return new Blob(byteArrays, { type: contentType });
}
