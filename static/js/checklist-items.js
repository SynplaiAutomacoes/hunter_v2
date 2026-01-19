document.addEventListener('DOMContentLoaded', function() {
    const tableBody = document.getElementById('itens-tabela-body');
    const btnAdd = document.getElementById('btn-add-item');

    const inputAgrupamento = document.getElementById('novo-agrupamento');
    const inputDescricao = document.getElementById('novo-item-descricao');
    const inputTipo = document.getElementById('novo-tipo-resposta');

    function addItem(agrupamento, descricao, tipoValor, tipoTexto) {
        if (!descricao.trim()) return;

        const rowCount = tableBody.rows.length + 1;
        const row = document.createElement('tr');
        row.className = "hover:bg-base-200 transition-colors";
        row.innerHTML = `
            <input type="hidden" name="agrupamento" value="${agrupamento}">
            <input type="hidden" name="descricao" value="${descricao}">
            <input type="hidden" name="tipo_resposta" value="${tipoValor}">

            <td class="font-mono text-xs">${rowCount}</td>
            <td class="font-mono text-xs">${agrupamento || 'Sem Grupo'} / ${descricao}</td>
            <td class="font-mono text-xs">${tipoTexto}</td>
            <td><button type="button" class="btn btn-ghost btn-xs text-error btn-remove">Remover</button></td>
        `;

        // Listener para remover
        row.querySelector('.btn-remove').addEventListener('click', function() {
            row.remove();
            reorderRows();
        });

        tableBody.appendChild(row);
        inputDescricao.value = '';
    }

    window.reorderRows = function() {
        const rows = tableBody.querySelectorAll('tr');
        rows.forEach((row, index) => {
            row.querySelector('td:first-child').textContent = index + 1;
        });
    }

    if (btnAdd) {
        btnAdd.addEventListener('click', function(e) {
            e.preventDefault();
            const agrupamento = inputAgrupamento.value;
            const descricao = inputDescricao.value;
            const tipoValor = inputTipo.value;
            let tipoTexto = "";
            if (inputTipo.tagName === 'SELECT') {
                tipoTexto = inputTipo.options[inputTipo.selectedIndex].text;
            } else {
                tipoTexto = inputTipo.value || "Padrão";
            }

            if (!descricao) {
                inputDescricao.focus();
                inputDescricao.classList.add('input-error');
                return;
            }
            inputDescricao.classList.remove('input-error');
            addItem(agrupamento, descricao, tipoValor, tipoTexto);
        });
    }
});