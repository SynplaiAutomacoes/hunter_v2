# Fase 4.2.8 — Homologação Final e Auditoria de Entrega Fiscal

Data da auditoria: 31/07/2026
Base consolidada commitada: `79c399b6414dbd3d2d4292eadbb6fbd06e53ec62`
Branch auditada: `codex/fase-4-2-7d-fiscal-ux-review`

## Resultado executivo

**Situação: aprovado com ressalva funcional.**

O ciclo 4.2 entregou o gateway fiscal, a origem manual da NF-e, emissão sem Ordem de Serviço, múltiplos produtos, cadastros rápidos, integração das operações existentes, Central de Notas, formulários avançados e revisão de UX/permissões.

Os fluxos fiscais automatizados passaram pela regressão consolidada. Não foi encontrado desvio nos motores de CC-e, devolução, complementar, ajuste, transporte, cancelamento ou inutilização.

A ressalva é o destinatário fornecedor: a emissão manual seleciona somente `Customer`. Um registro existente exclusivamente em `Supplier` não pode ser escolhido diretamente. Para emitir para essa pessoa, hoje é necessário cadastrá-la também como cliente. Portanto, o requisito “cliente ou fornecedor existente” não está integralmente atendido.

## Entregas consolidadas

- Gateway `Emitir Nota` com NF-e Normal, Devolução, Carta de Correção, Nota Complementar, Nota de Ajuste e Transporte.
- Escolha da origem da NF-e entre Ordem de Serviço e Emissão Manual.
- `NfeRequest` com origem `WORK_ORDER` ou `MANUAL`.
- Emissão manual sem OS e sem orçamento.
- Destinatário manual baseado no cadastro de clientes.
- Cadastro rápido de pessoa pelo fluxo de `Customer`.
- Produto existente ou cadastro rápido de produto.
- Múltiplos produtos com quantidade e valor unitário.
- Reutilização do mesmo `build_nfe_payload`, emissão Webmania e `FiscalEmissionAttempt`.
- Central de Notas como ponto de consulta, downloads, histórico e ações sobre documentos existentes.
- Devolução parcial por item, Nota Complementar e Nota de Ajuste sem edição manual de JSON.
- Transporte com modalidade, transportador, veículo, volumes e reboques em campos estruturados.
- Ocultação de operações e ações conforme as permissões existentes.

## Ponto 1 — NF-e sem dependência obrigatória de OS

**Situação: atendido.**

Fluxo homologado:

`Emitir Nota → NF-e Normal → Emissão Manual → Destinatário → Produtos → Revisar e emitir`

Evidências:

- `NfeEmissionOrigin.MANUAL` permite `workorder=None`.
- A restrição do modelo exige destinatário manual quando a origem é `MANUAL` e OS quando a origem é `WORK_ORDER`.
- O formulário manual aceita pessoa existente do cadastro `Customer`.
- O cadastro rápido utiliza o fluxo existente de cliente e respeita `add_customer`.
- Produtos são filtrados pela oficina ativa.
- O cadastro rápido de produto respeita `add_product` e exige os dados fiscais necessários.
- O formset exige ao menos um produto, aceita múltiplos itens e bloqueia produtos repetidos.
- A emissão manual chama `get_fiscal_service().emit_nfe(...)` e sincroniza a resposta pelo serviço existente.
- O mesmo `build_nfe_payload` trata as duas origens; não existe builder paralelo.
- `FiscalEmissionAttempt` é criado pelo fluxo fiscal compartilhado.

O fluxo tradicional permanece:

`Ordem de Serviço → Emitir Nota → NF-e Normal → Ordem de Serviço → wizard produtivo → Emitir`

Os testes de compatibilidade confirmam que o ramo `WORK_ORDER` continua exigindo OS e preserva a construção de payload anterior.

## Ponto 2 — Operações fiscais pelo Emitir Nota

**Situação: atendido.**

| Operação | Entrada | Destino e formulário | Histórico/resultado |
|---|---|---|---|
| NF-e Normal | Gateway | Escolha Manual ou Ordem de Serviço | Detalhe da NF-e e Central |
| Emissão Manual | Origem MANUAL | Destinatário, produtos e revisão | Mesmo detalhe e motor da NF-e |
| Ordem de Serviço | Origem WORK_ORDER | Wizard produtivo preservado | Mesmo detalhe e motor da NF-e |
| Devolução/Estorno | Gateway → Central | Seleção da referência, itens, quantidades e revisão | `FiscalDocument`, links, saldo e downloads preservados |
| Carta de Correção | Gateway → Central | Seleção da referência e texto da correção | Sequência, histórico, XML e DACCE preservados |
| Nota Complementar | Gateway → Central | Itens, quantidade, valor, CFOP e situação tributária | Documento vinculado e downloads preservados |
| Nota de Ajuste | Gateway → Central | Dados fiscais, destinatário e revisão | Documento vinculado e validações de regime preservadas |
| Transporte | Gateway → NF-e por OS | Modalidade, transportador, veículo, volumes e reboques | `transport_snapshot` preservado; nenhum CT-e/MDF-e criado |

As operações sem permissão são removidas do gateway. POST forjado é rejeitado e cada endpoint fiscal mantém sua própria autorização como camada definitiva.

## Ponto 3 — Emissão sobre qualquer produto/pessoa

**Situação: parcialmente atendido.**

### Pessoa

- Cliente existente: **atendido**.
- Pessoa ainda não cadastrada: **atendido** pelo cadastro rápido de `Customer`.
- Fornecedor existente apenas em `Supplier`: **não atendido**.
- Fornecedor que também possua cadastro de cliente: **atendido pelo cadastro de cliente**, mas com duplicação de cadastro.

O campo `manual_recipient` e o formulário manual apontam diretamente para `customer.Customer`. Não existe adaptador, cadastro unificado de pessoa ou seleção de `Supplier` nesse fluxo.

### Produto

- Produto cadastrado no catálogo da oficina: **atendido**.
- Cadastro rápido: **atendido**.
- Múltiplos itens: **atendido**.
- Produto sem vínculo com estoque: **atendido**, desde que exista no catálogo e possua dados fiscais válidos.
- Movimentação automática de estoque: **não ocorre**, conforme o escopo definido.

### Dependências

A emissão manual não exige:

- Ordem de Serviço;
- orçamento;
- movimento ou saldo de estoque.

Ela exige cadastro fiscal válido de destinatário como `Customer`, produto de catálogo, NCM, preço, quantidade e classe tributária aplicável.

Serviços permanecem no domínio de NFS-e e não são itens da emissão manual de NF-e de produto.

## Auditoria UX/UI

**Situação: atendida para os fluxos homologados.**

- “Emitir Nota” é o ponto de criação e início das operações fiscais.
- “Central de Notas” é o ponto de consulta, downloads, histórico e ações sobre documentos existentes.
- A lista de NF-e e o endpoint legado `/nfe/create/` direcionam ao gateway oficial.
- A escolha Manual/Ordem de Serviço não é mais ignorada pelos CTAs da lista.
- As operações referenciadas retornam à Central para seleção da NF-e correta.
- Formulários de devolução, complementar, ajuste e reboques não expõem JSON ao usuário.
- Textos obsoletos como “Nesta fase” e instruções baseadas em “atalhos” foram removidos na revisão 4.2.7D.
- Usuário somente com consulta não visualiza “Editar” ou “Reconsultar status”.

## Auditoria de segurança

**Situação: atendida nos testes automatizados.**

- Gateway filtra operações pelas permissões atuais.
- Operação não permitida enviada por POST é bloqueada.
- Cadastro rápido de cliente exige `add_customer`.
- Cadastro rápido de produto exige `add_product`.
- Queries de destinatário e produto são limitadas à oficina ativa.
- Central e detalhe respeitam o escopo da oficina.
- Endpoints de CC-e, devolução, complementar, ajuste, cancelamento, inutilização e downloads mantêm permissões próprias.
- Ações de alteração/reconsulta não aparecem para usuários somente com visualização.

## Auditoria técnica

### Models e migrations

O ciclo alterou models somente onde necessário para representar a nova origem:

- `NfeEmissionOrigin`;
- `NfeRequest.emission_origin`;
- `NfeRequest.manual_recipient`;
- OS opcional para origem manual;
- `NfeRequestManualItem`.

Migrations necessárias e rastreáveis:

- `0082_nferequest_emission_origin_and_more.py`;
- `0083_nferequestmanualitem_and_more.py`.

Não há migrations pendentes após o ciclo.

### Builder, payload e emissão

O `build_nfe_payload` existente foi **estendido**, de forma necessária, para obter destinatário e produtos da origem manual. Ele não foi substituído e nenhum builder paralelo foi criado.

O ramo `WORK_ORDER` continua usando a mesma extração, precificação e validações produtivas. Testes específicos comparam e preservam o payload de emissão por OS.

A origem manual chega ao mesmo caminho:

`NfeRequest → build_nfe_payload → FiscalEmissionAttempt → Webmania`

Não foi criado novo endpoint externo ou contrato Webmania paralelo.

### Motores fiscais avançados

As fases de gateway e UX apenas conectaram ou adaptaram a interface dos motores existentes:

- CC-e: `FiscalDocumentEvent`, UUID, sequência, webhook, XML e DACCE preservados.
- Devolução: `FiscalDocument`, `FiscalDocumentLink`, saldo, snapshots, idempotência, webhook e reconciliação preservados.
- Complementar e ajuste: serviços e validações fiscais preservados.
- Transporte: mesmo `transport_snapshot` e mesmo payload de NF-e.
- Cancelamento e inutilização: endpoints e integrações existentes preservados.

## Fluxos e testes executados

Comando de regressão fiscal consolidada:

```text
uv run python manage.py test \
  apps.finance.tests \
  apps.finance.test_fiscal_operation_gateway \
  apps.finance.test_issued_documents \
  apps.finance.test_nfe_emission_origin \
  apps.finance.test_nfe_manual_emission \
  apps.finance.test_nfe_correction \
  apps.finance.test_nfe_returns \
  apps.finance.test_nfe_transport --keepdb
```

Resultado: **104/104 testes aprovados**.

Cobertura funcional da seleção executada:

- gateway e escolha de origem;
- NF-e por OS;
- NF-e manual;
- pessoa existente e cadastro rápido de cliente;
- produto existente, cadastro rápido e múltiplos itens;
- mesmo builder, payload e `FiscalEmissionAttempt`;
- Central de Notas e downloads;
- CC-e, histórico, XML e DACCE;
- devolução parcial/total, múltiplos itens, saldo e vínculos;
- Nota Complementar;
- Nota de Ajuste;
- transporte e reboques;
- cancelamento e inutilização;
- permissões e POST manipulado.

Validações técnicas:

- `python manage.py check`: aprovado;
- `python manage.py makemigrations finance --check --dry-run`: aprovado, sem alterações;
- Ruff nos arquivos Python pendentes da revisão 4.2.7D: aprovado;
- `git diff --check`: aprovado antes da criação deste documento e deve ser repetido na conferência final.

## Problemas encontrados

### 1. Fornecedor existente não é destinatário selecionável

Severidade de entrega: **alta para o requisito original de qualquer pessoa**.

O fluxo manual consulta apenas `Customer.objects`. `Supplier` é um domínio separado e não existe adaptação segura para destinatário fiscal. Corrigir exige decisão arquitetural para evitar duplicação de Cliente/Fornecedor, portanto não foi alterado nesta fase documental.

### 2. Homologação externa não executada

Os testes simulam respostas da Webmania e validam builder, tentativa fiscal, persistência, reconciliação e webhooks. Eles não substituem uma emissão real em ambiente de homologação com certificado, credenciais Webmania e autorização da SEFAZ.

### 3. Fase 4.2.7D ainda não commitada

As correções finais de textos e visibilidade de ações estão validadas no working tree, mas aguardam aprovação e commit separado com a mensagem sugerida `chore: finalize fiscal ux review`.

## Pendências futuras

1. Definir uma abstração única de pessoa fiscal ou um adaptador seguro para selecionar `Customer` e `Supplier` sem duplicar domínios.
2. Adicionar teste de emissão manual usando fornecedor após a decisão arquitetural.
3. Executar roteiro real em ambiente Webmania/SEFAZ de homologação com credenciais e certificado da oficina.
4. Validar responsividade e acessibilidade dos formulários avançados com usuários finais e dados representativos.
5. Tratar a recusa/manifestação de NF-e recebida, melhoria explicitamente postergada no início do ciclo.
6. Manter serviços no fluxo próprio de NFS-e; caso se deseje uma experiência manual unificada de produtos e serviços, planejar isso como fase separada sem misturar os documentos fiscais.

## Conclusão

Os Pontos 1 e 2 estão homologados. O Ponto 3 está homologado para clientes, novas pessoas cadastradas como clientes e produtos de catálogo sem dependência de estoque, porém permanece incompleto para fornecedores cadastrados exclusivamente no domínio `Supplier`.

O ciclo pode ser considerado tecnicamente estável e aprovado com ressalva. O encerramento funcional integral do requisito “qualquer pessoa” depende da decisão e implementação futura para destinatários fornecedores.
