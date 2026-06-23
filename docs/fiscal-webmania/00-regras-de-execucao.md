# Regras de execucao fiscal

## Regras nao negociaveis

- O estado atual do codigo e a fonte de verdade local.
- A documentacao oficial da Webmania e a fonte de verdade da API.
- O OpenAPI recebido e material de apoio; usar somente a versao validada em `api/webmania_fiscal_openapi_validated.json`.
- PRDs devem ser atualizados durante a implementacao quando o codigo revelar divergencias.
- Nao implementar fase sem aceite explicito.
- Nao emitir documentos reais em testes automatizados.
- Nao expor credenciais, certificados, tokens, payloads sensiveis ou headers secretos.
- Nao quebrar fluxos atuais de NF-e/NFS-e.
- Nao permitir acesso cross-workshop em emissao, consulta, cancelamento, download, webhook, reconciliacao ou payload.
- Nao executar reemissao automatica quando o estado remoto for incerto.
- Nao apagar legado antes de plano de migracao e backfill aprovado.
- Nao usar NFCom ou DC-e sem feature flag e habilitacao administrativa. A documentacao oficial revalidada em 2026-06-23 identifica ambas como API v2.0.0 e nao mais como beta; remover apenas a sinalizacao beta, preservando o isolamento interno.

## Limites da Fase 0

Permitido:

- Ler codigo, documentacao interna e documentacao oficial.
- Criar ou editar somente arquivos em `docs/fiscal-webmania/`.
- Criar `docs/fiscal-webmania/api/webmania_fiscal_openapi_validated.json`.
- Registrar auditoria, riscos, plano, ADRs e backlog.

Proibido:

- Alterar models, migrations, views, services, forms, templates, permissoes ou comandos.
- Alterar emissao, webhook ou reconciliacao existentes.
- Instalar dependencias.
- Fazer chamada real de emissao Webmania.

## Regra de parada

Ao concluir Fase 0, parar e aguardar aprovacao dos PRDs e da primeira fase de codigo.

## Regra da Fase 3.0

Auditar e planejar NFS-e somente em `docs/fiscal-webmania/**`. Nao criar models, migrations, gateways, telas ou testes. Creditos 2-5, debitos restantes, eventos `112120`/`112140`/`211xxx`, complementar tributaria, CT-e, MDF-e, NFCom e DC-e permanecem adiados.

## Regra da Fase 3.2

Somente operacoes GET de consulta NFS-e, lote RPS e status municipal foram autorizadas. Nenhum caminho pode emitir, cancelar, substituir ou manifestar; cancelamento idempotente permanece reservado a Fase 3.3.
