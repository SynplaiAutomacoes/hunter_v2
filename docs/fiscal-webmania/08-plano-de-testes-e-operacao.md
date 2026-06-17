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
| 7 | DC-e beta isolada, feature flag e cancelamento | Desativacao segura |
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

- testes de `itens[].item` como sequencial fiscal;
- valores IBS/CBS e `controle_estoque` obrigatorios por codigo;
- bloqueio de saldo/quantidade/controle insuficiente antes do gateway;
- timeout e duplicidade com payload congelado.

Para Grupo C/D:

- testes iniciais devem provar bloqueio por ausencia de credito/debito, papel destinatario, documento de aquisicao ou apuracao externa antes de qualquer chamada remota.
