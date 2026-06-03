# PRD UX, permissoes e workflows fiscais

## Interface final

- Central fiscal unificada.
- Filtros por periodo, tipo, status, origem, cliente, oficina, UUID, chave e numero.
- KPIs de aprovadas, processando, rejeitadas, canceladas, contingencia, incertas e MDF-e aberto.
- Assistente de emissao contextual.
- Emissao manual avulsa.
- Tela de detalhe com timeline, payloads autorizados, downloads e acoes condicionais.
- Historico de eventos e tentativas.
- Alertas de homologacao e producao.
- Alertas de contingencia.
- Alerta MDF-e autorizado nao encerrado.
- Badge NFCom beta.
- Badge DC-e beta.
- Erro de configuracao incompleta.
- Bloqueio por municipio/provedor para NFS-e.

## Acoes condicionais

Acoes devem depender de:

- tipo documental;
- status local;
- status remoto;
- capacidade Webmania;
- capacidade municipal/provedor;
- permissao;
- oficina ativa;
- ambiente.

## Matriz de permissoes proposta

| Acao                    | Owner |  Diretor |  Gerente | Colaborador | Permissao especifica        | Escopo oficina |
| ----------------------- | ----: | -------: | -------: | ----------: | --------------------------- | -------------- |
| Visualizar documento    |   Sim |      Sim |      Sim |    Opcional | `view_fiscaldocument`       | Obrigatorio    |
| Emitir                  |   Sim |      Sim | Opcional |         Nao | `add_fiscaldocument`        | Obrigatorio    |
| Cancelar                |   Sim |      Sim | Opcional |         Nao | `cancel_fiscaldocument`     | Obrigatorio    |
| Inutilizar              |   Sim |      Sim |      Nao |         Nao | `invalidate_fiscaldocument` | Obrigatorio    |
| Emitir correcao         |   Sim |      Sim | Opcional |         Nao | `correct_fiscaldocument`    | Obrigatorio    |
| Emitir devolucao        |   Sim |      Sim | Opcional |         Nao | `return_fiscaldocument`     | Obrigatorio    |
| Substituir NFS-e        |   Sim |      Sim | Opcional |         Nao | `substitute_nfse`           | Obrigatorio    |
| Manifestar              |   Sim |      Sim | Opcional |         Nao | `manifest_fiscaldocument`   | Obrigatorio    |
| Reconciliar             |   Sim |      Sim |      Nao |         Nao | `reconcile_fiscaldocument`  | Obrigatorio    |
| Baixar XML/PDF          |   Sim |      Sim |      Sim |    Opcional | `download_fiscaldocument`   | Obrigatorio    |
| Visualizar payload      |   Sim | Opcional |      Nao |         Nao | `view_fiscal_payload`       | Obrigatorio    |
| Administrar credenciais |   Sim | Opcional |      Nao |         Nao | `change_webmaniacompany`    | Obrigatorio    |
| Habilitar beta          |   Sim |      Nao |      Nao |         Nao | `enable_fiscal_beta`        | Obrigatorio    |

## Compatibilidade UX

Na Fase 1, preservar telas atuais de NF-e/NFS-e. A central unificada pode evoluir em paralelo apenas apos idempotencia e dominio estarem aprovados.

## Regras beta NFCom e DC-e

- NFCom e DC-e devem aparecer como recursos beta em qualquer UI futura.
- Ambos exigem feature flag global, habilitacao administrativa por oficina e permissao especifica.
- Desativar NFCom ou DC-e nao pode afetar NF-e, NFC-e, NFS-e, CT-e ou MDF-e.
- Erros beta devem ser isolados e nao podem bloquear workflows fiscais prioritarios.

## Fase 2.0 - UX NF-e/NFC-e

A Fase 2 deve preservar as telas legadas de NF-e e adicionar acoes condicionais no detalhe/listagem do documento:

- CC-e: disponivel somente para NF-e autorizada da oficina ativa.
- Devolucao/estorno: disponivel para NF-e autorizada local ou NF-e externa por chave confirmada, com itens/quantidades selecionaveis somente quando houver ordem fiscal validada e referencia obrigatoria.
- Complementar: disponivel para NF-e autorizada local ou NF-e externa por chave confirmada, com tipo de complemento explicito: preco/quantidade, impostos ou adicao/importacao. Complementar de preco/quantidade externa exige itens importados/validados; complementar tributaria externa exige confirmacao forte e permissao restrita.
- Ajuste: disponivel para usuario autorizado, com `operacao`, natureza, CFOP, valor ICMS, ambiente e cliente; nao exigir documento original quando a operacao for avulsa.
- Nota Fiscal de Credito/Debito: planejada para Fase 2.5, com finalidade 5/6, `tipo_credito`/`tipo_debito` e UI propria.
- NFC-e: disponivel em emissao manual/contextual somente se a oficina tiver configuracao NFC-e habilitada.
- Manifestacao: disponivel para documento/chave elegivel e usuario autorizado.
- IBS/CBS: inicialmente atras de permissao especifica e aviso de Reforma Tributaria.

Eventos devem aparecer em timeline/historico do documento original. Documentos derivados devem aparecer como documentos proprios na listagem, mas com link "Documento original".

## Permissoes especificas Fase 2

| Acao | Owner | Diretor | Gerente | Colaborador | Permissao especifica | Escopo oficina |
| ---- | ----: | ------: | ------: | ----------: | -------------------- | -------------- |
| Emitir CC-e | Sim | Sim | Opcional | Nao | `issue_nfe_correction` | Obrigatorio |
| Emitir devolucao/estorno | Sim | Sim | Opcional | Nao | `issue_nfe_return` | Obrigatorio |
| Emitir complementar preco/quantidade | Sim | Sim | Opcional | Nao | `issue_nfe_complementary_price_quantity` | Obrigatorio |
| Emitir complementar tributaria | Sim | Sim | Nao | Nao | `issue_nfe_complementary_tax` | Obrigatorio |
| Visualizar complementar | Sim | Sim | Sim | Opcional | `view_nfe_complementary` | Obrigatorio |
| Baixar XML/DANFE complementar | Sim | Sim | Sim | Opcional | `download_nfe_complementary` | Obrigatorio |
| Visualizar payload complementar | Sim | Opcional | Nao | Nao | `view_nfe_complementary_payload` | Obrigatorio |
| Emitir ajuste | Sim | Sim | Nao | Nao | `issue_nfe_adjustment` | Obrigatorio |
| Visualizar ajuste | Sim | Sim | Sim | Opcional | `view_nfe_adjustment` | Obrigatorio |
| Baixar XML/DANFE ajuste | Sim | Sim | Sim | Opcional | `download_nfe_adjustment` | Obrigatorio |
| Visualizar payload ajuste | Sim | Opcional | Nao | Nao | `view_nfe_adjustment_payload` | Obrigatorio |
| Emitir NF-e de credito | Sim | Sim | Nao | Nao | `issue_nfe_credit` | Obrigatorio |
| Emitir NF-e de debito | Sim | Sim | Nao | Nao | `issue_nfe_debit` | Obrigatorio |
| Emitir NFC-e | Sim | Sim | Opcional | Nao | `issue_nfce` | Obrigatorio |
| Cancelar NFC-e | Sim | Sim | Opcional | Nao | `cancel_nfce` | Obrigatorio |
| Inutilizar NFC-e | Sim | Sim | Nao | Nao | `invalidate_nfce_number` | Obrigatorio |
| Baixar XML/DANFE NFC-e | Sim | Sim | Sim | Opcional | `download_nfce` | Obrigatorio |
| Visualizar payload NFC-e | Sim | Opcional | Nao | Nao | `view_nfce_payload` | Obrigatorio |
| Manifestar NF-e | Sim | Sim | Opcional | Nao | `manifest_nfe` | Obrigatorio |
| Emitir evento IBS/CBS | Sim | Sim | Nao | Nao | `issue_ibs_cbs_event` | Obrigatorio |
| Cancelar evento IBS/CBS | Sim | Sim | Nao | Nao | `cancel_nfe_ibs_cbs_event` | Obrigatorio |
| Consultar documentos/eventos NF-e/NFC-e | Sim | Sim | Sim | Opcional | `view_fiscaldocument` | Obrigatorio |
| Baixar XML/DANFE/eventos | Sim | Sim | Sim | Opcional | `download_fiscaldocument` | Obrigatorio |
| Visualizar payload de evento | Sim | Opcional | Nao | Nao | `view_fiscal_payload` | Obrigatorio |

Compatibilidade:

- Enquanto permissoes novas nao forem migradas para todos os usuarios, views Fase 2 podem manter fallback documentado para permissoes legadas apenas quando nao ampliar acesso.
- Fallback nunca deve permitir acesso cross-workshop.

### UI minima Fase 2.2B - Nota complementar

Entrada principal: detalhe da NF-e original.

Controles planejados:

- Botao "Emitir Nota Complementar" somente para NF-e elegivel e usuario autorizado.
- Seletor de subtipo: preco/quantidade, impostos, adicao/importacao.
- Formulario preco/quantidade com sequencial fiscal do item original, valor complementar e/ou quantidade complementar.
- Formulario tributario separado por imposto: ICMS, ICMS-ST, IPI, ISSQN, IBS/CBS.
- Aviso de que a complementar acrescenta valores/dados e nao substitui a nota original.
- Confirmacao explicita antes do envio.
- Historico no detalhe da NF-e original listando complementares derivadas, status, UUID/chave e downloads.

Bloqueios visuais:

- NF-e externa minima sem itens validados bloqueia preco/quantidade.
- `complementary_import_addition` aparece como planejado/indisponivel ate aprovacao especifica.
- Complementar tributaria externa deve exibir alerta de entrada manual auditada e exigir permissao `issue_nfe_complementary_tax`.

Fase 2.2B.1 implementada para revisao: a UI minima ficou restrita ao detalhe da NF-e original local elegivel, com acao "Emitir Nota Complementar", formulario de itens em JSON, confirmacao explicita, historico de complementares e downloads XML/DANFE protegidos. Central fiscal, complementar tributaria e importacao/adicao nao foram iniciadas.

### UI minima Fase 2.2C - Nota de ajuste

Entrada implementada: detalhe da NF-e local existente, com link opcional `adjusts` para o documento relacionado. O service tambem permite ajuste avulso sem documento original, mas a central fiscal/entrada avulsa ampla permanece fora desta subfase.

Controles implementados:

- Botao "Emitir Nota de Ajuste" somente para usuario com `issue_nfe_adjustment`.
- Formulario com operacao, natureza da operacao, CFOP, valor ICMS, valor ICMS-ST opcional, situacao tributaria, cliente em JSON, ambiente e informacoes opcionais.
- Avisos sobre escrituração contabil, regime tributario permitido, ausencia de movimentacao de produtos e excecao de estorno SC/ES pelo fluxo de devolucao/estorno.
- Confirmacao explicita antes da transmissao.
- Historico de ajustes vinculados no detalhe da NF-e e downloads XML/DANFE protegidos por `download_nfe_adjustment`.

Bloqueios visuais/funcionais:

- Regime tributario ausente, Simples Nacional ou MEI bloqueia antes do gateway.
- Cenário de estorno SC/ES identificado pelo usuario deve usar devolucao/estorno; a implementacao exige confirmacao de que a operacao nao pertence a esse caso.
- Complementar tributaria, IBS/CBS, importacao/adicao, NFC-e, manifestacao e credito/debito nao foram iniciados.

### UX Fase 2.3.0 - NFC-e planejada

Entrada minima recomendada para a primeira implementacao:

- Acao "Emitir NFC-e" somente quando a oficina ativa tiver configuracao NFC-e completa para o ambiente selecionado.
- Emissao manual avulsa de venda consumidor e, se aprovado, emissao contextual a partir de OS/origem operacional com produtos.
- Formulario separado de NF-e, com indicacao clara de modelo NFC-e, consumidor, itens, pagamento e ambiente.
- Aviso de homologacao/producao destacado.
- Historico/listagem distinguindo NF-e e NFC-e por modelo.
- Tela/detalhe com status, chave, UUID, XML, DANFE NFC-e, payload autorizado e tentativas.

Bloqueios:

- Sem `issue_nfce`, nao exibir acao nem chamar gateway.
- Sem serie/numero/CSC do ambiente, bloquear antes do gateway.
- Cancelamento e inutilizacao exigem permissoes separadas.
- Contingencia/offline e cancelamento por substituicao devem aparecer como indisponiveis ate nova aprovacao.

Nao criar central fiscal completa na primeira subfase funcional de NFC-e.
## Atualizacao Fase 2.3.2 - UX E Permissao Cancelamento NFC-e

- Permissao nova: `finance.fiscaldocument.cancel_nfce`.
- `issue_nfce` nao concede cancelamento.
- UI minima: acao "Cancelar NFC-e" apenas em NFC-e manual autorizada/elegivel, formulario com motivo, aviso de irreversibilidade e confirmacao explicita.
- A listagem mostra status do evento e download de XML de cancelamento quando disponivel.
- Downloads usam `download_nfce` e continuam escopados pela oficina ativa.
- A interface informa que cancelamento por substituicao, contingencia/offline e PDV/TEF/SAT/MFE permanecem fora de escopo.

## Atualizacao Fase 2.3.3 - UX e Permissoes de Inutilizacao NFC-e

- UI minima adicionada ao fluxo/listagem NFC-e: acao "Inutilizar numeracao NFC-e", formulario de ambiente, serie, sequencia inicial/final e motivo.
- O formulario exige confirmacao explicita de que a verificacao local nao cobre uso externo ao Hunter.
- A listagem mostra historico de inutilizacoes separado das NFC-e emitidas, reforcando que inutilizacao nao e cancelamento.
- Permissoes especificas:
- `inutilize_nfce_numbering`: transmitir inutilizacao.
- `view_nfce_inutilization`: visualizar registro de inutilizacao.
- `download_nfce_inutilization`: baixar XML retornado.
- `view_nfce_inutilization_payload`: visualizar payload sanitizado.
- `issue_nfce` e `cancel_nfce` nao concedem inutilizacao automaticamente.

## Fase 2.5.0 - UX e Permissoes Planejadas para Credito/Debito

Permissoes planejadas:

- `issue_nfe_credit`: emitir Nota Fiscal de Credito.
- `issue_nfe_debit`: emitir Nota Fiscal de Debito.
- `view_nfe_credit_debit`: visualizar notas de credito/debito.
- `download_nfe_credit_debit`: baixar XML/DANFE de credito/debito.
- `view_nfe_credit_debit_payload`: visualizar payload sanitizado.

Politica:

- Emissao deve ser restrita a perfis administrativos/fiscais. Owner e Diretor podem receber por padrao de papel; Gerente somente com permissao explicita; Colaborador nao recebe.
- A funcionalidade deve depender de feature flag e habilitacao administrativa por oficina.
- Permissoes de NF-e normal, ajuste, complementar, NFC-e ou cancelamento nao concedem credito/debito automaticamente.
- Acoes, payloads e downloads continuam escopados por oficina ativa.

UI minima planejada:

- Entrada manual administrativa "Emitir Nota Fiscal de Credito/Debito".
- Escolha explicita entre credito e debito.
- Campo obrigatorio para `tipo_credito` ou `tipo_debito`, com labels oficiais e aviso tributario.
- Formulario de `cliente`, `produtos`, `pedido` e ambiente seguindo o contrato validado de NF-e.
- Link opcional a documento anterior somente quando o usuario informar relacao real ou quando o tipo remoto exigir.
- Confirmacao explicita informando que finalidades 5/6 se relacionam a IBS/CBS/Reforma Tributaria e exigem validacao contabil/fiscal.
- Historico/downloads em tela existente de documentos fiscais, sem criar central fiscal nova nesta subfase.

Bloqueios:

- Sem feature flag/habilitacao administrativa, nao exibir action.
- Sem suporte IBS/CBS aprovado, bloquear implementacao funcional ou limitar a subconjunto aprovado explicitamente.
- Nao permitir emissao por usuario de outra oficina nem visualizar payload/download fora do escopo.

## Fase 2.4.0 - UX e permissoes IBS/CBS

UX planejada:

- A configuracao fiscal da oficina deve exibir alerta quando NF-e/NFC-e estiverem em producao e classes/produtos ainda nao possuirem IBS/CBS minimo.
- Formularios de emissao NF-e/NFC-e devem bloquear antes do envio quando a configuracao IBS/CBS obrigatoria estiver ausente.
- Homologacao deve mostrar aviso claro quando estiver usando modo controlado de teste, sem afirmar conformidade produtiva.
- Classes fiscais NF-e devem indicar visualmente se estao aptas para IBS/CBS e para quais modelos (`nfe`, `nfce` ou ambos).
- Eventos IBS/CBS, credito/debito e complementar tributaria devem continuar ocultos/desabilitados ate subfase aprovada.

Permissoes planejadas:

| Acao | Owner | Diretor | Gerente | Colaborador | Permissao especifica | Escopo oficina |
| ---- | ----: | ------: | ------: | ----------: | -------------------- | -------------- |
| Configurar IBS/CBS em classe fiscal NF-e | Sim | Sim | Condicional | Nao | `manage_nfe_ibs_cbs_tax_classes` | Oficina ativa |
| Visualizar configuracao IBS/CBS | Sim | Sim | Sim | Condicional | `view_nfe_ibs_cbs_tax_classes` | Oficina ativa |
| Ver payload IBS/CBS enviado | Sim | Sim | Condicional | Nao | `view_nfe_ibs_cbs_payload` | Oficina/documento |
| Liberar modo controlado de homologacao | Sim | Condicional | Nao | Nao | `manage_fiscal_compliance_overrides` | Oficina ativa |
| Emitir evento IBS/CBS futuro | Sim | Condicional | Nao | Nao | `issue_ibs_cbs_event` | Oficina/documento |
| Emitir credito/debito futuro | Sim | Condicional | Nao | Nao | `issue_nfe_credit` / `issue_nfe_debit` | Oficina ativa |

Regras:

- Nenhuma permissao IBS/CBS deve ser concedida por fallback legado de NF-e/NFS-e.
- Bloqueios de configuracao devem ocorrer antes do gateway e devem ser compreensiveis para o usuario fiscal.
- UI nao deve sugerir que a classificacao tributaria foi calculada pelo Hunter quando ela foi informada por usuario/admin.

## Fase 2.4C.0 - UX, permissoes e bloqueios para derivados com IBS/CBS

Permissoes: a Fase 2.4C deve reutilizar as permissoes especificas ja existentes de cada operacao (`issue_nfe_return`, `issue_nfe_complementary_price_quantity`, `issue_nfe_adjustment` e permissoes de visualizacao/download/payload correspondentes). Configuracao ou correcao de IBS/CBS em classe fiscal continua restrita a permissao administrativa fiscal. Nenhuma permissao de NF-e normal deve liberar automaticamente complementar tributaria, evento IBS/CBS ou credito/debito.

Mensagens de bloqueio planejadas:

- Devolucao/estorno local: "A NF-e original nao possui snapshot IBS/CBS suficiente para gerar o documento derivado. Revise/importe a tributacao original antes de transmitir."
- Devolucao parcial externa: "NF-e externa informada por chave nao possui itens fiscais importados; devolucao parcial com IBS/CBS permanece bloqueada."
- Complementar preco/quantidade: "A nota complementar deve usar apenas os acrescimos informados. IBS/CBS sera aplicado somente quando houver snapshot fiscal do item original e configuracao validada."
- Ajuste: "Nota de ajuste nao usa automaticamente IBS/CBS de produtos. Se esta operacao depender da Reforma Tributaria, aguarde fase fiscal especifica ou revise com responsavel fiscal."

UI minima futura:

- Exibir, no detalhe da NF-e original, indicador de snapshot tributario disponivel para derivados.
- Em devolucao/complementar, mostrar sequencial fiscal do item original, status IBS/CBS do snapshot e classe fiscal atual apenas como informacao auxiliar.
- Para NF-e externa minima, mostrar que a chave foi validada apenas por formato e que XML/importacao ainda nao ocorreu.
- Para ajuste, manter aviso de escrituração contabil e regime tributario; adicionar aviso de que IBS/CBS nao foi liberado para ajuste sem regra oficial aprovada.
- Nao criar central fiscal nova nem expor eventos IBS/CBS/credito/debito nesta fase.

Resultado 2.4C.3:

- A UI de ajuste passa a avisar que ajuste nao e credito/debito fiscal nem evento IBS/CBS.
- Nao ha campos de produto ou IBS/CBS no formulario.
- `issue_nfe_adjustment` segue obrigatoria antes do gateway; permissoes de emissao NF-e normal, credito/debito ou IBS/CBS nao concedem ajuste.
- Estorno SC/ES permanece direcionado ao fluxo de devolucao/estorno ja implementado.

## Fase 2.4D.0 - UX e permissoes planejadas para Eventos IBS/CBS

Permissoes planejadas:

- `issue_ibs_cbs_event`: registrar evento IBS/CBS.
- `view_ibs_cbs_event`: visualizar evento e status.
- `download_ibs_cbs_event`: baixar XML de evento quando retornado.
- `view_ibs_cbs_event_payload`: visualizar payload/resposta sanitizados.

Politica:

- Nenhuma permissao legada de NF-e, NFC-e, ajuste, complementar, devolucao ou credito/debito concede evento IBS/CBS automaticamente.
- Eventos de destinatario exigem habilitacao administrativa adicional ou feature flag por oficina, porque o papel fiscal difere do emitente.
- Usuario emissor deve pertencer a oficina do documento base e ter permissao especifica antes do gateway.
- Downloads e payloads seguem escopo de oficina ativa e permissoes especificas.

UI minima futura:

- Exibir acao "Registrar evento IBS/CBS" apenas no detalhe de NF-e/NFC-e elegivel.
- Listar somente `cod_evento` permitido para o documento e papel fiscal da oficina.
- Para a primeira subfase recomendada, expor apenas `112110` se aprovado.

Resultado da Fase 2.4D.1:

- Permissoes efetivas: `issue_ibs_cbs_event`, `view_ibs_cbs_event`, `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`.
- A UI minima foi adicionada no detalhe da NF-e elegivel, com acao para registrar somente `112110`, aviso operacional e confirmacao explicita.
- Historico do evento mostra codigo, sequencia, status, UUID, XML e payload quando o usuario tem permissao.
- Cancelamento de evento, outros codigos e central fiscal nova permanecem fora do escopo.
- Para eventos com itens, mostrar sequencial fiscal da nota, nao ID interno.
- Exigir confirmacao explicita de responsabilidade fiscal e informar que eventos nao corrigem payload base, nao emitem credito/debito e nao substituem complementar tributaria.
- Exibir historico de eventos, status, protocolo/UUID remoto, XML quando retornado e eventual cancelamento.

Bloqueios de UI:

- Nao exibir evento `211128` enquanto credito/debito nao estiverem implementados e aprovados.
- Nao exibir cancelamento de evento sem UUID remoto autorizado.
- Nao oferecer evento IBS/CBS a partir do fluxo de ajuste.
- Nao criar central fiscal nova nesta fase.
