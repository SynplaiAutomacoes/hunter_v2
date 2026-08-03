# Fase 4.1.0 — Inventário Técnico Rápido NF-e Operacional

## Objetivo e recorte

Este documento registra um inventário técnico curto para orientar:

1. Carta de Correção Eletrônica da NF-e (CC-e);
2. NF-e de devolução;
3. informações de transporte dentro da NF-e.

Não é uma auditoria fiscal ampla. CT-e, MDF-e, NFCom, DC-e, pendências de IBS/CBS, créditos/débitos e complementar tributária permanecem fora do escopo.

Nenhuma funcionalidade, migration, model, service, view, template, teste, OpenAPI, endpoint remoto ou payload fiscal foi alterado nesta fase.

## Revisão analisada

O checkout no início da análise estava em `fase1/pessoa1`, revisão `49f28aaf`, onde o diretório `docs/fiscal-webmania/` e os modelos fiscais maduros ainda não estão presentes. O próprio repositório identifica o bloco fiscal na branch local `feat/notas-fiscais`.

Para preservar o working tree e não trocar de branch, o inventário funcional foi feito por leitura dos objetos Git de:

- branch: `feat/notas-fiscais`;
- revisão: `c59335224b3b0db257a54e2fe4e5c41185e26e87`.

As conclusões abaixo descrevem essa revisão fiscal. Antes de implementar a próxima fase, o trabalho deve ocorrer sobre uma branch que contenha essa revisão ou seu equivalente integrado.

## Resumo executivo

| Funcionalidade | Estado encontrado | Reaproveitamento | Menor lacuna |
|---|---|---|---|
| CC-e | Já implementada na branch fiscal | `FiscalDocument`, `FiscalDocumentEvent`, `FiscalEmissionAttempt`, webhook, permissões e detalhe da NF-e | Restaurar cobertura de regressão no estado atual, tornar protocolo explícito se exigido e fechar reconciliação específica de tentativa `uncertain` |
| NF-e de devolução | Já implementada, incluindo devolução total/parcial e estorno | Documento derivado, vínculo com original, snapshot, saldo parcial, idempotência, webhook, consulta, reconciliação, downloads e UI | Restaurar testes de regressão; substituir entrada JSON por seleção de itens se a operação exigir melhor UX; manter bloqueio de parcial externa sem XML validado |
| Transporte na NF-e | Não implementado como grupo operacional | Builder, preview/emissão, payload congelado e trilha de tentativa da NF-e normal; suporte parcial a `volume` no serviço de devolução | Modelar somente os campos mínimos, incluí-los no wizard/preview e montar o grupo Webmania no payload normal |

Conclusão: CC-e e devolução não devem ser recriadas. O caminho mais curto é validar e endurecer os fluxos existentes, depois estender a NF-e normal com transporte.

## Inventário de modelos

### Núcleo legado de emissão

- `NfeRequest` mantém oficina, ordem de serviço, etapa do wizard, status, slider de precificação, classe fiscal, informações complementares, número/série reservados e dados de inutilização.
- `NfeItem` representa a NF-e retornada pela Webmania: UUID, status, número, série, recibo, chave, URLs de XML/DANFE, payload bruto/log e marcadores de webhook/reconciliação.
- A emissão normal continua partindo de `NfeRequest` e da OS. Não há motivo para criar outro domínio de emissão para devolução ou transporte.

### Projeção fiscal e documentos relacionados

- `FiscalDocument` projeta uma `NfeItem` legada por `legacy_nfe_item` e também representa documentos derivados.
- Campos reutilizáveis: oficina/conta, tipo, origem, finalidade, UUID, chave, série, número, recibo, ambiente, status, `request_payload`, `response_payload`, XML, DANFE e solicitante.
- Finalidades existentes incluem `normal`, `return`, `reversal`, `complementary`, `adjustment`, `credit` e `debit`.
- `FiscalDocumentLink` relaciona documento derivado e original. Os papéis `returns` e `reverses` já cobrem devolução e estorno.
- Restrições únicas por oficina protegem UUID e chave, e a projeção de uma `NfeItem` é única.

### Eventos fiscais

- `FiscalDocumentEvent` já é a estrutura genérica de eventos.
- Para CC-e, armazena tipo `cce`, sequência, status, UUID/modelo remoto, texto da correção, payload de requisição/resposta, XML, DACCE, solicitante e confirmação legal.
- A restrição `(document, event_type, event_sequence)` e o limite de sequência no serviço evitam duplicidade lógica.
- Não existe campo explícito de protocolo de CC-e. Caso o protocolo precise ser consultável sem abrir o payload de resposta, essa é uma lacuna pequena de persistência/mapeamento.

### Tentativas, idempotência e estado incerto

- `FiscalEmissionAttempt` registra tipo de documento, tipo de operação, objeto de origem, documento/evento relacionado, chave de idempotência, hash e cópias sanitizadas dos payloads.
- Estados existentes: `started`, `sent`, `succeeded`, `failed` e `uncertain`.
- Operações existentes incluem `cce`, `return` e `reversal`.
- A restrição única `(workshop, document_kind, idempotency_key)` é reutilizável pelas três frentes.

### Produtos e impostos

- A emissão normal extrai produtos da OS/snapshots e já monta código, descrição, NCM, CEST, quantidade, unidade, origem, subtotal, total e referência da classe fiscal.
- `Product` já fornece unidade, NCM e CEST; OS/orçamento fornecem quantidade, preço e snapshots comerciais.
- `TaxClassNfe` e seus cenários de ICMS, IPI, PIS e COFINS já representam configuração tributária, incluindo CFOP em cenário de ICMS.
- A NF-e normal envia `classe_imposto` por produto e delega a tributação correspondente à configuração Webmania.
- Devolução usa o snapshot da NF-e original para preservar sequenciais, quantidades e IBS/CBS quando aplicável; não usa a classe fiscal atual como substituto automático do histórico.

### Transporte

- Não há modelo de transportadora, transporte ou volumes ligado a `NfeRequest`/`FiscalDocument`.
- O builder normal fixa apenas `pedido.modalidade_frete = 9`.
- O serviço de devolução aceita opcionalmente um dicionário `volume` e o repassa ao payload, mas a UI atual não o coleta nem o envia.
- Frete comercial existente em produto/OS não equivale a dados fiscais de transporte e não deve ser convertido automaticamente em transportadora, modalidade, placa, volumes ou pesos.

## Inventário de serviços Webmania

| Capacidade | Componente encontrado | Observação |
|---|---|---|
| Emissão NF-e normal | `apps/core/infrastructure/services/webmania/nfe_emission.py` | Builder, preview, download de prévia, POST de emissão, sincronização de resposta |
| Cancelamento NF-e | `cancel_nfe_document(...)` | PUT remoto; fluxo legado separado da estrutura genérica de eventos |
| Inutilização NF-e | `invalidate_nfe_number(...)` | PUT remoto e persistência no `NfeRequest` |
| Consulta NF-e | `apps/core/infrastructure/services/webmania/nfe_consulta.py` | Consulta e reconciliação de `NfeItem` |
| CC-e | `apps/finance/services/nfe_events.py` | `POST /1/nfe/cartacorrecao/`, reserva do evento/tentativa antes do envio e replay de webhook |
| Devolução/estorno | `apps/finance/services/nfe_returns.py` | `POST /1/nfe/devolucao/`, documento derivado, consulta e reconciliação |
| Webhook | `apps/core/infrastructure/services/webmania/webmania_webhooks.py` | Inbox persistida, fingerprint idempotente, processamento diferido e proteção contra status regressivo |
| Reconciliação operacional | `reconcile_webmania_documents` | Reprocessa webhooks, NF-e normal, devoluções/estornos e tentativas incertas, entre outros documentos |
| Download remoto | `webmania_documents.py` | Reutilizável para XML, DANFE e DACCE |
| Autenticação/erros/status | `webmania_auth.py`, `webmania_errors.py`, `webmania_status.py` | Cabeçalhos por oficina/global, mensagens e normalização |

Observações relevantes:

- O comando de reconciliação da revisão analisada chama `service.reconcile_nfe_item(item=item)` dentro do laço cujo objeto se chama `pending_nfe_item`. Isso aparenta ser um erro local que deve ser confirmado antes de confiar na reconciliação da NF-e normal.
- A reconciliação de devolução/estorno é explícita e consulta sem repetir o POST.
- CC-e possui webhook e bloqueio seguro de reenvio após timeout, mas não foi localizado um método de consulta/reconciliação específico para a CC-e. Uma tentativa `uncertain` de CC-e não deve ser liberada por repetição cega do POST.

## Infraestrutura reutilizável

### Idempotência e payload congelado

- `begin_emission_attempt(...)` persiste a tentativa antes da chamada remota.
- `build_fiscal_operation_idempotency_key(...)` atende eventos sequenciais como CC-e.
- `build_fiscal_document_operation_idempotency_key(...)` atende documentos derivados como devolução.
- `payload_hash`, `request_payload` e `response_payload` permitem auditoria e comparação.
- `sanitize_fiscal_payload(...)` deve continuar sendo usado antes de persistir ou expor payloads.

### Timeout e estado remoto incerto

- Emissão normal, CC-e e devolução marcam timeout/resposta inválida como `uncertain`.
- Novos POSTs são bloqueados enquanto a intenção anterior estiver enviada, concluída ou incerta.
- O padrão correto é reconciliar por consulta/webhook, nunca repetir automaticamente a emissão.

### Auditoria

- Documento, evento e tentativa registram timestamps e vínculo com solicitante.
- CC-e registra texto, confirmação legal e momento da confirmação.
- Devolução preserva o documento original por `FiscalDocumentLink` e congela o payload do derivado.
- O webhook é persistido antes do processamento e possui fingerprint único.

### Permissões e isolamento por oficina

- Views usam `WorkshopScopedMixin` e filtros por oficina.
- CC-e possui `issue_nfe_correction`, `download_nfe_correction` e `view_nfe_correction_payload`.
- Devolução/estorno possuem permissões específicas de emissão, download e visualização de payload.
- O detalhe da NF-e calcula ações disponíveis por status, documento e permissão contextual.

### UI existente

- Wizard de `NfeRequest`: seleção da OS, revisão do cliente e etapa fiscal com slider, classe fiscal e informação complementar.
- Detalhe da NF-e: reconsulta, cancelamento, inutilização, downloads e ações derivadas.
- CC-e: modal, confirmação legal, envio, histórico sequencial, XML/DACCE e payload protegido.
- Devolução: modal para finalidade, total/parcial, natureza, CFOP, produtos em JSON e confirmações; histórico, XML/DANFE e payload protegido.
- Transporte: não há formulário, preview, resumo ou histórico específico.

## Testes existentes

Na revisão `c5933522`, os testes fiscais retidos estão concentrados em:

- `apps/finance/tests.py`: permissões dedicadas da NF-e normal;
- `test_tax_classes.py`: classes fiscais;
- `test_nfse_preview.py`: preview NFS-e;
- arquivos dedicados a base fiscal referenciada, NF-e de crédito/débito e cancelamentos correspondentes.

Não foram encontrados, no tree atual da branch fiscal:

- testes comportamentais de CC-e;
- testes comportamentais de devolução/estorno;
- testes específicos do grupo de transporte na NF-e;
- testes focados da emissão normal, webhook e reconciliação compatíveis com todo o código atualmente presente.

O histórico Git mostra que os checkpoints `af76387f` e `bf3d67e5` adicionaram testes de devolução e CC-e, respectivamente, mas um commit posterior (`b71ccc44`, `remove: tests files`) retirou esses testes antes da revisão inventariada. Portanto, o histórico comprova intenção de cobertura, mas não substitui testes presentes e executáveis.

## Análise da Carta de Correção NF-e

### O que já existe

- Projeção da NF-e autorizada em `FiscalDocument`, sem criar nova NF-e.
- Evento genérico `FiscalDocumentEvent(event_type="cce")`.
- Endpoint Webmania `/1/nfe/cartacorrecao/`.
- Validação de elegibilidade, 15–1000 caracteres, máximo de 20 sequências e bloqueio textual conservador para campos essenciais.
- Persistência transacional de evento e tentativa antes do POST.
- Idempotência, payload congelado, timeout `uncertain`, webhook, histórico, permissões e downloads XML/DACCE.
- O fluxo não altera XML original, valores fiscais nem status da NF-e base.

### Menores lacunas

1. Reintroduzir testes presentes na suíte para sucesso, rejeição, timeout, concorrência/idempotência, webhook, permissão, oficina e downloads.
2. Mapear protocolo para campo explícito somente se a resposta Webmania o fornecer e a operação precisar exibi-lo diretamente; hoje ele fica, no máximo, dentro de `response_payload`.
3. Implementar consulta/reconciliação específica de CC-e ou documentar uma fonte remota segura; até lá, manter bloqueado o reenvio de tentativa `uncertain`.
4. Confirmar no teste de integração que o webhook identifica sem ambiguidade `modelo=cce` e UUID do evento.

### Implementação mínima recomendada

Não implementar CC-e novamente. A próxima fase deve ser de validação/endurecimento do fluxo existente, mantendo:

`NF-e autorizada -> FiscalDocument projetado -> FiscalDocumentEvent sequencial -> FiscalEmissionAttempt -> Webmania -> webhook/consulta -> histórico/download`.

## Análise da NF-e de devolução

### O que já existe

- Reuso da NF-e original local por `ensure_fiscal_document_for_nfe_item(...)`.
- Documento derivado `FiscalDocument(origin="derived", purpose="return"|"reversal")`.
- Vínculo obrigatório `FiscalDocumentLink(role="returns"|"reverses")`.
- Endpoint Webmania `/1/nfe/devolucao/`.
- Devolução total, parcial e estorno; natureza da operação, CFOP e informações adicionais.
- Seleção parcial por sequencial/quantidade, cálculo de saldo e bloqueio de quantidade acima do disponível.
- Snapshot de produtos/impostos da nota original, inclusive IBS/CBS conservador quando aplicável.
- NF-e externa mínima por chave somente para total/estorno; parcial externa bloqueada sem XML/importação validada.
- Documento/tentativa persistidos antes do POST, idempotência, timeout `uncertain`, consulta, webhook, reconciliação, XML/DANFE e histórico.
- O fluxo emite nova NF-e derivada sem duplicar `NfeRequest` ou criar domínio paralelo.

### O que pode ser reutilizado

- O fluxo completo de `FiscalDocument`/`FiscalDocumentLink`.
- Produtos e sequenciais do snapshot original.
- Validações de chave, elegibilidade e saldo devolvível.
- Builder e transmissor de `nfe_returns.py`.
- `FiscalEmissionAttempt`, webhook, consulta e comando de reconciliação.
- A tela de detalhe da NF-e original como ponto de entrada.

### Menores lacunas

1. Restaurar testes de regressão para total, parcial, estorno, saldo, snapshot fiscal, idempotência, timeout, webhook, consulta, permissões e oficina.
2. Trocar o campo `produtos_json` por seleção estruturada de itens/quantidades para uso operacional; o serviço já aceita a estrutura necessária.
3. Preservar o bloqueio de devolução parcial externa até existir importação/validação de XML com sequencial, quantidade e tributos.
4. Confirmar CFOP e natureza como entrada fiscal aprovada; não inferir automaticamente apenas pela classe atual.
5. Se transporte também for necessário no documento de devolução, expor o parâmetro `volume` já suportado pelo serviço somente depois de fechar o contrato do grupo de transporte.

### Implementação mínima recomendada

Não criar novo domínio de devolução e não duplicar preview/emissão normal. A próxima fase deve validar e melhorar o fluxo derivado existente. A UI pode evoluir sem alterar a arquitetura:

`NF-e original -> selecionar escopo/itens -> congelar documento derivado e vínculo -> emitir em /1/nfe/devolucao/ -> webhook/consulta -> histórico/download`.

## Análise de transporte na NF-e

### Decisão de escopo

O escopo correto é o grupo de transporte dentro da NF-e. CT-e é outro documento fiscal, usa domínio, atores, carga, regras, API e ciclo de vida próprios. Não deve ser iniciado nesta sequência.

### Estado encontrado

- NF-e normal e NFC-e enviam `modalidade_frete=9`, equivalente operacionalmente a não ocorrência de transporte.
- Não há campos em `NfeRequest`, formulário, preview ou detalhe para modalidade, transportadora, veículo, volumes ou pesos.
- Não há domínio de CT-e no código fiscal analisado.
- `nfe_returns.py` já sabe anexar um dicionário `volume` ao payload de devolução, mas não existe captura na UI.
- Valores comerciais de frete na OS não são substitutos seguros para o grupo fiscal de transporte.

### Caminho mínimo

1. Validar no contrato Webmania somente os campos necessários ao primeiro caso operacional.
2. Definir um DTO/estrutura pequena para o grupo, evitando criar domínio de CT-e.
3. Persistir os dados antes da emissão, preferencialmente em estrutura ligada à intenção `NfeRequest`, para que preview e emissão usem o mesmo snapshot.
4. Adicionar campos ao passo fiscal do wizard e ao preview.
5. Estender `_build_payment_payload(...)` ou criar um builder específico de transporte chamado por `build_nfe_payload(...)`.
6. Congelar o grupo no `FiscalEmissionAttempt.request_payload`.
7. Cobrir modalidade sem transporte e ao menos um cenário com transportadora/volumes, além de permissões e isolamento por oficina já herdados do fluxo.

Não reutilizar automaticamente placa do veículo atendido como placa do veículo transportador.

## Lacunas transversais prioritárias

1. A suíte atual da branch fiscal não retém os testes de CC-e e devolução existentes nos checkpoints históricos.
2. CC-e precisa de estratégia explícita para reconciliar `uncertain` sem novo POST.
3. O comando de reconciliação da NF-e normal contém uma referência aparentemente incorreta a `item`; deve ser confirmado antes da próxima rodada funcional.
4. Transporte normal não possui persistência nem UI e hoje sempre informa modalidade 9.
5. A UI de devolução parcial ainda exige JSON manual, embora a camada de serviço já esteja estruturada.

## Decisão final de ordem

### Opção A

1. Carta de Correção;
2. NF-e de devolução;
3. transporte na NF-e.

Justificativa:

- CC-e é o menor fluxo: um evento sobre documento autorizado, sem nova NF-e, sem itens, sem recomposição tributária e com quase toda a infraestrutura pronta.
- Devolução já está implementada, mas tem mais combinações e risco fiscal: documento novo, total/parcial, saldo, CFOP, natureza, snapshot e impostos.
- Transporte é uma extensão da emissão normal, mas ainda exige contrato de campos, persistência, formulário, preview e builder; possui menos infraestrutura específica pronta que as duas anteriores.

Na prática, as duas primeiras etapas são de validação/endurecimento, não de implementação do zero.

## Próxima fase proposta

**Fase 4.1.1 — Validação operacional e fechamento de lacunas da CC-e.**

Escopo proposto:

- trabalhar sobre a branch fiscal integrada;
- restaurar testes focados de CC-e;
- validar endpoint, sucesso/rejeição, webhook, XML/DACCE, sequência e permissões;
- definir protocolo explícito somente se suportado pela resposta real;
- fechar reconciliação segura de `uncertain` sem repetir POST;
- não tocar em devolução, transporte, CT-e ou outros domínios fiscais.

Depois:

- Fase 4.1.2: validação operacional e UX estruturada da devolução;
- Fase 4.1.3: extensão mínima do grupo de transporte na NF-e normal.

## Validação documental prevista

Conforme a restrição da fase, executar somente:

```text
git diff --check -- docs/fiscal-webmania
git status --short
```

Não executar testes funcionais.

### Resultado desta execução

- `git diff --check -- docs/fiscal-webmania`: aprovado, sem saída.
- Verificação complementar do arquivo ainda não rastreado com `git diff --no-index --check`: sem erro de whitespace.
- `git status --short`: confirmou somente este novo diretório dentro do escopo fiscal documental; também mostrou alterações de performance preexistentes e fora do escopo.
- Código funcional, migrations, models, services, views, templates, testes e OpenAPI: não alterados.
- Testes funcionais: não executados, conforme solicitado.
- Checkpoint documental: não criado, pois o working tree já estava sujo com alterações fora de `docs/fiscal-webmania/**` e não poderia ficar limpo após o commit sem interferir em trabalho preexistente.
