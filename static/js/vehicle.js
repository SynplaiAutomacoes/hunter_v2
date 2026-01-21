document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === "vehicle-list") {
        // Atualiza o TOTAL_FORMS com a quantidade real de .vehicle-item na tela
        const totalForms = document.getElementById('id_vehicles-TOTAL_FORMS');
        const currentForms = document.querySelectorAll('#vehicle-list .vehicle-item').length;
        totalForms.value = currentForms;
    }
});