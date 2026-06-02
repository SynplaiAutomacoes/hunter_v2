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
- Decisao: na 2.4C.2, IBS/CBS deve ser aplicado somente ao acrescimo de preco/quantidade quando o contrato e o snapshot permitirem. Complementar tributaria ampla permanece subfase separada e nao implementada.
- Alternativas consideradas: reintroduzir todo objeto `impostos`; manter bloqueio total; misturar preco/quantidade e impostos no mesmo formulario.
- Consequencias: preserva escopo incremental e evita rejeicoes por payload tributario incompatível.
- Riscos: alguns cenarios fiscais podem exigir complementar tributaria antes de preco/quantidade com IBS/CBS; nesses casos deve haver nova aprovacao.
- Status: proposta na Fase 2.4C.0.
- Fase: 2.4C.2.

## ADR-039 - Ajuste IBS/CBS exige revalidacao especifica

- Contexto: o fluxo implementado de ajuste usa `/1/nfe/ajuste/` com ICMS/ICMS-ST, cliente, CFOP e regime tributario. O endpoint oficial de eventos IBS/CBS e separado e credito/debito usa finalidades proprias.
- Decisao: nao inserir `produtos[].impostos.ibs_cbs` no ajuste por inferencia. A Fase 2.4C.3 deve revalidar o contrato oficial do ajuste e bloquear operacoes que dependam de Reforma Tributaria ate regra aprovada.
- Alternativas consideradas: transformar ajuste em emissao normal com IBS/CBS; reutilizar evento IBS/CBS; liberar ajuste sem revisao.
- Consequencias: evita payload fora do contrato e mantem ajuste avulso com link opcional.
- Riscos: pode bloquear casos fiscais de ajuste ate esclarecimento oficial/contabil.
- Status: proposta na Fase 2.4C.0.
- Fase: 2.4C.3.
