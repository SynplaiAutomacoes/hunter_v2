from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Checklist, ChecklistItem
from apps.core.widgets import TextInput, SearchableSelectInput
from ..workshops.models.workshops import Workshop


class ChecklistForm(forms.ModelForm):
    imported_pdf = forms.FileField(
        required=False,
        label="Arquivo PDF",
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf", "class": "file-input file-input-bordered w-full", "id": "imported-pdf"}),
    )

    class Meta:
        model = Checklist
        fields = ["name", "checklist_type", "source"]
        widgets = {
            "name": TextInput(),
            "checklist_type": SearchableSelectInput(choices=[(str(value), str(label)) for value, label in Checklist.ChecklistType.choices]),
            "source": forms.HiddenInput(attrs={"id": "id_source"}),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.attrs = {"enctype": "multipart/form-data"}

        cancel_url = reverse("checklist:checklist_list")
        self.fields["source"].initial = self.instance.source if self.instance and self.instance.pk else Checklist.ChecklistSource.MANUAL

        agrupamento_widget = TextInput(attrs={"id": "novo-agrupamento", "list": "agrupamentos-sugestoes", "class": "col-span-12 lg:col-span-4"}).render("agrupamento_input", "")
        item_widget = TextInput(attrs={"id": "novo-item-descricao", "class": "col-span-12 lg:col-span-4"}).render("item_input", "")
        tipo_resposta_widget = SearchableSelectInput(choices=ChecklistItem.TIPO_RESPOSTA_CHOICES, attrs={"id": "novo-tipo-resposta", "class": "col-span-12 lg:col-span-4"}).render("tipo_resposta_select", "")

        existing_items_html = ""
        if self.instance and self.instance.pk:
            items = self.instance.items.all().order_by("order")
            for obj in items:
                existing_items_html += render_to_string(
                    "checklists/partials/item_row.html",
                    {
                        "group": obj.group,
                        "description": obj.description,
                        "response_type": obj.response_type,
                        "response_type_display": obj.get_response_type_display(),
                    },
                )

        current_pdf_html = ""
        if self.instance and self.instance.pk and self.instance.has_pdf_file:
            current_pdf_html = f'<p class="text-sm text-base-content/70 mt-2">Arquivo atual: <span class="font-semibold">{self.instance.pdf_file_name}</span></p>'

        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                Field("checklist_type", wrapper_class="col-span-12 lg:col-span-4"),
                Field("source"),
                HTML(
                    """
                    <script>
                    function activateChecklistSource(source) {
                        const sourceInput = document.getElementById('id_source');
                        const pdfInput = document.getElementById('imported-pdf');
                        const manualGroup = document.getElementById('manual-checklist-area');
                        const manualInputs = document.querySelectorAll('#manual-checklist-area input, #manual-checklist-area select, #manual-checklist-area button');
                        if (!sourceInput) {
                            return;
                        }
                        sourceInput.value = source;

                        if (pdfInput) {
                            pdfInput.disabled = source !== 'PDF';
                        }

                        manualInputs.forEach((element) => {
                            element.disabled = source !== 'MANUAL';
                        });

                        if (manualGroup) {
                            manualGroup.classList.toggle('opacity-50', source !== 'MANUAL');
                            manualGroup.classList.toggle('pointer-events-none', source !== 'MANUAL');
                        }

                        const importSection = document.getElementById('import-checklist-section');
                        const createSection = document.getElementById('create-checklist-section');
                        if (importSection) {
                            importSection.classList.toggle('ring', source === 'PDF');
                            importSection.classList.toggle('ring-primary', source === 'PDF');
                            importSection.classList.toggle('ring-offset-2', source === 'PDF');
                        }
                        if (createSection) {
                            createSection.classList.toggle('ring', source === 'MANUAL');
                            createSection.classList.toggle('ring-primary', source === 'MANUAL');
                            createSection.classList.toggle('ring-offset-2', source === 'MANUAL');
                        }
                    }

                    function initChecklistSource() {
                        const sourceInput = document.getElementById('id_source');
                        const resolvedSource = sourceInput && sourceInput.value ? sourceInput.value : 'MANUAL';
                        activateChecklistSource(resolvedSource);

                        const pdfInput = document.getElementById('imported-pdf');
                        if (pdfInput) {
                            pdfInput.addEventListener('change', () => {
                                if (pdfInput.files && pdfInput.files.length > 0) {
                                    activateChecklistSource('PDF');
                                }
                            });
                        }

                        const addButton = document.getElementById('btn-add-item');
                        if (addButton) {
                            addButton.addEventListener('click', () => activateChecklistSource('MANUAL'));
                        }
                    }
                    document.addEventListener('DOMContentLoaded', initChecklistSource);
                    </script>
                    """
                ),
                HTML('<h4 class="text-xl font-semibold mt-8 mb-3">Importe seu Checklist</h4>'),
                Div(
                    HTML('<p class="text-sm text-base-content/70 mb-3">Envie um PDF pronto para uso. Ao importar, a criação manual será anulada.</p>'),
                    Field("imported_pdf", wrapper_class="mb-0"),
                    HTML(current_pdf_html),
                    HTML(
                        """
                        <div class="mt-3">
                            <button type="button" class="btn btn-outline btn-primary" onclick="activateChecklistSource('PDF')">Usar importação por PDF</button>
                        </div>
                        """
                    ),
                    css_id="import-checklist-section",
                    css_class="col-span-12 border border-base-300 rounded-xl p-4 transition-all",
                ),
                HTML('<div class="divider my-8">ou</div>'),
                HTML('<h4 class="text-xl font-semibold mb-3">Crie seu Checklist</h4>'),
                Div(
                    Div(
                        HTML('<p class="text-sm text-base-content/70 mb-3">Monte os itens manualmente. Ao adicionar itens, a importação de PDF será anulada.</p>'),
                        Div(
                            Div(
                                HTML('<label class="label"><span class="label-text font-bold">Agrupamento</span></label>'),
                                HTML(agrupamento_widget),
                                HTML('<datalist id="agrupamentos-sugestoes"></datalist>'),
                                css_class="col-span-12 lg:col-span-3",
                            ),
                            Div(
                                HTML('<label class="label"><span class="label-text font-bold">Item</span></label>'),
                                HTML(item_widget),
                                css_class="col-span-12 lg:col-span-3",
                            ),
                            Div(HTML('<label class="label"><span class="label-text font-bold">Tipo de Resposta</span></label>'), HTML(tipo_resposta_widget), css_class="col-span-12 lg:col-span-3"),
                            Div(
                                HTML('<label class="label"><span class="label-text opacity-0">Ação</span></label>'),
                                Button(
                                    "add",
                                    "Adicionar",
                                    css_id="btn-add-item",
                                    css_class="btn btn-primary w-full",
                                    hx_post=reverse("checklist:add_item_row"),
                                    hx_target="#itens-tabela-body",
                                    hx_swap="beforeend",
                                    hx_include="#novo-agrupamento, #novo-item-descricao, #novo-tipo-resposta",
                                    hx_on_after_settle="window.dispatchEvent(new CustomEvent('reorder'))",
                                ),
                                css_class="col-span-12 lg:col-span-3",
                            ),
                            css_class="grid grid-cols-12 gap-4 w-full items-end",
                        ),
                        css_class="col-span-12",
                    ),
                    HTML('<h2 class="text-xl font-bold mt-8">Itens do Checklist</h2>'),
                    HTML('<div class="divider"></div>'),
                    HTML(f"""
                        <div class="overflow-x-auto col-span-12" 
                             x-data="{{
                                reorder() {{
                                    this.$nextTick(() => {{
                                        let indexes = this.$el.querySelectorAll('.row-index');
                                        indexes.forEach((el, i) => {{
                                            el.textContent = i + 1;
                                        }});
                                    }});
                                }}
                             }}"
                             @reorder.window="reorder()"
                             x-init="reorder()">
                            <table class="table w-full">
                                <thead>
                                    <tr>
                                        <th class="w-16">Seq.</th>
                                        <th>Agrupamento</th>
                                        <th>Item</th>
                                        <th>Tipo de Resposta</th>
                                        <th class="w-20">Ações</th>
                                    </tr>
                                </thead>
                                <tbody id="itens-tabela-body">{existing_items_html}</tbody>
                            </table>
                        </div>
                    """),
                    css_id="manual-checklist-area",
                ),
                HTML(
                    """
                    <div class="mt-3">
                        <button type="button" class="btn btn-outline btn-primary" onclick="activateChecklistSource('MANUAL')">Usar criação manual</button>
                    </div>
                    """
                ),
                css_id="create-checklist-section",
                css_class="col-span-12 border border-base-300 rounded-xl p-4 transition-all",
            ),
            HTML('<div class="divider"></div>'),
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def clean_source(self) -> str:
        source = str(self.cleaned_data.get("source") or "").strip()
        if source not in {choice[0] for choice in Checklist.ChecklistSource.choices}:
            return Checklist.ChecklistSource.MANUAL
        return source

    def clean_imported_pdf(self):
        uploaded_pdf = self.cleaned_data.get("imported_pdf")
        if uploaded_pdf is None:
            return None

        uploaded_name = str(getattr(uploaded_pdf, "name", "") or "").lower()
        uploaded_content_type = str(getattr(uploaded_pdf, "content_type", "") or "").lower()
        if not uploaded_name.endswith(".pdf") and uploaded_content_type not in {"application/pdf", "application/x-pdf"}:
            raise forms.ValidationError("Envie um arquivo PDF valido.")

        return uploaded_pdf
