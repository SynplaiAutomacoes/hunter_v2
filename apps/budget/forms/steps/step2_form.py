# ruff: noqa: F403,F405
from django.urls import reverse

from apps.budget.models import SignatureStatus
from apps.terms.models import BudgetTermSigning, TermTemplateType
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

            preview_url = reverse("terms:budget_term_preview", kwargs={"budget_id": self.instance.pk})
            send_url = reverse("terms:budget_term_send_signature", kwargs={"budget_id": self.instance.pk})
            terms_list_url = reverse("terms:term_template_list")

            term_section_layout = [
                Div(
                    HTML('<h3 class="text-2xl font-bold col-span-12">Termo de Recebimento</h3>'),
                    HTML(
                        f"""
                        <div class="col-span-12 rounded-box border border-base-300 p-4 bg-base-200/40">
                            <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
                                <span class="badge {status_class}">{status_label}</span>
                                <a href="{terms_list_url}" target="_blank" class="link link-primary text-sm">Cadastrar novo termo</a>
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
                                    <button type="button" class="btn btn-outline btn-sm" id="budget-term-preview-btn" data-base-url="{preview_url}">Visualizar</button>
                                    <button type="button" class="btn btn-primary btn-sm" id="budget-term-send-btn" data-url="{send_url}" {"disabled" if self.term_signature_locked or not self.term_templates else ""}>Enviar para assinatura</button>
                                </div>
                            </div>
                            {"<p class='text-sm text-base-content/70 mt-3'>O termo selecionado foi bloqueado após o envio para assinatura.</p>" if self.term_signature_locked else ""}
                            {"<div class='alert alert-warning mt-3'><span>Cadastre ao menos um termo de recebimento ativo para enviar ao cliente.</span></div>" if not self.term_templates else ""}
                        </div>
                        <dialog id="budget-term-preview-modal" class="modal">
                            <div class="modal-box w-11/12 max-w-5xl">
                                <h3 class="font-bold text-lg mb-3">Pré-visualização do termo</h3>
                                <iframe id="budget-term-preview-frame" class="w-full min-h-[70vh] border border-base-300 rounded-box bg-white" title="Pré-visualização do termo"></iframe>
                                <div class="modal-action">
                                    <form method="dialog"><button class="btn">Fechar</button></form>
                                </div>
                            </div>
                            <form method="dialog" class="modal-backdrop"><button>close</button></form>
                        </dialog>
                        <script>
                        (function () {{
                            const previewBtn = document.getElementById('budget-term-preview-btn');
                            const sendBtn = document.getElementById('budget-term-send-btn');
                            const termSelect = document.getElementById('id_term_template');
                            const previewModal = document.getElementById('budget-term-preview-modal');
                            const previewFrame = document.getElementById('budget-term-preview-frame');
                            if (!previewBtn || !termSelect) return;

                            previewBtn.addEventListener('click', function () {{
                                const termId = termSelect.value;
                                if (!termId) {{
                                    window.dispatchEvent(new CustomEvent('showToast', {{ detail: {{ message: 'Selecione um termo para visualizar.', type: 'warning' }} }}));
                                    return;
                                }}
                                const url = previewBtn.dataset.baseUrl + '?term_template=' + encodeURIComponent(termId);
                                previewFrame.src = url;
                                previewModal.showModal();
                            }});

                            if (!sendBtn || sendBtn.disabled) return;
                            sendBtn.addEventListener('click', async function () {{
                                const termId = termSelect.value;
                                if (!termId) {{
                                    window.dispatchEvent(new CustomEvent('showToast', {{ detail: {{ message: 'Selecione um termo antes de enviar.', type: 'warning' }} }}));
                                    return;
                                }}
                                sendBtn.disabled = true;
                                try {{
                                    const body = new FormData();
                                    body.append('term_template', termId);
                                    const response = await fetch(sendBtn.dataset.url, {{
                                        method: 'POST',
                                        headers: {{ 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value }},
                                        body,
                                    }});
                                    const data = await response.json();
                                    window.dispatchEvent(new CustomEvent('showToast', {{
                                        detail: {{ message: data.message || data.error || 'Operação concluída.', type: data.ok ? 'success' : 'error' }}
                                    }}));
                                    if (data.ok) window.location.reload();
                                }} catch (_error) {{
                                    window.dispatchEvent(new CustomEvent('showToast', {{ detail: {{ message: 'Falha ao enviar termo para assinatura.', type: 'error' }} }}));
                                }} finally {{
                                    sendBtn.disabled = false;
                                }}
                            }});
                        }})();
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
