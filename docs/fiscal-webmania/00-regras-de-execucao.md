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
- Nao usar DC-e sem feature flag, habilitacao administrativa e sinalizacao beta.

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
