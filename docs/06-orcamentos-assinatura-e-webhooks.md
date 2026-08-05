# Orcamentos, assinatura e webhooks

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md) | [Proximo: Estoque e catalogo](07-estoque-e-catalogo.md)

## Por que este modulo merece doc propria

`apps.budget` parece ser o principal app do produto. Ele concentra o fluxo comercial e tecnico de atendimento, alem de PDF, assinatura e eventos. Boa parte do comportamento de negocio do sistema passa por aqui.

## O que o modulo cobre

Pelo mapa de rotas em `apps/budget/urls.py`, o app de orcamento cobre:

- listagem, criacao, edicao e exclusao de orcamentos
- eventos em tempo real
- detalhes de cliente e veiculo
- selecao, adicao, remocao e calculo de itens
- edicao de kits e componentes
- slider, desconto e mudanca de status
- observacoes e resumos
- PDFs e visualizacoes auxiliares
- assinatura digital
- webhook da SynplaiSign
- criacao rapida de itens locais

## O fluxo de orcamento em termos praticos

### 1. Contexto inicial

O orcamento nasce associado a cliente, veiculo e oficina. Sem esse contexto, o restante do fluxo perde sentido.

### 2. Triagem e perguntas investigativas

O sistema coleta informacoes iniciais do problema relatado e perguntas investigativas que ajudam a orientar o diagnostico.

### 3. Diagnostico tecnico

Entram checklist, colaboradores, defeitos, observacoes e imagens.

### 4. Composicao comercial

O usuario adiciona produtos, servicos e kits. O modulo tambem suporta criacao local e criacao rapida de itens em alguns cenarios.

### 5. Precificacao

Aqui entram os calculos mais sensiveis:

- valor de item
- valor de servico
- kits e componentes
- slider de composicao
- desconto
- rentabilidade

### 6. Fechamento

O orcamento pode ser consolidado em PDF, mudar de status e seguir para assinatura.

## Eventos em tempo real

O projeto possui endpoints de eventos e algumas env vars para polling/SSE:

- `BUDGET_EVENTS_ENABLED`
- `BUDGET_POLL_INTERVAL_SECONDS`
- `BUDGET_SSE_CHECK_INTERVAL_SECONDS`

Quando houver bug ou comportamento estranho em atualizacao de tela relacionada a status/calculo, vale revisar esse conjunto.

## Assinatura digital

O app de orcamento possui endpoints para:

- envio para assinatura
- preview por token
- download/arquivo por token
- webhook de conclusao da SynplaiSign

Isso indica um fluxo completo de assinatura no proprio dominio do orcamento.

O envio cria o envelope na SynplaiSign com a **API key da oficina**, envia o documento como **HTML** (mesmo template do modal, com atributo `sign-box` no bloco de assinatura; sem coordenadas `fieldX/Y/...`), inclui `phone` + `deliveryChannel` (`EMAIL` ou `BOTH` quando ha telefone), envia `whatsappInstance` com o `whatsapp_instance_name` da oficina e dispara a entrega via `POST /envelopes/:id/send`. O preview/download do modal **sem assinatura** continua em PDF (Playwright). **Respostas da SynplaiSign (documento assinado e downloads) sao sempre PDF.** O PDF assinado e obtido via `GET /envelopes/:id/file` (bytes diretos; preferivel a `/download` + URL do storage). O Hunter tenta SynplaiSign primeiro e, se falhar, faz fallback para SuperSign (documentos legados). Novos envios usam somente SynplaiSign. O WhatsApp de assinatura e nativo da SynplaiSign (usando a instancia da oficina); o WhatsApp Evolution da oficina (`whatsapp_instance_name`) continua usado tambem por messaging (agendamento, grupos, planos de revisao, etc.).

Cada oficina recebe sua propria organizacao/API key no cadastro via `POST /auth/register-with-api-key` (Master Key), com `organizationName` = nome fantasia (fallback razao social), dados do Owner da conta e senha aleatoria criptografada em `Workshop.synplaisign_owner_password`. A API key fica em `Workshop.synplaisign_api_key`, junto com o secret do webhook daquela chave.

## Comando de sincronizacao de webhook

O comando `manage.py webhook`, implementado em `apps/budget/management/commands/webhook.py`, provisiona API keys/webhooks SynplaiSign por oficina (ou `--workshop-id`) para o evento `ENVELOPE_COMPLETED`. Use `--force-recreate` (obrigatorio com `--workshop-id`) para recriar credenciais locais/remotas e `--show-secrets` para imprimir API key e senha aleatoria do OWNER SynplaiSign.

Pontos importantes do comando:

- usa `APP_BASE_URL` para construir URL absoluta (`/budget/signature/webhook/`)
- exige `SYNPLAISIGN_MASTER_KEY` para criar chaves faltantes
- avisa quando a URL publica nao esta adequadamente configurada
- pode falhar em modo estrito
- e chamado automaticamente no `entrypoint.sh`

## Por que `APP_BASE_URL` e critico

Sem `APP_BASE_URL` correto:

- a URL do webhook pode ser montada incorretamente
- ambientes locais sem tunel publico nao conseguem receber callback externo
- o fluxo de assinatura pode parecer funcional ate a parte de retorno do provedor

## Arquivos importantes para navegar

- `apps/budget/urls.py`
- `apps/budget/management/commands/webhook.py`
- `apps/core/infrastructure/services/signature_webhook.py`
- `apps/core/infrastructure/services/signature_synplaisign.py`
- `apps/core/infrastructure/gateways/synplaisign.py`

## Perguntas que valem ao alterar esse modulo

- a mudanca interfere em status do orcamento?
- ela altera calculo de itens, kits ou desconto?
- ela impacta PDF ou resumo?
- ela mexe no fluxo de aprovacao?
- ela pode quebrar assinatura ou webhook?

## Bugs comuns nesse dominio

### Assinatura nao conclui

- confira `APP_BASE_URL`
- confira `SYNPLAISIGN_MASTER_KEY` e se a oficina tem `synplaisign_api_key` provisionada
- confira se o webhook remoto da oficina foi sincronizado
- confira HMAC `x-synplai-signature` (secret da oficina)

### Webhook retorna HTTP 403 `invalid_signature`

O algoritmo HMAC (header `x-synplai-signature: sha256=...`) e o mesmo no SynplaiSign e no Hunter. O 403 quase sempre indica **secret errado no POST**, nao bug de assinatura.

Causa frequente em producao: varios `WebhookConfig` ativos no SynplaiSign apontando para a mesma URL (`www.hunterapp.io/budget/signature/webhook/`, staging, ngrok antigo), cada um com secret diferente. O `dispatch` do SynplaiSign (hoje) nao filtra por `apiKeyId`/`organizationId` e dispara para todos; o Hunter so guarda um secret por oficina — POSTs com secret stale falham, o que bate passa.

Limpeza operacional:

1. No SynplaiSign, listar webhooks e remover URLs ngrok/staging mortas e duplicatas da URL de prod
2. Deixar **um** webhook por org/API key alinhado ao `synplaisign_webhook_secret` da oficina no Hunter
3. Re-rodar provision/`manage.py webhook` se o secret local estiver vazio (o sync recria o remoto e grava o secret)

Eventos tratados pelo Hunter: `ENVELOPE_COMPLETED` (aprova) e `DOCUMENT_DECLINED` (reprova orcamento/OS). Demais eventos sao ignorados com HTTP 200.

### Lembrete de agendamento com `%%primeiro_nome%%` literal

Agendamentos **guest** (sem `customer_id`) nao tem Customer no contexto de variaveis. O render resolve `nome`/`primeiro_nome` via `appointment.guest_customer_name` (e extras). Mensagens ja `SENT` com token literal nao se corrigem no WhatsApp; PENDING sao re-renderizados ao salvar o template de Agendamento ou no envio pelo poller.

### Calculo parece inconsistente

- revise custos de oficina e regras de precificacao
- confira se o item e local, catalogado ou parte de kit
- confira se ha desconto/slider afetando o valor final

### Status nao atualiza como esperado

- revise endpoints de evento
- confira toggles de budget events
- confirme se ha algum side effect bloqueando a transicao

## Relacao com outros apps

`apps.budget` conversa diretamente com:

- `apps.customer`
- `apps.quote`
- `apps.checklist`
- `apps.catalog`
- `apps.workshops`
- `apps.workorder`
- `apps.finance`

Por isso, alteracoes nesse modulo quase nunca ficam isoladas.

[Anterior: Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md) | [Indice da documentacao](README.md) | [Proximo: Estoque e catalogo](07-estoque-e-catalogo.md) | [Voltar ao README principal](../README.md)
