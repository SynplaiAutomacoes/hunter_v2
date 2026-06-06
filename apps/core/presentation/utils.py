from crispy_forms.layout import HTML


def alert_confirm_layout(title="Deseja realmente prosseguir?", func_name="customConfirm"):
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
                const modal = document.getElementById('alert_confirm_modal');
                const titleElem = document.getElementById('confirm-title');
                const yesBtn = document.getElementById('confirm-yes');
                const cancelBtn = modal ? modal.querySelector('.modal-action .btn-ghost') : null;

                const normalizedOptions = (typeof options === 'object' && options !== null) ? options : {{}};
                const singleClose = normalizedOptions.singleClose === true;
                const confirmText = normalizedOptions.confirmText || 'Confirmar';
                const cancelText = normalizedOptions.cancelText || 'Cancelar';

                if (customTitle) titleElem.innerText = customTitle;

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

                modal.showModal();

                const newYesBtn = yesBtn.cloneNode(true);
                yesBtn.parentNode.replaceChild(newYesBtn, yesBtn);

                let isResolved = false;

                newYesBtn.addEventListener('click', () => {{
                    modal.close();
                    isResolved = true;
                    resolve(!singleClose);
                }});

                modal.addEventListener('close', () => {{
                    if (isResolved) return;
                    resolve(false);
                }}, {{ once: true }});
            }});
        }}

        document.body.addEventListener('htmx:confirm', function(evt) {{
            const confirmMessage = evt.detail.elt.getAttribute('data-confirm');
            if (!confirmMessage) return;
            evt.preventDefault();
            customConfirm(confirmMessage).then(function(confirmed) {{
                if (confirmed) {{
                    evt.detail.issueRequest();
                }}
            }});
        }});
    </script>
    """)
