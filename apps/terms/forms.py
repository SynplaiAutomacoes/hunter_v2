from django import forms
from crispy_forms.helper import FormHelper  # type: ignore[import-untyped]
from crispy_forms.layout import ButtonHolder, Div, Field, HTML, Layout, Submit  # type: ignore[import-untyped]
from django.template.loader import render_to_string
from django.urls import reverse

from apps.core.presentation.forms import CoreModelForm
from apps.core.presentation.widgets import CheckboxInput, SearchableSelectInput, TextInput, TextareaInput
from apps.core.text_normalization import sentence_case
from apps.terms.content import DEFAULT_INTRO_TEXT, DEFAULT_RECEIPT_SECTIONS
from apps.terms.models import TERM_DEFAULT_ACCENT_COLOR, TERM_DEFAULT_PRIMARY_COLOR, TermKind, TermSource, TermTemplate
from apps.terms.placeholders import get_term_variable_groups
from apps.terms.util import new_topic_key
from apps.workshops.models.workshops import Workshop


def _render_color_picker(*, field_name: str, label: str, value: str, default_value: str, help_text: str = "") -> str:
    return render_to_string(
        "terms/partials/color_picker_field.html",
        {
            "field_name": field_name,
            "label": label,
            "value": value,
            "default_value": default_value,
            "help_text": help_text,
        },
    )


class TermTemplateForm(CoreModelForm):
    class Meta:
        model = TermTemplate
        fields = ["name", "kind", "intro_text", "is_active", "primary_color", "accent_color"]
        widgets = {
            "name": TextInput(),
            "kind": SearchableSelectInput(choices=[(str(value), str(label)) for value, label in TermKind.choices]),
            "intro_text": TextareaInput(attrs={"rows": 3, "id": "id_intro_text"}),
            "is_active": CheckboxInput(),
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("terms:term_list")
        primary_color = TERM_DEFAULT_PRIMARY_COLOR
        accent_color = TERM_DEFAULT_ACCENT_COLOR

        if self.instance and self.instance.pk:
            primary_color = self.instance.primary_color or TERM_DEFAULT_PRIMARY_COLOR
            accent_color = self.instance.accent_color or TERM_DEFAULT_ACCENT_COLOR
        else:
            self.fields["intro_text"].initial = DEFAULT_INTRO_TEXT

        self.fields["primary_color"].initial = primary_color
        self.fields["accent_color"].initial = accent_color

        topics_html = self._render_topics_html()
        placeholder_chips_html = render_to_string(
            "terms/partials/placeholder_chips.html",
            {"variable_groups": get_term_variable_groups()},
        )
        add_topic_url = reverse("terms:add_topic")

        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-6"),
                Field("kind", wrapper_class="col-span-12 lg:col-span-4"),
                Field("is_active", wrapper_class="col-span-12 lg:col-span-2"),
                Div(
                    HTML('<h4 class="text-xl font-semibold mb-1">Aparência do documento</h4>'),
                    HTML('<p class="text-sm text-base-content/70 mb-4">Personalize as cores do cabeçalho, faixas e destaques. O texto do termo permanece na cor padrão.</p>'),
                    HTML(
                        '<div class="col-span-12 grid grid-cols-1 gap-4 md:grid-cols-2">'
                        + _render_color_picker(
                            field_name="primary_color",
                            label="Cor principal",
                            value=primary_color,
                            default_value=TERM_DEFAULT_PRIMARY_COLOR,
                            help_text="Cabeçalho e barras escuras do documento.",
                        )
                        + _render_color_picker(
                            field_name="accent_color",
                            label="Cor de destaque",
                            value=accent_color,
                            default_value=TERM_DEFAULT_ACCENT_COLOR,
                            help_text="Faixa, numeração dos tópicos e marcadores.",
                        )
                        + "</div>"
                    ),
                    css_class="col-span-12 border border-base-300 rounded-xl p-4",
                ),
                HTML(
                    """
                    <script>
                    function copyTermPlaceholder(button) {
                        const token = button.getAttribute('data-term-token') || '';
                        if (!token) {
                            return;
                        }

                        const showCopiedFeedback = function () {
                            button.classList.add('btn-success', 'text-success-content');
                            const icon = button.querySelector('.material-icons');
                            const originalIcon = icon ? icon.textContent : '';
                            if (icon) {
                                icon.textContent = 'done';
                            }

                            document.body.dispatchEvent(new CustomEvent('showToast', {
                                detail: {
                                    type: 'success',
                                    message: 'Copiado para a área de transferência.',
                                },
                            }));

                            window.setTimeout(function () {
                                button.classList.remove('btn-success', 'text-success-content');
                                if (icon) {
                                    icon.textContent = originalIcon || 'content_copy';
                                }
                            }, 1200);
                        };

                        const fallbackCopy = function () {
                            const textarea = document.createElement('textarea');
                            textarea.value = token;
                            textarea.setAttribute('readonly', '');
                            textarea.style.position = 'absolute';
                            textarea.style.left = '-9999px';
                            document.body.appendChild(textarea);
                            textarea.select();
                            try {
                                if (document.execCommand('copy')) {
                                    showCopiedFeedback();
                                }
                            } finally {
                                document.body.removeChild(textarea);
                            }
                        };

                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            navigator.clipboard.writeText(token).then(showCopiedFeedback).catch(fallbackCopy);
                            return;
                        }

                        fallbackCopy();
                    }

                    function normalizeHexColor(rawValue) {
                        let value = String(rawValue || '').trim();
                        if (!value) {
                            return '';
                        }
                        if (!value.startsWith('#')) {
                            value = '#' + value;
                        }
                        if (!/^#[0-9a-fA-F]{6}$/.test(value)) {
                            return '';
                        }
                        return value.toLowerCase();
                    }

                    function updateTermColorField(field, color) {
                        const picker = field.querySelector('[data-term-color-picker]');
                        const text = field.querySelector('[data-term-color-text]');
                        const swatch = field.querySelector('[data-term-color-swatch]');
                        if (picker) {
                            picker.value = color;
                        }
                        if (text) {
                            text.value = color;
                        }
                        if (swatch) {
                            swatch.style.backgroundColor = color;
                        }
                    }

                    function initTermColorFields() {
                        document.querySelectorAll('[data-term-color-field]').forEach(function (field) {
                            if (field.dataset.termColorReady === 'true') {
                                return;
                            }
                            field.dataset.termColorReady = 'true';

                            const defaultColor = field.dataset.default || '#000000';
                            const picker = field.querySelector('[data-term-color-picker]');
                            const text = field.querySelector('[data-term-color-text]');
                            const resetButton = field.querySelector('[data-term-color-reset]');

                            const applyColor = function (color) {
                                const normalized = normalizeHexColor(color);
                                if (!normalized) {
                                    return;
                                }
                                updateTermColorField(field, normalized);
                            };

                            if (picker) {
                                picker.addEventListener('input', function (event) {
                                    applyColor(event.target.value);
                                });
                            }

                            if (text) {
                                text.addEventListener('input', function (event) {
                                    const normalized = normalizeHexColor(event.target.value);
                                    if (!normalized) {
                                        return;
                                    }
                                    updateTermColorField(field, normalized);
                                });
                                text.addEventListener('blur', function (event) {
                                    const normalized = normalizeHexColor(event.target.value) || defaultColor;
                                    updateTermColorField(field, normalized);
                                });
                            }

                            if (resetButton) {
                                resetButton.addEventListener('click', function () {
                                    applyColor(defaultColor);
                                });
                            }

                            applyColor(text && text.value ? text.value : defaultColor);
                        });
                    }

                    document.addEventListener('DOMContentLoaded', function () {
                        initTermColorFields();
                        document.querySelectorAll('[data-term-token]').forEach(function (button) {
                            button.addEventListener('click', function () {
                                copyTermPlaceholder(button);
                            });
                        });
                    });
                    </script>
                    """
                ),
                Div(
                    HTML('<h4 class="text-xl font-semibold mb-2">Conteúdo do termo</h4>'),
                    HTML('<p class="text-sm text-base-content/70 mb-3">Monte o termo em tópicos, como no checklist. Cada texto vira um item na lista. Use as variáveis abaixo onde quiser que os dados do cliente e do veículo apareçam no documento.</p>'),
                    HTML(placeholder_chips_html),
                    Field("intro_text", wrapper_class="col-span-12"),
                    HTML(f'<div id="term-topics-container" class="flex flex-col gap-4 mt-4">{topics_html}</div>'),
                    HTML(
                        f"""
                        <div class="mt-4">
                            <button type="button" class="btn btn-primary" hx-post="{add_topic_url}" hx-target="#term-topics-container" hx-swap="beforeend" hx-include="[name='csrfmiddlewaretoken']">Adicionar tópico</button>
                        </div>
                        """
                    ),
                    css_class="col-span-12 border border-base-300 rounded-xl p-4",
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

    def clean_name(self):
        value = self.cleaned_data.get("name")
        return sentence_case(value) if value else value

    def _clean_hex_color(self, field_name: str, *, default: str) -> str:
        raw_value = str(self.cleaned_data.get(field_name) or default).strip()
        if not raw_value.startswith("#"):
            raw_value = f"#{raw_value}"
        normalized = raw_value.lower()
        if len(normalized) != 7 or any(char not in "0123456789abcdef#" for char in normalized[1:]):
            raise forms.ValidationError("Informe uma cor válida no formato #RRGGBB.")
        return normalized

    def clean_primary_color(self) -> str:
        return self._clean_hex_color("primary_color", default=TERM_DEFAULT_PRIMARY_COLOR)

    def clean_accent_color(self) -> str:
        return self._clean_hex_color("accent_color", default=TERM_DEFAULT_ACCENT_COLOR)

    def save(self, commit: bool = True):
        instance = super().save(commit=False)
        instance.source = TermSource.HTML
        if commit:
            instance.save()
        return instance
