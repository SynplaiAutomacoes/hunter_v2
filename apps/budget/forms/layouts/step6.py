# ruff: noqa: F403,F405
from apps.budget.forms.layouts.step6_assets import build_step6_assets_html
from apps.budget.forms.presenters.step6_context import build_step6_context
from apps.budget.forms.steps.common import *


def configure_budget_step6_form(form):
    customer_agreed_departure_at_field = form.fields["customer_agreed_departure_at"]
    service_expected_completion_at_field = form.fields["service_expected_completion_at"]

    if not isinstance(customer_agreed_departure_at_field, forms.DateTimeField) or not isinstance(service_expected_completion_at_field, forms.DateTimeField):
        raise TypeError("Campos de data/hora invalidos no BudgetStep6Form")

    for field in (customer_agreed_departure_at_field, service_expected_completion_at_field):
        field.input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ]
        field.required = True

    customer_agreed_departure_at_field.error_messages["required"] = Budget.CUSTOMER_AGREED_DEPARTURE_REQUIRED_MESSAGE
    service_expected_completion_at_field.error_messages["required"] = Budget.SERVICE_EXPECTED_COMPLETION_REQUIRED_MESSAGE

    if form.instance and form.instance.pk:
        autosave_url = reverse("budget:autosave_review_date", args=[form.instance.pk])
        for field_name in ("customer_agreed_departure_at", "service_expected_completion_at"):
            form.fields[field_name].widget.attrs.update(
                {
                    "data-budget-review-date-autosave": "1",
                    "data-autosave-field": field_name,
                    "data-autosave-url": autosave_url,
                }
            )

    budget = _get_budget_with_prefetched_items(form.instance)
    ctx = build_step6_context(budget, form)

    status_label = ctx.status_label
    status_class = ctx.status_class
    is_signature_resend = ctx.is_signature_resend
    signature_button_label = ctx.signature_button_label
    signature_blocked_json = ctx.signature_blocked_json
    signature_blocked_reason_json = ctx.signature_blocked_reason_json
    can_toggle_signed_pdf = ctx.can_toggle_signed_pdf
    default_pdf_url = ctx.default_pdf_url
    default_pdf_download_url = ctx.default_pdf_download_url
    signed_pdf_url = ctx.signed_pdf_url
    base_pdf_url = ctx.base_pdf_url
    signed_pdf_download_url = ctx.signed_pdf_download_url
    base_pdf_download_url = ctx.base_pdf_download_url
    saved_observation_html = ctx.saved_observation_html
    cancellation_reason_html = ctx.cancellation_reason_html
    reopen_history_html = ctx.reopen_history_html
    approval_button_class = ctx.approval_button_class
    approval_button_attrs = ctx.approval_button_attrs
    cancel_button_attrs = ctx.cancel_button_attrs
    cancel_button_class = ctx.cancel_button_class
    reject_button_attrs = ctx.reject_button_attrs
    reject_button_class = ctx.reject_button_class
    products_html = ctx.products_html
    services_html = ctx.services_html
    kits_html = ctx.kits_html

    form.helper = FormHelper()
    form.helper.form_tag = False

    form.helper.layout = Layout(
        # =========================
        # CSS utilitário obrigatório
        # =========================
        HTML(build_step6_assets_html()),
        alert_confirm_layout(),
        # =========================
        # MODAL DE CANCELAMENTO
        # =========================
        HTML("""
                <dialog id="cancelBudgetModal" class="modal">
                  <div class="modal-box">
                    <h3 class="font-bold text-lg">Cancelar Orçamento</h3>
                    <p class="py-4">Por favor, informe o motivo do cancelamento:</p>
                    <textarea id="cancellation-reason-input" class="textarea textarea-bordered w-full" rows="3" placeholder="Motivo do cancelamento..."></textarea>
                    <div class="modal-action">
                      <button type="button" class="btn" onclick="document.getElementById('cancelBudgetModal').close()">Voltar</button>
                      <button type="button" class="btn btn-error" id="confirm-cancel-btn">Confirmar Cancelamento</button>
                    </div>
                  </div>
                </dialog>
                """),
        # =========================
        # SCRIPTS (mantidos do código original)
        # =========================
        Div(
            HTML('<h3 class="text-2xl font-bold col-span-12">Revisão e Confirmação</h3>'),
        ),
        Div(
            Div(
                HTML('<div class="border-t-2 mb-6"></div>'),
                # -------- PRODUTOS --------
                Div(
                    HTML('<h3 class="text-xl font-semibold text-gray-700 mb-4">Peças Selecionadas</h3>'),
                    HTML(f"""
                            <div class="mb-10 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden">
                              <div class="overflow-x-auto">
                                <table class="table table-zebra table-fixed w-full">
                                  <thead class="bg-primary text-primary-content">
                                    <tr>
                                      <th class="w-[18%]">NOME</th>
                                      <th class="w-[18%]">APLICAÇÃO</th>
                                      <th class="w-[18%] text-center whitespace-normal break-words leading-tight">FORNECIDO PELO CLIENTE</th>
                                      <th class="w-[6%] text-center">QTD.</th>
                                      <th class="w-[10%]">CUSTO</th>
                                      <th class="w-[12%]">VALOR</th>
                                      <th class="w-[8%]">FRETE</th>
                                      <th class="w-[10%]">TOTAL</th>
                                    </tr>
                                  </thead>
                                  <tbody id="product-list-body">
                                    {products_html}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                            """),
                ),
                # -------- SERVIÇOS --------
                Div(
                    HTML('<h3 class="text-xl font-semibold text-gray-700 mb-4">Serviços Selecionados</h3>'),
                    HTML(f"""
                            <div class="mb-10 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden">
                                <div class="overflow-x-auto">
                                    <table class="table table-zebra table-fixed w-full">
                                        <thead class="bg-primary text-primary-content">
                                            <tr>
                                                <th class="w-[32%] whitespace-nowrap text-left">
                                                    NOME
                                                </th>
                                                
                                                <th class="w-[8%] whitespace-nowrap text-center">
                                                    QTD.
                                                </th>
                                                
                                                <th class="w-[14%] whitespace-nowrap text-right">
                                                    CUSTO
                                                </th>
                                                
                                                <th class="w-[16%] whitespace-nowrap text-right">
                                                    VALOR
                                                </th>

                                                <th class="w-[10%] whitespace-nowrap text-right">
                                                    FRETE
                                                </th>
                                                
                                                <th class="w-[10%] whitespace-nowrap text-center">
                                                    TEMPO
                                                </th>
                                                
                                                <th class="w-[20%] whitespace-nowrap text-right">
                                                    TOTAL
                                                </th>
                                            </tr>
                                            </thead>
                                    
                                        <tbody id = "service-list-body">
                                            {services_html}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                            """),
                ),
                # -------- KITS --------
                Div(
                    HTML('<h3 class="text-xl font-semibold text-gray-700 mb-4">Kits Selecionados</h3>'),
                    HTML(f"""
                            <div class="mb-6 rounded-lg shadow-md shadow-gray-300/50 overflow-hidden">
                                <div class="overflow-x-auto">
                                    <table class="table table-compact table-fixed w-full">
                                        <thead class="bg-primary text-primary-content">
                                            <tr>
                                                <th class="w-[40%] whitespace-nowrap text-left">
                                                NOME
                                                </th>
                                            
                                                <th class="w-[10%] whitespace-nowrap text-center">
                                                QTD.
                                                </th>
                                            
                                                <th class="w-[15%] whitespace-nowrap text-center">
                                                PRODUTOS
                                                </th>
                                            
                                                <th class="w-[15%] whitespace-nowrap text-center">
                                                SERVIÇOS
                                                </th>
                                            
                                                <th class="w-[20%] whitespace-nowrap text-center">
                                                AÇÕES
                                                </th>
                                            </tr>
                                        </thead>
                                    
                                        <tbody id="kit-list-body">
                                        {kits_html}
                                        </tbody>
                                    </table>
                                </div>

                            </div>
                            """),
                ),
                css_class="col-span-12 lg:col-span-7",
            ),
            # Div(css_class="hidden lg:block lg:col-span-0"),
            # ===== COLUNA DIREITA =====
            Div(
                Div(
                    HTML(f"""
                                    <div class="w-full mb-4 py-3 px-4 rounded-lg flex items-center justify-between border-l-4 {status_class} bg-opacity-20">
                                        <span class="font-bold text-sm uppercase tracking-wider">Status do Orçamento</span>
                                        <span class="badge {status_class} font-bold p-3">{status_label}</span>
                                    </div>
                                    """),
                ),
                Div(
                    HTML('<h4 class="font-bold text-lg mb-2 border-b">Prazos</h4>'),
                    Div(
                        Field("customer_agreed_departure_at", wrapper_class="col-span-12"),
                        Field("service_expected_completion_at", wrapper_class="col-span-12"),
                        css_class="grid grid-cols-1 gap-4 mb-8",
                    ),
                    css_class="p-4 bg-base-200/50 rounded-lg",
                ),
                # -------- PDF (RESTORED 1:1) --------
                Div(
                    HTML('<h4 class="font-bold text-lg mb-2 border-b">PDF</h4>'),
                    HTML(f"""
                            <div class="grid grid-cols-12 gap-3 text-center mb-8">
                                <button type="button" class="btn btn-success col-span-4" data-allow-locked="1"
                                    onclick="openBudgetPdfModal({{ url: '{default_pdf_url}', downloadUrl: '{default_pdf_download_url}', showSignatureBtn: true, signatureButtonLabel: '{signature_button_label}', isSignatureResend: {"true" if is_signature_resend else "false"}, signatureBlocked: {signature_blocked_json}, signatureBlockedReason: {signature_blocked_reason_json}, showPdfVariantToggle: {"true" if can_toggle_signed_pdf else "false"}, pdfVariant: '', signedPdfUrl: '{signed_pdf_url}', basePdfUrl: '{base_pdf_url}', signedDownloadUrl: '{signed_pdf_download_url}', baseDownloadUrl: '{base_pdf_download_url}' }})">
                                    PDF Cliente
                                </button>

                                <button type="button" class="btn btn-success col-span-4" data-allow-locked="1"
                                    onclick="openBudgetPdfModal({{ url: '{reverse("budget:visualizar_pdf_gestor", args=[budget.pk])}', showSignatureBtn: false }})">
                                    PDF Gestor
                                </button>

                                <button type="button" class="btn btn-success col-span-4" data-allow-locked="1"
                                    onclick="openBudgetPdfModal({{ url: '{reverse("budget:visualizar_pdf_mecanico", args=[budget.pk])}', showSignatureBtn: false }})">
                                    PDF Mecânico
                                </button>
                            </div>
                            """),
                    css_class="p-4 bg-base-200/50 rounded-lg",
                ),
                # -------- OBSERVAÇÕES DO ORÇAMENTO --------
                Div(
                    HTML('<h4 class="font-bold text-lg mb-2 border-b">Observação</h4>'),
                    HTML(f"""
                                                    <div class="flex flex-col gap-3 mb-8">
                                                        <textarea
                                                            class="textarea textarea-bordered w-full"
                                                            rows="4"
                                                            id="budget-observation"
                                                            placeholder="Digite uma observação para o PDF..."
                                                        >{saved_observation_html}</textarea>

                                                        <div class="flex justify-end items-center">
                                                            <button type="button"
                                                                    class="btn btn-sm btn-primary"
                                                                    onclick="saveObservation({budget.pk})">
                                                                Salvar observação
                                                            </button>
                                                        </div>
                                                    </div>
                                                    """),
                    css_class="p-4 bg-base-200/50 rounded-lg",
                ),
                # -------- APROVAÇÃO --------
                Div(
                    HTML(cancellation_reason_html),
                    HTML(reopen_history_html),
                    HTML('<h4 class="font-bold text-lg mb-2 border-b">Aprovação</h4>'),
                    HTML(f"""
                            <div class="grid grid-cols-12 gap-3">
                                <button type="button"
                                    class="btn btn-error col-span-4 {cancel_button_class}"
                                    {cancel_button_attrs}>
                                    Cancelar
                                </button>

                                <button type="button"
                                    class="btn col-span-4 {approval_button_class}"
                                    {approval_button_attrs}>
                                    Aprovar
                                </button>

                                <button type="button"
                                    class="btn btn-warning col-span-4 {reject_button_class}"
                                    {reject_button_attrs}>
                                    Reprovar
                                </button>

                                {f"<button type='button' class='btn btn-warning col-span-12' data-allow-locked='1' onclick='updateBudgetStatus({budget.pk}, &#39;reopen&#39;, {str(bool(form.request and form.workshop and has_workshop_perm(user=form.request.user, workshop=form.workshop, app_label='budget', model='budget', codename='add_budget', request=form.request))).lower()})'>Reabrir Orçamento</button>" if budget.is_status_locked else ""}

                                {f"<div id='reopen-budget-form' class='col-span-12 mt-2 space-y-3 rounded-xl border border-warning/40 bg-warning/10 p-4 hidden' data-allow-locked='1'><p class='text-sm text-base-content/80' data-allow-locked='1'>Informe a justificativa da reabertura antes de concluir esta ação.</p><textarea id='reopen-reason-input' class='textarea textarea-bordered w-full' rows='4' placeholder='Explique por que este orçamento deve ser reaberto...' data-allow-locked='1'></textarea><div class='flex flex-wrap gap-3' data-allow-locked='1'><button type='button' class='btn btn-warning' data-allow-locked='1' onclick='confirmReopenBudgetStatus({budget.pk})'>Confirmar reabertura</button><button type='button' class='btn btn-ghost' data-allow-locked='1' onclick='cancelReopenBudgetStatus()'>Fechar</button></div></div>" if budget.is_status_locked else ""}
                            </div>
                            """),
                    css_class="p-4 bg-base-200/50 rounded-lg",
                ),
                css_class="col-span-12 lg:col-span-5 sticky top-4",
            ),
            css_class="grid grid-cols-1 lg:grid-cols-12 gap-8",
        ),
        # =========================
        # MODAL DE PDF (RESTAURADO)
        # =========================
        HTML("""
                <dialog id="pdfModal"
                        class="modal"
                        x-data="{ pdfUrl: '', pdfDownloadUrl: '', showSignatureBtn: false, signatureButtonLabel: 'Enviar para Assinatura', isSignatureResend: false, signatureBlocked: false, signatureBlockedReason: '', showPdfVariantToggle: false, pdfVariant: 'signed', pdfToggleLabel: 'Ver não assinado', signedPdfUrl: '', basePdfUrl: '', signedDownloadUrl: '', baseDownloadUrl: '', togglePdfVariant() { if (!this.showPdfVariantToggle) return; const shouldShowBase = this.pdfVariant === 'signed'; this.pdfVariant = shouldShowBase ? 'base' : 'signed'; this.pdfUrl = shouldShowBase ? this.basePdfUrl : this.signedPdfUrl; this.pdfDownloadUrl = shouldShowBase ? this.baseDownloadUrl : this.signedDownloadUrl; this.pdfToggleLabel = shouldShowBase ? 'Ver assinado' : 'Ver não assinado'; } }"
                        @open-pdf-modal.window="pdfUrl = $event.detail.url; pdfDownloadUrl = $event.detail.downloadUrl || ''; showSignatureBtn = $event.detail.showSignatureBtn || false; signatureButtonLabel = $event.detail.signatureButtonLabel || 'Enviar para Assinatura'; isSignatureResend = $event.detail.isSignatureResend || false; signatureBlocked = $event.detail.signatureBlocked || false; signatureBlockedReason = $event.detail.signatureBlockedReason || ''; showPdfVariantToggle = $event.detail.showPdfVariantToggle || false; pdfVariant = $event.detail.pdfVariant || 'signed'; pdfToggleLabel = pdfVariant === 'base' ? 'Ver assinado' : 'Ver não assinado'; signedPdfUrl = $event.detail.signedPdfUrl || ''; basePdfUrl = $event.detail.basePdfUrl || ''; signedDownloadUrl = $event.detail.signedDownloadUrl || ''; baseDownloadUrl = $event.detail.baseDownloadUrl || ''; $el.showModal()">

                  <div class="modal-box max-w-5xl w-full h-[90vh] p-0 flex flex-col">

                    <div class="flex items-center justify-between px-6 py-4 border-b bg-base-200">
                        <h3 class="text-xl font-bold flex items-center gap-2">
                            <span class="material-icons">description</span>
                            Visualização do PDF
                        </h3>

                        <div class="flex gap-2">
                            <button type="button"
                                    class="btn btn-sm"
                                    id="send-signature-btn"
                                    x-show="showSignatureBtn"
                                    data-url="{% url 'budget:send_signature' form.instance.pk %}"
                                    :data-is-resend="isSignatureResend ? 'true' : 'false'"
                                    :data-blocked="signatureBlocked ? 'true' : 'false'"
                                    :data-blocked-reason="signatureBlockedReason"
                                    :class="signatureBlocked ? 'btn-neutral opacity-60 pointer-events-none' : 'btn-primary'"
                                    :aria-disabled="signatureBlocked ? 'true' : 'false'"
                                    :title="signatureBlockedReason"
                                    onclick="if (this.dataset.blocked === 'true') { showBlockedStep6Action(this.dataset.blockedReason); return; } sendBudgetForSignature(this)">
                                <span class="loading loading-spinner loading-xs hidden" id="send-signature-spinner"></span>
                                <span id="send-signature-label" x-text="signatureButtonLabel"></span>
                            </button>

                            <button type="button"
                                    class="btn btn-sm btn-outline"
                                    x-show="showPdfVariantToggle"
                                    @click="togglePdfVariant()"
                                    x-text="pdfToggleLabel">
                            </button>

                            <button type="button"
                                    class="btn btn-sm btn-success"
                                    data-allow-locked="1"
                                    onclick="
                                      const frame = document.querySelector('#pdfModal iframe');
                                      const downloadUrl = frame ? frame.dataset.downloadUrl : '';
                                      if (downloadUrl) {
                                          window.open(downloadUrl, '_blank');
                                      } else if (frame && frame.contentWindow) {
                                          frame.contentWindow.focus();
                                          frame.contentWindow.print();
                                      }
                                    ">
                                Baixar PDF
                            </button>

                            <button type="button"
                                    class="btn btn-sm"
                                    data-allow-locked="1"
                                    onclick="document.getElementById('pdfModal').close()">
                                Fechar
                            </button>
                        </div>
                    </div>

                    <div class="flex-1 bg-gray-100">
                        <template x-if="pdfUrl">
                            <iframe :src="pdfUrl"
                                    :data-download-url="pdfDownloadUrl"
                                    class="w-full h-full"
                                    frameborder="0"></iframe>
                        </template>
                    </div>

                  </div>

                  <form method="dialog" class="modal-backdrop">
                    <button>close</button>
                  </form>
                </dialog>
                """),
        HTML("""
                    <dialog
                        id="kitModal"
                        class="modal"
                        onclick="if(event.target === this) closeKitModal()"
                    >
                      <div class="modal-box max-w-5xl w-full max-h-[75vh] p-0 flex flex-col">

                        <!-- HEADER -->
                        <div class="flex items-center justify-between px-8 py-5 border-b bg-base-200">
                            <div class="flex items-center gap-4">
                                <div class="p-3 rounded-lg bg-primary/10">
                                    <span class="material-icons text-primary text-3xl">inventory_2</span>
                                </div>

                                <div>
                                    <h3 class="text-2xl font-bold leading-tight" id="kit-modal-title"></h3>
                                    <span class="badge badge-primary badge-outline mt-1">
                                        Kit de Serviços
                                    </span>
                                </div>
                            </div>
                        </div>

                        <!-- BODY -->
                        <div class="p-8 grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 overflow-y-auto">

                            <!-- PRODUTOS (CARD VERTICAL) -->
                            <div class="card bg-base-100 shadow-md border lg:col-span-1">
                                <div class="card-body gap-4">
                                    <div class="flex items-center justify-between">
                                        <h4 class="font-semibold text-base flex items-center gap-2">
                                            <span class="material-icons text-info">build</span>
                                            Produtos
                                        </h4>
                                        <span id="kit-products-count" class="badge badge-info"></span>
                                    </div>

                                    <div class="divider my-1"></div>

                                    <ul
                                        id="kit-modal-products"
                                        class="flex flex-col gap-3 text-sm
                                             max-h-64 overflow-y-auto pr-2
                                             overflow-x-hidden"
                                    ></ul>
                                </div>
                            </div>

                            <!-- SERVIÇOS (CARD VERTICAL) -->
                            <div class="card bg-base-100 shadow-md border lg:col-span-1">
                                <div class="card-body gap-4">
                                    <div class="flex items-center justify-between">
                                        <h4 class="font-semibold text-base flex items-center gap-2">
                                            <span class="material-icons text-success">engineering</span>
                                            Serviços
                                        </h4>
                                        <span id="kit-services-count" class="badge badge-success"></span>
                                    </div>

                                    <div class="divider my-1"></div>

                                    <ul
                                        id="kit-modal-services"
                                        class="flex flex-col gap-3 text-sm
                                             max-h-64 overflow-y-auto pr-2
                                             overflow-x-hidden"
                                    ></ul>
                                </div>
                            </div>

                            <!-- COLUNA DE CONTEXTO (PROFISSIONAL) -->
                            <div class="card bg-base-200/60 border lg:col-span-1">
                                <div class="card-body gap-4">
                                    <h4 class="font-semibold text-base">
                                        Informações do Kit
                                    </h4>

                                    <div class="flex flex-col gap-3 text-sm text-base-content/80">
                                        <div class="flex justify-between">
                                            <span>Total de Produtos</span>
                                            <strong id="kit-products-count-side"></strong>
                                        </div>

                                        <div class="flex justify-between">
                                            <span>Total de Serviços</span>
                                            <strong id="kit-services-count-side"></strong>
                                        </div>
                                    </div>

                                    <div class="divider"></div>

                                    <p class="text-xs text-base-content/60 leading-relaxed">
                                        Este kit agrupa produtos e serviços vinculados ao orçamento,
                                        facilitando a visualização e conferência antes da aprovação.
                                    </p>
                                </div>
                            </div>

                        </div>

                        <!-- FOOTER -->
                        <div class="flex justify-end px-8 py-5 border-t bg-base-200">
                            <button
                                type="button"
                                class="btn btn-primary"
                                onclick="closeKitModal()"
                            >
                                <span class="material-icons text-sm">close</span>
                                Fechar
                            </button>
                        </div>

                      </div>
                    </dialog>
                """),
    )
