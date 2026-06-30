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

## ADR-010 - NFCom e DC-e com feature flag

- Decisao atualizada na Fase 2.6.0: NFCom e DC-e so podem ser implementadas atras de feature flag e habilitacao administrativa explicita por oficina. As APIs oficiais atuais sao v2.0.0 e nao possuem marcador beta.
- Alternativas consideradas: liberar por permissao comum; manter totalmente fora do produto; esconder apenas por menu. Rejeitadas porque o baixo valor imediato e o risco operacional exigem isolamento e desativacao sem afetar NF-e/NFS-e.
- Consequencias: as futuras implementacoes exigirao configuracao por oficina, testes isolados e rollback independente; a UI nao deve rotula-las como beta sem evidencia oficial vigente.
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

## ADR-014 - Documentos derivados e ajustes possuem regras distintas de vinculo

- Contexto: devolucao/estorno, complementar e ajuste geram NF-e novas, mas a documentacao oficial nao exige a mesma referencia para todas. Devolucao exige `chave`; complementar exige `chave` ou `uuid`; ajuste usa body com `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `ambiente` e `cliente`, sem exigir chave/UUID original.
- Decisao: persistir todos como `FiscalDocument` proprio. `FiscalDocumentLink` e obrigatorio para devolucao/estorno e complementar, e opcional para ajuste. Ajuste sem original nao deve ser bloqueado.
- Alternativas consideradas: exigir link para qualquer documento Fase 2.2; atualizar o documento original; guardar derivado apenas no payload.
- Consequencias: evita sobrescrever a nota original, suporta NF-e externa referenciada e permite ajuste avulso compativel com a API.
- Riscos: UI e permissoes precisam deixar claro quando ha nota original local, nota externa ou operacao avulsa.
- Status: implementada e validada para devolucao/estorno na Fase 2.2A; complementar e ajuste permanecem planejados.
- Fase: 2.2.

## ADR-016 - NF-e externa referenciada por devolucao e complemento

- Contexto: devolucao e complemento podem referenciar uma NF-e nao emitida pelo Hunter V2.
- Decisao: permitir chave manual de 44 digitos, validar formato, criar `FiscalDocument` externo minimo como original referenciado, marcar `origin=external`, exigir confirmacao explicita e registrar que a origem nao foi emitida localmente. Nao tratar `/1/nfe/consulta/` como validador garantido de NF-e de outro emissor.
- Alternativas consideradas: bloquear documentos externos; guardar apenas chave no payload.
- Consequencias: amplia cobertura fiscal sem forcar backfill inexistente e preserva auditoria por oficina.
- Riscos: consulta remota pode ser insuficiente; nesses casos a UI deve bloquear ou exigir decisao operacional documentada antes de transmissao.
- Status: implementada e validada para devolucao/estorno na Fase 2.2A; complemento externo permanece planejado para 2.2B. NF-e externa minima nao permite parcial sem XML/importacao validada.
- Fase: 2.2.

## ADR-018 - Idempotencia de devolucao/estorno por documento derivado

- Contexto: duas devolucoes parciais legitimas podem ter os mesmos itens, quantidades e CFOP em momentos diferentes, portanto a identidade nao pode ser somente `original + itens + quantidades + CFOP`.
- Decisao: na Fase 2.2A, criar o `FiscalDocument` derivado antes da chamada remota e associar `FiscalEmissionAttempt` ao derivado. A chave recomendada e `hash(workshop_id, derived_document_id, operation_type, request_generation)`.
- Alternativas consideradas: chave por payload fiscal; chave por nota original e itens.
- Consequencias: cada intencao fiscal persistida transmite uma unica vez e permite devolucoes parciais legitimas independentes.
- Riscos: documentos derivados iniciados e abandonados exigem status local claro e limpeza operacional futura.
- Status: implementada e validada na Fase 2.2A para devolucao/estorno.
- Fase: 2.2A.

## ADR-020 - Nota complementar por subtipos e documento derivado

- Contexto: a Nota Fiscal Complementar pode complementar preco/quantidade, impostos ou documento de adicao/importacao. Misturar todos os cenarios no mesmo formulario/idempotencia aumenta risco fiscal e operacional.
- Decisao: modelar a complementar como `FiscalDocument(purpose="complementary")` com subtipo explicito `complementary_type`: `price_quantity`, `tax` ou `import_addition`. O link `FiscalDocumentLink(role="complements")` e obrigatorio para a NF-e original local ou externa.
- Alternativas consideradas: usar `purpose` separado para cada subtipo; armazenar tudo apenas no payload; tratar complementar como variacao de devolucao.
- Consequencias: simplifica historico e downloads como documento derivado unico, mas requer campo/subtipo persistente ou estrutura equivalente aprovada na implementacao.
- Riscos: payload oficial varia por subtipo e deve ser revalidado imediatamente antes do codigo.
- Status: implementada e validada parcialmente na Fase 2.2B.1 para `price_quantity` local; subtipos `tax` e `import_addition` permanecem propostos e nao implementados.
- Fase: 2.2B.

## ADR-021 - NF-e externa em Nota Complementar

- Contexto: uma complementar pode referenciar NF-e externa por chave, mas a consulta padrao da Webmania nao deve ser tratada como validacao garantida de documento de outro emissor.
- Decisao: permitir NF-e externa minima por chave de 44 digitos e confirmacao explicita. Bloquear `complementary_price_quantity` sem XML/importacao validada dos itens originais. Permitir `complementary_tax` externa somente se aprovado com confirmacao forte, payload auditavel e permissao restrita. Adiar `complementary_import_addition` externa ate haver importacao/validacao adequada.
- Alternativas consideradas: bloquear toda complementar externa; permitir qualquer subtipo por entrada manual; consultar `/1/nfe/consulta/` como validador.
- Consequencias: mantem capacidade fiscal com risco controlado e evita complemento de itens sem ordem fiscal original.
- Riscos: usuarios podem precisar de fluxo futuro de importacao XML para casos reais externos.
- Status: validada na Fase 2.2B.1 para bloquear `complementary_price_quantity` externo minimo; complementar tributaria externa e importacao permanecem propostos e nao implementados.
- Fase: 2.2B.

## ADR-022 - Idempotencia da Nota Complementar

- Contexto: duas complementares legitimas podem ter payload semelhante em momentos diferentes; usar apenas hash do payload/original bloquearia casos validos ou permitiria reenvio duplicado em timeout.
- Decisao: seguir o padrao validado na Fase 2.2A: criar `FiscalDocument` complementar derivado antes do gateway e associar `FiscalEmissionAttempt` com chave `hash(workshop_id, complementary_document_id, operation_type, request_generation)`.
- Alternativas consideradas: idempotencia por original+payload; cache; idempotencia por tela/formulario.
- Consequencias: cada intencao complementar e auditavel, bloqueavel em `uncertain` e reconciliavel sem reemitir.
- Riscos: documentos complementares iniciados e abandonados exigem limpeza/observabilidade futura.
- Status: implementada e validada parcialmente na Fase 2.2B.1 para `operation_type="complementary_price_quantity"`.
- Fase: 2.2B.

## ADR-023 - Complementar de preco/quantidade local antes de complementar tributaria

- Contexto: o payload de complementar de preco/quantidade reaproveita itens fiscais locais conhecidos, enquanto complemento tributario, IBS/CBS e adicao/importacao exigem validacoes fiscais adicionais e UI propria.
- Decisao: implementar primeiro somente `complementary_price_quantity` para NF-e original local autorizada, bloqueando NF-e externa minima e removendo do payload objetos tributarios fora do escopo.
- Alternativas consideradas: liberar complemento externo por chave manual; misturar complemento tributario no mesmo formulario; implementar todo `/1/nfe/complementar/` em lote.
- Consequencias: entrega incremental reduz risco e preserva caminho para `complementary_tax` e `complementary_import_addition` com nova autorizacao.
- Riscos: casos reais de complemento tributario ou externo continuam sem atendimento ate subfase propria.
- Status: validada na Fase 2.2B.1.
- Fase: 2.2B.1.

## ADR-017 - NF-e de credito e debito ficam em Fase 2.5

- Contexto: a familia NF-e inclui finalidades 5 e 6 pelo endpoint `/1/nfe/emissao/`, com `tipo_credito` e `tipo_debito`. A documentacao oficial lista os tipos remotos e artigos Webmania de rejeicao indicam que finalidade credito/debito deve estar relacionada a IBS/CBS.
- Decisao: planejar subfase propria 2.5 para Nota Fiscal de Credito e Nota Fiscal de Debito, usando `FiscalDocument(document_type="nfe", purpose="credit"|"debit")`, campo futuro `fiscal_purpose_type`, `FiscalEmissionAttempt(operation_type="nfe_credit_emission"|"nfe_debit_emission")`, feature flag e habilitacao administrativa por oficina. Codigo funcional deve ser adiado ate suporte IBS/CBS ou aprovacao explicita de subconjunto seguro.
- Alternativas consideradas: incluir credito/debito em 2.2 ou 2.3; implementar como NF-e normal com finalidade diferente; usar apenas hash de payload como idempotencia.
- Consequencias: reduz risco fiscal, evita duplicacao por payload equivalente e preserva separacao de dominio entre NF-e normal, derivados e documentos de credito/debito.
- Riscos: demanda fiscal pode antecipar prioridade; se isso ocorrer, exigir aprovacao explicita e revalidacao tributaria imediata.
- Status: revisada na Fase 2.5.0; funcionalidade nao implementada.
- Fase: 2.5.

## ADR-024 - Nota Fiscal de Ajuste exige regime tributario explicito

- Contexto: a Webmania documenta a Nota Fiscal de Ajuste como recurso para empresas de Lucro Normal ou Presumido, sem representar entrada ou saida de produtos. O Hunter V2 ja possui `WebmaniaCompany.regime_tributario` editavel nos fluxos de empresa/oficina.
- Decisao: reutilizar `WebmaniaCompany.regime_tributario` como fonte local de elegibilidade. Permitir ajuste somente para `lucro_real`, `lucro_normal` ou `lucro_presumido`; bloquear Simples Nacional, MEI, vazio ou desconhecido antes do gateway.
- Alternativas consideradas: inferir pelo tipo de tributacao; liberar quando ausente; criar novo campo duplicado. Rejeitadas por risco fiscal e duplicacao de configuracao.
- Consequencias: oficinas precisam manter a empresa Webmania configurada corretamente antes de emitir ajuste.
- Riscos: dados remotos antigos podem nao preencher `regime_tributario`; nesses casos a emissao fica bloqueada ate ajuste administrativo.
- Status: implementada e validada na Fase 2.2C.
- Fase: 2.2C.

## ADR-025 - Ajuste como documento fiscal avulso com link opcional

- Contexto: a API `/1/nfe/ajuste/` nao exige chave ou UUID de NF-e anterior; apenas cenarios de negocio podem relacionar o ajuste a outro documento.
- Decisao: criar `FiscalDocument(purpose="adjustment")` antes do gateway e permitir `FiscalDocumentLink(role="adjusts")` apenas quando o usuario informar documento relacionado existente.
- Alternativas consideradas: exigir documento original sempre; reaproveitar devolucao/estorno; guardar apenas payload sem documento.
- Consequencias: ajuste avulso permanece auditavel, e relacoes reais podem ser rastreadas sem bloquear casos fiscais validos.
- Riscos: UI deve deixar claro que estorno SC/ES usa devolucao/estorno, nao ajuste.
- Status: implementada e validada na Fase 2.2C.
- Fase: 2.2C.

## ADR-026 - NFC-e nasce em `FiscalDocument`, nao em legado paralelo

- Contexto: NF-e legada ainda usa `NfeRequest`/`NfeItem`, mas NFC-e ainda nao possui fluxo operacional. Criar `NfceRequest` paralelo aumentaria legado sem necessidade.
- Decisao: planejar NFC-e diretamente em `FiscalDocument(document_type="nfce", purpose="normal")`, com `FiscalEmissionAttempt(operation_type="nfce_emission")` e configuracao por `WebmaniaCompany`.
- Alternativas consideradas: reutilizar `NfeRequest` com flag de modelo; criar `NfceRequest`; implementar NFC-e apenas como payload manual sem documento local.
- Consequencias: separa NF-e e NFC-e no dominio, reduz risco de confundir numeracao/status e aproxima a Fase 8.
- Riscos: telas legadas de NF-e nao podem ser reaproveitadas sem filtros rigorosos por `document_type`.
- Status: implementada e validada na Fase 2.3.1 para emissao manual simples.
- Fase: 2.3.

## ADR-027 - Configuracao NFC-e reutiliza `WebmaniaCompany`

- Contexto: o codigo atual ja possui `nfce_serie`, `nfce_numero`, `nfce_id_csc`, `nfce_codigo_csc`, `nfce_numero_dev`, `nfce_id_csc_dev` e `nfce_codigo_csc_dev` em `WebmaniaCompany` e forms de oficina/empresa, mas nao possuia flag explicita de habilitacao nem protecao suficiente de CSC em HTML/formularios.
- Decisao: usar esses campos como gate local de NFC-e, adicionar somente `WebmaniaCompany.nfce_enabled` como flag explicita por oficina, tratar CSC/ID CSC como segredos nos formularios e ampliar os campos CSC para 255 caracteres para suportar criptografia local. Nao criar model/configuracao paralela na primeira subfase funcional.
- Alternativas consideradas: criar `WorkshopNfceConfig`; guardar CSC em settings; inferir configuracao por resposta remota.
- Consequencias: menor ruptura, reaproveitamento da UI/configuracao existente, bloqueio operacional por padrao ate habilitacao administrativa explicita e ausencia de CSC em payload/HTML visivel.
- Riscos: valores antigos em texto puro permanecem legiveis pelo backend ate serem substituidos; os formularios nao os exibem e preservam valor quando campo fica vazio.
- Status: implementada e validada na Fase 2.3.1.
- Fase: 2.3.

## ADR-028 - Cancelamento padrao de NFC-e como evento do documento

- Contexto: a Webmania usa `PUT /1/nfe/cancelar/` para NF-e/NFC-e. Quando `nfce_referenciada` e informado, a API processa cancelamento por substituicao; a Fase 2.3.2 autoriza somente cancelamento padrao.
- Decisao: modelar cancelamento padrao NFC-e como `FiscalDocumentEvent(event_type="cancellation")` associado ao `FiscalDocument(document_type="nfce")`, com `FiscalEmissionAttempt(operation_type="nfce_cancellation")`. O documento original muda para `cancelado` apenas depois de resposta/webhook/reconciliacao valida de cancelamento.
- Alternativas consideradas: alterar diretamente `FiscalDocument` sem evento; criar documento derivado; reaproveitar cancelamento NF-e legado.
- Consequencias: preserva historico auditavel, idempotencia por evento e separacao de substituicao/inutilizacao.
- Riscos: regras estaduais/prazos de cancelamento podem exigir validacoes futuras; nao impor prazo local fixo nesta fase sem validacao oficial aplicavel.
- Status: implementada e validada na Fase 2.3.2.
- Fase: 2.3.2.

## ADR-029 - Inutilizacao NFC-e usa entidade propria de faixa

- Contexto: inutilizacao de numeracao comunica a SEFAZ/Webmania que um numero ou intervalo nao sera utilizado. Diferente de cancelamento, nao existe NFC-e emitida a ser cancelada e, portanto, nao ha documento fiscal original ao qual vincular um evento.
- Decisao: criar `FiscalNumberInutilization` para representar a faixa inutilizada, escopada por oficina, documento `nfce`, ambiente e serie. A idempotencia usara `FiscalEmissionAttempt(operation_type="nfce_inutilization")` associado a essa entidade. A Fase 2.3.3 usa somente `modelo=2`; embora o contrato aceite `modelo=1`, inutilizacao funcional de NF-e fica fora de escopo.
- Alternativas consideradas: modelar como `FiscalDocumentEvent` de uma NFC-e existente; criar `FiscalDocument` ficticio para numeros nao emitidos; implementar inutilizacao NF-e/NFC-e generica no mesmo fluxo.
- Consequencias: a modelagem evita confundir inutilizacao com cancelamento, permite bloquear faixas sobrepostas e preserva compatibilidade com futuras operacoes NF-e sem expor funcionalidade nao autorizada.
- Riscos: a validacao local nao garante que a faixa nao tenha sido usada fora do Hunter; a UI deve exigir confirmacao explicita dessa limitacao e a resposta remota permanece a fonte final.
- Status: implementada e validada na Fase 2.3.3.
- Fase: 2.3.3.

## ADR-015 - Fase 2 dividida em subfases obrigatorias

- Contexto: NF-e/NFC-e adicional combina eventos simples, documentos derivados, novo modelo NFC-e e eventos tributarios avancados.
- Decisao: executar em 2.1 CC-e, 2.2A devolucao/estorno, 2.2B complementar, 2.2C ajuste, 2.3 NFC-e, 2.4 manifestacao e IBS/CBS, 2.5 credito/debito.
- Alternativas consideradas: implementar toda Fase 2 em lote.
- Consequencias: menor risco, gates claros, rollback por capacidade.
- Riscos: mais etapas de aprovacao e manutencao documental.
- Status: aprovada documentalmente; Fase 2.1 validada.
- Fase: 2.0.

## ADR-030 - Modelagem IBS/CBS local em classes fiscais NF-e/NFC-e

- Contexto: NF-e/NFC-e atuais usam `classe_imposto`, mas `TaxClassNfe` local nao guarda IBS/CBS. A Webmania documenta `produtos[].impostos.ibs_cbs` e suporte IBS/CBS em classes fiscais.
- Decisao: evoluir `TaxClassNfe` com estrutura IBS/CBS local auditavel: campos normalizados para situacao/classificacao, campos de regime regular, `ibs_cbs_details` JSON validado para grupos condicionais oficiais, usuario/data de configuracao e sincronizacao `ibs_cbs` no payload da classe fiscal Webmania.
- Alternativas consideradas: depender apenas da classe remota Webmania; inserir JSON livre direto no produto; calcular automaticamente por NCM/regime.
- Consequencias: emissao pode ser bloqueada antes do gateway quando configuracao minima estiver ausente e o payload usado fica auditavel por oficina.
- Riscos: schema IBS/CBS pode mudar com a Reforma Tributaria; por isso preservar payload bruto sanitizado e revalidar docs antes do codigo.
- Status: implementada e validada na Fase 2.4A+B.
- Fase: 2.4A.

## ADR-031 - Fonte de classificacao tributaria IBS/CBS

- Contexto: `situacao_tributaria` e `classificacao_tributaria` dependem de regra fiscal; inferencia automatica por produto/regime sem base confiavel cria risco fiscal.
- Decisao: a fonte local deve ser configuracao administrativa/fiscal explicita por oficina/classe/produto, com auditoria de usuario e timestamp. `WebmaniaCompany.regime_tributario` auxilia validacoes, mas nao determina sozinho a classificacao.
- Alternativas consideradas: inferir por NCM/CFOP; liberar campos vazios; deixar apenas a Webmania rejeitar.
- Consequencias: aumenta trabalho de configuracao, mas evita emissao sabidamente incompleta.
- Riscos: oficinas sem apoio fiscal podem ficar bloqueadas ate configurar corretamente.
- Status: implementada e validada na Fase 2.4A+B para classes NF-e/NFC-e.
- Fase: 2.4A.

## ADR-032 - Bloqueio seguro quando IBS/CBS estiver ausente

- Contexto: a Webmania informa obrigatoriedade IBS/CBS em producao para NF-e/NFC-e com data de emissao >= `05/01/2026`.
- Decisao: bloquear transmissao NF-e/NFC-e normal antes do gateway quando a classe fiscal local nao estiver IBS/CBS-ready. Homologacao tambem exige configuracao valida por padrao; nenhum bypass silencioso foi criado.
- Alternativas consideradas: tentar emitir e tratar rejeicao; permitir bypass silencioso em homologacao; preencher defaults.
- Consequencias: reduz rejeicoes e falsas garantias de conformidade.
- Riscos: pode interromper emissao ate configuracao fiscal ser concluida.
- Status: implementada e validada na Fase 2.4A+B para NF-e normal e NFC-e manual simples.
- Fase: 2.4A/2.4B.

## ADR-033 - Coexistencia de tributos antigos e IBS/CBS na transicao

- Contexto: emissoes normais podem coexistir com tributos antigos durante a transicao, mas finalidades de credito/debito devem usar somente IBS/CBS segundo rejeicao 1001.
- Decisao: permitir coexistencia somente quando a operacao oficial permitir; bloquear preventivamente tributos antigos em credito/debito e em qualquer finalidade que exigir somente IBS/CBS.
- Alternativas consideradas: remover tributos antigos de todos os fluxos; manter todos os tributos em todos os fluxos.
- Consequencias: preserva NF-e/NFC-e normal e reduz risco de rejeicao 1001.
- Riscos: exige validadores por finalidade e operacao.
- Status: validada parcialmente na Fase 2.4A+B para emissao normal por `classe_imposto`; credito/debito seguem bloqueados ate 2.4E.
- Fase: 2.4B/2.4E.

## ADR-034 - Eventos IBS/CBS somente apos base de emissao

- Contexto: eventos IBS/CBS sao operacoes posteriores vinculadas a NF-e/NFC-e, mas nao substituem o preenchimento IBS/CBS na emissao.
- Decisao: implementar eventos e cancelamento IBS/CBS apenas depois de a base de classes/emissao NF-e/NFC-e estar conformada.
- Alternativas consideradas: implementar eventos antes da base; misturar eventos em complemento tributario.
- Consequencias: evita criar eventos sobre documentos base inconsistentes.
- Riscos: adia cobertura de eventos avancados da Reforma Tributaria.
- Status: proposta.
- Fase: 2.4D.

## ADR-035 - Credito/debito bloqueados ate base IBS/CBS aprovada

- Contexto: finalidades 5/6 dependem de IBS/CBS e rejeitam tributos incompatíveis.
- Decisao: manter Nota Fiscal de Credito e Debito sem codigo funcional ate Fase 2.4B validada e subfase 2.4E aprovada.
- Alternativas consideradas: implementar credito/debito com payload NF-e normal; liberar atras de feature flag sem IBS/CBS.
- Consequencias: evita rejeicao 1001 e preserva dominio planejado de `FiscalDocument(purpose=credit|debit)`.
- Riscos: demanda contabil por credito/debito fica adiada.
- Status: proposta.
- Fase: 2.4E/2.5.

## ADR-036 - Derivados IBS/CBS usam snapshot fiscal original

- Contexto: devolucao, estorno e complementar de preco/quantidade derivam de uma NF-e anterior. A classe fiscal atual do produto pode ter sido alterada apos a emissao original, especialmente durante a migracao IBS/CBS.
- Decisao: a fonte primaria para IBS/CBS em derivados deve ser o snapshot fiscal da NF-e original local. `TaxClassNfe` atual pode ser usado apenas como apoio/validacao quando houver confirmacao fiscal explicita e registro auditavel.
- Alternativas consideradas: usar sempre a classe fiscal atual; copiar integralmente o produto original; bloquear todos os derivados ate backfill completo.
- Consequencias: reduz risco de gerar derivado com tributacao diferente da nota original, mas exige preservar ou reconstruir snapshot fiscal antes do gateway.
- Riscos: notas legadas sem snapshot suficiente podem ficar bloqueadas ate importacao/revisao fiscal.
- Status: implementada e validada na Fase 2.4C.1 para devolucao/estorno.
- Fase: 2.4C.

## ADR-037 - NF-e externa minima nao suporta derivados IBS/CBS por item

- Contexto: NF-e externa criada por chave manual nao possui itens, sequenciais fiscais, quantidades nem tributacao original no Hunter.
- Decisao: bloquear devolucao parcial e complementar preco/quantidade com IBS/CBS para NF-e externa minima. Estorno/devolucao total so podem ser avaliados em fase funcional com confirmacao forte, permissao restrita e contrato oficial que dispense detalhe de itens.
- Alternativas consideradas: permitir entrada manual de itens/IBS-CBS; usar `/1/nfe/consulta/` como garantia; bloquear toda NF-e externa.
- Consequencias: evita emissao derivada com base fiscal incompleta e cria backlog claro para importacao/validacao XML.
- Riscos: usuarios com notas externas reais precisarao de fluxo futuro antes de operar parcialmente.
- Status: implementada e validada parcialmente na Fase 2.4C.1 para manter devolucao parcial externa bloqueada; importacao/XML permanece backlog.
- Fase: 2.4C.

## ADR-038 - Complementar preco/quantidade IBS/CBS nao e complementar tributaria

- Contexto: a Fase 2.2B.1 implementou apenas complementar de preco/quantidade e removeu objetos tributarios amplos do payload. A Reforma Tributaria pode exigir IBS/CBS no item, mas isso nao autoriza abrir complemento tributario geral.
- Decisao: na 2.4C.2, IBS/CBS deve ser aplicado somente ao acrescimo de preco/quantidade quando o contrato e o snapshot permitirem. O bloco permitido e `produtos[].impostos.ibs_cbs`, derivado do snapshot fiscal da NF-e original local; `base_calculo` e obrigatorio na complementar conforme contrato oficial e deve estar no snapshot usado. `TaxClassNfe` atual nao e fallback automatico. Complementar tributaria ampla permanece subfase separada e nao implementada.
- Alternativas consideradas: reintroduzir todo objeto `impostos`; manter bloqueio total; misturar preco/quantidade e impostos no mesmo formulario.
- Consequencias: preserva escopo incremental e evita rejeicoes por payload tributario incompatível.
- Riscos: alguns cenarios fiscais podem exigir complementar tributaria antes de preco/quantidade com IBS/CBS; nesses casos deve haver nova aprovacao.
- Status: implementada e validada na Fase 2.4C.2 para complementar de preco/quantidade local.
- Fase: 2.4C.2.

## ADR-039 - Ajuste IBS/CBS exige revalidacao especifica

- Contexto: o fluxo implementado de ajuste usa `/1/nfe/ajuste/` com ICMS/ICMS-ST, cliente, CFOP e regime tributario. O endpoint oficial de eventos IBS/CBS e separado e credito/debito usa finalidades proprias.
- Decisao: nao inserir `produtos[].impostos.ibs_cbs` no ajuste por inferencia. Na Fase 2.4C.3, a revalidacao oficial confirmou que `/1/nfe/ajuste/` documenta `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `valor_icms_st`, `ambiente`, `cliente`, `situacao_tributaria` e informacoes textuais; nao documenta produtos, IBS/CBS, credito/debito ou eventos. Portanto, qualquer tentativa de usar ajuste como credito/debito, evento IBS/CBS, complemento tributario ou estorno deve ser bloqueada antes do gateway.
- Alternativas consideradas: transformar ajuste em emissao normal com IBS/CBS; reutilizar evento IBS/CBS; liberar ajuste sem revisao.
- Consequencias: evita payload fora do contrato e mantem ajuste avulso com link opcional.
- Riscos: pode bloquear casos fiscais de ajuste ate esclarecimento oficial/contabil.
- Status: implementada e validada na Fase 2.4C.3.
- Fase: 2.4C.3.

## ADR-040 - Eventos IBS/CBS sao eventos documentais, nao documentos

- Contexto: a Webmania documenta `POST /1/nfe/evento-ibs-cbs/` para registrar eventos da Reforma Tributaria vinculados a NF-e/NFC-e, com `chave`, `ambiente`, `cod_evento`, `evento` e campos especificos por codigo. Esses eventos nao emitem uma nova NF-e/NFC-e.
- Decisao: modelar eventos IBS/CBS como `FiscalDocumentEvent(event_type="ibs_cbs")` associado ao `FiscalDocument` base. Adicionar campos planejados para `event_code`, `event_sequence`, `event_payload_type`, `remote_event_id/protocol`, `remote_uuid`, payload/resposta sanitizados e XML de evento quando retornado.
- Alternativas consideradas: criar `FiscalDocument` para cada evento; reutilizar ajuste/complementar; tratar como webhook avulso sem persistencia propria.
- Consequencias: preserva historico auditavel do evento sem alterar o status fiscal da NF-e/NFC-e original indevidamente e reaproveita o padrao de CC-e/cancelamento.
- Riscos: eventos de destinatario e eventos com itens exigem validacoes fiscais fortes antes de liberar UI.
- Status: proposta documental na Fase 2.4D.0.
- Fase: 2.4D.

## ADR-041 - Cancelamento de evento IBS/CBS e subfase propria

- Contexto: a Webmania documenta `PUT /1/nfe/evento-ibs-cbs/cancelar/` por UUID do evento autorizado, com ambiente e `url_notificacao` opcionais. Isso cancela o evento, nao o documento fiscal base.
- Decisao: planejar cancelamento de evento como subfase propria, com tentativa `nfe_ibs_cbs_event_cancellation`, associada ao evento IBS/CBS original. A ausencia de UUID remoto ou status incerto do evento original bloqueia cancelamento.

### ADR 2.4D.2 - Cancelamento do evento IBS/CBS 112110 como evento relacionado

- Decisao: implementar cancelamento somente do evento `112110` autorizado como `FiscalDocumentEvent(event_type="ibs_cbs_cancellation")`, associado ao evento original por `related_event`.
- Justificativa: o endpoint oficial cancela um evento por UUID remoto e retorna um novo ciclo de status/log; isso nao representa novo documento fiscal nem cancelamento da NF-e/NFC-e base.
- Payload: enviar somente `uuid`, `ambiente` e `url_notificacao` quando aplicavel. Nao enviar `chave`, `cod_evento`, `evento`, `ibs_cbs`, produtos ou campos de credito/debito.
- Idempotencia: `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")` associado ao evento de cancelamento; constraint condicional impede cancelamentos ativos/incertos duplicados para o mesmo evento original.
- Consequencia: sucesso marca o evento original como `cancelado`, mas preserva o status do `FiscalDocument` base. Demais cancelamentos de eventos IBS/CBS permanecem pendentes de subfase propria.
- Status: implementada na Fase 2.4D.2.

## ADR-042 - Proxima subfase IBS/CBS prioriza 112150 isolado

- Contexto: apos validar `112110` e seu cancelamento, os eventos restantes se dividem entre payload minimo de data, eventos com itens/controle de estoque/transporte, eventos de destinatario e evento ligado a credito/debito.
- Decisao: recomendar `2.4D.3 - Implementar somente evento IBS/CBS 112150`, sem agrupar `112120`, `112130` ou `112140` na mesma subfase.
- Justificativa: `112150` possui menor superficie fiscal porque exige apenas `data_previsao_entrega` alem do envelope, nao depende de credito/debito, nao exige papel destinatario e nao exige `itens[]`.
- Alternativas consideradas: agrupar todos os eventos `1121xx`; implementar destinatario primeiro; generalizar cancelamento para todos os codigos.
- Consequencias: reduz risco e permite testar o primeiro evento com payload especifico antes de abrir eventos com item/estoque. Eventos com itens, destinatario, apuracao externa e credito/debito permanecem bloqueados ate subfases proprias.
- Status: proposta documental na Fase 2.4D.3.0.
- Fase: 2.4D.3.0.

## ADR-043 - Evento IBS/CBS 112150 com payload oficial estreito

- Decisao: implementar `cod_evento=112150` somente para NF-e normal local autorizada, como `FiscalDocumentEvent(event_type="ibs_cbs", event_code="112150")`, sem criar documento fiscal novo e sem alterar status da NF-e base.
- Contrato: a revalidacao oficial confirmou `data_previsao_entrega` no topo do payload, enquanto `evento` e a sequencia numerica. O Hunter nao envia `ibs_cbs`, `itens`, `produtos`, credito/debito ou cancelamento nesse evento.
- Idempotencia: manter `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")` e chave por oficina/documento/tipo/codigo/sequencia. A mesma data de previsao fica bloqueada enquanto houver evento ativo, aprovado ou incerto; datas diferentes podem gerar nova sequencia ate o limite de 20 eventos por documento/tipo.
- Elegibilidade: NFC-e, derivados, ajuste, documentos externos, credito/debito e documentos sem chave ficam bloqueados nesta subfase.
- Cancelamento: cancelamento do `112150` nao foi implementado. O cancelamento validado em 2.4D.2 permanece restrito ao `112110`.
- Status: validada na Fase 2.4D.3.
- Fase: 2.4D.3.

## ADR-044 - Cancelamento do evento IBS/CBS 112150 por UUID

- Decisao: implementar somente cancelamento do evento IBS/CBS `112150` autorizado, usando `PUT /1/nfe/evento-ibs-cbs/cancelar/`, sem criar cancelamento generico para outros codigos.
- Contrato: payload com `uuid` do evento original, `ambiente` quando aplicavel e `url_notificacao` opcional. O Hunter nao envia `chave`, `cod_evento`, `evento`, `data_previsao_entrega`, `ibs_cbs`, produtos, payload de nota ou credito/debito.
- Modelagem: criar `FiscalDocumentEvent(event_type="ibs_cbs_cancellation", event_code="112150", related_event=<evento 112150>)`, com tentativa `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`. Nenhum `FiscalDocument` novo e criado.
- Status: retorno remoto positivo atualiza o evento de cancelamento e marca o evento original como cancelado; o `FiscalDocument` base nao muda status.
- Compatibilidade: cancelamento do `112110` permanece no fluxo validado e intacto.
- Status: validada na Fase 2.4D.4.
- Fase: 2.4D.4.

## ADR-045 - Eventos IBS/CBS 112120, 112130 e 112140 devem ser separados por semantica operacional

- Contexto: a Webmania documenta `112120`, `112130` e `112140` como eventos de emitente por `POST /1/nfe/evento-ibs-cbs/`, todos com `itens[]`, sequencial fiscal do item, `valor_ibs`, `valor_cbs` e campos especificos de `controle_estoque`. Apesar da estrutura comum, cada codigo representa fato fiscal distinto: importacao ALC/ZFM nao convertida em isencao, perecimento/perda/roubo/furto em transporte contratado pelo fornecedor, e fornecimento nao realizado com pagamento antecipado.
- Decisao: nao implementar os tres juntos. Planejar subfases isoladas, com `112130` como primeiro candidato funcional apenas se houver snapshot fiscal confiavel e input operacional/fiscal auditavel. `112120` fica atras de contexto de importacao/ALC-ZFM validado; `112140` fica atras de regra de pagamento antecipado/nota de debito.
- Fonte de dados: usar snapshot fiscal do documento original (`FiscalDocument.request_payload`, `FiscalDocument.response_payload`, `NfeItem.raw_payload` ou `NfeItem.log_payload`) somente quando contiver item fiscal, sequencia e dados IBS/CBS suficientes. `TaxClassNfe` atual nao e fallback automatico para evento de documento ja emitido.
- Bloqueio seguro: documentos externos sem XML/importacao validada, documentos sem snapshot suficiente, itens sem sequencial fiscal, divergencia de itens e valores IBS/CBS ausentes ou incompletos bloqueiam antes do gateway.
- Cancelamento: manter em subfase separada por codigo, usando UUID remoto do evento autorizado. Nao criar cancelamento generico para `112120/112130/112140` junto com a emissao.
- Alternativas consideradas: implementar os tres juntos por compartilharem `itens[]`; criar formulario generico de evento com JSON livre; usar classe fiscal atual para recompor valores. Rejeitadas por risco de payload fiscal incorreto e falta de fonte operacional uniforme.
- Consequencias: menor velocidade de cobertura, mas maior controle sobre fonte fiscal, estoque/transporte e pagamento antecipado.
- Status: proposta documental na Fase 2.4D.5.0.
- Fase: 2.4D.5.

### ADR 2.4D.1 - Primeiro evento IBS/CBS implementado como evento, nao documento

- Decisao: implementar `cod_evento=112110` como `FiscalDocumentEvent(event_type="ibs_cbs")`, associado a um `FiscalDocument` NF-e/NFC-e normal local autorizado.
- Justificativa: evento IBS/CBS altera historico/eventos da nota, mas nao representa nova NF-e/NFC-e nem documento derivado. O documento base nao deve ter status alterado pelo evento.
- Idempotencia: usar `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event")` associado ao documento e ao evento; chave com oficina, documento, tipo, codigo, sequencia e geracao.
- Sequencia: reservar `event_sequence` por documento e tipo de evento IBS/CBS, porque a constraint persistente e `(document, event_type, event_sequence)`.
- Payload: para `112110`, enviar somente envelope oficial confirmado. Nao enviar `ibs_cbs`, produtos, credito/debito, cancelamento ou campos de outros eventos.
- Consequencia: eventos futuros com itens/campos especificos devem ampliar a modelagem de payload de forma controlada; cancelamento de evento permanece em fase propria.
- Alternativas consideradas: implementar cancelamento junto ao primeiro evento; reutilizar cancelamento NF-e/NFC-e; cancelar documento base.
- Consequencias: reduz risco de atualizar/cancelar documento errado e permite idempotencia especifica para cancelamento de evento.
- Riscos: se a SEFAZ/Webmania retornar modelos/codigos diferentes por evento cancelado, o parser deve preservar resposta bruta sanitizada e mapear apenas campos confirmados.
- Status: proposta documental na Fase 2.4D.0.
- Fase: 2.4D.
## ADR - Evento IBS/CBS 112130 isolado

Status: aprovado e validado em 2026-06-18.

Decisao: implementar o evento `112130` como caso especifico, usando `FiscalDocumentEvent` e `FiscalEmissionAttempt` existentes, sem criar model novo, sem `FiscalDocumentLink` e sem cancelamento nesta fase.

Justificativa: o contrato oficial do `112130` exige payload proprio com `itens[]` e `controle_estoque` para perecimento/perda/roubo/furto no transporte contratado pelo fornecedor. Um formulario generico para eventos IBS/CBS aumentaria risco de payload fiscal incorreto e de uso indevido de eventos `112120`, `112140` ou `211xxx`.

Consequencias: o Hunter exige snapshot fiscal original com sequencial fiscal e IBS/CBS por item; `TaxClassNfe` atual nao e fallback automatico para evento de documento ja emitido. Cancelamento do `112130`, eventos `112120/112140`, eventos `211xxx`, credito/debito e complementar tributaria permanecem para fases posteriores.

## ADR - Cancelamento do evento IBS/CBS 112130 por UUID

Status: aprovado e validado em 2026-06-18.

Decisao: implementar somente o cancelamento do evento IBS/CBS `112130` autorizado, usando `PUT /1/nfe/evento-ibs-cbs/cancelar/`, sem criar cancelamento generico para `112120`, `112140` ou eventos `211xxx`.

Contrato: payload restrito a `uuid` do evento original, `ambiente` quando aplicavel e `url_notificacao` opcional. O Hunter nao envia `chave`, `cod_evento`, `evento`, `itens`, `controle_estoque`, `ibs_cbs`, produtos, payload de nota, credito/debito ou dados de documento derivado.

Modelagem: criar `FiscalDocumentEvent(event_type="ibs_cbs_cancellation", event_code="112130", related_event=<evento 112130>)`, com tentativa `FiscalEmissionAttempt(operation_type="nfe_ibs_cbs_event_cancellation")`. Nenhum `FiscalDocument` novo e criado.

Status: retorno remoto positivo atualiza o evento de cancelamento e marca o evento `112130` original como cancelado; o `FiscalDocument` base nao muda status. Timeout preserva evento/tentativa `uncertain` e bloqueia novo cancelamento automatico.

Compatibilidade: cancelamentos validados de `112110` e `112150` permanecem intactos. Eventos `112120`, `112140`, `211xxx`, credito/debito e complementar tributaria continuam bloqueados ate autorizacao propria.

Fase: 2.4D.5.2.

## ADR - Adiar eventos IBS/CBS 112120 e 112140 ate fontes fiscais confiaveis

Status: aprovado documentalmente na Fase 2.4D.6.0.

Contexto: a Webmania documenta `112120` como evento de importacao ALC/ZFM nao convertida em isencao e `112140` como fornecimento nao realizado com pagamento antecipado. Ambos exigem `itens[]`, item sequencial fiscal, valores IBS/CBS e campos especificos de `controle_estoque`.

Decisao: adiar a implementacao funcional de ambos. A infraestrutura tecnica de eventos IBS/CBS ja esta validada, mas o Hunter ainda nao possui fonte fiscal/operacional confiavel para os dados especificos desses eventos.

Justificativa:

- `112120` exige NF-e de importacao referenciada, contexto ALC/ZFM e quantidade sem conversao em isencao. O app de estoque possui importacao/parser XML, mas nao projeta documento fiscal Webmania com snapshot IBS/CBS e regra ALC/ZFM para eventos.
- `112140` exige item da nota de debito de pagamento antecipado e quantidade nao fornecida. Nota de debito/credito IBS/CBS segue bloqueada e o financeiro atual nao cria vinculo fiscal item-pagamento antecipado.

Consequencias: criar primeiro fase preparatoria de importacao XML/snapshot fiscal e/ou fase de credito/debito/pagamento antecipado. Cancelamentos de `112120` e `112140` so podem ser implementados depois da emissao do codigo correspondente estar validada.

Fase: 2.4D.6.0.

## ADR-046 - Adiar credito/debito ate existir fonte fiscal por tipo

- Status: proposto na Fase 2.5.1.0.
- Contexto: a base IBS/CBS e a infraestrutura de documentos/tentativas existem, mas o Hunter nao possui apuracao, evidencia legal e vinculo por item para nenhum dos tipos de credito/debito.
- Decisao: escolher Opcao D e criar Fase 2.5.1P preparatoria. Nenhuma emissao sera liberada apenas por input manual ou por reaproveitamento de movimento financeiro/estoque generico.
- Consequencias: `FiscalDocument` continua sendo o documento futuro; `fiscal_purpose_type` preservara o enum remoto; referencias serao modeladas por documento/item; emissao exigira feature flag global, habilitacao por oficina e permissao fiscal.
- Contrato: credito usa `nfe_referenciada[]`; debito `3`/`4` usa `produtos[].dfe_referenciado`; todos os itens usam exclusivamente `impostos.ibs_cbs` e CFOP na raiz.
- Separacao: notas de credito/debito nao substituem eventos IBS/CBS, inclusive `112140` e `211128`.

## ADR-047 - Base fiscal referenciada e entidade propria sem emissao

- Status: aprovada e implementada na Fase 2.5.1P.
- Decisao: usar `FiscalReferencedBasis` para preparar documento/item, snapshot historico, hipotese e referencias operacionais. Nao reutilizar `FiscalDocumentLink`, pois ainda nao existe documento de credito/debito derivado.
- Snapshot: extrair somente do documento emitido/NfeItem; nunca recalcular por `TaxClassNfe` atual; congelar apos aprovacao.
- Habilitacao: flag auditavel em `WebmaniaCompany` permite preparar bases, nao emitir documentos.
- Operacao remota: nenhuma. Nao criar `FiscalEmissionAttempt`, webhook ou reconciliacao nesta fase.

## ADR-048 - Adiar primeiro tipo ate existir base monetaria por item

- Status: proposto na Fase 2.5.2.0.
- Decisao: Opcao D. `FiscalReferencedBasis` aprovada e necessaria, mas nao suficiente para emissao.
- Motivo: o snapshot atual cobre IBS/CBS e identidade do item, enquanto o contrato exige produto comercial completo e valores fiscais. `FinancialMovement.amount` agregado nao separa principal, multa e juros por item.
- Direcao: criar 2.5.2P sem operacao remota; depois priorizar credito tipo 1. Debito tipo 4 permanece posterior porque exige `dfe_referenciado` por produto.
## ADR-049 - Snapshot monetario/comercial one-to-one

- Status: aceita na Fase 2.5.2P.
- Decisao: criar `FiscalReferencedBasisItem` one-to-one, preservando `FiscalReferencedBasis` como identidade/hipotese e evitando misturar seu ciclo com composicao monetaria.
- Fonte: somente snapshots historicos do documento/NF-e legada; sem cadastro atual, classe fiscal ou valor financeiro agregado como fallback.
- Composicao: multa/juros usa somente multa + juros; demais hipoteses somam principal + multa + juros + outros.
- Consequencia: bases antigas sem item monetario continuam legiveis, mas nao podem ser aprovadas ate receberem uma preparacao valida por fluxo futuro controlado. Nenhum backfill implicito foi criado.
## ADR-050 - Adiar credito tipo 1 ate validar valoracao fiscal

- Status: proposta pela Fase 2.5.3.0, aguardando aprovacao.
- Contexto: a base 2.5.2P congela item e `multa + juros`, mas o contrato oficial consultado nao determina como esses valores ocupam quantidade/subtotal/total nem como formar IBS/CBS do produto de credito.
- Decisao: nao inventar quantidade 1, nao copiar o item original integralmente e nao proporcionalizar IBS/CBS automaticamente. Adiar gateway ate confirmacao fiscal/documental.
- Contrato confirmado: `finalidade=5`, `tipo_credito=1`, `nfe_referenciada[]`, CFOP na raiz, apenas `impostos.ibs_cbs`; sem `dfe_referenciado`.
- Consequencia: proxima fase recomendada `2.5.3P`; futura emissao usa documento derivado, link `credits`, tentativa `nfe_credit_emission`, flag/permissoes proprias e cancelamento posterior pelo fluxo NF-e padrao.
## ADR-051 - Preview fiscal versionado sem transmissao

- Status: aceita na Fase 2.5.3P.
- Decisao: criar `FiscalCreditProductPreview` separado da base. Quantidade, unitario, total e CFOP sao input administrativo explicito; total deve fechar com quantidade x unitario e com multa + juros.
- IBS/CBS: copia sanitizada e imutavel do snapshot aprovado, sem calculo e sem `TaxClassNfe` atual.
- Seguranca: permissoes proprias, revisao por base, imutabilidade apos aprovacao e nenhum objeto remoto.
- Consequencia: a previa reduz ambiguidade tecnica, mas ainda nao autoriza emissao fiscal; cliente/pedido e validacao externa permanecem pendentes.

## ADR - Emissao de credito tipo 1 consome preview aprovada

- Status: aceita na Fase 2.5.4.
- Decisao: produto e IBS/CBS sao copiados exclusivamente da preview imutavel; cliente e pedido reutilizam os builders da NF-e normal vinculada a origem. O documento derivado possui FK para base, one-to-one para preview, link `credits` e tentativa persistida antes do gateway.
- Consequencia: uma nova emissao legitima exige nova preview aprovada. Cancelamento e tipos 2-5 exigem fases proprias.

## ADR - Cancelamento padrao da NF-e de credito tipo 1

- Status: aceita na Fase 2.5.5.
- Decisao: usar `FiscalDocumentEvent(cancellation)` e operacao especifica `nfe_credit_cancellation`, sem reutilizar cancelamento de evento IBS/CBS. O body segue estritamente o contrato oficial: chave/UUID e motivo, sem ambiente ou dados da emissao.
- Consequencia: somente resposta, webhook ou consulta remota com status positivo altera o documento de credito; origem, base e preview permanecem imutaveis. Tipos 2-5 e debito continuam bloqueados.

## ADR - Proximo bloco apos credito tipo 1

**Status:** aprovado na Fase 2.5.6.0 e implementado na Fase 2.5.6P.

**Decisao:** priorizar debito tipo 4, mas iniciar por uma preview fiscal propria sem transmissao. Nao reutilizar nem mutar `FiscalCreditProductPreview`.

**Motivos:**

- o contrato oficial e claro: `finalidade=6`, `tipo_debito=4`, `dfe_referenciado` por produto, CFOP na raiz e somente IBS/CBS;
- `FiscalReferencedBasis` e `FiscalReferencedBasisItem` ja fornecem chave, sequencial e snapshots necessarios;
- a composicao multa + juros ja e auditavel;
- credito e debito sao intencoes fiscais diferentes, portanto precisam de aprovacao e payload congelado independentes;
- uma preview sem gateway reduz o risco de rejeicao 1001 e de transmissao semanticamente incorreta.

**Alternativas rejeitadas agora:** reutilizar preview de credito; emitir debito diretamente; priorizar creditos 2-5; retomar eventos sem fonte local; iniciar NFS-e/CT-e antes das auditorias proprias.

**OpenAPI:** nenhuma alteracao; o schema validado ja representa tipos, referencias, IBS/CBS exclusivo e eventos pendentes.

**Implementacao:** model separado, sem heranca ou mutacao da preview de credito. A flag preparatoria geral foi reutilizada; quatro permissoes de preview de debito foram criadas. Nenhum gateway ou model remoto foi ampliado.

## ADR - Emissao da NF-e de debito tipo 4

**Status:** implementado e validado tecnicamente na Fase 2.5.7.

**Decisao:** a proxima fase pode implementar somente debito tipo 4, a partir de `FiscalDebitProductPreview` aprovada e origem local. Nao enviar `nfe_referenciada`; usar exclusivamente `produtos[].dfe_referenciado` conforme contrato oficial. Criar flag de emissao propria, distinta da flag preparatoria.

**Justificativa:** todos os snapshots fiscais/comerciais/monetarios estao congelados; o payload esta validado; a infraestrutura do credito e reutilizavel; a separacao de preview, documento, operation type, permissoes e flag impede confusao entre credito e debito.

**Cancelamento:** fase posterior pelo cancelamento NF-e padrao, nunca pelo endpoint de cancelamento de evento IBS/CBS.

**Auto-revisao:** a emissao exige nota original local normal e aprovada, chave coerente, snapshots comercial/monetario, composicao multa+juros e produto/IBS-CBS identicos aos valores congelados. O webhook verifica ambiguidade global antes de atualizar o debito.

## ADR - Cancelamento da NF-e de debito tipo 4

**Status:** implementado e validado tecnicamente na Fase 2.5.8.

**Decisao:** usar `FiscalDocumentEvent(event_type="cancellation", event_payload_type="nfe_debit_cancellation")` e operation type especifico `nfe_debit_cancellation`. O body segue o contrato NF-e padrao com identificador e motivo, sem ambiente ou campos de emissao. O documento original, base e preview sao imutaveis.

**Resolucao remota:** webhook de cancelamento de debito e avaliado antes do documento emitido, mas somente e aceito quando houver um unico evento candidato em todo o conjunto de cancelamentos NF-e. A reconciliacao consulta o documento e nunca reenvia o cancelamento.

## ADR - Proximo bloco apos credito/debito de multa e juros

**Status:** proposto na Fase 2.6.0.

**Decisao:** priorizar `Fase 3.0 - Auditoria e Planejamento Tecnico da NFS-e Expandida`, sem codigo funcional, antes de continuar os tipos restantes de credito/debito ou eventos IBS/CBS pendentes.

**Justificativa:** NFS-e possui alto valor direto para oficinas e fluxo operacional legado reutilizavel, mas exige decisao explicita sobre capacidades municipais, Padrao Nacional, ISS/IBS-CBS, RPS/lotes, substituicao e manifestacao. Os demais candidatos dependem de ZFM/ALC, sucessao, estoque fiscal, apuracao externa, pagamento antecipado ou fontes do destinatario ainda inexistentes.

**Rollout:** a auditoria deve propor flags/capacidades por oficina e municipio, mantendo compatibilidade legada. Nenhum model, migration ou gateway e autorizado pela decisao documental.

**NFCom/DC-e:** a classificacao oficial atual foi corrigida para API v2.0.0. Feature flag e habilitacao administrativa permanecem como politica interna Hunter devido ao baixo valor imediato e ao risco de rollout, nao por status beta oficial.

## ADR - Evolucao gradual da NFS-e legada

**Status:** proposto na Fase 3.0.

**Decisao:** preservar `NfseRequest`, `NfseBatch` e `NfseItem` como fonte operacional do fluxo por OS. Criar projecao `FiscalDocument(nfse)` somente sob demanda para novas operacoes; emissao manual futura nasce no dominio fiscal novo. Nao executar backfill em massa na estabilizacao.

**Capacidades:** usar entidade `NfseMunicipalCapability` separada de `WebmaniaCompany`, porque status, versao, ambientes, autenticacao, emissao, funcoes, servicos e parametros variam por municipio/provedor e no tempo.

**Ordem:** 3.1 estabiliza idempotencia/webhook/capacidades; 3.2 amplia consulta; 3.3 corrige cancelamento; 3.4 substituicao; 3.5.0 reavalia o proximo bloco; 3.6.0 planeja manifestacao; 3.6.x implementa manifestacao se aprovada; rollout/emissao manual e downloads/observabilidade ficam em fases posteriores.

**Consequencias:** compatibilidade legada e flags por oficina sao obrigatorias. Nenhuma nova operacao herda permissao legada automaticamente. O gateway continua sendo Webmania; documentos nacionais definem semantica, nao uma integracao paralela.

**Status da decisao em 2026-06-23:** aceita e implementada na Fase 3.1. A primeira versao usa snapshot administrativo local por oficina/empresa/municipio e compatibilidade legada explicita; sincronizacao automatica e TTL remoto permanecem para fase futura. O timestamp remoto canonico foi adicionado ao item/lote sem backfill.

## ADR - Consultas NFS-e nao usam tentativa de emissao

**Decisao:** consultas da Fase 3.2 sao GETs repetiveis e nao recebem `FiscalEmissionAttempt`. A trilha usa `last_reconciled_at`, `last_update_source`, payload sanitizado e erro. Isso evita aplicar semantica `uncertain` de transmissao a uma leitura: timeout de GET nao prova alteracao fiscal remota.

**Lote:** o UUID do `lote_rps` usa o mesmo endpoint de consulta. Batch e `info_nfse` sao aplicados transacionalmente; nao foi inventada consulta por numero RPS.

**Status municipal:** resposta remota e snapshot informativo. Somente acao administrativa futura pode alterar flags aprovadas.
## ADR - cancelamento NFS-e legado sem `FiscalDocument`

**Decisao:** manter a base operacional legada e criar `NfseCancellation` como trilha auditavel, referenciada pela tentativa via `request_model/request_id`.

**Motivo:** a Fase 3.3 nao autoriza projecao generalizada `FiscalDocument(nfse)` nem backfill. A constraint parcial e o bloqueio pessimista do item resolvem concorrencia sem acoplar o legado ao dominio novo. `nfse_cancellation` permanece separado de emissao e de qualquer futura substituicao.

## ADR - preview obrigatoria antes da substituicao NFS-e

**Contexto:** `POST /2/nfse/substituir` cria nova NFS-e a partir de `rps`. A documentacao oficial apresenta inconsistencia entre o texto (`uuid`/`motivo`) e a tabela/exemplo (`ambiente`, `codigo_verificacao`, `motivo`, `rps`). O Hunter pode reconstruir RPS usando dados atuais, mas eles sao mutaveis.

**Decisao:** adotar a Opcao B. Criar primeiro `NfseSubstitutionPreview` imutavel e aprovada, sem transmissao. A fase funcional futura usa somente preview aprovada, capability municipal e feature flag. `NfseSubstitution` representa a operacao e liga dois `NfseItem`; nao e cancelamento e nao requer `FiscalDocument(nfse)` generalizado.

**Consequencias:** evita substituir com tomador, servico, valor ou tributacao alterados silenciosamente; permite auditoria e testes do novo RPS. O custo e uma fase preparatoria adicional e a necessidade de nova confirmacao contratual sobre a identificacao da original antes do POST funcional.

**Implementacao 3.4P:** entidade propria no legado NFS-e, sem `FiscalDocument(nfse)` e sem tentativa remota. O snapshot XML preserva URL, identificadores e payload remoto sanitizado disponivel; o Hunter nao baixa nem reconstrói conteudo XML durante a preparacao. Tomador, servico, valores e tributacao do novo RPS sao input administrativo explicito.

**Implementacao 3.4.1:** seguir tabela/exemplo oficial e nao a frase contraditoria sobre `uuid`. A operacao remota usa `NfseSubstitution` + tentativa; retorno sincrono aprovado exige `nfse_substituida.uuid` igual a original. Webhook por UUID substituto pode concluir uma intencao previamente identificada. XML original nunca e sobrescrito; estado `substituido` possui rank terminal equivalente a cancelado.

## ADR - Proximo bloco apos cancelamento e substituicao NFS-e

**Status:** proposto na Fase 3.5.0.

**Decisao:** priorizar manifestacao de NFS-e Padrao Nacional em fase propria, antes de emissao manual nova, NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes ou complementar tributaria.

**Justificativa:** manifestacao trabalha sobre NFS-e existente e pode reutilizar capacidade municipal, tentativa persistida, payload sanitizado, webhook e reconciliacao consultiva. Ela nao cria RPS, nao consome numeracao, nao altera XML original e nao exige dominio novo de transporte, estoque, sucessao, ZFM/ALC, pagamento antecipado ou apuracao fiscal. O valor de produto e menor que emissao manual nova, mas o risco e o tamanho da fase sao muito menores.

**Restricoes:** aplicar apenas quando `NfseMunicipalCapability.manifestation_enabled` e a configuracao administrativa da oficina permitirem. Timeout deve permanecer `uncertain`, sem retry automatico. Webhook ambiguo ou retorno sem identificador suficiente deve ficar pendente para reconciliacao/acao administrativa, sem inferir sucesso.

**OpenAPI:** nenhuma alteracao nesta fase; o endpoint `/2/nfse/manifestar` ja esta representado no OpenAPI validado.

## ADR - Manifestacao NFS-e sem preview previa

**Status:** proposto na Fase 3.6.0.

**Decisao:** implementar futuramente manifestacao NFS-e como `NfseManifestation` proprio vinculado a `NfseItem`, sem criar preview previa e sem criar `FiscalDocument(nfse)`. A intencao congelada e a tentativa `nfse_manifestation` sao suficientes para auditoria/idempotencia.

**Justificativa:** diferentemente da substituicao, manifestacao nao reconstrói RPS nem cria nova NFS-e. O contrato oficial e pequeno: ambiente, identificador, papel, evento e campos condicionais de rejeicao. Uma preview adicionaria friccao sem reduzir risco material, desde que rejeicao tenha confirmacao explicita e payload congelado.

**Restricoes:** somente Padrao Nacional confirmado; bloquear municipal legado, NFS-e cancelada, substituida, incerta ou sem identificador suficiente. Desfazer/cancelar manifestacao nao sera implementado sem endpoint oficial claro.

**Implementacao 3.6.1:** `NfseManifestation` proprio, sem preview e sem `FiscalDocument(nfse)`. O gateway transmite apenas o contrato oficial de manifestacao; cancelamento, substituicao e XML original da NFS-e permanecem preservados.

## ADR - Proximo bloco apos manifestacao NFS-e

**Status:** proposto na Fase 3.7.0.

**Decisao:** escolher a Opcao F: fase preparatoria para emissao manual nova de NFS-e, antes de qualquer transmissao por `POST /2/nfse/emissao`.

**Justificativa:** emissao manual nova e o proximo bloco com maior valor de produto e maior reaproveitamento da infraestrutura NFS-e validada. Porem, diferentemente da manifestacao, ela cria documento fiscal novo e pode consumir RPS/numeracao. A base local existe apenas parcialmente e permanece acoplada a OS/cadastros mutaveis. A preview imutavel reduz risco fiscal ao congelar tomador, servico, valores, ISS, IBS/CBS, ambiente, municipio/capability e payload planejado antes da fase funcional.

## ADR - Fase 3.7.1: emissao manual somente a partir de preview aprovada

**Decisao:** implementar `NfseManualEmission` como intencao remota propria e transmitir somente o `request_payload` aprovado da `NfseManualEmissionPreview`.

**Consequencias:** `NfseItem` pode existir sem OS legada quando originado por emissao manual. Nao sera criado `FiscalDocument(nfse)` nesta fase. Cancelamento, substituicao e manifestacao da NFS-e manual exigem fases futuras proprias. A diferenca entre exemplo com `rps` objeto e contrato local com `rps` lista foi resolvida preservando o payload aprovado, sem conversao.

**Alternativas rejeitadas agora:** importacao de NFS-e recebida sem XML/papel fiscal seguro; CT-e/MDF-e/NFCom/DC-e sem dominio local; eventos IBS/CBS `112120`, `112140` e `211xxx` sem fontes especificas; creditos/debitos restantes sem evidencias fiscais; complementar tributaria sem auditoria propria.

**Consequencia:** a proxima fase recomendada nao cria `FiscalEmissionAttempt`, nao chama Webmania e nao cria NFS-e emitida. Uma fase funcional posterior devera consumir somente preview aprovada, com tentativa persistida antes do POST, `uncertain` bloqueante, webhook seguro e reconciliacao consultiva.
## ADR - Fase 3.8.0: proximo ciclo apos emissao manual NFS-e

Data: 2026-06-28.

Contexto: a Fase 3.7.1 foi validada no checkpoint `2cb35206`, criando `NfseManualEmission`, tentativa `nfse_manual_emission`, emissao exclusiva por preview aprovada e `NfseItem` somente apos confirmacao remota valida.

Decisao: priorizar **Fase 3.8.1 - Cancelamento da NFS-e Manual Nova** como extensao segura do cancelamento NFS-e existente.

Justificativa:

- contrato oficial do cancelamento (`PUT /2/nfse/cancelar` com `uuid` e `motivo`) e o mesmo ja usado pelo fluxo validado;
- a fonte local e confiavel quando `NfseManualEmission.nfse_item` aponta para `NfseItem` autorizado com UUID;
- reaproveita `NfseCancellation`, `FiscalEmissionAttempt(operation_type="nfse_cancellation")`, webhook e reconciliacao consultiva;
- fecha o primeiro ciclo operacional da NFS-e manual sem criar nova NFS-e, sem novo RPS e sem depender de importacao ou `FiscalDocument(nfse)`;
- reduz risco frente a substituicao e manifestacao, que exigem respectivamente novo RPS/substituta ou Padrao Nacional/papel fiscal.

Consequencia: substituicao e manifestacao da NFS-e manual permanecem fases separadas; preview e emissao manual sao imutaveis e nao devem ser alteradas pelo cancelamento.

Implementacao 3.8.1: a decisao foi mantida. Nao foi criado novo modelo; `NfseCancellation` passou a aceitar `request` opcional para origem manual, mantendo `item` obrigatorio e a constraint de uma intencao ativa por NFS-e. A operacao de idempotencia continuou `nfse_cancellation`, porque a separacao por `NfseItem` e oficina e suficiente e evita bifurcar o contrato remoto por origem.

## ADR - Fase 3.9.0: proximo bloco apos ciclo minimo da NFS-e manual

Data: 2026-06-28.

Contexto: a Fase 3.8.1 foi validada no checkpoint `29f3f3a9`, completando o ciclo minimo `preview -> emissao -> cancelamento` da NFS-e manual. A origem manual usa `NfseManualEmissionPreview`, `NfseManualEmission`, `NfseItem` autorizado e `NfseCancellation` com `request` opcional. O contrato de cancelamento permanece `{uuid, motivo}`, XML original preservado e XML de cancelamento separado.

Decisao: priorizar **substituicao da NFS-e manual** como extensao segura do fluxo atual de substituicao NFS-e.

Justificativa:

- `NfseSubstitutionPreview` e `NfseSubstitution` ja existem e ja foram validados para NFS-e local;
- `POST /2/nfse/substituir` ja esta representado no OpenAPI validado;
- a NFS-e manual autorizada possui `NfseItem`, UUID e, quando elegivel, `codigo_verificacao` para identificar a original;
- a preview imutavel ja mitiga o maior risco da substituicao: novo RPS construido a partir de dados mutaveis;
- o ajuste esperado e de elegibilidade/origem, sem criar gateway paralelo, sem `FiscalDocument(nfse)` e sem abrir NFS-e recebida/importada.

Alternativas adiadas: manifestacao da NFS-e manual, porque depende de Padrao Nacional e papel fiscal; NFS-e recebida/importada, porque falta dominio de XML/identidade/tenancy; NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria, por maior dependencia externa e risco fiscal.

Consequencia: a proxima fase funcional deve ser pequena e escolher explicitamente extensao do fluxo atual, nao fluxo paralelo especifico de `NfseManualEmission`.

## ADR - Fase 3.9.1: substituicao manual como extensao do fluxo existente

**Status:** implementado e validado tecnicamente em 2026-06-29.

**Decisao:** nao criar modelo ou fluxo paralelo para substituicao da NFS-e manual. A origem manual passa a ser apenas mais uma origem elegivel de `NfseItem` original para `NfseSubstitutionPreview` e `NfseSubstitution`.

**Justificativa:** o contrato remoto e identico ao fluxo ja validado de substituicao NFS-e. A diferenca relevante e local: a original pode ter `request_id=None`, desde que exista `NfseManualEmission` vinculada e confirmada. A capability vem da preview de emissao manual, e nao de `NfseRequest`.

**Consequencias:** a substituta manual tambem pode nascer sem `NfseRequest`/OS; isso e intencional quando a original manual nao possui esses vinculos. `FiscalDocument(nfse)` permanece adiado. Manifestacao manual e NFS-e recebida/importada permanecem fases futuras separadas.

## ADR - Fase 3.10.0: adiar manifestacao da NFS-e manual

**Status:** validada documentalmente em 2026-06-29 no checkpoint `8d5c7192`.

**Decisao:** adiar a manifestacao da NFS-e manual. Nao implementar `Fase 3.10.1` agora.

**Justificativa:** `NfseManifestation` e `operation_type="nfse_manifestation"` ja existem e o endpoint oficial `POST /2/nfse/manifestar` continua claro para Padrao Nacional. O problema e o papel fiscal: a documentacao oficial descreve manifestacao por tomador ou intermediario, enquanto a NFS-e manual emitida pelo Hunter normalmente e documento da propria oficina prestadora. Sem criterio local para provar que a oficina atua como tomadora/intermediaria, a extensao funcional abriria risco fiscal.

**Alternativas avaliadas:** implementar como extensao segura de `NfseManifestation`; criar fluxo separado manual; preparar NFS-e recebida/importada. A primeira e tecnicamente possivel, mas fiscalmente ambigua. A segunda foi rejeitada por duplicar fluxo. A terceira permanece recomendada como preparacao posterior, porque documentos recebidos de terceiros tendem a se alinhar melhor ao papel de manifestador.

**Consequencias:** manifestacao da NFS-e manual continua pendente; NFS-e recebida/importada deve ser planejada antes de manifestacao de terceiros; nenhuma alteracao em OpenAPI ou codigo funcional foi feita.

## ADR - Fase 3.11.0: NFS-e recebida por XML antes de manifestacao

**Status:** em planejamento documental em 2026-06-29.

**Decisao:** escolher Opcao A, criar em fase futura um registro local de NFS-e recebida/importada baseado em XML validado (`NfseReceivedDocument` ou nome equivalente), antes de qualquer manifestacao funcional.

**Justificativa:** a manifestacao faz mais sentido para documentos em que a oficina e tomadora ou intermediaria. A forma mais defensavel de provar esse papel e validar o XML recebido, extrair CNPJs, municipio, ambiente, UUID/chave/codigo e congelar hash/snapshot. A consulta Webmania por identificador e util como complemento, mas a documentacao revalidada nao confirma endpoint de importacao que substitua XML e papel fiscal.

**Consequencias:** a proxima implementacao, se aprovada, deve ser preparatoria e local; nao deve criar `NfseItem`, `FiscalDocument(nfse)` nem executar `POST /2/nfse/manifestar`. Manifestacao futura dependera de documento recebido validado, papel `taker` ou `intermediary`, Padrao Nacional e capability ativa.

## ADR - Fase 3.12.0: manifestacao de NFS-e recebida por extensao segura

**Status:** em planejamento documental em 2026-06-29.

**Contexto:** a Fase 3.11.1 foi validada no checkpoint `b25ad698`, criando `NfseReceivedDocument` por XML validado. O documento recebido agora possui XML snapshot/hash, UUID/identificador/codigo, CNPJs extraidos, role fiscal, oficina, empresa, status de validacao e protecao por permissoes. A importacao nao cria artefatos de emissao nem chama Webmania.

**Decisao:** escolher Opcao A e planejar `3.12.1 - Manifestacao de NFS-e Recebida` como extensao segura de `NfseManifestation` existente, nao como fluxo paralelo.

**Justificativa:** a manifestacao oficial e por tomador ou intermediario no Padrao Nacional. Diferente da NFS-e manual emitida pela propria oficina, a NFS-e recebida validada por XML pode provar que a oficina atua como tomadora ou intermediaria. O fluxo existente de `NfseManifestation` ja resolve payload, tentativa, idempotencia, timeout, webhook e reconciliacao; duplicar isso criaria risco e manutencao desnecessaria.

**Consequencias:** a fase funcional futura deve adaptar a modelagem para vincular uma manifestacao a exatamente uma origem: `nfse_item` ou `received_document`. Deve bloquear provider, unknown, multiple, sem UUID, sem Padrao Nacional, status terminal/incerto e cross-workshop. Nao criar `NfseItem`, nao criar `FiscalDocument(nfse)`, nao alterar XML recebido e nao reusar permissoes de importacao como permissao de manifestacao.

**OpenAPI:** nenhuma alteracao. O contrato oficial ja esta representado para manifestacao, webhook, consulta e status.

## ADR - Fase 3.13.0: proximo bloco apos fechamento NFS-e

**Status:** em planejamento documental em 2026-06-29.

**Contexto:** a Fase 3.12.1 foi validada no checkpoint `6cc3a788`, fechando os principais fluxos NFS-e atuais: cancelamento legado, substituicao, manifestacao Padrao Nacional, preview/emissao/cancelamento/substituicao manual, registro de NFS-e recebida por XML e manifestacao de NFS-e recebida. A manifestacao recebida estendeu `NfseManifestation` para `NfseReceivedDocument` sem criar `NfseItem` ou `FiscalDocument(nfse)`.

**Decisao:** escolher consulta/reconciliacao auxiliar de `NfseReceivedDocument` como proxima recomendacao, desde que seja estritamente consultiva.

**Justificativa:** o documento recebido validado por XML agora fornece fonte local suficiente para consulta segura: oficina, empresa, UUID/identificador, XML/hash, CNPJs e papel fiscal. `GET /2/nfse/consulta/{identifier}` e `/2/nfse/status` podem reduzir incerteza operacional e apoiar manifestacao/reconciliacao, reaproveitando infraestrutura NFS-e existente. Importacao em lote tem valor, mas exige UX e processamento parcial; e-mail/ERP e novas familias abrem dependencias externas maiores; eventos IBS/CBS, creditos/debitos e complementar tributaria continuam dependentes de fontes fiscais especificas.

**Consequencias:** a futura consulta nao pode criar NFS-e recebida sem XML, substituir XML validado, recalcular papel fiscal, criar manifestacao automaticamente, criar `NfseItem` ou criar `FiscalDocument(nfse)`. Manifestacao manual permanece adiada. NFS-e expandida ampla, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes e complementar tributaria permanecem fora do escopo imediato.

**OpenAPI:** nenhuma alteracao. O schema validado atual permanece suficiente para consulta, status, manifestacao e webhooks.

## ADR - Fase 3.13.1: consulta recebida como snapshot auxiliar

**Status:** implementado e validado tecnicamente em 2026-06-29.

**Decisao:** representar a consulta remota de NFS-e recebida em entidade propria (`NfseReceivedDocumentConsultation`), vinculada ao `NfseReceivedDocument`, sem promover a resposta Webmania a fonte primaria.

**Justificativa:** o XML validado continua sendo a evidencia local principal de identidade, papel fiscal e dados tributarios. A consulta remota e util para reconciliacao operacional, mas pode divergir do XML e nao deve sobrescrever hash, snapshot, UUID, CNPJs, municipio, ambiente ou valor extraidos.

**Consequencias:** a consulta usa somente GET, depende de feature flag e permissao propria, registra divergencias auditaveis e nao cria `NfseItem`, `FiscalDocument(nfse)`, `FiscalEmissionAttempt` ou manifestacao automatica. Importacao por consulta, lote e integracoes externas continuam fases futuras.

## ADR - Fase 3.14.0: proximo bloco apos NFS-e recebida completa

**Status:** em planejamento documental em 2026-06-29.

**Contexto:** a Fase 3.13.1 foi validada no checkpoint `01f0924d`. O bloco NFS-e recebida possui registro local por XML, manifestacao segura e consulta/reconciliacao GET-only. A consulta implementada preserva XML/hash/dados extraidos, registra divergencias em `NfseReceivedDocumentConsultation` e nao cria manifestacao automatica, `NfseItem` ou `FiscalDocument(nfse)`.

**Decisao:** escolher importacao em lote de XML de NFS-e recebida como proxima fase funcional pequena.

**Justificativa:** o lote XML reaproveita a fonte local mais confiavel ja validada, aumenta valor operacional para oficinas com muitos documentos recebidos e evita dependencia de consulta Webmania como origem. E menor e mais testavel que e-mail/ERP, NFS-e expandida ampla, CT-e/MDF-e/NFCom/DC-e, eventos IBS/CBS pendentes, creditos/debitos restantes ou complementar tributaria.

**Consequencias:** a proxima fase deve ser XML-only, com relatorio por arquivo, importacao parcial segura, bloqueio de duplicidade e cross-workshop. Consulta Webmania continua apenas apoio consultivo; e-mail/ERP fica posterior ao lote local; manifestacao manual e demais dominios fiscais permanecem adiados.

## ADR - Fase 3.14.1: lote persistido e importacao parcial

**Status:** implementado e validado tecnicamente em 2026-06-29.

**Decisao:** persistir lote e itens por arquivo em `NfseReceivedImportBatch` e `NfseReceivedImportBatchItem`, em vez de relatorio transiente.

**Justificativa:** o lote e uma operacao fiscal auditavel com importacao parcial. Persistir resultados por arquivo permite explicar duplicidades, XMLs invalidos, CNPJ/oficina divergente e documentos criados sem depender de estado de tela.

**Consequencias:** a importacao continua usando `NfseReceivedDocument` como documento fiscal primario, reaproveita o parser/importador unitario e nao cria Webmania calls, manifestacoes, `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt`.

## ADR - Fase 3.15.0: proximo bloco apos consolidacao recebida

**Status:** validada documentalmente em 2026-06-29 no checkpoint `4815728b`.

**Contexto:** a Fase 3.14.1 foi validada no checkpoint `b53e862b`, encerrando o ciclo recebido com upload unitario XML, manifestacao, consulta GET-only e lote XML auditavel.

**Decisao:** escolher planejamento de integracao e-mail/ERP para XML de NFS-e como proxima fase, somente preparatoria/documental.

**Justificativa:** o dominio fiscal recebido ja esta pronto para processar XMLs locais. A lacuna agora e a origem externa desses XMLs. Implementar conector real sem fase preparatoria criaria riscos de credenciais, anexos errados, duplicidade, fila e importacao silenciosa.

**Consequencias:** nenhuma integracao real deve ser implementada na proxima fase documental. Consulta Webmania ampliada, manifestacao manual, NFS-e expandida, CT-e, MDF-e, NFCom, DC-e, eventos IBS/CBS pendentes, creditos/debitos e complementar tributaria permanecem adiados.

## ADR - Fase 3.15.1: caixa de entrada externa antes de conectores reais

**Status:** em planejamento documental em 2026-06-29.

**Contexto:** a Fase 3.15.0 foi validada documentalmente no checkpoint `4815728b` e autorizou apenas planejamento preparatorio de integracao e-mail/ERP para XML de NFS-e. O lote XML local ja existe e e a fronteira fiscal segura.

**Decisao:** escolher **Opcao A - Implementar caixa de entrada externa de XML** como recomendacao para uma futura fase funcional, com revisao humana antes do lote. Nao implementar conector real nesta fase.

**Justificativa:** a caixa de entrada separa origem operacional de importacao fiscal. E-mail, ERP, pasta externa ou webhook podem fornecer XML candidato, mas o documento recebido so nasce pelo pipeline validado de XML/lote. Isso reduz risco de credenciais, spoofing, anexo adulterado, documento de outra oficina e importacao silenciosa.

**Consequencias:** a proxima implementacao, se aprovada, deve criar dominio intermediario auditavel, permissoes e flags proprias, sem chamar Webmania, sem manifestar, sem criar `NfseItem`, sem criar `FiscalDocument(nfse)` e sem criar `FiscalEmissionAttempt`. Conectores reais IMAP/Gmail/Microsoft/ERP continuam posteriores.

**OpenAPI:** nenhuma alteracao. A decisao e local e nao envolve endpoint Webmania novo.

## ADR - Fase 3.15.2: inbox local/manual antes de conectores externos

**Status:** em implementacao controlada em 2026-06-30.

**Contexto:** a Fase 3.15.1 foi validada documentalmente no checkpoint `5882cd4e`. A decisao aprovada foi implementar caixa de entrada local para XMLs candidatos, sem conector real.

**Decisao:** implementar `NfseExternalXmlInbox` e `NfseExternalXmlInboxItem` como camada operacional intermediaria. Itens podem ser pendentes, invalidos, duplicados, aprovados, descartados, processados ou erro. Somente itens aprovados sao enviados ao lote XML validado.

**Justificativa:** a inbox permite capturar XMLs candidatos e auditar origem manual sem criar caminho fiscal paralelo. O lote continua dono da criacao de `NfseReceivedDocument`.

**Consequencias:** a implementacao adiciona flag e permissoes proprias. Nenhum conector real, Webmania automatica, manifestacao automatica, `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt` e criado pela inbox.

## ADR - Fase 3.16.0: ampliar inbox local antes de conectores reais

**Status:** em planejamento documental em 2026-06-30.

**Contexto:** a Fase 3.15.2 foi validada no checkpoint `517d25b8`. O bloco NFS-e recebida ja possui XML unitario, manifestacao recebida, consulta GET-only, lote XML e inbox local/manual.

**Decisao:** escolher **Opcao D - Ampliar inbox local** como proxima recomendacao funcional pequena.

**Justificativa:** conectores reais de e-mail/ERP/pasta/webhook ainda dependem de autenticacao, segregacao por oficina, contratos externos, idempotencia por origem e observabilidade. A inbox local ja tem fonte e dominio implementados; melhorar filtros, busca, auditoria, relatorio e acoes controladas aumenta valor com risco menor.

**Consequencias:** a proxima fase deve continuar local, sem conector real, sem Webmania automatica, sem manifestacao automatica e sem criar documento fiscal fora do lote XML. NFS-e expandida, CT-e/MDF-e/NFCom/DC-e, IBS/CBS pendentes, creditos/debitos e complementar tributaria permanecem adiados.

**OpenAPI:** nenhuma alteracao.

## ADR - Fase 3.16.1: operacao em massa e relatorio local da inbox XML

**Status:** em implementacao tecnica em 2026-06-30.

**Contexto:** a Fase 3.16.0 foi validada documentalmente no checkpoint `267fc601` e decidiu ampliar a inbox local antes de conectores reais.

**Decisao:** implementar filtros, busca, CSV e acoes em massa sobre `NfseExternalXmlInbox`/`NfseExternalXmlInboxItem`, mantendo `NfseReceivedImportBatch` como unica fronteira de criacao de `NfseReceivedDocument`.

**Justificativa:** a operacao local reduz trabalho manual sem introduzir credenciais externas, automacao fiscal ou fonte remota. CSV sem XML bruto atende relatorio operacional sem expor payload fiscal. Acoes em massa reaproveitam validacoes existentes e registram usuario/data por item.

**Consequencias:** foram criadas apenas permissoes de exportacao e gestao em massa. Retencao e reprocessamento de erro permanecem adiados. Nenhum conector, Webmania automatica, manifestacao automatica, `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt` foi introduzido.

**OpenAPI:** nenhuma alteracao.
