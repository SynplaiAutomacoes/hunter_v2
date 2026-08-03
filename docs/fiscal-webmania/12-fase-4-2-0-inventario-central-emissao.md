# Fase 4.2.0 — Inventário técnico da Central de Emissão Fiscal

## 1. Objetivo e limites

Este documento registra a arquitetura existente de emissão e operações fiscais e avalia como transformar o atual **Emitir Nota** em uma Central de Operações Fiscais.

Esta fase é exclusivamente documental. Não foram alterados código, models, migrations, services, views, templates, testes ou OpenAPI.

Princípio obrigatório para as fases seguintes:

```text
Nova entrada
    ↓
Fluxo fiscal existente
    ↓
Motor fiscal atual
    ↓
Webmania
```

Não devem ser criados um segundo builder de NF-e, um payload paralelo, outra integração Webmania ou uma segunda regra de idempotência.

### 1.1 Base auditada

A implementação fiscal consolidada auditada é a referência Git:

```text
codex/fase-4-1-8-nfe-return-complete
commit 918030f9
```

Ela foi inspecionada diretamente, sem checkout e sem interferir no worktree corrente. A referência contém as entregas consolidadas de CC-e, devolução, transporte, complementar e ajuste descritas neste inventário.

Também foram consideradas as regras de `docs/fiscal-webmania/00-regras-de-execucao.md`, os ADRs e os registros das fases fiscais anteriores. Em qualquer divergência, o código da referência auditada foi tratado como fonte da verdade.

---

## 2. Resumo executivo da arquitetura atual

Há três superfícies distintas:

1. **Emitir Nota**: wizard unificado que parte obrigatoriamente de uma OS e cria/usa `NfeRequest` e/ou `NfseRequest`.
2. **Central de Notas Emitidas**: lista unificada de `NfeRequest` e `NfseRequest`.
3. **Detalhe da NF-e**: hub operacional da NF-e, onde ficam cancelar, inutilizar numeração, reconciliar, CC-e, devolução/estorno, complementar, ajuste, eventos IBS/CBS e downloads.

Para a NF-e normal, o fluxo real é:

```text
WorkOrder
    ↓
NfeRequest
    ↓
build_nfe_payload(...)
    ↓
FiscalEmissionAttempt
    ↓
Webmania
    ↓
NfeItem
```

`FiscalDocument` não substitui `NfeRequest`/`NfeItem` na emissão normal. Ele é a representação fiscal normalizada usada pelos eventos e documentos derivados. Para uma NF-e legada/autorizada, é criado sob demanda por `ensure_fiscal_document_for_nfe_item(...)`.

As consequências arquiteturais são:

- emissão normal ainda é centrada em `NfeRequest` + `NfeItem`;
- CC-e usa `FiscalDocumentEvent`;
- devolução, complementar e ajuste usam `FiscalDocument`, `FiscalDocumentLink` e `FiscalEmissionAttempt`;
- transporte é configuração da mesma emissão NF-e normal, não um motor nem documento separado;
- a interface atual exige OS, embora os motores de documentos derivados já estejam mais desacoplados dela;
- a Central de Notas não é ainda uma visão completa de todos os `FiscalDocument` e eventos.

---

## 3. Mapa de telas, entradas e URLs

### 3.1 Como o usuário chega ao “Emitir Nota”

O menu é definido em:

- `apps/core/presentation/navigation.py`
- agrupamento: **Financeiro**
- item: **Emitir nota**
- rota: `finance:emission_create`
- query usada para reiniciar o wizard: `?reset=1`

O prefixo global é registrado em `config/urls.py`:

```text
/finance/
```

A rota em `apps/finance/urls.py` é:

```text
/finance/emissao/?reset=1
finance:emission_create
EmissionRequestCreateView
```

**URL inicial efetiva:** `/finance/emissao/?reset=1`.

As antigas entradas de criação continuam compatíveis:

- `finance:nfe_create` redireciona para `finance:emission_create?tipo=nfe&reset=1`;
- a criação de NFS-e redireciona de modo equivalente para o wizard unificado.

Não há hoje uma seleção inicial de “tipo de operação fiscal”. A primeira decisão do usuário é a seleção da OS.

### 3.2 Tela e componentes do wizard unificado

| Responsabilidade | Arquivo/classe |
|---|---|
| Orquestração principal | `apps/finance/views/emission.py` — `EmissionRequestCreateView` |
| Verificação de emissão anterior da OS | `apps/finance/views/emission.py` — `EmissionCheckWorkorderView` |
| Edição de item da OS | `EmissionWorkOrderItemUpdateView` |
| Edição de componente de kit | `EmissionWorkOrderKitComponentUpdateView` |
| Forms do wizard | `apps/finance/forms/emission.py` |
| Página principal | `apps/finance/templates/finance/emission_request_form.html` |
| Conteúdo dinâmico da etapa | `apps/finance/templates/finance/partials/emission_step_content.html` |
| Corpo/painel do resumo | `emission_step4_body.html` e `emission_step4_panel.html` |
| Modal de preview | `emission_preview_modal.html` |
| Modal de tipo de desconto | `emission_discount_type_modal.html` |
| Modais de edição | `modal_edit_workorder_item.html` e `modal_edit_workorder_kit_component.html` |

Rotas auxiliares:

- `/finance/emissao/preview/`;
- `/finance/emissao/check-workorder/`;
- endpoints de edição de item e de componente de kit da OS.

### 3.3 HTMX e JavaScript

Não foi encontrado bundle JavaScript exclusivo da emissão. O comportamento está distribuído entre templates e atributos produzidos pelos forms:

- navegação entre etapas por `hx-get`, atualizando `#step-container`;
- submissão por `hx-post` para a etapa atual;
- `hx-push-url` ao voltar;
- abertura e fechamento dos modais de cliente, veículo e itens;
- refresh da etapa após eventos `customerSaved`, `vehicleSaved` e `financeEmissionWorkorderItemSaved`;
- bloqueio visual do botão e spinner durante a requisição;
- preview e recálculo do slider por HTMX;
- troca fora de banda de avisos/painéis;
- modal de preview que dispara a transmissão de volta ao wizard.

Arquivos centrais:

- `finance/emission_request_form.html`: gerenciamento do `dialog`, eventos HTMX e refresh;
- `finance/partials/emission_step_content.html`: navegação, form, loading e submit;
- `apps/finance/forms/emission.py`: atributos HTMX do select de OS, slider e painéis;
- `finance/partials/emission_preview_modal.html`: confirmação da transmissão.

### 3.4 Permissões

`EmissionRequestCreateView` usa:

- `LoginRequiredMixin`;
- `WorkshopScopedMixin`;
- app `finance`;
- model/codename legado `nfserequest/view_nfserequest`.

O mesmo codename é reutilizado em partes da Central unificada, inclusive quando a operação é NF-e. Isso funciona, mas é uma dívida arquitetural: uma futura Central de Operações deve definir permissões por capacidade/operação sem retirar os fallbacks atuais.

Todos os lookups relevantes do wizard são limitados à oficina ativa. Esse isolamento deve permanecer obrigatório.

### 3.5 Cadeia completa de tela até a Webmania

O fluxo de uma NF-e normal é o seguinte:

```text
Menu Financeiro > Emitir nota
    ↓ GET /finance/emissao/?reset=1
EmissionRequestCreateView.get()
    ↓
emission_request_form.html
    + partials/emission_step_content.html
    ↓ POST /finance/emissao/?step=N
EmissionRequestCreateView.form_valid()
    ↓
_get_or_create_nfe_request()
    ↓
NfeRequest.save()
    ↓ preview
NfePreviewPdfView
    ↓
get_fiscal_service().download_nfe_preview_document()
    ↓
build_nfe_payload() + previa_danfe=True
    ↓
POST Webmania /1/nfe/emissao/
    ↓ confirmação no modal
POST /finance/emissao/?step=<nfe_config ou nfse_config>
    ↓
EmissionRequestCreateView._finalize_selected_notes()
    ↓
EmissionRequestCreateView._emit_nfe()
    ↓
get_fiscal_service().emit_nfe()
    ↓
WebmaniaFiscalService.emit_nfe()
    ↓
emit_nfe_request()
    ↓
reserve_nfe_request_number()
    ↓
build_nfe_payload()
    ↓
begin_emission_attempt()
    ↓
POST Webmania /1/nfe/emissao/
    ↓
mark_attempt_succeeded()/failed()/uncertain()
    ↓
sync_nfe_emission_response()
    ↓
NfeItem.update_or_create(workorder, uuid)
```

Mapa dos endpoints acionados diretamente pela tela:

| Endpoint | Nome | Método/owner | Uso |
|---|---|---|---|
| `/finance/emissao/` | `finance:emission_create` | `EmissionRequestCreateView` | Página, steps, reset, close, preview de painel e finalização |
| `/finance/emissao/check-workorder/` | `finance:emission_check_workorder` | `EmissionCheckWorkorderView` | Aviso HTMX de NF-e/NFS-e já existente |
| `/finance/emissao/preview/` | `finance:emission_preview` | `EmissionPreviewView` | Rota registrada para o corpo do resumo; não foi localizado call site por nome na UI consolidada |
| `/finance/emissao/workorder/<workorder_pk>/item/<item_id>/edit/` | `finance:emission_workorder_item_edit` | `EmissionWorkOrderItemUpdateView` | Edita item real da OS |
| `/finance/emissao/workorder/<workorder_pk>/kit-item/<item_id>/<component_type>/<component_id>/edit/` | `finance:emission_workorder_kit_component_edit` | `EmissionWorkOrderKitComponentUpdateView` | Persiste override de componente do kit |
| `/finance/nfe/<pk>/previa/pdf/` | `finance:nfe_preview_pdf` | `NfePreviewPdfView` | Gera/baixa a prévia da Webmania |

O `emission_preview_modal.html` não transmite diretamente para a Webmania. Ele repostará o form com os campos ocultos e sem o intent de preview; só então `_finalize_selected_notes()` executará a emissão.

---

## 4. Workflow completo do wizard atual

O estado transitório é mantido em sessão:

```text
finance.emission_wizard:{workshop_id}:{user_id}
```

Assim, dois usuários ou duas oficinas não compartilham o mesmo estado.

### 4.1 Etapas base

| Etapa | Identificador/título | Form | Dados manipulados |
|---|---|---|---|
| 1 | `workorder` — Selecionar OS | `EmissionStep1Form` | Seleciona `WorkOrder` aprovada da oficina. Exclui OS que já possua simultaneamente requisições NF-e e NFS-e. Consulta alertas de emissão anterior. |
| 2 | `customer` — Conferir Cliente | `EmissionStep2Form` | Exibe cliente de `workorder.budget.customer` e veículo. Permite abrir modais de edição rápida; não escolhe nem cria destinatário independente. |
| 3 | `items` — Conferir Produtos/Serviços | `EmissionStep3Form` | Exibe produtos, serviços, kits e componentes da OS. Permite editar quantidade, custo e preço nos registros operacionais da OS. |
| 4 | `summary` — Resumo | `EmissionStep4Form` | Manipula `pricing_slider`, tipo de desconto e resumo calculado pelo serviço de precificação. |
| 5 | `note_mode` — Emitir Nota | `EmissionStep5Form` | Escolhe NF-e, NFS-e ou ambas, conforme produtos/serviços disponíveis e requisições já existentes. |

### 4.2 Etapas dinâmicas

Depois da etapa 5, a sequência é montada conforme `note_mode`:

- `nfe`: adiciona `nfe_config`;
- `nfse`: adiciona `nfse_config`;
- `both`: adiciona `nfe_config` e depois `nfse_config`.

| Etapa | Form | Dados |
|---|---|---|
| `nfe_config` | `EmissionNfeConfigForm` | Classe de imposto, informações adicionais, modalidade do frete e snapshot completo de transporte. |
| `nfse_config` | `EmissionNfseConfigForm` | Classe de imposto, descrição do serviço e informações adicionais. |

### 4.2.1 Step 1 atual — `workorder`

**Objetivo:** selecionar a OS aprovada que fornecerá toda a origem operacional.

| Item | Implementação |
|---|---|
| View | `EmissionRequestCreateView` |
| Form | `apps/finance/forms/emission.py` — `EmissionStep1Form` |
| Campo | `workorder`: `ModelChoiceField`, obrigatório |
| Template | `emission_request_form.html` + `partials/emission_step_content.html`; o layout interno é produzido pelo form |
| Endpoint auxiliar | `finance:emission_check_workorder` |

Validações/filtros reais:

- `WorkOrder.workshop == oficina ativa`;
- `WorkOrder.status == WorkOrderStatus.APPROVED`;
- `select_related` de orçamento, cliente e veículo;
- anota existência de `NfeRequest` e `NfseRequest`;
- exclui a OS somente quando as duas requisições já existem;
- o próprio `ModelChoiceField` rejeita PK fora do queryset;
- o endpoint de aviso repete o filtro por oficina;
- a label é `Ordem de Servico <get_id> - <cliente>`.

Ao salvar:

- `form_valid()` grava `workorder_id` na sessão;
- se a OS mudou, limpa slider, override de desconto, configurações NF-e/NFS-e e progresso de submissão;
- mantém um `tipo=nfe|nfse|both` pré-selecionado, quando presente;
- avança para `customer`.

### 4.2.2 Step 2 atual — `customer`

**Objetivo:** conferir dados existentes; não selecionar nem cadastrar um novo destinatário.

| Item | Implementação |
|---|---|
| Form | `EmissionStep2Form` |
| Campos submetidos | nenhum campo de negócio |
| Fonte | `workorder.budget.customer` e `workorder.budget.vehicle` |
| Ações | `customer:quick_update` e `customer:vehicle_quick_update` |

Dados exibidos:

- nome;
- CPF/CNPJ;
- telefone;
- e-mail;
- endereço completo;
- veículo.

O form não possui `clean()` nem validação fiscal de destinatário. Ele apenas renderiza dados escapados. As alterações rápidas persistem globalmente no cadastro e o evento HTMX atualiza a etapa.

Ao salvar, `form_valid()` apenas avança para `items`. A validação fiscal obrigatória de endereço/documento ocorre mais tarde em `_build_customer_payload(...)`, já dentro do builder.

### 4.2.3 Step 3 atual — `items`

**Objetivo:** conferir e editar produtos/serviços que já pertencem à OS.

| Item | Implementação |
|---|---|
| Form | `EmissionStep3Form` |
| Campos submetidos | nenhum campo direto |
| Leitura | `_build_step3_rows(workorder=...)` |
| Edição de item | `EmissionWorkOrderItemUpdateView` + `WorkOrderItemEditForm` |
| Edição de kit | `EmissionWorkOrderKitComponentUpdateView` + forms `EmissionKitProductComponentForm`/`EmissionKitServiceComponentForm` |
| Permissão de edição | `workorder.change_workorder` |

Os itens são pré-carregados com `workorder_items_with_kit_prefetch(with_kit_tree=True)`. O step separa produtos e serviços, mostra descrição, quantidade, preço unitário e total.

Validações das edições:

- OS sempre filtrada pela oficina;
- `WorkOrderItem` deve pertencer simultaneamente à OS e à oficina;
- componente deve pertencer ao kit do item;
- quantidade do componente aceita zero ou mais;
- custo/preço/frete/duração são validados pelos forms específicos;
- overrides são persistidos em `WorkOrderKitItemOverride`;
- o evento `financeEmissionWorkorderItemSaved` fecha o modal e recarrega a etapa.

Importante: a edição altera dados/overrides operacionais da OS; não cria um snapshot fiscal próprio. Ao salvar o step principal, a view apenas avança para `summary`.

### 4.2.4 Step 4 atual — `summary`

**Objetivo:** distribuir os valores entre produto/serviço e revisar totais.

| Item | Implementação |
|---|---|
| Form | `EmissionStep4Form` |
| Campo | `pricing_slider`, inteiro obrigatório entre -100 e 100 |
| Cálculo | `build_step5_pricing_panel_data(...)`, `build_slider_allocation_for_workorder(...)` |
| Preview HTMX | `?step=4&preview=1`, retorno `emission_step4_panel.html`/OOB |

Validações:

- `clean_pricing_slider()` normaliza com `clamp_slider_value(...)`;
- a view calcula `products_target` e `services_target`;
- se ambos forem zero, bloqueia o avanço;
- a mudança do slider limpa IDs/progresso de emissões ainda não concluídas.

O valor inicial vem primeiro da sessão, depois de `workorder.budget.slider`. O preview é abortável/sincronizado via atributos HTMX produzidos pelo form.

### 4.2.5 Step 5 atual — `note_mode`

**Objetivo:** escolher quais documentos normais da OS serão emitidos.

Campo `note_mode`:

- `nfe`: Nota Fiscal de Produto;
- `nfse`: Nota Fiscal de Serviço;
- `both`: ambas.

Validações:

- a opção precisa existir em `_allowed_note_modes`;
- disponibilidade de NF-e exige `products_target > 0`;
- disponibilidade de NFS-e exige `services_target > 0`;
- existência anterior de `NfeRequest` remove `nfe` e `both`;
- existência anterior de `NfseRequest` remove `nfse` e `both`;
- se ambas já existem, nenhuma opção é permitida;
- incompatibilidade entre o tipo de desconto da OS e o modo escolhido abre `emission_discount_type_modal.html`;
- o override vale somente para a emissão e é guardado na sessão.

Esse step escolhe **tipo de documento normal** (produto/serviço), não tipo de operação fiscal. Reutilizá-lo para CC-e/devolução misturaria duas decisões diferentes.

### 4.2.6 Step dinâmico — `nfe_config`

**Objetivo:** completar configuração fiscal da NF-e normal e abrir a prévia.

Campos diretos:

- `tax_class`;
- `additional_information`.

Campos adicionados por `configure_nfe_transport_form(...)`:

- `freight_mode`;
- tipo, CPF/CNPJ, nome/razão social e IE do transportador;
- endereço, UF, cidade e CEP do transportador;
- placa, UF do veículo e RNTRC/ANTT;
- quantidade, espécie, marca, pesos bruto/líquido, numeração e lacres dos volumes;
- `nfe_transport_trailers_json`.

Validações:

- classe precisa constar na lista ativa retornada por `list_tax_classes(workshop=...)`;
- classes identificadas como NFS-e não aparecem na lista NF-e;
- informação adicional é normalizada por `sentence_case`;
- `clean_nfe_transport_form()` chama `build_nfe_transport_snapshot(...)`;
- modalidade deve ser uma de 0, 1, 2, 3, 4 ou 9;
- modalidade 9 rejeita detalhes de transporte preenchidos;
- documento/nome, UF, placa, volumes, pesos e reboques são validados em `apps/finance/nfe_transport.py`;
- antes de preview/emissão, NCM e código de produto são conferidos;
- o builder volta a validar classe remota e prontidão IBS/CBS.

Ao salvar:

- persiste a configuração na sessão;
- em modo `both`, avança para `nfse_config`;
- nos demais casos, `intent=preview` chama `_build_preview_response()`;
- `_get_or_create_nfe_request()` só é chamado ao preparar o preview ou transmitir.

### 4.2.7 Step dinâmico — `nfse_config`

Este inventário é centrado em NF-e, mas o step faz parte do mesmo wizard:

- `tax_class`;
- `service_description`;
- `additional_information`;
- classe deve constar na lista NFS-e ativa;
- descrição é obrigatória após `clean()`;
- descrição e informação adicional usam `sentence_case`;
- em `both`, a NF-e pode já estar concluída; um retry posterior tenta somente a NFS-e pendente.

### 4.2.8 Preview e confirmação final

O preview:

1. valida NCM;
2. cria/atualiza `NfeRequest`;
3. gera `embed_url` para `finance:nfe_preview_pdf`;
4. renderiza `emission_preview_modal.html`;
5. conserva os dados limpos em hidden fields.

A confirmação:

1. percorre `nfe` e/ou `nfse`;
2. ignora branch já marcado como concluído;
3. obtém lock de cache por oficina + OS + tipo de nota, por 120 segundos;
4. emite e sincroniza;
5. registra sucesso parcial no modo `both`;
6. em erro, retorna ao step de configuração correspondente;
7. no sucesso total, limpa a sessão.

O lock de UI/cache evita concorrência imediata, enquanto `FiscalEmissionAttempt` é a proteção fiscal persistente e obrigatória. Um não substitui o outro.

### 4.2.9 Ponto exato para a escolha de operação

Não é seguro apenas inserir `operation` antes de `workorder` em `base_steps_definition`. Hoje:

- `_load_state()` força `current_step = 1` quando não há `workorder_id`;
- `_current_step()` retorna 1 quando `_selected_workorder()` é `None`;
- `get_form_kwargs()` e vários steps pressupõem uma OS selecionada;
- a chave de lock contém `workorder_id`;
- `_handle_invalid_workorder()` reinicia o wizard;
- `_get_or_create_nfe_request()` recebe `workorder` obrigatório.

Portanto, o novo “Step 1 — Tipo de operação” deve ser visualmente o primeiro passo, mas tecnicamente uma **view roteadora anterior ao state machine existente**.

Compatibilidade sugerida:

```text
GET /finance/emissao/
    → nova tela de operações

GET /finance/emissao/normal/?reset=1
    → EmissionRequestCreateView atual, sem alterar seus steps

GET /finance/emissao/?tipo=nfe|nfse|both&reset=1
    → gateway reconhece link legado e redireciona para /emissao/normal/
```

Os nomes de rota antigos devem continuar resolvendo. Essa separação evita introduzir branches de CC-e/devolução dentro de métodos que exigem `WorkOrder`.

### 4.3 Persistência, preview e emissão

Na configuração/finalização de NF-e:

1. `_get_or_create_nfe_request(...)` cria ou atualiza `NfeRequest`;
2. vincula oficina e OS;
3. persiste classe tributária, observação, slider, override de desconto, `freight_mode` e `transport_snapshot`;
4. o preview usa o mesmo builder fiscal com marca de preview;
5. a confirmação final chama `_emit_nfe(...)`;
6. `_emit_nfe(...)` usa `get_fiscal_service().emit_nfe(...)`;
7. a resposta é persistida por `sync_nfe_emission_response(...)`;
8. o status da requisição é atualizado;
9. a sessão de submissão impede duplo clique/reenvio imediato;
10. no sucesso, o estado do wizard é limpo.

### 4.4 Fluxo legado ainda presente

`apps/finance/views/nfe.py` mantém o workflow legado para atualização e compatibilidade:

- `NfeRequestCreateView`;
- `NfeRequestUpdateView`;
- bases em `apps/finance/views/request_workflow.py`;
- `NfeRequestStep1Form`, `NfeRequestStep2Form`, `NfeRequestStep3Form`;
- templates `nfe_request_form.html`, `nfe_step_content.html` e `nfe_step3_preview.html`.

A rota de criação antiga redireciona para o wizard unificado, mas detalhes/edição ainda dependem dessas superfícies. Elas não devem ser removidas numa primeira evolução.

---

## 5. Dependências da OS e relação com a NF-e

### 5.1 A NF-e normal depende hoje de OS?

Sim, no fluxo produtivo auditado.

A dependência não está apenas na tela. Ela atravessa model, forms, builder, precificação, sincronização e consultas:

- `NfeRequest.workorder` é obrigatório;
- `NfeItem.workorder` é obrigatório;
- a seleção inicial do wizard exige uma `WorkOrder`;
- o destinatário é lido de `workorder.budget.customer`;
- itens e valores são lidos do snapshot de precificação da OS;
- pagamento é lido dos pagamentos da OS;
- veículo é exibido a partir do contexto da OS/orçamento;
- `customer_name`, pesquisas e telas navegam pela mesma cadeia.

Portanto, tornar somente `NfeRequest.workorder` anulável não produziria emissão manual funcional e ainda criaria falhas tardias.

### 5.2 Origem dos dados da emissão normal

| Dado fiscal/operacional | Origem atual |
|---|---|
| Oficina/emitente | `NfeRequest.workshop` e configuração Webmania da oficina |
| Destinatário | `NfeRequest.workorder.budget.customer` |
| Veículo/contexto | OS/orçamento |
| Produtos | itens e componentes de produto da OS, resolvidos pelo snapshot de precificação |
| Serviços | itens de serviço da OS; direcionam a possibilidade de NFS-e |
| Quantidades, preços, custo | registros da OS e cálculo de precificação |
| Desconto | orçamento/OS, com override na requisição |
| Slider | requisição, inicializado do orçamento/OS |
| Pagamento | primeiro registro de pagamentos da OS |
| Classe tributária | `NfeRequest.tax_class` |
| Informações adicionais | `NfeRequest.additional_information` |
| Transporte | `NfeRequest.freight_mode` + `transport_snapshot` |
| Estoque | não é consultado nem baixado diretamente pelo builder de NF-e |

### 5.3 Matriz completa de acoplamento

| Camada/ponto | Leitura da OS | Obrigatória hoje | Pode existir sem OS? | Desacoplamento necessário |
|---|---|---:|---:|---|
| `EmissionStep1Form` | seleciona a própria `WorkOrder` | sim | não se aplica | manter no fluxo OS; criar entrada manual separada |
| `EmissionRequestCreateView._selected_workorder()` | OS + orçamento + cliente + veículo + itens/kits | sim | sim | resolver uma `EmissionOrigin` em vez de exigir OS para todo fluxo |
| Sessão do wizard | `workorder_id` | sim | sim | guardar `origin_type` e um identificador de rascunho manual |
| Lock de submissão | `workorder_id` | sim | sim | chavear por `NfeRequest.pk`/intenção fiscal, preservando oficina e tipo |
| `NfeRequest.workorder` | FK direta | sim | sim | tornar condicional somente após introduzir origem e snapshots |
| `NfeRequest.save()` | slider do orçamento | sim na criação atual | sim | inicializar conforme origem |
| `NfeRequest.customer_name` | `workorder.budget.customer` | sim | sim | ler snapshot/vínculo conforme origem |
| `_build_customer_payload()` | cliente do orçamento | sim | sim | receber snapshot normalizado de destinatário |
| `_build_nfe_products_payload()` | snapshot de precificação da OS | sim | sim | consumir linhas fiscais normalizadas |
| `_build_payment_payload()` | primeiro pagamento da OS | não há FK obrigatória de payment, mas recebe OS | sim | consumir snapshot de pagamento |
| Desconto | valor/tipo da OS + override | sim | sim | snapshot manual de desconto e total |
| Slider/allocation | orçamento, OS e `NfeRequest.pricing_slider` | sim | opcional | fluxo manual pode informar totais diretamente ou usar política explícita |
| `build_nfe_payload()` | cliente, produtos, pagamento e log da OS | sim | sim | preservar função pública e trocar apenas a resolução de fonte por adaptador |
| `sync_nfe_emission_response()` | usa `nfe_request.workorder` no `update_or_create` | sim | sim | definir identidade do `NfeItem` sem depender exclusivamente da OS |
| `NfeItem.workorder` | FK e constraint `(workorder, uuid)` | sim | sim | FK condicional + nova constraint/identidade por request/oficina/UUID |
| Central de Notas | busca/exibe cliente e OS por relações legadas | sim para linhas normais atuais | sim | row adapter para origem OS/manual |
| Detalhe/edição | supõe requisição ligada a OS | sim em vários pontos | sim | apresentar origem e snapshots, mantendo rotas legadas |

### 5.4 Dados da OS: uso fiscal exato

**Cliente/destinatário**

`_build_customer_payload(...)` exige:

- CPF com 11 dígitos + `nome_completo`, ou CNPJ com 14 dígitos + `razao_social`;
- para CNPJ, IE informada ou `ISENTO`;
- endereço, número, bairro, cidade, UF e CEP;
- complemento, telefone e e-mail são opcionais.

Esses dados não precisam conceitualmente de OS. Precisam de um snapshot válido e auditável.

**Produtos**

`_extract_product_lines(...)` usa `build_emission_pricing_snapshot_for_workorder(...)` e ignora itens fornecidos pelo cliente. Cada linha elegível exige:

- objeto fonte `catalog.Product`;
- descrição;
- código;
- NCM com 8 dígitos;
- unidade, normalizando `UND` para `UN`;
- origem/CST;
- CEST opcional;
- quantidade positiva;
- total-base positivo.

Esses dados podem existir sem OS como linhas fiscais congeladas. O cadastro de produto pode ser fonte, mas não deve ser o histórico mutável da nota.

**Serviços**

Serviços alimentam o target de NFS-e e a descrição padrão do serviço. Não entram no array `produtos` da NF-e normal auditada. Uma Central deve manter a distinção NF-e de produto versus NFS-e de serviço em vez de enviar serviço arbitrariamente no modelo 55.

**Valores, slider e descontos**

- `build_slider_allocation_for_workorder(...)` divide o total entre `products_target` e `services_target`;
- os totais das linhas de produto são redistribuídos proporcionalmente ao target de produtos;
- o preço unitário é recalculado a partir do total alocado e quantidade;
- o desconto de produto é calculado conforme tipo da OS ou `discount_type_override`;
- o `pedido.total` recebe o target de produtos;
- o `pedido.desconto` recebe o desconto calculado.

No fluxo manual, quantidade, valor unitário, total e desconto precisam ser informados/derivados por uma regra explícita e congelados.

**Pagamentos**

`_build_payment_payload(...)` consulta apenas o primeiro `workorder.payments.order_by("id").first()`. Daquele registro usa o número de parcelas para definir:

- `pagamento=1` quando há mais de uma parcela;
- `pagamento=0` nos demais casos.

Também fixa `presenca=2`; a modalidade de frete começa em 9 e depois pode ser substituída pelo bloco de transporte. Método e valores das parcelas não são serializados nessa função.

**Veículo**

O veículo do orçamento é exibido no Step 2, mas não é usado automaticamente no payload NF-e. A placa/UF de transporte são campos independentes do `transport_snapshot`.

**Observações**

`additional_information` vem do form e do próprio `NfeRequest`, não da OS. A natureza da operação normal vem de setting (`WEBMANIA_NFE_NATUREZA_OPERACAO`, com fallback “Venda de mercadoria”).

**Estoque**

Não há leitura de `StockProduct`, validação de saldo nem criação de `StockMovement` no builder, preview, emissão ou sincronização da NF-e.

### 5.5 Dependência real de estoque

O builder normal exige um `catalog.Product` válido associado ao item operacional, incluindo dados fiscais como código, NCM, unidade, origem/CST e, quando aplicável, CEST. Ele não consulta `StockProduct.current_quantity` e não cria `StockMovement`.

Logo:

- a NF-e normal é dependente de **produto fiscal/catálogo**, não de saldo de estoque;
- a dependência de estoque pode existir antes, no fluxo operacional que formou a OS;
- emitir sem estoque é conceitualmente possível, mas o fluxo atual não oferece uma origem manual de itens;
- ligar emissão fiscal diretamente à baixa/entrada de estoque sem regra explícita criaria efeitos colaterais novos.

---

## 6. Mapa dos models fiscais

### 6.1 `NfeRequest`

Arquivo: `apps/finance/models/finance.py`.

Campos e relações relevantes:

| Campo | Tipo/obrigatoriedade | Default | Dependência |
|---|---|---|---|
| `workshop` | FK obrigatória, `CASCADE` | sem default | independente da OS; owner do escopo |
| `workorder` | FK obrigatória, `CASCADE` | sem default | dependência estrutural da OS |
| `current_step` | inteiro positivo obrigatório | `1` | legado do wizard de `NfeRequest` |
| `status` | `CharField(20)` obrigatório | `waiting_wo` | estado da requisição |
| `pricing_slider` | small integer anulável, -100..100 | `NULL` | inicializado da OS/orçamento |
| `discount_type_override` | choice opcional | `""` | independente como campo; fallback usa tipo da OS |
| `additional_information` | texto | `""` | independente |
| `tax_class` | `CharField(30)` | `REF000000` | independente; validado local/remotamente |
| `freight_mode` | inteiro/choice obrigatório | `NO_TRANSPORT` (9) | independente |
| `transport_snapshot` | JSON | `{}` | independente |
| `reserved_number` | inteiro positivo anulável | `NULL` | independente; reserva fiscal |
| `reserved_series` | inteiro positivo anulável | `NULL` | independente; reserva fiscal |
| `invalidation_reason` | texto | `""` | independente |
| `invalidation_xml_url` | URL | `""` | independente |
| `invalidation_log_payload` | JSON | `{}` | independente |
| `invalidated_at` | datetime anulável | `NULL` | independente |
| `criado_em`/`atualizado_em` | herdados de `TimeStampedModel` | automáticos | independente |

O `save()` inicializa o slider a partir do orçamento da OS. A propriedade `customer_name` também navega por `workorder.budget.customer`.

Propriedades/métodos calculados:

- `set_status(...)`: persiste status;
- `customer_name`: lê o cliente da OS;
- `nfe_request_status_badge`: transforma status em texto/classe visual;
- `update_status_based_on_request(...)`: normaliza resposta Webmania para processing/approved/reproved/canceled/denied/contingency;
- `number_display`: prefere número reservado e depois o primeiro `NfeItem`;
- `__str__`: inclui explicitamente a OS.

Status possíveis:

- `waiting_wo`;
- `checking_client`;
- `checking_products`;
- `processing`;
- `approved`;
- `reproved`;
- `denied`;
- `canceled`;
- `contingency`;
- `invalidated`.

Separação para a futura origem:

| Grupo | Campos |
|---|---|
| Independentes e reutilizáveis | `workshop`, status, classe, informação adicional, frete, transporte, reserva, inutilização, timestamps |
| Dependentes diretamente | `workorder` |
| Dependentes indiretamente | inicialização de `pricing_slider`, fallback de desconto, `customer_name`, `__str__`, builder e sincronização |
| Ausentes e necessários | tipo de origem, snapshot de destinatário, snapshot de linhas, snapshot de pagamento/valores e identidade manual |

#### Campos dependentes da OS

- `workorder`;
- valor inicial de `pricing_slider`;
- semântica de `discount_type_override`, cujo vazio usa a OS;
- `customer_name`;
- identificação textual em `__str__`;
- todos os dados acessados pelo builder por `nfe_request.workorder`;
- identidade usada por `sync_nfe_emission_response()` e pela constraint de `NfeItem`.

#### Campos independentes da OS

- `workshop`;
- `current_step` e `status`, embora seus nomes/estados ainda reflitam o workflow legado;
- `additional_information`;
- `tax_class`;
- `freight_mode` e `transport_snapshot`;
- número e série reservados;
- motivo, XML, log e timestamp de inutilização;
- timestamps herdados.

Não existem hoje:

- tipo explícito de origem (`workorder`/`manual`);
- destinatário próprio ou snapshot de destinatário;
- coleção própria de linhas fiscais manuais;
- forma de pagamento independente;
- totais independentes;
- vínculo opcional com cliente/fornecedor apenas como fonte de preenchimento.

### 6.2 `NfeItem`

É o registro operacional do resultado de emissão normal. Contém, entre outros:

- oficina e OS obrigatórias;
- vínculo opcional à `NfeRequest`;
- UUID, status, modelo, motivo;
- número, série, recibo e chave de acesso;
- URLs/artefatos XML e DANFE;
- payloads/logs e dados de reconciliação.

Há unicidade por `(workorder, uuid)`. Essa restrição e o FK obrigatório também impedem representar de forma direta uma NF-e normal manual sem OS.

### 6.3 `FiscalDocument`

É a representação normalizada para histórico fiscal, eventos e documentos derivados:

- oficina/conta;
- tipo, origem e finalidade;
- vínculo 1:1 opcional com `NfeItem` legado;
- identidade remota;
- status;
- request/response payload;
- XML e DANFE.

Uma NF-e normal legada passa a ter `FiscalDocument` quando `ensure_fiscal_document_for_nfe_item(...)` é chamado. Esse comportamento de projeção deve ser preservado enquanto `NfeItem` continuar sendo o resultado primário da emissão normal.

### 6.4 `FiscalDocumentEvent`

Registra eventos sobre um documento:

- tipo do evento;
- sequência e código;
- status e UUID;
- texto de correção, quando aplicável;
- request/response payload;
- XML/DACCE e dados de reconciliação.

É o owner correto de CC-e e eventos fiscais; eles não devem ser modelados como uma nova `NfeRequest`.

### 6.5 `FiscalDocumentLink`

Relaciona documento derivado ao original por papel semântico, por exemplo:

- devolve;
- estorna;
- complementa;
- ajusta.

Esse relacionamento deve continuar sendo a fonte do encadeamento fiscal entre documentos.

### 6.6 `FiscalEmissionAttempt`

Registra a fronteira de idempotência e auditoria:

- oficina;
- tipo de documento e operação;
- model/id da requisição ou documento;
- `FiscalDocument`/evento associado;
- chave de idempotência e hash do payload;
- status remoto;
- UUID/chave remota;
- payload de request e response.

Estados incertos bloqueiam reenvio cego e exigem reconciliação. Qualquer nova entrada deve desembocar nessa mesma proteção.

---

## 7. Fluxo de dados até a Webmania

### 7.1 Emissão NF-e normal

Serviços principais:

- fachada: `get_fiscal_service()`;
- emissão/builder: `apps/core/infrastructure/services/webmania/nfe_emission.py`;
- funções centrais: `emit_nfe_request(...)` e `build_nfe_payload(...)`;
- persistência do resultado: `sync_nfe_emission_response(...)`;
- tentativas: `apps/finance/services/fiscal_attempts.py`.

Fluxo:

1. recebe `NfeRequest`;
2. valida classe tributária e exigências IBS/CBS;
3. reserva número/série;
4. monta o payload com `build_nfe_payload(...)`;
5. congela o payload e abre `FiscalEmissionAttempt`;
6. transmite para o endpoint Webmania;
7. marca tentativa como enviada, concluída, falha ou incerta;
8. sincroniza resposta em `NfeItem`;
9. webhook/reconciliação podem atualizar o resultado sem reemitir.

O builder atual monta:

- cliente a partir da OS/orçamento;
- produtos a partir do snapshot de precificação da OS;
- pagamento a partir da OS;
- desconto e slider;
- finalidade/operação normal;
- informações adicionais;
- frete e transporte.

### 7.2 Preview

`download_nfe_preview_document(...)` usa o mesmo `build_nfe_payload(...)`, com configuração de preview. Não é um builder independente e não deve se tornar um.

### 7.3 Fronteiras que não devem ser alteradas

As próximas fases devem preservar:

- `get_fiscal_service()` como fachada;
- `build_nfe_payload(...)` como builder da NF-e normal;
- reserva de numeração;
- validação tributária;
- `FiscalEmissionAttempt`;
- tratamento de timeout/estado incerto;
- sincronização em `NfeItem`;
- webhook e reconciliação;
- contratos de transporte já incorporados;
- serviços existentes de eventos e documentos derivados.

O ponto de extensão seguro fica **antes** do builder: adaptar uma nova origem para o contrato de dados que o motor atual já consome, sem ramificar a integração remota.

---

## 8. Central de Notas existente

### 8.1 Lista

| Item | Implementação |
|---|---|
| URL | `/finance/notas-emitidas/` |
| Nome | `finance:issued_documents_list` |
| View | `apps/finance/views/issued_documents.py` — `IssuedDocumentsListView` |
| Template | `finance/issued_documents_list.html` |
| Resultado parcial | `finance/partials/issued_documents_results.html` |
| Download em lote | `IssuedDocumentsArchiveDownloadView` |

A lista agrega `NfeRequest` e `NfseRequest`, com filtros por período, tipo e busca. Exibe tipo, número, referência, OS, cliente, data, status, documentos e ação de abrir.

Ela não consulta todos os `FiscalDocument` e `FiscalDocumentEvent`. Portanto, documentos derivados e eventos só aparecem plenamente no detalhe da NF-e de origem, não como operações de primeira classe na lista central.

### 8.2 Detalhe de NF-e

| Item | Implementação |
|---|---|
| URL | `/finance/nfe/<pk>/` |
| View | `NfeRequestDetailView` |
| Template | `finance/nfe_request_detail.html` |

O detalhe é hoje o hub operacional real.

### 8.3 Ações existentes

| Ação | Entrada atual | Serviço/owner | Permissão principal |
|---|---|---|---|
| Editar requisição | detalhe | workflow legado de `NfeRequest` | view/change da requisição |
| Reconciliar NF-e | detalhe | `get_fiscal_service().reconcile_nfe_item(...)` | view da requisição |
| Cancelar NF-e | modal no detalhe | `get_fiscal_service().cancel_nfe(...)` | `nferequest.cancel_nferequest` |
| Inutilizar numeração | modal no detalhe | `get_fiscal_service().invalidate_nfe_number(...)` | `nferequest.invalidate_nferequest_numbering` |
| Baixar XML | detalhe | download fiscal/Webmania | `nferequest.download_nferequest_xml` |
| Baixar DANFE/variações | detalhe | download fiscal/Webmania | `nferequest.download_nferequest_pdf` |
| Ver payload/retorno | detalhe | dados sanitizados persistidos | permissões específicas de payload/response |
| Emitir CC-e | modal no detalhe | `emit_nfe_correction(...)` | `fiscaldocumentevent.issue_nfe_correction` |
| Baixar XML/DACCE CC-e | histórico no detalhe | serviço de documentos de evento | `fiscaldocumentevent.download_nfe_correction` |
| Ver payload CC-e | histórico no detalhe | `FiscalDocumentEvent` | `fiscaldocumentevent.view_nfe_correction_payload` |
| Devolução/estorno | modal no detalhe | `create_and_emit_nfe_return_from_item(...)` | acesso à view de `NfeRequest` (com fallback NFS-e) e checagem adicional de `fiscaldocument.issue_nfe_return` ou `issue_nfe_reversal`, conforme a finalidade |
| Baixar/ver devolução | histórico no detalhe | serviço de devolução | `fiscaldocument.download_nfe_return` / `view_nfe_return_payload` |
| Nota complementar | modal no detalhe | `create_and_emit_nfe_complementary_price_quantity_from_item(...)` | `fiscaldocument.issue_nfe_complementary_price_quantity` |
| Baixar complementar | histórico no detalhe | serviço de complementar | `fiscaldocument.download_nfe_complementary` |
| Nota de ajuste | modal no detalhe | `create_and_emit_nfe_adjustment(...)` | `fiscaldocument.issue_nfe_adjustment` |
| Baixar ajuste | histórico no detalhe | serviço de ajuste | `fiscaldocument.download_nfe_adjustment` |
| Eventos IBS/CBS | modais no detalhe | `nfe_ibs_cbs_events.py` | permissões de cada evento |

Mapa implementável das rotas e classes de NF-e:

| Ação | URL relativa | View em `apps/finance/views/nfe.py` | Chamada principal |
|---|---|---|---|
| Detalhe | `nfe/<pk>/` | `NfeRequestDetailView` | monta contexto/históricos |
| Reconciliar | `nfe/<pk>/reconciliar/` | `NfeRequestReconcileView` | `service.reconcile_nfe_item(item=...)` |
| Inutilizar | `nfe/<pk>/inutilizar/` | `NfeRequestInvalidateView` | `service.invalidate_nfe_number(...)` |
| Cancelar | `nfe/<pk>/cancelar/` | `NfeRequestCancelView` | `service.cancel_nfe(...)` |
| CC-e | `nfe/<pk>/carta-correcao/` | `NfeCorrectionIssueView` | `emit_nfe_correction(...)` |
| Payload CC-e | `nfe/<pk>/carta-correcao/<event_pk>/payload/` | `NfeCorrectionPayloadView` | lê payload sanitizado do evento |
| XML/DACCE CC-e | `nfe/<pk>/carta-correcao/<event_pk>/<document>/` | `NfeCorrectionDownloadView` | download do artefato do evento |
| Devolução/estorno | `nfe/<pk>/devolucao-estorno/` | `NfeReturnIssueView` | `create_and_emit_nfe_return_from_item(...)` |
| Payload devolução | `nfe/<pk>/devolucao-estorno/<document_pk>/payload/` | `NfeReturnPayloadView` | lê payload do documento derivado |
| Documento devolução | `nfe/<pk>/devolucao-estorno/<document_pk>/<document>/` | `NfeReturnDownloadView` | download XML/DANFE |
| Complementar | `nfe/<pk>/complementar/preco-quantidade/` | `NfeComplementaryPriceQuantityIssueView` | `create_and_emit_nfe_complementary_price_quantity_from_item(...)` |
| Documento complementar | `nfe/<pk>/complementar/<document_pk>/<document>/` | `NfeComplementaryDownloadView` | download XML/DANFE |
| Ajuste | `nfe/<pk>/ajuste/` | `NfeAdjustmentIssueView` | `validate_adjustment_tax_regime(...)` + `create_and_emit_nfe_adjustment(...)` |
| Documento de ajuste | `nfe/<pk>/ajuste/<document_pk>/<document>/` | `NfeAdjustmentDownloadView` | download XML/DANFE |
| XML/DANFE normal | `nfe/<pk>/documentos/<document>/` | `NfeDocumentDownloadView` | `service.download_document(...)` |
| Prévia normal | `nfe/<pk>/previa/pdf/` | `NfePreviewPdfView` | `service.download_nfe_preview_document(...)` |

Permissões e fallbacks observados:

| Capacidade | Permissão específica | Fallback/observação |
|---|---|---|
| Cancelar | `finance.cancel_nferequest` | `change_nferequest` e `change_nfserequest` |
| Inutilizar | `finance.invalidate_nferequest_numbering` | `change_nferequest` e `change_nfserequest` |
| XML normal | `finance.download_nferequest_xml` | controlada no contexto/detalhe |
| PDF normal | `finance.download_nferequest_pdf` | controlada no contexto/detalhe |
| Payload normal | `finance.view_nferequest_payload` | separado de resposta remota |
| Resposta remota | `finance.view_nferequest_remote_response` | separado de payload |
| Emitir CC-e | `finance.issue_nfe_correction` em `FiscalDocumentEvent` | sem novo motor |
| Download CC-e | `finance.download_nfe_correction` | XML/DACCE |
| Payload CC-e | `finance.view_nfe_correction_payload` | payload do evento |
| Emitir devolução | `finance.issue_nfe_return` | a view também exige acesso à requisição |
| Emitir estorno | `finance.issue_nfe_reversal` | verificação escolhida por `purpose` |
| Download devolução/estorno | `finance.download_nfe_return` | `FiscalDocument` |
| Payload devolução/estorno | `finance.view_nfe_return_payload` | `FiscalDocument` |
| Emitir complementar | `finance.issue_nfe_complementary_price_quantity` | `FiscalDocument` |
| Download complementar | `finance.download_nfe_complementary` | `FiscalDocument` |
| Payload complementar | `finance.view_nfe_complementary_payload` | permissão existe no model; a superfície atual é centrada no detalhe |
| Emitir ajuste | `finance.issue_nfe_adjustment` | `FiscalDocument` |
| Download ajuste | `finance.download_nfe_adjustment` | `FiscalDocument` |
| Payload ajuste | `finance.view_nfe_adjustment_payload` | permissão existe no model; a superfície atual é centrada no detalhe |

O novo seletor de referências deve aplicar duas autorizações: acesso à operação e acesso ao documento da oficina. Não basta esconder botões no template.

### 8.4 Cancelamento versus inutilização

São operações fiscalmente diferentes e a UI futura deve preservar essa distinção:

- **cancelar** atua sobre NF-e autorizada;
- **inutilizar** atua sobre número/série reservado que não será usado.

O código atual impede inutilizar uma nota aprovada/cancelada e só oferece a operação quando não há item transmitido válido ou quando o resultado permite inutilização. “Inutilizar Nota Fiscal” não deve ser apresentado como alternativa para alterar o status de uma NF-e autorizada.

---

## 9. Operações fiscais existentes

### 9.1 Carta de Correção — CC-e

**Como inicia hoje:** no detalhe de uma `NfeRequest`.

**Pré-condição:** `NfeItem` autorizado/elegível com chave de acesso ou UUID. Depende de uma NF-e existente; não depende da OS para sua regra fiscal depois que o documento foi identificado.

**Arquitetura:**

```text
NfeItem autorizado
    ↓ ensure_fiscal_document_for_nfe_item(...)
FiscalDocument
    ↓
FiscalDocumentEvent (CC-e, sequência)
    ↓
FiscalEmissionAttempt
    ↓
Webmania
```

Serviço: `apps/finance/services/nfe_events.py`.

Capacidades existentes:

- validação do texto e confirmação legal;
- bloqueio de evento ativo;
- sequência;
- UUID;
- idempotência;
- timeout incerto;
- webhook;
- reconciliação;
- XML e DACCE;
- payload/histórico.

**Evolução recomendada:** o seletor da Central deve pedir a NF-e de referência e então redirecionar para a mesma view/modal ou chamar a mesma camada de aplicação. Não criar outro emissor de CC-e.

### 9.2 Devolução/estorno

**Como inicia hoje:** modal no detalhe da NF-e original, por `NfeReturnIssueView` e `NfeReturnForm`.

**Documento origem:** `NfeItem` autorizado, projetado como `FiscalDocument`. O serviço também suporta uma NF-e externa normalizada com confirmação explícita, mas não foi localizada uma tela conectada para iniciar por documento externo.

**Serviço:** `apps/finance/services/nfe_returns.py`.

**Arquitetura:**

```text
FiscalDocument original
    ↓
FiscalDocument derivado (devolução/estorno)
    + FiscalDocumentLink
    + snapshot de itens/saldo
    ↓
FiscalEmissionAttempt
    ↓
Webmania
```

Capacidades existentes:

- devolução total;
- devolução parcial;
- validação de saldo;
- snapshots;
- prevenção de duplicidade;
- estado incerto;
- webhook;
- reconciliação;
- downloads e payload.

**Dependência de OS:** a entrada visual atual começa em uma NF-e que veio de `NfeRequest`/OS. O motor de devolução opera sobre o documento fiscal original e seus snapshots, não sobre a OS.

**Dependência de estoque:** não há integração com `StockProduct`, `StockImport` ou `StockMovement`. Os itens elegíveis vêm do payload/snapshot da NF-e original.

Se a Central permitir “selecionar produto de entrada do estoque”, isso será uma nova fonte auxiliar de seleção. A referência de estoque deve ser convertida para os itens do documento original e ainda passar pelas validações fiscais de sequência, quantidade e saldo. Ela não pode substituir o snapshot fiscal original nem criar movimentação automática sem uma regra de negócio separada.

### 9.3 Transporte

**Como inicia hoje:** dentro da etapa `nfe_config` do wizard normal.

**Campos principais:**

- `freight_mode`;
- transportador;
- veículo;
- volumes;
- reboques;
- demais dados congelados em `transport_snapshot`.

**Fluxo:** o form valida e normaliza, `NfeRequest` persiste, o attempt congela e o mesmo `build_nfe_payload(...)` incorpora o bloco de transporte.

Transporte não é uma emissão paralela e não representa CT-e ou MDF-e. Na Central, “Transporte” deve:

- abrir a emissão NF-e normal;
- pré-selecionar/exibir a seção de transporte;
- manter o mesmo `NfeRequest`, builder, preview e attempt.

### 9.4 Nota complementar

Está implementada para complemento de preço e/ou quantidade.

**Entrada atual:** modal no detalhe da NF-e original.

**Form/view:**

- `NfeComplementaryPriceQuantityForm`;
- `NfeComplementaryPriceQuantityIssueView`.

**Serviço:** `apps/finance/services/nfe_complementary.py`.

**Fluxo:**

- valida NF-e original elegível;
- extrai itens do payload original;
- cria `FiscalDocument` derivado;
- cria `FiscalDocumentLink` com papel `COMPLEMENTS`;
- abre `FiscalEmissionAttempt`;
- transmite, consulta, reconcilia e recebe webhook.

A UI atual recebe os itens complementares em JSON. Isso é funcional, mas não é a experiência final desejável.

### 9.5 Nota de ajuste

Está implementada.

**Entrada atual:** modal no detalhe de uma NF-e, embora o motor aceite documento manual e o vínculo de referência seja opcional.

**Form/view:**

- `NfeAdjustmentForm`;
- `NfeAdjustmentIssueView`.

**Serviço:** `apps/finance/services/nfe_adjustment.py`.

**Fluxo:**

- valida regime tributário elegível;
- valida escopo restrito de ajuste;
- cria `FiscalDocument` com origem manual e finalidade de ajuste;
- opcionalmente cria `FiscalDocumentLink` com papel `ADJUSTS`;
- abre `FiscalEmissionAttempt`;
- transmite, consulta, reconcilia e recebe webhook.

O próprio fluxo deixa explícito que ajuste não representa entrada/saída de produtos e não substitui devolução/estorno.

### 9.6 Contratos atuais das operações

| Operação | Form/entradas atuais | Entidade gravada | Vínculo com original | Attempt |
|---|---|---|---|---|
| CC-e | `NfeCorrectionForm`: correção 15..1000 caracteres + confirmação legal | `FiscalDocumentEvent` | FK `document` | ligado ao evento |
| Devolução/estorno | `NfeReturnForm`: finalidade, total/parcial, natureza, CFOP, classe, produtos JSON, volume e informações | `FiscalDocument` derivado | `FiscalDocumentLink` com papel de devolução/estorno | ligado ao documento derivado |
| Complementar | `NfeComplementaryPriceQuantityForm`: operação, natureza, CFOP, itens JSON e confirmação | `FiscalDocument` derivado, tipo preço/quantidade | `FiscalDocumentLink.COMPLEMENTS` | ligado ao documento derivado |
| Ajuste | `NfeAdjustmentForm`: entrada/saída, natureza, CFOP, ICMS/ICMS-ST, situação tributária, cliente JSON, informações e confirmações | `FiscalDocument` manual/ajuste | `FiscalDocumentLink.ADJUSTS` opcional | ligado ao documento |
| Transporte | campos adicionados ao `EmissionNfeConfigForm` | `NfeRequest.transport_snapshot` | não é documento derivado | congelado no attempt normal |

Pontos de extensão:

- views novas podem reutilizar os forms atuais ou extrair sua apresentação, mas devem continuar chamando os mesmos services;
- a seleção amigável de itens pode substituir a digitação JSON na UI, desde que produza exatamente a estrutura validada pelos services existentes;
- a Central não deve criar `NfeRequest` para representar CC-e/devolução/complementar/ajuste;
- o estado `uncertain` continua exigindo consulta/reconciliação, nunca nova emissão automática.

---

## 10. Cadastros rápidos reutilizáveis

Foram encontrados padrões existentes:

### 10.1 Pessoa/cliente

- URL `customer:quick_create`;
- `QuickCustomerCreateView`;
- já usado no fluxo de orçamento;
- escopo por oficina e resposta compatível com modal/evento.

Esse padrão pode ser reutilizado ou generalizado para preencher o destinatário da emissão manual.

### 10.2 Produtos e serviços

No orçamento:

- `budget:quick_create_item`;
- `QuickCreateProductView`;
- `budget/partials/modals/modal_quick_create.html`.

No estoque:

- `stock:product_quick_create`;
- `stock:supplier_quick_create`;
- modais HTMX correspondentes.

Os endpoints de itens do orçamento dependem de `budget_id`; o cadastro de produto do estoque pode depender de `StockImport`. Eles não devem ser ligados diretamente ao wizard manual por meio de uma OS/orçamento/importação fictícia.

O caminho seguro é reutilizar:

- forms e regras de validação existentes;
- componentes/modal e eventos HTMX;
- serviços de criação do cadastro;
- escopo de oficina e permissões.

Se necessário, deve-se extrair uma entrada rápida neutra de contexto, mantendo os endpoints antigos para compatibilidade.

### 10.3 Cadastro versus snapshot fiscal

O destinatário e os itens usados na transmissão precisam ser congelados. Um vínculo com `Customer`, `Supplier`, `Product` ou `Service` deve funcionar como fonte de preenchimento, não como única fonte histórica.

Uma emissão manual segura deve admitir:

- selecionar cadastro existente;
- criar cadastro rápido;
- opcionalmente informar destinatário eventual conforme a decisão funcional;
- congelar o snapshot usado no payload;
- não mudar uma nota já preparada porque o cadastro mestre foi editado depois.

---

## 11. Avaliação do primeiro passo “Tipo de operação”

A proposta é compatível com a arquitetura existente se o novo primeiro passo for um **roteador**, não um wizard fiscal monolítico.

| Opção | Reaproveitamento recomendado | Natureza da mudança |
|---|---|---|
| NF-e normal com OS | Redirecionar para o wizard atual, preservado | Somente roteamento |
| NF-e normal manual | Nova entrada de origem/destinatário/itens; convergir ao motor normal | Extensão controlada |
| NF-e devolução | Selecionar documento original e abrir fluxo existente | Roteamento + nova seleção |
| Carta de correção | Selecionar NF-e elegível e abrir fluxo existente | Roteamento + nova seleção |
| Complementar | Selecionar NF-e e abrir o serviço/modal existente | Roteamento; futura melhoria de UI dos itens |
| Ajuste | Abrir formulário próprio reutilizando serviço existente; referência opcional | Nova entrada fina |
| Transporte | Abrir NF-e normal com transporte ativado/destacado | Roteamento/preenchimento |

Sugestão de desenho:

```text
/finance/emissao/
    ↓
Selecionar operação
    ├── Normal com OS ─────────────→ wizard atual
    ├── Normal manual ─────────────→ nova origem → mesmo motor NF-e
    ├── Devolução ─────────────────→ selecionar referência → serviço existente
    ├── Carta de correção ─────────→ selecionar referência → evento existente
    ├── Complementar ──────────────→ selecionar referência → serviço existente
    ├── Ajuste ────────────────────→ formulário fino → serviço existente
    └── Transporte ────────────────→ wizard normal/nfe_config
```

O detalhe da NF-e deve continuar exibindo os mesmos comandos como **atalhos contextuais**. Centralizar as entradas não exige remover as ações onde elas já são úteis.

### 11.1 Roteamento exato por opção

| Opção visual | Pré-condição solicitada pela nova entrada | Fluxo que deve ser chamado | O que não deve ser duplicado |
|---|---|---|---|
| NF-e Normal | escolher origem OS ou manual | OS: `EmissionRequestCreateView`; manual: novo preparador que converge antes de `build_nfe_payload()` | builder, preview, reserva, attempt, HTTP e sync |
| NF-e Devolução | escolher NF-e original elegível e total/parcial | `NfeReturnIssueView`/`NfeReturnForm` ou uma view fina chamando `create_and_emit_nfe_return_from_item(...)` | saldo, snapshots, links, attempt, webhook |
| Carta de Correção | escolher NF-e autorizada elegível | redirecionar ao detalhe/modal ou reutilizar `NfeCorrectionForm` + `emit_nfe_correction(...)` | sequência, evento ativo, UUID, attempt, DACCE |
| Complementar | escolher NF-e local autorizada | `NfeComplementaryPriceQuantityIssueView` + serviço atual | extração do original, link, IBS/CBS, attempt |
| Ajuste | informar cliente/tributação e referência opcional | view própria fina sobre `NfeAdjustmentForm` + `create_and_emit_nfe_adjustment(...)` | validação de regime/escopo, document, attempt |
| Transporte | escolher NF-e normal e origem | abrir o fluxo normal com intenção de destacar `nfe_config` | `NfeRequest`, snapshot, validações e `_apply_transport_to_nfe_payload()` |

Para operações referenciadas, o novo fluxo deve selecionar por `NfeRequest`/`NfeItem` ou `FiscalDocument`, mas revalidar no servidor:

- oficina;
- status autorizado/elegível;
- chave/UUID;
- evento/documento ativo;
- saldo, quando devolução;
- permissão específica.

O PK recebido na URL nunca é prova suficiente de elegibilidade.

### 11.2 Estado da sessão por operação

Não se recomenda compartilhar `finance.emission_wizard:{workshop}:{user}` com seletores de CC-e/devolução. O estado atual contém chaves próprias de NF-e/NFS-e normal:

- `workorder_id`;
- `pricing_slider`;
- `discount_type_override`;
- `note_mode`;
- `nfe_config`/`nfse_config`;
- IDs das requisições;
- flags `nfe_done`/`nfse_done`.

Cada nova entrada deve ser curta/stateless quando possível. Se precisar de múltiplos passos, deve usar namespace próprio por oficina, usuário e operação, evitando que abrir uma CC-e apague uma emissão normal em andamento.

---

## 12. Emissão sem OS

### 12.1 O cenário é suportado hoje?

Não.

O cenário “Empresa X, Elevador, quantidade 1, sem OS, orçamento e estoque” falha antes do motor remoto porque não há:

- origem manual no `NfeRequest`;
- destinatário próprio;
- linhas fiscais próprias;
- totais/pagamentos independentes;
- alternativa às leituras de `workorder.budget`;
- forma de persistir o resultado normal em `NfeItem` sem `workorder`;
- unicidade/idempotência operacional preparada para uma origem manual.

### 12.2 Pontos a desacoplar

Os acoplamentos mínimos estão em:

1. seleção e estado do wizard;
2. `NfeRequest.workorder`;
3. `NfeRequest.save()` e propriedades derivadas;
4. builder de cliente;
5. snapshot de produtos/precificação;
6. pagamento e desconto;
7. preview;
8. sincronização em `NfeItem`;
9. buscas, lista central e detalhe;
10. constraints e escopo de `NfeItem`;
11. testes de idempotência, oficina e regressão.

### 12.3 Menor alteração segura

A menor mudança segura não é simplesmente tornar a OS opcional. É introduzir uma origem explícita e um contrato normalizado de entrada:

```text
NfeRequest
    origin = workorder | manual

Origem OS
    → adaptador atual
    → recipient snapshot
    → line snapshots
    → payment/totals snapshot

Origem manual
    → novos forms de entrada
    → os mesmos snapshots normalizados

Snapshots normalizados
    → mesmo build_nfe_payload(...)
    → mesmo FiscalEmissionAttempt
    → mesma Webmania
```

Características necessárias:

- origem explícita com validação exclusiva;
- `workorder` preservado e obrigatório quando `origin=workorder`;
- destinatário congelado, com vínculo mestre opcional;
- linhas fiscais congeladas, com vínculo opcional a catálogo/estoque;
- pagamento, descontos e totais independentes da OS;
- mesmo builder, preferencialmente recebendo uma interface/adaptador de origem;
- mesma reserva, preview, attempt, transmissão e reconciliação;
- estratégia compatível para `NfeItem` sem OS ou projeção normalizada sem quebrar os registros existentes;
- feature flag/permissão separada para implantação gradual.

Não se deve criar OS ou orçamento artificial apenas para satisfazer FKs. Isso esconderia a nova origem e contaminaria regras operacionais, estoque, financeiro e relatórios.

### 12.4 Mudanças obrigatórias, opcionais e riscos

| Tema | Mudança obrigatória | Mudança opcional | Risco principal |
|---|---|---|---|
| Origem | discriminator `workorder/manual` e regra de consistência | outras origens futuras | registros híbridos sem fonte confiável |
| OS | permitir ausência somente em origem manual | vínculo de referência operacional opcional | quebrar cascatas, relatórios e propriedades |
| Destinatário | snapshot fiscal completo | FK opcional para `Customer` ou `Supplier` | cadastro alterado depois mudar intenção |
| Produtos | linhas fiscais congeladas com código/NCM/unidade/origem/quantidade/valores | FK opcional a `Product`, seleção de estoque | linha sem dados fiscais ou mutável |
| Serviços | manter fluxo NFS-e separado | futura central unificada de NFS-e manual | enviar serviço indevidamente na NF-e |
| Valores | totais/desconto/pagamento independentes | política de slider manual | diferença entre soma das linhas e pedido |
| Builder | aceitar/resolver fonte normalizada mantendo o mesmo output | DTO tipado/adaptadores | mudança de payload produtivo da OS |
| Preview | mesma função e endpoint remoto | preview local anterior | divergência preview/transmissão |
| Attempt | continuar obrigatório | chave mais legível por origem | duplicidade após timeout |
| Resultado | suportar identidade de `NfeItem` sem OS ou normalizar persistência | criação antecipada de `FiscalDocument` | webhook sem encontrar destino |
| Central | adapter de linha OS/manual | timeline completa | erros ao navegar `workorder.budget` nulo |
| Cadastro rápido | entrada neutra de contexto para produto/serviço; cliente existente pode ser reutilizado | cadastro eventual sem mestre | criar Budget/StockImport fictício |
| Estoque | nenhuma dependência obrigatória | busca somente leitura e movimentação em fase separada | efeito colateral de saldo |

### 12.5 Contrato mínimo de snapshots manuais

Sem definir o schema final nesta fase, o motor precisará receber equivalentes aos dados já usados:

```text
recipient_snapshot
    person_type
    cpf/cnpj
    name/company_name
    state_registration
    address, number, district, city, state, postal_code
    complement, phone, email

line_snapshots[]
    description
    code
    ncm
    cest
    unit
    origin
    quantity
    unit_value
    total_value
    tax_class/reference

payment_snapshot
    indicator/installments
    presence
    discount
    total

transport_snapshot
    contrato atual, sem alteração
```

Os nomes do payload Webmania não devem necessariamente virar campos de banco. O snapshot interno pode ser um DTO/model próprio e continuar sendo convertido pelo builder atual.

### 12.6 Cadastros rápidos: o que é realmente reutilizável

**Cliente**

`QuickCustomerCreateView` + `QuickCustomerForm` já são oficina-scoped, persistem `Customer` e retornam `HX-Trigger` por `build_customer_saved_trigger(...)`. Essa é a entrada mais diretamente reutilizável.

**Produto/serviço**

`budget:quick_create_item` usa `QuickCreateProductView`, mas exige `budget_id`, permissão `add_budget`, lock do orçamento e, no contexto principal, cria também `BudgetItem`. O form `QuickProductForm`/`QuickServiceForm` e o padrão do modal podem ser reaproveitados; o endpoint não deve ser chamado com orçamento fictício.

**Estoque**

`stock:product_quick_create` é contextual a `StockImport` em parte de seu fluxo. Serve como padrão de UI/validação, não como entrada fiscal neutra pronta.

Para a emissão manual, a extensão segura é um endpoint de catálogo neutro, oficina-scoped, reutilizando os mesmos forms/regras e emitindo evento HTMX específico. Criar esse endpoint é obrigatório somente se o usuário precisar persistir o novo cadastro; informar um snapshot eventual pode ser uma opção funcional separada.

---

## 13. Riscos

### 13.1 Riscos críticos

1. **Duplicação de motor:** um builder manual separado divergiria em impostos, IBS/CBS, transporte, idempotência e correções futuras.
2. **Nullable incompleto:** liberar apenas o FK da OS produziria exceções em cadeia e notas sem histórico coerente.
3. **Dupla transmissão:** qualquer caminho que contorne `FiscalEmissionAttempt` pode reenviar após timeout.
4. **Quebra de isolamento:** seletores de documentos, pessoas ou produtos sem filtro de oficina permitem vazamento entre oficinas.
5. **Snapshot mutável:** montar payload diretamente do cadastro mestre pode alterar uma intenção fiscal já conferida.
6. **Mistura fiscal/estoque:** emissão ou devolução não devem movimentar estoque implicitamente sem regra transacional e auditável.
7. **Semântica de inutilização:** tratar inutilização como mudança livre de status de nota autorizada é incorreto.
8. **Central incompleta:** listar somente `NfeRequest`/`NfseRequest` não cobre documentos manuais/derivados.
9. **Permissões legadas:** reutilizar indefinidamente `view_nfserequest` para toda operação reduz a granularidade.
10. **Remoção precoce do legado:** update, detalhe, links e relatórios ainda dependem das estruturas atuais.

### 13.2 Riscos de UX

- colocar todas as operações em um único wizard aumentaria ramificações e estados inválidos;
- “Transporte” pode ser interpretado como CT-e/MDF-e;
- “Produto de entrada do estoque” pode ser confundido com o item fiscal original da devolução;
- cadastros rápidos contextuais podem criar orçamento/importação artificial;
- complementar por JSON é tecnicamente funcional, mas suscetível a erro humano.

---

## 14. Recomendação incremental

O plano abaixo evita juntar roteamento, mudança de persistência e emissão manual na mesma entrega.

### Fase A — Congelar contratos de regressão

**Objetivo**

Caracterizar o payload e o comportamento do fluxo OS antes de mudar qualquer estrutura.

**Arquivos envolvidos**

- existentes: `apps/finance/views/emission.py`, `apps/finance/forms/emission.py`;
- existentes: `apps/core/infrastructure/services/webmania/nfe_emission.py`;
- testes candidatos: novo `apps/finance/test_emission_wizard.py` e/ou ampliação de testes fiscais focados.

**Impacto:** nenhum comportamento novo.

**Risco:** baixo; risco de mocks frágeis se os testes compararem detalhes irrelevantes.

**Testes necessários**

- sequência e acesso aos steps;
- filtro da OS por oficina/status;
- payload golden master da emissão com OS;
- preview e emissão usando o mesmo builder;
- attempt criado uma única vez;
- timeout permanece `uncertain`;
- `sync_nfe_emission_response()` continua criando `NfeItem`;
- modo `both` não reemite NF-e após sucesso parcial.

**Critério de saída:** payload normal atual capturado por testes sem alteração.

### Fase B — Gateway/Central como roteador

**Objetivo**

Adicionar a escolha visual de operação sem alterar `EmissionRequestCreateView`.

**Arquivos envolvidos**

- `apps/finance/urls.py`;
- `apps/finance/views/emission.py` ou nova view de apresentação em `apps/finance/views/`;
- novo template de seleção em `apps/finance/templates/finance/`;
- `apps/core/presentation/navigation.py`;
- redirects `NfeCreateRedirectView`/`NfseCreateRedirectView`.

**Impacto**

- menu abre a Central;
- fluxo normal passa a ter rota interna explícita;
- links antigos com `tipo=` continuam redirecionando para o wizard atual.

**Risco:** médio, concentrado em compatibilidade de URL, reset de sessão e favoritos.

**Testes necessários**

- menu/`reverse("finance:emission_create")`;
- links legados `nfe_create`/`nfse_create`;
- `?tipo=nfe|nfse|both&reset=1`;
- acesso sem permissão;
- nenhum reset indevido da sessão ao apenas abrir a Central;
- rota normal ainda renderiza os mesmos steps/templates.

**Critério de saída:** NF-e/NFS-e com OS continuam idênticas, com a Central apenas roteando.

### Fase C — Seletor comum de documento fiscal

**Objetivo**

Permitir escolher uma NF-e elegível para CC-e, devolução e complementar.

**Arquivos envolvidos**

- nova view/form de seleção em `apps/finance/views/` e `apps/finance/forms/`;
- `apps/finance/urls.py`;
- novo template/partial;
- somente chamadas/reuso de `apps/finance/views/nfe.py`;
- serviços existentes `nfe_events.py`, `nfe_returns.py`, `nfe_complementary.py`.

**Impacto:** novas portas de entrada; detalhe atual permanece.

**Risco:** médio/alto por autorização e seleção cross-workshop.

**Testes necessários**

- queryset limitado à oficina;
- filtro por status/elegibilidade para cada operação;
- chave/UUID obrigatórios;
- usuário com acesso à Central mas sem permissão específica;
- PK de outra oficina retorna 404/nega;
- redirect preserva o documento correto;
- serviço atual é chamado uma vez;
- nenhum novo payload/builder aparece.

**Critério de saída:** operação iniciada pela Central produz o mesmo resultado da iniciada pelo detalhe.

### Fase D — Ajuste independente e atalho de transporte

**Objetivo**

Expor operações que não precisam do seletor da mesma maneira.

**Arquivos envolvidos**

- form/view/template fino de ajuste;
- reuso de `NfeAdjustmentForm` ou extração sem alterar sua validação;
- `apps/finance/services/nfe_adjustment.py`;
- parâmetros/intenção da rota normal para transporte;
- forms existentes `apps/finance/forms/nfe_transport.py`.

**Impacto**

- ajuste pode começar sem uma `NfeRequest` apenas para hospedar o modal;
- transporte abre o mesmo wizard normal e destaca sua seção.

**Risco:** médio; principalmente regime tributário, referência opcional e interpretação de transporte.

**Testes necessários**

- regime tributário inelegível;
- confirmações legais obrigatórias;
- documento relacionado de outra oficina;
- ajuste sem referência usa o mesmo `FiscalEmissionAttempt`;
- transporte não cria operação/documento paralelo;
- modalidade 9 e snapshots continuam validados;
- payload de transporte permanece idêntico.

### Fase E — Contrato normalizado de origem, ainda somente OS

**Objetivo**

Introduzir DTO/adaptador interno e fazer a origem OS produzir snapshots normalizados, sem habilitar manual.

**Arquivos envolvidos**

- candidato em `apps/finance/application/` ou serviço próximo ao owner atual;
- `apps/core/infrastructure/services/webmania/nfe_emission.py`;
- `apps/finance/services/pricing.py`;
- models ainda sem mudança funcional, se possível;
- testes golden master da Fase A.

**Impacto:** refatoração interna controlada; UI e banco permanecem iguais.

**Risco:** alto, pois toca a montagem do payload produtivo.

**Testes necessários**

- igualdade estrutural integral entre payload anterior e novo para PF/PJ;
- produtos simples, kits, overrides e item fornecido pelo cliente;
- desconto products/services/both;
- slider extremos e intermediários;
- pagamento sem registro, uma parcela e múltiplas;
- transporte completo;
- classes e IBS/CBS;
- preview e emissão;
- logs não podem acessar `workorder` quando a fonte já estiver normalizada.

**Critério de saída:** origem OS passa por adaptador sem diferença no payload enviado.

### Fase F — Persistência da origem manual

**Objetivo**

Criar suporte de banco seguro para uma intenção normal sem OS, ainda atrás de feature flag e sem necessariamente expor transmissão.

**Arquivos envolvidos**

- `apps/finance/models/finance.py`;
- nova migration;
- possível model de linhas/snapshots ou JSON validado;
- `NfeRequest`, `NfeItem`, constraints e métodos calculados;
- admin/serializações internas, se existentes;
- Central/listas/detalhe que acessam `workorder`.

**Impacto:** schema e caminhos de leitura.

**Risco:** alto/crítico por constraints, cascatas, webhooks e dados legados.

**Testes necessários**

- todos os registros antigos assumem `origin=workorder`;
- constraint exige OS na origem OS;
- constraint proíbe ou controla OS na origem manual;
- snapshots obrigatórios na origem manual;
- `customer_name`, `number_display`, `__str__` e badges sem OS;
- identidade única de `NfeItem` por oficina/request/UUID;
- webhook e reconciliação encontram item manual;
- exclusão de OS antiga preserva comportamento histórico previsto;
- migrations forward/backward em dados representativos.

**Critério de saída:** rascunho manual pode ser persistido e consultado sem quebrar registros OS.

### Fase G — Wizard de NF-e normal manual

**Objetivo**

Permitir destinatário, produtos e valores sem OS/orçamento/estoque.

**Arquivos envolvidos**

- novas views/forms/templates de origem manual;
- endpoints de busca/cadastro rápido;
- `QuickCustomerForm`;
- `QuickProductForm` e padrões de `QuickServiceForm`, sem dependência de Budget;
- contrato/adaptador da Fase E;
- mesmos `build_nfe_payload()`, preview, reserva, attempt, Webmania e sync.

**Impacto:** nova capacidade fiscal produtiva.

**Risco:** alto/crítico.

**Testes necessários**

- PF, PJ, IE/ISENTO e endereço obrigatório;
- pessoa existente e cadastro rápido;
- produto existente e cadastro rápido;
- produto sem NCM/código;
- emissão sem `StockProduct`;
- quantidade/preço/total/desconto;
- snapshot imutável após editar Customer/Product;
- preview igual à transmissão;
- duplo clique, request concorrente e timeout;
- isolamento de oficina;
- permissões e feature flag;
- webhook, reconciliação, cancelamento, inutilização elegível e downloads;
- Central/detalhe para origem manual.

**Rollout**

1. homologação;
2. oficina interna/piloto;
3. emissão manual sob permissão específica;
4. métricas de erro/uncertain;
5. expansão gradual.

### Fase H — Central fiscal completa

**Objetivo**

Exibir requisições normais, eventos e documentos derivados numa leitura unificada.

**Arquivos envolvidos**

- `apps/finance/views/issued_documents.py`;
- `issued_documents_list.html` e `issued_documents_results.html`;
- adapter/query de `NfeRequest`, `NfseRequest`, `FiscalDocument` e `FiscalDocumentEvent`;
- downloads em lote.

**Impacto:** consulta e navegação; não muda emissão.

**Risco:** médio por duplicidade de linhas, paginação e downloads.

**Testes necessários**

- um documento legado não aparece duplicado por causa da projeção `FiscalDocument`;
- hierarquia original/CC-e/devolução/complementar/ajuste;
- filtros, busca, datas e paginação;
- linhas manual e OS;
- downloads e permissões;
- performance/N+1;
- isolamento por oficina.

### Fase I — Estoque opcional, em projeto separado

**Objetivo**

Oferecer seleção somente leitura de produto/entrada de estoque e, apenas depois, decidir movimentação.

**Arquivos envolvidos**

- `apps/stock/models.py`: `StockImport`, `StockProduct`, `StockMovement`;
- novas queries/adapters de seleção;
- `apps/finance/services/nfe_returns.py` somente como consumidor do item fiscal normalizado, sem perder validação de saldo.

**Impacto:** conveniência operacional; não é requisito do motor fiscal.

**Risco:** alto se emissão fiscal e saldo forem acoplados na mesma transação sem idempotência.

**Testes necessários**

- seleção por oficina;
- item de estoque mapeado ao sequencial da NF-e original;
- saldo fiscal de devolução prevalece;
- nenhuma movimentação no simples ato de selecionar/emitir;
- se movimentação for aprovada futuramente: idempotência, rollback, estorno e reconciliação.

---

## 15. Checklist de preservação para implementação futura

Antes de liberar qualquer nova entrada:

- [ ] payload da emissão com OS permanece igual;
- [ ] preview e transmissão usam o mesmo builder;
- [ ] toda transmissão abre/usa `FiscalEmissionAttempt`;
- [ ] timeout incerto nunca causa reenvio automático;
- [ ] toda consulta é filtrada pela oficina ativa;
- [ ] snapshots não mudam com edição posterior do cadastro;
- [ ] URLs antigas continuam funcionando;
- [ ] detalhe mantém os atalhos operacionais;
- [ ] cancelamento e inutilização conservam suas regras distintas;
- [ ] devolução conserva saldo e documento original;
- [ ] transporte continua no payload normal;
- [ ] CC-e continua em `FiscalDocumentEvent`;
- [ ] documentos derivados continuam em `FiscalDocument` + `FiscalDocumentLink`;
- [ ] nenhuma OS/orçamento fictício é criado;
- [ ] testes de regressão cobrem origem OS e origem manual.

---

## 16. Conclusão

**Qual é o menor caminho seguro para transformar o Emitir Nota em uma central de operações fiscais sem alterar nada que já funciona em produção?**

Criar primeiro um **gateway roteador anterior ao wizard atual**, mantendo `EmissionRequestCreateView` e sua rota normal interna intactos. Esse gateway apenas escolhe a operação:

- normal com OS segue para o wizard existente;
- CC-e, devolução e complementar selecionam a NF-e e seguem para as views/services existentes;
- ajuste usa uma view fina sobre o service existente;
- transporte abre a configuração da NF-e normal.

As operações que já existem — CC-e, devolução, complementar, ajuste e transporte — devem ganhar novas portas de entrada na Central, mas continuar chamando exatamente seus services, models de auditoria, regras de idempotência, webhooks, reconciliação e downloads atuais. O detalhe da NF-e permanece como atalho contextual.

Em uma entrega posterior e isolada, a NF-e normal sem OS deve ganhar uma origem manual explícita que produza snapshots normalizados de destinatário, itens, valores e pagamento. Antes de habilitá-la, a origem OS deve passar pelo mesmo contrato interno e provar, por testes golden master, que o payload produtivo permanece idêntico. Só depois a origem manual converge para o mesmo `build_nfe_payload(...)`, o mesmo `FiscalEmissionAttempt`, a mesma integração Webmania e a mesma reconciliação.

Em síntese:

```text
Preservar o núcleo fiscal.
Adicionar entradas finas.
Normalizar as origens antes do builder.
Roteá-las aos serviços existentes.
Implantar incrementalmente, com compatibilidade e isolamento por oficina.
```

Essa abordagem permite ampliar a Central sem reescrever a emissão, sem duplicar integração e sem transformar a evolução funcional em uma migração arriscada do núcleo fiscal que já opera em produção.
