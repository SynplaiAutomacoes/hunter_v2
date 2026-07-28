# ruff: noqa: F403,F405
from apps.budget.forms.steps.common import *
from dataclasses import dataclass
from typing import Any


@dataclass
class Step6ReviewContext:
    budget: "Budget"
    status_label: str
    status_class: str
    is_signature_resend: bool
    signature_button_label: str
    action_blockers: list[str]
    action_blockers_display: str
    action_blocked_reason_json: str
    has_active_workorder: bool
    cancel_workorder_block_message: str
    cancel_workorder_blocked_reason_json: str
    reject_workorder_block_message: str
    reject_workorder_blocked_reason_json: str
    approval_blockers: list[str]
    approval_blockers_display: str
    approval_blocked_reason_json: str
    signature_blockers: list[str]
    signature_blockers_display: str
    signature_blocked_json: str
    signature_blocked_reason_json: str
    can_toggle_signed_pdf: bool
    default_pdf_url: str
    default_pdf_download_url: str
    signed_pdf_url: str
    base_pdf_url: str
    signed_pdf_download_url: str
    base_pdf_download_url: str
    saved_observation_html: str
    cancellation_reason_html: str
    reopen_history_html: str
    step6_action_button_state_class: str
    blocked_step6_action_attrs: str
    blocked_approval_action_attrs: str
    approval_button_class: str
    approval_button_attrs: str
    cancel_button_attrs: str
    cancel_button_class: str
    reject_button_attrs: str
    reject_button_class: str
    products_html: str
    services_html: str
    kits_html: str


def build_step6_context(budget, form: Any) -> Step6ReviewContext:
    status_data = budget.budget_status_badge
    status_label = status_data["text"]
    status_class = status_data["class"]
    is_signature_resend = budget.signature_request_status == SignatureStatus.SENT and bool(budget.signature_external_id)
    signature_button_label = "Reenviar Documento" if is_signature_resend else "Enviar para Assinatura"
    action_blockers = list(budget.step6_action_blockers)
    action_blockers_display = " ".join(action_blockers)
    action_blocked_reason_json = escape(json.dumps(action_blockers_display))
    has_active_workorder = budget.workorders.exclude(status=WorkOrderStatus.CANCELLED).exists()
    cancel_workorder_block_message = "Nao e possivel cancelar um orcamento enquanto existir uma O.S. ativa vinculada. Cancele a O.S. primeiro para depois cancelar o orcamento."
    cancel_workorder_blocked_reason_json = escape(json.dumps(cancel_workorder_block_message))
    reject_workorder_block_message = "Nao e possivel reprovar um orcamento apos a abertura da O.S. Cancele a ordem de servico primeiro ou siga com o cancelamento do orcamento."
    reject_workorder_blocked_reason_json = escape(json.dumps(reject_workorder_block_message))
    approval_blockers = list(budget.approval_blockers)
    approval_blockers_display = " ".join(approval_blockers)
    approval_blocked_reason_json = escape(json.dumps(approval_blockers_display))
    signature_blockers = list(budget.signature_blockers)
    signature_blockers_display = " ".join(signature_blockers)
    step6_action_button_state_class = "opacity-60 cursor-not-allowed" if action_blockers else ""
    blocked_step6_action_attrs = 'onclick="showBlockedStep6Action({action_blocked_reason_json})" aria-disabled="true" title="{action_blockers_display}"'.format(action_blocked_reason_json=action_blocked_reason_json, action_blockers_display=escape(action_blockers_display)) if action_blockers else ""
    blocked_approval_action_attrs = 'onclick="showBlockedStep6Action({approval_blocked_reason_json})" aria-disabled="true" title="{approval_blockers_display}"'.format(approval_blocked_reason_json=approval_blocked_reason_json, approval_blockers_display=escape(approval_blockers_display)) if approval_blockers else ""
    approval_button_class = "btn-success" if not approval_blockers else "opacity-60 cursor-not-allowed"
    approval_button_attrs = blocked_approval_action_attrs if approval_blockers else "onclick=\"updateBudgetStatus({pk}, 'approve')\"".format(pk=budget.pk)
    if action_blockers:
        cancel_button_attrs = blocked_step6_action_attrs
        cancel_button_class = step6_action_button_state_class
    elif has_active_workorder:
        cancel_button_attrs = 'onclick="showBlockedStep6Action({cancel_blocked})" aria-disabled="true" title="{cancel_title}"'.format(cancel_blocked=cancel_workorder_blocked_reason_json, cancel_title=escape(cancel_workorder_block_message))
        cancel_button_class = "opacity-60 cursor-not-allowed"
    else:
        cancel_button_attrs = "onclick=\"updateBudgetStatus({pk}, 'cancel')\"".format(pk=budget.pk)
        cancel_button_class = ""
    if action_blockers:
        reject_button_attrs = blocked_step6_action_attrs
        reject_button_class = step6_action_button_state_class
    elif has_active_workorder:
        reject_button_attrs = 'onclick="showBlockedStep6Action({reject_blocked})" aria-disabled="true" title="{reject_title}"'.format(reject_blocked=reject_workorder_blocked_reason_json, reject_title=escape(reject_workorder_block_message))
        reject_button_class = "opacity-60 cursor-not-allowed"
    else:
        reject_button_attrs = "onclick=\"updateBudgetStatus({pk}, 'reject')\"".format(pk=budget.pk)
        reject_button_class = ""
    signature_blocked_json = "true" if signature_blockers else "false"
    signature_blocked_reason_json = escape(json.dumps(signature_blockers_display))
    can_toggle_signed_pdf = budget.signature_request_status in {SignatureStatus.SENT, SignatureStatus.APPROVED} and bool(budget.signature_external_id or budget.signature_document_id)
    default_pdf_url = reverse("budget:visualizar_pdf_assinatura", args=[budget.pk])
    default_pdf_download_url = "{default_pdf_url}?download=1".format(default_pdf_url=default_pdf_url)
    signed_pdf_url = "{default_pdf_url}?variant=signed".format(default_pdf_url=default_pdf_url)
    base_pdf_url = "{default_pdf_url}?variant=base".format(default_pdf_url=default_pdf_url)
    signed_pdf_download_url = "{default_pdf_url}?download=1&variant=signed".format(default_pdf_url=default_pdf_url)
    base_pdf_download_url = "{default_pdf_url}?download=1&variant=base".format(default_pdf_url=default_pdf_url)

    saved_observation = budget.observations or ""
    saved_observation_html = escape(saved_observation)

    cancellation_reason_html = ""
    if budget.cancellation_reason:
        cancellation_reason_html = (
            '<div class="alert alert-error shadow-sm mb-4 bg-opacity-20 border-error"><div class="flex flex-col gap-1 text-error"><span class="text-gray-900 font-bold text-sm uppercase tracking-wider">Motivo do Cancelamento</span><span class="text-gray-900 text-base">{reason}</span></div></div>'
        ).format(reason=budget.cancellation_reason)

    history_entries = list(budget.history_entries.filter(action=BudgetHistory.Action.REOPENED).select_related("user")[:10])
    history_entries.reverse()
    reopen_history_html = ""
    if history_entries:
        snapshot_scripts = ""
        history_rows = ""
        for idx, entry in enumerate(history_entries):
            rev_number = idx + 1
            has_snapshot = bool(entry.snapshot)
            rev_button = ""
            if has_snapshot:
                snapshot_json = json.dumps(entry.snapshot)
                snapshot_scripts += f"<script type='application/json' id='rev-snapshot-{entry.pk}'>{snapshot_json}</script>"
                rev_button = f"<a role='button' class='btn btn-ghost btn-xs text-info' onclick='openRevisionModal({entry.pk}, {rev_number}); return false;'>Rev {rev_number}</a>"
            else:
                rev_button = f"<span class='badge badge-ghost badge-sm'>Rev {rev_number}</span>"

            user_display = f" por {escape(entry.user.get_full_name() or entry.user.username)}" if entry.user else ""
            history_rows += (
                "<div class='rounded-lg border border-base-300 bg-base-100 p-3'>"
                f"<div class='flex items-center justify-between'>"
                f"<p class='text-sm font-medium text-base-content'>"
                f"{timezone.localtime(entry.criado_em).strftime('%d/%m/%Y %H:%M')} - Orçamento reaberto"
                f"{user_display}</p>"
                f"{rev_button}"
                f"</div>"
                f"<p class='mt-1 whitespace-pre-line text-sm text-base-content/80'>{escape(entry.reason)}</p>"
                "</div>"
            )

        revision_modal_html = """
        <dialog id="revisionModal" class="modal">
            <div class="modal-box w-11/12 max-w-3xl">
                <a role="button" class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2"
                   onclick="this.closest('dialog').close()">&#10005;</a>
                <h3 class="font-bold text-lg" id="revisionModalTitle">Revisão</h3>
                <div class="overflow-y-auto mt-4" id="revisionModalBody"></div>
            </div>
        </dialog>
        <script>
        function openRevisionModal(entryPk, revNumber) {
            const el = document.getElementById('rev-snapshot-' + entryPk);
            if (!el) return;
            const snapshot = JSON.parse(el.textContent);
            const modal = document.getElementById('revisionModal');
            document.getElementById('revisionModalTitle').textContent = 'Revisão ' + revNumber;
            const body = document.getElementById('revisionModalBody');

            let html = '';

            const isOldFormat = snapshot.items && Array.isArray(snapshot.items);

            if (isOldFormat) {
                if (snapshot.discount_value && snapshot.discount_value !== 'R$\\u00a00,00' && snapshot.discount_value !== 'R$ 0,00') {
                    html += '<div class="alert alert-info mb-4 text-sm"><span>Desconto: ' +
                        snapshot.discount_value + ' (' + snapshot.discount_percentage + '%)</span></div>';
                }

                const items = snapshot.items || [];
                if (items.length === 0) {
                    html += '<p class="text-sm text-base-content/60">Nenhum item registrado nesta revisão.</p>';
                } else {
                    html += '<table class="table table-sm table-zebra w-full">';
                    html += '<thead><tr>';
                    html += '<th>Tipo</th><th>Descrição</th><th class="text-center">Qtd</th>';
                    html += '<th class="text-right">Peça</th><th class="text-right">Serviço</th>';
                    html += '<th class="text-right">Total</th>';
                    html += '</tr></thead><tbody>';
                    const typeLabels = {product: 'Peça', service: 'Serviço', kit: 'Kit'};
                    const typeBadges = {product: 'badge-primary', service: 'badge-secondary', kit: 'badge-accent'};
                    items.forEach(function(item) {
                        const badge = typeBadges[item.item_type] || 'badge-ghost';
                        const label = typeLabels[item.item_type] || item.item_type;
                        html += '<tr>';
                        html += '<td><span class="badge badge-sm ' + badge + '">' + label + '</span></td>';
                        html += '<td>' + (item.description || '-') + '</td>';
                        html += '<td class="text-center">' + item.quantity + '</td>';
                        html += '<td class="text-right">' + (item.product_selling_price || '-') + '</td>';
                        html += '<td class="text-right">' + (item.service_selling_price || '-') + '</td>';
                        html += '<td class="text-right font-medium">' + (item.total || '-') + '</td>';
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                }
            } else {
                const fields = snapshot.fields || {};
                const items = snapshot.items || {added: [], removed: [], modified: []};

                let hasChanges = false;

                const fieldKeys = Object.keys(fields);
                if (fieldKeys.length > 0) {
                    hasChanges = true;
                    html += '<div class="mb-5">';
                    html += '<h4 class="font-semibold text-base mb-2 border-b pb-1 text-base-content">Informações Gerais Modificadas</h4>';
                    html += '<ul class="list-disc list-inside space-y-1 text-sm text-base-content/80">';
                    const budgetTypeLabels = {sale: 'Venda', warranty: 'Garantia', courtesy: 'Cortesia'};
                    fieldKeys.forEach(function(key) {
                        const change = fields[key];
                        let oldVal = (change.old !== null && change.old !== undefined && change.old !== '') ? change.old : '<i>(vazio)</i>';
                        let newVal = (change.new !== null && change.new !== undefined && change.new !== '') ? change.new : '<i>(vazio)</i>';
                        if (key === 'budget_type') {
                            oldVal = budgetTypeLabels[oldVal] || oldVal;
                            newVal = budgetTypeLabels[newVal] || newVal;
                        }
                        html += '<li><strong>' + change.label + '</strong>: de ' + oldVal + ' para ' + newVal + '</li>';
                    });
                    html += '</ul>';
                    html += '</div>';
                }

                const added = items.added || [];
                if (added.length > 0) {
                    hasChanges = true;
                    html += '<div class="mb-5">';
                    html += '<h4 class="font-semibold text-base mb-2 border-b pb-1 text-success">Itens Adicionados</h4>';
                    html += '<table class="table table-sm table-zebra w-full">';
                    html += '<thead><tr><th>Tipo</th><th>Descrição</th><th class="text-center">Qtd</th><th class="text-right">Total</th></tr></thead><tbody>';
                    const typeLabels = {product: 'Peça', service: 'Serviço', kit: 'Kit'};
                    const typeBadges = {product: 'badge-primary', service: 'badge-secondary', kit: 'badge-accent'};
                    added.forEach(function(item) {
                        const badge = typeBadges[item.item_type] || 'badge-ghost';
                        const label = typeLabels[item.item_type] || item.item_type;
                        html += '<tr>';
                        html += '<td><span class="badge badge-sm ' + badge + '">' + label + '</span></td>';
                        html += '<td>' + (item.description || '-') + '</td>';
                        html += '<td class="text-center">' + item.quantity + '</td>';
                        html += '<td class="text-right font-medium">' + (item.total || '-') + '</td>';
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                    html += '</div>';
                }

                const removed = items.removed || [];
                if (removed.length > 0) {
                    hasChanges = true;
                    html += '<div class="mb-5">';
                    html += '<h4 class="font-semibold text-base mb-2 border-b pb-1 text-error">Itens Removidos</h4>';
                    html += '<table class="table table-sm table-zebra w-full">';
                    html += '<thead><tr><th>Tipo</th><th>Descrição</th><th class="text-center">Qtd</th><th class="text-right">Total</th></tr></thead><tbody>';
                    const typeLabels = {product: 'Peça', service: 'Serviço', kit: 'Kit'};
                    const typeBadges = {product: 'badge-primary', service: 'badge-secondary', kit: 'badge-accent'};
                    removed.forEach(function(item) {
                        const badge = typeBadges[item.item_type] || 'badge-ghost';
                        const label = typeLabels[item.item_type] || item.item_type;
                        html += '<tr>';
                        html += '<td><span class="badge badge-sm ' + badge + '">' + label + '</span></td>';
                        html += '<td>' + (item.description || '-') + '</td>';
                        html += '<td class="text-center">' + item.quantity + '</td>';
                        html += '<td class="text-right font-medium">' + (item.total || '-') + '</td>';
                        html += '</tr>';
                    });
                    html += '</tbody></table>';
                    html += '</div>';
                }

                const modified = items.modified || [];
                if (modified.length > 0) {
                    hasChanges = true;
                    html += '<div class="mb-5">';
                    html += '<h4 class="font-semibold text-base mb-2 border-b pb-1 text-warning">Itens Modificados</h4>';
                    html += '<div class="space-y-3">';
                    modified.forEach(function(mod) {
                        const typeLabels = {product: 'Peça', service: 'Serviço', kit: 'Kit'};
                        const label = typeLabels[mod.item_type] || mod.item_type;
                        html += '<div class="p-3 rounded bg-base-200/50 text-sm border border-base-300">';
                        html += '<div class="font-semibold text-base-content mb-1">' + label + ': ' + mod.description + '</div>';
                        html += '<ul class="list-disc list-inside space-y-1 text-xs text-base-content/80">';
                        Object.keys(mod.changes).forEach(function(fKey) {
                            const change = mod.changes[fKey];
                            html += '<li><strong>' + change.label + '</strong>: de ' + change.old + ' para ' + change.new + '</li>';
                        });
                        html += '</ul>';
                        html += '</div>';
                    });
                    html += '</div>';
                    html += '</div>';
                }

                if (!hasChanges) {
                    html += '<p class="text-sm text-base-content/60">Nenhuma alteração foi realizada nesta revisão.</p>';
                }
            }

            body.innerHTML = html;
            modal.showModal();
        }
        </script>
        """

        reopen_history_html = f"{snapshot_scripts}<div class='mt-4 rounded-xl border border-base-300 bg-base-200/40 p-4'><h5 class='text-lg font-semibold text-base-content'>Histórico de reaberturas</h5><div class='mt-3 space-y-3'>{history_rows}</div></div>{revision_modal_html}"

    rows = _render_budget_items_rows(budget, step6=True)
    products_html = rows["product"]
    services_html = rows["service"]
    kits_html = rows["kit"]

    return Step6ReviewContext(
        budget=budget,
        status_label=status_label,
        status_class=status_class,
        is_signature_resend=is_signature_resend,
        signature_button_label=signature_button_label,
        action_blockers=action_blockers,
        action_blockers_display=action_blockers_display,
        action_blocked_reason_json=action_blocked_reason_json,
        has_active_workorder=has_active_workorder,
        cancel_workorder_block_message=cancel_workorder_block_message,
        cancel_workorder_blocked_reason_json=cancel_workorder_blocked_reason_json,
        reject_workorder_block_message=reject_workorder_block_message,
        reject_workorder_blocked_reason_json=reject_workorder_blocked_reason_json,
        approval_blockers=approval_blockers,
        approval_blockers_display=approval_blockers_display,
        approval_blocked_reason_json=approval_blocked_reason_json,
        signature_blockers=signature_blockers,
        signature_blockers_display=signature_blockers_display,
        signature_blocked_json=signature_blocked_json,
        signature_blocked_reason_json=signature_blocked_reason_json,
        can_toggle_signed_pdf=can_toggle_signed_pdf,
        default_pdf_url=default_pdf_url,
        default_pdf_download_url=default_pdf_download_url,
        signed_pdf_url=signed_pdf_url,
        base_pdf_url=base_pdf_url,
        signed_pdf_download_url=signed_pdf_download_url,
        base_pdf_download_url=base_pdf_download_url,
        saved_observation_html=saved_observation_html,
        cancellation_reason_html=cancellation_reason_html,
        reopen_history_html=reopen_history_html,
        step6_action_button_state_class=step6_action_button_state_class,
        blocked_step6_action_attrs=blocked_step6_action_attrs,
        blocked_approval_action_attrs=blocked_approval_action_attrs,
        approval_button_class=approval_button_class,
        approval_button_attrs=approval_button_attrs,
        cancel_button_attrs=cancel_button_attrs,
        cancel_button_class=cancel_button_class,
        reject_button_attrs=reject_button_attrs,
        reject_button_class=reject_button_class,
        products_html=products_html,
        services_html=services_html,
        kits_html=kits_html,
    )
