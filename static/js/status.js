/**
 * PSIF Platform — status.js
 * Polls the dataset status API and updates the UI in real time,
 * handling automatic crash recovery, resumption, and retry actions.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Configured via inline script in status.html
    const datasetId = window.PSIF_DATASET_ID;
    const csrfToken = window.PSIF_CSRF_TOKEN || getCookie('csrftoken');
    if (!datasetId) return;

    // Elements
    const statusBadge = document.getElementById('status-badge');
    const statusText = document.getElementById('status-text');
    const statusSpinner = document.getElementById('status-spinner');
    const statusBanner = document.getElementById('status-banner');
    
    const progressBar = document.getElementById('progress-bar');
    const rowsLabel = document.getElementById('rows-label');
    const pctLabel = document.getElementById('pct-label');
    
    const statProcessed = document.getElementById('stat-processed');
    const statTotal = document.getElementById('stat-total');
    const statPct = document.getElementById('stat-pct');
    
    const errorSection = document.getElementById('error-log-section');
    const errorLog = document.getElementById('error-log');
    
    const redirectNotice = document.getElementById('redirect-notice');
    const actionRowPending = document.getElementById('action-row-pending');
    const actionRowComplete = document.getElementById('action-row-complete');
    const actionRowFailed = document.getElementById('action-row-failed');
    const actionRowProcessing = document.getElementById('action-row-processing');
    const actionRowCanceled = document.getElementById('action-row-canceled');
    const btnRetry = document.getElementById('btn-retry-dataset');
    const retrySpinner = document.getElementById('retry-spinner');
    const btnCancelProcessing = document.getElementById('btn-cancel-processing');
    const cancelSpinner = document.getElementById('cancel-spinner');
    const btnCancelProcessingText = document.getElementById('btn-cancel-processing-text');
    const btnResumeCanceled = document.getElementById('btn-resume-canceled');
    const resumeSpinner = document.getElementById('resume-spinner');
    const btnDiscardCanceled = document.getElementById('btn-discard-canceled');
    const btnDiscardStatus = document.getElementById('btn-discard-status');
    const btnDiscardFailed = document.getElementById('btn-discard-failed');
    const btnDeleteCompleted = document.getElementById('btn-delete-completed');

    // Timing & ETA elements
    const timingStrip = document.getElementById('timing-strip');
    const timingElapsed = document.getElementById('timing-elapsed');
    const timingEtaLabel = document.getElementById('timing-eta-label');
    const timingRemaining = document.getElementById('timing-remaining');
    const timingTotalWrap = document.getElementById('timing-total-wrap');
    const timingTotal = document.getElementById('timing-total');
    const timingRateWrap = document.getElementById('timing-rate-wrap');
    const timingRate = document.getElementById('timing-rate');

    let pollInterval = null;
    let localCountdownInterval = null;
    let latestTiming = null;
    let lastPollTime = null;
    let currentStatus = null;

    // Bind retry buttons
    if (btnRetry) {
        btnRetry.addEventListener('click', handleRetry);
    }
    if (btnResumeCanceled) {
        btnResumeCanceled.addEventListener('click', handleResume);
    }

    // Bind cancel processing button
    async function handleCancelProcessing() {
        if (!btnCancelProcessing) return;
        const confirmed = window.confirm(
            "Cancel processing for this dataset? Processing will stop safely at the next checkpoint, preserving all completed incident rows."
        );
        if (!confirmed) return;

        btnCancelProcessing.disabled = true;
        if (cancelSpinner) cancelSpinner.style.display = 'inline-block';
        if (btnCancelProcessingText) btnCancelProcessingText.textContent = 'Canceling…';

        if (statusBanner) {
            statusBanner.className = 'status-banner cancel_requested';
            statusBanner.style.display = 'block';
            statusBanner.innerHTML = '<strong>Canceling…</strong> Waiting for the current processing checkpoint to finish.';
        }

        try {
            const res = await fetch(`/api/datasets/${datasetId}/cancel/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({}),
            });

            const data = await res.json().catch(() => ({}));
            if (res.ok || res.status === 202) {
                if (!pollInterval) {
                    pollInterval = setInterval(pollStatus, 1000);
                }
                await pollStatus();
            } else {
                alert(`Cancel failed: ${data.detail || data.message || JSON.stringify(data)}`);
                btnCancelProcessing.disabled = false;
                if (cancelSpinner) cancelSpinner.style.display = 'none';
                if (btnCancelProcessingText) btnCancelProcessingText.textContent = 'Cancel Processing';
            }
        } catch (err) {
            console.error("Cancel request error:", err);
            alert("Network error while requesting cancellation.");
            btnCancelProcessing.disabled = false;
            if (cancelSpinner) cancelSpinner.style.display = 'none';
            if (btnCancelProcessingText) btnCancelProcessingText.textContent = 'Cancel Processing';
        }
    }
    if (btnCancelProcessing) {
        btnCancelProcessing.addEventListener('click', handleCancelProcessing);
    }

    async function handleResume() {
        if (!btnResumeCanceled) return;
        btnResumeCanceled.disabled = true;
        if (resumeSpinner) resumeSpinner.style.display = 'inline-block';
        try {
            await handleRetry();
        } finally {
            btnResumeCanceled.disabled = false;
            if (resumeSpinner) resumeSpinner.style.display = 'none';
        }
    }

    // Bind discard/delete buttons
    async function handleDiscard(btn, isCompleted = false) {
        const confirmMsg = isCompleted
            ? 'Delete this dataset?\n\nThis will permanently delete the dataset, its uploaded file, and ALL associated incident records.\n\nThis action cannot be undone.'
            : 'Discard this dataset?\n\nThis will permanently delete the dataset, its uploaded file, and any partially-ingested incident records.\n\nThis action cannot be undone.';
        const confirmed = window.confirm(confirmMsg);
        if (!confirmed) return;

        btn.disabled = true;
        const origHtml = btn.innerHTML;
        btn.innerHTML = isCompleted ? 'Deleting…' : 'Discarding…';

        try {
            const res = await fetch(`/api/datasets/${datasetId}/`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
            });

            if (res.ok) {
                window.location.href = '/datasets/';
            } else {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Unable to delete this dataset. It may currently be processing or have protected incident records.');
            }
        } catch (e) {
            btn.disabled = false;
            btn.innerHTML = origHtml;
            alert(e.message || 'Unable to delete this dataset.');
        }
    }

    if (btnDiscardStatus) {
        btnDiscardStatus.addEventListener('click', () => handleDiscard(btnDiscardStatus, false));
    }
    if (btnDiscardFailed) {
        btnDiscardFailed.addEventListener('click', () => handleDiscard(btnDiscardFailed, false));
    }
    if (btnDiscardCanceled) {
        btnDiscardCanceled.addEventListener('click', () => handleDiscard(btnDiscardCanceled, false));
    }
    if (btnDeleteCompleted) {
        btnDeleteCompleted.addEventListener('click', () => handleDiscard(btnDeleteCompleted, true));
    }

    // Initialize category explanation popovers
    initDataQualityTooltips();

    // Start local 1-second countdown ticker for smooth visual progression
    startLocalCountdown();

    // Start polling immediately
    pollStatus();
    pollInterval = setInterval(pollStatus, 1000); // 1s polling

    async function pollStatus() {
        try {
            const res = await fetch(`/api/datasets/${datasetId}/status/`);
            if (!res.ok) {
                console.error("Failed to fetch status", res.status);
                return;
            }
            
            const data = await res.json();
            updateUI(data);

            // Stop polling when completed, failed, canceled, or awaiting mapping
            if (data.status === 'completed' || data.status === 'failed' || data.status === 'canceled' || data.status === 'mapping_pending' || data.status === 'uploaded') {
                if (pollInterval) {
                    clearInterval(pollInterval);
                    pollInterval = null;
                }
                
                // Show appropriate action row
                if (actionRowComplete) actionRowComplete.style.display = (data.status === 'completed') ? 'flex' : 'none';
                if (actionRowFailed) actionRowFailed.style.display = (data.status === 'failed') ? 'flex' : 'none';
                if (actionRowCanceled) actionRowCanceled.style.display = (data.status === 'canceled') ? 'flex' : 'none';
                if (actionRowPending) actionRowPending.style.display = (data.status === 'mapping_pending' || data.status === 'uploaded') ? 'flex' : 'none';
                if (actionRowProcessing) actionRowProcessing.style.display = 'none';
            } else {
                // In active states (processing, retrying, cancel_requested)
                if (actionRowComplete) actionRowComplete.style.display = 'none';
                if (actionRowFailed) actionRowFailed.style.display = 'none';
                if (actionRowCanceled) actionRowCanceled.style.display = 'none';
                if (actionRowPending) actionRowPending.style.display = 'none';
                if (actionRowProcessing) actionRowProcessing.style.display = 'flex';

                if (btnCancelProcessing) {
                    if (data.status === 'cancel_requested') {
                        btnCancelProcessing.disabled = true;
                        if (cancelSpinner) cancelSpinner.style.display = 'inline-block';
                        if (btnCancelProcessingText) btnCancelProcessingText.textContent = 'Canceling…';
                    } else {
                        btnCancelProcessing.disabled = false;
                        if (cancelSpinner) cancelSpinner.style.display = 'none';
                        if (btnCancelProcessingText) btnCancelProcessingText.textContent = 'Cancel Processing';
                    }
                }
            }

        } catch (e) {
            console.error("Polling error:", e);
        }
    }

    async function handleRetry() {
        if (!btnRetry && !btnResumeCanceled) return;
        const targetBtn = btnRetry || btnResumeCanceled;
        targetBtn.disabled = true;
        if (retrySpinner) retrySpinner.style.display = 'inline-block';
        if (resumeSpinner) resumeSpinner.style.display = 'inline-block';

        try {
            const res = await fetch(`/api/datasets/${datasetId}/retry/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({}),
            });

            if (res.ok) {
                if (actionRowFailed) actionRowFailed.style.display = 'none';
                if (actionRowCanceled) actionRowCanceled.style.display = 'none';
                if (actionRowProcessing) actionRowProcessing.style.display = 'flex';
                // Restart polling
                if (!pollInterval) {
                    pollInterval = setInterval(pollStatus, 1000);
                }
                await pollStatus();
            } else {
                const errData = await res.json().catch(() => ({}));
                alert(`Retry failed: ${errData.detail || errData.message || JSON.stringify(errData)}`);
            }
        } catch (err) {
            console.error("Retry request error:", err);
            alert("Network error while requesting retry.");
        } finally {
            targetBtn.disabled = false;
            if (retrySpinner) retrySpinner.style.display = 'none';
            if (resumeSpinner) resumeSpinner.style.display = 'none';
        }
    }

    function updateUI(data) {
        const pct = data.percent || 0;
        const processed = data.processed_rows || 0;
        const total = data.total_rows ? data.total_rows : '?';
        const st = data.status || 'processing';

        // Update badge
        statusBadge.className = `status-badge ${st}`;
        statusText.textContent = formatStatus(st, data.retry_count);
        
        if (st === 'processing' || st === 'retrying' || st === 'cancel_requested') {
            statusSpinner.style.display = 'inline-block';
        } else {
            statusSpinner.style.display = 'none';
        }

        // Update status banner text
        if (statusBanner) {
            if (st === 'processing') {
                statusBanner.className = 'status-banner';
                statusBanner.style.display = 'none';
                statusBanner.textContent = '';
            } else if (st === 'retrying') {
                statusBanner.className = 'status-banner retrying';
                statusBanner.style.display = 'block';
                statusBanner.innerHTML = `<strong>Resuming Processing:</strong> Processing worker restarted. Resuming from saved progress (checkpoint: row ${processed}). Attempt ${data.retry_count || 1} of ${data.max_retries || 3}.`;
            } else if (st === 'cancel_requested') {
                statusBanner.className = 'status-banner cancel_requested';
                statusBanner.style.display = 'block';
                statusBanner.innerHTML = `<strong>Canceling…</strong> Waiting for the current processing checkpoint to finish. (${processed} rows committed).`;
            } else if (st === 'canceled') {
                statusBanner.className = 'status-banner canceled';
                statusBanner.style.display = 'block';
                statusBanner.innerHTML = `<strong>Canceled:</strong> Processing stopped at ${pct}%. ${processed} of ${total} rows were processed. All committed records and predictions have been safely preserved.`;
            } else if (st === 'failed') {
                statusBanner.className = 'status-banner failed';
                statusBanner.style.display = 'block';
                const lastErr = data.last_error ? `<br><span style="font-family: var(--font-mono); font-size: 0.8rem;">${data.last_error}</span>` : '';
                statusBanner.innerHTML = `<strong>Processing Interrupted:</strong> Processing failed after automatic recovery attempts.<br>The dataset was not lost. Previously completed rows (${processed}) were preserved.${lastErr}`;
            } else if (st === 'completed') {
                const hasDqIssues = (data.quality_summary && (data.quality_summary.rejected > 0 || data.quality_summary.accepted_with_warnings > 0));
                if (hasDqIssues) {
                    statusBanner.className = 'status-banner completed_with_warnings';
                    statusBanner.style.display = 'block';
                    statusBanner.textContent = 'Dataset processed with data-quality warnings.';
                } else {
                    statusBanner.className = 'status-banner';
                    statusBanner.style.display = 'none';
                    statusBanner.textContent = '';
                }
            }
        }

        // Update progress bar
        progressBar.style.width = `${pct}%`;
        progressBar.className = `progress-bar-inner ${st}`;
        
        rowsLabel.textContent = `${processed} / ${total} rows`;
        pctLabel.textContent = `${pct}%`;

        // Update stats
        statProcessed.textContent = processed;
        statTotal.textContent = total;
        statPct.textContent = `${pct}%`;

        // Update Data Quality Summary
        const dqAcceptedEl = document.getElementById('dq-count-accepted');
        const dqWarningsEl = document.getElementById('dq-count-warnings');
        const dqRejectedEl = document.getElementById('dq-count-rejected');
        const dqRejectionsCont = document.getElementById('dq-rejections-container');
        const dqRejectionsList = document.getElementById('dq-rejections-list');

        if (data.quality_summary) {
            const qs = data.quality_summary;
            if (dqAcceptedEl) dqAcceptedEl.textContent = qs.accepted !== undefined ? qs.accepted : processed;
            if (dqWarningsEl) dqWarningsEl.textContent = qs.accepted_with_warnings !== undefined ? qs.accepted_with_warnings : 0;
            if (dqRejectedEl) dqRejectedEl.textContent = qs.rejected !== undefined ? qs.rejected : 0;

            if (qs.rejections && qs.rejections.length > 0) {
                if (dqRejectionsCont) dqRejectionsCont.style.display = 'block';
                if (dqRejectionsList) {
                    dqRejectionsList.innerHTML = qs.rejections.map(rej => `
                        <div style="margin-bottom: 0.35rem;">
                            <strong style="color: var(--risk-critical);">Row ${rej.row}</strong>: Rejected &mdash; Reason: ${rej.reason}
                        </div>
                    `).join('');
                }
            }
        }

        // Update PSIF Classification Summary
        const psifCountEl = document.getElementById('classification-count-psif');
        const nonPsifCountEl = document.getElementById('classification-count-non-psif');
        const psifPctEl = document.getElementById('classification-pct-psif');
        const nonPsifPctEl = document.getElementById('classification-pct-non-psif');

        const psifCount = data.psif_count !== undefined ? data.psif_count : (data.quality_summary && data.quality_summary.psif_count !== undefined ? data.quality_summary.psif_count : 0);
        const nonPsifCount = data.non_psif_count !== undefined ? data.non_psif_count : (data.quality_summary && data.quality_summary.non_psif_count !== undefined ? data.quality_summary.non_psif_count : 0);
        const totalClassified = psifCount + nonPsifCount;

        if (psifCountEl) psifCountEl.textContent = psifCount.toLocaleString();
        if (nonPsifCountEl) nonPsifCountEl.textContent = nonPsifCount.toLocaleString();

        if (totalClassified > 0) {
            if (psifPctEl) psifPctEl.textContent = `(${((psifCount / totalClassified) * 100).toFixed(1)}%)`;
            if (nonPsifPctEl) nonPsifPctEl.textContent = `(${((nonPsifCount / totalClassified) * 100).toFixed(1)}%)`;
        } else {
            if (psifPctEl) psifPctEl.textContent = '';
            if (nonPsifPctEl) nonPsifPctEl.textContent = '';
        }

        // Ensure navigation links point to the filtered dataset
        const btnViewIncidents = document.getElementById('btn-view-incidents');
        if (btnViewIncidents && datasetId) {
            btnViewIncidents.href = `/incidents/?dataset=${datasetId}`;
        }
        const btnBrowseDataset = document.getElementById('btn-browse-dataset-incidents');
        if (btnBrowseDataset && datasetId) {
            btnBrowseDataset.href = `/incidents/?dataset=${datasetId}`;
        }

        // Update errors
        if (data.error_log) {
            errorSection.style.display = 'block';
            errorLog.textContent = data.error_log;
            errorLog.scrollTop = errorLog.scrollHeight;
        } else {
            errorSection.style.display = 'none';
        }

        // Update Timing & ETA
        currentStatus = st;
        renderTiming(data.timing, st);
    }

    function renderTiming(timing, st) {
        if (!timingStrip) return;
        latestTiming = timing;
        lastPollTime = Date.now();

        if (!timing) {
            timingStrip.style.display = 'none';
            return;
        }
        timingStrip.style.display = 'flex';

        if (st === 'completed') {
            if (timingEtaLabel) timingEtaLabel.textContent = 'Status:';
            if (timingRemaining) {
                timingRemaining.textContent = 'Completed';
                timingRemaining.style.color = 'var(--risk-low)';
            }
            if (timingElapsed) {
                timingElapsed.textContent = timing.formatted_duration || timing.formatted_elapsed || 'Duration unavailable';
            }
            if (timingTotalWrap) timingTotalWrap.style.display = 'none';
            if (timingRateWrap) {
                if (timing.processing_rate_rows_per_second) {
                    timingRateWrap.style.display = 'flex';
                    timingRate.textContent = `~${timing.processing_rate_rows_per_second} rows/s`;
                } else {
                    timingRateWrap.style.display = 'none';
                }
            }
            return;
        }

        if (st === 'failed') {
            if (timingEtaLabel) timingEtaLabel.textContent = 'Status:';
            if (timingRemaining) {
                timingRemaining.textContent = 'Failed';
                timingRemaining.style.color = 'var(--risk-critical)';
            }
            if (timingElapsed) {
                timingElapsed.textContent = timing.formatted_duration || timing.formatted_elapsed || 'Duration unavailable';
            }
            if (timingTotalWrap) timingTotalWrap.style.display = 'none';
            if (timingRateWrap) timingRateWrap.style.display = 'none';
            return;
        }

        if (st === 'retrying' || timing.is_stalled) {
            if (timingEtaLabel) timingEtaLabel.textContent = 'Status:';
            if (timingRemaining) {
                timingRemaining.textContent = 'Processing paused / retrying…';
                timingRemaining.style.color = '#d97706';
            }
            if (timingElapsed) timingElapsed.textContent = timing.formatted_elapsed || '—';
            if (timingTotalWrap) timingTotalWrap.style.display = 'none';
            if (timingRateWrap) timingRateWrap.style.display = 'none';
            return;
        }

        // Active processing state
        if (timingEtaLabel) timingEtaLabel.textContent = 'Remaining:';
        if (timingRemaining) {
            timingRemaining.textContent = timing.formatted_remaining || 'Estimating…';
            timingRemaining.style.color = 'var(--brand)';
        }
        if (timingElapsed) timingElapsed.textContent = timing.formatted_elapsed || '—';
        if (timingTotalWrap) {
            timingTotalWrap.style.display = 'flex';
            timingTotal.textContent = timing.formatted_total || '—';
        }
        if (timingRateWrap) {
            timingRateWrap.style.display = 'flex';
            timingRate.textContent = timing.processing_rate_rows_per_second
                ? `~${timing.processing_rate_rows_per_second} rows/s`
                : '—';
        }
    }

    function startLocalCountdown() {
        if (localCountdownInterval) clearInterval(localCountdownInterval);
        localCountdownInterval = setInterval(() => {
            if (currentStatus !== 'processing' || !latestTiming || !latestTiming.is_estimate_reliable) {
                return;
            }
            if (!lastPollTime) return;

            const deltaSeconds = Math.floor((Date.now() - lastPollTime) / 1000);
            if (deltaSeconds <= 0) return;

            // Increment elapsed time
            if (latestTiming.elapsed_seconds !== null && latestTiming.elapsed_seconds !== undefined) {
                const localElapsed = latestTiming.elapsed_seconds + deltaSeconds;
                if (timingElapsed) {
                    timingElapsed.textContent = formatSecondsClient(localElapsed, false);
                }
            }

            // Decrement remaining time smoothly, clamped to 0
            if (latestTiming.estimated_remaining_seconds !== null && latestTiming.estimated_remaining_seconds !== undefined) {
                const localRemaining = Math.max(0, latestTiming.estimated_remaining_seconds - deltaSeconds);
                if (timingRemaining) {
                    timingRemaining.textContent = formatSecondsClient(localRemaining, true);
                }
            }
        }, 1000);
    }

    function formatSecondsClient(seconds, isEstimate) {
        if (seconds === null || seconds === undefined || isNaN(seconds)) return '';
        const totalSec = Math.max(0, Math.round(seconds));
        const prefix = isEstimate ? '~' : '';

        if (totalSec < 60) {
            return `${prefix}${totalSec}s`;
        }
        const minutes = Math.floor(totalSec / 60);
        const remainingSec = totalSec % 60;
        if (minutes < 60) {
            return remainingSec > 0 ? `${prefix}${minutes}m ${remainingSec < 10 ? '0' : ''}${remainingSec}s` : `${prefix}${minutes}m`;
        }
        const hours = Math.floor(minutes / 60);
        const remainingMin = minutes % 60;
        return remainingMin > 0 ? `${prefix}${hours}h ${remainingMin}m` : `${prefix}${hours}h`;
    }

    function formatStatus(status, retryCount) {
        if (status === 'retrying') {
            return retryCount ? `Retrying (${retryCount})` : 'Retrying';
        }
        const map = {
            'uploaded': 'Uploaded',
            'mapping_pending': 'Awaiting Mapping',
            'processing': 'Processing',
            'retrying': 'Retrying',
            'cancel_requested': 'Canceling…',
            'canceled': 'Canceled',
            'completed': 'Completed',
            'failed': 'Failed'
        };
        return map[status] || status;
    }

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

    function initDataQualityTooltips() {
        const infoButtons = document.querySelectorAll('.dq-info-btn');
        if (!infoButtons.length) return;

        let activePopover = null;
        let hideTimeout = null;

        function openPopover(btn, popover) {
            if (activePopover && activePopover !== popover) {
                const prevBtn = activePopover.dataset.btnId ? document.getElementById(activePopover.dataset.btnId) : null;
                closePopover(prevBtn, activePopover);
            }
            clearTimeout(hideTimeout);
            
            // Boundary safety: ensure popover does not overflow off-screen on the right
            const rect = btn.getBoundingClientRect();
            const viewportWidth = window.innerWidth;
            if (rect.left + 330 > viewportWidth) {
                popover.style.left = 'auto';
                popover.style.right = '0';
            } else {
                popover.style.left = '0';
                popover.style.right = 'auto';
            }

            popover.classList.add('is-open');
            popover.setAttribute('aria-hidden', 'false');
            btn.setAttribute('aria-expanded', 'true');
            popover.dataset.btnId = btn.id;
            activePopover = popover;
        }

        function closePopover(btn, popover) {
            if (!popover) return;
            clearTimeout(hideTimeout);
            popover.classList.remove('is-open');
            popover.setAttribute('aria-hidden', 'true');
            if (btn) {
                btn.setAttribute('aria-expanded', 'false');
            } else if (popover.dataset.btnId) {
                const b = document.getElementById(popover.dataset.btnId);
                if (b) b.setAttribute('aria-expanded', 'false');
            }
            if (activePopover === popover) {
                activePopover = null;
            }
        }

        infoButtons.forEach(btn => {
            const popoverId = btn.getAttribute('aria-controls') || btn.getAttribute('aria-describedby');
            if (!popoverId) return;
            const popover = document.getElementById(popoverId);
            if (!popover) return;

            // Click / Tap toggle
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                if (popover.classList.contains('is-open')) {
                    closePopover(btn, popover);
                } else {
                    openPopover(btn, popover);
                }
            });

            // Hover interactions
            btn.addEventListener('mouseenter', () => {
                openPopover(btn, popover);
            });

            btn.addEventListener('mouseleave', () => {
                hideTimeout = setTimeout(() => {
                    closePopover(btn, popover);
                }, 150);
            });

            popover.addEventListener('mouseenter', () => {
                clearTimeout(hideTimeout);
            });

            popover.addEventListener('mouseleave', () => {
                hideTimeout = setTimeout(() => {
                    closePopover(btn, popover);
                }, 150);
            });

            // Focus interactions for keyboard users
            btn.addEventListener('focus', () => {
                openPopover(btn, popover);
            });

            btn.addEventListener('blur', () => {
                hideTimeout = setTimeout(() => {
                    if (!popover.contains(document.activeElement)) {
                        closePopover(btn, popover);
                    }
                }, 100);
            });

            // Escape key dismiss on button
            btn.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    closePopover(btn, popover);
                }
            });

            // Escape key dismiss on popover
            popover.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    closePopover(btn, popover);
                    btn.focus();
                }
            });
        });

        // Click outside dismiss
        document.addEventListener('click', (e) => {
            if (activePopover && !activePopover.contains(e.target) && !e.target.closest('.dq-info-btn')) {
                const b = activePopover.dataset.btnId ? document.getElementById(activePopover.dataset.btnId) : null;
                closePopover(b, activePopover);
            }
        });

        // Escape dismiss from anywhere
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && activePopover) {
                const b = activePopover.dataset.btnId ? document.getElementById(activePopover.dataset.btnId) : null;
                closePopover(b, activePopover);
                if (b) b.focus();
            }
        });
    }
});
