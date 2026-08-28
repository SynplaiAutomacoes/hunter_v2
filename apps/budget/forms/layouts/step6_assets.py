def build_step6_assets_html() -> str:
    return """
                <style>
                    .table-fixed { table-layout: fixed; }
                </style>
                <script>
                    window.budgetPdfCacheVersion = Date.now().toString();

                    function withBudgetPdfCache(url) {
                        if (!url) return '';
                        const separator = url.includes('?') ? '&' : '?';
                        return `${url}${separator}_pdfv=${encodeURIComponent(window.budgetPdfCacheVersion)}`;
                    }

                    function openBudgetPdfModal(detail) {
                        const normalizedDetail = { ...(detail || {}) };
                        normalizedDetail.url = withBudgetPdfCache(normalizedDetail.url || '');
                        normalizedDetail.downloadUrl = withBudgetPdfCache(normalizedDetail.downloadUrl || '');
                        normalizedDetail.signedPdfUrl = withBudgetPdfCache(normalizedDetail.signedPdfUrl || '');
                        normalizedDetail.basePdfUrl = withBudgetPdfCache(normalizedDetail.basePdfUrl || '');
                        normalizedDetail.signedDownloadUrl = withBudgetPdfCache(normalizedDetail.signedDownloadUrl || '');
                        normalizedDetail.baseDownloadUrl = withBudgetPdfCache(normalizedDetail.baseDownloadUrl || '');
                        window.dispatchEvent(new CustomEvent('open-pdf-modal', { detail: normalizedDetail }));
                    }

                    async function saveObservation(budgetId) {
                        const observationEl = document.getElementById('budget-observation');
                        const observation = observationEl ? observationEl.value : '';

                        const response = await fetch('/budget/save-observation/', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                'X-CSRFToken': '{{ csrf_token }}'
                            },
                            body: JSON.stringify({
                                budget_id: budgetId,
                                observation: observation,
                            })
                        });
                        const payload = await response.json().catch(() => ({}));

                        if (!response.ok || payload.success === false) {
                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: {
                                    type: 'error',
                                    message: payload.error || 'Falha ao salvar a observação.',
                                },
                            }));
                            return;
                        }

                        if (observationEl && typeof payload.observation === 'string') {
                            observationEl.value = payload.observation;
                        }

                        window.budgetPdfCacheVersion = Date.now().toString();
                        const pdfModalFrame = document.querySelector('#pdfModal iframe');
                        if (pdfModalFrame) {
                            pdfModalFrame.src = 'about:blank';
                        }

                        document.body.dispatchEvent(new CustomEvent('showToast', {
                            detail: {
                                type: 'success',
                                message: 'Observação salva.',
                            },
                        }));
                    }

                    function showBlockedStep6Action(message) {
                        document.body.dispatchEvent(new CustomEvent('showToast', {
                            detail: {
                                type: 'error',
                                message: message || 'Preencha e salve os campos obrigatorios da revisao antes de continuar.',
                            },
                        }));
                    }

                    async function updateBudgetStatus(budgetId, status) {
                        const canReopenBudget = arguments.length > 2 ? Boolean(arguments[2]) : true;

                        if (status === 'reopen' && !canReopenBudget) {
                            await customConfirm(
                                'Você não tem permissão para reabrir este orçamento. Fale com um responsável que tenha essa permissão para continuar.',
                                { singleClose: true, closeText: 'Fechar' }
                            );
                            return;
                        }

                        if (status === 'cancel') {
                            const modal = document.getElementById('cancelBudgetModal');
                            const input = document.getElementById('cancellation-reason-input');
                            const responsibleInput = document.getElementById('cancellation-responsible-input');
                            const confirmBtn = document.getElementById('confirm-cancel-btn');

                            input.value = '';
                            responsibleInput.value = '';
                            modal.showModal();

                            confirmBtn.onclick = async () => {
                                const reason = input.value.trim();
                                if (!reason) {
                                    document.body.dispatchEvent(new CustomEvent('showToast', {
                                        detail: { type: 'error', message: 'O motivo do cancelamento é obrigatório.' },
                                    }));
                                    return;
                                }
                                if (!responsibleInput.value) {
                                    document.body.dispatchEvent(new CustomEvent('showToast', {
                                        detail: { type: 'error', message: 'O responsável pelo atendimento é obrigatório.' },
                                    }));
                                    return;
                                }
                                modal.close();

                                const formData = new FormData();
                                formData.append('cancellation_reason', reason);
                                formData.append('cancellation_responsible_id', responsibleInput.value);
                                executeStatusUpdate(budgetId, status, formData);
                            };
                            return;
                        }

                        if (status === 'reject') {
                            const modal = document.getElementById('rejectBudgetModal');
                            const input = document.getElementById('rejection-reason-input');
                            const responsibleInput = document.getElementById('rejection-responsible-input');
                            const confirmBtn = document.getElementById('confirm-reject-btn');

                            input.value = '';
                            responsibleInput.value = '';
                            modal.showModal();

                            confirmBtn.onclick = async () => {
                                const reason = input.value.trim();
                                if (!reason) {
                                    document.body.dispatchEvent(new CustomEvent('showToast', {
                                        detail: { type: 'error', message: 'O motivo da reprovação é obrigatório.' },
                                    }));
                                    return;
                                }
                                if (!responsibleInput.value) {
                                    document.body.dispatchEvent(new CustomEvent('showToast', {
                                        detail: { type: 'error', message: 'O responsável pelo atendimento é obrigatório.' },
                                    }));
                                    return;
                                }
                                modal.close();

                                const formData = new FormData();
                                formData.append('rejection_reason', reason);
                                formData.append('rejection_responsible_id', responsibleInput.value);
                                executeStatusUpdate(budgetId, status, formData);
                            };
                            return;
                        }

                        if (status === 'reopen') {
                            const reopenForm = document.getElementById('reopen-budget-form');
                            const reopenInput = document.getElementById('reopen-reason-input');

                            if (!reopenForm || !reopenInput) {
                                document.body.dispatchEvent(new CustomEvent('showToast', {
                                    detail: { type: 'error', message: 'Falha ao abrir o formulário de reabertura.' },
                                }));
                                return;
                            }

                            reopenForm.classList.remove('hidden');
                            reopenInput.focus();
                            return;
                        }

                        const confirmed = await customConfirm('Você tem certeza que deseja alterar o status deste orçamento?');
                        if (!confirmed) return;

                        executeStatusUpdate(budgetId, status);
                    }

                    async function executeStatusUpdate(budgetId, status, body = null) {
                        const response = await fetch(`/budget/update-status/${budgetId}/${status}`, {
                            method: 'POST',
                            headers: { 'X-CSRFToken': '{{ csrf_token }}', 'X-Requested-With': 'XMLHttpRequest' },
                            body: body
                        });

                        const payload = await response.json().catch(() => ({}));
                        if (!response.ok || payload.success === false) {
                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: {
                                    type: 'error',
                                    message: payload.error || 'Falha ao atualizar o status do orçamento.',
                                },
                            }));
                            return;
                        }

                        if (status === 'reopen') {
                            window.location.reload();
                            return;
                        }

                        window.location.href = "{% url 'budget:budget_list' %}";
                    }

                    async function confirmReopenBudgetStatus(budgetId) {
                        const reopenInput = document.getElementById('reopen-reason-input');
                        if (!reopenInput) {
                            return;
                        }

                        const reason = reopenInput.value.trim();
                        if (!reason) {
                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: { type: 'error', message: 'A justificativa da reabertura é obrigatória.' },
                            }));
                            reopenInput.focus();
                            return;
                        }

                        const formData = new FormData();
                        formData.append('reopen_reason', reason);
                        await executeStatusUpdate(budgetId, 'reopen', formData);
                    }

                    function cancelReopenBudgetStatus() {
                        const reopenForm = document.getElementById('reopen-budget-form');
                        const reopenInput = document.getElementById('reopen-reason-input');
                        if (reopenForm) {
                            reopenForm.classList.add('hidden');
                        }
                        if (reopenInput) {
                            reopenInput.value = '';
                        }
                    }

                    async function sendBudgetForSignature(buttonEl) {
                        const btn = buttonEl || document.getElementById('send-signature-btn');
                        const label = document.getElementById('send-signature-label');
                        const spinner = document.getElementById('send-signature-spinner');
                        const endpoint = btn ? btn.dataset.url : '';
                        const isResend = btn ? btn.dataset.isResend === 'true' : false;
                        const defaultLabel = isResend ? 'Reenviar Documento' : 'Enviar para Assinatura';

                        if (!endpoint) {
                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: {
                                    type: 'error',
                                    message: 'Endpoint de assinatura não configurado.',
                                },
                            }));
                            return;
                        }

                        if (isResend) {
                            const confirmed = await customConfirm('Você tem certeza que deseja reenviar este documento para assinatura?');
                            if (!confirmed) {
                                if (label) label.textContent = defaultLabel;
                                return;
                            }
                        }

                        if (btn) btn.disabled = true;
                        if (label) label.textContent = 'Enviando...';
                        if (spinner) spinner.classList.remove('hidden');

                        try {
                            const response = await fetch(endpoint, {
                                method: 'POST',
                                headers: {
                                    'X-CSRFToken': '{{ csrf_token }}',
                                    'X-Requested-With': 'XMLHttpRequest',
                                },
                            });

                            const payload = await response.json().catch(() => ({}));
                            if (!response.ok) {
                                throw new Error(payload.message || 'Falha ao enviar para assinatura.');
                            }

                            const toastType = payload.type || (payload.success ? 'success' : 'error');
                            const toastMessage = payload.message || (payload.success ? 'Orçamento enviado para assinatura.' : 'Falha ao enviar para assinatura.');

                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: {
                                    type: toastType,
                                    message: toastMessage,
                                },
                            }));

                            if (payload.success) {
                                setTimeout(() => {
                                    window.location.href = "{% url 'budget:budget_list' %}";
                                }, 900);
                            }
                        } catch (error) {
                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: {
                                    type: 'error',
                                    message: error && error.message ? error.message : 'Falha ao enviar para assinatura. Tente novamente.',
                                },
                            }));
                        } finally {
                            if (btn) btn.disabled = false;
                            if (label) label.textContent = defaultLabel;
                            if (spinner) spinner.classList.add('hidden');
                        }
                    }
                </script>
                <script>
                    (function() {
                        if (window.location.search.includes('reopen=1')) {
                            const btn = document.querySelector('[onclick*="reopen"]');
                            if (btn) {
                                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                btn.click();
                            }
                        }
                    })();
                </script>
    """
