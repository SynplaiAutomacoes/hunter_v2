document.addEventListener('DOMContentLoaded', function() {
    const cepField = document.querySelector('#id_cep');
    const btnSubmit = document.querySelector('#submit-id-submit');

    if (!cepField) return;

    cepField.addEventListener('blur', function() {
        const cep = this.value.replace(/\D/g, '');

        if (cep.length === 8) {
            if (btnSubmit) {
                // Bloqueia o salvamento e indica carregamento
                btnSubmit.disabled = true;
                btnSubmit.innerHTML = 'Buscando CEP...';
                cepField.classList.add('loading');
            }

            // Chamada à API ViaCEP
            fetch(`https://viacep.com.br/ws/${cep}/json/`)
                .then(response => response.json())
                .then(data => {
                    if (!data.erro) {
                        // Mapeamento dinâmico para garantir que pegamos os elementos atuais do DOM
                        const map = {
                            '#id_logradouro': data.logradouro || "",
                            '#id_bairro': data.bairro || "",
                            '#id_cidade': data.localidade || "",
                            '#id_estado': data.uf | "",
                            '#id_complemento': data.complemento || ""
                        };

                        for (const [selector, value] of Object.entries(map)) {
                            const el = document.querySelector(selector);
                            if (el) {
                                el.value = value;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        }

                        // Foca no número
                        setTimeout(() => document.querySelector('#id_numero')?.focus(), 100);
                    } else {
                        alert("CEP não encontrado.");
                        cepField.value = "";
                        cepField.focus();
                    }
                })
                .catch(error => {
                    console.error('Erro na busca do CEP:', error);
                    alert("Erro ao buscar CEP. Verifique sua conexão.");
                })
                .finally(() => {
                    // Libera o botão independente do resultado
                    btnSubmit.disabled = false;
                    btnSubmit.innerHTML = 'Salvar';
                });
        }
    });
});