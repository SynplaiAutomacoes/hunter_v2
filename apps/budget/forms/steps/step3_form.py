# ruff: noqa: F403,F405
from .base import BudgetStepBaseForm
from .common import *
from .step3_support import *


class BudgetStep3Form(BudgetStepBaseForm):
    new_defect = forms.CharField(label=False, required=False, widget=TextInput(attrs={"id": "id_new_defect", "placeholder": "Digite um defeito e clique em Adicionar", "onkeypress": "if(event.keyCode==13){ event.preventDefault(); addDefectRow(); }"}))
    collaborator = forms.ModelMultipleChoiceField(label="Selecione os colaboradores", required=False, queryset=WorkshopCollaborator.objects.none())
    images = MultipleFileField(label=None, required=False, widget=MultipleFileInput(attrs={"class": "file-input file-input-bordered w-full"}))

    class Meta:
        model = Budget
        fields = ["checklist", "technical_diagnosis"]
        widgets = {
            "technical_diagnosis": TextareaInput(
                attrs={
                    "rows": 10,
                    "placeholder": "Descreva detalhadamente as observações técnicas, diagnósticos preliminares, testes realizados...",
                    "class": "bg-base-200",
                    "style": "background-color: var(--color-base-200); resize: none;",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.workshop:
            self.fields["collaborator"].queryset = WorkshopCollaborator.objects.filter(workshop=self.workshop, is_active=True)
            diagnostic_checklists = Checklist.objects.filter(
                workshop=self.workshop,
                checklist_type=Checklist.ChecklistType.AUTOMOTIVE_DIAGNOSTIC,
            )
            if self.instance.pk and self.instance.checklist_id:
                self.fields["checklist"].queryset = (diagnostic_checklists | Checklist.objects.filter(workshop=self.workshop, pk=self.instance.checklist_id)).order_by("name").distinct()
            else:
                self.fields["checklist"].queryset = diagnostic_checklists.order_by("name")

        initial_collaborators = []
        if self.instance.pk:
            initial_collaborators = [{"id": str(c.id), "name": c.name, "is_new": False} for c in self.instance.collaborators.all()]

        if not initial_collaborators:
            initial_collaborators = [{"id": "", "is_new": True}]

        import json

        self.initial_collaborators_json = json.dumps(initial_collaborators)

        checklist_pdf_base_url = reverse("budget:visualizar_pdf_checklist", args=[self.instance.pk]) if self.instance.pk else ""

        slot_placeholder_urls = {slot_type: static(path) for slot_type, path in SLOT_PLACEHOLDER_PATHS.items()}
        slot_placeholder_urls_js = "{" + ", ".join([f"'{slot_type}': '{slot_placeholder_urls[slot_type]}'" for slot_type in SLOT_IMAGE_TYPES]) + "}"
        slots_initial_html, additional_initial_html = _build_step3_images_initial_html(self.instance, slot_placeholder_urls)
        if not slots_initial_html:
            slots_initial_html = _build_step3_slot_fallback_html(slot_placeholder_urls)

        from django.template.loader import render_to_string

        collaborator_html = render_to_string(template_name="budget/partials/components/collaborator_field.html", context={"field": self["collaborator"], "initial_collaborators_json": self.initial_collaborators_json}, request=self.request)

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML(f"""<script>
                    function addDefectRow() {{
                        const input = document.getElementById('id_new_defect');
                        const container = document.getElementById('defect-list-container');
                        const text = input.value.trim();
                        if (text === "") return;
                        const id = 'new-' + Date.now();
                        const html = `<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-${{id}}">
                                <input type="hidden" name="defects_list" value="${{text}}">
                                <span class="font-medium">${{text}}</span>
                                <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                    X
                                </button>
                            </div>`;
                        container.insertAdjacentHTML('beforeend', html);
                        input.value = "";
                        input.focus();
                    }}

                    function printSelectedChecklist() {{
                        const checklistInput = document.getElementById('id_checklist');
                        const checklistId = checklistInput ? checklistInput.value.trim() : '';
                        if (!checklistId) {{
                            document.body.dispatchEvent(new CustomEvent('showToast', {{
                                detail: {{
                                    type: 'warning',
                                    message: 'Selecione um checklist antes de imprimir.',
                                }},
                            }}));
                            return;
                        }}

                        const checklistPdfBaseUrl = '{checklist_pdf_base_url}';
                        if (!checklistPdfBaseUrl) {{
                            document.body.dispatchEvent(new CustomEvent('showToast', {{
                                detail: {{
                                    type: 'error',
                                    message: 'Salve o orçamento para imprimir o checklist.',
                                }},
                            }}));
                            return;
                        }}

                        const checklistPrintUrl = checklistPdfBaseUrl + '?checklist=' + encodeURIComponent(checklistId);
                        window.dispatchEvent(new CustomEvent('open-pdf-modal', {{ 
                            detail: {{ url: checklistPrintUrl }} 
                        }}));
                    }}
                     
                    document.body.addEventListener('collaboratorSaved', function(evt) {{
                        const modal = document.getElementById('form_modal');
                        if (modal) modal.close();

                        const eventDetail = evt && evt.detail ? evt.detail : null;
                        const createdCollaboratorId = eventDetail && eventDetail.id ? String(eventDetail.id) : '';

                        const budgetId = {self.instance.pk if self.instance.pk else "null"};
                        const collabIdx = localStorage.getItem('budget_step3_collaborator_idx');
                        
                        // Atualiza as opções de todos os selects de colaboradores na página
                        if (createdCollaboratorId && eventDetail.name) {{
                             const selects = document.querySelectorAll('select[name="collaborators_list"]');
                             selects.forEach(select => {{
                                 const option = document.createElement('option');
                                 option.value = createdCollaboratorId;
                                 option.textContent = eventDetail.name;
                                 select.appendChild(option);
                             }});
                             
                             // Se sabermos qual índice estava sendo editado, selecionamos o novo lá
                             if (collabIdx !== null) {{
                                 const container = document.getElementById('collaborator-field-container');
                                 if (container && typeof Alpine !== 'undefined') {{
                                     const alpineData = Alpine.$data(container);
                                     if (alpineData && alpineData.collabs[collabIdx]) {{
                                         alpineData.collabs[collabIdx].id = createdCollaboratorId;
                                     }}
                                 }}
                             }}
                        }}
                        
                        localStorage.removeItem('budget_step3_collaborator_idx');
                    }});
                </script>"""),
            Div(
                # Coluna Esquerda
                Div(
                    # Diagnóstico Técnico
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Diagnóstico Técnico</h3>'),
                        HTML(collaborator_html),
                        #
                        HTML('<label class="block text-gray-700 font-bold mb-2">Adicione os defeitos encontrados durante a inspeção</label>'),
                        Div(id="defect-list-container", css_class="mb-4 p-4 border-2 border-dashed border-gray-200 rounded-lg min-h-[120px] flex flex-wrap content-start"),
                        Div(
                            Div(Field("new_defect", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2" onclick="addDefectRow()">
                                    Adicionar</button>"""),
                            css_class="flex items-end mb-8",
                        ),
                        css_class="mb-8",
                    ),
                    # Checklist para Impressão
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Checklist para Impressão</h3>'),
                        Div(
                            Div(Field("checklist", wrapper_class="mb-0"), css_class="flex-1"),
                            HTML("""<button type="button" class="btn btn-primary ml-2" onclick="printSelectedChecklist()">
                                            Imprimir</button>"""),
                            css_class="flex items-end mb-8",
                        ),
                        css_class="mb-8",
                    ),
                    css_class="col-span-12 lg:col-span-5",
                ),
                #
                Div(css_class="hidden lg:block lg:col-span-1"),
                #
                # Coluna Direita
                Div(
                    # Observações Técnicas
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Observações Técnicas</h3>'),
                        Field("technical_diagnosis", label=False, wrapper_class="mb-0"),
                        css_class="mb-8",
                    ),
                    # Imagens
                    Div(
                        HTML('<h3 class="text-2xl font-bold mb-4">Anexar Imagens do Veículo</h3>'),
                        HTML(f'<div id="vehicle-images-slots">{slots_initial_html}</div>'),
                        HTML('<h4 class="text-lg font-semibold mt-6 mb-2">Arquivos Adicionais</h4>'),
                        HTML(f'<div id="additional-images-container" class="space-y-2 mb-4">{additional_initial_html}</div>'),
                        Field("images", label=False, wrapper_class="mb-0"),
                        HTML('<p class="text-sm text-gray-500 mt-2">Use os slots acima para fotos específicas do veículo. Aqui você pode adicionar arquivos adicionais.</p>'),
                        css_class="mb-6",
                    ),
                    css_class="col-span-12 lg:col-span-6",
                ),
                css_class="grid grid-cols-1 lg:grid-cols-12 gap-4",
            ),
            HTML("""
                <dialog id="pdfModal" class="modal" x-data="{ pdfUrl: '' }" @open-pdf-modal.window="pdfUrl = $event.detail.url; $el.showModal()">
                    <div class="modal-box max-w-5xl w-full h-[90vh] p-0 flex flex-col">
                        <div class="flex items-center justify-between px-6 py-4 border-b bg-base-200">
                            <h3 class="text-xl font-bold flex items-center gap-2">
                                <span class="material-icons">description</span>
                                Visualização do Checklist
                            </h3>
                            <div class="flex gap-2">
                                <button type="button" class="btn btn-sm btn-success" data-allow-locked="1"
                                    onclick="const frame = document.querySelector('#pdfModal iframe'); frame.contentWindow.focus(); frame.contentWindow.print();">
                                    Baixar PDF
                                </button>
                                <button type="button" class="btn btn-sm" data-allow-locked="1" onclick="document.getElementById('pdfModal').close()">
                                    Fechar
                                </button>
                            </div>
                        </div>
                        <div class="flex-1 bg-gray-100">
                            <template x-if="pdfUrl">
                                <iframe :src="pdfUrl" class="w-full h-full" frameborder="0"></iframe>
                            </template>
                        </div>
                    </div>
                    <form method="dialog" class="modal-backdrop"><button data-allow-locked="1">close</button></form>
                </dialog>
            """),
        )

        self.helper.layout.append(
            HTML(
                """
                <style>
                    [data-theme="dark"] #vehicle-images-slots [id^="slot-"] {
                        background-color: rgb(31 41 55 / 0.75) !important;
                        border-color: rgb(75 85 99) !important;
                    }
                    [data-theme="dark"] #vehicle-images-slots [id^="slot-"] p {
                        color: rgb(229 231 235) !important;
                    }
                    [data-theme="dark"] #additional-images-container [id^="additional-image-"] {
                        background-color: rgb(31 41 55 / 0.75) !important;
                        border-color: rgb(75 85 99) !important;
                    }
                </style>
                """
            )
        )
        if self.instance.pk:
            existing_defects = self.instance.defects.all()
            if existing_defects.exists():
                defects_json = "".join(
                    [
                        f"""<div class="badge badge-lg badge-ghost gap-2 py-5 mb-2 mr-2 pr-1" id="defect-old-{d.id}">
                            <input type="hidden" name="defects_list" value="{d.name}">
                            <span class="font-medium">{d.name}</span>
                            <button type="button" onclick="this.parentElement.remove()" class="btn btn-ghost btn-xs btn-circle text-error">
                                X
                            </button>
                        </div>"""
                        for d in existing_defects
                    ]
                )
                # Injeta os defeitos existentes após a renderização do container
                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        document.getElementById('defect-list-container').innerHTML = `{defects_json}`;
                    </script>
                    """)
                )

            # Inject existing images organized by type (slots + additional)
            existing_images = self.instance.ordered_images
            if existing_images.exists():
                existing_images_list = list(existing_images)
                images_by_type = {}
                additional_images = []
                for existing_image in existing_images_list:
                    if existing_image.image_type in SLOT_IMAGE_TYPES and existing_image.content and existing_image.image_type not in images_by_type:
                        images_by_type[existing_image.image_type] = existing_image
                    elif existing_image.content:
                        additional_images.append(existing_image)

                # Define slots layout
                slots_config = SLOT_LAYOUT_CONFIG

                # Build slots HTML
                slots_html = []

                # Principal (full width)
                slot = slots_config[0]
                img = images_by_type.get(slot["type"])
                if img and img.content:
                    img_data = base64.b64encode(img.content).decode("utf-8")
                    img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                    slots_html.append(f"""
                    <div class="mb-4">
                        <div class="relative border-2 border-gray-300 rounded-lg p-4 bg-white hover:border-primary transition-colors cursor-pointer group" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <img src="{img_src}" alt="{slot["label"]}" class="w-full h-48 object-contain rounded mb-2">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                            <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                            <button type="button" 
                                    onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                    class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span class="material-icons text-xs">delete</span>
                            </button>
                        </div>
                    </div>
                    """)
                else:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="mb-4">
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-48">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-32 object-contain rounded mb-2 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                    </div>
                    """)

                # Two columns for Frontal/Traseira
                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[1:3]:
                    img = images_by_type.get(slot["type"])
                    if img and img.content:
                        img_data = base64.b64encode(img.content).decode("utf-8")
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        slots_html.append(f"""
                        <div class="relative border-2 border-gray-300 rounded-lg p-3 bg-white hover:border-primary transition-colors cursor-pointer group" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <img src="{img_src}" alt="{slot["label"]}" class="w-full h-32 object-contain rounded mb-2">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                            <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                            <button type="button" 
                                    onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                    class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span class="material-icons text-xs">delete</span>
                            </button>
                        </div>
                        """)
                    else:
                        placeholder_src = slot_placeholder_urls[slot["type"]]
                        slots_html.append(f"""
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-32">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                        """)
                slots_html.append("</div>")

                # Two columns for Direita/Esquerda
                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[3:5]:
                    img = images_by_type.get(slot["type"])
                    if img and img.content:
                        img_data = base64.b64encode(img.content).decode("utf-8")
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        slots_html.append(f"""
                        <div class="relative border-2 border-gray-300 rounded-lg p-3 bg-white hover:border-primary transition-colors cursor-pointer group" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <img src="{img_src}" alt="{slot["label"]}" class="w-full h-32 object-contain rounded mb-2">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                            <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                            <button type="button" 
                                    onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                    class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <span class="material-icons text-xs">delete</span>
                            </button>
                        </div>
                        """)
                    else:
                        placeholder_src = slot_placeholder_urls[slot["type"]]
                        slots_html.append(f"""
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-32">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                        """)
                slots_html.append("</div>")

                # Full width for Painel, Chassi, Motor
                for slot in slots_config[5:]:
                    img = images_by_type.get(slot["type"])
                    if img and img.content:
                        img_data = base64.b64encode(img.content).decode("utf-8")
                        img_src = f"data:{img.content_type or 'image/jpeg'};base64,{img_data}"
                        slots_html.append(f"""
                        <div class="mb-4">
                            <div class="relative border-2 border-gray-300 rounded-lg p-4 bg-white hover:border-primary transition-colors cursor-pointer group" 
                                 id="slot-{slot["type"]}"
                                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                                <img src="{img_src}" alt="{slot["label"]}" class="w-full h-40 object-contain rounded mb-2">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                       onchange="previewSlotImage('{slot["type"]}', this)">
                                <input type="hidden" id="delete-slot-{slot["type"]}" name="slot_to_delete" value="">
                                <button type="button" 
                                        onclick="event.stopPropagation(); deleteSlotImage('{slot["type"]}', '{img.id}')"
                                        class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <span class="material-icons text-xs">delete</span>
                                </button>
                            </div>
                        </div>
                        """)
                    else:
                        placeholder_src = slot_placeholder_urls[slot["type"]]
                        slots_html.append(f"""
                        <div class="mb-4">
                            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                                 id="slot-{slot["type"]}"
                                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                                <div class="flex flex-col items-center justify-center h-40">
                                    <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-24 object-contain rounded mb-2 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                    <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                                </div>
                                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                       onchange="previewSlotImage('{slot["type"]}', this)">
                            </div>
                        </div>
                        """)

                # Additional images (type=ADDITIONAL)
                additional_images_html = []
                for img in additional_images:
                    if img.content:
                        file_name = escape(img.content_name or f"Arquivo {img.id}")
                        file_size = _format_file_size(len(img.content or b""))
                        additional_images_html.append(f"""
                        <div class="flex items-center justify-between gap-3 border border-gray-200 rounded-lg px-3 py-2 hover:border-primary transition-colors" id="additional-image-{img.id}">
                            <div class="min-w-0 flex-1">
                                <p class="text-sm font-semibold text-gray-700 truncate" title="{file_name}">{file_name}</p>
                                <p class="text-xs text-gray-500">{file_size}</p>
                            </div>
                            <input type="hidden" name="images_to_delete" value="" id="delete-flag-{img.id}">
                            <button type="button" 
                                    onclick="document.getElementById('delete-flag-{img.id}').value='{img.id}'; document.getElementById('additional-image-{img.id}').classList.add('opacity-50'); this.disabled=true; this.textContent='Será excluído';"
                                    class="btn btn-xs btn-error text-white"
                                    title="Marcar para exclusão">
                                Excluir
                            </button>
                        </div>
                        """)

                # Inject JavaScript for image preview and deletion
                slots_html_joined = "".join(slots_html)
                additional_html_joined = "".join(additional_images_html)

                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        function renderBudgetStep3Images() {{
                            const slotsContainer = document.getElementById('vehicle-images-slots');
                            const additionalContainer = document.getElementById('additional-images-container');
                            if (!slotsContainer || !additionalContainer) {{
                                return;
                            }}
                            if (slotsContainer.children.length > 0) {{
                                return;
                            }}
                            slotsContainer.innerHTML = `{slots_html_joined}`;
                            if (additionalContainer.children.length === 0) {{
                                additionalContainer.innerHTML = `{additional_html_joined}`;
                            }}
                        }}

                        renderBudgetStep3Images();
                        window.setTimeout(renderBudgetStep3Images, 0);

                        const slotPlaceholders = {slot_placeholder_urls_js};
                        function getSlotHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-48';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-40';
                            return 'h-32';
                        }}

                        function getSlotEmptyImageHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-32';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-24';
                            return 'h-16';
                        }}

                        function getSlotHintMarginClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}' || slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return ' mt-1';
                            return '';
                        }}

                        function removeNewSlotImage(slotType) {{
                            const slotDiv = document.getElementById('slot-' + slotType);
                            const input = document.getElementById('file-input-' + slotType);
                            if (!slotDiv || !input) {{
                                return;
                            }}

                            const labelElement = slotDiv.querySelector('p');
                            const label = labelElement ? labelElement.textContent : '';
                            const height = getSlotHeightClass(slotType);
                            const imageHeight = getSlotEmptyImageHeightClass(slotType);
                            const hintMargin = getSlotHintMarginClass(slotType);
                            const placeholderSrc = slotPlaceholders[slotType] || '';

                            input.value = '';
                            slotDiv.classList.remove('bg-white', 'opacity-50');
                            slotDiv.classList.add('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');

                            slotDiv.innerHTML = `
                                <div class="flex flex-col items-center justify-center ${{height}}">
                                    <img src="${{placeholderSrc}}" alt="Placeholder ${{label}}" class="w-full ${{imageHeight}} object-contain rounded mb-1 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                    <p class="text-center text-xs text-gray-400${{hintMargin}}">Clique para adicionar</p>
                                </div>
                            `;

                            slotDiv.appendChild(input);
                        }}
                        
                        function previewSlotImage(slotType, input) {{
                            if (input.files && input.files[0]) {{
                                const reader = new FileReader();
                                reader.onload = function(e) {{
                                    const slotDiv = document.getElementById('slot-' + slotType);
                                    const label = slotDiv.querySelector('p').textContent;
                                    const height = getSlotHeightClass(slotType);
                                    slotDiv.innerHTML = `
                                        <img src="${{e.target.result}}" alt="${{label}}" class="w-full ${{height}} object-contain rounded mb-2">
                                        <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                        <button type="button"
                                                onclick="event.stopPropagation(); removeNewSlotImage('${{slotType}}')"
                                                class="absolute top-2 right-2 btn btn-xs btn-error text-white"
                                                title="Remover imagem">
                                            <span class="material-icons text-xs">delete</span>
                                        </button>
                                        <div class="absolute top-2 left-2 badge badge-success gap-1">
                                            <span class="material-icons text-xs">check</span>
                                            Nova
                                        </div>
                                    `;
                                    slotDiv.classList.remove('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');
                                    slotDiv.classList.add('border-gray-300', 'bg-white');
                                    slotDiv.classList.remove('opacity-50');
                                    
                                    // Re-attach the input element
                                    slotDiv.appendChild(input);
                                }};
                                reader.readAsDataURL(input.files[0]);
                            }}
                        }}
                        
                        function deleteSlotImage(slotType, imageId) {{
                            const slotDiv = document.getElementById('slot-' + slotType);
                            const label = slotDiv.querySelector('p').textContent;
                            
                            // Mark for deletion
                            const deleteInput = document.getElementById('delete-slot-' + slotType) || document.createElement('input');
                            deleteInput.type = 'hidden';
                            deleteInput.name = 'slot_to_delete';
                            deleteInput.id = 'delete-slot-' + slotType;
                            deleteInput.value = imageId;
                            slotDiv.appendChild(deleteInput);
                            
                            // Replace with empty slot
                            slotDiv.classList.add('border-dashed', 'bg-gray-50', 'hover:bg-gray-100', 'opacity-50');
                            const height = getSlotHeightClass(slotType);
                            const placeholderSrc = slotPlaceholders[slotType] || '';
                            slotDiv.innerHTML = `
                                <div class="flex flex-col items-center justify-center ${{height}}">
                                    <img src="${{placeholderSrc}}" alt="Placeholder ${{label}}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                    <p class="text-center text-xs text-error">Será removida (clique para substituir)</p>
                                </div>
                                <input type="file" id="file-input-${{slotType}}" name="image_${{slotType}}" accept="image/*" class="hidden" onchange="previewSlotImage('${{slotType}}', this)">
                            `;
                            slotDiv.appendChild(deleteInput);
                        }}
                    </script>
                    """)
                )
            else:
                # No existing images, show empty slots
                slots_config = SLOT_LAYOUT_CONFIG

                slots_html = []

                # Principal (full width)
                slot = slots_config[0]
                placeholder_src = slot_placeholder_urls[slot["type"]]
                slots_html.append(f"""
                <div class="mb-4">
                    <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                         id="slot-{slot["type"]}"
                         onclick="document.getElementById('file-input-{slot["type"]}').click()">
                        <div class="flex flex-col items-center justify-center h-48">
                            <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-32 object-contain rounded mb-2 opacity-40">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                        </div>
                        <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                               onchange="previewSlotImage('{slot["type"]}', this)">
                    </div>
                </div>
                """)

                # Two columns grid
                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[1:3]:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                         id="slot-{slot["type"]}"
                         onclick="document.getElementById('file-input-{slot["type"]}').click()">
                        <div class="flex flex-col items-center justify-center h-32">
                            <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                        </div>
                        <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                               onchange="previewSlotImage('{slot["type"]}', this)">
                    </div>
                    """)
                slots_html.append("</div>")

                slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
                for slot in slots_config[3:5]:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                         id="slot-{slot["type"]}"
                         onclick="document.getElementById('file-input-{slot["type"]}').click()">
                        <div class="flex flex-col items-center justify-center h-32">
                            <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                            <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                            <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                        </div>
                        <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                               onchange="previewSlotImage('{slot["type"]}', this)">
                    </div>
                    """)
                slots_html.append("</div>")

                # Full width for remaining
                for slot in slots_config[5:]:
                    placeholder_src = slot_placeholder_urls[slot["type"]]
                    slots_html.append(f"""
                    <div class="mb-4">
                        <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                             id="slot-{slot["type"]}"
                             onclick="document.getElementById('file-input-{slot["type"]}').click()">
                            <div class="flex flex-col items-center justify-center h-40">
                                <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-24 object-contain rounded mb-2 opacity-40">
                                <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                                <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                            </div>
                            <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" 
                                   onchange="previewSlotImage('{slot["type"]}', this)">
                        </div>
                    </div>
                    """)

                slots_html_joined = "".join(slots_html)

                self.helper.layout.append(
                    HTML(f"""
                    <script>
                        function renderBudgetStep3EmptySlots() {{
                            const slotsContainer = document.getElementById('vehicle-images-slots');
                            if (!slotsContainer) {{
                                return;
                            }}
                            if (slotsContainer.children.length > 0) {{
                                return;
                            }}
                            slotsContainer.innerHTML = `{slots_html_joined}`;
                        }}

                        renderBudgetStep3EmptySlots();
                        window.setTimeout(renderBudgetStep3EmptySlots, 0);

                        const slotPlaceholders = {slot_placeholder_urls_js};
                        function getSlotHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-48';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-40';
                            return 'h-32';
                        }}

                        function getSlotEmptyImageHeightClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}') return 'h-32';
                            if (slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return 'h-24';
                            return 'h-16';
                        }}

                        function getSlotHintMarginClass(slotType) {{
                            if (slotType === '{BudgetImageType.PRINCIPAL}' || slotType === '{BudgetImageType.PAINEL}' || slotType === '{BudgetImageType.CHASSI}' || slotType === '{BudgetImageType.MOTOR}') return ' mt-1';
                            return '';
                        }}

                        function removeNewSlotImage(slotType) {{
                            const slotDiv = document.getElementById('slot-' + slotType);
                            const input = document.getElementById('file-input-' + slotType);
                            if (!slotDiv || !input) {{
                                return;
                            }}

                            const labelElement = slotDiv.querySelector('p');
                            const label = labelElement ? labelElement.textContent : '';
                            const height = getSlotHeightClass(slotType);
                            const imageHeight = getSlotEmptyImageHeightClass(slotType);
                            const hintMargin = getSlotHintMarginClass(slotType);
                            const placeholderSrc = slotPlaceholders[slotType] || '';

                            input.value = '';
                            slotDiv.classList.remove('bg-white', 'opacity-50');
                            slotDiv.classList.add('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');

                            slotDiv.innerHTML = `
                                <div class="flex flex-col items-center justify-center ${{height}}">
                                    <img src="${{placeholderSrc}}" alt="Placeholder ${{label}}" class="w-full ${{imageHeight}} object-contain rounded mb-1 opacity-40">
                                    <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                    <p class="text-center text-xs text-gray-400${{hintMargin}}">Clique para adicionar</p>
                                </div>
                            `;

                            slotDiv.appendChild(input);
                        }}
                        
                        function previewSlotImage(slotType, input) {{
                            if (input.files && input.files[0]) {{
                                const reader = new FileReader();
                                reader.onload = function(e) {{
                                    const slotDiv = document.getElementById('slot-' + slotType);
                                    const label = slotDiv.querySelector('p').textContent;
                                    const height = getSlotHeightClass(slotType);
                                    
                                    slotDiv.innerHTML = `
                                        <img src="${{e.target.result}}" alt="${{label}}" class="w-full ${{height}} object-contain rounded mb-2">
                                        <p class="text-center text-sm font-semibold text-gray-600">${{label}}</p>
                                        <button type="button"
                                                onclick="event.stopPropagation(); removeNewSlotImage('${{slotType}}')"
                                                class="absolute top-2 right-2 btn btn-xs btn-error text-white"
                                                title="Remover imagem">
                                            <span class="material-icons text-xs">delete</span>
                                        </button>
                                        <div class="absolute top-2 left-2 badge badge-success gap-1">
                                            <span class="material-icons text-xs">check</span>
                                            Nova
                                        </div>
                                    `;
                                    slotDiv.classList.remove('border-dashed', 'bg-gray-50', 'hover:bg-gray-100');
                                    slotDiv.classList.add('border-gray-300', 'bg-white');
                                    slotDiv.classList.remove('opacity-50');
                                    
                                    // Re-attach the input element
                                    slotDiv.appendChild(input);
                                }};
                                reader.readAsDataURL(input.files[0]);
                            }}
                        }}
                    </script>
                    """)
                )

    def clean_technical_diagnosis(self):
        value = self.cleaned_data.get("technical_diagnosis")
        return sentence_case(value) if value else value

    def clean(self):
        cleaned_data = super().clean()

        collaborator_ids = [cid for cid in self.request.POST.getlist("collaborators_list") if cid.strip()]
        if not collaborator_ids:
            self.add_error("collaborator", "Selecione pelo menos um colaborador para continuar.")

        if not self.files:
            return cleaned_data

        new_additional_images = self.files.getlist("images")
        if new_additional_images:
            _validate_uploaded_files(new_additional_images)

        uploaded_slot_files = []
        uploaded_slot_types = set()
        for slot_type in SLOT_IMAGE_TYPES:
            uploaded_file = self.files.get(f"image_{slot_type}")
            if uploaded_file:
                uploaded_slot_files.append(uploaded_file)
                uploaded_slot_types.add(slot_type)

        if uploaded_slot_files:
            _validate_uploaded_images(uploaded_slot_files)

        if self.instance and self.instance.pk:
            existing_images = self.instance.budget_image.all()
            existing_additional_count = existing_images.exclude(image_type__in=SLOT_IMAGE_TYPES).count()

            additional_delete_ids = [img_id for img_id in self.request.POST.getlist("images_to_delete") if img_id.strip()]
            additional_delete_count = existing_images.filter(id__in=additional_delete_ids).exclude(image_type__in=SLOT_IMAGE_TYPES).count()

            current_slot_types = set(existing_images.filter(image_type__in=SLOT_IMAGE_TYPES).values_list("image_type", flat=True))
            slot_delete_ids = [img_id for img_id in self.request.POST.getlist("slot_to_delete") if img_id.strip()]
            slot_types_to_delete = set(existing_images.filter(id__in=slot_delete_ids, image_type__in=SLOT_IMAGE_TYPES).values_list("image_type", flat=True))

            final_slot_types = (current_slot_types - slot_types_to_delete) | uploaded_slot_types
            final_additional_count = existing_additional_count - additional_delete_count + len(new_additional_images)
            final_count = len(final_slot_types) + final_additional_count
        else:
            final_count = len(uploaded_slot_types) + len(new_additional_images)

        if final_count > MAX_BUDGET_IMAGES:
            raise forms.ValidationError(f"Máximo de {MAX_BUDGET_IMAGES} anexos permitido. Você terá {final_count} anexos após esta operação.")

        return cleaned_data

    def save(self, commit=True):
        budget = super().save(commit=commit)

        # Processamento dos Colaboradores
        if "collaborators_list" in self.request.POST:
            collaborator_ids = [cid for cid in self.request.POST.getlist("collaborators_list") if cid.strip()]
            if collaborator_ids:
                budget.collaborators.set(collaborator_ids)
            else:
                budget.collaborators.clear()

            if budget.status == BudgetStatus.APPROVED:
                workorder = budget.workorders.order_by("id").first()
                if workorder is not None:
                    workorder.sync_from_budget()

        # Processamento dos Defeitos (Somente no Save final)
        if "defects_list" in self.request.POST:
            defect_names = self.request.POST.getlist("defects_list")

            # Sincronização: remove antigos e adiciona novos
            budget.defects.all().delete()
            for name in defect_names:
                if name.strip():
                    Defect.objects.create(workshop=self.workshop, budget=budget, name=name.strip())

        # Handle slot image deletions
        slots_to_delete = self.request.POST.getlist("slot_to_delete")
        if slots_to_delete:
            image_ids = [img_id for img_id in slots_to_delete if img_id.strip()]
            if image_ids:
                BudgetImage.objects.filter(id__in=image_ids, budget=budget, image_type__in=SLOT_IMAGE_TYPES).delete()

        # Handle slot image uploads (update or create)
        slot_uploads = []
        for slot_type in SLOT_IMAGE_TYPES:
            file_key = f"image_{slot_type}"
            if file_key in self.request.FILES:
                uploaded_file = self.request.FILES[file_key]
                if uploaded_file:
                    slot_uploads.append((slot_type, uploaded_file))

        if slot_uploads:
            _validate_uploaded_images([uploaded_file for _, uploaded_file in slot_uploads])
            for slot_type, uploaded_file in slot_uploads:
                # Delete existing image of this type if exists (should be handled by unique constraint)
                BudgetImage.objects.filter(budget=budget, image_type=slot_type).delete()

                # Create new image
                BudgetImage.objects.create(workshop=self.workshop, budget=budget, content=uploaded_file.read(), content_name=uploaded_file.name, content_type=getattr(uploaded_file, "content_type", "image/jpeg"), image_type=slot_type)

        # Handle additional image deletion
        images_to_delete = self.request.POST.getlist("images_to_delete")
        if images_to_delete:
            image_ids = [img_id for img_id in images_to_delete if img_id.strip()]
            if image_ids:
                BudgetImage.objects.filter(id__in=image_ids, budget=budget).exclude(image_type__in=SLOT_IMAGE_TYPES).delete()

        # Handle new additional images upload
        new_images = self.request.FILES.getlist("images")
        if new_images:
            _validate_uploaded_files(new_images)

            for new_image in new_images:
                if new_image and hasattr(new_image, "read"):
                    BudgetImage.objects.create(workshop=self.workshop, budget=budget, content=new_image.read(), content_name=new_image.name, content_type=getattr(new_image, "content_type", "application/octet-stream"), image_type=BudgetImageType.ADDITIONAL)

        return budget
