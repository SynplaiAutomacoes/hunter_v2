window.reorderRows = function() {
    const tableBody = document.getElementById('itens-tabela-body');
    const rows = tableBody.querySelectorAll('tr');
    rows.forEach((row, index) => {
        const indexCell = row.querySelector('.row-index');
        if (indexCell) indexCell.textContent = index + 1;
    });
}

// Executar ao carregar a página para numerar os itens vindos do banco
document.addEventListener('DOMContentLoaded', reorderRows);