from __future__ import annotations

# Códigos cIndOp (Anexo VII — IndOp IBS/CBS, Portal Nacional da NFS-e / LC 214/2025).
# Usados no campo servico.cod_indicador_operacao do Padrão Nacional.

NFSE_COD_INDICADOR_OPERACAO_CHOICES: list[tuple[str, str]] = [
    ("", "—"),
    ("010101", "010101 — Bem móvel material (retirada no estabelecimento)"),
    ("010102", "010102 — Bem móvel material (retirada fora do estabelecimento)"),
    ("010103", "010103 — Bem móvel material (entrega em endereço fornecido)"),
    ("010104", "010104 — Bem móvel material (licitação / leilão judicial)"),
    ("010105", "010105 — Bem móvel material (irregularidade documental)"),
    ("010106", "010106 — Locação de bem móvel (aquisição centralizada)"),
    ("010201", "010201 — Veículo automotor (entrega ao destinatário)"),
    ("010202", "010202 — Veículo automotor em licitação / leilão judicial"),
    ("020101", "020101 — Operação com bem imóvel / direito relacionado"),
    ("020201", "020201 — Serviço físico sobre bem imóvel"),
    ("020202", "020202 — Serviço sobre BICE (bem imóvel especial)"),
    ("020301", "020301 — Administração / intermediação de imóvel"),
    ("020401", "020401 — Locação / passagem / uso de ferrovia, rodovia, postes etc."),
    ("030101", "030101 — Serviço físico sobre a pessoa (no estabelecimento)"),
    ("030102", "030102 — Serviço físico sobre a pessoa (no endereço do adquirente)"),
    ("030103", "030103 — Serviço físico sobre a pessoa (no endereço do destinatário)"),
    ("030104", "030104 — Serviço físico sobre a pessoa (endereço diverso)"),
    ("040101", "040101 — Feiras, exposições, congressos e congêneres"),
    ("050101", "050101 — Serviço físico sobre bem móvel (no estabelecimento)"),
    ("050102", "050102 — Serviço físico sobre bem móvel (no endereço do adquirente)"),
    ("050103", "050103 — Serviço físico sobre bem móvel (no endereço do destinatário)"),
    ("050104", "050104 — Serviço físico sobre bem móvel (endereço diverso)"),
    ("050201", "050201 — Serviços portuários"),
    ("060101", "060101 — Transporte de passageiros"),
    ("070101", "070101 — Transporte de carga (entrega)"),
    ("070102", "070102 — Transporte de carga (retirada)"),
    ("080101", "080101 — Exploração de via"),
    ("090101", "090101 — Telefonia fixa / comunicação por cabos e fibras"),
    ("090102", "090102 — Telefonia fixa / comunicação (aquisição centralizada)"),
    ("100101", "100101 — Cessão de espaço publicitário (onerosa)"),
    ("100102", "100102 — Cessão de espaço publicitário (onerosa, adquirente exterior)"),
    ("100201", "100201 — Cessão de espaço publicitário (não onerosa)"),
    ("100301", "100301 — Demais serviços (onerosa)"),
    ("100302", "100302 — Demais serviços (onerosa, adquirente exterior)"),
    ("100401", "100401 — Demais serviços (não onerosa)"),
    ("100501", "100501 — Demais bens móveis imateriais / direitos (onerosa)"),
    ("100502", "100502 — Demais bens móveis imateriais / direitos (onerosa, exterior)"),
    ("100601", "100601 — Demais bens móveis imateriais / direitos (não onerosa)"),
    ("110101", "110101 — Água, gás ou energia (consumo)"),
    ("110201", "110201 — Água, gás ou energia (sem consumo efetivo)"),
    ("120101", "120101 — Energia elétrica (aquisição multilateral)"),
    ("130101", "130101 — Transporte dutoviário de gás (capacidade de entrada)"),
    ("130201", "130201 — Transporte dutoviário de gás (capacidade de saída)"),
]

NFSE_COD_INDICADOR_OPERACAO_VALUES: frozenset[str] = frozenset(code for code, _label in NFSE_COD_INDICADOR_OPERACAO_CHOICES if code)


def is_valid_nfse_cod_indicador_operacao(value: object) -> bool:
    code = "".join(char for char in str(value or "") if char.isdigit())
    return code in NFSE_COD_INDICADOR_OPERACAO_VALUES


def normalize_nfse_cod_indicador_operacao(value: object) -> str:
    """Keep digits only (cIndOp is 6 digits). Unknown codes are preserved for sync/display."""
    return "".join(char for char in str(value or "") if char.isdigit())[:6]
