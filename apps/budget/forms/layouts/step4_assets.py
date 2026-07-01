def build_step4_assets_html(budget_summary_url: str) -> str:
    return f"""
            <script>
            (function() {{
                document.body.addEventListener('update-summary', function() {{
                    // Recarrega apenas a coluna de resumo via HTMX
                    htmx.ajax('GET', '{budget_summary_url}', {{
                        target: '#budget-summary',
                        swap: 'innerHTML'
                    }});
                }});

                function setupBatchDeleteSelection(config) {{
                    const listBody = document.getElementById(config.listBodyId);
                    const selectAll = document.getElementById(config.selectAllId);
                    const deleteBtn = document.getElementById(config.deleteBtnId);

                    if (!listBody || !selectAll || !deleteBtn) {{
                        return;
                    }}

                    function getCheckboxes() {{
                        return Array.from(listBody.querySelectorAll(config.checkboxSelector));
                    }}

                    function updateState() {{
                        const checkboxes = getCheckboxes();
                        const selectedCount = checkboxes.filter((cb) => cb.checked).length;

                        const canDeleteBatch = selectedCount > 1;
                        deleteBtn.classList.toggle('hidden', !canDeleteBatch);
                        deleteBtn.disabled = !canDeleteBatch;

                        if (checkboxes.length === 0) {{
                            selectAll.checked = false;
                            selectAll.indeterminate = false;
                            selectAll.disabled = true;
                            return;
                        }}

                        selectAll.disabled = false;
                        const allChecked = selectedCount === checkboxes.length;
                        const someChecked = selectedCount > 0 && !allChecked;
                        selectAll.checked = allChecked;
                        selectAll.indeterminate = someChecked;
                    }}

                    selectAll.addEventListener('change', function(event) {{
                        const checkboxes = getCheckboxes();
                        checkboxes.forEach((checkbox) => {{
                            checkbox.checked = event.target.checked;
                        }});
                        updateState();
                    }});

                    listBody.addEventListener('change', function(event) {{
                        if (!event.target.matches(config.checkboxSelector)) {{
                            return;
                        }}
                        updateState();
                    }});

                    listBody.addEventListener('htmx:afterSwap', function() {{
                        updateState();
                    }});

                    updateState();
                }}

                setupBatchDeleteSelection({{
                    listBodyId: 'product-list-body',
                    selectAllId: 'select-all-products',
                    deleteBtnId: 'delete-selected-products-btn',
                    checkboxSelector: '.budget-product-select',
                }});

                setupBatchDeleteSelection({{
                    listBodyId: 'service-list-body',
                    selectAllId: 'select-all-services',
                    deleteBtnId: 'delete-selected-services-btn',
                    checkboxSelector: '.budget-service-select',
                }});

                setupBatchDeleteSelection({{
                    listBodyId: 'kit-list-body',
                    selectAllId: 'select-all-kits',
                    deleteBtnId: 'delete-selected-kits-btn',
                    checkboxSelector: '.budget-kit-select',
                }});
            }})();
            </script>
    """
