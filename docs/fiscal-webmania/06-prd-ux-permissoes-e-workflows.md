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
- Devolucao/estorno: disponivel para NF-e autorizada, com itens selecionaveis e referencia obrigatoria.
- Complementar: disponivel para NF-e autorizada, com tipo de complemento explicito.
- Ajuste: disponivel para usuario autorizado, com justificativa e dados fiscais obrigatorios.
- NFC-e: disponivel em emissao manual/contextual somente se a oficina tiver configuracao NFC-e habilitada.
- Manifestacao: disponivel para documento/chave elegivel e usuario autorizado.
- IBS/CBS: inicialmente atras de permissao especifica e aviso de Reforma Tributaria.

Eventos devem aparecer em timeline/historico do documento original. Documentos derivados devem aparecer como documentos proprios na listagem, mas com link "Documento original".

## Permissoes especificas Fase 2

| Acao | Owner | Diretor | Gerente | Colaborador | Permissao especifica | Escopo oficina |
| ---- | ----: | ------: | ------: | ----------: | -------------------- | -------------- |
| Emitir CC-e | Sim | Sim | Opcional | Nao | `issue_nfe_correction` | Obrigatorio |
| Emitir devolucao/estorno | Sim | Sim | Opcional | Nao | `issue_nfe_return` | Obrigatorio |
| Emitir complementar | Sim | Sim | Opcional | Nao | `issue_nfe_complementary` | Obrigatorio |
| Emitir ajuste | Sim | Sim | Nao | Nao | `issue_nfe_adjustment` | Obrigatorio |
| Emitir NFC-e | Sim | Sim | Opcional | Nao | `issue_nfce` | Obrigatorio |
| Manifestar NF-e | Sim | Sim | Opcional | Nao | `manifest_nfe` | Obrigatorio |
| Emitir evento IBS/CBS | Sim | Sim | Nao | Nao | `issue_nfe_ibs_cbs_event` | Obrigatorio |
| Cancelar evento IBS/CBS | Sim | Sim | Nao | Nao | `cancel_nfe_ibs_cbs_event` | Obrigatorio |
| Consultar documentos/eventos NF-e/NFC-e | Sim | Sim | Sim | Opcional | `view_fiscaldocument` | Obrigatorio |
| Baixar XML/DANFE/eventos | Sim | Sim | Sim | Opcional | `download_fiscaldocument` | Obrigatorio |
| Visualizar payload de evento | Sim | Opcional | Nao | Nao | `view_fiscal_payload` | Obrigatorio |

Compatibilidade:

- Enquanto permissoes novas nao forem migradas para todos os usuarios, views Fase 2 podem manter fallback documentado para permissoes legadas apenas quando nao ampliar acesso.
- Fallback nunca deve permitir acesso cross-workshop.
