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
| Emitir NF-e de credito | Sim | Sim | Nao | Nao | `issue_nfe_credit_note` | Obrigatorio |
| Emitir NF-e de debito | Sim | Sim | Nao | Nao | `issue_nfe_debit_note` | Obrigatorio |
| Emitir NFC-e | Sim | Sim | Opcional | Nao | `issue_nfce` | Obrigatorio |
| Cancelar NFC-e | Sim | Sim | Opcional | Nao | `cancel_nfce` | Obrigatorio |
| Inutilizar NFC-e | Sim | Sim | Nao | Nao | `invalidate_nfce_number` | Obrigatorio |
| Baixar XML/DANFE NFC-e | Sim | Sim | Sim | Opcional | `download_nfce` | Obrigatorio |
| Visualizar payload NFC-e | Sim | Opcional | Nao | Nao | `view_nfce_payload` | Obrigatorio |
| Manifestar NF-e | Sim | Sim | Opcional | Nao | `manifest_nfe` | Obrigatorio |
| Emitir evento IBS/CBS | Sim | Sim | Nao | Nao | `issue_nfe_ibs_cbs_event` | Obrigatorio |
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
