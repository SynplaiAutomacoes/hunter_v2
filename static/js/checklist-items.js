window.reorderRows = function() {
    const tableBody = document.getElementById('itens-tabela-body');
    const rows = tableBody.querySelectorAll('tr');
    rows.forEach((row, index) => {
        const indexCell = row.querySelector('.row-index');
        if (indexCell) indexCell.textContent = index + 1;
    });
}

document.addEventListener('DOMContentLoaded', reorderRows);