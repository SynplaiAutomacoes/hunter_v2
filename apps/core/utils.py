from io import BytesIO

from crispy_forms.layout import HTML
from django.template.loader import get_template
from xhtml2pdf import pisa


def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()

    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)

    if not pdf.err:
        return result
    return None


def alert_confirm_layout(title="Deseja realmente prosseguir?", func_name="customConfirm"):
    """
    Gera um layout HTML/JS que pode ser chamado em qualquer form.
    Usa o <dialog> nativo do HTML5 (compatível com DaisyUI/Tailwind).
    """
    return HTML(f"""
    <dialog id="alert_confirm_modal" class="modal">
        <div class="modal-box border-t-4 border-warning">
            <h3 class="font-bold text-lg text-center" id="confirm-title">{title}</h3>
            <div class="modal-action flex justify-center gap-4">
                <button type="button" class="btn btn-ghost" onclick="alert_confirm_modal.close()">Cancelar</button>
                <button type="button" class="btn btn-warning" id="confirm-yes">Confirmar</button>
            </div>
        </div>
    </dialog>

    <script>
        function {func_name}(customTitle) {{
            return new Promise((resolve) => {{
                const modal = document.getElementById('alert_confirm_modal');
                const titleElem = document.getElementById('confirm-title');
                const yesBtn = document.getElementById('confirm-yes');

                if (customTitle) titleElem.innerText = customTitle;

                modal.showModal();

                // Limpa eventos anteriores para não duplicar chamadas
                const newYesBtn = yesBtn.cloneNode(true);
                yesBtn.parentNode.replaceChild(newYesBtn, yesBtn);

                newYesBtn.addEventListener('click', () => {{
                    modal.close();
                    resolve(true);
                }});
            }});
        }}
        
        document.body.addEventListener('htmx:confirm', function(evt) {{
            // Verifica se o elemento tem o nosso atributo de confirmação
            const confirmMessage = evt.detail.elt.getAttribute('data-confirm');
            if (!confirmMessage) return;
    
            // Impede o envio imediato do HTMX
            evt.preventDefault();
    
            // Chama o nosso modal customizado
            customConfirm(confirmMessage).then(function(confirmed) {{
                if (confirmed) {{
                    // Se confirmado, dispara a requisição HTMX originalmente interrompida
                    evt.detail.issueRequest();
                }}
            }});
        }});
    </script>
    """)