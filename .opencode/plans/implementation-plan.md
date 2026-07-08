# Resumo

## Objetivo

Garantir que, ao finalizar uma WorkOrder (entregar o veículo), as peças utilizadas sejam debitadas do estoque, criando movimentações de saída (EXIT) e reduzindo as quantidades dos produtos no estoque.

## Requisitos

### Funcionais

- RF1: Ao aprovar uma WorkOrder manualmente (via `UpdateWorkOrderStatusView` com status `approve`), os itens com produto devem ser debitados do estoque.
- RF2: Ao aprovar uma WorkOrder via assinatura digital (webhook Supersign), os itens com produto devem ser debitados do estoque.
- RF3: Se o estoque for insuficiente para algum produto, a aprovação deve ser bloqueada com mensagem clara.
- RF4: Ao reabrir uma WorkOrder, os movimentos de estoque devem ser estornados (reversão).

### Não Funcionais

- RNF1: A dedução de estoque deve ser atômica — ou tudo é deduzido, ou nada (transação).
- RNF2: A operação deve usar `select_for_update` para evitar condições de corrida.
- RNF3: A webhook deve ser resiliente: se a dedução de estoque falhar, a assinatura digital ainda deve ser registrada, e o erro deve ser logado.

## Premissas

- P1: Produtos em WorkOrderItems estão vinculados a registros `Product` no catálogo.
- P2: Cada `Product` possui um registro `StockProduct` correspondente na oficina.
- P3: O campo `current_quantity` em `StockProduct` reflete o saldo atual em estoque.
- P4: O fluxo de assinatura digital só é enviado se não houver blockers (pagamento completo ou garantia/cortesia).

## Dependências

- D1: `apps.workorder.approval.approve_workorder_with_stock` — função existente que faz a checagem e dedução.
- D2: `apps.stock.models.StockMovement` — modelo para registrar movimentações.
- D3: `apps.stock.models.StockProduct` — modelo com o saldo de estoque.

## Riscos

| Risco | Impacto | Probabilidade | Mitigação |
|---|---|---|---|
| Webhook pode receber evento antes do pagamento estar completo | Médio | Baixa | `mark_signature_approved` já trata early return; só chama `approve_workorder_with_stock` se for pagamento completo |
| Concorrência entre webhook e entrega manual | Alto | Baixa | Usar `select_for_update` + transação; após signature, status APPROVED bloqueia entrega manual |
| Produto deletado do catálogo após criação da WorkOrder | Médio | Baixa | `WorkOrderItem.product` usa `SET_NULL`; nesse caso o produto não é debitado (entity_id == None) |

# Plano de Implementação

## Etapa 1 — Consumir estoque na aprovação por assinatura digital

### Objetivo

Corrigir o fluxo de aprovação via webhook Supersign (`ENVELOPE_COMPLETED`) para que o estoque seja debitado quando a WorkOrder for aprovada por assinatura digital.

Atualmente:
- `process_supersign_webhook_payload` → `workorder.mark_signature_approved()` → atualiza status mas **não consome estoque**.

Após a correção:
- `process_supersign_webhook_payload` → `approve_workorder_with_stock()` → deduz estoque + cria `StockMovement` → `workorder.mark_signature_approved()` → registra assinatura.

### Alterações

1. **`apps/core/infrastructure/services/supersign.py`** (linha 162-165):
   - Importar `approve_workorder_with_stock` e `WorkOrderApprovalError`
   - Envolver a chamada `approve_workorder_with_stock` em try/except para capturar `WorkOrderApprovalError`
   - Chamar `approve_workorder_with_stock` ANTES de `workorder.mark_signature_approved()`
   - Logar warning se estoque for insuficiente, mas continuar o fluxo

### Arquivos Impactados

| Arquivo | Impacto |
|---|---|
| `apps/core/infrastructure/services/supersign.py` | Adicionar import + lógica no `process_supersign_webhook_payload` |

### Código Esperado (na região relevante)

```python
from apps.workorder.approval import WorkOrderApprovalError, approve_workorder_with_stock

# ... dentro de process_supersign_webhook_payload, bloco workorder:

if workorder is not None:
    try:
        approve_workorder_with_stock(workorder=workorder, user=None)
    except WorkOrderApprovalError as exc:
        logger.warning(
            "supersign_webhook_workorder_stock_insufficient",
            extra={
                "workorder_id": workorder.pk,
                "envelope_id": envelope_id,
                "error": str(exc),
            },
        )

    workorder.mark_signature_approved()
    sync_workorder_financial_movement(workorder=workorder)
    logger.info("supersign_webhook_workorder_approved", extra={"workorder_id": workorder.pk, "envelope_id": envelope_id})
```

### Critérios de Aceite

- [ ] Quando webhook `ENVELOPE_COMPLETED` chega para uma WorkOrder com pagamento completo e produtos em estoque, o estoque é debitado e `StockMovement` de saída é criado.
- [ ] Quando o estoque é insuficiente, a assinatura ainda é registrada, mas um log warning é emitido.
- [ ] WorkOrders de garantia/cortesia também consomem estoque corretamente.

---

## Etapa 2 — Envolver fluxo de entrega manual em transação única

### Objetivo

Prevenir estado inconsistente no fluxo de entrega manual quando a dedução de estoque falha após o `complete_delivery` já ter persistido dados parciais.

Atualmente:
- `workorder.complete_delivery(km_final, ...)` — **já persiste** `km_final` no banco
- `approve_workorder_with_stock(...)` — se falhar, `km_final` já foi salvo mas status não foi alterado

### Alterações

1. **`apps/workorder/views.py`** (método `UpdateWorkOrderStatusView.post`, linhas 1288-1299):
   - Envolver `complete_delivery`, `approve_workorder_with_stock` e `sync_workorder_financial_movement` em um único `transaction.atomic()`

### Arquivos Impactados

| Arquivo | Impacto |
|---|---|
| `apps/workorder/views.py` | Envolver as 3 chamadas em `transaction.atomic()` |

### Código Esperado

```python
try:
    with transaction.atomic():
        workorder.complete_delivery(km_final=km_final, unsigned_delivery_reason=unsigned_delivery_reason)
        approve_workorder_with_stock(workorder=workorder, user=request.user)
        sync_workorder_financial_movement(workorder=workorder)
except WorkOrderApprovalError as exc:
    response = render(...)
    response["HX-Trigger"] = json.dumps({"showToast": {"message": str(exc), "type": "error"}})
    return response
```

### Critérios de Aceite

- [ ] Se a dedução de estoque falhar, `km_final` NÃO é persistido no banco (rollback completo).
- [ ] Se tudo der certo, todas as alterações são salvas atômicamente.
- [ ] Testes manuais: simular falha de estoque e verificar que nenhum dado parcial foi salvo.

---

## Etapa 3 — Adicionar warning para produtos sem estoque configurado

### Objetivo

Melhorar a experiência do usuário e a diagnosticabilidade do sistema: quando um produto da WorkOrder não possui `StockProduct` configurado, a mensagem de blocker deve ser clara.

Atualmente, `_collect_required_products` em `apps/workorder/approval.py` trata `stock_entry = None` como `available_quantity = 0`, o que gera blocker de "quantidade acima do estoque". Mas a mensagem não distingue "produto sem cadastro de estoque" de "produto com estoque insuficiente".

### Alterações

1. **`apps/workorder/approval.py`** — Função `approve_workorder_with_stock`:
   - Diferenciar na mensagem de blocker quando o produto não existe em `StockProduct` vs. quando a quantidade é insuficiente.

### Arquivos Impactados

| Arquivo | Impacto |
|---|---|
| `apps/workorder/approval.py` | Melhorar mensagens de blocker |

### Critérios de Aceite

- [ ] Se um produto da WorkOrder não tem `StockProduct`, a mensagem indica "produto sem estoque cadastrado".
- [ ] Se o produto tem estoque mas é insuficiente, a mensagem indica "quantidade insuficiente".

---

## Etapa 4 — Revisão e Testes

### Objetivo

Garantir que todas as alterações estão corretas e que o estorno (reopening) continua funcionando.

### Atividades

1. Revisar `apps/workorder/reopening.py` para confirmar que o estorno de estoque já funciona (linhas 28-55). Confirmado: o código já encontra movimentos EXIT, reverte a quantidade e cria movimentos ENTRY com `reversal_of`.
2. Verificar que `mark_signature_approved` não é chamado em nenhum outro lugar além do webhook (confirmado: apenas no webhook).
3. Testar manualmente os dois fluxos:
   - Criar WorkOrder com produtos, enviar para assinatura, assinar → verificar estoque debitado.
   - Criar WorkOrder com produtos, entregar manualmente → verificar estoque debitado.
   - Reabrir WorkOrder → verificar estoque estornado.

### Artefatos

- Logs de warning para estoque insuficiente no webhook.
- Testes manuais seguindo os cenários acima.

# Checklist Final

- [ ] **Etapa 1**: Webhook chama `approve_workorder_with_stock` antes de `mark_signature_approved`.
- [ ] **Etapa 2**: Fluxo de entrega manual envolto em `transaction.atomic()`.
- [ ] **Etapa 3**: Mensagens de blocker diferenciam "sem estoque" de "estoque insuficiente".
- [ ] **Etapa 4**: Estorno no reopening verificado.
- [ ] Nenhuma alteração em `apps/stock/models.py` (modelos já estão corretos).
- [ ] Nenhuma alteração em `apps/workorder/service.py` (assinatura já está correta; só adicionar stock ao webhook).
