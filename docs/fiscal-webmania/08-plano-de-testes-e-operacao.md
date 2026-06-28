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
| 7 | DC-e v2.0.0 isolada, feature flag interna e cancelamento | Desativacao segura |
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

### Fase 2.2A - Devolucao e estorno

- Documento de devolucao/estorno referencia obrigatoriamente documento original local ou externo.
- Devolucao parcial valida produtos e quantidades contra a nota original quando houver dados locais/consulta.
- NF-e externa cria `FiscalDocument` minimo `origin=external` e registra chave manual.
- NF-e externa valida somente formato da chave de 44 digitos e exige confirmacao explicita; nao chama consulta padrao como garantia.
- NF-e externa minima bloqueia devolucao parcial sem XML/importacao validada dos itens e da ordem fiscal original.
- Devolucao parcial local envia `produtos` como sequenciais fiscais e `quantidade` alinhado pelo mesmo indice; devolucao total e estorno nao enviam selecao parcial desnecessaria.
- Saldo parcial considera documentos derivados aprovados, processando, contingencia e `uncertain`; reprovado e cancelado confirmado nao reservam saldo.
- Duas devolucoes parciais legitimas com payload equivalente podem existir como documentos derivados distintos.
- Mesma intencao derivada nao pode trocar payload apos envio.
- Timeout apos envio vira `uncertain` e bloqueia reenvio.
- Webhook de derivado atualiza derivado, nao sobrescreve original.

### Fase 2.2B - Nota complementar

- Complementar referencia obrigatoriamente NF-e original local ou externa por chave/UUID.
- Testar complemento de preco local.
- Testar complemento de quantidade local.
- Testar complemento tributario separado para ICMS, ICMS-ST, IPI, ISSQN e IBS/CBS conforme campos suportados no payload aprovado.
- Testar documento externo minimo com chave de 44 digitos, confirmacao explicita e sem falsa validacao remota.
- Testar bloqueio de `complementary_price_quantity` para NF-e externa minima sem XML/importacao validada dos itens.
- Testar regra aprovada para `complementary_tax` externa: bloqueio ou permissao restrita com confirmacao forte e payload auditavel.
- Testar que `complementary_import_addition` permanece indisponivel se for adiado.
- Testar `FiscalDocumentLink(role="complements")` obrigatorio.
- Testar idempotencia por documento complementar derivado e timeout `uncertain`.
- Testar concorrencia da mesma intencao gerando uma chamada remota.
- Testar webhook atualizando somente derivado e nao alterando a nota original.
- Testar permissao, cross-workshop, downloads protegidos e payload/log sanitizados.

Cobertura executada na Fase 2.2B.1: somente `complementary_price_quantity` local. Os testes cobrem complemento de preco, quantidade, preco+quantidade, link obrigatorio, bloqueio de original inelegivel, bloqueio de NF-e externa minima, ausencia de objetos tributarios/IBS-CBS fora do escopo, idempotencia por documento derivado, concorrencia com uma chamada remota, duas complementares independentes, timeout `uncertain`, payload congelado, webhook duplicado/fallback/ambiguidade, reconciliacao sem emissao, permissao especifica, cross-workshop, downloads protegidos e sanitizacao. A validacao final reforcou que complemento apenas de preco nao envia quantidade original, complemento apenas de quantidade nao envia valor original, e o payload nao repete silenciosamente `subtotal`, `total` ou `valor_unitario` da NF-e original.

### Fase 2.2C - Nota de ajuste

- Ajuste sem documento original e permitido.
- Ajuste com documento original usa `FiscalDocumentLink` opcional e nao obrigatorio.
- Payload exige `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `ambiente` e `cliente`.
- Timeout vira `uncertain`; retry automatico e proibido.
- Regime tributario permite Lucro Real/Normal e Lucro Presumido; bloqueia Simples Nacional, MEI e regime ausente/desconhecido.
- Payload nao envia `produtos`, `pedido`, `impostos`, IBS, CBS, `agropecuario`, importacao ou adicao.
- Link `adjusts` opcional nao altera status do documento relacionado.
- Webhook atualiza somente o ajuste por UUID/tentativa/fallback seguro; ambiguidade nao atualiza nada.
- Reconciliacao consulta ajuste `uncertain` sem emissao.
- Permissao `issue_nfe_adjustment` e exigida antes do gateway; downloads exigem `download_nfe_adjustment`.
- Cobertura executada na validacao: Fases 1, 2.1, 2.2A, 2.2B.1 e 2.2C direcionadas com 68 testes OK; `makemigrations finance --check --dry-run`, `ruff check` nos arquivos Python tocados e `git diff --check` OK.

### Fase 2.3 - NFC-e

- Oficina sem configuracao NFC-e bloqueia acao.
- `nfce_enabled=False` bloqueia emissao antes do gateway.
- Payload NFC-e usa `modelo=2` e configuracao correta sem afetar NF-e.
- NFC-e e NF-e da mesma origem nao compartilham chave idempotente.
- Cancelamento NFC-e respeita status e permissao.
- Downloads distinguem DANFE/NFC-e conforme retorno.
- Ambiente producao exige `nfce_serie`, `nfce_numero`, `nfce_id_csc` e `nfce_codigo_csc`.
- Ambiente homologacao exige serie, numero homologacao e CSC homologacao quando configuracao de teste estiver ativa.
- Concorrencia da mesma intencao cria uma chamada remota.
- Timeout marca documento/tentativa como `uncertain` e bloqueia retry.
- Webhook `modelo=nfce` resolve `FiscalDocument(document_type="nfce")` por UUID antes de chave e nao atualiza `NfeItem`.
- Reconciliacao de NFC-e `uncertain` usa consulta e nunca emite.
- Payload/log nao persistem headers, consumer secret, access token secret, CSC ou codigo CSC.

### Fase 2.4 - Conformidade IBS/CBS

- Base 2.4A exige classe/produto com situacao/classificacao IBS/CBS validas.
- Emissao 2.4B deve bloquear producao sem configuracao minima.
- Derivados 2.4C devem ter regra propria por operacao; nao reutilizar payload normal cegamente.
- Eventos 2.4D exigem codigo de evento, sequencia e payload compativel com documentacao vigente.
- Credito/debito 2.4E devem barrar tributos incompatíveis e enviar somente IBS/CBS.
- Revalidar schemas com documentacao oficial imediatamente antes de codificar cada subfase.

### Fase 2.5 - Nota Fiscal de Credito e Debito

- NF-e de credito usa `/1/nfe/emissao/`, `finalidade=5` e `tipo_credito`.
- NF-e de debito usa `/1/nfe/emissao/`, `finalidade=6` e `tipo_debito`.
- Validar documento referenciado quando o tipo oficial exigir relacao com documento anterior.
- Idempotencia por `FiscalDocument` persistido e tentativa (`nfe_credit_emission`/`nfe_debit_emission`), nao por hash de payload.
- Timeout vira `uncertain` e bloqueia reenvio automatico.
- Bloquear implementacao funcional quando o tipo depender de IBS/CBS ainda nao implementado.

Testes obrigatorios planejados:

- Payload de credito envia `modelo=1`, `finalidade=5`, `tipo_credito` valido e nao envia `tipo_debito`.
- Payload de debito envia `modelo=1`, `finalidade=6`, `tipo_debito` valido e nao envia `tipo_credito`.
- Lista de `tipo_credito` aceita somente valores oficiais `1` a `5`.
- Lista de `tipo_debito` aceita somente valores oficiais `1` a `8`.
- Campos `cliente`, `produtos`, `pedido`, ambiente e notificacao seguem contrato validado da NF-e.
- Campos de NFC-e, cancelamento, inutilizacao, ajuste, complementar, devolucao e contingencia nao entram no payload.
- `FiscalDocument(document_type="nfe", purpose="credit"|"debit")` e criado antes do gateway.
- `fiscal_purpose_type` preserva codigo remoto enviado.
- `FiscalDocumentLink(role="credits"|"debits")` e opcional/condicional conforme tipo; quando informado, pertence a mesma oficina.
- Feature flag/habilitacao administrativa bloqueia action e gateway quando desligada.
- Permissoes `issue_nfe_credit`, `issue_nfe_debit`, `view_nfe_credit_debit`, `download_nfe_credit_debit` e `view_nfe_credit_debit_payload` sao respeitadas.
- Usuario de outra oficina nao emite, consulta payload nem baixa XML/DANFE.
- Concorrencia da mesma intencao gera uma chamada remota.
- Duas intencoes legitimas com payload equivalente podem coexistir.
- Timeout gera `uncertain`; `uncertain` bloqueia retry automatico.
- Webhook e reconciliacao atualizam apenas o documento de credito/debito correto, sem afetar NF-e normal, derivados, eventos, NFC-e ou inutilizacao.
- Payloads/logs nao expoem credenciais, certificados, CSC, headers ou tokens.
- Quando IBS/CBS for dependencia ativa, teste deve provar bloqueio antes do gateway ate suporte tributario aprovado.
## Atualizacao Fase 2.3.2 - Testes Executados/Planejados

Cobertura adicionada:

- cancelamento valido envia somente `chave`/`uuid` e `motivo`;
- `nfce_referenciada` nao e enviado;
- motivo fora de 15 a 255 caracteres bloqueia;
- NFC-e processando, reprovada, denegada, cancelada, incerta ou sem chave/UUID bloqueia antes do gateway;
- evento `cancellation` e tentativa `nfce_cancellation` sao criados sem novo documento e sem `FiscalDocumentLink`;
- timeout gera `uncertain` e bloqueia retry automatico;
- concorrencia da mesma intencao faz uma chamada remota;
- webhook duplica sem duplicar efeitos, rejeita ambiguidade e atualiza somente evento/documento NFC-e;
- reconciliacao consulta cancelamento incerto sem reenviar;
- permissao `cancel_nfce`, cross-workshop e download de XML de cancelamento sao protegidos;
- payload/log permanecem sanitizados e sem segredos.

## Atualizacao Fase 2.3.3 - Testes de Inutilizacao NFC-e

Testes direcionados adicionados/obrigatorios:
- Body remoto contem somente `sequencia`, `motivo`, `ambiente`, `serie` e `modelo=2`.
- Campos de cancelamento, substituicao, contingencia/offline, pedido e pagamento nao entram no payload.
- Motivo, ambiente, serie e intervalo invalidos sao bloqueados antes do gateway.
- `FiscalNumberInutilization` e criado; `FiscalDocument`, `FiscalDocumentEvent` e `NfeItem` nao sao criados/alterados.
- Faixa com NFC-e local aprovada, cancelada, denegada ou `uncertain` e bloqueada.
- Faixa sobreposta a inutilizacao `succeeded` ou `uncertain` e bloqueada; faixa sobreposta a `failed` pode ser reavaliada.
- Concorrencia da mesma faixa ou de faixas sobrepostas transmite apenas uma chamada remota.
- Timeout gera `uncertain`, preserva payload e reserva a faixa.
- Rejeicao remota com XML nao e convertida em sucesso.
- Permissao, cross-workshop, download e payload sanitizado sao verificados.
- Reconcilacao nao reenvia inutilizacao e nao altera NFC-e emitida.

## Fase 2.4.0 - Testes planejados IBS/CBS

Testes transversais para futura implementacao:

- Emissao normal NF-e em producao com data >= `05/01/2026` bloqueia quando classe/produto nao possuir IBS/CBS minimo.
- Emissao normal NFC-e em producao com data >= `05/01/2026` bloqueia quando classe/produto nao possuir IBS/CBS minimo.
- Payload NF-e/NFC-e normal inclui `produtos[].impostos.ibs_cbs` ou usa `classe_imposto` com IBS/CBS validado, conforme decisao da subfase.
- Coexistencia de tributos antigos com IBS/CBS e permitida apenas nas operacoes normais em que a documentacao permitir.
- Credito/debito enviam somente `impostos.ibs_cbs` nos itens e bloqueiam ICMS, ISSQN, IPI, II, PIS, COFINS, ICMS UF Destino e imposto devolvido.
- Classe fiscal NF-e com IBS/CBS persiste `situacao_tributaria`, `classificacao_tributaria` e grupos condicionais.
- Regime tributario de `WebmaniaCompany` participa da validacao quando aplicavel, mas nao substitui a classificacao tributaria.
- Usuario sem permissao administrativa nao altera configuracao IBS/CBS.
- Usuario de outra oficina nao visualiza nem usa classe IBS/CBS de outra oficina.
- Payload/log sanitizados nao expoem credenciais, certificado, CSC, tokens ou headers.

Testes por subfase:

| Subfase | Testes obrigatorios |
| ------- | ------------------- |
| 2.4A | Criar/editar classe NF-e com IBS/CBS; validar situacao/classificacao; bloquear classe incompleta; permissao e cross-workshop. |
| 2.4B | NF-e/NFC-e normal com IBS/CBS; bloqueio producao sem configuracao; homologacao controlada; snapshot do payload. |
| 2.4C | Devolucao/estorno, complementar preco/quantidade e ajuste com regra propria; nenhum derivado altera original; `uncertain` preserva payload. |
| 2.4D | Evento IBS/CBS e cancelamento com sequencia/idempotencia; webhook duplicado/fora de ordem; permissao restrita. |
| 2.4E | Credito/debito com `finalidade=5/6`; tipos oficiais; tributos incompatíveis bloqueados antes do gateway; feature flag/habilitacao por oficina. |

Resultado da Fase 2.4A+B:

- Classes `FiscalPhaseTwoIbsCbsTaxClassTests` e `FiscalPhaseTwoIbsCbsNormalEmissionTests` cobrem validacao de situacao/classificacao, condicionais `620`/`811`, chave JSON desconhecida, sincronizacao de classe com `ibs_cbs`, permissao administrativa, escopo por oficina, bloqueio NF-e/NFC-e sem classe pronta, homologacao exigindo configuracao e preservacao de idempotencia.
- A validacao direcionada executada com as fases fiscais anteriores totalizou 99 testes aprovados.

Impacto operacional:

- Antes de liberar nova emissao em producao, executar testes direcionados das fases 1, 2.1, 2.2A, 2.2B.1, 2.2C, 2.3.1, 2.3.2, 2.3.3 e a classe da subfase 2.4.
- Rodar `makemigrations finance --check --dry-run`, `ruff check` nos Python tocados e `git diff --check`.

### Fase 2.4C.0 - Testes planejados para derivados com IBS/CBS

Testes transversais:

- Documento derivado usa snapshot tributario da NF-e original local, nao a classe fiscal atual alterada depois da emissao.
- Classe fiscal atual IBS/CBS-ready so pode ser usada como apoio quando o snapshot original estiver ausente e houver confirmacao fiscal explicita.
- NF-e externa minima por chave bloqueia operacoes que dependam de itens/sequenciais/snapshot IBS-CBS.
- Payload congelado com IBS/CBS nao muda apos tentativa `sent` ou `uncertain`.
- Webhook e reconciliacao atualizam somente o derivado e nao recalculam IBS/CBS.
- Usuario de outra oficina nao acessa snapshot, payload, XML/DANFE nem action derivada.
- Logs de bloqueio nao expoem payload completo, credenciais, CSC, certificado, headers ou tokens.

Testes 2.4C.1 - Devolucao/estorno:

- Devolucao parcial local inclui IBS/CBS derivado do item original e preserva `produtos` como sequenciais fiscais.
- `quantidade[i]` continua alinhada a `produtos[i]` apos incluir IBS/CBS.
- Devolucao total nao envia selecao parcial desnecessaria.
- Faixa de saldo considera derivado `uncertain` com payload IBS/CBS congelado.
- NF-e externa minima bloqueia devolucao parcial.
- Estorno usa payload proprio e nao e tratado como devolucao parcial comum.

Resultado da Fase 2.4C.1:

- `FiscalPhaseTwoReturnTests` passou com 21 testes, incluindo novos cenarios de devolucao total/parcial em producao com snapshot IBS/CBS, bloqueio de snapshot ausente/incompleto, nao uso de `TaxClassNfe` atual divergente e estorno com payload proprio.
- `FiscalPhaseTwoReturnConcurrentTests` passou apos recriacao limpa da base de teste e tambem dentro da suite direcionada final com `--keepdb`.
- A suite fiscal direcionada final passou com 100 testes.
- `makemigrations finance --check --dry-run`, `ruff check apps/finance/services/nfe_returns.py apps/finance/tests.py` e `git diff --check` passaram.

Testes 2.4C.2 - Complementar preco/quantidade:

- Complemento apenas de preco envia somente acrescimo e IBS/CBS aplicavel ao acrescimo.
- Complemento apenas de quantidade envia somente quantidade adicional e IBS/CBS aplicavel.
- Complemento simultaneo, se autorizado, prova payload explicito para os dois acrescimos.
- Payload nao envia objeto de complementar tributaria ampla, ICMS-ST/IPI/ISSQN/IBS-CBS fora do subtipo aprovado, agropecuario ou importacao/adicao.
- NF-e externa minima permanece bloqueada sem XML/importacao validada.

Testes 2.4C.3 - Ajuste:

- Ajuste continua sem `produtos`, `pedido`, `impostos`, `ibs_cbs` ou grupos de produto quando o contrato oficial nao confirmar esses campos.
- Ajuste bloqueia `tipo_credito`, `tipo_debito`, `finalidade=5/6`, `dfe_referenciado`, `evento_ibs_cbs`, `cod_evento`, `produtos` e `impostos.ibs_cbs` antes do gateway.
- Regime tributario continua bloqueando Simples Nacional, MEI e desconhecido.
- Cenario de estorno SC/ES continua direcionado para devolucao/estorno.
- Se a operacao fiscal selecionada depender de Reforma Tributaria, o service bloqueia antes do gateway ate regra IBS/CBS aprovada.
- Regressao: idempotencia, concorrencia, timeout `uncertain`, webhook, reconciliacao, documento vinculado, cross-workshop, downloads e sanitizacao devem continuar passando na suite de ajuste existente.

## Fase 2.4D.0 - Testes planejados para Eventos IBS/CBS

Contrato e payload:

- Evento `112110` envia apenas `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao` quando configurada.
- Eventos com itens usam `itens[].item` como numero sequencial fiscal da NF-e/NFC-e, nao ID interno.
- Evento `112150` valida `data_previsao_entrega`.
- Evento `211128` permanece bloqueado enquanto credito/debito nao estiverem implementados.
- Campos de credito/debito, complementar tributaria, ajuste, cancelamento de nota e contingencia nao entram no payload de evento.

Documento e modelagem:

- Cria `FiscalDocumentEvent(event_type=ibs_cbs)`, nao cria `FiscalDocument` novo.
- Evento fica vinculado a `FiscalDocument(document_type=nfe|nfce)` da oficina ativa.
- Documento base nao tem status alterado pelo evento aprovado/reprovado.
- Ajuste, devolucao, complementar e NFC-e cancelada nao recebem evento indevido sem regra aprovada.

Idempotencia e concorrencia:

- Primeira sequencia reservada por documento e `cod_evento`.
- Segunda emissao legitima do mesmo codigo usa proxima sequencia quando permitido.
- Concorrencia da mesma intencao gera uma chamada remota.
- Mesma sequencia com payload diferente gera conflito.
- Sequencia acima de 20 e bloqueada.
- Timeout gera `uncertain`, preserva sequencia e bloqueia reenvio automatico.

Webhook/reconciliacao:

- Webhook resolve por UUID remoto do evento.
- Fallback por tentativa exige candidato unico da mesma oficina/documento/codigo/sequencia.
- Webhook duplicado nao duplica efeitos.
- Webhook fora de ordem nao regride status de evento aprovado.
- Associacao ambigua nao atualiza evento nem documento.
- Reconciliacao, se suportada por consulta oficial, consulta sem reenviar; se nao houver contrato, fica como decisao administrativa.

Cancelamento de evento:

- Cancelamento por `/1/nfe/evento-ibs-cbs/cancelar/` envia UUID do evento original e ambiente quando aplicavel.
- Cancelamento nao altera NF-e/NFC-e base.
- Evento original sem UUID remoto ou `uncertain` bloqueia cancelamento.
- Cancelamento duplicado e idempotente.

Permissao e seguranca:

- `issue_ibs_cbs_event` exigida antes do gateway.

Resultado da Fase 2.4D.1:

- `FiscalPhaseTwoIbsCbsEvent112110Tests` valida payload oficial estreito, elegibilidade, bloqueio de documento inelegivel, timeout `uncertain`, limite de sequencia, webhook por UUID, fallback por chave+sequencia, ambiguidade, permissao, cross-workshop, download e payload protegidos.
- `FiscalPhaseTwoIbsCbsEvent112110ConcurrentTests` valida concorrencia da mesma intencao com somente uma chamada remota.
- A bateria fiscal direcionada ate 2.4D.1 executou 107 testes com sucesso.

Resultado validado da Fase 2.4D.2:

- `FiscalPhaseTwoIbsCbsEvent112110CancellationTests` deve validar body com somente `uuid`, `ambiente` e `url_notificacao` quando aplicavel, ausencia de `chave`, `cod_evento`, `evento`, `ibs_cbs`, produtos e campos de credito/debito.
- Deve validar elegibilidade do evento original: `112110`, autorizado, com UUID remoto, documento base elegivel e oficina ativa.
- Deve validar timeout `uncertain`, rejeicao remota sem marcar sucesso, payload congelado, duplicidade bloqueada e evento original cancelado somente apos retorno/webhook valido.
- Deve validar webhook por UUID do cancelamento, fallback por tentativa, ambiguidade sem update, download/payload protegidos, permissao `cancel_ibs_cbs_event` e cross-workshop.
- `FiscalPhaseTwoIbsCbsEvent112110CancellationConcurrentTests` deve validar concorrencia da mesma intencao com somente uma chamada remota.
- Validacao final executou 161 testes fiscais direcionados com `--keepdb` e sucesso, incluindo as classes de Fase 1, 2.1, 2.2, 2.3, 2.4A+B, 2.4C, 2.4D.1 e 2.4D.2. O alvo solicitado `FiscalPhaseTwoAdjustmentReformTests` nao existe no modulo atual; a bateria foi repetida com os alvos existentes equivalentes, incluindo `FiscalPhaseTwoAdjustmentTests` e `FiscalPhaseTwoIbsCbsNormalEmissionTests`.
- `view_ibs_cbs_event`, `download_ibs_cbs_event` e `view_ibs_cbs_event_payload` protegem visualizacao/download/payload.
- Cross-workshop bloqueado.
- Payload/log sanitizados sem headers Webmania, tokens, CSC, certificado ou credenciais.

### Fase 2.4D.3.0 - Testes planejados para os demais Eventos IBS/CBS

Para a proxima subfase recomendada `112150`:

- payload envia somente envelope oficial, `cod_evento=112150`, `evento` e `data_previsao_entrega`;
- bloqueia ausencia/data invalida de previsao de entrega antes do gateway;
- bloqueia documento nao autorizado, sem chave, de outra oficina, derivado, ajuste ou credito/debito;
- bloqueia codigos fora de `112150`;
- idempotencia por documento/codigo/sequencia/data;
- concorrencia da mesma intencao gera uma chamada remota;
- timeout marca evento/tentativa como `uncertain` e preserva sequencia/data;
- webhook por UUID e fallback seguro atualizam somente o evento;
- documento base nao tem status alterado;
- permissoes, cross-workshop, download/payload e sanitizacao.

Resultado 2.4D.3:

- Testes adicionados: `FiscalPhaseTwoIbsCbsEvent112150Tests` e `FiscalPhaseTwoIbsCbsEvent112150ConcurrentTests`.
- Cobertura: payload oficial com `cod_evento=112150`, `evento` numerico e `data_previsao_entrega` no topo; bloqueio de data invalida; ausencia de `ibs_cbs`, `itens`, `produtos`, credito/debito e cancelamento; NF-e normal local elegivel; NFC-e/derivados/ajuste bloqueados; duplicidade da mesma data bloqueada; nova data legitima reserva nova sequencia; timeout fica `uncertain`; webhook por UUID e fallback chave+sequencia; ambiguidade rejeitada; permissao/download/payload/cross-workshop protegidos; cancelamento do `112150` nao e aceito pelo fluxo de cancelamento `112110`.

Resultado 2.4D.4:

- Testes adicionados: `FiscalPhaseTwoIbsCbsEvent112150CancellationTests` e `FiscalPhaseTwoIbsCbsEvent112150CancellationConcurrentTests`.
- Cobertura: payload de cancelamento oficial com `uuid`, `ambiente` e `url_notificacao` opcional; ausencia de `chave`, `cod_evento`, `evento`, `data_previsao_entrega`, `ibs_cbs`, produtos e payload de nota; elegibilidade por evento `112150` autorizado com UUID; bloqueio de sem UUID, rejeitado/falho, incerto, ja cancelado, outro codigo e outra oficina; criacao de evento auditavel de cancelamento; nenhuma criacao de `FiscalDocument`; idempotencia, concorrencia, timeout `uncertain`, webhook por UUID/tentativa, ambiguidade, permissao, download/payload e sanitizacao.

Para Grupo B (`112120`, `112130`, `112140`) quando autorizado:

- `112120`: payload com `cod_evento=112120`, `itens[].item` como sequencial fiscal, `valor_ibs`, `valor_cbs`, `controle_estoque.quantidade` e `controle_estoque.unidade`; bloqueio sem contexto ALC/ZFM/importacao; bloqueio de NF-e externa minima.
- `112130`: payload com `cod_evento=112130`, `quantidade_perecimento`, `unidade_perecimento`, `valor_ibs_estorno` e `valor_cbs_estorno`; bloqueio sem evento operacional de transporte/estoque; estorno IBS/CBS obrigatorio.
- `112140`: payload com `cod_evento=112140`, item da nota de debito/pagamento antecipado, `quantidade_nao_fornecida` e `unidade_nao_fornecida`; bloqueio ate existir origem de pagamento antecipado confiavel.
- Para todos: `itens[].item` deve ser sequencial fiscal, nao ID interno; `valor_ibs`/`valor_cbs` obrigatorios; snapshot fiscal original exigido; `TaxClassNfe` atual como fallback automatico deve ser bloqueado; divergencia entre itens selecionados e nota base deve bloquear antes do gateway.
- Idempotencia: mesma intencao faz uma chamada remota; concorrencia da mesma intencao gera uma chamada; payload congelado; timeout marca `uncertain`; `uncertain` bloqueia reenvio automatico e preserva itens/valores.
- Webhook: UUID remoto atualiza somente o evento; fallback por tentativa/chave+sequencia exige candidato unico; ambiguidade nao atualiza.
- Regressao obrigatoria: eventos `112110`, cancelamento `112110`, `112150` e cancelamento `112150` continuam passando.

Para Grupo C/D:

- testes iniciais devem provar bloqueio por ausencia de credito/debito, papel destinatario, documento de aquisicao ou apuracao externa antes de qualquer chamada remota.
### Testes adicionados na Fase 2.4D.5.1

- `FiscalPhaseTwoIbsCbsEvent112130Tests`: payload oficial com `itens[]`, ausencia de top-level `ibs_cbs`, bloqueios de documento inelegivel, snapshot ausente, item inexistente, valores invalidos, duplicidade do mesmo payload, timeout `uncertain`, webhook por UUID/fallback/ambiguidade, permissao, cross-workshop, downloads e payload protegidos.
- `FiscalPhaseTwoIbsCbsEvent112130ConcurrentTests`: duas requisicoes concorrentes da mesma intencao resultam em uma unica chamada remota e um unico evento local.
- Regressao executada junto das suites fiscais direcionadas de Fase 1, CC-e, devolucao/estorno, complementar, ajuste, NFC-e simples, inutilizacao, IBS/CBS normal, derivados IBS/CBS e eventos `112110/112150`.

### Testes adicionados na Fase 2.4D.5.2

- `FiscalPhaseTwoIbsCbsEvent112130CancellationTests`: payload oficial de cancelamento com somente `uuid`, `ambiente` e `url_notificacao` quando aplicavel; ausencia de `chave`, `cod_evento`, `evento`, `itens`, `controle_estoque`, `ibs_cbs`, produtos, credito/debito e campos de documento; bloqueio de evento sem UUID, falho/rejeitado/incerto, outro codigo, documento base cancelado e cancelamento duplicado/incerto; timeout `uncertain`, rejeicao remota sem marcar sucesso, payload congelado, webhook duplicado/idempotente e ambiguidade sem update; permissao, confirmacao explicita, cross-workshop, downloads e payload protegidos.
- `FiscalPhaseTwoIbsCbsEvent112130CancellationConcurrentTests`: duas requisicoes concorrentes da mesma intencao de cancelamento resultam em uma unica chamada remota e um unico evento de cancelamento local.

### Testes planejados apos Fase 2.4D.6.0

Para `112120`, se houver fase futura:

- payload oficial com `cod_evento=112120`, `evento` numerico, `itens[].item` como sequencial fiscal, `valor_ibs`, `valor_cbs`, `controle_estoque.quantidade` e `controle_estoque.unidade`;
- bloqueio sem NF-e de importacao local/XML validada, sem contexto ALC/ZFM, sem snapshot IBS/CBS, sem sequencial fiscal ou com documento externo minimo;
- idempotencia, concorrencia, timeout `uncertain`, webhook por UUID/fallback, permissao, cross-workshop, sanitizacao e regressao dos eventos ja validados.

Para `112140`, se houver fase futura:

- payload oficial com `cod_evento=112140`, `itens[].item` da nota de debito de pagamento antecipado, `valor_ibs`, `valor_cbs`, `controle_estoque.quantidade_nao_fornecida` e `controle_estoque.unidade_nao_fornecida`;
- bloqueio sem nota de debito/pagamento antecipado, sem vinculo financeiro-item fiscal, sem snapshot IBS/CBS, sem sequencial fiscal ou sem quantidade nao fornecida auditavel;
- bloqueio ate credito/debito IBS/CBS ou fluxo fiscal equivalente estar implementado e aprovado;
- idempotencia, concorrencia, timeout `uncertain`, webhook por UUID/fallback, permissao, cross-workshop, sanitizacao e regressao de `112110`, `112150`, `112130` e cancelamentos.

Para cancelamento futuro de `112120`/`112140`:

- criar testes especificos por codigo somente apos emissao do codigo correspondente existir;
- payload restrito a `uuid`, `ambiente` e `url_notificacao` quando aplicavel;
- nao alterar `FiscalDocument` base nem criar cancelamento generico.
### Fase 2.5.1.0 - Testes planejados para credito/debito

- `finalidade=5` exige `tipo_credito` permitido; `finalidade=6` exige `tipo_debito` permitido.
- Credito serializa `nfe_referenciada[]` apenas a partir de referencias validadas.
- Debito tipos `3`/`4` exigem `dfe_referenciado` dentro de cada produto e rejeitam chave/item ausente.
- Cada produto envia `codigo_cfop` na raiz e somente `impostos.ibs_cbs`; tributos incompatíveis falham antes do gateway.
- Tipos sem fonte local, documento externo sem XML/importacao validada, ausencia de item fiscal, apuracao ou vinculo financeiro exigido ficam bloqueados.
- Documento/tentativa existem antes do gateway; retry e concorrencia fazem uma chamada; timeout vira `uncertain` e reconciliacao somente consulta.
- Webhook atualiza somente o credito/debito correto; eventos IBS/CBS existentes nao regridem.
- Permissao, feature flag, habilitacao por oficina, cross-workshop, payload/download e sanitizacao possuem cobertura dedicada.
- Testes de regressao preservam emissoes normais, derivados e eventos `112110`, `112130`, `112150` e cancelamentos.

### Evidencias executadas na Fase 2.5.1P

- 13 testes focados cobrem criacao, sequencial, snapshot, ausencia/incompletude, ausencia de fallback `TaxClassNfe`, imutabilidade, referencias, hipotese desconhecida, flag, tenancy, XML externo, permissao e ausencia de operation types de emissao.
- Regressao fiscal direcionada: 192 testes das Fases 1 a 2.4D mais a base 2.5.1P passaram com PostgreSQL e `--keepdb`.
- `makemigrations finance --check --dry-run`, ruff dos Python tocados e `git diff --check` compoem o fechamento.

## Fase 2.5.2.0 - Testes planejados

Para 2.5.2P: snapshot comercial por item; valores `Decimal`; decomposicao principal/multa/juros; soma consistente; movimento financeiro e item da mesma oficina; imutabilidade; flag de preparacao sem emissao.

Para futura emissao credito tipo 1: base aprovada; `finalidade=5`; `tipo_credito=1`; `nfe_referenciada[]`; CFOP na raiz; somente `impostos.ibs_cbs`; bloqueio preventivo de ICMS/IPI/PIS/COFINS/ISSQN; documento/tentativa antes do gateway; concorrencia; timeout `uncertain`; webhook; reconciliacao sem emissao; permissoes; cross-workshop; sanitizacao; XML/DANFE; regressao de eventos IBS/CBS.
## Testes Fase 2.5.2P

- Extracao historica por sequencial de descricao, NCM, CFOP, quantidade, unidade, unitario e total.
- Persistencia exclusiva em `Decimal`, consistencia com tolerancia de R$ 0,01 e rejeicao de negativos.
- Composicao multa + juros para hipotese tipo 1; composicao integral nas demais hipoteses.
- Rascunho incompleto permitido e aprovacao incompleta bloqueada.
- Imutabilidade comercial, monetaria, CFOP e item apos aprovacao.
- Ausencia de fallback por cadastro/`TaxClassNfe`, de documento derivado, tentativa remota e chamada Webmania.
- Permissao, tenancy, feature flag e sanitizacao continuam cobertas pela suite 2.5.1P.
## Testes planejados - futura emissao credito tipo 1

- Exige `FiscalReferencedBasis` aprovada e `FiscalReferencedBasisItem` completo/imutavel.
- Bloqueia base nao aprovada, snapshot ausente, chave/CFOP ausentes, documento externo sem XML validado e `multa + juros <= 0`.
- Payload fixa `finalidade=5`, `tipo_credito=1`, `nfe_referenciada[]`, CFOP na raiz e somente `impostos.ibs_cbs`.
- Rejeita ICMS, IPI, PIS, COFINS, ISSQN, II, imposto devolvido, `tipo_debito`, `dfe_referenciado` e campos de evento IBS/CBS.
- Valida regra fiscal aprovada de quantidade, unitario, total e IBS/CBS sem inferencia/copia silenciosa.
- Cria documento/link/tentativa antes do gateway; retry/concorrencia fazem uma chamada; timeout fica `uncertain`.
- Duas intencoes legitimas usam documentos distintos; payload enviado e imutavel.
- Webhook/reconciliacao atualizam somente o credito; original e eventos nao mudam; reconciliacao nunca emite.
- Permissao `issue_nfe_credit`, feature flag de emissao, tenancy, sanitizacao e downloads protegidos.
- Regressao da base 2.5.1P/2.5.2P e dos eventos IBS/CBS.
## Testes implementados - Fase 2.5.3P

- Preview exige base aprovada, item congelado, hipotese multa/juros, flag e oficina correta.
- Quantidade/unitario/total positivos, confirmados explicitamente e reconciliados com `multa + juros`.
- Produto usa identidade historica e somente IBS/CBS historico; `TaxClassNfe` e cadastro atual nao sao fallback.
- Detector bloqueia tributos tradicionais, tipo debito, DF-e por item e campos de evento.
- Preview aprovado e imutavel; payload protegido por permissao/tenancy e sanitizado.
- Contagens provam ausencia de documento/tentativa; choices provam ausencia de `nfe_credit_emission`.

## Testes Fase 2.5.4

Cobertura: contrato finalidade/tipo, somente IBS/CBS, campos proibidos, preview/base/flag/permissao, tenancy, documento/link/tentativa antes do gateway, retry, concorrencia real, timeout `uncertain`, resposta rejeitada, webhook idempotente/ambiguo, reconciliacao sem emissao, downloads/payload sanitizados e regressao fiscal das fases anteriores.

## Testes Fase 2.5.5

Cobertura: elegibilidade por tipo/status/flag; motivo e confirmacao; payload somente com identificador e motivo; evento/tentativa antes do gateway; nenhuma nova nota; imutabilidade da origem/base/preview; concorrencia real; timeout `uncertain`; rejeicao com XML; webhook idempotente e ambiguo; reconciliacao sem `PUT`; permissoes, tenancy, download e payload sanitizado; regressao fiscal integral.

## Testes planejados - Preview de debito tipo 4

- cria preview somente a partir de base/item aprovados;
- persiste `finalidade=6`, `tipo_debito=4`, chave e item em `dfe_referenciado`;
- congela produto, CFOP, snapshots comercial/monetario e IBS/CBS;
- valida composicao multa + juros positiva e coerente;
- bloqueia base/item incompletos, valores zero/negativos e CFOP ausente;
- bloqueia ICMS, IPI, PIS, COFINS, ISSQN, II e grupos estranhos;
- bloqueia uso de `FiscalCreditProductPreview`, `TaxClassNfe` atual ou cadastro atual como fallback;
- exige feature flag e permissoes preparatorias proprias;
- bloqueia cross-workshop e protege payload;
- payload aprovado fica imutavel;
- nao cria `FiscalDocument`, `FiscalEmissionAttempt`, webhook/reconciliacao ou chamada HTTP;
- regressao: credito tipo 1 e eventos IBS/CBS existentes permanecem operacionais;
- demais creditos/debitos continuam indisponiveis.

Testes de emissao, idempotencia remota, concorrencia de gateway, timeout, webhook, reconciliacao, downloads e cancelamento pertencem a fases funcionais posteriores.

### Evidencia executada em 2026-06-22

- `FiscalPhaseTwoDebitProductPreviewTests`: 14/14 testes passaram.
- regressao direta de base, previews e ciclo de credito: 80/80 testes passaram.
- suite fiscal dirigida completa: 260/260 testes passaram.
- `makemigrations finance --check --dry-run`, Ruff dos arquivos tocados e `git diff --check`: aprovados.
- o alvo solicitado `FiscalPhaseTwoCreditTypeOneEmissionTests` nao existe; foram usados os equivalentes reais `FiscalPhaseTwoCreditTypeOneTests` e `FiscalPhaseTwoCreditTypeOneConcurrentTests`.

## Testes planejados - Emissao de debito tipo 4

### Evidencia executada - Fase 2.5.7

- 16 testes especificos de debito tipo 4 aprovados, incluindo `TransactionTestCase` concorrente.
- 276 testes fiscais dirigidos aprovados com `--keepdb`.
- `makemigrations finance --check --dry-run`, Ruff dos arquivos tocados e `git diff --check` aprovados.
- Regressao atualizada: preparar base/preview nao emite, embora o operation type de debito agora exista legitimamente.

## Evidencia executada - Fase 2.5.8

- 10 testes especificos de cancelamento de debito tipo 4 aprovados, incluindo concorrencia transacional.
- 51 testes cruzados de emissao/cancelamento de credito e debito aprovados.
- 286 testes fiscais dirigidos aprovados com `--keepdb`.
- Contrato, permissao isolada, tenancy, sanitizacao, webhook ambiguo e reconciliacao sem reenvio comprovados.

## Testes planejados para a expansao NFS-e

A Fase 3.0 deve produzir casos de teste detalhados, sem implementa-los, cobrindo:

- capacidades municipais bloqueando emissao, cancelamento, substituicao ou manifestacao nao suportada;
- payload ISS/IBS-CBS e Padrao Nacional conforme municipio, provedor, ambiente e regime;
- RPS, lote e item preservando identidade e sequencia;
- concorrencia com uma chamada remota por intencao, retry idempotente e timeout `uncertain`;
- webhook duplicado e fora de ordem sem regressao de status;
- reconciliacao usando somente consulta, sem POST de emissao/substituicao/manifestacao;
- substituicao vinculando novo documento sem mutar incorretamente o original;
- manifestacao com papel, motivo e estado validos;
- isolamento por oficina, permissoes separadas, downloads protegidos e sanitizacao de credenciais;
- regressao dos fluxos NFS-e legados durante a convivencia.

Operacionalmente, a futura liberacao deve ser incremental por oficina/municipio, com checklist de capacidades, homologacao previa e rollback que desative novas operacoes sem apagar documentos ou eventos persistidos.

### Matriz minima de testes 3.x

- emissao simples sincrona e retorno `nfse`;
- emissao/lote assincrono e multiplos RPS;
- consulta de item e lote por UUID;
- cancelamento elegivel, rejeitado, concorrente e timeout `uncertain`;
- substituicao criando novo documento e preservando o substituido;
- manifestacao de tomador/intermediario, confirmacao/rejeicao e justificativa condicional;

## Testes planejados para Fase 3.6.x - manifestacao NFS-e Padrao Nacional

- manifesta NFS-e elegivel Padrao Nacional;
- bloqueia NFS-e municipal legada;
- bloqueia NFS-e cancelada;
- bloqueia NFS-e substituida;
- bloqueia NFS-e `uncertain`;
- bloqueia NFS-e sem UUID/chave suficiente;
- bloqueia feature flag/capability desligada;
- bloqueia usuario sem `issue_nfse_manifestation`;
- valida payload por tipo: confirmacao e rejeicao;
- exige justificativa quando `motivo_rejeicao=9`;
- idempotencia nao reenvia;
- concorrencia gera uma unica chamada remota;
- timeout marca `uncertain`;
- webhook com UUID atualiza somente a manifestacao;
- webhook ambiguo fica pendente;
- reconciliacao nao executa POST;
- payload e resposta sao sanitizados;
- cross-workshop bloqueado;
- regressao de cancelamento e substituicao NFS-e permanece intacta.

Resultado 3.6.1: adicionados testes direcionados para contrato/payload, rejeicao com motivo/justificativa, bloqueios por status/capability/Padrao Nacional, timeout `uncertain`, webhook/reconciliacao sem alterar a NFS-e original e payload protegido por view.
- webhook duplicado, fora de ordem por `atualizado_em`, ambiguo e anterior a sincronizacao local;
- reconciliacao de `uncertain` somente por GET;
- municipio inativo, sem homologacao, sem lote, sem cancelamento, sem substituicao ou fora do Padrao Nacional;
- RPS/serie/lote concorrentes sem duplicidade;
- permissao legada preservada e novas permissoes isoladas;
- cross-workshop em lista, detalhe, operacao, payload e download;
- XML/PDF/RPS autenticados e indisponibilidade de PDF tratada;
- segredos e payloads sanitizados;
- regressao do wizard por OS, modo NF-e+NFS-e, pricing slider, NF-e/NFC-e e eventos IBS/CBS.

Rollback: flags desligam novas operacoes e capacidades sem apagar legado. Migrations futuras devem ser aditivas; projecoes `FiscalDocument` nao podem assumir ownership exclusivo antes de backfill separado e aprovado.
- cria documento `nfe/debit/4` somente de preview/base aprovadas e locais;
- cria link `debits` e preserva original/base/item/preview;
- payload usa `modelo=1`, `finalidade=6`, `tipo_debito=4` e nao usa `nfe_referenciada`;
- cada produto preserva `codigo_cfop`, valores e `dfe_referenciado` da preview;
- envia somente `impostos.ibs_cbs`; bloqueia ICMS/IPI/PIS/COFINS/ISSQN/II, imposto devolvido, credito e eventos;
- bloqueia snapshots/CFOP/referencia/valores ausentes ou divergentes;
- exige flag de emissao e `issue_nfe_debit`; permissoes preparatorias ou de credito nao bastam;
- bloqueia cross-workshop, origem externa e duplicidade por preview;
- documento existe antes do gateway; uma chamada por intencao e concorrencia;
- timeout/resposta incerta geram `uncertain` e bloqueiam retry;
- webhook atualiza somente debito correto; ambiguidade nao atualiza;
- reconciliacao consulta sem emitir; XML/DANFE e payload respeitam tenancy/permissao;
- rejeicao com XML nao vira sucesso; payload/log ficam sanitizados;
- regressao completa de credito tipo 1, NF-e/NFC-e e eventos IBS/CBS.

## Evidencia da Fase 3.1

Executados 13 testes especificos de capacidade, compatibilidade, webhook, sanitizacao, reconciliacao e permissao. A regressao fiscal dirigida totalizou 297 testes e concluiu com `OK`. A primeira execucao ampla foi interrompida exclusivamente pelo limite de 300 segundos; a repeticao com janela suficiente concluiu em 410,316 segundos sem falhas.

## Evidencia da Fase 3.2

- 14 testes especificos: item/lote, identidade, ambiguidade, transacao, anti-regressao, capacidade, status municipal, permissao, tenancy, comando e webhook compartilhado.
- 2 testes legados de consulta por view confirmaram a compatibilidade de `change_nfserequest`.
- 311 testes fiscais direcionados concluidos em 425,444 segundos com `OK`.
- Migration-check, Ruff e diff-check aprovados.
## Fase 3.3 - cobertura obrigatoria

Contrato restrito a `uuid`/`motivo`; elegibilidade; capacidade municipal; permissao e tenancy; payload imutavel; concorrencia com uma chamada; timeout `uncertain`; rejeicao sem falso sucesso; webhook anti-regressao; reconciliacao somente consultiva; XML separado do documento original; regressao de emissao, consulta e downloads legados.

## Testes planejados para Fase 3.4P e substituicao futura

- preview exige original autorizada, UUID, codigo de verificacao, XML, motivo e novo RPS completo;
- bloquear original cancelada, substituida, `uncertain`, sem XML ou de outra oficina;
- snapshot de tomador, servico, valores, impostos/retencoes e RPS permanece imutavel apos aprovacao;
- dados atuais da OS, cliente ou classe fiscal nao alteram preview aprovada;
- capability, feature flag e permissoes separadas; preparar/aprovar nao transmite;
- fase funcional: payload exato, uma chamada por preview, concorrencia, timeout `uncertain` e nenhum reenvio;
- retorno/webhook associa `nfse_substituida` a original correta, preserva XML original e separa XML substituto;
- ambiguidade nao atualiza documentos; reconciliacao somente consulta;
- cancelamento idempotente da Fase 3.3 e emissao/consulta/downloads legados nao regridem.

Cobertura implementada na 3.4P: payload exato; original inelegivel; UUID/codigo/XML; RPS/tomador/servico/valor; flag/capability; oficina/permissoes; uma preview aprovada por original; imutabilidade de payload/XML/estado; ausencia de POST/PUT, `FiscalEmissionAttempt`, item substituto e alteracao da original; regressao do cancelamento NFS-e.

Cobertura 3.4.1: body exato sem `uuid`; preview/original/flag/capability; confirmacao cruzada da original; criacao tardia da substituta; XMLs separados; rejeicao; timeout/uncertain; retry; concorrencia; webhook direto e fallback; duplicidade; anti-regressao; GET sem POST; permissao/tenancy e regressao 3.1-3.4P.

## Testes planejados pela Fase 3.7.0

Para a fase preparatoria recomendada (`3.7P - Preview de emissao manual nova de NFS-e`):

- cria preview sem chamada HTTP;
- congela tomador, endereco, servico, codigo municipal, discriminacao, valores, retencoes, ISS, IBS/CBS, ambiente e municipio;
- bloqueia capability ausente/inativa, feature flag desligada, usuario sem permissao e cross-workshop;
- valida payload planejado sem depender de dados mutaveis de OS, cliente, servico ou classe fiscal apos aprovacao;
- aprovacao torna payload e snapshot imutaveis;
- preparar/aprovar nao cria `FiscalEmissionAttempt`, `NfseItem` emitido, webhook, reconciliacao ou download remoto;
- payload protegido exige permissao propria;
- regressoes: emissao legada por OS, consulta, cancelamento, substituicao e manifestacao NFS-e continuam intactas.

Testes da fase funcional posterior, ainda nao autorizada: uma chamada por preview aprovada, concorrencia, timeout `uncertain`, webhook NFS-e por UUID, reconciliacao sem POST, downloads protegidos e bloqueio de duplicidade RPS/numeracao.
