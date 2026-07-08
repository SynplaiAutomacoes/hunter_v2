# Plano de testes e operacao fiscal

## Fase 4.0.3 - Testes de permissoes NF-e normal

- Criar testes focados para `NfeRequest` cobrindo UI e backend.
- Cancelamento: permissao dedicada, ausencia de permissao, fallbacks `change_nferequest`/`change_nfserequest` e separacao contra permissao de inutilizacao.
- Inutilizacao: permissao dedicada, ausencia de permissao, fallbacks `change_nferequest`/`change_nfserequest` e separacao contra permissao de cancelamento.
- Downloads: `download_nferequest_xml`, `download_nferequest_pdf`, fallback `view_nferequest`/`change_nferequest`, bloqueio sem permissao e cross-workshop.
- Payload/resposta remota: confirmar permissoes criadas sem nova view nesta fase.
- Regressao: executar bateria fiscal direcionada NF-e/NFC-e relevante; confirmar que nao houve novo endpoint remoto, payload fiscal novo ou regra fiscal nova.

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

### Fase 3.7.1 - testes de emissao manual NFS-e

Cobertura adicionada em `FiscalPhaseThreeNfseManualEmissionTests`:

- envio de `POST /2/nfse/emissao` usando exatamente `request_payload` da preview aprovada;
- criacao de `NfseManualEmission`, tentativa `nfse_manual_emission` e `NfseItem` somente apos resposta aprovada;
- bloqueios para preview em rascunho, feature flag desligada, capability desligada, RPS reservado/duplicado e retry;
- timeout para `uncertain` sem reenvio;
- webhook e reconciliacao consultiva sem repetir POST;
- permissoes especificas e cross-workshop para payload.

Regressoes obrigatorias continuam cobrindo cancelamento, preview/substituicao, manifestacao e preview manual.

- cria preview sem chamada HTTP;
- congela tomador, endereco, servico, codigo municipal, discriminacao, valores, retencoes, ISS, IBS/CBS, ambiente e municipio;
- bloqueia capability ausente/inativa, feature flag desligada, usuario sem permissao e cross-workshop;
- valida payload planejado sem depender de dados mutaveis de OS, cliente, servico ou classe fiscal apos aprovacao;
- aprovacao torna payload e snapshot imutaveis;
- preparar/aprovar nao cria `FiscalEmissionAttempt`, `NfseItem` emitido, webhook, reconciliacao ou download remoto;
- payload protegido exige permissao propria;
- regressoes: emissao legada por OS, consulta, cancelamento, substituicao e manifestacao NFS-e continuam intactas.

Testes da fase funcional posterior, ainda nao autorizada: uma chamada por preview aprovada, concorrencia, timeout `uncertain`, webhook NFS-e por UUID, reconciliacao sem POST, downloads protegidos e bloqueio de duplicidade RPS/numeracao.

## Testes planejados pela Fase 3.8.0

Para a fase recomendada (`3.8.1 - Cancelamento da NFS-e Manual Nova`):

- cancela NFS-e manual autorizada vinculada a `NfseManualEmission.nfse_item`;
- envia somente `{uuid, motivo}` para `PUT /2/nfse/cancelar`;
- exige UUID seguro, oficina ativa, capability de cancelamento e permissao `cancel_nfse`;
- bloqueia preview aprovada sem emissao, emissao `sent/uncertain/failed`, NFS-e sem UUID, NFS-e ja cancelada, substituida ou com cancelamento ativo/incerto;
- cria/reutiliza `NfseCancellation` e `FiscalEmissionAttempt(operation_type="nfse_cancellation")`;
- timeout vira `uncertain` e bloqueia retry automatico;
- webhook por UUID atualiza apenas cancelamento/NFS-e manual correspondente;
- webhook ambiguo fica pendente;
- reconciliacao usa GET/consulta e nunca repete PUT;
- XML de cancelamento fica separado do XML original;
- payload/downloads sanitizados e protegidos;
- regressao: cancelamento NFS-e legado, substituicao NFS-e, manifestacao NFS-e e emissao manual 3.7.1 continuam funcionando.

Cobertura adicionada na Fase 3.8.1 em `FiscalPhaseThreeNfseManualEmissionTests`:

- contrato remoto estrito para cancelamento manual;
- bloqueios de status, UUID inelegivel, capability desligada, emissao manual incerta e duplicidade incerta;
- preservacao de `NfseManualEmissionPreview`, `NfseManualEmission.request_payload` e XML original;
- webhook e reconciliacao sem novo `PUT`;
- payload protegido e cross-workshop nas views manuais.

Regressao executada junto com `FiscalPhaseThreeNfseCancellationTests` e previews/emissao manual.

## Testes planejados pela Fase 3.9.0

Para a fase recomendada (`Substituicao da NFS-e Manual`):

- prepara preview de substituicao a partir de NFS-e manual autorizada;
- bloqueia NFS-e manual sem `NfseItem`, sem UUID, sem `codigo_verificacao`, cancelada, substituida, incerta ou com cancelamento/substituicao ativa;
- exige `substitution_enabled`, flag administrativa, permissao e oficina ativa;
- preview congela novo RPS e snapshot da original manual sem recalcular dados de emissao manual;
- aprovacao torna preview imutavel;
- transmissao envia exatamente `POST /2/nfse/substituir` com `ambiente`, `codigo_verificacao`, `motivo` e `rps`, sem `uuid`, payload de emissao manual ou payload de cancelamento;
- cria `NfseSubstitution`, tentativa `nfse_substitution` e nova `NfseItem` substituta somente com confirmacao remota valida;
- preserva XML original manual e armazena XML/PDF da substituta separadamente;
- timeout ou resposta inconclusiva marca `uncertain` e bloqueia retry automatico;
- webhook resolve substituta por UUID e confirma `nfse_substituida` contra a original manual;
- reconciliacao usa GET e nunca repete POST;
- payload/downloads protegidos por permissao e cross-workshop;
- regressoes: substituicao legada, cancelamento manual, manifestacao NFS-e, emissao manual e cancelamento legado continuam funcionando.

Nenhum teste funcional foi criado na Fase 3.9.0 porque ela e documental.

## Cobertura adicionada na Fase 3.9.1

Novos testes em `FiscalPhaseThreeNfseManualEmissionTests` cobrem:

- preview de substituicao para NFS-e manual autorizada;
- bloqueios de status cancelado/substituido/uncertain, codigo de verificacao ausente, XML ausente, capability desligada, emissao manual incerta, cancelamento ativo e substituicao incerta;
- contrato remoto exato de `POST /2/nfse/substituir` usando somente `ambiente`, `codigo_verificacao`, `motivo` e `rps`;
- preservacao de `NfseManualEmissionPreview`, `NfseManualEmission.request_payload` e XML original;
- criacao de nova `NfseItem` substituta somente apos confirmacao remota valida;
- ausencia de `FiscalDocument(nfse)`, cancelamento e manifestacao;
- webhook e reconciliacao sem novo POST;
- acao de preparar substituicao no detalhe da emissao manual condicionada a permissao.

Validacoes executadas na fase:

- `FiscalPhaseThreeNfseManualEmissionTests`: 13 testes OK.
- `FiscalPhaseThreeNfseSubstitutionPreviewTests`, `FiscalPhaseThreeNfseSubstitutionTests`, `FiscalPhaseThreeNfseSubstitutionConcurrentTests`, `FiscalPhaseThreeNfseManualEmissionPreviewTests`, `FiscalPhaseThreeNfseManualEmissionTests` e `FiscalPhaseThreeNfseCancellationTests`: 52 testes OK.
- `FiscalPhaseThreeNfseManifestationTests`: 6 testes OK.
- `makemigrations finance --check --dry-run`: OK, sem migration.
- `ruff check` nos arquivos Python tocados: OK.
- `git diff --check`: OK.
- `mypy .`: nao bloqueante; falhou no baseline preexistente com 3205 erros em 261 arquivos, incluindo stubs ausentes e managers Django nao resolvidos.

## Testes planejados pela Fase 3.10.0

Nenhum teste funcional foi criado na Fase 3.10.0 porque ela e documental.

Se uma fase futura de manifestacao manual for aprovada, a cobertura minima devera incluir:

- manifesta NFS-e manual Padrao Nacional autorizada apenas quando o papel fiscal estiver confirmado;
- manifesta NFS-e manual substituta Padrao Nacional somente se a substituta estiver autorizada e o papel fiscal estiver confirmado;
- bloqueia NFS-e manual cancelada;
- bloqueia NFS-e manual substituida;
- bloqueia NFS-e manual `uncertain`;
- bloqueia NFS-e manual sem UUID;
- bloqueia NFS-e manual sem Padrao Nacional confirmado;
- bloqueia NFS-e recebida/importada enquanto nao existir dominio proprio;
- bloqueia NFS-e municipal legada;
- exige `issue_nfse_manifestation`;
- envia somente payload do contrato atual (`ambiente`, `uuid` ou `chave`, `manifestador`, `evento`, e campos de rejeicao quando aplicavel);
- usa idempotencia por `nfse_manifestation`;
- webhook resolve somente com identificador seguro da manifestacao;
- reconciliacao consulta sem reenviar `POST /2/nfse/manifestar`;
- regressoes de emissao, cancelamento e substituicao manual continuam passando.

## Testes planejados pela Fase 3.11.0

Nenhum teste funcional foi criado na Fase 3.11.0 porque ela e documental.

Para a fase futura de registro local de NFS-e recebida, planejar:

- importa XML valido;
- bloqueia XML invalido;
- bloqueia duplicidade por hash;
- bloqueia duplicidade por UUID;
- bloqueia duplicidade por chave/identificador;
- identifica papel tomador;
- identifica papel intermediario;
- bloqueia papel prestador para manifestacao;
- bloqueia papel desconhecido;
- bloqueia CNPJ divergente;
- bloqueia cross-workshop;
- bloqueia documento cancelado/substituido/uncertain;
- protege payload/XML por permissao;
- documento recebido nao cria `NfseItem` emitido;
- documento recebido nao cria `FiscalDocument(nfse)`;
- manifestacao futura so libera documentos recebidos validados.

## Cobertura adicionada na Fase 3.11.1

Novos testes em `FiscalPhaseThreeNfseReceivedDocumentTests` cobrem:

- importacao de XML valido com snapshot/hash e papel tomador;
- roles intermediario e prestador, com prestador nao manifestavel;
- bloqueio de role desconhecido, multiplo, status cancelado e feature flag desligada;
- duplicidade por XML e colisao com NFS-e emitida localmente;
- imutabilidade de dados fiscais validados;
- payload/XML protegidos por permissoes especificas;
- ausencia de chamada Webmania, `NfseItem`, `FiscalDocument`, `FiscalEmissionAttempt` e `NfseManifestation`.

Validacoes executadas: 6 testes especificos da fase, 57 regressivos NFS-e, migration-check, Ruff focado e diff-check passaram. `mypy .` permaneceu bloqueado por baseline preexistente.

## Testes planejados pela Fase 3.12.0

Nenhum teste funcional foi criado na Fase 3.12.0 porque ela e documental.

Para `3.12.1 - Manifestacao de NFS-e Recebida`, planejar:

### Elegibilidade

- manifesta documento recebido validado como tomador;
- manifesta documento recebido validado como intermediario;
- bloqueia papel prestador;
- bloqueia papel desconhecido;
- bloqueia multiplos papeis;
- bloqueia CNPJ divergente;
- bloqueia XML invalido;
- bloqueia sem UUID;
- bloqueia sem Padrao Nacional confirmado;
- bloqueia cancelado;
- bloqueia substituido;
- bloqueia uncertain;
- bloqueia duplicado;
- bloqueia cross-workshop.

### Payload

- envia payload restrito a `ambiente`, `uuid`, `manifestador`, `evento`;
- rejeicao envia `motivo_rejeicao`;
- `justificativa_rejeicao` somente com `motivo_rejeicao=9`;
- nao envia XML;
- nao envia dados fiscais extraidos;
- nao envia payload de emissao, cancelamento ou substituicao.

### Modelagem

- cria `NfseManifestation` vinculada ao recebido;
- nao cria `NfseItem`;
- nao cria `FiscalDocument(nfse)`;
- nao altera XML recebido;
- nao altera dados extraidos;
- idempotencia por documento/evento/manifestador.

### Seguranca

- exige `issue_nfse_manifestation`;
- payload protegido;
- downloads protegidos;
- permissoes de importacao nao manifestam;
- permissoes de emissao/cancelamento/substituicao nao manifestam;
- cross-workshop bloqueado.

### Webhook/reconciliacao

- webhook seguro atualiza manifestacao recebida correta;
- webhook ambiguo fica pendente;
- reconciliacao consulta sem reenviar POST;
- reconciliacao ambigua nao atualiza.

### Regressao

- importacao de NFS-e recebida continua funcionando;
- manifestacao NFS-e existente continua funcionando;
- emissao manual continua funcionando;
- cancelamento manual continua funcionando;
- substituicao manual continua funcionando;
- NFS-e legada nao regride;
- NF-e/NFC-e nao regridem.

## Cobertura adicionada na Fase 3.13.1

Novos testes em `FiscalPhaseThreeNfseReceivedConsultationTests` cobrem:

- consulta de `NfseReceivedDocument` por UUID seguro;
- uso de `GET /2/nfse/consulta/{identifier}`;
- registro de snapshot consultivo com payload sanitizado, status remoto e Padrao Nacional quando retornado;
- preservacao de XML, hash, UUID, CNPJs, municipio, ambiente, valor e role fiscal;
- ausencia de `NfseItem`, `FiscalDocument(nfse)`, `NfseManifestation` e `FiscalEmissionAttempt`;
- ausencia de POST de manifestacao, emissao, cancelamento ou substituicao;
- divergencias de UUID, status, CNPJ, municipio, ambiente, valor e Padrao Nacional registradas sem sobrescrita;
- bloqueio por feature flag desligada, XML ausente, hash ausente e identificador inseguro;
- permissao especifica para consultar e payload protegido.

Regressoes obrigatorias da fase: importacao recebida, manifestacao recebida, manifestacao NFS-e existente, emissao manual, cancelamento manual e substituicao manual.

## Plano de testes para Fase 3.14.1 - lote XML de NFS-e recebida

Status: planejado na Fase 3.14.0.

Testes obrigatorios recomendados:

- lote com todos os XMLs validos cria um `NfseReceivedDocument` por arquivo;
- lote misto persiste os validos e registra erro por arquivo invalido;
- duplicidade por hash bloqueia novo registro sem sobrescrever o existente;
- duplicidade por UUID e identificador bloqueia novo registro;
- duplicidade dentro do proprio lote e reportada corretamente;
- XML de outra oficina/empresa e bloqueado por validacao de CNPJ/papel fiscal;
- XML malformado ou sem UUID/identificador seguro gera erro por arquivo;
- limites de quantidade e tamanho sao aplicados;
- relatorio apresenta nome do arquivo, resultado, motivo e link do documento criado;
- nenhuma chamada Webmania e feita automaticamente;
- nenhuma manifestacao automatica e criada;
- nenhum `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt` e criado;
- permissoes de lote, payload e download permanecem separadas;
- upload unitario, manifestacao recebida e consulta recebida nao regridem.

Operacao: a fase deve ser validada com testes deterministicos usando arquivos XML pequenos e cenarios de falha parcial. `mypy .` continua nao bloqueante enquanto o baseline amplo preexistente nao for saneado.

## Cobertura adicionada na Fase 3.14.1

`FiscalPhaseThreeNfseReceivedBatchImportTests` cobre:

- lote com multiplos XMLs validos;
- relatorio persistido por arquivo;
- lote misto com valido, XML invalido, duplicado e CNPJ/oficina divergente;
- duplicidade por hash, UUID e identificador contra base existente;
- duplicidade dentro do proprio lote;
- limites de quantidade, tamanho, arquivo vazio e extensao insegura;
- permissoes especificas de lote e relatorio protegido;
- upload multiplo pela UI;
- ausencia de chamada Webmania;
- ausencia de `NfseManifestation`, `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt`.

Validacao executada: 6 testes focados da fase OK; 79 testes fiscais direcionados OK; `makemigrations finance --check --dry-run` OK; Ruff nos Python tocados OK.

## Plano de testes para Fase 3.15.1 - planejamento e-mail/ERP

Status: planejado na Fase 3.15.0.

Como a proxima fase recomendada e documental/preparatoria, os testes funcionais ficam para uma fase posterior. A fase 3.15.1 deve especificar testes futuros para:

- conectores externos mockados;
- anexos validos e invalidos;
- XML duplicado por hash/fingerprint;
- documento de outra oficina;
- permissao para configurar fonte externa;
- permissao para processar fila;
- isolamento por oficina;
- reprocessamento idempotente;
- ausencia de chamada Webmania;
- ausencia de manifestacao automatica;
- integracao com `NfseReceivedImportBatch`.

## Plano de testes para futura Fase 3.15.2 - caixa externa de XML

Status: planejado na Fase 3.15.1.

Testes funcionais futuros recomendados:

- registra XML candidato vindo de fonte externa sem criar `NfseReceivedDocument`;
- bloqueia arquivo nao XML, vazio, executavel, ZIP inseguro e path traversal;
- bloqueia arquivo acima do limite e mensagem com anexos acima do limite;
- calcula hash/fingerprint e bloqueia duplicidade por hash, UUID, identificador e origem externa;
- bloqueia XML de outra oficina/empresa antes de enviar ao lote;
- mantem item em `pending_review` ate acao humana;
- descarta item com auditoria e sem apagar XML/historico quando a politica exigir retencao;
- envia item aprovado para `NfseReceivedImportBatch`;
- vincula item importado ao lote e ao `NfseReceivedDocument`;
- nao cria documento recebido diretamente fora do pipeline validado;
- nao consulta Webmania automaticamente;
- nao manifesta automaticamente;
- nao cria `NfseItem`, `FiscalDocument(nfse)` ou `FiscalEmissionAttempt`;
- valida permissoes de configuracao, visualizacao, processamento, descarte e payload;
- bloqueia cross-workshop em lista, detalhe, processamento, descarte e payload;
- reprocessa de forma idempotente sem duplicar documento nem sobrescrever XML validado.

Operacao planejada: iniciar com importacao sob demanda/revisao humana. Conectores reais de e-mail, ERP, pasta monitorada ou webhook externo devem ter bateria propria quando forem autorizados.

## Cobertura planejada/implementada na Fase 3.15.2

Status: em implementacao controlada em 2026-06-30.

Nova classe: `FiscalPhaseThreeNfseExternalXmlInboxTests`.

Cobertura esperada: registro de XML candidato, multiplos XMLs, resumo parseado, hash, status pendente, ausencia de documento/lote automatico, invalidos por arquivo, duplicidade no envio, duplicidade contra inbox/documento, CNPJ/oficina divergente, aprovacao humana, descarte com auditoria, processamento pelo lote XML, vinculos com lote/item/documento, bloqueio de reprocessamento, permissoes e payload protegido.

Regressoes obrigatorias: upload unitario, lote XML, consulta recebida, manifestacao recebida, manifestacao NFS-e existente, preview/emissao/cancelamento/substituicao manual e NFS-e legada.

## Plano de testes para Fase 3.16.1 - ampliacao operacional da inbox XML

Status: planejado na Fase 3.16.0.

Testes futuros recomendados:

- filtros por status, empresa, origem e periodo;
- busca por nome de arquivo, hash, UUID e identificador parseado;
- exportacao de relatorio sem expor XML quando usuario nao possuir permissao de payload;
- acoes em massa de aprovacao/descarte com confirmacao explicita;
- bloqueio de aprovacao em massa para itens invalidos, duplicados, descartados ou processados;
- reprocessamento controlado sem duplicar lote nem documento;
- painel de auditoria com criacao, aprovacao, descarte, processamento, lote e documento;
- cross-workshop em lista, filtros, detalhe, exportacao e acoes;
- ausencia de chamada Webmania, manifestacao automatica, `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt`.

## Cobertura implementada na Fase 3.16.1

Status: validada em 2026-06-30 no checkpoint `166eda86`.

Classe ampliada: `FiscalPhaseThreeNfseExternalXmlInboxTests`.

Cobertura adicionada:

- filtros e busca por dados dos itens respeitando oficina ativa;
- acoes em massa com sucesso/erro por item;
- aprovacao em massa bloqueando item invalido;
- descarte em massa com motivo obrigatorio;
- processamento em massa somente de itens aprovados selecionados;
- processamento preservando `NfseReceivedImportBatch` como unico criador de `NfseReceivedDocument`;
- view de acao em massa exigindo permissao propria;
- exportacao CSV exigindo permissao propria, respeitando oficina ativa e sem XML bruto;
- garantias negativas de ausencia de Webmania, `NfseManifestation`, `NfseItem`, `FiscalDocument(nfse)` e `FiscalEmissionAttempt`.

Nao implementado nesta fase: retencao/arquivamento e reprocessamento de erro. Ambos permanecem pendentes por exigirem politica fiscal propria e testes adicionais de duplicidade.

## Plano de testes para Fase 3.17.1 - auditoria tecnica/fiscal geral

Status: validada em 2026-07-02 no checkpoint `305dc22cf5d811f8c875812a178f68634583a986`. A Fase 3.17.0 foi validada documentalmente no checkpoint `424a3c2a`.

Testes e verificacoes recomendados:

- mapear baterias direcionadas por subfase fiscal;
- revisar cobertura de NFS-e recebida, inbox, manifestacao, consulta, lote, NFS-e manual, NFS-e legada, NF-e/NFC-e e IBS/CBS ja implementados;
- identificar lacunas de regressao sem criar testes funcionais nesta fase documental;
- revisar `makemigrations --check`, Ruff, `git diff --check` e baseline `mypy`;
- listar alvos de teste obrigatorios para qualquer fase posterior;
- confirmar ausencia de chamada Webmania automatica em fluxos locais;
- confirmar protecao de payload/XML e cross-workshop nas trilhas fiscais;
- gerar backlog priorizado de correcoes pequenas, sem executar implementacao funcional.

Plano de validacao desta auditoria:

- `uv run python manage.py makemigrations finance --check --dry-run`;
- bateria fiscal direcionada cobrindo NFS-e recebida, lote, inbox, consulta, manifestacao, NFS-e manual, cancelamento e substituicao;
- `uv run mypy .` como nao bloqueante, com registro do baseline se falhar;
- `git diff --check`;
- `git status --short` antes do checkpoint.

Ruff nao e obrigatorio se a fase permanecer exclusivamente documental, sem Python tocado.

Resultado executado em 2026-06-30:

- `uv run python manage.py makemigrations finance --check --dry-run`: OK, sem changes detected;
- bateria fiscal direcionada: 89 testes OK;
- `uv run mypy .`: nao bloqueante, falhou no baseline amplo preexistente com 3284 erros em 266 arquivos, checando 688 fontes;
- `git diff --check`: OK antes do checkpoint;
- Ruff: nao aplicavel, pois a fase permaneceu documental e nenhum Python foi alterado.

## Plano de testes para Fase 3.18.1 - saneamento tecnico pos-auditoria

Status: em execucao pela Fase 3.18.1. A Fase 3.18.0 foi validada documentalmente no checkpoint `274df7f7`.

Validacoes obrigatorias se a fase futura tocar Python:

- `uv run python manage.py makemigrations finance --check --dry-run`;
- testes focados dos services, models, views ou permissoes tocados;
- bateria fiscal direcionada cobrindo NFS-e recebida, lote, inbox, consulta, manifestacao, NFS-e manual, cancelamento e substituicao quando houver risco de regressao;
- `uv run ruff check <arquivos_python_tocados>`;
- `uv run mypy <subconjunto_fiscal_tocado>` quando viavel;
- `uv run mypy .` global como nao bloqueante, apenas para medir baseline;
- `git diff --check`.

Regra de operacao: nao alterar comportamento fiscal, payload remoto, endpoint, permissao efetiva ou documento fiscal apenas para satisfazer tipo. Qualquer mudanca de regra deve sair da fase tecnica e exigir fase funcional/documental propria.

Cobertura adicionada nesta fase: regressao de payload de consulta recebida e payload de manifestacao recebida contra acesso cross-workshop, preservando permissao separada e escopo por oficina.

Resultado executado em 2026-07-02:

- `uv run python manage.py makemigrations finance --check --dry-run`: OK, sem changes detected;
- testes focados `FiscalPhaseThreeNfseReceivedConsultationTests` e `FiscalPhaseThreeNfseReceivedManifestationTests`: 12 testes OK;
- bateria fiscal direcionada: 91 testes OK;
- `uv run ruff check apps/finance/tests.py`: OK;
- `uv run mypy apps/finance/tests.py`: nao bloqueante, falhou no baseline amplo com 1641 erros em 132 arquivos, checando 1 fonte;
- `uv run mypy .`: nao bloqueante, falhou no baseline preexistente com 3284 erros em 266 arquivos, checando 688 fontes.

## Registro final do ciclo fiscal funcional - Fase 3.19.0

Status: em encerramento documental em 2026-07-02. A Fase 3.18.1 foi validada no checkpoint `96665e2142a3f8163508f36784b31d5af32247cb`.

Resultados finais conhecidos:

- Fase 3.17.1: `makemigrations finance --check --dry-run` OK; bateria fiscal direcionada com 89 testes OK; `git diff --check` OK; `mypy .` nao bloqueante falhou no baseline preexistente com 3284 erros em 266 arquivos.
- Fase 3.18.1: `makemigrations finance --check --dry-run` OK; testes focados de consulta/manifestacao recebida com 12 testes OK; bateria fiscal direcionada com 91 testes OK; Ruff no Python tocado OK; `mypy` focado e global nao bloqueantes falharam no baseline; `git diff --check` OK.
- Checkpoint da Fase 3.18.1: `96665e2142a3f8163508f36784b31d5af32247cb`.
- `git status --short` apos o checkpoint anterior: limpo.
- A Fase 3.18.1 nao adicionou funcionalidade fiscal nova nem alterou comportamento fiscal em producao.

Para a Fase 3.19.0, por ser documental, a validacao exigida e `git diff --check -- docs/fiscal-webmania` e `git status --short`. Testes funcionais nao sao necessarios enquanto nenhum codigo for alterado.

## Plano de testes para Fase 4.0.0 - auditoria NF-e/NFC-e

Status: em auditoria documental/tecnica em 2026-07-02.

Testes existentes mapeados:

- NF-e normal e estabilizacao: `NfeProductExtractionTests`, `NfePermissionFallbackTests`, `NfeCancelServiceTests`, `FiscalPhaseOneStabilizationTests`, `FiscalPhaseOneConcurrentEmissionTests`.
- IBS/CBS classe/emissao normal: `FiscalPhaseTwoIbsCbsTaxClassTests`, `FiscalPhaseTwoIbsCbsNormalEmissionTests`.
- CC-e: `FiscalPhaseTwoCorrectionTests`, `FiscalPhaseTwoCorrectionConcurrentTests`.
- Devolucao/estorno: `FiscalPhaseTwoReturnTests`, `FiscalPhaseTwoReturnIbsCbsTests`, `FiscalPhaseTwoReturnConcurrentTests`.
- Complementar preco/quantidade: `FiscalPhaseTwoComplementaryPriceQuantityTests`, `FiscalPhaseTwoComplementaryTests`, `FiscalPhaseTwoComplementaryIbsCbsTests`, `FiscalPhaseTwoComplementaryConcurrentTests`.
- Ajuste: `FiscalPhaseTwoAdjustmentTests`, `FiscalPhaseTwoAdjustmentConcurrentTests`.
- NFC-e: `FiscalPhaseTwoNfceManualTests`, `FiscalPhaseTwoNfceManualConcurrentTests`, `FiscalPhaseTwoNfceCancellationTests`, `FiscalPhaseTwoNfceCancellationConcurrentTests`, `FiscalPhaseTwoNfceInutilizationTests`, `FiscalPhaseTwoNfceInutilizationConcurrentTests`.
- Eventos IBS/CBS: classes `FiscalPhaseTwoIbsCbsEvent112110/112130/112150*` e cancelamentos correspondentes.
- Credito/debito: `FiscalPhaseTwoCreditDebitBasisTests`, previews de credito/debito, emissao/cancelamento de credito tipo 1 e debito tipo 4, incluindo testes concorrentes.

Lacunas de teste mapeadas:

- payload/view propria de NF-e normal ainda nao tem matriz de permissao separada como os fluxos modernos;
- cancelamento NF-e normal legado precisa regressao de idempotencia/permissao comparavel a NFC-e;
- inutilizacao NF-e normal precisa cobertura equivalente a `FiscalNumberInutilization` da NFC-e, ou decisao de manter legado bloqueado;
- manifestacao do destinatario NF-e nao possui testes porque esta ausente;
- contingencia/offline NFC-e nao possui testes porque esta ausente.

Para a Fase 4.0.0, por ser documental, executar apenas `git diff --check -- docs/fiscal-webmania` e `git status --short`. Testes funcionais nao sao necessarios enquanto nenhum codigo for alterado.

## Plano de testes para Fase 4.0.1 - saneamento NF-e/NFC-e

Status: validada em 2026-07-02 no checkpoint `613a73cb31de23e68883ac35ddbf396e3f08f030`.

Validacoes obrigatorias porque Python foi tocado:

- `uv run python manage.py makemigrations finance --check --dry-run`;
- teste focado de detalhe NF-e/permissao em `FiscalDocumentDetailFlowTests`;
- bateria fiscal direcionada NF-e/NFC-e se houver risco de regressao;
- `uv run ruff check apps/finance/views/nfe.py apps/finance/tests.py`;
- `uv run mypy apps/finance/views/nfe.py apps/finance/tests.py` como nao bloqueante se contaminado pelo baseline;
- `git diff --check`;
- remocao de `.codex-uv-cache` antes do checkpoint.

Cobertura adicionada: regressao comprovando que a tela de detalhe da NF-e normal nao expõe cancelar/inutilizar quando falta permissao de alteracao, ainda que o documento esteja em estado elegivel.

Testes futuros recomendados: permissao dedicada para download/payload de NF-e normal, idempotencia moderna de cancelamento/inutilizacao NF-e normal e cross-workshop nos caminhos legados, todos dependentes de fase propria se exigirem migration ou mudanca operacional.

Resultado executado em 2026-07-02:

- `uv run python manage.py makemigrations finance --check --dry-run`: OK, sem changes detected;
- teste focado `FiscalDocumentDetailFlowTests.test_nfe_detail_hides_legacy_fiscal_actions_without_change_permission`: OK;
- regressao direcionada NF-e/NFC-e com `NfePermissionFallbackTests`, dois testes de `FiscalDocumentDetailFlowTests` e `FiscalPhaseTwoNfceManualTests.test_nfce_webhook_reconciliation_download_permission_and_cross_workshop`: 4 testes OK;
- alvo ampliado `FiscalDocumentDetailFlowTests` + `FiscalPhaseTwoNfceManualTests`: 22 testes OK e 1 falha preexistente/fora do escopo em texto de preview NFS-e (`Previa da NFS-e indisponivel` esperado contra tela atual `Previa da Nota Fiscal de Serviço indisponivel`); nao corrigido nesta fase por envolver NFS-e;
- `uv run ruff check apps/finance/views/nfe.py apps/finance/tests.py`: OK;
- `uv run mypy apps/finance/views/nfe.py apps/finance/tests.py`: nao bloqueante, falhou no baseline amplo com 1642 erros em 132 arquivos, checando 2 fontes;
- `git diff --check`: OK.

## Plano de testes para Fase 4.0.2 - planejamento de permissoes NF-e normal

Status: em planejamento documental em 2026-07-02.

Por ser fase exclusivamente documental, executar apenas:

- `git diff --check -- docs/fiscal-webmania`;
- `git status --short`.

Testes planejados para a fase funcional futura:

- usuario com `cancel_nferequest` ve botao e consegue POST de cancelamento;
- usuario sem `cancel_nferequest` nao ve botao e nao consegue POST;
- fallback legado de cancelamento funciona enquanto ativo;
- usuario com `invalidate_nferequest_numbering` ve botao e consegue POST de inutilizacao;
- usuario com permissao de cancelamento nao consegue inutilizar;
- usuario com permissao de inutilizacao nao consegue cancelar;
- download XML exige `download_nferequest_xml` ou fallback temporario;
- download DANFE/PDF exige `download_nferequest_pdf` ou fallback temporario;
- payload exige `view_nferequest_payload` se view futura for criada;
- resposta remota exige `view_nferequest_remote_response` se view futura for criada;
- cross-workshop permanece bloqueado;
- permissoes genericas deixam de bastar quando fallback for removido em fase propria;
- nenhuma chamada Webmania nova;
- nenhum payload fiscal alterado;
- nenhuma regra fiscal alterada;
- regressao NF-e/NFC-e direcionada.
## Testes da Fase 4.1.0 - retomada da devolucao NF-e

Cobertura obrigatoria adicionada ou reaproveitada:
- Devolucao total via view sem JSON parcial.
- Devolucao parcial bloqueada sem produtos.
- Estorno via view ignorando produtos parciais.
- Payload/response de devolucao protegido por permissao dedicada e oficina ativa.
- Regressao ja existente para payload parcial com sequenciais fiscais, saldo disponivel, timeout `uncertain`, webhook idempotente e reconciliacao sem novo POST.

Validacao esperada:
- `uv run python manage.py makemigrations finance --check --dry-run`.
- Suites direcionadas `FiscalPhaseOneStabilizationTests`, `FiscalPhaseOneConcurrentEmissionTests`, `FiscalPhaseTwoReturnTests`, `FiscalPhaseTwoReturnIbsCbsTests`, `FiscalPhaseTwoReturnConcurrentTests` e regressao NF-e/NFC-e/NFS-e relevante conforme tempo de execucao.
- `uv run ruff check` nos arquivos Python tocados.
- `uv run mypy` no subconjunto fiscal tocado; falha por baseline preexistente deve ser registrada como nao bloqueante.
- `git diff --check`.
## Fase 4.2.0 - Testes de fechamento da CC-e

- Testes focados: `FiscalPhaseTwoCorrectionTests` e `FiscalPhaseTwoCorrectionConcurrentTests`.
- Cobertura obrigatoria adicionada/confirmada: NF-e autorizada elegivel, status inelegiveis, texto curto/longo, texto fiscal perigoso, confirmacao explicita, permissao especifica, cross-workshop, payload protegido, download protegido, webhook idempotente, ambiguidade, timeout `uncertain` e concorrencia sem POST duplicado.
- Regressao dirigida deve incluir NF-e normal, devolucao/estorno, NFC-e, NFS-e e fluxos fiscais ja validados, sem iniciar dominios posteriores.
- `mypy` permanece validacao complementar nao bloqueante quando falhar por baseline/stubs preexistentes.
