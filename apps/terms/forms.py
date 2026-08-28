from django import forms
from crispy_forms.helper import FormHelper  # type: ignore[import-untyped]
from crispy_forms.layout import ButtonHolder, Div, Field, HTML, Layout, Submit  # type: ignore[import-untyped]
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import CheckboxInput, SearchableSelectInput, TextInput, TextareaInput
from apps.core.text_normalization import sentence_case
from apps.terms.content import DEFAULT_INTRO_TEXT, DEFAULT_RECEIPT_SECTIONS
from apps.terms.models import TermKind, TermSource, TermTemplate
from apps.terms.placeholders import TERM_PLACEHOLDERS
from apps.terms.util import new_topic_key
from apps.workshops.models.workshops import Workshop


class TermTemplateForm(CoreModelForm):
    imported_pdf = forms.FileField(
        required=False,
        label="Arquivo PDF",
        widget=forms.ClearableFileInput(attrs={"accept": "application/pdf", "class": "file-input file-input-bordered w-full", "id": "imported-pdf"}),
    )

    class Meta:
        model = TermTemplate
        fields = ["name", "kind", "source", "intro_text", "is_active"]
        widgets = {
            "name": TextInput(),
            "kind": SearchableSelectInput(choices=[(str(value), str(label)) for value, label in TermKind.choices]),
            "source": forms.HiddenInput(attrs={"id": "id_source"}),
            "intro_text": TextareaInput(attrs={"rows": 3, "id": "id_intro_text"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"
        self.helper.attrs = {"enctype": "multipart/form-data"}

        cancel_url = reverse("terms:term_list")
        if self.instance and self.instance.pk:
            self.fields["source"].initial = self.instance.source
        else:
            self.fields["source"].initial = TermSource.HTML
            self.fields["intro_text"].initial = DEFAULT_INTRO_TEXT

        current_pdf_html = ""
        if self.instance and self.instance.pk and self.instance.has_pdf_file:
            current_pdf_html = f'<p class="text-sm text-base-content/70 mt-2">Arquivo atual: <span class="font-semibold">{self.instance.pdf_file_name}</span></p>'

        topics_html = self._render_topics_html()
        chips = "".join((f'<button type="button" class="btn btn-xs btn-outline" data-term-token="{{{{{item.token}}}}}">{item.label}</button>' for item in TERM_PLACEHOLDERS))
        add_topic_url = reverse("terms:add_topic")

        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-6"),
                Field("kind", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-2"),
                Field("source"),
                HTML(
                    """
                    <script>
                    function activateTermSource(source) {
                        const sourceInput = document.getElementById('id_source');
                        const pdfInput = document.getElementById('imported-pdf');
                        if (sourceInput) {
                            sourceInput.value = source;
                        }
                        if (pdfInput) {
                            pdfInput.disabled = source !== 'pdf';
                        }
                        const htmlSection = document.getElementById('html-term-section');
                        const pdfSection = document.getElementById('pdf-term-section');
                        if (htmlSection) {
                            htmlSection.classList.toggle('ring', source === 'html');
                            htmlSection.classList.toggle('ring-primary', source === 'html');
                            htmlSection.classList.toggle('opacity-50', source !== 'html');
                            htmlSection.classList.toggle('pointer-events-none', source !== 'html');
                        }
                        if (pdfSection) {
                            pdfSection.classList.toggle('ring', source === 'pdf');
                            pdfSection.classList.toggle('ring-primary', source === 'pdf');
                            pdfSection.classList.toggle('opacity-50', source !== 'pdf');
                        }
                    }
                    function insertTermToken(token) {
                        const active = document.activeElement;
                        if (!active || (active.tagName !== 'TEXTAREA' && active.tagName !== 'INPUT')) {
                            return;
                        }
                        const start = active.selectionStart || 0;
                        const end = active.selectionEnd || 0;
                        const value = active.value || '';
                        active.value = value.slice(0, start) + token + value.slice(end);
                        active.focus();
                        active.selectionStart = active.selectionEnd = start + token.length;
                    }
                    document.addEventListener('DOMContentLoaded', function () {
                        const sourceInput = document.getElementById('id_source');
                        activateTermSource(sourceInput && sourceInput.value ? sourceInput.value : 'html');
                        document.querySelectorAll('[data-term-token]').forEach(function (button) {
                            button.addEventListener('click', function () {
                                activateTermSource('html');
                                insertTermToken(button.getAttribute('data-term-token') || '');
                            });
                        });
                    });
                    </script>
                    """
                ),
                Div(
                    HTML('<h4 class="text-xl font-semibold mb-2">Conteúdo do termo</h4>'),
                    HTML('<p class="text-sm text-base-content/70 mb-3">Monte o termo em tópicos, como no checklist. Cada texto vira um item na lista. Dados do veículo, placa, nome e CPF entram sozinhos no documento na hora da assinatura.</p>'),
                    HTML(f'<div class="flex flex-wrap gap-2 mb-4">{chips}</div>'),
                    Field("intro_text", wrapper_class="col-span-12"),
                    HTML(f'<div id="term-topics-container" class="flex flex-col gap-4 mt-4">{topics_html}</div>'),
                    HTML(
                        f"""
                        <div class="mt-4 flex flex-wrap gap-2">
                            <button type="button" class="btn btn-primary" hx-post="{add_topic_url}" hx-target="#term-topics-container" hx-swap="beforeend" hx-include="[name='csrfmiddlewaretoken']" onclick="activateTermSource('html')">Adicionar tópico</button>
                            <button type="button" class="btn btn-outline btn-primary" onclick="activateTermSource('html')">Usar texto na plataforma</button>
                        </div>
                        """
                    ),
                    css_id="html-term-section",
                    css_class="col-span-12 border border-base-300 rounded-xl p-4 transition-all",
                ),
                HTML('<div class="divider my-8">ou</div>'),
                Div(
                    HTML('<h4 class="text-xl font-semibold mb-2">Importar PDF</h4>'),
                    HTML('<p class="text-sm text-base-content/70 mb-3">PDF estático para consulta. Este modo não preenche campos dinâmicos e não envia para assinatura.</p>'),
                    Field("imported_pdf", wrapper_class="mb-0"),
                    HTML(current_pdf_html),
                    HTML('<div class="mt-3"><button type="button" class="btn btn-outline btn-primary" onclick="activateTermSource(\'pdf\')">Usar arquivo PDF</button></div>'),
                    css_id="pdf-term-section",
                    css_class="col-span-12 border border-base-300 rounded-xl p-4 transition-all",
                ),
                css_class="grid grid-cols-12 gap-4",
            ),
            HTML('<div class="divider"></div>'),
            ButtonHolder(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )

    def _render_topics_html(self) -> str:
        sections: list[dict[str, object]]
        if self.instance and self.instance.pk:
            sections = [
                {
                    "key": new_topic_key(),
                    "title": topic.title,
                    "items": [bullet.text for bullet in topic.bullets.all()],
                }
                for topic in self.instance.topics.prefetch_related("bullets").all()
            ]
        else:
            sections = [{"key": new_topic_key(), "title": section["title"], "items": list(section["items"])} for section in DEFAULT_RECEIPT_SECTIONS]

        return "".join(render_to_string("terms/partials/topic_card.html", {"topic_key": section["key"], "title": section["title"], "items": section["items"]}) for section in sections)

    def clean_source(self) -> str:
        source = str(self.cleaned_data.get("source") or "").strip()
        if source not in {choice[0] for choice in TermSource.choices}:
            return TermSource.HTML
        return source

    def clean_imported_pdf(self):
        uploaded_pdf = self.cleaned_data.get("imported_pdf")
        if uploaded_pdf is None:
            return None
        uploaded_name = str(getattr(uploaded_pdf, "name", "") or "").lower()
        uploaded_content_type = str(getattr(uploaded_pdf, "content_type", "") or "").lower()
        if not uploaded_name.endswith(".pdf") and uploaded_content_type not in {"application/pdf", "application/x-pdf"}:
            raise forms.ValidationError("Envie um arquivo PDF válido.")
        return uploaded_pdf

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return sentence_case(value) if value else value

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source") or TermSource.HTML
        if source == TermSource.PDF:
            has_existing = bool(self.instance and self.instance.pk and self.instance.has_pdf_file)
            if cleaned.get("imported_pdf") is None and not has_existing:
                self.add_error("imported_pdf", "Envie um arquivo PDF para este termo.")
        return cleaned
