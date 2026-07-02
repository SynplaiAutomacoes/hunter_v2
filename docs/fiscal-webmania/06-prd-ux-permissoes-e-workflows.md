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
- Indicacao NFCom v2.0.0 com rollout interno controlado.
- Indicacao DC-e v2.0.0 com rollout interno controlado.
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

Resultado da Fase 2.4D.2:

- Permissao efetiva: `cancel_ibs_cbs_event`, restrita ao cancelamento do evento IBS/CBS `112110` autorizado.
- A UI exibe acao "Cancelar evento" apenas quando o evento `112110` possui UUID remoto e status autorizado.
- O formulario exige confirmacao explicita e informa que o cancelamento afeta apenas o evento IBS/CBS, nao cancela NF-e/NFC-e e nao libera credito/debito ou outros eventos.
- Downloads e payloads do cancelamento reutilizam protecao de oficina ativa e permissoes de visualizacao/download de eventos IBS/CBS.
- Para eventos com itens, mostrar sequencial fiscal da nota, nao ID interno.
- Exigir confirmacao explicita de responsabilidade fiscal e informar que eventos nao corrigem payload base, nao emitem credito/debito e nao substituem complementar tributaria.
- Exibir historico de eventos, status, protocolo/UUID remoto, XML quando retornado e eventual cancelamento.

Bloqueios de UI:

- Nao exibir evento `211128` enquanto credito/debito nao estiverem implementados e aprovados.
- Nao exibir cancelamento de evento sem UUID remoto autorizado.
- Nao oferecer evento IBS/CBS a partir do fluxo de ajuste.
- Nao criar central fiscal nova nesta fase.

## Fase 2.4D.3.0 - UX e permissoes planejadas para demais Eventos IBS/CBS

Decisao: a proxima UI funcional deve expor somente `112150`, se aprovada, no detalhe de NF-e/NFC-e normal local elegivel. A interface deve pedir `data_previsao_entrega`, mostrar aviso fiscal de que o evento altera previsao de entrega e exigir confirmacao explicita.

Resultado 2.4D.3: a UI minima do detalhe de NF-e passou a oferecer `112150` somente quando a NF-e normal local esta elegivel e o usuario possui `issue_ibs_cbs_event`. O formulario exige `data_previsao_entrega` em formato de data e confirmacao explicita. A mesma permissao `issue_ibs_cbs_event` foi reutilizada; permissoes comuns de NF-e/NFC-e nao liberam o evento automaticamente. Downloads e payloads continuam protegidos por `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`. A tela informa que cancelamento do `112150`, credito/debito, complementar tributaria e demais eventos nao estao disponiveis.

Resultado 2.4D.4: a UI minima do detalhe de NF-e passou a oferecer cancelamento do evento `112150` somente quando o evento esta aprovado, possui UUID remoto e o usuario tem `cancel_ibs_cbs_event`. O formulario exige confirmacao explicita e informa que o cancelamento afeta apenas o evento IBS/CBS, nao a NF-e original. O cancelamento do `112110` permanece preservado; nao ha acao de cancelamento generico para outros codigos.

## Fase 2.4D.5.0 - UX e permissoes planejadas para 112120/112130/112140

Decisao: nao criar uma tela generica de JSON livre para eventos com itens. Cada codigo deve ter formulario proprio, com campos e avisos especificos.

UI planejada por evento:

- `112120`: selecao de itens fiscais de NF-e de importacao, quantidade/unidade sem conversao em isencao, valores IBS/CBS e confirmacao de contexto ALC/ZFM.
- `112130`: selecao de itens fiscais, quantidade/unidade de perecimento/perda/roubo/furto, valores IBS/CBS relacionados e valores de estorno IBS/CBS, com confirmacao de transporte contratado pelo fornecedor.
- `112140`: selecao de itens do documento/pagamento antecipado, quantidade/unidade nao fornecida e valores IBS/CBS, com confirmacao de que nao e nota de credito/debito nem cancelamento.

Permissoes:

- Reutilizar `issue_ibs_cbs_event`, `view_ibs_cbs_event`, `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`.
- Nao criar permissao por codigo nesta fase documental.
- Nao conceder eventos por fallback de NF-e, NFC-e, devolucao, complementar, ajuste ou credito/debito.

Bloqueios de UI:

- Ocultar todos os tres eventos para documento externo minimo sem XML/importacao validada.
- Ocultar evento quando o snapshot fiscal nao contem sequencial fiscal e IBS/CBS por item.
- Ocultar `112140` ate haver regra de pagamento antecipado/documento de debito modelada.
- Mostrar erro operacional ao emissor sem permissao administrativa para corrigir snapshot ou configuracao fiscal.

Permissoes:

- Reutilizar `issue_ibs_cbs_event`, `view_ibs_cbs_event`, `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`.
- Nao conceder eventos de destinatario por fallback de NF-e/NFC-e emitente.
- Eventos do Grupo D devem exigir futura habilitacao administrativa por oficina e permissao adicional de papel destinatario.

Bloqueios:

- Ocultar Grupo B ate haver origem operacional segura para item/estoque/transporte/pagamento antecipado.
- Ocultar Grupo C ate credito/debito IBS/CBS estar implementado.
- Ocultar Grupo D ate haver importacao/monitor/validador de documentos de aquisicao ou decisao fiscal equivalente.
### Resultado Fase 2.4D.5.1 - UX Evento 112130

A UI minima do detalhe da NF-e passou a expor `Registrar evento IBS/CBS` para `112130` somente quando a NF-e local normal esta elegivel e o usuario possui `issue_ibs_cbs_event`. O formulario exige item fiscal, valores IBS/CBS, quantidade/unidade de perecimento, valores de estorno e confirmacao explicita. A tela informa que cancelamento do `112130`, eventos `112120/112140`, eventos `211xxx`, credito/debito e complementar tributaria permanecem fora do escopo. Downloads e payloads reutilizam `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`, com escopo por oficina.

### Resultado Fase 2.4D.5.2 - UX Cancelamento 112130

A UI minima do detalhe da NF-e passou a expor cancelamento apenas para evento `112130` aprovado, com UUID remoto e usuario com `cancel_ibs_cbs_event`. O formulario exige confirmacao explicita e informa que o cancelamento afeta somente o evento IBS/CBS, nao a NF-e original. Nao ha acao generica para cancelamento de `112120`, `112140` ou eventos `211xxx`. Downloads e payloads permanecem protegidos por `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`, com escopo por oficina.

### Fase 2.4D.6.0 - UX planejada para 112120 e 112140

Decisao: nao expor acoes de UI para `112120` ou `112140` agora.

Quando houver fase preparatoria aprovada:

- `112120` deve aparecer somente para usuario com `issue_ibs_cbs_event`, documento de importacao/ALC-ZFM validado e itens fiscais importados/projetados. A UI deve exibir item fiscal sequencial, quantidade/unidade sem conversao em isencao, valores IBS/CBS e confirmacao fiscal explicita.
- `112140` deve aparecer somente depois de existir nota de debito/pagamento antecipado e vinculo financeiro-item fiscal. A UI deve exibir item da nota de debito, quantidade/unidade nao fornecida, valores IBS/CBS, referencia financeira e confirmacao explicita.
- Cancelamento desses eventos deve aparecer somente apos a emissao correspondente validada e evento autorizado com UUID remoto.

Permissoes: reutilizar `issue_ibs_cbs_event`, `cancel_ibs_cbs_event`, `view_ibs_cbs_event`, `download_ibs_cbs_event` e `view_ibs_cbs_event_payload`, sem fallback de NF-e/NFC-e, credito/debito, financeiro ou estoque.
## Fase 2.5.1.0 - Permissoes e UX futura

Permissoes planejadas: `issue_nfe_credit`, `issue_nfe_debit`, `view_nfe_credit_debit`, `download_nfe_credit_debit` e `view_nfe_credit_debit_payload`. Emissao deve ser restrita a perfil administrativo/fiscal e nao herdar fallback de NF-e normal.

UI minima futura, somente apos fase preparatoria: feature flag e habilitacao por oficina; escolha credito/debito; lista limitada aos tipos habilitados pelas fontes locais; selecao de documento/item referenciado quando aplicavel; dados IBS/CBS somente leitura a partir do snapshot validado; confirmacao fiscal explicita; status, XML/DANFE e payload protegido. A UI nao deve oferecer tipos bloqueados nem permitir entrada livre que contorne a fonte fiscal.

### UI implementada na Fase 2.5.1P

- Listagem e detalhe de bases por oficina.
- Habilitacao/desabilitacao administrativa auditada.
- Criacao somente a partir de NF-e normal local autorizada, sequencial fiscal e hipotese.
- Visualizacao sanitizada do snapshot e aprovacao separada.
- Avisos explicitos de que nenhuma NF-e de credito/debito e emitida.
- Permissoes: `prepare_nfe_credit_debit_basis`, `approve_nfe_credit_debit_basis`, `view_nfe_credit_debit_basis` e `view_nfe_credit_debit_basis_payload`.

## Fase 2.5.2.0 - UX futura

Nao expor acao de emissao. A proxima UI preparatoria deve permitir decompor multa/juros por item fiscal, exibir o snapshot comercial/IBS-CBS, validar totais e exigir aprovacao fiscal separada. A futura emissao de credito tipo 1 exigira permissao `issue_nfe_credit`, feature flag funcional distinta da flag de preparacao e confirmacao explicita.
## UI preparatoria 2.5.2P

O formulario existente passou a receber principal, multa, juros e outros por item. O detalhe exibe descricao, NCM, CFOP, quantidade, unidade, valores originais e base calculada. As permissoes `prepare_nfe_credit_debit_basis`, `approve_nfe_credit_debit_basis`, `view_nfe_credit_debit_basis` e `view_nfe_credit_debit_basis_payload` foram reutilizadas. A interface informa explicitamente que nenhuma emissao esta disponivel.
## UX/permissoes futuras - credito tipo 1

Permissoes planejadas: `issue_nfe_credit`, `view_nfe_credit`, `download_nfe_credit` e `view_nfe_credit_payload`. Preparar ou aprovar base nao concede emissao. A futura emissao exigira `credit_debit_basis_enabled=true` e uma habilitacao administrativa de emissao distinta (ou flag equivalente mais restritiva); a flag de preparacao isolada nunca libera o gateway.

UI futura minima: acao a partir de base aprovada, resumo imutavel do item/NF-e original, multa, juros, base, CFOP e IBS/CBS, confirmacao fiscal explicita e aviso de que se trata de novo documento. Enquanto a regra de valoracao estiver pendente, nenhuma acao de emissao deve ser exibida.
## UI implementada na 2.5.3P

Listagem, formulario, detalhe, aprovacao e visualizacao sanitizada do pre-payload foram adicionados. O formulario mostra multa, juros e total esperado quando a base e selecionada por contexto. Permissoes: `prepare_nfe_credit_product_preview`, `approve_nfe_credit_product_preview`, `view_nfe_credit_product_preview`, `view_nfe_credit_product_preview_payload`. Nenhuma acao de emissao existe.

## UI e permissoes Fase 2.5.4

A preview aprovada elegivel oferece confirmacao explicita e acao unica "Emitir NF-e de credito". Emissao, visualizacao, download e payload usam respectivamente `issue_nfe_credit`, `view_nfe_credit`, `download_nfe_credit` e `view_nfe_credit_payload`, sempre escopados a oficina. Permissoes de preparar/aprovar base ou preview nao concedem emissao.

## UI e permissao Fase 2.5.5

Documento de credito autorizado e sem cancelamento ativo exibe formulario de motivo e confirmacao explicita. `cancel_nfe_credit` e independente de `issue_nfe_credit`; payload e XML do evento continuam protegidos por `view_nfe_credit_payload` e `download_nfe_credit`. A interface informa que origem, base e preview permanecem imutaveis.

## UX e permissoes recomendadas - Fase 2.5.6P

Permissoes preparatorias separadas:

- `prepare_nfe_debit_product_preview`;
- `approve_nfe_debit_product_preview`;
- `view_nfe_debit_product_preview`;
- `view_nfe_debit_product_preview_payload`.

Nenhuma delas concede emissao. A futura permissao `issue_nfe_debit` deve ser criada somente na fase de transmissao e nao pode decorrer de permissoes de credito.

UI minima preparatoria: listar bases aprovadas elegiveis, criar preview de debito tipo 4, exibir multa/juros, chave e item DF-e referenciado, CFOP, produto e IBS/CBS sanitizados, erros e aprovacao. Deve haver aviso explicito de que nao existe transmissao Webmania. Nao exibir outros tipos de debito, novos creditos ou eventos IBS/CBS.

Implementado: listagem, formulario, detalhe, aprovacao e payload sanitizado. A base de hipotese `debit_fine_interest` oferece atalho somente com permissao propria. A flag geral `credit_debit_basis_enabled` habilita preparacao, mas nao concede permissao nem emissao.

## UX e permissoes planejadas - Emissao debito tipo 4

### UX e permissoes implementadas

Foram adicionadas `issue_nfe_debit`, `view_nfe_debit`, `download_nfe_debit` e `view_nfe_debit_payload`. A listagem permite ativacao administrativa auditada e a tela da preview aprovada exibe confirmacao e emissao somente quando flag e permissao especifica estiverem presentes. Payload e downloads continuam escopados pela oficina.

### Cancelamento de debito tipo 4

`cancel_nfe_debit` e independente de `issue_nfe_debit` e das permissoes de credito. A tela da preview exibe motivo, confirmacao explicita, status do evento e XML somente para documento elegivel. O texto informa que nota original, base e preview permanecem imutaveis. Payload e download usam as permissoes de consulta do debito e escopo da oficina ativa.
Permissoes futuras separadas: `issue_nfe_debit`, `view_nfe_debit`, `download_nfe_debit` e `view_nfe_debit_payload`. Preparar/aprovar base ou preview e emitir credito nao concedem emissao de debito.

Criar flag administrativa propria `nfe_debit_emission_enabled` (nome final pode seguir padrao do model), separada de `credit_debit_basis_enabled`. UI minima: botao de emissao somente em preview aprovada/elegivel, confirmacao explicita de `finalidade=6`/`tipo_debito=4`, resumo do DF-e/item, produto e IBS/CBS, status, payload e downloads. Nao oferecer cancelamento na primeira emissao.

## UX e permissoes recomendadas apos a Fase 2.6.0

A Fase 3.0 deve mapear as telas NFS-e legadas e propor evolucao incremental, sem central fiscal nova. O planejamento deve separar emissao, consulta/download, cancelamento, substituicao e manifestacao, sempre por oficina e capacidade municipal.

Permissoes NFS-e legadas devem ser auditadas antes de qualquer nova permissao. A UI futura deve ocultar ou bloquear operacoes nao suportadas pelo municipio/provedor, informar o regime ISS/IBS-CBS aplicavel e preservar as telas existentes durante a transicao.

NFCom e DC-e sao documentadas atualmente pela Webmania como APIs v2.0.0. A feature flag e a habilitacao administrativa por oficina continuam obrigatorias como politica interna de rollout do Hunter, nao como classificacao oficial beta.

## Fase 3.0 - UX e permissoes NFS-e planejadas

Permissoes futuras separadas: `issue_nfse`, `query_nfse`, `cancel_nfse`, `substitute_nfse`, `manifest_nfse`, `download_nfse`, `view_nfse_payload` e `manage_nfse_capabilities`. Durante a convivencia, mapear explicitamente as permissoes legadas `nfserequest` para consulta/emissao existente; nao conceder novas operacoes por fallback.

UI incremental:

- preservar lista, detalhe e wizard por OS;
- adicionar checklist de capacidade/configuracao por oficina antes de novas acoes;
- exibir consulta/reconciliacao sem permitir reemissao;
- mostrar cancelamento, substituicao e manifestacao apenas quando status local, capacidade municipal, Padrao Nacional e permissao permitirem;
- exibir XML, PDF NFS-e e PDF RPS por proxy autenticado;
- informar modelo/provedor, ambiente, ultima sincronizacao e indisponibilidade municipal;
- feature flag por oficina para cada nova subfase, sem central fiscal nova.

### UI entregue na Fase 3.1

Foi adicionada listagem e edicao minima de capacidades municipais no fluxo NFS-e existente, protegida por `finance.manage_nfse_capabilities` e pelo escopo da oficina ativa. A tela nao libera cancelamento, substituicao, manifestacao ou emissao manual nova; flags dessas operacoes permanecem informativas e desabilitadas por padrao.

## UX e permissoes planejadas para manifestacao NFS-e

Fase: 3.6.0 documental.

Permissoes planejadas:

- `issue_nfse_manifestation`;
- `view_nfse_manifestation`;
- `download_nfse_manifestation`;
- `view_nfse_manifestation_payload`.

A permissao de cancelar ou substituir NFS-e nao deve permitir manifestar automaticamente. A acao futura deve aparecer somente em NFS-e elegivel, com Padrao Nacional confirmado, capability/flag ativa e permissao especifica. A UI minima deve permitir selecionar tipo de manifestacao, papel do manifestador, motivo/justificativa quando a rejeicao exigir, confirmacao explicita, historico de manifestacoes, payload protegido e XML/artefatos protegidos quando retornados.

Nao criar tela de emissao manual nova de NFS-e nesta fase ou na fase funcional de manifestacao.

### Resultado 3.6.1

UI minima adicionada no detalhe da NFS-e: acao de manifestar apenas quando a NFS-e e elegivel, selecao de evento, manifestador, motivo/justificativa de rejeicao, confirmacao explicita, historico de manifestacoes, payload protegido e download de XML/artefato quando retornado. Permissoes criadas: `issue_nfse_manifestation`, `view_nfse_manifestation`, `download_nfse_manifestation` e `view_nfse_manifestation_payload`.

## UX e permissoes recomendadas pela Fase 3.7.0

Proxima fase recomendada: preview de emissao manual nova de NFS-e, sem transmissao.

Permissoes candidatas:

- `prepare_nfse_manual_emission`;
- `approve_nfse_manual_emission`;
- `view_nfse_manual_emission_preview`;
- `view_nfse_manual_emission_payload`.

## Fase 3.7.1 - UX e permissoes da emissao manual

Permissoes implementadas para a transmissao: `issue_nfse_manual_emission`, `view_nfse_manual_emission`, `download_nfse_manual_emission` e `view_nfse_manual_emission_payload`. Permissoes de preparar/aprovar preview, `cancel_nfse`, `substitute_nfse` e `issue_nfse_manifestation` nao autorizam emissao manual.

A UI minima lista emissoes manuais, mostra previews aprovadas elegiveis, exige confirmacao explicita antes do envio e apresenta payload/retorno/downloads protegidos. A tela nao permite editar payload aprovado e nao oferece cancelamento, substituicao ou manifestacao da NFS-e manual nesta fase.

Nenhuma permissao preparatoria concede emissao. A futura permissao de transmissao deve ser criada em fase funcional propria.

UI minima: lista de previews por oficina, formulario de tomador/servico/valores/impostos, validacao de capability municipal, detalhe com payload sanitizado, aprovacao fiscal e aviso explicito de que nenhuma NFS-e sera emitida na fase preparatoria. A UI nao deve abrir CT-e, MDF-e, NFCom, DC-e, importacao de NFS-e recebida, eventos IBS/CBS pendentes ou credito/debito restante.

### UX e permissoes da Fase 3.2

- `query_nfse`: consulta item por UUID; `change_nfserequest` permanece fallback explicito somente para compatibilidade da acao legada.
- `query_nfse_batch`: consulta lote RPS; sem fallback legado.
- `query_nfse_status`: consulta status municipal e protege retorno sanitizado; gerenciar capacidade nao implica consultar automaticamente.
- detalhe da request separa “Consultar NFS-e” de “Consultar lote RPS”; tela da capacidade exibe status, horario, erro e ultimo retorno sanitizado.
## Fase 3.3 - UX e permissao

`cancel_nfse` e obrigatoria e nao possui fallback para permissao generica de alteracao. A acao aparece apenas para item autorizado, com UUID, sem cancelamento reservado e com capacidade municipal compativel. O formulario exige motivo oficial e confirmacao explicita, informa que cancelamento nao e substituicao e protege payload/XML por oficina e permissao.

## Fase 3.4.0 - UX planejada

- Permissoes separadas: `prepare_nfse_substitution`, `approve_nfse_substitution`, `substitute_nfse` e leitura protegida de payload/XML.
- Preparar/aprovar preview nao concede `substitute_nfse`; permissoes de emissao/cancelamento legadas nao possuem fallback.
- Acao disponivel somente para NFS-e autorizada, nao cancelada/substituida/incerta, com UUID/codigo de verificacao/XML, capability `substitution_enabled` e feature flag de rollout por oficina.
- Formulario da preview exibe original, motivo e novo RPS completo; exige confirmacao de que a operacao pode substituir/cancelar a original. A Fase 3.4P nao possui botao de transmissao.
- Futuro detalhe mostra original e substituta, payload, erros, status e XMLs separados.

Implementado na 3.4P: lista, formulario, detalhe, aprovacao local e JSON sanitizado. Permissoes efetivas: `prepare_nfse_substitution`, `approve_nfse_substitution`, `view_nfse_substitution_preview` e `view_nfse_substitution_preview_payload`. O detalhe da NFS-e original oferece apenas **Preparar substituicao** quando elegivel; nao existe botao de transmissao.

Implementado na 3.4.1: **Substituir NFS-e** aparece apenas em preview aprovada elegivel e abre confirmacao explicita. `substitute_nfse` nao possui fallback para preparar, aprovar ou cancelar. `view_nfse_substitution_payload` e `download_nfse_substitution` protegem request/response, XML original, XML/PDF substitutos e tenancy.
## Fase 3.8.0 - UX e permissoes pos-emissao manual NFS-e

A Fase 3.7.1 validada no checkpoint `2cb35206` entregou UI minima de emissao manual e visualizacao de payload/artefatos. A proxima acao recomendada e expor cancelamento da NFS-e manual nova somente quando a emissao estiver autorizada e vinculada a `NfseItem` com UUID seguro.

UX recomendada para a Fase 3.8.1:

- botao de cancelamento no detalhe da emissao manual e/ou detalhe da NFS-e manual autorizada;
- confirmacao explicita;
- selecao de motivo permitido (`1`, `2`, `4`);
- aviso de que o XML de cancelamento fica separado e que a preview/emissao original permanecem imutaveis;
- historico/estado do cancelamento no detalhe;
- payload, resposta e download protegidos por permissao e oficina.

Permissoes: usar `cancel_nfse` para cancelar; `issue_nfse_manual_emission`, permissoes de preview, substituicao ou manifestacao nao devem liberar cancelamento. Cross-workshop deve retornar bloqueio/404 conforme padrao atual.

Resultado da Fase 3.8.1: a tela de detalhe da emissao manual mostra acao de cancelamento somente quando a NFS-e manual esta autorizada, vinculada a `NfseItem`, possui UUID seguro, esta elegivel e o usuario possui `cancel_nfse`. A UI exige motivo e confirmacao explicita, mostra payload/XML de cancelamento protegidos e nao oferece substituicao ou manifestacao da NFS-e manual nesta fase.

## Fase 3.9.0 - UX recomendada apos ciclo minimo manual

A Fase 3.8.1 foi validada no checkpoint `29f3f3a9`. A proxima UX recomendada e expor substituicao da NFS-e manual como extensao do fluxo atual de substituicao NFS-e.

Permissoes:

- reutilizar `prepare_nfse_substitution`, `approve_nfse_substitution`, `substitute_nfse`, `view_nfse_substitution_payload` e `download_nfse_substitution`;
- `issue_nfse_manual_emission` nao concede substituicao;
- `cancel_nfse` nao concede substituicao;
- `issue_nfse_manifestation` nao concede substituicao.

UI minima da proxima fase:

- acao para preparar substituicao no detalhe da emissao manual autorizada, somente quando elegivel;
- detalhe da preview mostrando NFS-e manual original, motivo e novo RPS completo;
- aprovacao fiscal da preview sem transmissao;
- acao de substituir somente em preview aprovada, com confirmacao explicita;
- historico mostrando original manual e substituta;
- payload/retorno/downloads protegidos por oficina e permissao;
- aviso de que XML original e payload da emissao manual permanecem preservados.

Nao exibir manifestacao da NFS-e manual ou importacao de NFS-e recebida nesta proxima fase.

## Fase 3.9.1 - UX e permissoes implementadas

O detalhe da emissao manual passou a exibir **Preparar substituicao** somente quando a NFS-e manual possui `NfseItem` autorizado/elegivel e o usuario tem `prepare_nfse_substitution`.

O fluxo reutilizado permanece:

- criar preview em `NfseSubstitutionPreviewCreateView`;
- aprovar preview com `approve_nfse_substitution`;
- executar POST remoto somente com `substitute_nfse`;
- visualizar payload com `view_nfse_substitution_preview_payload`/`view_nfse_substitution_payload`;
- baixar XML/PDF com `download_nfse_substitution`.

Permissoes de emissao manual, cancelamento e manifestacao nao autorizam substituicao. A UI nao oferece manifestacao da NFS-e manual nesta fase.

## Fase 3.10.0 - UX e permissoes reavaliadas para manifestacao manual

Nenhuma UI nova deve ser criada nesta fase. A acao de manifestar NFS-e manual continua oculta, mesmo quando o usuario possui permissao de manifestacao, porque permissao nao resolve o papel fiscal do manifestador.

Se uma fase futura for aprovada, a UI minima devera:

- mostrar a acao somente para NFS-e manual Padrao Nacional autorizada e com papel fiscal explicitamente confirmado;
- reutilizar `issue_nfse_manifestation`, `view_nfse_manifestation_payload` e downloads/eventos protegidos;
- exigir selecao de manifestador (`tomador` ou `intermediario`) e evento (`confirmacao` ou `rejeicao`);
- exigir motivo/justificativa de rejeicao quando aplicavel;
- pedir confirmacao explicita antes do POST;
- nao oferecer manifestacao para cancelada, substituida, uncertain, municipal legada ou recebida/importada sem dominio proprio.

## Fase 3.11.0 - UX e permissoes planejadas para NFS-e recebida

Permissoes planejadas:

- `import_nfse_received`;
- `view_nfse_received`;
- `view_nfse_received_payload`;
- `download_nfse_received_xml`.

Manifestacao futura, em fase separada, podera reutilizar:

- `issue_nfse_manifestation`;
- `view_nfse_manifestation`;
- `download_nfse_manifestation`;
- `view_nfse_manifestation_payload`.

UX planejada: tela de importacao/registro de NFS-e recebida com upload de XML como fonte preferencial, exibicao de divergencias, validacao explicita do papel fiscal da oficina, historico de validacoes, status "nao manifestavel" quando o papel for prestador/desconhecido/divergente, e payload/XML protegidos por permissao e oficina.

## Fase 3.11.1 - UX e permissoes implementadas para NFS-e recebida

Foram implementadas lista, importacao por XML, detalhe, payload sanitizado e download do XML original para `NfseReceivedDocument`. Permissoes efetivas:

- `import_nfse_received`;
- `view_nfse_received`;
- `view_nfse_received_payload`;
- `download_nfse_received_xml`.

A UI nao oferece manifestacao, consulta Webmania, emissao, cancelamento ou substituicao da recebida.

## Fase 3.12.0 - UX e permissoes planejadas para manifestacao recebida

A futura acao de manifestar deve aparecer somente no detalhe de `NfseReceivedDocument` validado, role `taker` ou `intermediary`, UUID seguro, Padrao Nacional confirmado, capability `manifestation_enabled` ativa e usuario com `issue_nfse_manifestation`.

Permissoes planejadas: reutilizar `issue_nfse_manifestation`, `view_nfse_manifestation`, `view_nfse_manifestation_payload` e `download_nfse_manifestation`. Permissoes de importacao de recebida, emissao manual, cancelamento ou substituicao nao autorizam manifestacao.

UI minima:

- acao "Manifestar" condicionada a elegibilidade;
- form com evento confirmacao/rejeicao;
- manifestador predefinido ou restrito conforme role (`taker` => tomador, `intermediary` => intermediario);
- motivo obrigatorio para rejeicao;
- justificativa obrigatoria somente para motivo `9`;
- justificativa bloqueada para motivos `1..5`;
- confirmacao explicita antes do POST;
- historico de manifestacoes no detalhe da recebida;
- payload/retorno/download protegidos por permissao e oficina;
- aviso de que XML recebido e dados fiscais extraidos permanecem imutaveis.

Nao exibir manifestacao para `provider`, `unknown`, `multiple`, documento cancelado/substituido/uncertain, sem UUID, sem Padrao Nacional, duplicado ou cross-workshop.

## Fase 3.13.1 - UX e permissoes da consulta auxiliar recebida

Permissoes implementadas em `NfseReceivedDocumentConsultation`:

- `consult_nfse_received`;
- `view_nfse_received_consultation`;
- `view_nfse_received_consultation_payload`.

Permissoes de importar recebida, manifestar, emitir, cancelar ou substituir nao autorizam consulta por si so.

UI minima:

- detalhe de `NfseReceivedDocument` mostra ultimo status consultivo;
- botao "Consultar Webmania" aparece somente quando o documento e elegivel e o usuario possui `consult_nfse_received`;
- formulario exige confirmacao explicita de que a consulta e auxiliar e nao substitui XML;
- historico de consultas mostra identificador, status, UUID remoto e quantidade de divergencias;
- payload consultivo fica protegido por `view_nfse_received_consultation_payload`;
- alertas informam divergencias sem sugerir sobrescrita de dados fiscais.

Nao ha botao de importacao por identificador nesta fase e a consulta nao manifesta automaticamente.

## Fase 3.14.0 - UX recomendada para importacao em lote XML

Status: em planejamento documental em 2026-06-29. A Fase 3.13.1 foi validada no checkpoint `01f0924d`.

Workflow recomendado para a proxima fase:

1. Usuario com permissao especifica acessa acao de importacao em lote em NFS-e recebidas.
2. Usuario seleciona multiplos arquivos XML, respeitando limites de quantidade e tamanho.
3. Sistema processa cada arquivo isoladamente, reaproveitando a validacao do upload unitario.
4. Sistema exibe relatorio com totais de importados, duplicados, invalidos e bloqueados por oficina/empresa.
5. Cada linha do relatorio deve indicar nome do arquivo, resultado, motivo de erro e link para o documento criado quando houver.

Permissoes recomendadas:

- permissao propria para importar lote de NFS-e recebida;
- permissoes existentes de payload/XML continuam governando visualizacao e download;
- permissao de manifestacao nao autoriza importacao em lote;
- permissao de consulta Webmania nao autoriza importacao em lote.

UX explicitamente fora do escopo da proxima fase: e-mail/ERP, processamento assincrono externo, consulta Webmania automatica, manifestacao automatica, edicao/substituicao de XML validado e criacao de `NfseItem` ou `FiscalDocument(nfse)`.

## Fase 3.14.1 - UX e permissoes implementadas para lote XML

Foi adicionada acao "Importar lote XML" na lista de NFS-e recebidas, formulario com upload multiplo, limites visiveis e confirmacao explicita de que nao ha consulta Webmania nem manifestacao automatica.

O relatorio do lote exibe status, totais, duplicados, erros e uma linha por arquivo, com link para o `NfseReceivedDocument` importado quando houver.

Permissoes implementadas: `import_nfse_received_batch` para iniciar lote e `view_nfse_received_batch` para visualizar o relatorio. Permissoes de consulta, manifestacao, emissao, cancelamento ou substituicao nao autorizam lote.

## Fase 3.15.0 - UX e permissoes planejadas para e-mail/ERP

Status: validada documentalmente em 2026-06-29 no checkpoint `4815728b`. A Fase 3.14.1 foi validada no checkpoint `b53e862b`.

UX futura a planejar:

- tela de fontes externas por oficina;
- status de autenticacao/conexao;
- fila de anexos/XMLs pendentes;
- acao manual para revisar/processar;
- vinculo do processamento com lote XML;
- erros por anexo e historico de reprocessamento.

Permissoes futuras devem separar configuracao de fonte externa, visualizacao da fila, processamento de anexos e visualizacao de documentos importados. Permissoes de consulta, manifestacao, emissao, cancelamento ou substituicao nao devem autorizar e-mail/ERP.

## Fase 3.15.1 - UX, permissoes e flags planejadas para caixa externa

Status: em planejamento documental em 2026-06-29. A Fase 3.15.0 foi validada documentalmente no checkpoint `4815728b`.

Telas futuras planejadas:

- configuracao de fonte externa por oficina/empresa;
- status de autenticacao, revogacao e ultima coleta;
- caixa de entrada de XMLs candidatos;
- detalhe do item com origem, remetente ou sistema, nome original, hash, data de recebimento e erros;
- revisao antes da importacao fiscal;
- acao para descartar item;
- acao para enviar itens aprovados ao lote XML;
- historico de descartes, erros e reprocessamentos;
- desativacao de fonte externa sem apagar historico.

Permissoes planejadas:

- `configure_nfse_external_xml_source`;
- `view_nfse_external_xml_inbox`;
- `process_nfse_external_xml_inbox`;
- `discard_nfse_external_xml_inbox`;
- `view_nfse_external_xml_payload`.

Decisao de permissao: `import_nfse_received_batch` nao deve, sozinha, processar a caixa externa. A caixa de entrada precisa de permissao separada porque envolve origem externa, credenciais, anexos e descarte; a permissao de lote continua governando a importacao fiscal apos revisao.

Feature flags planejadas: `nfse_external_xml_inbox_enabled`, `nfse_email_xml_import_enabled` e `nfse_erp_xml_import_enabled`. As flags devem ser por oficina/empresa quando envolverem credenciais ou fonte operacional; flag global pode existir apenas como kill switch administrativo.

## Fase 3.15.2 - UX e permissoes implementadas para inbox externa

Status: em implementacao controlada em 2026-06-30. A Fase 3.15.1 foi validada documentalmente no checkpoint `5882cd4e`.

UX minima implementada: lista de inboxes, upload manual/assistido de XMLs candidatos, detalhe da inbox com contadores, itens, erros, resumo, vinculos com lote/documento, aprovacao, descarte com motivo, processamento de aprovados e payload protegido.

Permissoes implementadas em `NfseExternalXmlInbox`: `view_nfse_external_xml_inbox`, `upload_nfse_external_xml_inbox`, `approve_nfse_external_xml_inbox`, `process_nfse_external_xml_inbox`, `discard_nfse_external_xml_inbox` e `view_nfse_external_xml_payload`.

Permissoes de consulta, manifestacao, emissao, cancelamento, substituicao e lote nao aprovam nem processam a inbox por si so.

## Fase 3.16.0 - UX apos inbox externa local

Status: em planejamento documental em 2026-06-30. A Fase 3.15.2 foi validada no checkpoint `517d25b8`.

A inbox local ja possui fluxo minimo. Melhorias pequenas recomendadas antes de conectores reais: filtros por status/empresa/origem, busca por hash/arquivo/UUID, exportacao de relatorio, acoes em massa de aprovacao/descarte com confirmacao, retencao visivel, reprocessamento controlado e painel de auditoria.

Permissoes existentes devem continuar separadas: visualizar, enviar, aprovar, processar, descartar e payload. Nenhuma permissao de consulta, manifestacao, emissao, cancelamento, substituicao ou lote deve liberar automaticamente a operacao da inbox.

## Fase 3.16.1 - UX e permissoes operacionais da inbox XML

Status: validada em 2026-06-30 no checkpoint `166eda86`. A Fase 3.16.0 foi validada documentalmente no checkpoint `267fc601`.

UX implementada: filtros na lista, busca textual, paginacao, CSV, filtros no detalhe, selecao de itens, acoes em massa para aprovar, descartar e processar, motivo obrigatorio no descarte em massa, auditoria resumida por item e links mais claros para lote/documento recebido.

Permissoes novas: `export_nfse_external_xml_inbox` para relatorio CSV e `bulk_manage_nfse_external_xml_inbox` para acoes em massa. As permissoes existentes continuam separadas para visualizar, enviar, aprovar, processar, descartar e ver payload/XML.

Workflow preservado: a inbox continua local e manual/assistida; nenhum item cria documento fiscal diretamente; somente o lote XML validado cria `NfseReceivedDocument`.

## Fase 3.17.0 - UX e permissoes apos consolidacao NFS-e recebida

O bloco NFS-e recebida possui UX suficiente para operacao local: importacao unitaria, lote XML, consulta consultiva, manifestacao recebida, inbox e operacao ampliada da inbox. Permissoes permanecem separadas para importar, consultar, manifestar, visualizar payload/XML, aprovar/processar/descartar inbox, exportar CSV e executar acoes em massa.

A proxima fase recomendada deve auditar consistencia de permissoes e labels antes de novos dominios fiscais, sem criar novo fluxo de usuario funcional.

## Fase 3.17.1 - auditoria de UX, permissoes e workflows

Status: validada em 2026-07-02 no checkpoint `305dc22cf5d811f8c875812a178f68634583a986`. A Fase 3.17.0 foi validada documentalmente no checkpoint `424a3c2a`.

Achado de UX: as telas existentes comunicam a diferenca entre importacao XML, consulta consultiva, manifestacao recebida, lote e inbox. A auditoria nao autorizou nova tela, novo botao funcional ou novo fluxo de usuario.

Achado de permissoes: a granularidade atual continua adequada para o bloco recebido. Permissoes de lote nao autorizam inbox por si so; permissoes de inbox nao criam documento recebido diretamente; permissoes de consulta nao manifestam; permissoes de manifestacao nao substituem/cancelam/emitem.

Decisao: manter qualquer melhoria de labels, painel analitico de auditoria, retencao ou reprocessamento como backlog futuro, para evitar acoplamento de UX com regra fiscal nova nesta fase.

## Fase 3.18.0 - UX e permissoes para o proximo ciclo

Status: validada documentalmente em 2026-07-02 no checkpoint `274df7f7`.

Proximo ciclo recomendado: saneamento tecnico pos-auditoria. Permissoes e UX podem ser revisadas apenas para consistencia, nomenclatura, cobertura de testes e documentacao; nao devem liberar acao fiscal nova, botao de integracao externa, consulta automatica, manifestacao automatica ou novo dominio fiscal.

## Fase 3.18.1 - saneamento de UX, permissoes e workflows

Status: validada em 2026-07-02 no checkpoint `96665e2142a3f8163508f36784b31d5af32247cb`. A Fase 3.18.0 foi validada documentalmente no checkpoint `274df7f7`.

Saneamento permitido: labels, mensagens e testes de permissao/cross-workshop para fluxos existentes. Nao devem surgir botoes ou caminhos que importem, consultem, manifestem, emitam, cancelem, substituam ou exportem dados fiscais alem das permissoes ja existentes.

## Fase 3.19.0 - UX e permissoes no encerramento temporario

Status: em encerramento documental em 2026-07-02.

O ciclo fiscal funcional fica temporariamente encerrado sem criar nova tela, botao, permissao ou workflow. O escopo consolidado ja possui UX minima para NFS-e manual, manifestacao, recebida por XML, consulta consultiva, lote XML e inbox local/manual/assistida.

Permanece proibido iniciar por UX funcional qualquer frente futura de conector real, consulta Webmania automatica, manifestacao automatica, documento recebido sem XML, CT-e, MDF-e, NFCom, DC-e, IBS/CBS pendente, credito/debito pendente ou complementar tributaria. A retomada deve comecar por decisao documental e so entao definir permissoes, feature flags, telas, payloads e testes.

## Fase 4.0.0 - auditoria de UX e permissoes NF-e/NFC-e

Status: em auditoria documental/tecnica em 2026-07-02.

UX existente:

- NF-e normal possui lista, detalhe, wizard compartilhado com NFS-e, preview DANFE, emissao, reconciliacao, cancelamento, inutilizacao, CC-e, devolucao/estorno, complementar preco/quantidade, ajuste, eventos IBS/CBS e downloads.
- NFC-e possui lista, emissao manual simples, cancelamento, inutilizacao, downloads e payload/inutilizacao protegidos.
- Telas exibem confirmacoes antes de acoes fiscais sensiveis, especialmente cancelamento, inutilizacao, CC-e, eventos e derivados.

Permissoes existentes:

- NF-e normal ainda usa `view_nferequest` e `change_nferequest` com fallback temporario para `nfserequest` em partes do fluxo legado.
- Operacoes modernas possuem permissoes especificas: `issue_nfe_correction`, `download_nfe_correction`, `issue_nfe_return`, `issue_nfe_reversal`, `issue_nfe_complementary_price_quantity`, `issue_nfe_adjustment`, `issue_nfce`, `view_nfce`, `download_nfce`, `view_nfce_payload`, `cancel_nfce`, permissoes de credito/debito, eventos IBS/CBS e inutilizacao NFC-e.
- Lacunas: nao ha permissao propria para cancelamento NF-e normal, inutilizacao NF-e normal, payload NF-e normal ou manifestacao NF-e porque o fluxo e legado/ausente.

Decisao de UX/permissoes: a proxima fase deve sanear permissoes e mensagens sem criar botoes novos nem nova acao fiscal. Foco em reduzir permissao ampla nos pontos legados e documentar bloqueios.

## Fase 4.0.1 - saneamento de UX e permissoes NF-e/NFC-e

Status: validada em 2026-07-02 no checkpoint `613a73cb31de23e68883ac35ddbf396e3f08f030`.

Correcao executada: no detalhe da NF-e normal, os botoes/modais de cancelar e inutilizar deixaram de aparecer para usuario sem permissao de alteracao da NF-e legada. A validacao server-side ja exigia `change_nferequest` ou fallback `change_nfserequest`; a UX agora reflete a mesma barreira.

Areas revisadas sem alteracao: NFC-e manual, cancelamento NFC-e, inutilizacao NFC-e, downloads/payloads modernos, CC-e, derivados e eventos IBS/CBS mantiveram permissoes especificas existentes.

Backlog de UX/permissoes: criar decisao propria para permissao dedicada de cancelamento/inutilizacao/download/payload de NF-e normal, sem aproveitar esta fase para migration ou mudanca operacional ampla.

## Fase 4.0.2 - UX e workflow para permissoes dedicadas NF-e normal

Status: em planejamento documental em 2026-07-02.

Decisao de UX: a fase funcional futura deve atualizar UI e POST/download juntos. Um botao fiscal so deve aparecer quando a mesma permissao exigida pela view estiver presente. Durante transicao, a UI pode aceitar permissao dedicada ou fallback legado; a retirada do fallback deve ser fase posterior.

Permissoes planejadas para UX:

- `cancel_nferequest`: exibir/enviar cancelamento NF-e normal.
- `invalidate_nferequest_numbering`: exibir/enviar inutilizacao NF-e normal.
- `download_nferequest_xml`: exibir/baixar XML NF-e normal.
- `download_nferequest_pdf`: exibir/baixar DANFE/PDF NF-e normal.
- `view_nferequest_payload`: reservar para eventual tela payload NF-e normal.
- `view_nferequest_remote_response`: reservar para eventual tela de resposta remota NF-e normal.

Regras de transicao: manter `change_nferequest` e `change_nfserequest` como fallback temporario para acoes fiscais; manter `view_nferequest` como fallback temporario para downloads; documentar grupos afetados; testar usuarios com permissao antiga, permissao nova e sem permissao.
## Fase 4.1.0 - UX e permissoes da retomada de devolucao NF-e

Estado encontrado:
- O detalhe da NF-e ja oferecia acao "Devolucao/Estorno" quando o item local estava aprovado e o usuario possuia `issue_nfe_return` ou `issue_nfe_reversal`.
- A listagem de documentos derivados ja exibia XML/DANFE protegidos por `download_nfe_return`.
- Lacuna operacional: o modal exigia JSON de produtos para qualquer operacao, inclusive devolucao total e estorno.
- Lacuna de seguranca/operacao: nao havia link/rota dedicada para payload de devolucao/estorno.

Decisao aplicada:
- A UI passa a pedir tipo de devolucao (`total` ou `partial`) e torna o JSON obrigatorio apenas para parcial.
- Estorno permanece na mesma acao visual, mas o servidor ignora produtos e usa payload proprio.
- Foi adicionada confirmacao explicita de que a devolucao/estorno cria novo documento fiscal sem alterar a NF-e original.
- Foi criada a permissao `view_nfe_return_payload` para consultar request/response sanitizados do documento derivado.
## Fase 4.2.0 - UX e permissoes da CC-e

- A acao "Emitir Carta de Correcao" aparece apenas para NF-e autorizada da oficina ativa, usuario com `issue_nfe_correction` e ausencia de CC-e ativa ou `uncertain`.
- O formulario exige texto entre 15 e 1000 caracteres e confirmacao explicita de que a correcao respeita as restricoes legais.
- A timeline do detalhe da NF-e mostra status, sequencia, XML/DACCE e link de payload quando o usuario possui `view_nfe_correction_payload`.
- Permissoes usadas: `issue_nfe_correction`, `download_nfe_correction` e `view_nfe_correction_payload`; permissao de NF-e normal nao libera payload da CC-e.
- O texto da UI continua alertando que CC-e nao pode alterar base de calculo, aliquota, preco, quantidade, remetente, destinatario, data, serie ou numero da NF-e.
