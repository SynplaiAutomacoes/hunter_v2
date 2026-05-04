# Fiscal, NFe/NFSe e Webmania

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Financeiro e DRE](08-financeiro-e-dre.md) | [Proximo: Deploy, build e operacao](10-deploy-build-e-operacao.md)

## Escopo

O projeto possui camada fiscal relevante. Ela nao se limita a um formulario de emissao. Existe configuracao de empresa, classes de imposto, certificados, requisicoes, webhook, download de documentos e conciliacao.

## Componentes principais desse dominio

### Oficina

A oficina e o ponto operacional de onde saem configuracoes importantes, inclusive logo, certificado e dados conectados a emissao.

### Empresa Webmania

Existe uma representacao de empresa integrada com a Webmania, associada a oficina, usada para emissao e sincronizacao.

### Classes de imposto

O sistema expoe gerencia de classes e presets, o que indica uma modelagem mais rica para emissao do que um payload fiscal fixo.

### Requisicoes de emissao

As rotas em `apps/finance/urls.py` mostram suporte a:

- preview de emissao
- criacao de emissao
- listagem de NF-e
- detalhe, reconciliacao, cancelamento e download de documentos de NF-e
- listagem de NFS-e
- detalhe, cancelamento e download de documentos de NFS-e

### Webhook da Webmania

O projeto possui endpoint dedicado para receber callbacks da Webmania.

## Autenticacao do webhook

`apps/finance/views/webhook.py` mostra alguns comportamentos importantes:

- o webhook aceita `GET` para ping
- no `POST`, valida token via querystring ou header `X-Webhook-Token`
- o token esperado e derivado do projeto
- apenas modelos conhecidos sao aceitos
- o payload e persistido antes do processamento
- o processamento pode ser imediato ou adiado

Isso reduz risco de perda de evento e ajuda no troubleshooting.

## Certificado e armazenamento de arquivos

`apps/workshops/services/files.py` mostra que certificado e logo de oficina ficam em um bucket S3 compativel. No caso do certificado, ha ainda sincronizacao com dados da Webmania e tratamento atomico para evitar estado parcial.

Pontos relevantes:

- `ACCESS_KEY_ID`, `SECRET_ACCESS_KEY`, `BUCKET` e `ENDPOINT` precisam estar configurados para o fluxo de arquivos
- certificados e logos sao persistidos por chave no bucket privado
- o servico faz limpeza de arquivos antigos quando substitui conteudo
- o logo da oficina e sincronizado com a Webmania por uma URL publica servida pela aplicacao
- o processo tenta manter consistencia entre banco local e estado remoto na Webmania

## Variaveis de ambiente essenciais

### Credenciais Webmania

- `WEBMANIA_API_KEY`
- `WEBMANIA_CONSUMER_KEY`
- `WEBMANIA_CONSUMER_SECRET`
- `WEBMANIA_ACCESS_TOKEN`
- `WEBMANIA_ACCESS_TOKEN_SECRET`
- `WEBMANIA_B2B_CONSUMER_KEY`
- `WEBMANIA_B2B_CONSUMER_SECRET`
- `WEBMANIA_B2B_ACCESS_TOKEN`
- `WEBMANIA_B2B_ACCESS_TOKEN_SECRET`
- `WEBMANIA_WEBHOOK_TOKEN`
- `WEBMANIA_AMBIENT`

### Estrutura de certificado/arquivo

- `ACCESS_KEY_ID`
- `SECRET_ACCESS_KEY`
- `BUCKET`
- `ENDPOINT`
- `REGION`

## Homologacao x producao

`WEBMANIA_AMBIENT` controla o ambiente da integracao.

- `1`: producao
- `2`: homologacao

Esse detalhe precisa estar correto antes de investigar qualquer erro de emissao, porque muda comportamento e expectativa de documentos.

## Reconciliacao

O repositorio contem o comando `manage.py reconcile_webmania_documents`. Isso e um indicio claro de que o sistema precisa de ferramenta operacional para alinhar estado local e remoto quando necessario.

## Sintomas comuns e o que verificar

### Emissao falha antes de sair

- confira credenciais Webmania
- confira oficina/empresa configurada
- confira certificado e senha
- confira classe de imposto e atributos fiscais do item

### Webhook nao chega

- confira token
- confira endpoint publicado
- confira logs do webhook

### Documento saiu na Webmania, mas nao refletiu localmente

- confira armazenamento do evento
- confira processamento do webhook
- use o comando de reconciliacao se fizer sentido para o caso

### Erro envolvendo certificado

- confira se o certificado esta salvo para a oficina correta
- confira as credenciais do bucket
- confira senha do certificado

## Onde navegar no codigo

- `apps/finance/urls.py`
- `apps/finance/views/webhook.py`
- `apps/finance/services/`
- `apps/workshops/services/files.py`

## Relacao com outros dominios

Fiscal conversa com:

- `apps.workshops`
- `apps.catalog`
- `apps.stock`
- `apps.workorder`
- `apps.finance`

Por isso, erros fiscais as vezes nascem de dados de produto, de oficina ou de execucao, e nao do emissor em si.

[Anterior: Financeiro e DRE](08-financeiro-e-dre.md) | [Indice da documentacao](README.md) | [Proximo: Deploy, build e operacao](10-deploy-build-e-operacao.md) | [Voltar ao README principal](../README.md)
