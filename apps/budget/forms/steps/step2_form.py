# ruff: noqa: F403,F405
import json

from django.urls import reverse

from apps.budget.models import SignatureStatus
from apps.terms.models import BudgetTermSigning, TermTemplateType
from apps.terms.presenters.budget_term_modal import resolve_budget_term_modal_urls
from apps.terms.selectors import get_active_term_templates, get_default_term_template, update_budget_term_template

from .base import BudgetStepBaseForm
from .common import *


class BudgetStep2Form(BudgetStepBaseForm):
    class Meta:
        model = Budget
        fields = ["problem_description", "notes"]
        widgets = {
            "problem_description": TextareaInput(
                attrs={
                    "rows": 4,
                    "cols": 40,
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none; height: 40vh; min-height: 40vh; max-height: 40vh; overflow-y: auto;",
                }
            ),
            "notes": TextareaInput(
                attrs={
                    "rows": 4,
                    "cols": 40,
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none;",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.investigative_questions = InvestigativeQuestion.objects.filter(workshop=self.workshop, is_active=True).order_by("order")

        responses_by_question_id: dict[int, str] = {}
        if self.instance.pk:
            responses_by_question_id = {response.question_id: response.response for response in InvestigativeResponse.objects.filter(budget=self.instance).only("question_id", "response")}

        self.question_field_names = []
        for q in self.investigative_questions:
            field_name = f"question_{q.id}"
            self.question_field_names.append(field_name)
            # Valor inicial (se estiver editando)
            initial_value = responses_by_question_id.get(q.id, "")
            # Definir o tipo de campo
            if q.response_type == InvestigativeQuestion.ResponseType.BOOLEAN:
                choices = [("", "Selecione..."), ("Sim", "Sim"), ("Não", "Não")]
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices, required=False, initial=initial_value, widget=SearchableSelectInput(choices=choices))
            elif q.response_type == InvestigativeQuestion.ResponseType.SCALE:
                display_id = f"display_{field_name}"
                self.fields[field_name] = forms.IntegerField(
                    label=q.text,
                    min_value=1,
                    max_value=10,
                    required=False,
                    initial=initial_value or 5,
                    widget=forms.NumberInput(attrs={"class": "range range-primary w-full", "type": "range", "step": "1", "min": "1", "max": "10", "oninput": f"document.getElementById('{display_id}').innerText = this.value"}),
                )
                self.fields[field_name].help_text = f'Valor selecionado: <span id="{display_id}" class="font-bold text-xs">{initial_value or 5}</span>'
            elif q.response_type == InvestigativeQuestion.ResponseType.MULTIPLE_CHOICE:
                choices = [(opt, opt) for opt in q.options]
                choices1 = [("", "Selecione...")] + choices
                self.fields[field_name] = forms.ChoiceField(label=q.text, choices=choices1, required=False, initial=initial_value, widget=SearchableSelectInput(choices=choices1))
            else:  # FREE_TEXT
                self.fields[field_name] = forms.CharField(label=q.text, required=False, initial=initial_value, widget=TextInput())

        self.term_templates = get_active_term_templates(workshop=self.workshop, template_type=TermTemplateType.VEHICLE_RECEIPT)
        term_choices = [("", "Selecione um termo...")] + [(str(template.pk), template.name) for template in self.term_templates]
        signing = None
        if self.instance.pk:
            signing = BudgetTermSigning.objects.filter(budget=self.instance).select_related("term_template").first()
        initial_term = ""
        if signing is not None:
            initial_term = str(signing.term_template_id)
        elif self.term_templates:
            default_template = get_default_term_template(workshop=self.workshop, template_type=TermTemplateType.VEHICLE_RECEIPT)
            if default_template is not None:
                initial_term = str(default_template.pk)

        self.fields["term_template"] = forms.ChoiceField(
            label="Termo de recebimento",
            choices=term_choices,
            required=False,
            initial=initial_term,
            widget=SearchableSelectInput(choices=term_choices),
        )
        self.term_signing = signing
        self.term_signature_locked = bool(signing and signing.is_signature_locked)
        if self.term_signature_locked and signing is not None:
            self.fields["term_template"].disabled = True

        # 3. Configurar Layout dinâmico do Crispy
        question_layout_fields = [Field(name, wrapper_class="mb-4") for name in self.question_field_names]

        self.helper = FormHelper()
        self.helper.form_tag = False

        term_section_layout = []
        if self.instance.pk:
            status_label = "Não enviado"
            status_class = "badge-ghost"
            if signing is not None:
                if signing.signature_request_status == SignatureStatus.APPROVED:
                    status_label = "Assinado"
                    status_class = "badge-success"
                elif signing.signature_request_status == SignatureStatus.SENT:
                    status_label = "Enviado"
                    status_class = "badge-info"
                elif signing.signature_request_status == SignatureStatus.FAILED:
                    status_label = "Falha no envio"
                    status_class = "badge-error"
                elif signing.signature_request_status == SignatureStatus.SENDING:
                    status_label = "Enviando"
                    status_class = "badge-warning"

            pdf_base_path = reverse("terms:budget_term_pdf", kwargs={"budget_id": self.instance.pk})
            send_url = reverse("terms:budget_term_send_signature", kwargs={"budget_id": self.instance.pk})
            terms_create_url = reverse("terms:term_template_create")

            selected_term_id = signing.term_template_id if signing else None
            if selected_term_id is None and initial_term:
                try:
                    selected_term_id = int(initial_term)
                except (ValueError, TypeError):
                    selected_term_id = None

            modal_urls = resolve_budget_term_modal_urls(
                budget_id=self.instance.pk,
                signing=signing,
                term_template_id=selected_term_id,
                request=self.request,
            )
            signature_button_label = "Reenviar Documento" if modal_urls.is_signature_resend else "Enviar para Assinatura"
            modal_urls_json = json.dumps(
                {
                    "canToggleSignedPdf": modal_urls.can_toggle_signed_pdf,
                    "isSignatureResend": modal_urls.is_signature_resend,
                    "signatureBlocked": modal_urls.signature_blocked or self.term_signature_locked,
                    "initialPdfVariant": modal_urls.initial_pdf_variant,
                    "signedPdfUrl": modal_urls.signed_pdf_url,
                    "signedDownloadUrl": modal_urls.signed_download_url,
                    "pdfBasePath": pdf_base_path,
                    "sendUrl": send_url,
                    "signatureButtonLabel": signature_button_label,
                }
            )

            term_section_layout = [
                Div(
                    HTML('<h3 class="text-2xl font-bold col-span-12">Termo de Recebimento</h3>'),
                    HTML(
                        f"""
                        <div class="col-span-12 rounded-box border border-base-300 p-4 bg-base-200/40">
                            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
                                <span class="badge {status_class}">{status_label}</span>
                                <a href="{terms_create_url}" target="_blank" class="btn btn-primary btn-sm gap-2">
                                    <span class="material-icons text-base">add</span>
                                    Novo termo
                                </a>
                            </div>
                            <div class="grid grid-cols-12 gap-4 items-end">
                                <div class="col-span-12 lg:col-span-8">
                        """
                    ),
                    Field("term_template", wrapper_class="mb-0"),
                    HTML(
                        f"""
                                </div>
                                <div class="col-span-12 lg:col-span-4 flex flex-wrap gap-2">
                                    <button type="button" class="btn btn-primary btn-sm gap-2" id="budget-term-preview-btn" {"disabled" if not self.term_templates else ""}>
                                        <span class="material-icons text-base">visibility</span>
                                        Visualizar PDF
                                    </button>
                                </div>
                            </div>
                            {"<p class='text-sm text-base-content/70 mt-3'>O termo selecionado foi bloqueado após o envio para assinatura.</p>" if self.term_signature_locked else ""}
                            {"<div class='alert alert-warning mt-3'><span>Cadastre ao menos um termo de recebimento ativo para visualizar ou enviar ao cliente.</span></div>" if not self.term_templates else ""}
                        </div>
                        <dialog id="budgetTermPdfModal"
                                class="modal"
                                x-data="{{ pdfUrl: '', pdfDownloadUrl: '', showSignatureBtn: true, signatureButtonLabel: 'Enviar para Assinatura', isSignatureResend: false, signatureBlocked: false, showPdfVariantToggle: false, pdfVariant: 'signed', pdfToggleLabel: 'Ver não assinado', signedPdfUrl: '', basePdfUrl: '', signedDownloadUrl: '', baseDownloadUrl: '', togglePdfVariant() {{ if (!this.showPdfVariantToggle) return; const shouldShowBase = this.pdfVariant === 'signed'; this.pdfVariant = shouldShowBase ? 'base' : 'signed'; this.pdfUrl = shouldShowBase ? this.basePdfUrl : this.signedPdfUrl; this.pdfDownloadUrl = shouldShowBase ? this.baseDownloadUrl : this.signedDownloadUrl; this.pdfToggleLabel = shouldShowBase ? 'Ver assinado' : 'Ver não assinado'; }} }}"
                                @open-budget-term-pdf-modal.window="pdfUrl = $event.detail.url; pdfDownloadUrl = $event.detail.downloadUrl || ''; showSignatureBtn = $event.detail.showSignatureBtn !== false; signatureButtonLabel = $event.detail.signatureButtonLabel || 'Enviar para Assinatura'; isSignatureResend = $event.detail.isSignatureResend || false; signatureBlocked = $event.detail.signatureBlocked || false; showPdfVariantToggle = $event.detail.showPdfVariantToggle || false; pdfVariant = $event.detail.pdfVariant || 'signed'; pdfToggleLabel = pdfVariant === 'base' ? 'Ver assinado' : 'Ver não assinado'; signedPdfUrl = $event.detail.signedPdfUrl || ''; basePdfUrl = $event.detail.basePdfUrl || ''; signedDownloadUrl = $event.detail.signedDownloadUrl || ''; baseDownloadUrl = $event.detail.baseDownloadUrl || ''; $el.showModal()">
                            <div class="modal-box max-w-5xl w-full h-[90vh] p-0 flex flex-col">
                                <div class="flex items-center justify-between px-6 py-4 border-b bg-base-200">
                                    <h3 class="text-xl font-bold flex items-center gap-2">
                                        <span class="material-icons">description</span>
                                        Termo de Recebimento
                                    </h3>
                                    <div class="flex flex-wrap gap-2">
                                        <button type="button"
                                                class="btn btn-sm"
                                                id="budget-term-send-btn"
                                                x-show="showSignatureBtn"
                                                data-url="{send_url}"
                                                :data-is-resend="isSignatureResend ? 'true' : 'false'"
                                                :data-blocked="signatureBlocked ? 'true' : 'false'"
                                                :class="signatureBlocked ? 'btn-neutral opacity-60 pointer-events-none' : 'btn-primary'"
                                                :aria-disabled="signatureBlocked ? 'true' : 'false'"
                                                onclick="sendBudgetTermForSignature(this)">
                                            <span class="loading loading-spinner loading-xs hidden" id="budget-term-send-spinner"></span>
                                            <span id="budget-term-send-label" x-text="signatureButtonLabel"></span>
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
                                                onclick="const frame = document.querySelector('#budgetTermPdfModal iframe'); const downloadUrl = frame ? frame.dataset.downloadUrl : ''; if (downloadUrl) {{ window.open(downloadUrl, '_blank'); }}">
                                            Baixar PDF
                                        </button>
                                        <button type="button" class="btn btn-sm" data-allow-locked="1" onclick="document.getElementById('budgetTermPdfModal').close()">
                                            Cancelar
                                        </button>
                                    </div>
                                </div>
                                <div class="flex-1 bg-gray-100">
                                    <template x-if="pdfUrl">
                                        <iframe :src="pdfUrl"
                                                :data-download-url="pdfDownloadUrl"
                                                class="w-full h-full"
                                                frameborder="0"
                                                title="Pré-visualização do termo de recebimento"></iframe>
                                    </template>
                                </div>
                            </div>
                            <form method="dialog" class="modal-backdrop bg-black/50">
                                <button>close</button>
                            </form>
                        </dialog>
                        <script>
                        (function () {{
                            const modalConfig = {modal_urls_json};
                            const previewBtn = document.getElementById('budget-term-preview-btn');
                            const termSelect = document.getElementById('id_term_template');
                            if (!previewBtn || !termSelect) return;

                            function buildTermPdfUrls(termId) {{
                                const query = termId ? `?term_template=${{encodeURIComponent(termId)}}` : '';
                                const downloadQuery = termId ? `?download=1&term_template=${{encodeURIComponent(termId)}}` : '?download=1';
                                return {{
                                    basePdfUrl: `${{modalConfig.pdfBasePath}}${{query}}`,
                                    baseDownloadUrl: `${{modalConfig.pdfBasePath}}${{downloadQuery}}`,
                                }};
                            }}

                            previewBtn.addEventListener('click', function () {{
                                const termId = termSelect.value;
                                if (!termId) {{
                                    window.dispatchEvent(new CustomEvent('showToast', {{ detail: {{ message: 'Selecione um termo para visualizar.', type: 'warning' }} }}));
                                    return;
                                }}
                                const urls = buildTermPdfUrls(termId);
                                const canToggle = Boolean(modalConfig.canToggleSignedPdf && modalConfig.signedPdfUrl);
                                const initialVariant = canToggle ? 'signed' : 'base';
                                window.dispatchEvent(new CustomEvent('open-budget-term-pdf-modal', {{
                                    detail: {{
                                        url: canToggle ? modalConfig.signedPdfUrl : urls.basePdfUrl,
                                        downloadUrl: canToggle ? modalConfig.signedDownloadUrl : urls.baseDownloadUrl,
                                        showSignatureBtn: true,
                                        signatureButtonLabel: modalConfig.signatureButtonLabel,
                                        isSignatureResend: modalConfig.isSignatureResend,
                                        signatureBlocked: modalConfig.signatureBlocked,
                                        showPdfVariantToggle: canToggle,
                                        pdfVariant: initialVariant,
                                        signedPdfUrl: modalConfig.signedPdfUrl,
                                        basePdfUrl: urls.basePdfUrl,
                                        signedDownloadUrl: modalConfig.signedDownloadUrl,
                                        baseDownloadUrl: urls.baseDownloadUrl,
                                    }},
                                }}));
                            }});
                        }})();

                        async function sendBudgetTermForSignature(buttonEl) {{
                            const btn = buttonEl || document.getElementById('budget-term-send-btn');
                            const label = document.getElementById('budget-term-send-label');
                            const spinner = document.getElementById('budget-term-send-spinner');
                            const termSelect = document.getElementById('id_term_template');
                            const endpoint = btn ? btn.dataset.url : '';
                            const isResend = btn ? btn.dataset.isResend === 'true' : false;
                            const defaultLabel = isResend ? 'Reenviar Documento' : 'Enviar para Assinatura';

                            if (btn && btn.dataset.blocked === 'true') {{
                                return;
                            }}

                            const termId = termSelect ? termSelect.value : '';
                            if (!termId) {{
                                window.dispatchEvent(new CustomEvent('showToast', {{ detail: {{ message: 'Selecione um termo antes de enviar.', type: 'warning' }} }}));
                                return;
                            }}

                            if (isResend) {{
                                const confirmed = await customConfirm('Você tem certeza que deseja reenviar este documento para assinatura?');
                                if (!confirmed) {{
                                    if (label) label.textContent = defaultLabel;
                                    return;
                                }}
                            }}

                            if (btn) btn.disabled = true;
                            if (label) label.textContent = 'Enviando...';
                            if (spinner) spinner.classList.remove('hidden');

                            try {{
                                const body = new FormData();
                                body.append('term_template', termId);
                                const response = await fetch(endpoint, {{
                                    method: 'POST',
                                    headers: {{
                                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
                                        'X-Requested-With': 'XMLHttpRequest',
                                    }},
                                    body,
                                }});
                                const data = await response.json().catch(() => ({{}}));
                                if (!response.ok || !data.ok) {{
                                    throw new Error(data.error || data.message || 'Falha ao enviar termo para assinatura.');
                                }}
                                window.dispatchEvent(new CustomEvent('showToast', {{
                                    detail: {{ message: data.message || 'Termo enviado para assinatura do cliente.', type: 'success' }}
                                }}));
                                setTimeout(() => window.location.reload(), 900);
                            }} catch (error) {{
                                window.dispatchEvent(new CustomEvent('showToast', {{
                                    detail: {{ message: error && error.message ? error.message : 'Falha ao enviar termo para assinatura.', type: 'error' }}
                                }}));
                            }} finally {{
                                if (btn) btn.disabled = false;
                                if (label) label.textContent = defaultLabel;
                                if (spinner) spinner.classList.add('hidden');
                            }}
                        }}
                        </script>
                        """
                    ),
                    css_class="grid grid-cols-12 gap-6 mt-8",
                )
            ]
        else:
            term_section_layout = [
                HTML('<div class="col-span-12 alert alert-info mt-6">Salve a etapa 1 para configurar o termo de recebimento.</div>')
            ]

        self.helper.layout = Layout(
            Div(
                HTML('<h3 class="text-2xl font-bold col-span-12">Relato do Cliente</h3>'),
                # Descrição do Problema
                Div(Field("problem_description", wrapper_class="flex flex-col h-full", css_class="flex-1"), css_class="col-span-12 lg:col-span-6 flex flex-col"),
                # Perguntas Investigativas
                Div(
                    HTML('<h5 class="font-bold mb-2">Perguntas Investigativas</h5>'),
                    Div(*question_layout_fields, css_class="border bg-base-200 px-4 py-2 rounded-lg pr-4 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-400", style="border-color: var(--color-input-ring); height: 40vh; min-height: 40vh; max-height: 40vh;"),
                    css_class="col-span-12 lg:col-span-6",
                ),
                # Observações
                Div(Field("notes", wrapper_class="w-full", css_class="bg-base-200"), css_class="col-span-12"),
                css_class="budget-step2-client-report grid grid-cols-12 gap-6",
            ),
            *term_section_layout,
        )

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Salvar as respostas vinculadas
        for field_name in self.question_field_names:
            question_id = field_name.split("_")[1]
            response_text = self.cleaned_data.get(field_name)

            if response_text:
                InvestigativeResponse.objects.update_or_create(budget=budget, question_id=question_id, defaults={"workshop": self.workshop, "response": str(response_text)})

        term_template_value = self.cleaned_data.get("term_template")
        if term_template_value and not self.term_signature_locked:
            try:
                update_budget_term_template(budget=budget, term_template_id=int(term_template_value))
            except (ValueError, TypeError):
                pass
        return budget

    def clean_problem_description(self):
        value = self.cleaned_data.get("problem_description")
        return sentence_case(value) if value else value

    def clean_notes(self):
        value = self.cleaned_data.get("notes")
        return sentence_case(value) if value else value
