# Plano de testes e operacao fiscal

## Estrategia

- Unitarios para normalizacao de status, payloads e idempotencia.
- Services/gateways com `requests` mockado.
- Contratos OpenAPI para validar request bodies, responses e parametros por operacao antes de implementar gateways.
- Webhook com payload duplicado, fora de ordem e desconhecido.
- Concorrencia com transacoes e locks.
- Tenancy e permissoes por oficina.
- Downloads com autorizacao.
- Reconciliacao sem emissao.
- Migrations e backfill em dry-run.
- Homologacao manual sem documentos reais em testes automatizados.

## Matriz de testes por camada

| Camada | Testes obrigatorios | Observacoes |
| ------ | ------------------- | ----------- |
| Schemas/OpenAPI | Validar JSON, schemas referenciados, `requestBody` em POST/PUT/DELETE, responses em todas operacoes | Fase 0.1 e futuras atualizacoes |
| Gateways Webmania | Montagem de URL, headers v1/v2, body, timeout, parse de erro, parse de downloads | Sempre com mock, nunca emissao real |
| Services fiscais | Idempotencia, estados, persistencia de payload sanitizado, transicao `uncertain` | Fase 1 antes de expandir documentos |
| Webhook | Token, payload bruto, fingerprint, duplicidade, ordem, modelo desconhecido | Reprocessamento seguro |
| Reconciliacao | Consulta sem emissao, recuperacao de downloads, relatorio operacional | Incluir NF-e e NFS-e na Fase 1 |
| Tenancy/permissoes | Cross-workshop negado, payload restrito, downloads restritos | Testar owner, diretor, gerente, colaborador |
| UI/workflows | Acoes condicionais por status/permissao/capacidade | Sem depender de dados reais Webmania |
| Migrations/backfill | `--check --dry-run`, plano, backfill idempotente | Antes da Fase 8 |
| Feature flags | NFCom/DC-e desligadas por padrao, habilitacao por oficina | Obrigatorio antes das Fases 6/7 |

## Testes obrigatorios antes de nova emissao

- Duas solicitacoes concorrentes nao geram duas emissoes remotas.
- Timeout apos envio remoto entra em `uncertain`.
- `uncertain` bloqueia reenvio.
- Webhook duplicado nao duplica efeitos.
- Webhook fora de ordem nao regride status.
- Webhook antes de documento local e recuperavel.
- Reconciliacao atualiza sem emitir.
- Usuario de uma oficina nao acessa documento de outra.
- Cancelamento respeita status e permissao.
- Downloads respeitam autorizacao.
- Credenciais nao aparecem em logs.
- Homologacao e producao nao se confundem.
- NFCom desligada nao aparece nem permite chamadas.
- DC-e desligada nao aparece nem permite chamadas.
- Divergencias oficiais NFS-e/MDF-e possuem testes de URL conforme rota operacional validada.

## Comandos esperados

```bash
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py migrate --plan
uv run python manage.py test apps.finance --keepdb
uv run python manage.py test apps.workshops --keepdb
uv run python manage.py test apps.workorder --keepdb
uv run ruff check .
uv run mypy .
```

## Operacao

- Reconciliacao deve produzir relatorio de documentos consultados, atualizados, incertos, falhos e ignorados.
- Logs devem conter ids locais, oficina e tipo documental, nunca credenciais.
- Falhas de webhook devem ser reprocessaveis.
- Falhas `uncertain` exigem acao manual ou reconciliacao antes de nova tentativa.
- NFCom e DC-e devem ter metrica/flag separada para desligamento rapido.

## Rollback

- Fase 1 deve manter legado operacional.
- Novas tabelas nao devem impedir leitura das telas atuais.
- Flags devem permitir desativar documentos novos sem afetar NF-e/NFS-e existentes.

## Plano completo de validacao por fase

| Fase | Validacao minima | Validacao complementar |
| ---- | ---------------- | ---------------------- |
| 0/0.1 | JSON OpenAPI valido, docs alterados somente em `docs/fiscal-webmania/**` | Revisao manual das divergencias oficiais |
| 1 | Testes de idempotencia, webhook, reconciliacao NF-e/NFS-e, tenancy e downloads | `ruff check .`, `mypy .` se Python tipado mudar |
| 2 | Gateway NF-e/NFC-e para cada operacao nova com mock | UI de acoes condicionais e permissao |
| 3 | Capacidades municipais, substituicao e cancelamento NFS-e com mock | Municipios com recurso indisponivel |
| 4 | CT-e/CT-e OS emissao/consulta/cancelamento/eventos | Bloqueio CT-e OS simplificado |
| 5 | MDF-e pendente nao encerrado e encerramento/cancelamento | Vinculos com NF-e/CT-e |
| 6 | NFCom feature flag, emissao manual, consulta, download | Desligamento sem efeito colateral |
| 7 | DC-e beta isolada, feature flag e cancelamento | Desativacao segura |
| 8 | Backfill dry-run, migracao, rollback e comparacao legado/unificado | Remocao controlada apos validacao |

## Fase 2.0 - Testes planejados NF-e/NFC-e

Testes transversais obrigatorios para cada subfase da Fase 2:

- Gateway monta URL, headers v1 e body esperado sem credenciais persistidas.
- Uma acao concorrente da mesma intencao gera uma unica chamada remota.
- Timeout apos `sent` marca tentativa como `uncertain`.
- Tentativa `uncertain` bloqueia reenvio automatico.
- Webhook/consulta atualizam documento/evento existente, sem emitir.
- Usuario de outra oficina nao acessa documento, evento, payload ou download.
- Permissao especifica e exigida antes da chamada remota.
- Logs e payloads persistidos sao sanitizados.
- `makemigrations finance --check --dry-run` passa apos migrations da subfase.
- `ruff check` nos arquivos tocados passa.

### Fase 2.1 - CC-e

- Emitir CC-e para NF-e autorizada com `requests.post` mockado.
- Bloquear CC-e para NF-e reprovada, cancelada, denegada, `processing` ou `uncertain`.
- Validar texto obrigatorio/minimo e impedir alteracao de valores fiscais.
- Concorrencia: duas requisicoes da mesma CC-e geram uma chamada remota.
- Timeout: evento fica `uncertain` e bloqueia reenvio.
- Webhook/consulta: atualiza `FiscalDocumentEvent` sem criar nota comum.
- Download: XML de evento acessivel apenas por usuario autorizado.
- Tenancy: NF-e de outra oficina retorna 404/403 antes do gateway.
- Permissao: sem `issue_nfe_correction`, nao chama Webmania.

### Fase 2.2A - Devolucao e estorno

- Documento de devolucao/estorno referencia obrigatoriamente documento original local ou externo.
- Devolucao parcial valida produtos e quantidades contra a nota original quando houver dados locais/consulta.
- NF-e externa cria `FiscalDocument` minimo `origin=external` e registra chave manual.
- NF-e externa valida somente formato da chave de 44 digitos e exige confirmacao explicita; nao chama consulta padrao como garantia.
- NF-e externa minima bloqueia devolucao parcial sem XML/importacao validada dos itens e da ordem fiscal original.
- Devolucao parcial local envia `produtos` como sequenciais fiscais e `quantidade` alinhado pelo mesmo indice; devolucao total e estorno nao enviam selecao parcial desnecessaria.
- Saldo parcial considera documentos derivados aprovados, processando, contingencia e `uncertain`; reprovado e cancelado confirmado nao reservam saldo.
- Duas devolucoes parciais legitimas com payload equivalente podem existir como documentos derivados distintos.
- Mesma intencao derivada nao pode trocar payload apos envio.
- Timeout apos envio vira `uncertain` e bloqueia reenvio.
- Webhook de derivado atualiza derivado, nao sobrescreve original.

### Fase 2.2B - Nota complementar

- Complementar referencia obrigatoriamente NF-e original local ou externa por chave/UUID.
- Testar complemento de preco local.
- Testar complemento de quantidade local.
- Testar complemento tributario separado para ICMS, ICMS-ST, IPI, ISSQN e IBS/CBS conforme campos suportados no payload aprovado.
- Testar documento externo minimo com chave de 44 digitos, confirmacao explicita e sem falsa validacao remota.
- Testar bloqueio de `complementary_price_quantity` para NF-e externa minima sem XML/importacao validada dos itens.
- Testar regra aprovada para `complementary_tax` externa: bloqueio ou permissao restrita com confirmacao forte e payload auditavel.
- Testar que `complementary_import_addition` permanece indisponivel se for adiado.
- Testar `FiscalDocumentLink(role="complements")` obrigatorio.
- Testar idempotencia por documento complementar derivado e timeout `uncertain`.
- Testar concorrencia da mesma intencao gerando uma chamada remota.
- Testar webhook atualizando somente derivado e nao alterando a nota original.
- Testar permissao, cross-workshop, downloads protegidos e payload/log sanitizados.

Cobertura executada na Fase 2.2B.1: somente `complementary_price_quantity` local. Os testes cobrem complemento de preco, quantidade, preco+quantidade, link obrigatorio, bloqueio de original inelegivel, bloqueio de NF-e externa minima, ausencia de objetos tributarios/IBS-CBS fora do escopo, idempotencia por documento derivado, concorrencia com uma chamada remota, duas complementares independentes, timeout `uncertain`, payload congelado, webhook duplicado/fallback/ambiguidade, reconciliacao sem emissao, permissao especifica, cross-workshop, downloads protegidos e sanitizacao. A validacao final reforcou que complemento apenas de preco nao envia quantidade original, complemento apenas de quantidade nao envia valor original, e o payload nao repete silenciosamente `subtotal`, `total` ou `valor_unitario` da NF-e original.

### Fase 2.2C - Nota de ajuste

- Ajuste sem documento original e permitido.
- Ajuste com documento original usa `FiscalDocumentLink` opcional e nao obrigatorio.
- Payload exige `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `ambiente` e `cliente`.
- Timeout vira `uncertain`; retry automatico e proibido.
- Regime tributario permite Lucro Real/Normal e Lucro Presumido; bloqueia Simples Nacional, MEI e regime ausente/desconhecido.
- Payload nao envia `produtos`, `pedido`, `impostos`, IBS, CBS, `agropecuario`, importacao ou adicao.
- Link `adjusts` opcional nao altera status do documento relacionado.
- Webhook atualiza somente o ajuste por UUID/tentativa/fallback seguro; ambiguidade nao atualiza nada.
- Reconciliacao consulta ajuste `uncertain` sem emissao.
- Permissao `issue_nfe_adjustment` e exigida antes do gateway; downloads exigem `download_nfe_adjustment`.
- Cobertura executada na validacao: Fases 1, 2.1, 2.2A, 2.2B.1 e 2.2C direcionadas com 68 testes OK; `makemigrations finance --check --dry-run`, `ruff check` nos arquivos Python tocados e `git diff --check` OK.

### Fase 2.3 - NFC-e

- Oficina sem configuracao NFC-e bloqueia acao.
- `nfce_enabled=False` bloqueia emissao antes do gateway.
- Payload NFC-e usa `modelo=2` e configuracao correta sem afetar NF-e.
- NFC-e e NF-e da mesma origem nao compartilham chave idempotente.
- Cancelamento NFC-e respeita status e permissao.
- Downloads distinguem DANFE/NFC-e conforme retorno.
- Ambiente producao exige `nfce_serie`, `nfce_numero`, `nfce_id_csc` e `nfce_codigo_csc`.
- Ambiente homologacao exige serie, numero homologacao e CSC homologacao quando configuracao de teste estiver ativa.
- Concorrencia da mesma intencao cria uma chamada remota.
- Timeout marca documento/tentativa como `uncertain` e bloqueia retry.
- Webhook `modelo=nfce` resolve `FiscalDocument(document_type="nfce")` por UUID antes de chave e nao atualiza `NfeItem`.
- Reconciliacao de NFC-e `uncertain` usa consulta e nunca emite.
- Payload/log nao persistem headers, consumer secret, access token secret, CSC ou codigo CSC.

### Fase 2.4 - Manifestacao e IBS/CBS

- Manifestacao exige chave/documento elegivel.
- IBS/CBS exige codigo de evento e payload compativel com documentacao vigente.
- Cancelamento IBS/CBS referencia evento original.
- Evento duplicado e fora de ordem nao duplica nem regride historico.
- Revalidar schemas com documentacao oficial imediatamente antes de codificar.

### Fase 2.5 - Nota Fiscal de Credito e Debito

- NF-e de credito usa `/1/nfe/emissao/`, `finalidade=5` e `tipo_credito`.
- NF-e de debito usa `/1/nfe/emissao/`, `finalidade=6` e `tipo_debito`.
- Validar documento referenciado quando o tipo oficial exigir `dfe_referenciado`.
- Idempotencia por tipo e payload; timeout vira `uncertain`.
## Atualizacao Fase 2.3.2 - Testes Executados/Planejados

Cobertura adicionada:

- cancelamento valido envia somente `chave`/`uuid` e `motivo`;
- `nfce_referenciada` nao e enviado;
- motivo fora de 15 a 255 caracteres bloqueia;
- NFC-e processando, reprovada, denegada, cancelada, incerta ou sem chave/UUID bloqueia antes do gateway;
- evento `cancellation` e tentativa `nfce_cancellation` sao criados sem novo documento e sem `FiscalDocumentLink`;
- timeout gera `uncertain` e bloqueia retry automatico;
- concorrencia da mesma intencao faz uma chamada remota;
- webhook duplica sem duplicar efeitos, rejeita ambiguidade e atualiza somente evento/documento NFC-e;
- reconciliacao consulta cancelamento incerto sem reenviar;
- permissao `cancel_nfce`, cross-workshop e download de XML de cancelamento sao protegidos;
- payload/log permanecem sanitizados e sem segredos.
