import re

from crispy_forms.layout import HTML


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
                <button type="button" class="btn btn-ghost" data-allow-locked="1" onclick="alert_confirm_modal.close()">Cancelar</button>
                <button type="button" class="btn btn-warning" id="confirm-yes" data-allow-locked="1">Confirmar</button>
            </div>
        </div>
    </dialog>

    <script>
        function {func_name}(customTitle, options = {{}}) {{
            return new Promise((resolve) => {{
                const modals = Array.from(document.querySelectorAll('dialog#alert_confirm_modal'));
                const modal = (modals.filter((item) => !item.closest('.hidden')).pop()) || null;
                const titleElem = modal ? modal.querySelector('#confirm-title') : null;
                const yesBtn = modal ? modal.querySelector('#confirm-yes') : null;
                const cancelBtn = modal ? modal.querySelector('.modal-action .btn-ghost') : null;

                const normalizedOptions = (typeof options === 'object' && options !== null) ? options : {{}};
                const singleClose = normalizedOptions.singleClose === true;
                const confirmText = normalizedOptions.confirmText || 'Confirmar';
                const cancelText = normalizedOptions.cancelText || 'Cancelar';

                if (!modal || !yesBtn) {{
                    resolve(!singleClose && window.confirm(customTitle || 'Deseja realmente prosseguir?'));
                    return;
                }}

                if (customTitle && titleElem) titleElem.innerText = customTitle;

                if (cancelBtn) {{
                    cancelBtn.textContent = cancelText;
                    cancelBtn.classList.toggle('hidden', singleClose);
                    cancelBtn.disabled = false;
                }}

                if (yesBtn) {{
                    yesBtn.textContent = singleClose ? (normalizedOptions.closeText || 'Fechar') : confirmText;
                    yesBtn.classList.toggle('btn-primary', singleClose);
                    yesBtn.classList.toggle('btn-warning', !singleClose);
                    yesBtn.disabled = false;
                }}

                try {{
                    modal.showModal();
                }} catch (error) {{
                    resolve(!singleClose && window.confirm(customTitle || 'Deseja realmente prosseguir?'));
                    return;
                }}

                // Limpa eventos anteriores para não duplicar chamadas
                const newYesBtn = yesBtn.cloneNode(true);
                yesBtn.parentNode.replaceChild(newYesBtn, yesBtn);

                let isResolved = false;

                newYesBtn.addEventListener('click', () => {{
                    isResolved = true;
                    resolve(!singleClose);
                    modal.close();
                }});

                modal.addEventListener('close', () => {{
                    if (isResolved) {{
                        return;
                    }}
                    resolve(false);
                }}, {{ once: true }});
            }});
        }}

        if (!window.__hunterHtmxConfirmBound) {{
            window.__hunterHtmxConfirmBound = true;
            document.body.addEventListener('htmx:confirm', function(evt) {{
                const confirmMessage = evt.detail.elt.getAttribute('data-confirm');
                if (!confirmMessage) return;

                evt.preventDefault();
                {func_name}(confirmMessage).then(function(confirmed) {{
                    if (confirmed) {{
                        evt.detail.issueRequest(true);
                    }}
                }});
            }});
        }}
    </script>
    """)


def clean_id(value):
    """Remove pontuação de milhar e espaços de uma string de ID/Índice."""
    if value is None:
        return None
    # Remove qualquer caractere que não seja número (como pontos e espaços)
    return re.sub(r"\D", "", str(value))
