/**
 * PSIF Platform — upload.js
 * Handles the dataset upload flow:
 * 1. File drag/drop + XHR upload with progress
 * 2. Renders preview table and mapping dropdowns
 * 3. Submits mapping
 * 4. Triggers background processing
 */

document.addEventListener('DOMContentLoaded', () => {
    // ── Elements ────────────────────────────────────────────────────────────
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseTrigger = document.getElementById('browse-trigger');
    const uploadProgress = document.getElementById('upload-progress');
    const progressBar = document.getElementById('progress-bar');
    const progressLabel = document.getElementById('progress-label');
    const uploadError = document.getElementById('upload-error');

    const sectionUpload = document.getElementById('section-upload');
    const sectionPreview = document.getElementById('section-preview');
    const sectionProcess = document.getElementById('section-process');

    const mappingGrid = document.getElementById('mapping-grid');
    const btnSaveMapping = document.getElementById('btn-save-mapping');
    const mappingError = document.getElementById('mapping-error');
    const mappingSavedBadge = document.getElementById('mapping-saved-badge');
    const btnProcess = document.getElementById('btn-process');
    const processError = document.getElementById('process-error');

    // ── State ───────────────────────────────────────────────────────────────
    let currentDatasetId = null;
    let csrfToken = getCookie('csrftoken');
    let currentXhr = null;
    let currentUploadDurationSeconds = null;

    // ── File Selection & Drag-Drop ──────────────────────────────────────────
    if (!dropZone) return; // Not on upload page

    browseTrigger.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    
    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
    });
    
    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            handleFileUpload(e.dataTransfer.files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileUpload(e.target.files[0]);
        }
    });

    // In-flight upload abort
    const btnCancelInFlight = document.getElementById('btn-cancel-in-flight');
    if (btnCancelInFlight) {
        btnCancelInFlight.addEventListener('click', async () => {
            if (currentXhr) {
                currentXhr.abort();
                currentXhr = null;
            }
            if (currentDatasetId) {
                try {
                    await fetch(`/api/datasets/${currentDatasetId}/`, {
                        method: 'DELETE',
                        headers: {
                            'X-CSRFToken': csrfToken,
                            'Content-Type': 'application/json'
                        }
                    });
                } catch (e) {
                    console.warn("Could not delete in-flight dataset:", e);
                }
            }
            resetUploadWizard();
            showNotification('Upload canceled and file discarded.', 'info');
        });
    }

    // ── Upload Step ─────────────────────────────────────────────────────────
    function handleFileUpload(file) {
        // Reset state
        hideNotification();
        uploadError.style.display = 'none';
        dropZone.style.display = 'none';
        uploadProgress.classList.add('visible');
        progressBar.style.width = '0%';
        progressLabel.textContent = `Uploading ${file.name}…`;

        const formData = new FormData();
        formData.append('file', file);

        const uploadStartTime = performance.now();
        const xhr = new XMLHttpRequest();
        currentXhr = xhr;
        xhr.open('POST', '/api/datasets/upload/', true);
        xhr.setRequestHeader('X-CSRFToken', csrfToken);

        // Upload progress
        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                progressBar.style.width = `${percent}%`;
                progressLabel.textContent = `Uploading ${file.name} — ${percent}%`;
                
                if (percent === 100) {
                    progressLabel.textContent = 'Parsing preview (this may take a moment)…';
                }
            }
        });

        // Response handling
        xhr.onload = () => {
            currentXhr = null;
            if (xhr.status === 201) {
                const uploadDurationMs = performance.now() - uploadStartTime;
                currentUploadDurationSeconds = Math.max(0.1, Math.round(uploadDurationMs / 100) / 10);
                const data = JSON.parse(xhr.responseText);
                showPreviewStep(data, file.name);
            } else {
                let errorMsg = 'Upload failed.';
                try {
                    const data = JSON.parse(xhr.responseText);
                    // DRF validation errors usually come as objects
                    if (data.file) {
                        errorMsg = Array.isArray(data.file) ? data.file[0] : data.file;
                    } else if (data.detail) {
                        errorMsg = data.detail;
                    }
                } catch (e) {
                    errorMsg = `Server error (${xhr.status}).`;
                }
                showUploadError(errorMsg);
            }
        };

        xhr.onerror = () => {
            currentXhr = null;
            showUploadError('Network error occurred during upload.');
        };
        xhr.onabort = () => {
            currentXhr = null;
        };
        xhr.send(formData);
    }

    function showUploadError(msg) {
        uploadProgress.classList.remove('visible');
        dropZone.style.display = 'block';
        uploadError.textContent = msg;
        uploadError.style.display = 'block';
        fileInput.value = ''; // Reset input
    }

    // ── Preview Step ────────────────────────────────────────────────────────
    function showPreviewStep(data, originalName) {
        currentDatasetId = data.dataset_id;
        
        // Hide upload section, show preview
        sectionUpload.style.display = 'none';
        sectionPreview.classList.add('visible');
        
        // Fill file info
        document.getElementById('file-type-badge').textContent = data.file_type;
        document.getElementById('file-name-label').textContent = originalName;
        document.getElementById('file-rows-label').textContent = data.total_rows ? `(~${data.total_rows.toLocaleString()} rows)` : '';
        document.getElementById('preview-count-badge').textContent = `${data.preview_rows.length} rows`;
        
        const uploadDur = currentUploadDurationSeconds || data.upload_duration_seconds;
        const uploadTimeEl = document.getElementById('file-upload-time-label');
        if (uploadTimeEl) {
            if (uploadDur) {
                uploadTimeEl.textContent = `Uploaded in ${uploadDur}s`;
                uploadTimeEl.style.display = 'inline-block';
            } else {
                uploadTimeEl.style.display = 'none';
            }
        }
        
        renderPreviewTable(data.columns, data.preview_rows);
        renderMappingUI(data.columns, data.column_types, data.suggested_mapping, data.canonical_field_labels);
    }

    function renderPreviewTable(columns, rows) {
        const thead = document.getElementById('preview-header');
        const tbody = document.getElementById('preview-body');
        
        // Header
        thead.innerHTML = '';
        columns.forEach(col => {
            const th = document.createElement('th');
            th.textContent = col;
            thead.appendChild(th);
        });

        // Body
        tbody.innerHTML = '';
        rows.forEach(row => {
            const tr = document.createElement('tr');
            columns.forEach(col => {
                const td = document.createElement('td');
                const val = row[col];
                td.textContent = (val === null || val === undefined) ? '' : String(val);
                td.title = td.textContent; // Tooltip for truncated text
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    }

    function renderMappingUI(columns, types, suggestedMapping, canonicalFields) {
        mappingGrid.innerHTML = '';
        
        // Build the <select> options once
        const buildOptions = (selectedValue) => {
            let html = `<option value="">-- Do not map (keep in raw data) --</option>`;
            for (const [field, label] of Object.entries(canonicalFields)) {
                const selected = (field === selectedValue) ? 'selected' : '';
                html += `<option value="${field}" ${selected}>${label}</option>`;
            }
            return html;
        };

        columns.forEach(col => {
            const row = document.createElement('div');
            const suggested = suggestedMapping[col] || '';
            row.className = `mapping-row ${suggested ? 'has-mapping' : 'unmapped'}`;
            
            const typeStr = types[col] || 'string';
            
            row.innerHTML = `
                <div class="source-col">
                    <span class="col-type-chip">${typeStr}</span>
                    <span title="${col}">${col}</span>
                </div>
                <div class="dest-col">
                    <select class="mapping-select" data-source-col="${col}" aria-label="Map ${col} to">
                        ${buildOptions(suggested)}
                    </select>
                </div>
            `;
            
            // Highlight row when mapped
            const select = row.querySelector('select');
            select.addEventListener('change', () => {
                if (select.value) {
                    row.classList.remove('unmapped');
                    row.classList.add('has-mapping');
                } else {
                    row.classList.remove('has-mapping');
                    row.classList.add('unmapped');
                }
                // Hide success badge if they change something after saving
                mappingSavedBadge.classList.remove('visible');
                sectionProcess.classList.remove('visible');
                btnProcess.disabled = true;
            });

            mappingGrid.appendChild(row);
        });
    }

    // ── Save Mapping ────────────────────────────────────────────────────────
    btnSaveMapping.addEventListener('click', async () => {
        if (!currentDatasetId) return;
        
        mappingError.style.display = 'none';
        btnSaveMapping.disabled = true;
        btnSaveMapping.textContent = 'Saving...';
        
        // Gather mapping
        const mapping = {};
        const selects = mappingGrid.querySelectorAll('.mapping-select');
        selects.forEach(sel => {
            mapping[sel.dataset.sourceCol] = sel.value;
        });

        try {
            const res = await fetch(`/api/datasets/${currentDatasetId}/column-mapping/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ column_mapping: mapping })
            });

            const data = await res.json();
            
            if (res.ok) {
                btnSaveMapping.textContent = 'Save Mapping';
                btnSaveMapping.disabled = false;
                mappingSavedBadge.classList.add('visible');
                
                // Reveal step 3
                sectionProcess.classList.add('visible');
                btnProcess.disabled = false;
                
                // Scroll down
                sectionProcess.scrollIntoView({ behavior: 'smooth' });
            } else {
                throw new Error(data.column_mapping || data.detail || 'Failed to save mapping');
            }
        } catch (e) {
            btnSaveMapping.disabled = false;
            btnSaveMapping.textContent = 'Save Mapping';
            mappingError.textContent = e.message;
            mappingError.style.display = 'block';
        }
    });

    // ── Trigger Process ─────────────────────────────────────────────────────
    btnProcess.addEventListener('click', async () => {
        if (!currentDatasetId) return;
        
        processError.style.display = 'none';
        btnProcess.disabled = true;
        btnProcess.textContent = 'Starting...';

        try {
            const res = await fetch(`/api/datasets/${currentDatasetId}/process/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({
                    upload_duration_seconds: currentUploadDurationSeconds
                })
            });

            const data = await res.json();
            
            if (res.ok || res.status === 202) {
                // Redirect to status page
                window.location.href = `/datasets/${currentDatasetId}/status/`;
            } else {
                throw new Error(data.detail || data.column_mapping || data.status || 'Failed to start processing');
            }
        } catch (e) {
            btnProcess.disabled = false;
            btnProcess.textContent = '🚀 Start Processing';
            processError.textContent = e.message;
            processError.style.display = 'block';
        }
    });

    // ── Cancel & Discard ────────────────────────────────────────────────────
    const cancelButtons = document.querySelectorAll('.btn-cancel-upload');
    cancelButtons.forEach(btn => {
        btn.addEventListener('click', async () => {
            if (!currentDatasetId) {
                resetUploadWizard();
                return;
            }

            const confirmed = window.confirm(
                "Are you sure you want to cancel this upload?\n\nThe uploaded file will be deleted and no records will be saved."
            );
            if (!confirmed) return;

            const originalText = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = 'Canceling…';

            try {
                const res = await fetch(`/api/datasets/${currentDatasetId}/`, {
                    method: 'DELETE',
                    headers: {
                        'X-CSRFToken': csrfToken,
                        'Content-Type': 'application/json'
                    }
                });

                const data = await res.json().catch(() => ({}));

                if (res.ok) {
                    resetUploadWizard();
                    showNotification('Upload canceled and file discarded.', 'success');
                } else {
                    throw new Error(data.detail || 'Unable to discard this dataset. It may currently be processing or protected.');
                }
            } catch (err) {
                btn.disabled = false;
                btn.innerHTML = originalText;
                alert('Error canceling upload: ' + err.message);
            }
        });
    });

    // Check if resuming an existing uncompleted upload
    async function checkResume() {
        const resumeId = window.PSIF_RESUME_ID;
        if (!resumeId) return;
        try {
            const res = await fetch(`/api/datasets/${resumeId}/preview/`);
            if (res.ok) {
                const data = await res.json();
                showPreviewStep(data, data.name);
            }
        } catch (e) {
            console.warn("Could not resume dataset preview:", e);
        }
    }
    checkResume();

    function resetUploadWizard() {
        currentDatasetId = null;
        currentUploadDurationSeconds = null;
        fileInput.value = '';
        const uploadTimeEl = document.getElementById('file-upload-time-label');
        if (uploadTimeEl) {
            uploadTimeEl.style.display = 'none';
            uploadTimeEl.textContent = '';
        }
        uploadProgress.classList.remove('visible');
        progressBar.style.width = '0%';
        progressLabel.textContent = 'Uploading…';
        uploadError.style.display = 'none';
        mappingError.style.display = 'none';
        processError.style.display = 'none';
        mappingSavedBadge.classList.remove('visible');
        sectionPreview.classList.remove('visible');
        sectionProcess.classList.remove('visible');
        btnProcess.disabled = true;
        dropZone.style.display = 'block';
        sectionUpload.style.display = 'block';
        sectionUpload.scrollIntoView({ behavior: 'smooth' });
    }

    function showNotification(msg, type = 'success') {
        const el = document.getElementById('upload-notification');
        if (!el) return;
        el.textContent = msg;
        if (type === 'success') {
            el.style.borderLeftColor = 'var(--cat-green, #4e7a5e)';
            el.style.background = 'rgba(78, 122, 94, 0.08)';
            el.style.color = 'var(--cat-green, #4e7a5e)';
        } else {
            el.style.borderLeftColor = 'var(--cat-blue, #5c7c8a)';
            el.style.background = 'rgba(92, 124, 138, 0.08)';
            el.style.color = 'var(--cat-blue, #5c7c8a)';
        }
        el.style.display = 'block';
        el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function hideNotification() {
        const el = document.getElementById('upload-notification');
        if (el) {
            el.style.display = 'none';
            el.textContent = '';
        }
    }

    // ── Helper ──────────────────────────────────────────────────────────────
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }
});
