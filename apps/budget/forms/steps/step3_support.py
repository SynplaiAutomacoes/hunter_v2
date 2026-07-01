# ruff: noqa: F401,F403,F405
from .common import *

__all__ = [
    "SLOT_IMAGE_TYPES",
    "SLOT_LAYOUT_CONFIG",
    "SLOT_PLACEHOLDER_PATHS",
    "_format_file_size",
    "_build_step3_slot_fallback_html",
    "_build_step3_images_initial_html",
]


SLOT_IMAGE_TYPES = [
    BudgetImageType.PRINCIPAL,
    BudgetImageType.FRONTAL,
    BudgetImageType.TRASEIRA,
    BudgetImageType.DIREITA,
    BudgetImageType.ESQUERDA,
    BudgetImageType.PAINEL,
    BudgetImageType.CHASSI,
    BudgetImageType.MOTOR,
]

SLOT_LAYOUT_CONFIG = [
    {"type": BudgetImageType.PRINCIPAL, "label": "Principal", "full_width": True},
    {"type": BudgetImageType.FRONTAL, "label": "Frontal", "full_width": False},
    {"type": BudgetImageType.TRASEIRA, "label": "Traseira", "full_width": False},
    {"type": BudgetImageType.DIREITA, "label": "Direita", "full_width": False},
    {"type": BudgetImageType.ESQUERDA, "label": "Esquerda", "full_width": False},
    {"type": BudgetImageType.PAINEL, "label": "Painel", "full_width": True},
    {"type": BudgetImageType.CHASSI, "label": "Chassi", "full_width": True},
    {"type": BudgetImageType.MOTOR, "label": "Motor", "full_width": True},
]

SLOT_PLACEHOLDER_PATHS = {
    BudgetImageType.PRINCIPAL: "image/principal.png",
    BudgetImageType.FRONTAL: "image/frontal.png",
    BudgetImageType.TRASEIRA: "image/traseira.png",
    BudgetImageType.DIREITA: "image/direita.png",
    BudgetImageType.ESQUERDA: "image/esquerda.png",
    BudgetImageType.PAINEL: "image/painel.png",
    BudgetImageType.CHASSI: "image/chassi.png",
    BudgetImageType.MOTOR: "image/motor.png",
}


def _format_file_size(size_bytes: int) -> str:
    units = ["B", "kB", "MB", "GB", "TB"]
    size = float(max(size_bytes, 0))
    unit_index = 0

    while size >= 1000 and unit_index < len(units) - 1:
        size /= 1000
        unit_index += 1

    if size >= 999.5 and unit_index < len(units) - 1:
        size /= 1000
        unit_index += 1

    if unit_index == 0:
        formatted = str(int(size))
    elif size >= 100:
        formatted = str(int(round(size)))
    else:
        formatted = f"{size:.1f}".rstrip("0").rstrip(".")

    return f"{formatted} {units[unit_index]}"


def _build_step3_slot_fallback_html(slot_placeholder_urls):
    slots_html = []

    principal = SLOT_LAYOUT_CONFIG[0]
    principal_src = slot_placeholder_urls[principal["type"]]
    slots_html.append(
        f"""
        <div class="mb-4">
            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                 id="slot-{principal["type"]}"
                 onclick="document.getElementById('file-input-{principal["type"]}').click()">
                <div class="flex flex-col items-center justify-center h-48">
                    <img src="{principal_src}" alt="Placeholder {principal["label"]}" class="w-full h-32 object-contain rounded mb-2 opacity-40">
                    <p class="text-center text-sm font-semibold text-gray-600">{principal["label"]}</p>
                    <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                </div>
                <input type="file" id="file-input-{principal["type"]}" name="image_{principal["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{principal["type"]}', this)">
            </div>
        </div>
        """
    )

    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    for slot in SLOT_LAYOUT_CONFIG[1:3]:
        placeholder_src = slot_placeholder_urls[slot["type"]]
        slots_html.append(
            f"""
            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                 id="slot-{slot["type"]}"
                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                <div class="flex flex-col items-center justify-center h-32">
                    <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                    <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                    <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                </div>
                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot["type"]}', this)">
            </div>
            """
        )
    slots_html.append("</div>")

    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    for slot in SLOT_LAYOUT_CONFIG[3:5]:
        placeholder_src = slot_placeholder_urls[slot["type"]]
        slots_html.append(
            f"""
            <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-3 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                 id="slot-{slot["type"]}"
                 onclick="document.getElementById('file-input-{slot["type"]}').click()">
                <div class="flex flex-col items-center justify-center h-32">
                    <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-16 object-contain rounded mb-1 opacity-40">
                    <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                    <p class="text-center text-xs text-gray-400">Clique para adicionar</p>
                </div>
                <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot["type"]}', this)">
            </div>
            """
        )
    slots_html.append("</div>")

    for slot in SLOT_LAYOUT_CONFIG[5:]:
        placeholder_src = slot_placeholder_urls[slot["type"]]
        slots_html.append(
            f"""
            <div class="mb-4">
                <div class="relative border-2 border-dashed border-gray-300 rounded-lg p-4 bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                     id="slot-{slot["type"]}"
                     onclick="document.getElementById('file-input-{slot["type"]}').click()">
                    <div class="flex flex-col items-center justify-center h-40">
                        <img src="{placeholder_src}" alt="Placeholder {slot["label"]}" class="w-full h-24 object-contain rounded mb-2 opacity-40">
                        <p class="text-center text-sm font-semibold text-gray-600">{slot["label"]}</p>
                        <p class="text-center text-xs text-gray-400 mt-1">Clique para adicionar</p>
                    </div>
                    <input type="file" id="file-input-{slot["type"]}" name="image_{slot["type"]}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot["type"]}', this)">
                </div>
            </div>
            """
        )

    return "".join(slots_html)


def _build_step3_images_initial_html(budget, slot_placeholder_urls):
    images_by_type = {}
    additional_images = []

    if budget and getattr(budget, "pk", None):
        for existing_image in budget.ordered_images:
            if existing_image.image_type in SLOT_IMAGE_TYPES and existing_image.content and existing_image.image_type not in images_by_type:
                images_by_type[existing_image.image_type] = existing_image
            elif existing_image.content:
                additional_images.append(existing_image)

    def render_slot(slot):
        slot_type = slot["type"]
        slot_label = slot["label"]
        slot_image = images_by_type.get(slot_type)

        is_main = slot_type == BudgetImageType.PRINCIPAL
        is_bottom_full = slot_type in {BudgetImageType.PAINEL, BudgetImageType.CHASSI, BudgetImageType.MOTOR}

        padding = "p-4" if (is_main or is_bottom_full) else "p-3"
        height = "h-48" if is_main else ("h-40" if is_bottom_full else "h-32")
        empty_img_height = "h-32" if is_main else ("h-24" if is_bottom_full else "h-16")

        if slot_image and slot_image.content:
            img_data = base64.b64encode(slot_image.content).decode("utf-8")
            img_src = f"data:{slot_image.content_type or 'image/jpeg'};base64,{img_data}"
            return f"""
                <div class="mb-4">
                    <div class="relative border-2 border-gray-300 rounded-lg {padding} bg-white hover:border-primary transition-colors cursor-pointer group" 
                         id="slot-{slot_type}"
                         onclick="document.getElementById('file-input-{slot_type}').click()">
                        <img src="{img_src}" alt="{slot_label}" class="w-full {height} object-contain rounded mb-2">
                        <p class="text-center text-sm font-semibold text-gray-600">{slot_label}</p>
                        <input type="file" id="file-input-{slot_type}" name="image_{slot_type}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot_type}', this)">
                        <input type="hidden" id="delete-slot-{slot_type}" name="slot_to_delete" value="">
                        <button type="button" 
                                onclick="event.stopPropagation(); deleteSlotImage('{slot_type}', '{slot_image.id}')"
                                class="absolute top-2 right-2 btn btn-xs btn-error gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <span class="material-icons text-xs">delete</span>
                        </button>
                    </div>
                </div>
            """

        placeholder_src = slot_placeholder_urls[slot_type]
        hint_margin = " mt-1" if (is_main or is_bottom_full) else ""
        return f"""
            <div class="mb-4">
                <div class="relative border-2 border-dashed border-gray-300 rounded-lg {padding} bg-gray-50 hover:bg-gray-100 hover:border-primary transition-all cursor-pointer" 
                     id="slot-{slot_type}"
                     onclick="document.getElementById('file-input-{slot_type}').click()">
                    <div class="flex flex-col items-center justify-center {height}">
                        <img src="{placeholder_src}" alt="Placeholder {slot_label}" class="w-full {empty_img_height} object-contain rounded mb-1 opacity-40">
                        <p class="text-center text-sm font-semibold text-gray-600">{slot_label}</p>
                        <p class="text-center text-xs text-gray-400{hint_margin}">Clique para adicionar</p>
                    </div>
                    <input type="file" id="file-input-{slot_type}" name="image_{slot_type}" accept="image/*" class="hidden" onchange="previewSlotImage('{slot_type}', this)">
                </div>
            </div>
        """

    slots_html = [render_slot(SLOT_LAYOUT_CONFIG[0])]
    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[1]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[2]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append("</div>")
    slots_html.append('<div class="grid grid-cols-2 gap-4 mb-4">')
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[3]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append(render_slot(SLOT_LAYOUT_CONFIG[4]).replace('class="mb-4"', 'class="mb-0"', 1))
    slots_html.append("</div>")
    for slot in SLOT_LAYOUT_CONFIG[5:]:
        slots_html.append(render_slot(slot))

    additional_html = []
    for img in additional_images:
        file_name = escape(img.content_name or f"Arquivo {img.id}")
        file_size = _format_file_size(len(img.content or b""))
        additional_html.append(
            f"""
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
            """
        )

    return "".join(slots_html), "".join(additional_html)
