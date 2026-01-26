from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, Field, HTML, Submit, Button
from django.template.loader import render_to_string
from django.urls import reverse
from .models import Checklist, ChecklistItem
from apps.core.widgets import TextInput, SelectInput
from ..workshops.models.workshops import Workshop


class ChecklistForm(forms.ModelForm):
    class Meta:
        model = Checklist
        fields = [
            "name"
        ]
        widgets = {
            "name": TextInput()
        }

    def __init__(self, *args, workshop: Workshop | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.workshop = workshop
        self.helper = FormHelper()
        self.helper.form_method = "post"

        cancel_url = reverse("checklist:checklist_list")

        agrupamento_widget = TextInput(attrs={"id": "novo-agrupamento", "list": "agrupamentos-sugestoes", "class":"col-span-12 lg:col-span-4"}).render("agrupamento_input", "")
        item_widget = TextInput(attrs={"id": "novo-item-descricao", "class":"col-span-12 lg:col-span-4"}).render("item_input", "")
        tipo_resposta_widget = SelectInput(choices=ChecklistItem.TIPO_RESPOSTA_CHOICES, attrs={"id": "novo-tipo-resposta", "class":"col-span-12 lg:col-span-4"}).render("tipo_resposta_select", "")

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

        self.helper.layout = Layout(
            Div(
                Field("name", wrapper_class="col-span-12 lg:col-span-4"),
                #
                HTML('<h4 class="text-lg font-semibold" style="margin-top:4vh; margin-bottom:2vh;">Adicionar Itens ao Checklist</h4>'),
                Div(
                    Div(
                        # Agrupamento
                        Div(
                            HTML('<label class="label"><span class="label-text font-bold">Agrupamento</span></label>'),
                            HTML(agrupamento_widget),
                            HTML('<datalist id="agrupamentos-sugestoes"></datalist>'),
                            css_class="col-span-12 lg:col-span-3",
                        ),
                        # Item
                        Div(
                            HTML('<label class="label"><span class="label-text font-bold">Item</span></label>'),
                            HTML(item_widget),
                            css_class="col-span-12 lg:col-span-3",
                        ),
                        # Tipo de Resposta
                        Div(HTML('<label class="label"><span class="label-text font-bold">Tipo de Resposta</span></label>'),
                            HTML(tipo_resposta_widget),
                            css_class="col-span-12 lg:col-span-3"),

                        # Botão Adicionar
                        Div(
                            HTML('<label class="label"><span class="label-text opacity-0">Ação</span></label>'),
                            Button("add", "Adicionar", css_id="btn-add-item", css_class="btn btn-primary w-full",
                                hx_post=reverse("checklist:add_item_row"), hx_target="#itens-tabela-body", hx_swap="beforeend",
                                hx_include="#novo-agrupamento, #novo-item-descricao, #novo-tipo-resposta",
                                hx_on_after_settle="window.dispatchEvent(new CustomEvent('reorder'))",
                            ),
                            css_class="col-span-12 lg:col-span-3",
                        ),
                        css_class="grid grid-cols-12 gap-4 w-full items-end",
                    ),
                    css_class="col-span-12",
                ),
                #
                HTML('<h2 class="text-xl font-bold" style="margin-top:6vh;">Itens do Checklist</h2>'),
                HTML('<div class="divider"></div>'),
                #
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
            ),
            #
            HTML('<div class="divider"></div>'),
            #
            Div(
                HTML(f'<a href="{cancel_url}" class="btn-form-cancel">Cancelar</a>'),
                Submit("submit", "Salvar", css_class="btn-form-save"),
                css_class="flex items-center justify-end gap-2",
            ),
        )
