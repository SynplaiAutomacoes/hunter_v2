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

### Fase 2.2 - Devolucao, complementar e ajuste

- Documento derivado referencia documento original.
- Payload inclui chave/UUID original e finalidade correta.
- Itens/valores obrigatorios por operacao.
- Nao permite derivado a partir de documento de outra oficina.
- Cada operacao tem idempotencia propria e nao conflita com CC-e.
- Webhook de derivado atualiza derivado, nao sobrescreve original.

### Fase 2.3 - NFC-e

- Oficina sem configuracao NFC-e bloqueia acao.
- Payload NFC-e usa modelo/configuracao correta sem afetar NF-e.
- NFC-e e NF-e da mesma origem nao compartilham chave idempotente.
- Cancelamento NFC-e respeita status e permissao.
- Downloads distinguem DANFE/NFC-e conforme retorno.

### Fase 2.4 - Manifestacao e IBS/CBS

- Manifestacao exige chave/documento elegivel.
- IBS/CBS exige codigo de evento e payload compativel com documentacao vigente.
- Cancelamento IBS/CBS referencia evento original.
- Evento duplicado e fora de ordem nao duplica nem regride historico.
- Revalidar schemas com documentacao oficial imediatamente antes de codificar.
