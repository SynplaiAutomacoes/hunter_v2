# Fase 4.4.3 — Auditoria do fluxo de prévia e transmissão da NF-e

## 1. Escopo da auditoria

Esta auditoria mapeia a prévia e a transmissão da NF-e existentes no fluxo por Ordem de Serviço e compara esse comportamento com a emissão manual atual.

A análise foi realizada sobre a branch `staging`, incluindo as alterações locais ainda não commitadas das fases 4.4.1, 4.4.2A e 4.4.2B. Nenhum arquivo de aplicação, builder, payload, serviço fiscal, integração Webmania ou `FiscalEmissionAttempt` foi alterado nesta fase.

## 2. Conclusão executiva

A experiência futura desejada já existe quase integralmente no fluxo por OS:

```text
Revisar configuração fiscal
    ↓
Ver prévia
    ↓
Modal compartilhado
    ↓
DANFE em iframe
    ↓
Transmitir
    ↓
Mesmo serviço fiscal produtivo
```

Podem ser reutilizados diretamente:

- o helper `render_emission_preview_modal()`;
- o template `finance/partials/emission_preview_modal.html`;
- o endpoint `finance:nfe_preview_pdf`;
- a view `NfePreviewPdfView`;
- `get_fiscal_service().download_nfe_preview_document()`;
- o mesmo `build_nfe_payload()` com `previa_danfe=True`;
- `get_fiscal_service().emit_nfe()` e `sync_nfe_emission_response()` para a transmissão definitiva.

Não é seguro enviar a emissão manual ao endpoint do wizard por OS. Esse endpoint depende de estado de sessão, `workorder_id`, steps dinâmicos, lock por OS e `_get_or_create_nfe_request()` configurado explicitamente como `WORK_ORDER`.

A recomendação é manter `/finance/emissao/normal/manual/` como endpoint da emissão manual, acrescentando intents explícitos de **prévia** e **transmissão**, mas reutilizando o modal, o endpoint de PDF e os mesmos serviços já usados pelo fluxo por OS.

## 3. Entradas atuais

### 3.1 Entrada central

```text
GET /finance/emissao/
    ↓ FiscalOperationGatewayView
Nota Fiscal de Saída
    ↓
GET/POST /finance/emissao/normal/origem/
    ↓ NfeEmissionOriginGatewayView
Ordem de Serviço ou Emissão Manual
```

### 3.2 Origem Ordem de Serviço

O gateway redireciona para:

```text
/finance/emissao/normal/?reset=1
```

Owner: `EmissionRequestCreateView`, em `apps/finance/views/emission.py`.

### 3.3 Origem Manual

O gateway redireciona para:

```text
/finance/emissao/normal/manual/
```

Owner: `NfeManualEmissionCreateView`, em `apps/finance/views/nfe_manual.py`.

## 4. Fluxo existente por Ordem de Serviço

### 4.1 Página e navegação

Arquivos principais:

- `apps/finance/views/emission.py` — `EmissionRequestCreateView`;
- `apps/finance/templates/finance/emission_request_form.html` — página e `dialog#form_modal`;
- `apps/finance/templates/finance/partials/emission_step_content.html` — step atual e submissão HTMX;
- `apps/finance/forms/emission.py` — forms, resumo e painéis de valores;
- `apps/finance/views/request_workflow.py` — helper do modal;
- `apps/finance/templates/finance/partials/emission_preview_modal.html` — prévia e confirmação.

O estado do wizard é mantido na sessão por oficina e usuário:

```text
finance.emission_wizard:{workshop_id}:{user_id}
```

As etapas relevantes para NF-e são:

```text
Selecionar OS
    ↓
Conferir Cliente
    ↓
Conferir Produtos/Serviços
    ↓
Resumo
    ↓
Escolher NF-e/NFS-e
    ↓
Configuração da NF-e
```

### 4.2 Ação “Ver prévia”

No step final de configuração da NF-e, `EmissionRequestCreateView` define:

- label do botão: `Ver prévia`;
- POST para `/finance/emissao/normal/?step=<step>`;
- campo `intent=preview`;
- target HTMX: `#step-container` inicialmente, posteriormente redirecionado pelo response para o modal.

Em `form_valid()`:

1. os dados fiscais são armazenados no estado da sessão;
2. `_get_or_create_nfe_request()` cria ou atualiza um `NfeRequest` de origem `WORK_ORDER`;
3. `_preview_nfe()` produz o endereço `finance:nfe_preview_pdf`;
4. `_build_preview_response()` chama `render_emission_preview_modal()`;
5. a resposta HTMX recebe `HX-Retarget: #modal-container` e `HX-Reswap: innerHTML`;
6. `emission_request_form.html` detecta o swap e abre o `dialog#form_modal`.

### 4.3 Modal existente

O modal está em:

```text
apps/finance/templates/finance/partials/emission_preview_modal.html
```

Ele possui:

- título e orientação;
- uma ou mais prévias;
- iframe para o documento;
- link “Abrir em nova aba”;
- botão “Cancelar”;
- botão **“Transmitir”**;
- estado de loading **“Transmitindo...”**;
- bloqueio dos botões durante o POST;
- recuperação do estado visual em erro HTMX.

Não existe atualmente o texto literal “Transmitir nota”. O botão compartilhado usa “Transmitir”.

O modal aceita múltiplas prévias porque o wizard também suporta o modo NF-e + NFS-e.

### 4.4 Geração da prévia DANFE

O iframe chama:

```text
GET /finance/nfe/<pk>/previa/pdf/
URL name: finance:nfe_preview_pdf
View: NfePreviewPdfView
```

`NfePreviewPdfView`:

- exige login;
- aplica escopo da oficina ativa;
- exige `finance.view_nferequest`, com fallback legado de NFS-e;
- permite exibição em iframe por `xframe_options_exempt`;
- retorna `Content-Disposition: inline`;
- retorna `Cache-Control: no-store`.

Cadeia interna:

```text
NfePreviewPdfView
    ↓
get_fiscal_service().download_nfe_preview_document()
    ↓
WebmaniaFiscalService.download_nfe_preview_document()
    ↓
download_nfe_preview_document()
    ↓
build_nfe_payload()
    ↓
payload["previa_danfe"] = True
    ↓
POST Webmania /1/nfe/emissao/
    ↓
PDF direto ou download da URL devolvida pela Webmania
```

A prévia usa o mesmo builder e o mesmo endpoint remoto de emissão, mas com `previa_danfe=True`. Ela não chama `reserve_nfe_request_number()`, não cria `FiscalEmissionAttempt` e não sincroniza um documento fiscal emitido.

Existe também `preview_nfe_request()`, que obtém uma URL de prévia, porém o iframe atual usa `download_nfe_preview_document()` por meio de `NfePreviewPdfView`.

### 4.5 Confirmação e transmissão

O form do modal faz POST para o mesmo step do wizard e envia:

- CSRF token;
- `intent=transmit`;
- campos limpos preservados como hidden fields.

O modal não chama a Webmania diretamente. O POST retorna a `EmissionRequestCreateView.form_valid()`. Como o intent não é mais `preview`, a view chama:

```text
_finalize_selected_notes()
    ↓
_emit_nfe()
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
sync_nfe_emission_response()
```

Há duas proteções contra duplicidade:

- lock transitório de cache por oficina, OS e tipo de nota, com duração de 120 segundos;
- `FiscalEmissionAttempt`, que permanece como proteção fiscal persistente e definitiva.

### 4.6 Rotas relacionadas que não devem ser confundidas

`/finance/emissao/preview/`, associado a `EmissionPreviewView`, renderiza o corpo do resumo/precificação do wizard. Não é o endpoint do PDF DANFE nem o endpoint que transmite a nota. Não foi localizado call site ativo por nome dessa rota na UI consolidada.

O fluxo legado `NfeRequestCreateView`/`NfeRequestUpdateView` também usa o mesmo helper e o mesmo modal. Entretanto, a origem OS oficial acessada pelo gateway é hoje `EmissionRequestCreateView` em `/finance/emissao/normal/`.

## 5. Fluxo manual atual

### 5.1 Tela final

Arquivos:

- `apps/finance/forms/nfe_manual.py`;
- `apps/finance/views/nfe_manual.py`;
- `apps/finance/templates/finance/nfe_manual_emission_form.html`.

A tela manual possui três etapas controladas no navegador:

```text
Destinatário
    ↓
Produtos
    ↓
Revisar e emitir
```

Na última etapa são exibidos:

- classe de imposto;
- informações complementares;
- resumo do destinatário;
- resumo dos produtos;
- checkbox `Confirmo a emissão desta NF-e pela Webmania`;
- botão `Emitir NF-e`.

Não há botão “Ver prévia”, intent de preview, iframe ou modal de confirmação da transmissão.

### 5.2 POST e validações

O form principal usa POST HTML normal para:

```text
/finance/emissao/normal/manual/
```

Antes da emissão são validados:

- destinatário pertencente à oficina ativa;
- classe de imposto disponível;
- confirmação explícita;
- ao menos um item não removido;
- quantidade e valor unitário positivos;
- ausência de produto de catálogo repetido;
- origem `CATALOG` ou `TEMPORARY` coerente;
- produto de catálogo pertencente à oficina;
- snapshot fiscal obrigatório e válido para produto temporário.

### 5.3 Transmissão atual

`NfeManualEmissionCreateView.form_valid()` executa tudo na mesma requisição:

```text
POST do formulário
    ↓
cria NfeRequest MANUAL
    ↓
cria NfeRequestManualItem(s)
    ↓
get_fiscal_service().emit_nfe()
    ↓
get_fiscal_service().sync_nfe_emission_response()
    ↓
redirect para finance:nfe_detail
```

Logo, o clique em `Emitir NF-e` já é a transmissão definitiva. Não existe hoje uma requisição manual persistida especificamente como draft de prévia e reutilizada no segundo POST.

## 6. Componentes reutilizáveis

| Componente | Reutilização | Observação |
|---|---|---|
| `emission_preview_modal.html` | Direta | Já contém iframe, cancelar, transmitir, loading e proteção contra clique repetido |
| `render_emission_preview_modal()` | Direta | Basta informar título, preview, URL de transmissão e hidden fields mínimos |
| `NfePreviewPdfView` | Direta | É independente da origem e já limita o request à oficina ativa |
| `finance:nfe_preview_pdf` | Direta | Aceita qualquer `NfeRequest` compatível com o builder, inclusive `MANUAL` |
| `download_nfe_preview_document()` | Direta | Usa o mesmo builder com `previa_danfe=True` |
| `build_nfe_payload()` | Sem alteração | Já suporta WORK_ORDER, CATALOG manual e TEMPORARY manual no estado atual |
| `get_fiscal_service().emit_nfe()` | Direta | Deve continuar sendo a única entrada de transmissão manual |
| `sync_nfe_emission_response()` | Direta | Mantém sincronização e histórico atuais |
| `build_preview_hidden_fields()` | Parcial | Não representa sozinho um formset inteiro; é preferível transmitir o ID do draft persistido |
| Endpoint do wizard OS | Não reutilizar | Pressupõe OS, sessão própria, steps e origem WORK_ORDER |
| `EmissionPreviewView` | Não indicado | É preview do painel de resumo, não do DANFE |

## 7. Proposta de reutilização

### 7.1 Fluxo recomendado

```text
Revisar emissão manual
    ↓ POST intent=preview
NfeManualEmissionCreateView
    ↓ valida formulário e formset
cria/atualiza NfeRequest MANUAL e seus itens em transação
    ↓
render_emission_preview_modal()
    ↓
iframe finance:nfe_preview_pdf
    ↓
NfePreviewPdfView + download_nfe_preview_document()
    ↓ usuário confere
POST intent=transmit para /finance/emissao/normal/manual/
    ↓ carrega o mesmo NfeRequest MANUAL da oficina
get_fiscal_service().emit_nfe()
    ↓
sync_nfe_emission_response()
```

### 7.2 Endpoint de transmissão

É possível manter o mesmo endpoint manual:

```text
POST /finance/emissao/normal/manual/
```

Esse endpoint deve distinguir:

- `intent=preview`: valida e persiste o draft, sem emitir;
- `intent=transmit`: recupera o draft já exibido e executa o serviço atual.

Não é recomendável reaproveitar literalmente `/finance/emissao/normal/?step=...`, porque ele pertence ao state machine da OS.

### 7.3 Identidade do draft

O segundo POST deve referenciar o `NfeRequest` que gerou a prévia, em vez de reconstruir toda a emissão com hidden fields editáveis.

Alternativas seguras:

1. guardar o ID do draft manual na sessão por oficina e usuário;
2. enviar ID assinado no modal e sempre recarregar por `pk`, oficina e origem `MANUAL`;
3. combinar sessão e ID assinado para maior isolamento.

O modelo atual não possui proprietário `created_by`. Portanto, usar apenas um `pk` aberto no POST não é suficiente; o escopo da oficina é obrigatório e a vinculação à sessão é recomendada.

### 7.4 Integração HTMX

A página manual já possui `dialog#form_modal` e `#modal-container`, usados pelos cadastros rápidos. Para reutilizar o modal de prévia, será necessário:

- fazer o POST de preview por HTMX;
- direcionar a resposta para `#modal-container`;
- abrir o dialog após o swap, reutilizando o comportamento já existente em `emission_request_form.html`;
- em formulário inválido, manter os erros no wizard, sem inserir uma página completa dentro do modal;
- após transmissão, devolver `HX-Redirect` para o detalhe da NF-e.

Não é necessário criar outro modal.

### 7.5 Confirmação atual

O checkbox `Confirmo a emissão desta NF-e pela Webmania` se torna redundante quando o usuário precisa abrir a prévia e clicar em `Transmitir`.

Na implementação futura deve existir uma única confirmação inequívoca. A recomendação é transformar o botão do modal na confirmação final e remover a confirmação antecipada da etapa de revisão, desde que os testes e requisitos jurídicos não dependam dela.

## 8. Riscos e controles necessários

### 8.1 Duplicação de drafts

Hoje cada POST manual cria um novo `NfeRequest`. Se preview e transmissão forem implementados como dois POSTs sem identidade persistente, serão criadas requisições duplicadas.

Controle: criar ou atualizar um único draft e reutilizar seu ID na transmissão.

### 8.2 Divergência entre prévia e transmissão

Se os dados forem reconstruídos de hidden fields, eles podem ser alterados após a prévia.

Controle: transmitir o mesmo `NfeRequest` persistido que alimentou o PDF. Alterações posteriores devem exigir nova prévia.

### 8.3 Duplo clique e retry

O modal já desabilita o botão durante o POST. Ainda assim, isso é apenas proteção visual.

Controle: preservar `FiscalEmissionAttempt` como autoridade contra duplicidade. Pode-se avaliar um lock transitório específico por `NfeRequest`, sem substituir o attempt.

### 8.4 Cancelamento do modal

Fechar a prévia deixará um draft manual persistido.

Controle: definir se o draft será retomável, atualizado na próxima tentativa ou descartado de forma controlada. Não excluir automaticamente documentos que já possuam attempt.

### 8.5 Recarregamento do iframe

Cada carregamento de `finance:nfe_preview_pdf` pode gerar uma nova chamada remota de prévia à Webmania, pois a resposta usa `no-store`.

Controle: evitar múltiplos iframes/reloads acidentais e tratar falhas remotas de preview sem transmitir a nota.

### 8.6 Produtos temporários

O endpoint de PDF poderá usar itens `TEMPORARY` porque o adaptador manual atual já os converte para `ProductEmissionLine`.

Controle: testes devem comparar o payload da prévia e da transmissão para produtos de catálogo, temporários e mistos.

### 8.7 Permissões

O preview PDF e o fluxo manual utilizam `view_nferequest` com fallback legado. A transmissão deve continuar passando pela mesma view autorizada e pelo escopo da oficina.

Controle: testar acesso autorizado, oficina diferente, ID manipulado e POST de transmissão sem preview/draft válido.

## 9. Lacunas de teste encontradas

A regressão fiscal cobre emissão por OS e manual, mas não foi localizado um teste dedicado que percorra integralmente:

```text
intent=preview
    ↓
render do modal
    ↓
GET do PDF
    ↓
intent=transmit
    ↓
emissão única
```

A implementação futura deve adicionar essa cobertura tanto para OS quanto para manual, com atenção especial a retries e requests manipulados.

## 10. Fases recomendadas para implementação

### Fase 4.4.4A — Ciclo de vida do draft manual

- separar `preview` e `transmit` na view manual;
- criar/atualizar um único `NfeRequest MANUAL`;
- vincular o draft à oficina e à sessão;
- preservar itens CATALOG/TEMPORARY;
- impedir transmissão sem draft válido;
- não alterar builder, payload ou serviço fiscal.

### Fase 4.4.4B — Integração do modal existente

- trocar o botão final para `Ver prévia`;
- reutilizar `render_emission_preview_modal()`;
- reutilizar `emission_preview_modal.html`;
- reutilizar `NfePreviewPdfView`;
- integrar abertura/fechamento HTMX no dialog já existente;
- transmitir pelo mesmo endpoint manual com `intent=transmit`.

### Fase 4.4.4C — Regressão e homologação

- catálogo, temporário e itens mistos;
- preview sem `FiscalEmissionAttempt`;
- transmissão criando somente um attempt;
- preview e transmissão com payload coerente;
- cancelamento e nova abertura do modal;
- duplo clique/retry;
- permissões e escopo de oficina;
- regressão completa de NF-e por OS e operações fiscais derivadas.

## 11. Arquivos envolvidos em uma futura implementação

Alterações prováveis:

- `apps/finance/views/nfe_manual.py`;
- `apps/finance/forms/nfe_manual.py`;
- `apps/finance/templates/finance/nfe_manual_emission_form.html`;
- `apps/finance/test_nfe_manual_emission.py`.

Componentes a reutilizar sem duplicação:

- `apps/finance/views/request_workflow.py`;
- `apps/finance/templates/finance/partials/emission_preview_modal.html`;
- `apps/finance/views/nfe.py` — `NfePreviewPdfView`;
- `apps/core/infrastructure/services/fiscal/service.py`;
- `apps/core/infrastructure/services/webmania/nfe_emission.py`.

Não há evidência de necessidade de novo model, migration, builder, payload Webmania, serviço fiscal ou endpoint externo.

## 12. Decisão recomendada

Reutilizar integralmente a infraestrutura de prévia existente e manter a transmissão manual no endpoint manual atual.

O desenho recomendado é:

```text
NfeRequest MANUAL persistido
    ├── preview → NfePreviewPdfView → build_nfe_payload + previa_danfe=True
    └── transmit → get_fiscal_service().emit_nfe → FiscalEmissionAttempt → Webmania
```

Isso entrega a experiência solicitada sem criar modal, motor fiscal, builder, payload ou fluxo de transmissão paralelo.
