# Fase 4.2.7 - Auditoria de UX/UI e workflow da emissão fiscal

Data da auditoria: 2026-07-31.

Status: concluída documentalmente. Nenhum código funcional, model, migration, builder, payload, serviço fiscal ou endpoint externo foi alterado.

## Objetivo e método

Esta auditoria confronta a experiência exposta pelo ciclo 4.2 com os fluxos efetivamente implementados. Foram inspecionados os pontos de navegação, gateway, formulários, views, templates, models, permissões e serviços usados pela NF-e por Ordem de Serviço, pela NF-e manual e pelas operações que dependem de uma NF-e anterior.

O resultado é uma auditoria estática do produto consolidado no commit `990ea9211ef3b078518c95e04c995c8e34f6e1f1`. Não houve alteração de código nem execução de emissão real contra a Webmania.

## Conclusão executiva

A emissão manual existe, não exige OS e chega ao mesmo motor fiscal. Entretanto, ela **não foi integrada aos steps do wizard por OS**. O produto possui atualmente dois workflows depois da escolha da origem:

```text
Emitir Nota
  -> NF-e Normal
     -> Ordem de Serviço
        -> wizard de 6 steps, todos orientados à OS
     -> Manual
        -> formulário único próprio, sem os steps do wizard e sem prévia
```

Portanto, a OS não é uma dependência técnica da NF-e manual, mas ainda domina a experiência em pontos relevantes. A impressão de que toda NF-e depende de OS é reforçada principalmente por:

1. atalhos legados das listas de NF-e/NFS-e que enviam parâmetros como `tipo` e `reset` ao gateway e, por compatibilidade, são redirecionados diretamente ao wizard por OS, sem mostrar a escolha de origem;
2. título e subtítulo do wizard: “Emissão de nota” e “Fluxo unificado para conferir a OS...”;
3. todos os steps desse wizard dependerem de `workorder_id` e retornarem ao step 1 quando não existe OS;
4. a emissão manual estar em uma tela paralela, com interação e nível de revisão diferentes;
5. o card “Transporte” abrir diretamente o wizard por OS, enquanto a emissão manual fixa “Sem transporte”.

Resposta objetiva: **um usuário que entra pelo menu principal consegue entender que pode emitir sem OS; um usuário que entra pela lista de NF-e ou por atalhos legados pode não ver essa possibilidade e continuará percebendo a emissão como dependente de OS.**

## Mapa dos caminhos reais

### Entrada canônica pelo menu

```text
Menu -> Emitir nota
  -> Escolha da operação
     -> NF-e Normal
        -> Escolha da origem
           -> Ordem de Serviço -> wizard existente
           -> Manual -> formulário manual próprio -> transmissão
     -> Transporte -> wizard existente por OS
     -> Devolução/CC-e/Complementar/Ajuste
        -> Central de Notas -> selecionar NF-e -> detalhe -> modal existente
```

### Entradas legadas ainda ativas

- A lista de NF-e usa `finance:emission_create?tipo=nfe&reset=1`.
- A lista de NFS-e usa `finance:emission_create?tipo=nfse&reset=1`.
- `FiscalOperationGatewayView` considera `tipo`, `note_mode`, `step`, `reset`, `close` e `preview` como parâmetros do wizard legado e redireciona para `finance:emission_normal`.
- `NfeCreateRedirectView` também direciona a criação para o wizard unificado por OS.

Consequência: a entrada “Emitir nova Nota Fiscal de Produto” da lista de NF-e pula tanto a escolha da operação quanto a escolha `WORK_ORDER`/`MANUAL`.

## Auditoria do gateway

### Escolha da operação

Tela: `fiscal_operation_gateway.html`.

Objetivo: escolher entre NF-e Normal, Devolução, Carta de Correção, Nota Complementar, Nota de Ajuste e Transporte.

Comportamento:

- NF-e Normal abre a escolha da origem;
- Transporte abre diretamente o wizard por OS com `tipo=nfe`;
- operações referenciadas abrem a Central de Notas filtrada para NF-e e preservam `operacao`;
- operações derivadas sem permissão não são exibidas e um POST manipulado é bloqueado;
- os endpoints finais continuam validando elegibilidade e permissão.

Achado: o gateway é coerente como entrada principal, mas não é ainda a única entrada real.

### Escolha da origem

Tela: `nfe_emission_origin_gateway.html`.

Objetivo: escolher `Ordem de Serviço` ou `Manual`.

Comportamento:

- `WORK_ORDER` abre o wizard existente com estado reiniciado;
- `MANUAL` abre `NfeManualEmissionCreateView`;
- a escolha é clara nos cards e não exige que a OS já exista para selecionar Manual.

Achado de texto: permanece no template um alerta controlado por `manual_extension_pending` afirmando que os dados e a emissão manual serão disponibilizados em fase futura. O fluxo atual já está disponível. Ainda que o POST normal não gere esse parâmetro, uma URL com `?origin=manual` pode exibir uma mensagem falsa e contraditória.

## Wizard por Ordem de Serviço

O wizard servido por `EmissionRequestCreateView` possui cinco steps fixos e um ou dois steps dinâmicos. Seu estado é guardado na sessão por oficina e usuário. Sem `workorder_id`, `_load_state()` força `current_step=1` e `max_reached_step=1`.

### Step 1 - Selecionar OS

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Selecionar a OS que alimentará a emissão |
| Campos | `workorder` |
| Obrigatórios | `workorder` |
| Validações | Apenas OS da oficina ativa, com status `APPROVED`; exclui OS que já possui NF-e e NFS-e; avisa quando apenas uma delas já existe |
| Dependências | `WorkOrder`, `Budget`, `Customer`, `Vehicle`, `NfeRequest`, `NfseRequest` |
| Origem dos dados | Queryset de OS aprovadas da oficina |

Resposta ao requisito: neste step não existe escolha Manual. A escolha Manual ocorre **antes**, em outra view. Dentro do wizard a dependência de OS é fixa e intencional para o ramo `WORK_ORDER`.

### Step 2 - Conferir Cliente

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Revisar cliente e veículo vinculados à OS |
| Campos editáveis no form | Nenhum |
| Dados exibidos | Nome, documento, telefone, e-mail, endereço e veículo |
| Ações | Edição rápida do cliente e do veículo em modal |
| Validações | A existência da OS já foi exigida pelo estado do wizard |
| Dependências | `workorder.budget.customer` e `workorder.budget.vehicle` |
| Origem dos dados | Orçamento da OS selecionada |

Resposta ao requisito: o destinatário não pode ser escolhido nem criado neste step. O cliente é obrigatoriamente o cliente do orçamento da OS. O cadastro rápido da emissão manual existe, mas está em outra tela.

### Step 3 - Conferir Produtos/Serviços

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Revisar produtos e serviços da OS, inclusive componentes de kits |
| Campos editáveis no form | Nenhum campo direto; os itens são exibidos em tabelas |
| Ações | Edição rápida dos itens da própria OS em modal |
| Validações | A origem é a OS selecionada; alteração exige permissão de mudança da OS |
| Dependências | Itens da `WorkOrder`, produtos, serviços, kits e preços operacionais |
| Origem dos dados | OS e seu snapshot comercial |

Resposta ao requisito: produtos e serviços dependem exclusivamente da OS neste wizard. Seleção manual e cadastro rápido de produto pertencem ao formulário manual, não a este step.

### Step 4 - Resumo

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Revisar totais e ajustar o slider de precificação |
| Campos | `pricing_slider` |
| Obrigatórios | Slider entre `-100` e `100` |
| Validações | Normalização por `clamp_slider_value`; avisos e prévia recalculados por HTMX |
| Dependências | Pricing snapshot, desconto e totais da OS/orçamento |
| Origem dos dados | `WorkOrder.pricing_snapshot` e slider do orçamento |

Achado: este step é exclusivo do modelo comercial da OS e não é aplicável diretamente à emissão manual, que utiliza quantidade e valor unitário explícitos.

### Step 5 - Emitir Nota

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Escolher Nota Fiscal de Produto, Nota Fiscal de Serviço ou ambas |
| Campos | `note_mode` (`nfe`, `nfse`, `both`) |
| Obrigatórios | Uma opção disponível |
| Validações | Disponibilidade depende dos saldos de produtos/serviços e de notas já emitidas para a OS |
| Dependências | Alocação do slider, itens da OS, `NfeRequest` e `NfseRequest` existentes |
| Origem dos dados | OS e emissões já registradas |

Achado de linguagem: quem entrou por “NF-e Normal” reencontra uma escolha que inclui NFS-e e “Ambas”. Isso é coerente com o wizard unificado histórico, mas incoerente com a expectativa criada no gateway, que prometeu especificamente NF-e Normal.

### Step 6 - Nota Fiscal de Produto

Este step é incluído quando `note_mode` é `nfe` ou `both`.

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Configurar fiscalmente e visualizar os produtos da NF-e |
| Campos principais | `tax_class`, `additional_information`, modalidade de frete, transportador, endereço, veículo, volumes e reboques |
| Obrigatórios | Classe fiscal válida; modalidade de frete; campos condicionais conforme os dados de transporte preenchidos |
| Validações | Classe ativa e compatível; CPF/CNPJ, IE/UF, CEP, placa, pesos, volumes e JSON de reboques normalizados pelo helper existente |
| Dependências | Produtos da OS, slider, desconto, classes fiscais e helpers de transporte |
| Origem dos dados | OS, estado da sessão e `transport_snapshot` |

Achado de UX: “Reboques” exige JSON bruto. É funcional, mas inadequado para usuário comum.

### Step 7 - Nota Fiscal de Serviço

Este step existe somente quando `note_mode` é `nfse` ou `both`; quando a emissão é apenas NF-e, o step 6 é o último.

| Aspecto | Resultado |
| --- | --- |
| Objetivo | Configurar a NFS-e dos serviços da OS |
| Campos | `tax_class`, `service_description`, `additional_information` |
| Obrigatórios | Classe fiscal válida e descrição do serviço não vazia |
| Dependências | Serviços da OS, slider, desconto e classes fiscais NFS-e |
| Origem dos dados | OS e estado da sessão |

## Workflow Manual

A emissão manual não usa os steps acima. Ela é uma tela única com transmissão imediata após validação.

| Bloco | Campos e ações | Obrigatoriedade e validação | Origem dos dados |
| --- | --- | --- | --- |
| Destinatário | `recipient`; botão “Nova pessoa” | Cliente ativo da oficina; não aceita cliente de outra oficina | `Customer`; cadastro rápido reutiliza `QuickCustomerCreateView` |
| Configuração fiscal | `tax_class`; `additional_information` | Classe fiscal NF-e válida; informações complementares opcionais | Classes retornadas por `list_tax_classes` |
| Itens | Produto, quantidade, valor unitário; adicionar/remover; “Novo produto” | Ao menos um item; quantidade mínima `0,0001`; valor mínimo `0,01`; produto ativo da oficina; produto não pode repetir | `Product`; cadastro rápido reutiliza `QuickProductForm` |
| Confirmação | “Confirmo a emissão desta NF-e pela Webmania” | Obrigatória | Entrada explícita do usuário |
| Transporte | Não apresentado | A view fixa modalidade `9`, snapshot vazio | Constantes do fluxo manual |
| Ação final | “Emitir NF-e” | Cria `NfeRequest` e itens e chama o serviço fiscal | Mesma infraestrutura fiscal da NF-e por OS |

### O que funciona

- não existe vínculo com OS ou orçamento;
- pessoa existente pode ser selecionada;
- nova pessoa pode ser criada pelo cadastro rápido existente;
- produto existente pode ser selecionado;
- novo produto pode ser criado rapidamente com código, unidade, nome, grupo, custo, venda e NCM;
- múltiplos itens são suportados;
- a transmissão chega a `get_fiscal_service().emit_nfe()` e depois à sincronização existente;
- a solicitação é identificada como `MANUAL` e aparece na Central com referência “Manual”.

### Lacunas do workflow manual

- não há stepper, resumo consolidado ou prévia antes do POST remoto;
- destinatário, classe fiscal, itens e confirmação ficam na mesma tela, aumentando carga cognitiva;
- o botão “Emitir NF-e” transmite de fato, enquanto no wizard por OS a etapa final oferece prévia;
- não existe transporte manual; o sistema força `NO_TRANSPORT` e `{}`;
- serviços não fazem parte da NF-e manual; a própria tela informa que permanecem no fluxo de NFS-e;
- o cadastro rápido de pessoa exige a permissão própria de adicionar `Customer`; o botão não é condicionado a essa permissão e pode terminar em 403;
- o cadastro rápido de produto é protegido hoje pela permissão de visualização fiscal, e não pela permissão de adicionar produto ao catálogo;
- em falha remota, a `NfeRequest` já foi criada e o usuário é redirecionado ao detalhe; a recuperação depende das ações existentes de detalhe/reconciliação, sem uma etapa explícita de revisão/reenvio na tela manual.

## Auditoria dos cenários

### Cenário 1 - Venda tradicional por OS

```text
OS -> Emitir NF -> NF-e
```

Status: preservado.

O ramo `WORK_ORDER` continua usando a mesma OS, cliente, veículo, itens, pricing snapshot, desconto, configuração fiscal, transporte, prévia, `NfeRequest`, builder, tentativa fiscal e Webmania. Nenhuma evidência de substituição do fluxo produtivo foi encontrada.

Ponto de atenção apenas de navegação: entrar pela lista de NF-e abre diretamente este fluxo, sem lembrar ao usuário que Manual também existe.

### Cenário 2 - Venda sem OS

```text
Emitir Nota -> NF-e Normal -> Manual -> Pessoa -> Produtos -> Emitir NF-e
```

Status técnico: funcional, com ressalvas de permissão e experiência.

O usuário consegue concluir o processo sem OS se:

- possuir acesso à oficina e às views envolvidas;
- houver classe fiscal NF-e disponível;
- selecionar ou cadastrar destinatário válido;
- informar ao menos um produto válido;
- confirmar a transmissão.

Bloqueador encontrado para perfis não privilegiados: `NfeManualEmissionCreateView` e `NfeManualQuickProductCreateView` declaram `model="nferequest"` com `codename="view_nfserequest"`. Essa combinação de content type e codename não corresponde à permissão padrão de `NfeRequest`. Superusuário, proprietário, diretor e gerente passam pelos atalhos do `has_workshop_perm`, mas um membro comum pode receber 403 mesmo tendo uma permissão fiscal esperada. Os testes atuais exercitam as views diretamente e não cobrem integralmente o `dispatch` do `WorkshopScopedMixin` para esse caso.

### Cenário 3 - Operação vinculada a NF anterior

#### Devolução

```text
Emitir Nota -> Devolução -> Central de Notas -> Selecionar NF-e -> detalhe -> modal existente
```

Status: o direcionamento é coerente e reutiliza o motor existente. A Central força `tipo=nfe`, preserva filtros e altera a ação para “Selecionar”. O detalhe abre automaticamente o modal se a nota e a permissão forem elegíveis.

Lacuna de UX: a devolução parcial não oferece seleção visual dos produtos. O usuário precisa preencher `produtos_json`, por exemplo `[{"sequencial":1,"quantidade":"1"}]`. Isso não atende de forma amigável à expectativa “selecionar produtos da nota de referência”, embora o backend valide o fluxo existente.

#### Carta de Correção

```text
Emitir Nota -> Carta de Correção -> Central de Notas -> Selecionar NF-e -> detalhe -> modal de CC-e
```

Status: coerente. A nota de referência é escolhida na Central, a elegibilidade é revalidada no detalhe e o modal pede somente o texto da correção, com limites de 15 a 1.000 caracteres. Histórico, XML e DACCE permanecem no detalhe.

Ponto de fricção: o usuário atravessa Central e detalhe para chegar ao modal, mas há contexto suficiente e o modal é aberto automaticamente quando permitido.

#### Complementar e Ajuste

O direcionamento segue o mesmo padrão e reutiliza os fluxos existentes. Entretanto, os modais expõem estruturas técnicas:

- complementar exige “Itens complementares em JSON”;
- ajuste exige “Cliente em JSON”;
- reboques de transporte também exigem JSON.

São campos operáveis por usuário fiscal especializado, mas não constituem uma UX adequada para usuário comum.

## Auditoria de permissões e segurança

### Comportamentos corretos

- o gateway filtra Devolução, CC-e, Complementar e Ajuste conforme permissões existentes;
- POST manipulado para operação derivada não autorizada é bloqueado;
- o detalhe revalida permissão e elegibilidade da nota selecionada;
- todos os querysets relevantes são limitados à oficina ativa;
- os endpoints finais permanecem como autoridade de autorização.

### Inconsistências encontradas

1. Gateway, wizard unificado e Central usam como permissão-base `view_nfserequest`, mesmo quando a ação é iniciar ou visualizar NF-e.
2. A view manual combina content type `nferequest` com codename `view_nfserequest`, combinação inválida para membros comuns.
3. NF-e Normal e Transporte não possuem mapeamento específico em `OPERATION_PERMISSIONS`; dependem apenas da permissão-base do gateway e das views seguintes.
4. “Nova pessoa” depende de `add_customer`, mas o botão não é ocultado quando essa permissão falta.
5. “Novo produto” cria entidade de catálogo sem exigir a permissão padrão `add_product`; hoje usa a permissão fiscal declarada na view.

Não foi encontrado bypass de oficina ou dos endpoints fiscais. Os achados acima são de coerência e granularidade de autorização, podendo causar tanto 403 inesperado quanto capacidade de cadastro mais ampla que a nomenclatura das permissões sugere.

## Auditoria de UX/UI

### Pontos positivos

- o menu principal possui uma única entrada “Emitir nota”;
- os cards do gateway explicam a finalidade de cada operação;
- a escolha `Ordem de Serviço`/`Manual` é explícita quando o usuário chega pela rota canônica;
- a emissão manual informa claramente que não movimenta estoque e que serviços permanecem na NFS-e;
- a Central distingue origem manual no campo de OS;
- as operações referenciadas preservam contexto e retornam à Central;
- mensagens de indisponibilidade são apresentadas quando a NF-e escolhida não é elegível.

### Problemas priorizados

| Prioridade | Problema | Impacto no usuário |
| --- | --- | --- |
| P0 | Permissão inconsistente da view manual (`nferequest` + `view_nfserequest`) | Membro comum pode não conseguir abrir a emissão manual, embora ela apareça como opção |
| P1 | Lista de NF-e pula a escolha de origem por causa dos parâmetros legados | Usuário não descobre a emissão sem OS |
| P1 | Manual e OS têm padrões de interação diferentes; manual transmite sem prévia | Maior risco de erro e sensação de fluxo incompleto |
| P1 | Card Transporte abre somente o ramo OS; Manual força sem transporte | NF-e manual com transporte não pode ser concluída |
| P1 | Devolução parcial, Complementar, Ajuste e reboques exigem JSON | Usuário comum não consegue operar com segurança |
| P1 | Origem Manual pode exibir alerta obsoleto de “próxima fase” | Contradição direta com funcionalidade disponível |
| P2 | Quem escolheu NF-e Normal volta a escolher NF-e/NFS-e/Ambas no wizard | A hierarquia de escolhas parece redundante e contraditória |
| P2 | Título do wizard enfatiza “conferir a OS” sem dizer que é o ramo escolhido | Reforça a percepção de dependência global de OS |
| P2 | Ações de cadastro rápido não refletem visualmente permissões específicas | Clique pode terminar em 403 ou permissão semântica inadequada |
| P3 | Há textos sem acentuação em partes do wizard (“Emissao”, “Servico”, “veiculo”) | Reduz acabamento e consistência da interface pt-BR |

## Análise técnica

### Models envolvidos

| Model | Papel |
| --- | --- |
| `NfeRequest` | Intenção única de emissão; aceita `workorder` ou `manual_recipient` conforme `emission_origin` |
| `NfeEmissionOrigin` | Enum `WORK_ORDER`/`MANUAL` |
| `NfeRequestManualItem` | Produto, quantidade e valor unitário da emissão manual; restringe produto à mesma oficina |
| `NfeItem` | Resultado remoto associado à request; suporta request manual sem workorder |
| `WorkOrder` | Fonte do ramo por OS, incluindo orçamento, cliente, veículo, itens e pricing |
| `Customer` | Destinatário manual ou cliente do orçamento da OS |
| `Product` | Item reutilizado pelo fluxo manual e pelo cadastro rápido |
| `NfseRequest` | Emissão de serviço ainda vinculada à OS no wizard unificado |
| `FiscalEmissionAttempt` | Tentativa idempotente e snapshot do payload enviado |
| `FiscalDocument` / `FiscalDocumentLink` | Documentos e vínculos de devolução, complementar e ajuste |
| `FiscalDocumentEvent` | CC-e e demais eventos fiscais |

A constraint `nfe_request_origin_matches_workorder` garante:

- `WORK_ORDER`: OS obrigatória e destinatário manual ausente;
- `MANUAL`: OS ausente e destinatário manual obrigatório.

Essa modelagem está adequada e não precisa ser substituída para corrigir a UX.

### Forms

- `FiscalOperationGatewayForm`
- `NfeEmissionOriginGatewayForm`
- `EmissionStep1Form` a `EmissionStep5Form`
- `EmissionNfeConfigForm`
- `EmissionNfseConfigForm`
- `NfeManualEmissionForm`
- `NfeManualItemForm` / `NfeManualItemFormSet`
- `QuickCustomerForm`
- `QuickProductForm`
- helpers de `apps/finance/forms/nfe_transport.py`
- `NfeCorrectionForm`
- `NfeReturnForm`
- `NfeComplementaryPriceQuantityForm`
- `NfeAdjustmentForm`

### Views

- `FiscalOperationGatewayView`
- `NfeEmissionOriginGatewayView`
- `EmissionRequestCreateView`
- `EmissionPreviewView`
- `EmissionWorkOrderItemUpdateView`
- `EmissionWorkOrderKitComponentUpdateView`
- `NfeManualEmissionCreateView`
- `NfeManualQuickProductCreateView`
- `QuickCustomerCreateView`
- `IssuedDocumentsListView`
- `NfeRequestDetailView`
- `NfeCorrectionIssueView`
- `NfeReturnIssueView`
- `NfeComplementaryPriceQuantityIssueView`
- `NfeAdjustmentIssueView`

### Templates

- `finance/fiscal_operation_gateway.html`
- `finance/nfe_emission_origin_gateway.html`
- `finance/emission_request_form.html`
- `finance/partials/emission_step_content.html`
- `finance/nfe_manual_emission_form.html`
- `finance/partials/nfe_manual_quick_product_modal.html`
- template modal do cadastro rápido de cliente
- `finance/issued_documents_list.html`
- `finance/partials/issued_documents_results.html`
- `finance/nfe_request_detail.html`

### Services e helpers

- `get_fiscal_service()` / `WebmaniaFiscalService`
- `build_nfe_payload()`
- `emit_nfe_request()`
- `sync_nfe_emission_response()`
- `begin_emission_attempt()` e serviços de `FiscalEmissionAttempt`
- `list_tax_classes()`
- pricing e snapshots do workorder
- helpers de transporte em `apps/finance/nfe_transport.py`
- serviços existentes de CC-e, devolução, complementar e ajuste

As duas origens convergem em:

```text
NfeRequest
  -> get_fiscal_service().emit_nfe(...)
  -> emit_nfe_request(...)
  -> build_nfe_payload(...)
  -> FiscalEmissionAttempt
  -> Webmania
```

Não há justificativa para novo builder, payload ou serviço fiscal.

## Arquivos candidatos a alteração futura

### Alterações somente visuais/textuais

- `apps/finance/templates/finance/nfe_emission_origin_gateway.html`: remover alerta obsoleto e revisar texto da origem.
- `apps/finance/templates/finance/emission_request_form.html`: identificar explicitamente “Emissão por Ordem de Serviço” e revisar acentuação.
- `apps/finance/templates/finance/nfe_manual_emission_form.html`: melhorar hierarquia, separar revisão e esclarecer efeito irreversível do botão.
- `apps/finance/forms/emission.py`: revisar textos dos steps e retirar ambiguidade entre NF-e Normal e NFS-e.
- `apps/finance/forms/nfe_transport.py`: substituir futuramente JSON de reboques por formset visual, sem mudar snapshot.
- `apps/finance/templates/finance/nfe_request_detail.html`: substituir entradas JSON de operações por controles guiados.

### Alterações de navegação/permissão

- `apps/finance/templates/finance/nfe_request_list.html`: fazer “Emitir nova NF-e” passar pela escolha de origem.
- `apps/finance/views/fiscal_gateway.py`: consolidar permissões-base de NF-e Normal/Manual/Transporte e reduzir o bypass de navegação legado.
- `apps/finance/views/nfe_manual.py`: corrigir a permissão da emissão manual e separar a permissão de cadastro de produto.
- `apps/customer/views.py` e/ou template manual: expor “Nova pessoa” apenas quando `add_customer` estiver disponível.
- `apps/finance/test_fiscal_operation_gateway.py` e `apps/finance/test_nfe_manual_emission.py`: testar o `dispatch` real com membro comum e matriz de permissões.

### Alterações de workflow

- `apps/finance/views/emission.py`: somente se for aprovada uma casca comum de steps; o ramo existente por OS não deve ser reescrito.
- `apps/finance/forms/nfe_manual.py` e `apps/finance/views/nfe_manual.py`: introduzir revisão/prévia e, se aprovado, transporte manual reutilizando os helpers existentes.
- `apps/finance/templates/finance/nfe_manual_emission_form.html`: dividir a experiência manual em etapas ou revisão explícita.
- `apps/finance/forms/nfe_transport.py`: reutilizar os mesmos campos no ramo manual; não criar contrato paralelo.
- forms/templates das operações referenciadas: trocar JSON por formsets/controles estruturados mantendo os services atuais.

## Menor caminho seguro de adequação

1. Tornar o gateway e a escolha de origem as entradas canônicas de NF-e.
2. Corrigir a matriz de permissões antes de ampliar qualquer tela.
3. Renomear o wizard atual para deixar claro que ele é o ramo “por Ordem de Serviço”.
4. Manter internamente os dois ramos e o mesmo motor fiscal; não tentar tornar os forms da OS genéricos à força.
5. Dar ao ramo manual uma revisão explícita antes da transmissão. A primeira versão pode continuar em uma página, desde que o CTA final mostre resumo e intenção inequívoca; um stepper completo pode vir depois.
6. Reutilizar `configure_nfe_transport_form`, `clean_nfe_transport_form`, `freight_mode` e `transport_snapshot` se transporte manual for aprovado.
7. Substituir JSONs técnicos gradualmente por formsets sem mudar os payloads dos services existentes.

A correção da percepção de dependência de OS não exige reconstruir o módulo. Ela começa por corrigir entradas, nomes e permissões. A evolução do manual para revisão/prévia é uma segunda etapa controlada.

## Fases sugeridas

### Fase 4.2.7A - Entradas e permissões

- corrigir a permissão da view manual;
- definir permissão explícita para NF-e Normal, Manual e Transporte;
- respeitar `add_customer` e `add_product` nos cadastros rápidos;
- fazer o botão da lista de NF-e passar pela escolha de origem;
- adicionar testes de integração com `dispatch` real para perfis comuns;
- não alterar emissão, builder ou payload.

Critério de aceite: todo usuário autorizado vê apenas caminhos que consegue concluir, e toda entrada “Emitir NF-e” oferece OS/Manual.

### Fase 4.2.7B - Consistência visual e linguagem

- remover o alerta obsoleto da origem Manual;
- renomear o wizard para “Emissão por Ordem de Serviço”;
- alinhar títulos, acentuação, breadcrumbs e CTAs;
- explicar por que o ramo OS pode emitir NF-e, NFS-e ou ambas;
- manter o workflow produtivo intacto.

Critério de aceite: o usuário sabe em qual ramo está e entende que OS é uma origem, não uma obrigação global.

### Fase 4.2.7C - Revisão e transporte da NF-e manual

- incluir resumo/prévia antes da transmissão manual;
- reutilizar o mesmo preview/builder sempre que a arquitetura permitir, sem criar motor paralelo;
- adicionar transporte manual com os mesmos helpers e snapshot existentes, se confirmado como requisito;
- preservar `NfeRequest`, `FiscalEmissionAttempt` e Webmania.

Critério de aceite: a emissão manual permite revisar destinatário, itens, valores, classe e transporte antes do POST remoto.

### Fase 4.2.7D - Formulários guiados das operações referenciadas

- devolução parcial com seleção visual de itens e quantidades disponíveis;
- complementar com formset de itens;
- ajuste com campos estruturados de cliente;
- reboques com linhas estruturadas;
- manter os mesmos services, validações, snapshots e payloads existentes.

Critério de aceite: nenhuma operação de uso comum exige que o usuário escreva JSON.

## Decisão recomendada

Priorizar 4.2.7A e 4.2.7B. Elas resolvem o bloqueio de permissão e a falsa percepção de obrigatoriedade da OS com o menor risco, sem tocar no motor fiscal.

Planejar 4.2.7C separadamente porque introduzir prévia e transporte no ramo manual altera workflow, embora possa reutilizar integralmente a infraestrutura atual. Manter 4.2.7D isolada por envolver UX fiscal especializada e exigir testes próprios para não enfraquecer validações de devolução, complementar e ajuste.

## Garantias desta auditoria

- nenhum fluxo fiscal foi reconstruído;
- nenhuma emissão foi disparada;
- nenhum código funcional foi alterado;
- nenhuma migration foi criada;
- nenhum commit foi criado;
- nenhum push foi realizado.
