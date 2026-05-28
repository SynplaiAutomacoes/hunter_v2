# Decisoes arquiteturais

## ADR-001 - Manter fiscal dentro de `apps.finance`

- Contexto: codigo atual concentra fiscal em `apps.finance`.
- Decisao: evoluir dentro de `apps.finance`, com subdominio fiscal incremental.
- Alternativas: criar app `fiscal` novo.
- Consequencias: menor ruptura e melhor compatibilidade.
- Riscos: app finance permanece grande.
- Status: implementada e validada na Fase 1 para estrutura inicial dentro de `apps.finance`, com dividas preexistentes registradas.
- Fase: 1.

## ADR-002 - Evolucao incremental antes de dominio unificado completo

- Contexto: NF-e/NFS-e atuais funcionam em models legados.
- Decisao: estabilizar idempotencia e webhook antes de migrar tudo para `FiscalDocument`.
- Alternativas: migracao direta.
- Consequencias: menor risco operacional.
- Riscos: periodo de compatibilidade mais longo.
- Status: implementada e validada na Fase 1 para NF-e/NFS-e legados; dominio unificado completo permanece para fase futura.
- Fase: 1/8.

## ADR-003 - Compatibilidade com NF-e/NFS-e atuais

- Decisao: preservar `NfeRequest`, `NfseRequest`, `NfeItem`, `NfseItem`, `NfseBatch` ate backfill aprovado.
- Status: implementada e validada na Fase 1.
- Fase: 1.

## ADR-004 - Idempotencia persistida

- Decisao: criar tentativa persistida por intencao fiscal; cache pode ser apenas otimizacao secundaria.
- Alternativas: manter cache.
- Consequencias: permite `uncertain` e auditoria.
- Status: implementada e validada na Fase 1 com `FiscalEmissionAttempt`.
- Fase: 1.

## ADR-005 - Webhook idempotente por fingerprint

- Decisao: persistir payload bruto e calcular fingerprint unico para evitar efeitos duplicados.
- Status: implementada e validada na Fase 1 com fingerprint persistido em `WebmaniaWebhookEvent`.
- Fase: 1.

## ADR-006 - Reconciliacao nunca emite

- Decisao: reconciliacao so consulta remoto, processa webhooks e recupera downloads.
- Status: implementada e validada na Fase 1 para NF-e/NFS-e e tentativas `uncertain`.
- Fase: 1.

## ADR-007 - Permissoes fiscais especificas

- Decisao: criar matriz fiscal propria, mantendo compatibilidade temporaria com permissoes atuais.
- Status: implementada parcialmente e validada na Fase 1 para corrigir NF-e com fallback legado `nfserequest`.
- Fase: 1/6.

## ADR-008 - Backfill aprovado separadamente

- Decisao: nenhum backfill destrutivo antes da Fase 8.
- Status: proposta.
- Fase: 8.

## ADR-009 - NFS-e municipal guiada por capacidades

- Decisao: consultar e armazenar capacidades do municipio/provedor antes de habilitar acoes condicionais.
- Status: proposta.
- Fase: 3.

## ADR-010 - NFCom e DC-e beta com feature flag

- Decisao: NFCom e DC-e so podem ser implementadas atras de feature flag, com habilitacao administrativa explicita por oficina e sinalizacao visual de API beta.
- Alternativas consideradas: liberar por permissao comum; manter totalmente fora do produto; esconder apenas por menu. Rejeitadas porque APIs beta exigem isolamento operacional e desativacao sem afetar NF-e/NFS-e.
- Consequencias: modelos beta exigirao configuracao por oficina, testes isolados e rollback independente.
- Riscos: mudancas de contrato remoto Webmania podem exigir ajustes antes de producao.
- Status: proposta.
- Fase: 6/7.

## ADR-011 - Fonte de verdade local e remota

- Decisao: local guarda auditoria e estado projetado; remoto Webmania e fonte para autorizacao fiscal final.
- Status: proposta.
- Fase: todas.

## ADR-012 - Nucleo fiscal minimo para eventos e derivados NF-e/NFC-e

- Contexto: Fase 2 precisa representar CC-e, manifestacao, IBS/CBS e documentos derivados sem tratar eventos como notas comuns.
- Decisao: introduzir `FiscalDocument` e `FiscalDocumentEvent` minimos em `apps.finance` na Fase 2.1, preservando `NfeRequest`/`NfeItem` como legado operacional. `FiscalDocumentLink` fica reservado para a Fase 2.2, quando houver documentos derivados reais.
- Alternativas consideradas: criar models especificos de NF-e; adicionar campos/eventos diretamente em `NfeItem`; usar apenas `WebmaniaWebhookEvent`.
- Consequencias: modelagem correta para evento versus documento derivado, suporte a historico e compatibilidade futura com Fase 8, mantendo a Fase 2.1 restrita a CC-e.
- Riscos: exige espelho sob demanda de `NfeItem` legado e cuidado para nao tratar evento como nova nota.
- Status: implementada e validada na Fase 2.1 sem `FiscalDocumentLink`.
- Fase: 2.1/2.2/2.3/2.4.

## ADR-013 - Eventos fiscais nao sao documentos fiscais comuns

- Contexto: CC-e, manifestacao e IBS/CBS possuem protocolo/status e XML/evento, mas nao sao emissao de nota comum nem devem consumir numeracao como NF-e.
- Decisao: persistir eventos em `FiscalDocumentEvent`, vinculados ao documento ou evento original, com tentativa idempotente propria.
- Alternativas consideradas: criar `NfeItem` para cada evento; registrar apenas em logs.
- Consequencias: timeline auditavel, permissao especifica por acao e reconciliacao sem duplicidade.
- Riscos: telas legadas precisarao buscar historico em tabela nova quando exibirem detalhe.
- Status: implementada e validada para CC-e na Fase 2.1.
- Fase: 2.

## ADR-014 - Documentos derivados sao novos documentos com link ao original

- Contexto: devolucao, complementar e ajuste geram notas novas, mas dependem de uma nota original.
- Decisao: persistir cada derivado como `FiscalDocument` proprio e vincular ao original via `FiscalDocumentLink`.
- Alternativas consideradas: atualizar o documento original; guardar derivado apenas no payload.
- Consequencias: evita sobrescrever a nota original, suporta multiplos derivados e auditoria.
- Riscos: exige regras de exibicao para diferenciar original, derivado e evento.
- Status: proposta para Fase 2.2.
- Fase: 2.2.

## ADR-015 - Fase 2 dividida em subfases obrigatorias

- Contexto: NF-e/NFC-e adicional combina eventos simples, documentos derivados, novo modelo NFC-e e eventos tributarios avancados.
- Decisao: executar em 2.1 CC-e, 2.2 derivados, 2.3 NFC-e, 2.4 manifestacao e IBS/CBS.
- Alternativas consideradas: implementar toda Fase 2 em lote.
- Consequencias: menor risco, gates claros, rollback por capacidade.
- Riscos: mais etapas de aprovacao e manutencao documental.
- Status: aprovada documentalmente; Fase 2.1 validada.
- Fase: 2.0.
