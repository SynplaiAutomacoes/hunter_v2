(function () {
    const POLL_INTERVAL_MS = 5000;
    const SENT_STATUS_TEXT = 'Enviado';

    function applyStatusBadge(badge, status) {
        if (!badge || !status || !status.text) {
            return;
        }
        badge.textContent = status.text;
        badge.className = 'badge font-semibold uppercase ' + (status.class || 'badge-ghost');
    }

    function updateReceiptTermPanelStatus(status) {
        const badge = document.getElementById('receipt-term-status-badge');
        applyStatusBadge(badge, status);

        const panel = document.querySelector('[data-receipt-term-panel]');
        const selectEl = document.querySelector('[data-receipt-term-select]');
        const statusMapElement = document.getElementById('receipt-term-status-map');
        if (!panel || !selectEl || !statusMapElement) {
            return;
        }

        try {
            const statusMap = JSON.parse(statusMapElement.textContent || '{}');
            statusMap[selectEl.value] = status;
            statusMapElement.textContent = JSON.stringify(statusMap);
            panel.__receiptTermStatusMap = statusMap;
        } catch (_error) {
            return;
        }

        if (typeof panel.__syncStatusPolling === 'function') {
            panel.__syncStatusPolling();
        }
    }

    function bindReceiptTermGlobalEvents() {
        if (document.body.dataset.receiptTermEventsBound === '1') {
            return;
        }
        document.body.dataset.receiptTermEventsBound = '1';

        document.body.addEventListener('closeBudgetTermModal', function () {
            const box = document.getElementById('budget-term-modal-box');
            if (box && typeof box.__stopModalPolling === 'function') {
                box.__stopModalPolling();
            }
            const container = document.getElementById('modal-container');
            if (container) {
                container.innerHTML = '';
            }
        });

        document.body.addEventListener('updateReceiptTermStatusBadge', function (event) {
            updateReceiptTermPanelStatus(event.detail || {});
        });
    }

    function initReceiptTermPanel(root) {
        if (!root) {
            return;
        }

        const panel = root.querySelector('[data-receipt-term-panel]');
        if (!panel || panel.dataset.bound === '1') {
            return;
        }
        panel.dataset.bound = '1';

        bindReceiptTermGlobalEvents();

        const select = panel.querySelector('[data-receipt-term-select]');
        const button = panel.querySelector('#receipt-term-open-btn');
        const badge = panel.querySelector('#receipt-term-status-badge');
        const statusMapElement = document.getElementById('receipt-term-status-map');
        if (!select || !button) {
            return;
        }

        let statusMap = {};
        if (statusMapElement && statusMapElement.textContent) {
            try {
                statusMap = JSON.parse(statusMapElement.textContent);
            } catch (_error) {
                statusMap = {};
            }
        }
        panel.__receiptTermStatusMap = statusMap;

        const urlTemplate = button.dataset.urlTemplate || '';
        const statusUrlTemplate = panel.dataset.statusUrlTemplate || '';
        let statusPollTimer = null;

        const stopStatusPolling = function () {
            if (statusPollTimer !== null) {
                window.clearInterval(statusPollTimer);
                statusPollTimer = null;
            }
        };

        const shouldPollStatus = function () {
            const currentMap = panel.__receiptTermStatusMap || {};
            const status = currentMap[select.value] || {};
            return status.text === SENT_STATUS_TEXT;
        };

        const updateStatusBadge = function () {
            const currentMap = panel.__receiptTermStatusMap || {};
            const status = currentMap[select.value] || { text: 'Não enviado', class: 'badge-ghost' };
            applyStatusBadge(badge, status);
        };

        const pollSigningStatus = function () {
            if (!shouldPollStatus() || !statusUrlTemplate) {
                stopStatusPolling();
                return;
            }

            const statusUrl = statusUrlTemplate.replace('{id}', select.value);
            window.fetch(statusUrl, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            })
                .then(function (response) {
                    if (!response.ok) {
                        return null;
                    }
                    return response.json();
                })
                .then(function (status) {
                    if (!status || !status.text) {
                        return;
                    }
                    statusMap[select.value] = status;
                    panel.__receiptTermStatusMap = statusMap;
                    if (statusMapElement) {
                        statusMapElement.textContent = JSON.stringify(statusMap);
                    }
                    updateStatusBadge();
                    if (status.text !== SENT_STATUS_TEXT) {
                        stopStatusPolling();
                    }
                })
                .catch(function () {
                    return;
                });
        };

        const syncStatusPolling = function () {
            stopStatusPolling();
            if (!shouldPollStatus()) {
                return;
            }
            pollSigningStatus();
            statusPollTimer = window.setInterval(pollSigningStatus, POLL_INTERVAL_MS);
        };

        panel.__syncStatusPolling = syncStatusPolling;
        panel.__stopStatusPolling = stopStatusPolling;

        const updateModalUrl = function () {
            if (urlTemplate) {
                button.setAttribute('hx-get', urlTemplate.replace('{id}', select.value));
                if (window.htmx) {
                    window.htmx.process(button);
                }
            }
            updateStatusBadge();
            syncStatusPolling();
        };

        select.addEventListener('change', updateModalUrl);
        syncStatusPolling();
    }

    function initBudgetTermModal(root) {
        const container = root && root.closest
            ? root.closest('#modal-container')
            : null;
        const modalContainer = container || (root && root.id === 'modal-container' ? root : null) || document.getElementById('modal-container');
        if (!modalContainer) {
            return;
        }

        const box = modalContainer.querySelector('#budget-term-modal-box');
        if (!box || box.dataset.termModalBound === '1') {
            return;
        }
        box.dataset.termModalBound = '1';

        bindReceiptTermGlobalEvents();

        const iframe = box.querySelector('[data-term-preview-frame]');
        const toggleButton = box.querySelector('[data-term-pdf-toggle]');
        const downloadButton = box.querySelector('[data-term-pdf-download]');
        const modalBadge = box.querySelector('[data-term-modal-status-badge]');
        const canToggle = box.dataset.canToggle === 'true';
        const baseUrl = box.dataset.baseUrl || '';
        const signedUrl = box.dataset.signedUrl || '';
        const signedDownloadUrl = box.dataset.signedDownloadUrl || '';
        const statusUrl = box.dataset.statusUrl || '';
        const modalUrl = box.dataset.modalUrl || '';
        let variant = box.dataset.initialVariant || 'base';
        let modalPollTimer = null;

        const stopModalPolling = function () {
            if (modalPollTimer !== null) {
                window.clearInterval(modalPollTimer);
                modalPollTimer = null;
            }
        };

        const applyVariant = function () {
            if (!iframe) {
                return;
            }
            iframe.src = variant === 'signed' ? signedUrl : baseUrl;
            if (toggleButton) {
                toggleButton.textContent = variant === 'signed' ? 'Ver não assinado' : 'Ver assinado';
            }
        };

        if (toggleButton && canToggle) {
            toggleButton.classList.remove('hidden');
            applyVariant();
            toggleButton.addEventListener('click', function () {
                variant = variant === 'signed' ? 'base' : 'signed';
                applyVariant();
            });
        }

        if (downloadButton && signedDownloadUrl) {
            downloadButton.addEventListener('click', function () {
                window.open(signedDownloadUrl, '_blank');
            });
        }

        const shouldPollModalStatus = function () {
            const currentText = modalBadge ? modalBadge.textContent.trim() : box.dataset.signatureStatus || '';
            return currentText === SENT_STATUS_TEXT;
        };

        const pollModalStatus = function () {
            if (!shouldPollModalStatus() || !statusUrl) {
                stopModalPolling();
                return;
            }

            window.fetch(statusUrl, {
                headers: { Accept: 'application/json' },
                credentials: 'same-origin',
            })
                .then(function (response) {
                    if (!response.ok) {
                        return null;
                    }
                    return response.json();
                })
                .then(function (status) {
                    if (!status || !status.text) {
                        return;
                    }
                    applyStatusBadge(modalBadge, status);
                    updateReceiptTermPanelStatus(status);
                    if (status.text === SENT_STATUS_TEXT) {
                        return;
                    }
                    stopModalPolling();
                    if (modalUrl && window.htmx) {
                        window.htmx.ajax('GET', modalUrl, {
                            target: '#modal-container',
                            swap: 'innerHTML',
                        });
                    }
                })
                .catch(function () {
                    return;
                });
        };

        const syncModalPolling = function () {
            stopModalPolling();
            if (!shouldPollModalStatus()) {
                return;
            }
            pollModalStatus();
            modalPollTimer = window.setInterval(pollModalStatus, POLL_INTERVAL_MS);
        };

        box.__stopModalPolling = stopModalPolling;
        syncModalPolling();
    }

    function initBudgetTermSigning(root) {
        initReceiptTermPanel(root);
        initBudgetTermModal(root);
    }

    function initBudgetTermSigningFromEvent(event) {
        const target = event && event.target;
        if (!target || !target.closest) {
            return;
        }
        const stepContainer = target.closest('#step-container');
        if (stepContainer) {
            initReceiptTermPanel(stepContainer);
        }
        const modalContainer = target.closest('#modal-container');
        if (modalContainer) {
            initBudgetTermModal(modalContainer);
        }
    }

    window.initReceiptTermPanel = initReceiptTermPanel;
    window.initBudgetTermModal = initBudgetTermModal;
    window.initBudgetTermSigning = initBudgetTermSigning;

    if (!window.__budgetTermSigningHooksBound) {
        window.__budgetTermSigningHooksBound = true;

        document.body.addEventListener('htmx:afterSettle', initBudgetTermSigningFromEvent);
        document.body.addEventListener('htmx:afterSwap', initBudgetTermSigningFromEvent);

        document.addEventListener('DOMContentLoaded', function () {
            initReceiptTermPanel(document.getElementById('step-container'));
        });
    }
})();
