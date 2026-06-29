# PRD matriz API Webmania

Fonte oficial consultada:

- NF-e/NFC-e: `https://webmania.com.br/docs/rest-api-nfe/`
- NFS-e: `https://webmania.com.br/docs/rest-api-nfse/`
- CT-e/CT-e OS: `https://webmania.com.br/docs/rest-api-cte/`
- MDF-e: `https://webmania.com.br/docs/rest-api-mdfe/`
- NFCom: `https://webmania.com.br/docs/rest-api-nfcom/`
- DC-e: `https://webmania.com.br/docs/rest-api-dce/`

## Matriz resumida

| Documento    | Operacao                  | Metodo          | Endpoint                              | Autenticacao | Body principal                              | Resposta principal              | Downloads         | Webhook | Fase |
| ------------ | ------------------------- | --------------- | ------------------------------------- | ------------ | ------------------------------------------- | ------------------------------- | ----------------- | ------- | ---- |
| NF-e/NFC-e   | Emissao                   | POST            | `/1/nfe/emissao/`                     | Headers v1   | cliente, produtos, pedido, modelo, ambiente | uuid, status, chave, xml, danfe | XML/DANFE por URL | Sim     | 1/2  |
| NFC-e        | Emissao consumidor        | POST            | `/1/nfe/emissao/`                     | Headers v1   | `modelo=2`, cliente/consumidor, produtos, pedido/pagamento, ambiente | uuid, status, modelo `nfce`, chave, xml, danfe | XML/DANFE NFC-e | Sim | 2.3 |
| NF-e/NFC-e   | Devolucao/estorno         | POST            | `/1/nfe/devolucao/`                   | Headers v1   | `chave`, produtos/quantidades, dados fiscais | uuid, status, chave             | XML/DANFE         | Sim     | 2.2A |
| NF-e/NFC-e   | Ajuste                    | POST            | `/1/nfe/ajuste/`                      | Headers v1   | `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `ambiente`, `cliente` | uuid, status                    | XML/DANFE         | Sim     | 2.2C |
| NF-e/NFC-e   | Complementar              | POST            | `/1/nfe/complementar/`                | Headers v1   | `chave` ou `uuid`, tipo de complemento, valores/quantidades/impostos | uuid, status                    | XML/DANFE         | Sim     | 2.2B |
| NF-e/NFC-e   | Carta de correcao         | POST            | `/1/nfe/cartacorrecao/`               | Headers v1   | uuid/chave, correcao                        | modelo cce, status, xml         | XML CC-e          | Sim     | 2    |
| NF-e/NFC-e   | Manifestacao              | POST            | `/1/nfe/manifesta/`                   | Headers v1   | chave, evento, justificativa                | status/log                      | N/A               | Sim     | 2    |
| NF-e/NFC-e   | Eventos IBS/CBS           | POST            | `/1/nfe/evento-ibs-cbs/`              | Headers v1   | tipo evento, chave/uuid, dados IBS/CBS      | status/log                      | XML evento        | Sim     | 2    |
| NF-e/NFC-e   | Cancelar evento IBS/CBS   | PUT             | `/1/nfe/evento-ibs-cbs/cancelar/`     | Headers v1   | identificador evento                        | status/log                      | XML evento        | Sim     | 2    |
| NF-e/NFC-e   | Classe imposto            | GET/POST/DELETE | `/1/nfe/classe-imposto/`              | Headers v1   | referencia e payload tributario             | lista/resultado                 | N/A               | Nao     | 1/2  |
| NF-e/NFC-e   | Atualizar empresa         | POST            | `/1/nfe/empresa/`                     | Headers v1   | dados empresa, certificado, serie           | resultado                       | N/A               | Nao     | 1    |
| NF-e/NFC-e   | Relatorios                | POST            | `/1/nfe/relatorios/`                  | Headers v1   | periodo/modelo/formato                      | arquivo/link                    | CSV/XML/DANFE     | Nao     | 2    |
| NF-e/NFC-e   | Consulta                  | GET             | `/1/nfe/consulta/`                    | Headers v1   | query uuid/chave/ID                         | status, uuid, chave, URLs       | XML/DANFE por URL | Nao     | 1/2  |
| NF-e/NFC-e   | Status SEFAZ              | GET             | `/1/nfe/sefaz/`                       | Headers v1   | ambiente/modelo                             | status servico                  | N/A               | Nao     | 2    |
| NF-e/NFC-e   | Certificado A1            | GET             | `/1/nfe/certificado/`                 | Headers v1   | N/A                                         | validade/status                 | N/A               | Nao     | 1    |
| NF-e/NFC-e   | Cancelamento              | PUT             | `/1/nfe/cancelar/`                    | Headers v1   | uuid ou chave, motivo                       | status, xml cancelamento        | XML               | Sim     | 1/2  |
| NF-e/NFC-e   | Inutilizacao              | PUT             | `/1/nfe/inutilizar/`                  | Headers v1   | sequencia, serie, modelo, motivo            | status, xml                     | XML               | Nao     | 1/2  |
| NFS-e        | Emissao/RPS/lote          | POST            | `/2/nfse/emissao`                     | Bearer v2    | rps, servico, tomador, url_notificacao      | uuid/lote, status               | URLs retornadas   | Sim     | 1/3  |
| NFS-e        | Substituicao              | POST            | `/2/nfse/substituir`                  | Bearer v2    | documento original, novo RPS                | uuid/status                     | XML/PDF           | Sim     | 3    |
| NFS-e        | Manifestacao              | POST            | `/2/nfse/manifestar`                  | Bearer v2    | participacao padrao nacional                | status/log                      | N/A               | Sim     | 3    |
| NFS-e        | Consulta                  | GET             | `/2/nfse/consulta/{identifier}`       | Bearer v2    | path UUID/lote                              | status, itens, URLs             | XML/PDF/RPS       | Nao     | 1/3  |
| NFS-e        | Status municipio          | GET             | `/2/nfse/status`                      | Bearer v2    | municipio/provedor                          | capacidades                     | N/A               | Nao     | 3    |
| NFS-e        | Cancelamento/agendamento  | PUT             | `/2/nfse/cancelar`                    | Bearer v2    | uuid, motivo                                | status/xml                      | XML               | Sim     | 1/3  |
| CT-e/CT-e OS | Emissao                   | POST            | `/2/cte/emissao`                      | Bearer v2    | remetente, destinatario, transporte         | uuid, chave, status             | XML/DACTE         | Sim     | 4    |
| CT-e         | Emissao simplificada      | POST            | `/2/cte/emissao/simplificada`         | Bearer v2    | payload simplificado                        | uuid/status                     | XML/DACTE         | Sim     | 4    |
| CT-e         | Entrega                   | POST            | `/2/cte/entrega`                      | Bearer v2    | uuid/chave, dados entrega                   | evento/status                   | XML evento        | Sim     | 4    |
| CT-e/CT-e OS | Correcao                  | POST            | `/2/cte/correcao`                     | Bearer v2    | campos corrigidos                           | evento/status                   | XML evento        | Sim     | 4    |
| CT-e/CT-e OS | Consulta                  | GET             | `/2/cte/consulta/{identifier}`        | Bearer v2    | path uuid/chave                             | status, URLs                    | XML/DACTE         | Nao     | 4    |
| CT-e/CT-e OS | Cancelamento              | PUT             | `/2/cte/cancelar`                     | Bearer v2    | uuid/chave, motivo                          | status/xml                      | XML cancelamento  | Sim     | 4    |
| CT-e         | Cancelar entrega          | PUT             | `/2/cte/entrega/cancelar`             | Bearer v2    | identificador evento                        | status                          | XML evento        | Sim     | 4    |
| CT-e         | Evento pagamento          | POST            | `/2/cte/evento`                       | Bearer v2    | evento 110300/110301                        | status/evento                   | N/A               | Sim     | 4    |
| CT-e         | Cancelar evento pagamento | PUT             | `/2/cte/evento/cancelar`              | Bearer v2    | identificador evento                        | status                          | N/A               | Sim     | 4    |
| CT-e         | Historico eventos         | GET             | `/2/cte/consulta/evento/{identifier}` | Bearer v2    | uuid/chave                                  | historico                       | N/A               | Nao     | 4    |
| MDF-e        | Emissao                   | POST            | `/2/mdfe/emissao`                     | Bearer v2    | documentos, veiculo, condutor, modalidade   | uuid, chave, status             | XML/DAMDFE        | Sim     | 5    |
| MDF-e        | Consulta                  | GET             | `/2/mdfe/consulta/{identifier}`       | Bearer v2    | path uuid/chave                             | status, URLs                    | XML/DAMDFE        | Nao     | 5    |
| MDF-e        | Encerramento              | PUT             | `/2/mdfe/encerrar`                    | Bearer v2    | uuid/chave, municipio, data                 | status                          | XML evento        | Sim     | 5    |
| MDF-e        | Cancelamento              | PUT             | `/2/mdfe/cancelar`                    | Bearer v2    | uuid/chave, motivo                          | status                          | XML cancelamento  | Sim     | 5    |
| MDF-e        | Condutor                  | PUT             | `/2/mdfe/condutor`                    | Bearer v2    | uuid/chave, condutor                        | status                          | XML evento        | Sim     | 5    |
| NFCom        | Emissao/previa            | POST            | `/2/nfcom/emissao`                    | Bearer v2    | finalidade 1-4, assinante, cliente, itens   | uuid, chave, status             | XML/DANFECOM      | Sim     | 6    |
| NFCom        | Cancelamento              | PUT             | `/2/nfcom/cancelar`                   | Bearer v2    | uuid/chave, motivo                          | status/xml_cancelamento         | XML               | Sim     | 6    |
| NFCom        | Consulta                  | GET             | `/2/nfcom/consulta/{identifier}`      | Bearer v2    | uuid/chave                                  | status, URLs                    | XML/DANFECOM      | Nao     | 6    |
| NFCom        | Status                    | GET             | `/2/nfcom/status`                     | Bearer v2    | N/A                                         | status SEFAZ                    | N/A               | Nao     | 6    |
| NFCom        | XML                       | GET             | `/xmlnfcom/{identifier}`              | Bearer v2    | uuid/chave                                  | arquivo                         | XML               | Nao     | 6    |
| NFCom        | DANFECOM                  | GET             | `/danfecom/{identifier}`              | Bearer v2    | uuid/chave                                  | arquivo                         | PDF               | Nao     | 6    |
| DC-e         | Emissao                   | POST            | `/2/dce/emissao`                      | Bearer v2    | remetente/destinatario/itens/transporte     | uuid, chave, status             | XML/DACE          | Sim     | 7    |
| DC-e         | Consulta                  | GET             | `/2/dce/consulta/{identifier}`        | Bearer v2    | uuid/chave                                  | status, URLs                    | XML/DACE          | Nao     | 7    |
| DC-e         | Cancelamento              | PUT             | `/2/dce/cancelar`                     | Bearer v2    | uuid/chave, motivo                          | status/xml_cancelamento         | XML               | Sim     | 7    |

## Uso no Hunter V2

- NF-e: produtos e pecas de OS, venda avulsa, NFC-e futura para consumidor.
- NFS-e: servicos de OS, servico avulso, substituicao quando municipio suportar.
- CT-e/CT-e OS: uso medio, manual ou vinculado a documentos de transporte.
- MDF-e: manifesto de documentos, pendencia operacional quando autorizado e nao encerrado.
- NFCom: API v2.0.0, uso manual de baixa prioridade, isolada por feature flag e habilitacao administrativa por oficina como politica interna.
- DC-e: API v2.0.0, isolada por feature flag e habilitacao administrativa por oficina como politica interna.

## Planejamento Fase 2.0 - NF-e/NFC-e

Fonte oficial reconferida em 2026-05-28: a pagina NF-e/NFC-e confirma a API v1 em `https://webmania.com.br/api/`, autenticacao por quatro headers, formato JSON, notificacoes por `uuid`, `status`, `motivo`, `chave`, `xml`, `danfe` e `log`, e lista os endpoints de emissao, devolucao/estorno, ajuste, complementar, CC-e, manifestacao e eventos IBS/CBS.

| Subfase | Operacao | Endpoint Webmania | Tipo local recomendado | Uso no Hunter V2 |
| ------- | -------- | ----------------- | ---------------------- | ---------------- |
| 2.1 | CC-e | `POST /1/nfe/cartacorrecao/` | Evento fiscal vinculado a NF-e | Corrigir texto de NF-e autorizada sem alterar valores. |
| 2.2A | Devolucao/estorno | `POST /1/nfe/devolucao/` | Documento derivado com link obrigatorio | Devolver produtos total/parcialmente ou registrar estorno via endpoint de devolucao. |
| 2.2B | Complementar | `POST /1/nfe/complementar/` | Documento derivado com link obrigatorio | Complementar preco/quantidade, impostos ou documento de adicao/importacao. |
| 2.2C | Ajuste | `POST /1/nfe/ajuste/` | Documento de ajuste com link opcional | Ajustes fiscais que nao exigem obrigatoriamente chave/UUID original segundo a documentacao oficial. |
| 2.3 | NFC-e | `POST /1/nfe/emissao/` com modelo NFC-e | Documento fiscal legado/derivado futuro | Venda consumidor em oficina habilitada. |
| 2.3 | Cancelamento NFC-e | `PUT /1/nfe/cancelar/` | Evento de cancelamento do documento | Cancelar NFC-e conforme status e prazo/regra Webmania/SEFAZ. |
| 2.4 | Manifestacao | `POST /1/nfe/manifesta/` | Evento fiscal vinculado a chave/documento | Registrar ciencia, confirmacao, desconhecimento ou operacao nao realizada quando suportado. |
| 2.4 | Evento IBS/CBS | `POST /1/nfe/evento-ibs-cbs/` | Evento fiscal vinculado a NF-e/NFC-e | Registrar eventos da Reforma Tributaria. |
| 2.4 | Cancelar evento IBS/CBS | `PUT /1/nfe/evento-ibs-cbs/cancelar/` | Evento de cancelamento vinculado ao evento original | Cancelar evento IBS/CBS previamente autorizado. |
| 2.x | Consulta | `GET /1/nfe/consulta/` | Atualizacao de documento/evento | Reconciliar status e downloads sem emissao. |
| 2.5 | Nota Fiscal de Credito | `POST /1/nfe/emissao/` com `finalidade=5` e `tipo_credito` | Documento NF-e de finalidade especifica | Registrar credito fiscal conforme tipos oficiais da Reforma Tributaria. |
| 2.5 | Nota Fiscal de Debito | `POST /1/nfe/emissao/` com `finalidade=6` e `tipo_debito` | Documento NF-e de finalidade especifica | Registrar debito fiscal conforme tipos oficiais; `dfe_referenciado` pode ser obrigatorio para alguns tipos. |
| 2.x | Downloads | URLs `xml`, `danfe` e XML de evento quando retornado | Download autorizado | Baixar XML/PDF por URL retornada ou resposta remota. |

Observacoes condicionais:

- A Webmania usa o mesmo endpoint de emissao para NF-e e NFC-e; o Hunter deve diferenciar o modelo localmente antes do payload.
- CC-e, manifestacao e IBS/CBS sao eventos e nao devem consumir numeracao como nota comum.
- Devolucao/estorno e complementar sao documentos novos com tentativa idempotente propria e vinculo obrigatorio ao documento original. Ajuste tambem e documento novo, mas o vinculo ao original e opcional porque o body oficial nao exige chave/UUID de nota original.

### Detalhamento Fase 2.2C - `POST /1/nfe/ajuste/`

| Item | Decisao validada |
| ---- | ---------------- |
| Tipo local | `FiscalDocument(document_type="nfe", purpose="adjustment", origin="manual")` |
| Link | Opcional: `FiscalDocumentLink(role="adjusts")` quando houver documento relacionado no contexto |
| Endpoint | `POST /1/nfe/ajuste/` |
| Autenticacao | Headers v1 NF-e |
| Body permitido | `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `valor_icms_st` opcional, `ambiente`, `cliente`, `situacao_tributaria`, `informacoes_fisco`, `informacoes_complementares`, `url_notificacao` |
| Body proibido nesta fase | `produtos`, `pedido`, `impostos`, IBS, CBS, `agropecuario`, importacao, adicao |
| Resposta persistida | `uuid`, `status`, `nfe`, `serie`, `recibo`, `chave`, `xml`, `danfe`, `log` sanitizado |
| Regime tributario | Permitir Lucro Real/Normal e Lucro Presumido; bloquear Simples Nacional, MEI e regime ausente/desconhecido |
| Idempotencia | `hash(workshop_id, adjustment_document_id, operation_type, request_generation)` |
| Webhook/reconciliacao | Atualizam somente o ajuste; nao alteram documento relacionado opcional |
| Excecao SC/ES | Cenario de estorno ja coberto por devolucao/estorno deve ser bloqueado/direcionado para `/1/nfe/devolucao/` |
| Fora de escopo | Complementar tributaria, IBS/CBS, importacao/adicao, NFC-e, manifestacao e credito/debito |

### Detalhamento Fase 2.3.0 - NFC-e

Fonte oficial reconferida em 2026-05-29: a documentacao NF-e/NFC-e usa API v1 em `https://webmania.com.br/api/`, `Content-Type: application/json`, quatro headers de autenticacao, `POST /1/nfe/emissao/`, notificacoes com `modelo` podendo retornar `nfce`, consulta/cancelamento/inutilizacao em endpoints comuns e configuracao de empresa com campos especificos de NFC-e/CSC.

| Operacao | Endpoint | Modelo local | Body principal | Efeitos locais | Observacoes |
| -------- | -------- | ------------ | -------------- | -------------- | ----------- |
| Emissao NFC-e | `POST /1/nfe/emissao/` | `FiscalDocument(document_type="nfce", purpose="normal")` | `modelo=2`, `operacao`, `natureza_operacao`, `ambiente`, `cliente`, `produtos`, `pedido`/pagamento, `url_notificacao` | Criar documento NFC-e antes do gateway; tentativa `nfce_emission`; persistir UUID/chave/XML/DANFE/status | Nao reaproveitar numeracao NF-e; exigir configuracao NFC-e da oficina. |
| Consulta NFC-e | `GET /1/nfe/consulta/` | Atualizacao do `FiscalDocument` NFC-e | query `uuid`, `chave` ou ID | Atualizar status/downloads sem emitir | Usar para reconciliacao e tentativa `uncertain`. |
| Cancelamento NFC-e | `PUT /1/nfe/cancelar/` | `FiscalDocumentEvent(event_type="cancel")` ou status cancelado do documento | `uuid` ou `chave`, motivo, ambiente quando aplicavel | Atualizar documento/evento; preservar payload/log | Cancelamento por substituicao fica pendente de confirmacao oficial antes de codigo. |
| Inutilizacao NFC-e | `PUT /1/nfe/inutilizar/` | Evento/documento operacional de inutilizacao | modelo `2`, serie, numero inicial/final, motivo, ambiente | Registrar evento fiscal auditavel | Implementar somente se aprovado na Fase 2.3, com permissao propria. |
| Downloads | URLs retornadas | Download autorizado | URL `xml`/`danfe` retornada | Servir via view autorizada | Diferenciar DANFE NFC-e de DANFE NF-e na UI. |

Riscos especificos:

- CSC/token e numeracao por ambiente devem ser configurados corretamente antes da emissao.
- NFC-e possui regra operacional de consumidor/pagamento diferente de NF-e.
- Contingencia/offline e cancelamento por substituicao nao devem ser inferidos sem nova validacao oficial.

### Detalhamento Fase 2.2B - `POST /1/nfe/complementar/`

| Subtipo Hunter | Uso | Referencia original | Body principal planejado | Validacoes locais | Efeitos locais |
| -------------- | --- | ------------------- | ------------------------ | ----------------- | -------------- |
| `complementary_price_quantity` | Complementar preco e/ou quantidade | `chave` ou `uuid`; link `complements` obrigatorio | `chave`/`uuid`, `operacao`, `natureza_operacao`, `codigo_cfop`, `ambiente`, `cliente`, `produtos` com sequenciais fiscais, valores e/ou quantidades | NF-e local autorizada; sequenciais fiscais conhecidos; bloquear NF-e externa minima sem XML/importacao validada | Criar `FiscalDocument(purpose="complementary")`, `complementary_type="price_quantity"`, tentativa `complementary` |
| `complementary_tax` | Complementar ICMS, ICMS-ST, IPI, ISSQN, IBS/CBS | `chave` ou `uuid`; link `complements` obrigatorio | `chave`/`uuid`, `operacao`, `natureza_operacao`, `codigo_cfop`, `ambiente`, `cliente`, `impostos`, possivelmente `produtos` quando imposto for itemizado | Permissao restrita; formulario por imposto; NF-e externa minima somente com confirmacao forte e entrada manual auditada | Criar derivado complementar tributario; webhook/reconciliacao atualizam apenas derivado |
| `complementary_import_addition` | Documento de adicao/importacao | `chave` ou `uuid` quando houver nota original | Campos de adicao/importacao conforme payload oficial validado antes do codigo | Baixa prioridade; exigir aprovacao explicita e, para externa, importacao/validacao adequada | Planejado; recomendacao de adiar a implementacao |

Downloads: resposta esperada segue familia NF-e com `uuid`, `status`, `nfe`, `serie`, `recibo`, `chave`, `xml`, `danfe` e `log`, quando disponibilizados pela Webmania.

Webhook: tratar `modelo=nfe` como documento derivado quando `uuid`/tentativa/chave resolverem uma complementar; nao atualizar `NfeItem` original nem outros derivados. Associacao ambigua deve ficar pendente.
- NF-e externa: quando devolucao ou complemento referenciarem chave nao emitida pelo Hunter, criar projecao externa minima antes da emissao derivada, marcar `origin=external`, preservar chave informada e exigir confirmacao do usuario. A consulta padrao `/1/nfe/consulta/` pode ser usada para notas Webmania/Hunter da propria oficina, mas nao e garantia de validacao de NF-e de outro emissor.
- Para NFC-e, cancelamento por substituicao deve ser tratado como variacao de cancelamento somente se a documentacao vigente e a configuracao da oficina confirmarem suporte; ate la, registrar como pendencia de validacao.
- A matriz OpenAPI validada foi atualizada na Fase 2.4.0 para explicitar schemas `ibs_cbs`, dependencia de credito/debito e campos de classes fiscais NF-e/NFC-e.

## Validacao do arquivo OpenAPI recebido

| Item                   | OpenAPI recebido                       | Documentacao oficial                              | Correcao necessaria                      |
| ---------------------- | -------------------------------------- | ------------------------------------------------- | ---------------------------------------- |
| Autenticacao v1 NF-e   | Headers v1                             | Confirmado                                        | Manter                                   |
| Autenticacao v2        | Bearer v2 em familias novas            | Confirmado NFS-e/CT-e/MDF-e/NFCom/DC-e            | Garantir `Accept: application/json`      |
| NFS-e consulta         | `/2/nfse/consulta/{identifier}`        | Listagem cita `/2/nfse/consulta`, exemplo oficial usa `/2/nfse/consulta/{uuid}` | Registrar divergencia e modelar rota operacional por path-param |
| NFS-e downloads        | Implícitos por schema                  | URLs retornadas por resposta                      | Nao inventar endpoint fixo sem validacao |
| CT-e OS simplificada   | Endpoint marcado geral                 | Docs dizem CT-e OS ainda nao disponivel           | Bloquear CT-e OS simplificada            |
| CT-e eventos pagamento | Presentes                              | Confirmados em secao de funcoes                   | Manter, fase 4                           |
| MDF-e consulta         | Path-param no OpenAPI                  | Listagem cita `/2/mdfe/consulta`, exemplo oficial usa `/2/mdfe/consulta/{uuid-ou-chave}` | Registrar divergencia e modelar rota operacional por path-param |
| NFCom                  | Marcada beta no insumo antigo          | Docs atuais indicam versao 2.0.0 sem marcador beta | Corrigir classificacao; manter rollout interno controlado |
| DC-e downloads         | Nao endpoints dedicados no guia rapido | Payload retorna `xml`, `xml_cancelamento`, `dace` | Tratar downloads por URL retornada       |

## Divergencias oficiais registradas na Fase 0.1

| Operacao | Documentacao/listagem | Exemplo oficial | Decisao de modelagem |
| -------- | --------------------- | --------------- | -------------------- |
| Consulta NFS-e | `/2/nfse/consulta` | `GET /2/nfse/consulta/{uuid}` | O OpenAPI validado modela `/2/nfse/consulta/{identifier}` porque e a forma operacional demonstrada no exemplo oficial. |
| Consulta MDF-e | `/2/mdfe/consulta` | `GET /2/mdfe/consulta/{uuid-ou-chave}` | O OpenAPI validado modela `/2/mdfe/consulta/{identifier}` porque e a forma operacional demonstrada no exemplo oficial. |
| CT-e simplificado | CT-e simplificado listado | CT-e OS simplificado indicado como nao disponivel/condicional | O Hunter nao deve habilitar CT-e OS simplificado sem nova confirmacao oficial. |
| NFCom | Documentacao antiga indicava beta | API v2.0.0 sem marcador beta oficial | Manter feature flag e habilitacao administrativa por politica interna. |
| DC-e | Documentacao antiga indicava beta | API v2.0.0 sem marcador beta oficial | Manter feature flag e habilitacao administrativa por politica interna. |

## Autenticacao validada

API v1 NF-e/NFC-e:

- `X-Consumer-Key`;
- `X-Consumer-Secret`;
- `X-Access-Token`;
- `X-Access-Token-Secret`.

API v2 NFS-e, CT-e, MDF-e, NFCom e DC-e:

- `Authorization: Bearer {Access-Token}`;
- `Content-Type: application/json`;
- `Accept: application/json`.

## Webhook e responses

O OpenAPI validado inclui `WebhookPayload` e responses por familia contendo, quando aplicavel:

- `uuid`;
- `status`;
- `motivo`;
- `chave`;
- `xml`;
- `xml_cancelamento`;
- `danfe`;
- `pdf_nfse`;
- `pdf_rps`;
- `dacte`;
- `damdfe`;
- `danfecom`;
- `dace`;
- `log`.

## Versao validada

A versao validada para implementacao futura esta em `api/webmania_fiscal_openapi_validated.json`. Ela deve ser usada como mapa tecnico inicial de gateways e testes, ainda subordinada a nova checagem da documentacao oficial antes de cada fase de codigo.
## Atualizacao Fase 2.3.2 - NFC-e Cancelamento Padrao

| Documento | Operacao | Metodo | Endpoint | Autenticacao | Body principal | Resposta principal | Downloads | Webhook | Fase |
| --------- | -------- | ------ | -------- | ------------ | -------------- | ------------------ | --------- | ------- | ---- |
| NFC-e | Cancelamento padrao | PUT | `/1/nfe/cancelar/` | API v1 com quatro headers Webmania | `chave` ou `uuid`, `motivo` | `status=cancelado`, `xml`, `log` sanitizado | XML de cancelamento por URL retornada | `modelo=nfce`, `status=cancelado` resolve evento/documento | 2.3.2 validada |

Observacao: `nfce_referenciada` ativa cancelamento por substituicao e e explicitamente proibido na Fase 2.3.2.

## Atualizacao Fase 2.3.3 - Inutilizacao de Numeracao NFC-e

| Documento | Operacao | Metodo | Endpoint | Autenticacao | Body principal | Resposta principal | Downloads | Webhook | Fase |
| --------- | -------- | ------ | -------- | ------------ | -------------- | ------------------ | --------- | ------- | ---- |
| NFC-e | Inutilizacao de numeracao | PUT | `/1/nfe/inutilizar/` | API v1 com quatro headers Webmania | `sequencia`, `motivo`, `ambiente`, `serie`, `modelo=2` | `status`/log remoto, `xml` quando retornado; payload integral sanitizado | XML de inutilizacao quando retornado | Nao documentado para esta operacao | 2.3.3 validada |

Observacoes:
- A documentacao textual cita inutilizacao de numeracao de NF-e, mas o contrato inclui `modelo=1` para NF-e e `modelo=2` para NFC-e.
- A Fase 2.3.3 implementa somente `modelo=2`; nenhuma view, form ou service funcional de inutilizacao NF-e foi criado.
- O body nao envia `nfce_referenciada`, dados de cancelamento, contingencia/offline, documento emitido, produtos, pedido ou pagamento.
- Sem webhook ou consulta especifica confirmada para inutilizacao, o Hunter persiste resposta sincrona sanitizada. Estado `uncertain` permanece reservado ate decisao administrativa/rechecagem segura futura.

## Fase 2.5.0 - Matriz NF-e de Credito e Debito

Fonte oficial reconferida em 2026-05-29: documentacao Webmania NF-e/NFC-e em `https://webmania.com.br/docs/rest-api-nfe/` e artigos de rejeicao Webmania para finalidades 5/6. A documentacao lista `finalidade=5` para Credito, `finalidade=6` para Debito, `tipo_credito` e `tipo_debito` como campos especificos, e reutiliza os blocos de emissao de NF-e (`cliente`, `produtos`, `pedido`, notificacao e downloads). A central de ajuda informa que NF-e com finalidade de credito/debito somente pode se relacionar ao imposto IBS/CBS; portanto a implementacao funcional deve ser bloqueada ate a fase IBS/CBS ou ate aprovacao explicita de um subconjunto seguro.

| Documento | Operacao | Metodo | Endpoint | Autenticacao | Body principal | Resposta principal | Downloads | Webhook | Fase |
| --------- | -------- | ------ | -------- | ------------ | -------------- | ------------------ | --------- | ------- | ---- |
| NF-e | Nota Fiscal de Credito | POST | `/1/nfe/emissao/` | API v1 com quatro headers Webmania | `modelo=1`, `finalidade=5`, `tipo_credito`, `ambiente`, `cliente`, `produtos`, `pedido`, `url_notificacao` quando aplicavel | `uuid`, `status`, `motivo`, `nfe`, `serie`, `recibo`, `chave`, `xml`, `danfe`, `log` | XML/DANFE por URLs retornadas | Notificacao de NF-e por UUID quando `url_notificacao` for enviada | 2.5 futura; 2.5.0 documental |
| NF-e | Nota Fiscal de Debito | POST | `/1/nfe/emissao/` | API v1 com quatro headers Webmania | `modelo=1`, `finalidade=6`, `tipo_debito`, `ambiente`, `cliente`, `produtos`, `pedido`, `url_notificacao` quando aplicavel | `uuid`, `status`, `motivo`, `nfe`, `serie`, `recibo`, `chave`, `xml`, `danfe`, `log` | XML/DANFE por URLs retornadas | Notificacao de NF-e por UUID quando `url_notificacao` for enviada | 2.5 futura; 2.5.0 documental |

### Tipos oficiais de Nota Fiscal de Credito

| Tipo remoto | Descricao oficial | Requer IBS/CBS? | Pode implementar antes da fase tributaria? | Evidencia oficial |
| ----------- | ----------------- | --------------: | -----------------------------------------: | ----------------- |
| `1` | Multa e juros | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_credito=1`; artigo Webmania rejeicao 1001 relaciona finalidade credito/debito a IBS/CBS |
| `2` | Apropriacao de credito presumido de IBS sobre o saldo devedor na ZFM | Sim, explicitamente IBS | Nao | Documentacao NF-e menciona IBS e LC 214/25 no proprio tipo |
| `3` | Retorno por recusa total na entrega ou por nao localizacao do destinatario na tentativa de entrega | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado sem subfase tributaria | Documentacao NF-e lista `tipo_credito=3`; rejeicao 1001 exige relacao com IBS/CBS |
| `4` | Reducao de valores | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_credito=4`; rejeicao 1001 exige relacao com IBS/CBS |
| `5` | Transferencia de credito na sucessao | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_credito=5`; rejeicao 1001 exige relacao com IBS/CBS |

### Tipos oficiais de Nota Fiscal de Debito

| Tipo remoto | Descricao oficial | Requer IBS/CBS? | Pode implementar antes da fase tributaria? | Evidencia oficial |
| ----------- | ----------------- | --------------: | -----------------------------------------: | ----------------- |
| `1` | Transferencia de creditos para Cooperativas | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=1`; rejeicao 1001 exige relacao com IBS/CBS |
| `2` | Anulacao de Credito por Saidas Imunes/Isentas | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=2`; rejeicao 1001 exige relacao com IBS/CBS |
| `3` | Debitos de notas fiscais nao processadas na apuracao | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=3`; rejeicao 1001 exige relacao com IBS/CBS |
| `4` | Multa e juros | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=4`; rejeicao 1001 exige relacao com IBS/CBS |
| `5` | Transferencia de credito na sucessao | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=5`; rejeicao 1001 exige relacao com IBS/CBS |
| `6` | Pagamento antecipado | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=6`; rejeicao 1001 exige relacao com IBS/CBS |
| `7` | Perda em estoque | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=7`; rejeicao 1001 exige relacao com IBS/CBS |
| `8` | Desenquadramento do SN | Sim, por regra de finalidade 5/6 somente para IBS/CBS | Nao recomendado | Documentacao NF-e lista `tipo_debito=8`; rejeicao 1001 exige relacao com IBS/CBS |

### Decisoes da Fase 2.5.0

- Credito/debito devem usar `FiscalDocument(document_type="nfe", purpose="credit"|"debit")`, nao `NfeItem` legado nem variação visual de NF-e normal.
- Campo planejado: `fiscal_purpose_type` para armazenar `tipo_credito` ou `tipo_debito` remoto, preservando valor bruto e descricao interna.
- `FiscalDocumentLink(role="credits"|"debits")` sera opcional/condicional. Nao tornar obrigatorio sem exigencia oficial por tipo ou regra de negocio aprovada.
- Emissao funcional deve exigir feature flag e habilitacao administrativa por oficina.
- Recomendacao objetiva: adiar implementacao de codigo ate a fase IBS/CBS ou ate uma subfase tributaria aprovada confirmar payload seguro por tipo.

## Fase 2.4.0 - Matriz IBS/CBS NF-e/NFC-e

Fontes oficiais reconferidas em 2026-05-29:

- Documentacao Webmania NF-e/NFC-e: `https://webmania.com.br/docs/rest-api-nfe/`.
- Central de ajuda Webmania: rejeicao 1001 para NF-e com finalidade de credito/debito relacionada somente a IBS/CBS.

### Emissao e classes fiscais com IBS/CBS

| Documento | Operacao | Metodo | Endpoint | Autenticacao | Body principal | Resposta principal | Downloads | Webhook | Fase |
| --------- | -------- | ------ | -------- | ------------ | -------------- | ------------------ | --------- | ------- | ---- |
| NF-e/NFC-e | Emissao normal com IBS/CBS | POST | `/1/nfe/emissao/` | API v1 com quatro headers Webmania | `modelo`, `finalidade=1`, `cliente`, `produtos[].impostos.ibs_cbs` ou `classe_imposto` previamente configurada com IBS/CBS, `pedido` | `uuid`, `status`, `motivo`, `nfe`, `serie`, `recibo`, `chave`, `xml`, `danfe`, `log` | XML/DANFE por URL | Sim | 2.4B |
| NF-e/NFC-e | Classe de imposto com IBS/CBS | POST | `/1/nfe/classe-imposto/` | API v1 com quatro headers Webmania | `referencia`, `descricao`, cenarios tributarios, `ibs_cbs` | classe salva/listada | N/A | Nao | 2.4A |
| NF-e/NFC-e | Eventos IBS/CBS | POST | `/1/nfe/evento-ibs-cbs/` | API v1 com quatro headers Webmania | `chave`, `ambiente`, `cod_evento`, `evento`, `url_notificacao` e campos especificos do evento | `uuid`/evento, `status`, `modelo`, `xml`, `log` quando retornado | XML de evento quando retornado | Sim | 2.4D |
| NF-e/NFC-e | Cancelar evento IBS/CBS | PUT | `/1/nfe/evento-ibs-cbs/cancelar/` | API v1 com quatro headers Webmania | identificador do evento, motivo/dados exigidos pelo evento | `status`, `xml`, `log` quando retornado | XML de evento quando retornado | Sim | 2.4D |
| NF-e | Nota Fiscal de Credito | POST | `/1/nfe/emissao/` | API v1 com quatro headers Webmania | `finalidade=5`, `tipo_credito`, produtos com somente `impostos.ibs_cbs` | resposta NF-e padrao | XML/DANFE | Sim | 2.4E/2.5 |
| NF-e | Nota Fiscal de Debito | POST | `/1/nfe/emissao/` | API v1 com quatro headers Webmania | `finalidade=6`, `tipo_debito`, produtos com somente `impostos.ibs_cbs`, `dfe_referenciado` quando o tipo exigir | resposta NF-e padrao | XML/DANFE | Sim | 2.4E/2.5 |

### Campos IBS/CBS documentados para planejamento local

| Grupo | Campos/documentos | Decisao Hunter |
| ----- | ----------------- | -------------- |
| Identificacao tributaria | `situacao_tributaria`, `classificacao_tributaria`, `situacao_tributaria_regular`, `classificacao_tributaria_regular` | Nao inferir automaticamente; exigir configuracao fiscal auditavel por classe/produto. |
| IBS | `ibs_estadual`, `ibs_municipal` e respectivos valores/aliquotas condicionais | Modelar como estrutura tributaria versionada por classe fiscal NF-e/NFC-e. |
| CBS | `cbs` e valores/aliquotas condicionais | Modelar junto a IBS/CBS, preservando payload bruto sanitizado. |
| Monofasica/credito | `tributacao_monofasica`, `credito_presumido`, `transferencia_credito` | Implementar somente quando a situacao/classificacao exigir; validar contra tabela oficial antes de codigo. |
| Ajustes | `ajuste_competencia`, `estorno_credito` | Planejar com validacoes por situacao tributaria; nao liberar UI generica sem regra fiscal. |

### Cronograma e obrigatoriedade

- A documentacao Webmania informa obrigatoriedade de preenchimento IBS/CBS em producao para NF-e/NFC-e com data de emissao maior ou igual a `05/01/2026`.
- Essa regra afeta NF-e legada, NFC-e manual simples e possivelmente documentos derivados ja implementados.
- Eventos IBS/CBS sao operacoes posteriores separadas e nao substituem o preenchimento de IBS/CBS na emissao normal.

### Credito/debito e rejeicao 1001

| Operacao | Tipo remoto | Requer IBS/CBS? | Pode implementar antes da fase tributaria? | Evidencia oficial |
| -------- | ----------- | --------------: | -----------------------------------------: | ----------------- |
| Credito | `tipo_credito=1..5` | Sim | Nao | Documentacao NF-e lista finalidade 5; artigo Webmania rejeicao 1001 determina finalidade 5/6 somente para IBS/CBS. |
| Debito | `tipo_debito=1..8` | Sim | Nao | Documentacao NF-e lista finalidade 6; artigo Webmania rejeicao 1001 determina finalidade 5/6 somente para IBS/CBS e veda tributos incompatíveis. |

Campos proibidos em credito/debito quando usados como tributos do item: ICMS, ISSQN, IPI, II, PIS, PIS ST, COFINS, COFINS ST, ICMS UF Destino e imposto devolvido. O payload deve ser restringido a `produtos[].impostos.ibs_cbs` nos itens conforme a regra oficial.

### Separacao confirmada

- Confirmado pela documentacao oficial: endpoints v1, `produtos[].impostos.ibs_cbs`, eventos IBS/CBS, tipos de credito/debito e rejeicao 1001.
- Requisito interno Hunter: bloquear producao quando a configuracao local IBS/CBS estiver ausente para fluxo afetado.
- Decisao pendente: quais situacoes/classificacoes IBS/CBS serao disponibilizadas primeiro na UI administrativa e se a emissao em homologacao podera usar modo controlado sem todos os campos produtivos.

## Fase 2.4C.0 - Matriz API para derivados com IBS/CBS

Fontes oficiais reconsultadas nesta fase documental:

- Documentacao REST NF-e/NFC-e: guia rapido lista `/1/nfe/devolucao/`, `/1/nfe/ajuste/`, `/1/nfe/complementar/` e `/1/nfe/evento-ibs-cbs/` como endpoints separados.
- A mesma documentacao separa Nota Fiscal de Ajuste e Complementar da emissao normal por `/1/nfe/emissao/`.
- Eventos IBS/CBS sao vinculados a NF-e/NFC-e e enviados por `/1/nfe/evento-ibs-cbs/`; isso nao substitui o preenchimento IBS/CBS na emissao quando aplicavel.
- O artigo oficial de rejeicao 1001 confirma que finalidades 5/6 devem se relacionar somente a IBS/CBS e rejeitam ICMS, ISSQN, IPI, II, PIS, COFINS e correlatos.

| Operacao Hunter | Endpoint Webmania | Campos atuais do contrato validado | IBS/CBS oficialmente confirmado para esta operacao derivada? | Decisao 2.4C.0 |
| ---------------- | ----------------- | ---------------------------------- | ----------------------------------------------------------- | -------------- |
| Devolucao | `POST /1/nfe/devolucao/` | `chave`, natureza, ambiente, CFOP, produtos/quantidades quando parcial, informacoes opcionais | A documentacao geral confirma `ibs_cbs` em produtos NF-e/NFC-e, mas a fase precisa revalidar sua aplicacao especifica em devolucao | Planejar 2.4C.1 com snapshot original e bloqueio seguro |
| Estorno | `POST /1/nfe/devolucao/` | Mesmo endpoint de devolucao, com semantica de estorno | Nao confirmado como simples copia de IBS/CBS de devolucao parcial | Planejar payload proprio e manter excecao SC/ES fora de ajuste |
| Complementar preco/quantidade | `POST /1/nfe/complementar/` | `chave`/`uuid`, operacao, natureza, CFOP, ambiente, cliente, produtos | Complementar tributaria e IBS/CBS existem no contexto de Reforma, mas preco/quantidade nao deve abrir complemento tributario automaticamente | Planejar 2.4C.2 com IBS/CBS apenas do acrescimo e sem `impostos` amplos fora do escopo |
| Ajuste | `POST /1/nfe/ajuste/` | A documentacao descreve `operacao`, `natureza_operacao`, `codigo_cfop`, `valor_icms`, `valor_icms_st`, `ambiente`, `cliente`, `situacao_tributaria`, `informacoes_fisco` e `informacoes_complementares`; estorno SC/ES deve usar devolucao | Nao documenta `produtos`, `produtos[].impostos.ibs_cbs`, evento IBS/CBS, `tipo_credito`, `tipo_debito` ou `finalidade=5/6` neste endpoint | Fase 2.4C.3 deve bloquear campos fora do contrato antes do gateway e manter eventos/credito/debito em fases proprias |

Nota de OpenAPI: `webmania_fiscal_openapi_validated.json` nao foi alterado nesta Fase 2.4C.0 porque a consulta oficial nao confirmou novos campos exclusivos para os endpoints derivados alem dos schemas IBS/CBS ja documentados genericamente para produtos NF-e/NFC-e. A implementacao funcional de cada subfase deve revalidar se o endpoint derivado aceita `produtos[].impostos.ibs_cbs` ou depende de `classe_imposto`/snapshot.

## Fase 2.4D.0 - Matriz API dos Eventos IBS/CBS

Fonte oficial reconsultada em 2026-06-02: documentacao Webmania REST NF-e/NFC-e em `https://webmania.com.br/docs/rest-api-nfe/1000/`.

### Rotas oficiais

| Operacao | Metodo | Endpoint | Body documentado | Resposta documentada | Downloads/webhook | Decisao Hunter |
| -------- | ------ | -------- | ---------------- | -------------------- | ----------------- | -------------- |
| Registrar evento IBS/CBS | POST | `/1/nfe/evento-ibs-cbs/` | `chave`, `ambiente`, `cod_evento`, `evento` opcional com padrao 1, `url_notificacao` opcional e campos especificos por evento | `uuid`, `status`, `evento`, `modelo`, `log`; alguns exemplos retornam `xml`/`protocolo_evento` conforme evento/retorno | `url_notificacao` documentada para atualizacoes de status; XML quando retornado | Planejar como `FiscalDocumentEvent(event_type=ibs_cbs)`, vinculado ao documento base local. |
| Cancelar evento IBS/CBS autorizado | PUT | `/1/nfe/evento-ibs-cbs/cancelar/` | `uuid` do evento, `ambiente` opcional, `url_notificacao` opcional | `uuid`, `status`, `cod_evento`, `evento`, `modelo`, `log` | XML/log quando retornados | Planejar subfase propria; criar evento de cancelamento vinculado ao evento IBS/CBS original, nao ao documento como nova nota. |

### Codigos oficiais de evento IBS/CBS

| Codigo | Descricao oficial resumida | Autor | Payload especifico | Documento aplicavel | Cancelavel? | Prioridade Hunter |
| ------ | -------------------------- | ----- | ------------------ | ------------------- | ----------- | ----------------- |
| `112110` | Efetivo pagamento integral para liberar credito presumido do adquirente | Emitente | Sem campos especificos alem do envelope do evento | NF-e/NFC-e com chave local elegivel | Sim, por cancelamento por UUID quando autorizado | Alta; primeira subfase recomendada. |

Implementacao 2.4D.1: somente o `cod_evento=112110` foi implementado. O payload funcional usa `POST /1/nfe/evento-ibs-cbs/` com `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao` quando gerada pelo Hunter. A implementacao bloqueia `ibs_cbs`, produtos, credito/debito, cancelamento e demais campos fora do envelope oficial deste codigo.

Implementacao 2.4D.2: somente o cancelamento do evento `112110` foi implementado. O payload funcional usa `PUT /1/nfe/evento-ibs-cbs/cancelar/` com `uuid` do evento autorizado, `ambiente` opcional coerente com o documento base e `url_notificacao` quando gerada pelo Hunter. A resposta esperada e persistida no evento de cancelamento inclui `uuid`, `status`, `cod_evento=110001`, `evento`, `modelo`, `xml` quando retornado e `log` sanitizado. O Hunter nao envia `chave`, `cod_evento`, `evento`, `ibs_cbs`, produtos, credito/debito, complementar tributaria ou payload da NF-e/NFC-e nesse cancelamento.
| `112120` | Importacao em ALC/ZFM nao convertida em isencao | Emitente | `itens[].item`, `valor_ibs`, `valor_cbs`, `controle_estoque.quantidade`, `controle_estoque.unidade` | NF-e de importacao referenciada | Sim | Baixa para oficina; depende de item/importacao. |
| `112130` | Perecimento, perda, roubo ou furto no transporte contratado pelo fornecedor | Emitente | `itens[]` com `item`, valores IBS/CBS e controle de estoque de perecimento/estorno | NF-e de fornecimento | Sim | Media; depende de regra operacional e estoque. |
| `112140` | Fornecimento nao realizado com pagamento antecipado | Emitente | `itens[]` com item, valores IBS/CBS e quantidade/unidade nao fornecida | NF-e/debito de pagamento antecipado | Sim | Media/baixa; depende de pagamento antecipado. |
| `112150` | Atualizacao da data de previsao de entrega | Emitente | `data_previsao_entrega` | NF-e/NFC-e quando houver entrega/previsao aplicavel | Sim | Media; simples, mas exige regra de entrega. |
| `211110` | Solicitacao de apropriacao de credito presumido | Destinatario | `itens[].item`, `base_calculo`, `credito_presumido.classificacao`, aliquotas e valores IBS/CBS | Documento de aquisicao elegivel | Sim | Baixa; papel de destinatario e pouca aderencia oficina. |
| `211120` | Destinacao de item para consumo pessoal | Emitente e Destinatario | `tipo_autor`, `itens[].item`, valores IBS/CBS, controle de consumo e `dfe_referenciado` quando aplicavel | NF-e de aquisicao/uso | Sim | Baixa/media; depende de destinatario e referencia. |
| `211124` | Perecimento, perda, roubo ou furto no transporte contratado pelo adquirente | Destinatario | `itens[]` com item, valores IBS/CBS e controle de perecimento | NF-e de aquisicao | Sim | Baixa; destinatario e frete FOB. |
| `211128` | Aceite de debito na apuracao por emissao de nota de credito | Destinatario | `indicador_aceitacao` | Documento ligado a nota de credito/debito IBS/CBS | Sim | Bloqueada ate Fase 2.4E/2.5. |
| `211130` | Imobilizacao de item | Destinatario | `itens[]` com item, valores IBS/CBS e controle de imobilizacao | NF-e de aquisicao | Sim | Baixa; uso contábil restrito. |
| `211140` | Apropriacao de credito de combustivel | Destinatario | `itens[]` com item, valores IBS/CBS e controle de combustivel | NF-e de combustivel | Sim | Media baixa; pode ter relevancia futura para oficinas. |
| `211150` | Apropriacao de credito para bens e servicos dependentes da atividade do adquirente | Destinatario | `itens[]` com `valor_credito_ibs` e `valor_credito_cbs` | NF-e de aquisicao | Sim | Baixa/media; depende de regra contábil. |

### Observacoes condicionais

- `evento` e a sequencia do evento, aceita de 1 a 20 e possui padrao 1 na documentacao; o Hunter deve reservar sequencia transacionalmente por documento e `cod_evento`.
- Eventos com `itens[].item` devem usar numero sequencial fiscal do item, nao IDs internos.
- Eventos de destinatario exigem decisao de produto sobre papel do Hunter como destinatario; nao devem ser liberados por padrao para oficinas sem regra fiscal.
- `211128` depende do contexto de nota de credito/debito; por isso permanece bloqueado ate credito/debito com IBS/CBS estar aprovado.
- Cancelamento de evento e operacao propria por UUID remoto do evento autorizado; nao deve ser confundido com cancelamento de NF-e/NFC-e.

## Fase 2.4D.3.0 - Priorizacao dos demais Eventos IBS/CBS

Fonte oficial reconsultada em 2026-06-17: documentacao Webmania REST NF-e/NFC-e em `https://webmania.com.br/docs/rest-api-nfe/1000/`. A documentacao confirma que todos os eventos continuam usando `POST /1/nfe/evento-ibs-cbs/` com envelope `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao`, e que os campos especificos variam por codigo. O cancelamento por UUID continua documentado em `/1/nfe/evento-ibs-cbs/cancelar/`.

| cod_evento | Descricao | Payload especifico? | Documento elegivel | Pode cancelar? | Depende de credito/debito? | Depende de apuracao externa? | Risco | Recomendacao |
| ---------- | --------- | ------------------: | ------------------ | -------------: | -------------------------: | ---------------------------: | ----- | ------------ |
| `112120` | Importacao em ALC/ZFM nao convertida em isencao | Sim: `itens[]`, item fiscal, valores IBS/CBS e controle de estoque/importacao | NF-e de importacao local ou externa validada | Sim | Nao diretamente | Sim, por contexto de importacao/beneficio | Alto | Adiar; baixa aderencia oficina e exige importacao fiscal segura. |
| `112130` | Perecimento, perda, roubo ou furto no transporte contratado pelo fornecedor | Sim: `itens[]`, item fiscal, `valor_ibs`, `valor_cbs`, quantidade/unidade de perecimento | NF-e de fornecimento local com item/snapshot IBS/CBS e contexto de transporte | Sim | Nao | Sim, por evento operacional/estoque/transporte | Medio/alto | Planejar depois de `112150`; exige validacao de estoque/evento operacional. |
| `112140` | Fornecimento nao realizado com pagamento antecipado | Sim: `itens[]`, item fiscal, valores IBS/CBS e quantidade/unidade nao fornecida | NF-e vinculada a pagamento antecipado e entrega nao realizada | Sim | Possivelmente, por pagamento antecipado e nota de debito futura | Sim, por financeiro/apuracao de pagamento | Alto | Adiar ate regra de pagamento antecipado estar modelada. |
| `112150` | Atualizacao da data de previsao de entrega | Sim minimo: `data_previsao_entrega` | NF-e/NFC-e normal local autorizada com entrega prevista rastreavel | Sim | Nao | Baixa; depende apenas de contexto operacional de entrega | Baixo/medio | Recomendada como proxima subfase funcional isolada. |
| `211110` | Solicitacao de apropriacao de credito presumido | Sim: `itens[]`, `base_calculo`, `credito_presumido` com classificacao, aliquotas e valores | Documento de aquisicao; Hunter atuando como destinatario | Sim | Nao necessariamente | Sim, por credito presumido/apuracao | Alto | Adiar; exige papel destinatario e regra contabil/fiscal. |
| `211120` | Destinacao de item para consumo pessoal | Sim: `tipo_autor`, `itens[]`, valores IBS/CBS, controle de consumo e `dfe_referenciado` | NF-e de aquisicao/uso, possivelmente documento externo validado | Sim | Nao diretamente | Sim, por destino de uso e referencia externa | Alto | Adiar; exige papel emitente/destinatario e DF-e referenciado. |
| `211124` | Perecimento, perda, roubo ou furto no transporte contratado pelo adquirente | Sim: `itens[]`, valores IBS/CBS e controle de perecimento | NF-e de aquisicao com frete FOB; Hunter como destinatario | Sim | Nao | Sim, por evento de transporte externo | Alto | Adiar; depende de papel destinatario e frete/estoque. |
| `211128` | Aceite de debito na apuracao por emissao de nota de credito | Sim minimo: `indicador_aceitacao` | Documento relacionado a nota de credito/debito IBS/CBS | Sim | Sim | Sim, por apuracao assistida | Alto | Bloquear ate Fase 2.4E/2.5 funcional de credito/debito. |
| `211130` | Imobilizacao de item | Sim: `itens[]`, valores IBS/CBS e controle de imobilizacao | Documento de aquisicao; Hunter como destinatario | Sim | Nao diretamente | Sim, por ativo imobilizado/contabilidade | Alto | Adiar; exige modulo/decisao contábil. |
| `211140` | Apropriacao de credito de combustivel | Sim: `itens[]`, valores IBS/CBS e controle de combustivel | NF-e de combustivel; Hunter como destinatario | Sim | Nao diretamente | Sim, por apuracao de credito de combustivel | Medio/alto | Adiar; pode ser util futuramente para oficinas, mas exige aquisicao/estoque combustivel. |
| `211150` | Apropriacao de credito para bens/servicos dependentes da atividade do adquirente | Sim: `itens[]`, `valor_credito_ibs`, `valor_credito_cbs` | Documento de aquisicao; Hunter como destinatario | Sim | Nao diretamente | Sim, por regra de atividade do adquirente | Alto | Adiar; exige decisao fiscal/contabil e papel destinatario. |

### Grupos de implementacao 2.4D.3.0

| Grupo | Eventos | Caracteristica | Decisao |
| ----- | ------- | -------------- | ------- |
| A - simples proximos ao 112110 | `112150` | Payload estreito com `data_previsao_entrega`, sem itens ou credito/debito | Proxima subfase recomendada, isolada. |
| B - emitente com itens/controle | `112120`, `112130`, `112140` | Exigem `itens[]`, sequenciais fiscais, valores IBS/CBS e controle operacional/estoque | Implementar em subfases separadas depois de validar fonte operacional. |
| C - dependentes de credito/debito | `211128` | Depende de nota de credito/debito e apuracao assistida | Bloqueado ate credito/debito IBS/CBS funcional. |
| D - destinatario/apuracao externa | `211110`, `211120`, `211124`, `211130`, `211140`, `211150` | Exigem papel de destinatario, documentos de aquisicao, apuracao externa, estoque ou contabilidade | Backlog ate decisao de produto/fiscal. |

Decisao recomendada: a proxima subfase funcional deve ser `2.4D.3 - Implementar somente evento IBS/CBS 112150`, sem generalizar eventos com itens e sem generalizar cancelamento para todos os codigos. O motivo e menor risco fiscal, payload mais estreito, reaproveitamento quase total da infraestrutura `112110`, ausencia de dependencia de credito/debito e testes claros de data de entrega.

Resultado 2.4D.3: `POST /1/nfe/evento-ibs-cbs/` foi implementado somente para `cod_evento=112150`. A revalidacao oficial do exemplo de requisicao mostrou `data_previsao_entrega` como campo de topo do payload, enquanto `evento` permanece a sequencia numerica do evento. O OpenAPI validado permanece alinhado com essa forma operacional. O Hunter nao envia `ibs_cbs`, `itens`, `produtos`, `tipo_credito`, `tipo_debito` ou qualquer dado de cancelamento no `112150`.

Resultado 2.4D.4: `PUT /1/nfe/evento-ibs-cbs/cancelar/` foi implementado tambem para cancelamento do evento `112150` autorizado. A revalidacao oficial confirmou payload de cancelamento por `uuid`, com `ambiente` e `url_notificacao` opcionais/aplicaveis; o Hunter nao envia `chave`, `cod_evento`, `evento`, `data_previsao_entrega`, `ibs_cbs`, produtos, nota fiscal ou credito/debito. O cancelamento do `112110` permanece intacto e nao foi criado cancelamento generico para outros codigos.

## Fase 2.4D.5.0 - Planejamento dos Eventos IBS/CBS 112120, 112130 e 112140

Fonte oficial reconsultada em 2026-06-17: documentacao Webmania REST NF-e/NFC-e em `https://webmania.com.br/docs/rest-api-nfe/1000/`, secao Eventos IBS/CBS. Os tres eventos usam `POST /1/nfe/evento-ibs-cbs/` com envelope `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao` quando aplicavel. A resposta documentada contem `uuid`, `status`, `evento`, `modelo` e `log`.

| cod_evento | Descrição oficial | Payload específico | Exige itens? | Exige valores IBS/CBS? | Fonte local confiável | Documento elegível | Pode cancelar? | Risco | Recomendação |
| ---------- | ----------------- | ------------------ | -----------: | ---------------------: | --------------------- | ------------------ | -------------: | ----- | ------------ |
| `112120` | Importacao em ALC/ZFM nao convertida em isencao. | `itens[].item`, `itens[].valor_ibs`, `itens[].valor_cbs`, `itens[].controle_estoque.quantidade`, `itens[].controle_estoque.unidade`. | Sim | Sim | Snapshot fiscal original com sequencial fiscal e IBS/CBS por item, mais contexto de importacao ALC/ZFM validado. `TaxClassNfe` atual nao e fallback. | NF-e de importacao local emitida/projetada com itens fiscais conhecidos; documento externo somente apos XML/importacao validada. | Sim, pelo endpoint generico de cancelamento de evento, mas em subfase separada. | Alto; baixa aderencia oficina, exige contexto fiscal de importacao/beneficio e quantidade sem conversao. | Adiar; implementar somente apos fluxo confiavel de importacao/ALC-ZFM ou feature fiscal administrativa restrita. |
| `112130` | Perecimento, perda, roubo ou furto durante transporte contratado pelo fornecedor. | `itens[].item`, `valor_ibs`, `valor_cbs`, `controle_estoque.quantidade_perecimento`, `controle_estoque.unidade_perecimento`, `controle_estoque.valor_ibs_estorno`, `controle_estoque.valor_cbs_estorno`. | Sim | Sim | Snapshot fiscal original com sequencial fiscal/IBS/CBS e evento operacional de transporte/estoque com quantidade, unidade e estorno fiscal confirmados. | NF-e normal local de fornecimento, autorizada, com frete/entrega sob responsabilidade do fornecedor e item fiscal conhecido. | Sim, em subfase de cancelamento posterior. | Medio/alto; envolve estoque/transporte e estorno de credito IBS/CBS. | Implementar primeiro entre os tres, mas isoladamente, com input manual fiscal confirmado e bloqueio se faltar snapshot/item. |
| `112140` | Fornecimento nao realizado com pagamento antecipado. | `itens[].item`, `valor_ibs`, `valor_cbs`, `controle_estoque.quantidade_nao_fornecida`, `controle_estoque.unidade_nao_fornecida`. | Sim | Sim | Snapshot fiscal do documento de debito/pagamento antecipado e dados financeiros/operacionais de nao fornecimento. | Documento local vinculado a pagamento antecipado e nao fornecimento; sem origem confiavel, bloquear. | Sim, em subfase de cancelamento posterior. | Alto; depende de pagamento antecipado, possivel nota de debito e regra financeira ainda nao modelada. | Adiar ate credito/debito/financeiro antecipado estarem modelados ou aprovados. |

### Decisao de agrupamento 2.4D.5.0

Decisao: **Opcao B - implementar um por vez**.

Justificativa: apesar de todos exigirem `itens[]`, `valor_ibs` e `valor_cbs`, a semantica fiscal e a fonte operacional divergem. O `112120` depende de importacao ALC/ZFM; o `112130` depende de ocorrencia de transporte/estoque e estorno de credito; o `112140` depende de pagamento antecipado/nao fornecimento e possivel relacao com nota de debito. Agrupar os tres criaria formulario generico perigoso e incentivo a input manual sem fonte fiscal suficiente.

Subfases recomendadas:

| Subfase | Escopo | Motivo |
| ------- | ------ | ------ |
| `2.4D.5.1` | Evento `112130` isolado | Maior aderencia potencial ao dominio operacional de oficina; ainda exige snapshot fiscal e confirmacao de estoque/transporte. |
| `2.4D.5.2` | Cancelamento do evento `112130` | Fechar ciclo do primeiro evento com itens ja validado, sem generalizar cancelamento. |
| `2.4D.6.0` | Planejamento final de `112120` e `112140` | Reavaliar fontes locais antes de qualquer codigo funcional. |
| `2.4D.6.P` | Fase preparatoria para `112120/112140` | Criar/importar fonte fiscal confiavel antes de emissao. |
| `2.4D.6.1` | Evento `112120` isolado | Somente apos importacao/ALC-ZFM validada. |
| `2.4D.6.2` | Evento `112140` isolado | Somente apos nota de debito/pagamento antecipado e vinculo item fiscal. |
| `2.4D.6.3` | Cancelamento dos eventos `112120/112140` | Subfase propria apos emissao de cada evento, usando UUID remoto e sem cancelamento generico. |

### Fontes locais e bloqueios seguros

Fontes permitidas para implementacao futura:

- Snapshot fiscal do documento original em `FiscalDocument.request_payload`, `FiscalDocument.response_payload`, `NfeItem.raw_payload` ou `NfeItem.log_payload`, desde que contenha produtos, sequencial fiscal e IBS/CBS suficiente.
- Dados operacionais de estoque/transporte somente como complemento, nunca como fonte tributaria unica.
- Input manual com confirmacao fiscal explicita apenas para campos operacionais do evento, como quantidade/unidade/valores de estorno, e com payload auditavel.

Bloqueios obrigatorios:

- Bloquear documento externo sem XML/importacao validada.
- Bloquear documento sem snapshot fiscal suficiente.
- Bloquear item sem sequencial fiscal confiavel.
- Bloquear divergencia entre itens selecionados e itens da NF-e/NFC-e original.
- Bloquear valores IBS/CBS ausentes, zerados indevidamente ou incompletos.
- Bloquear uso de `TaxClassNfe` atual como fallback automatico para evento de documento ja emitido.
- Bloquear tentativa de usar qualquer um desses eventos como substituto de credito/debito, complementar tributaria ou ajuste.

OpenAPI: atualizado nesta fase para explicitar os campos oficiais de `controle_estoque` usados por `112120`, `112130` e `112140`. Nenhum endpoint novo foi adicionado.

Resultado 2.4D.5.1: o Hunter implementou somente `cod_evento=112130`. A revalidacao oficial confirmou que o payload operacional usa `itens[]` no topo, com `item`, `valor_ibs`, `valor_cbs` e `controle_estoque` contendo `quantidade_perecimento`, `unidade_perecimento`, `valor_ibs_estorno` e `valor_cbs_estorno`; nao existe top-level `ibs_cbs` neste evento. A implementacao bloqueia documentos sem NF-e normal local autorizada, sem chave, sem snapshot fiscal IBS/CBS por item ou com item fiscal inexistente. `112120`, `112140`, `211xxx` e cancelamento do `112130` permanecem fora do escopo.

Resultado 2.4D.5.2: o Hunter implementou somente o cancelamento do evento `112130` ja autorizado. A revalidacao oficial confirmou `PUT /1/nfe/evento-ibs-cbs/cancelar/` com payload restrito a `uuid`, `ambiente` e `url_notificacao` quando aplicavel. O Hunter nao envia `chave`, `cod_evento`, `evento`, `itens`, `controle_estoque`, `ibs_cbs`, produtos, credito/debito ou campos de cancelamento de documento. O cancelamento atualiza apenas `FiscalDocumentEvent` do cancelamento e, em retorno positivo, marca o evento `112130` original como cancelado sem alterar a NF-e base. `112120`, `112140`, eventos `211xxx` e cancelamento generico permanecem fora do escopo.

## Fase 2.4D.6.0 - Planejamento final dos Eventos IBS/CBS 112120 e 112140

Fonte oficial reconsultada em 2026-06-18: documentacao Webmania REST NF-e/NFC-e em `https://webmania.com.br/docs/rest-api-nfe/1000/`, secao Eventos IBS/CBS. O endpoint permanece `POST /1/nfe/evento-ibs-cbs/`, com envelope `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao` quando aplicavel. A resposta documentada permanece `uuid`, `status`, `evento`, `modelo` e `log`.

| cod_evento | Descrição oficial | Dados locais necessários | Fonte existe hoje? | Dependência | Risco | Decisão |
| ---------- | ----------------- | ------------------------ | -----------------: | ----------- | ----- | ------- |
| `112120` | Importacao em ALC/ZFM nao convertida em isencao; item da NF-e de importacao referenciada, IBS/CBS da quantidade sem conversao e `controle_estoque.quantidade/unidade`. | NF-e de importacao referenciada, item fiscal sequencial, snapshot IBS/CBS original, quantidade/unidade sem atendimento dos requisitos para isencao, contexto ALC/ZFM/importacao validado. | Nao. Ha parser/importacao XML em `apps.stock`, mas nao ha projecao fiscal validada para evento Webmania nem regra ALC/ZFM. | Importacao XML fiscal, validacao de contexto ALC/ZFM e snapshot por item. | Alto | Adiar. Nao implementar sem fase preparatoria de importacao/validacao fiscal e regra ALC/ZFM. |
| `112140` | Fornecimento nao realizado com pagamento antecipado; item da nota de debito de pagamento antecipado, IBS/CBS da quantidade nao fornecida e `controle_estoque.quantidade_nao_fornecida/unidade_nao_fornecida`. | Nota de debito/pagamento antecipado, item fiscal sequencial, snapshot IBS/CBS da nota de debito, vinculo com financeiro/pagamento antecipado e quantidade/unidade nao fornecida. | Nao. O financeiro operacional existe, mas nao ha NF-e de debito/credito funcional nem vinculo fiscal item-pagamento antecipado. | Credito/debito IBS/CBS, financeiro de pagamento antecipado e vinculo item fiscal. | Alto | Adiar. Bloquear ate fase de credito/debito ou fase preparatoria financeira/fiscal. |

Decisao 2.4D.6.0: **Opcao C - adiar ambos**, com recomendacao complementar de **Opcao D - planejar fase preparatoria**. Nenhum dos dois eventos deve ser implementado imediatamente porque a infraestrutura HTTP/evento ja existe, mas as fontes de dominio exigidas pela Webmania ainda nao estao modeladas com seguranca no Hunter.

## Fase 2.5.1.0 - Matriz oficial revalidada de credito/debito

Fonte revalidada em 2026-06-19: documentacao oficial Webmania NF-e/NFC-e, secoes "Emissao de Nota Fiscal de Credito" e "Emissao de Nota Fiscal de Debito". A resposta segue a emissao NF-e normal (`uuid`, `status`, `motivo`, numero, serie, recibo, chave, XML, DANFE e log quando aplicaveis), com notificacao pelo mecanismo NF-e existente quando `url_notificacao` for enviada. Cancelamento e consulta seguem as operacoes gerais do documento emitido; nao existe evento de cancelamento especifico de finalidade 5/6 documentado.

| Operacao | Tipo remoto | Descricao oficial | Requer dfe_referenciado? | Requer item/produto? | Requer financeiro? | Requer evento IBS/CBS? | Pode implementar agora? | Risco |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Credito | 1 | Multa e juros | Nao; `nfe_referenciada` e o campo do credito | Sim | Sim | Nao como pre-condicao oficial | Nao | Alto: sem multa/juros fiscal por item |
| Credito | 2 | Apropriacao de credito presumido de IBS sobre saldo devedor na ZFM | Nao; usa referencia NF-e quando aplicavel | Sim | Sim, apuracao | Nao substituir `211110` | Nao | Critico: ZFM e saldo nao modelados |
| Credito | 3 | Retorno por recusa total ou nao localizacao do destinatario | Nao; usa `nfe_referenciada` | Sim | Nao necessariamente | Nao | Nao | Alto: sem evento logistico fiscal confiavel |
| Credito | 4 | Reducao de valores | Nao; usa `nfe_referenciada` | Sim | Sim | Nao | Nao | Alto: sem causa/base fiscal auditavel |
| Credito | 5 | Transferencia de credito na sucessao | Nao; usa `nfe_referenciada` quando aplicavel | Sim | Sim, apuracao | Nao | Nao | Critico: sucessao nao modelada |
| Debito | 1 | Transferencia de creditos para cooperativas | Nao documentado como obrigatorio | Sim | Sim, apuracao | Nao | Nao | Critico: cooperativa/saldo ausentes |
| Debito | 2 | Anulacao de credito por saidas imunes/isentas | Nao documentado como obrigatorio | Sim | Sim, apuracao | Nao | Nao | Critico: apuracao ausente |
| Debito | 3 | Debitos de notas fiscais nao processadas na apuracao | Sim, em cada produto | Sim | Sim, apuracao | Nao | Nao | Critico: sem apuracao e referencia por item |
| Debito | 4 | Multa e juros | Sim, em cada produto | Sim | Sim | Nao | Nao | Alto: sem multa/juros fiscal e referencia por item |
| Debito | 5 | Transferencia de credito na sucessao | Nao documentado como obrigatorio | Sim | Sim, apuracao | Nao | Nao | Critico: sucessao nao modelada |
| Debito | 6 | Pagamento antecipado | Nao documentado como obrigatorio | Sim | Sim | Relaciona-se ao futuro `112140`, mas nao o substitui | Nao | Critico: sem vinculo adiantamento-item fiscal |
| Debito | 7 | Perda em estoque | Nao documentado como obrigatorio | Sim | Sim, apuracao | Nao substituir `112130`/`211124` | Nao | Critico: movimento de estoque nao prova perda fiscal |
| Debito | 8 | Desenquadramento do SN | Nao documentado como obrigatorio | Sim | Sim, apuracao | Nao | Nao | Critico: sem historico/transicao/apuracao |

Regras comuns confirmadas:

- `produtos` e obrigatorio e cada item deve conter exclusivamente `impostos.ibs_cbs`; ICMS, IPI, PIS, COFINS e correlatos devem ser rejeitados preventivamente.
- `codigo_cfop` permanece obrigatorio na raiz do produto.
- Credito documenta `nfe_referenciada` como array de chaves de 44 digitos; a documentacao nao publica uma matriz de obrigatoriedade por `tipo_credito`, portanto o Hunter nao deve inventar condicional remota e deve exigir fonte fiscal coerente com a hipotese.
- Debito tipos `3` e `4` exigem `produtos[].dfe_referenciado.chave`; `item` identifica o item anterior quando necessario.
- A rejeicao 1001 deve ser prevenida removendo/bloqueando tributos incompatíveis, sem converter automaticamente payload normal em credito/debito.

### Limite implementado na Fase 2.5.1P

Nenhuma rota Webmania foi adicionada. O OpenAPI permanece como contrato futuro de `POST /1/nfe/emissao/`; `FiscalReferencedBasis` e requisito interno Hunter e nao foi representado como endpoint remoto.

## Fase 2.5.2.0 - Matriz de escolha do primeiro tipo

Revalidacao oficial em 2026-06-19: finalidades 5/6 reutilizam `POST /1/nfe/emissao/`, cliente, produtos e pedido. `codigo_cfop` fica na raiz do produto e cada item envia somente `impostos.ibs_cbs`. Credito documenta `nfe_referenciada[]`; debito tipos 3/4 exigem `produtos[].dfe_referenciado`. Resposta, XML/DANFE, webhook, consulta e cancelamento seguem o ciclo geral da NF-e emitida. A rejeicao 1001 deve ser prevenida bloqueando ICMS, IPI, PIS, COFINS, ISSQN e correlatos.

| Tipo | Operacao | Dados exigidos | Fonte existe na 2.5.1P? | Risco fiscal | Risco tecnico | Pode ser o primeiro? |
| --- | --- | --- | ---: | --- | --- | ---: |
| Credito 1 | Multa/juros | NF-e referenciada, produto, CFOP, IBS/CBS, valores de multa/juros | Parcial | Alto: valor fiscal nao tipado | Medio | Nao agora; melhor candidato apos 2.5.2P |
| Credito 2 | Credito presumido IBS ZFM | Apuracao ZFM, saldo e produtos IBS/CBS | Nao | Critico | Alto | Nao |
| Credito 3 | Recusa/nao localizacao | NF-e, itens e evidencia logistica | Parcial | Alto | Alto | Nao |
| Credito 4 | Reducao de valores | Base anterior, reducao por item e motivo | Parcial | Alto | Alto | Nao |
| Credito 5 | Sucessao | Sucessor, saldo e apuracao | Nao | Critico | Alto | Nao |
| Debito 1 | Cooperativas | Cooperativa, saldo, produtos IBS/CBS | Nao | Critico | Alto | Nao |
| Debito 2 | Saidas imunes/isentas | Apuracao e saidas vinculadas | Nao | Critico | Alto | Nao |
| Debito 3 | NFs nao processadas | Apuracao e `dfe_referenciado` por item | Nao | Critico | Alto | Nao |
| Debito 4 | Multa/juros | Produto, valor tipado e `dfe_referenciado` por item | Parcial | Alto | Alto | Nao; mais complexo que credito 1 |
| Debito 5 | Sucessao | Sucessor, saldo e apuracao | Nao | Critico | Alto | Nao |
| Debito 6 | Pagamento antecipado | Adiantamento e vinculo item/financeiro | Parcial | Critico | Alto | Nao |
| Debito 7 | Perda em estoque | Perda fiscal, item e valores | Parcial | Critico | Alto | Nao |
| Debito 8 | Desenquadramento SN | Historico de regime e apuracao | Nao | Critico | Alto | Nao |

O schema OpenAPI atual permanece suficiente; nenhuma correcao oficial adicional foi identificada nesta fase.

Cancelamento: `112120` e `112140` devem seguir o mesmo padrao tecnico de cancelamento por UUID ja validado para `112110`, `112150` e `112130`, mas somente em subfases separadas apos a emissao correspondente existir e possuir testes proprios. Nao criar cancelamento generico de evento IBS/CBS.

Relacao com credito/debito: `112140` depende semanticamente de nota de debito de pagamento antecipado e nao deve ser liberado antes de existir suporte funcional aprovado para credito/debito IBS/CBS ou um fluxo fiscal equivalente que produza documento, item, pagamento antecipado e quantidade nao fornecida auditaveis. `112120` nao depende diretamente de finalidade 5/6, mas depende de importacao ALC/ZFM e validacao fiscal externa.

OpenAPI: o schema validado atual ja contem `NfeIbsCbsEventRequest`, `NfeIbsCbsEventItem` e `NfeIbsCbsEventStockControl` com campos documentados para `112120` e `112140`. Nenhuma correcao de OpenAPI foi necessaria nesta fase.
### Limite da Fase 2.5.2P

Nenhum endpoint, request ou response Webmania foi adicionado. A fase prepara exclusivamente dados internos para uma futura `finalidade=5/6`; o OpenAPI validado permanece inalterado. Credito tipo 1 continua candidato futuro, sem autorizacao de transmissao.
## Fase 2.5.3.0 - Credito tipo 1 multa/juros

Fonte oficial revalidada em 2026-06-22: documentacao REST NF-e/NFC-e Webmania, secao "Emissao de Nota Fiscal de Credito". O endpoint e `POST /1/nfe/emissao/`; credito usa `finalidade=5`, `tipo_credito=1`, `nfe_referenciada[]`, blocos usuais `cliente`, `produtos` e `pedido`, CFOP na raiz do produto e exclusivamente `impostos.ibs_cbs`. A pagina reserva `dfe_referenciado` ao debito tipos 3/4. Resposta, webhook, XML/DANFE, consulta e cancelamento seguem o ciclo geral da NF-e.

### Matriz de pre-condicoes

| Pre-condicao | Fonte atual | Existe? | Bloqueio se ausente? | Observacao |
| --- | --- | ---: | ---: | --- |
| `FiscalReferencedBasis` aprovada | Fase 2.5.1P | Sim | Sim | Deve ser `credit_fine_interest`, oficina ativa e origem elegivel. |
| `FiscalReferencedBasisItem` aprovado | One-to-one validado na 2.5.2P | Sim, pela aprovacao imutavel da base pai | Sim | O item nao possui status independente; a aprovacao da base valida e congela o item. |
| Chave da NF-e original | `source_access_key`/documento original | Sim | Sim | 44 digitos; compoe `nfe_referenciada[]`. |
| Item fiscal sequencial | Base e item comercial | Sim | Sim | Rastreabilidade interna; nao enviar `dfe_referenciado`. |
| Snapshot IBS/CBS por item | `ibs_cbs_snapshot` | Sim | Sim | Identidade/classificacao existe; valores especificos de multa/juros ainda precisam regra confirmada. |
| Snapshot comercial por item | `commercial_snapshot` | Sim | Sim | Descricao/codigo/NCM/unidade/origem historicos. |
| Snapshot monetario por item | `monetary_snapshot` | Sim | Sim | Congela principal, multa, juros, outros e regra. |
| CFOP | `source_item_cfop` | Sim | Sim | Nao copiar automaticamente sem validacao do CFOP aplicavel ao credito. |
| Quantidade fiscal original | `source_quantity` | Sim | Sim | Nao prova qual quantidade deve constar no novo item de multa/juros. |
| Valor unitario fiscal original | `source_unit_price` | Sim | Sim | Nao deve ser repetido silenciosamente no credito. |
| Valor total fiscal original | `source_total_amount` | Sim | Sim | Serve como evidencia/limite, nao como total automatico do credito. |
| Multa | `fine_amount` | Sim | Sim quando multa e parte da hipotese | Decimal, explicita e imutavel. |
| Juros | `interest_amount` | Sim | Sim quando juros sao parte da hipotese | Decimal, explicita e imutavel. |
| Base multa + juros | `credit_debit_base_amount` | Sim | Sim | Deve ser positiva e igual a multa + juros. |
| Feature flag por oficina | `WebmaniaCompany.credit_debit_basis_enabled` | Parcial | Sim | Flag atual libera apenas preparacao; emissao futura deve possuir habilitacao administrativa explicita. |
| Permissao especifica | Planejada `issue_nfe_credit` | Nao | Sim | Permissoes de preparar/aprovar base nao autorizam emissao. |

### Payload futuro confirmado e pontos bloqueados

Envelope confirmado:

```json
{
  "modelo": 1,
  "finalidade": 5,
  "tipo_credito": 1,
  "nfe_referenciada": ["<chave-original-44-digitos>"],
  "cliente": {},
  "produtos": [
    {
      "nome": "<descricao-fiscal-validada>",
      "codigo": "<codigo-historico-ou-especifico-validado>",
      "ncm": "<ncm-validado>",
      "quantidade": "<regra-pendente>",
      "unidade": "<unidade-validada>",
      "subtotal": "<regra-pendente>",
      "total": "<multa-mais-juros, somente apos validacao fiscal>",
      "codigo_cfop": "<cfop-validado>",
      "impostos": {"ibs_cbs": {}}
    }
  ],
  "pedido": {}
}
```

O esqueleto nao autoriza implementacao: `quantidade`, `subtotal`, `total`, CFOP e conteudo/valores de `ibs_cbs` dependem de validacao fiscal. Nao assumir quantidade 1, nao reaproveitar integralmente quantidade/unitario/total originais e nao proporcionalizar IBS/CBS automaticamente.

Campos proibidos: `impostos.icms`, `impostos.ipi`, `impostos.pis`, `impostos.cofins`, `impostos.issqn`, `impostos.ii`, `imposto_devolvido`, `evento_ibs_cbs`, `cod_evento`, `tipo_debito` e `dfe_referenciado`. A rejeicao 1001 deve ser prevenida antes do gateway.

Observacao de contrato: o exemplo oficial atual mostra `modelo="nfe"`, enquanto o contrato operacional validado e os builders Hunter usam `modelo=1`. Registrar a divergencia e revalidar imediatamente antes de qualquer codigo; o OpenAPI nao foi alterado nesta fase porque o contrato operacional existente permanece consistente com os fluxos atuais.
### Pre-payload implementado na 2.5.3P

O preview local contem apenas `modelo=1`, `finalidade=5`, `tipo_credito=1`, `nfe_referenciada[]` e um produto com identidade historica, valores administrativos explicitos, CFOP explicito e `impostos.ibs_cbs` historico. Nao contem `cliente`/`pedido` completos e nao e request transmitivel. O OpenAPI remoto permanece inalterado.

Validador preventivo rejeita qualquer grupo tributario diferente de `ibs_cbs`, alem de `dfe_referenciado`, `evento_ibs_cbs`, `cod_evento` e `tipo_debito`.

### Contrato operacional Fase 2.5.4

`POST /1/nfe/emissao/`: `modelo=1`, `finalidade=5`, `tipo_credito=1`, `nfe_referenciada`, `cliente`, `produtos`, `pedido` e notificacao quando configurada. Cada produto envia `codigo_cfop` e somente `impostos.ibs_cbs`; ICMS, IPI, PIS, COFINS, ISSQN, II, imposto devolvido, debito e campos de evento sao proibidos preventivamente.

### Cancelamento operacional Fase 2.5.5

`PUT /1/nfe/cancelar/` recebe somente `chave` ou `uuid` e `motivo` de 15 a 255 caracteres. O contrato oficial revalidado em 2026-06-22 nao inclui `ambiente`; o Hunter o preserva apenas no documento local. `finalidade`, `tipo_credito`, produtos, impostos, IBS/CBS, campos de evento e `nfce_referenciada` nao sao enviados. Resposta: `status`, `xml`, `xml_cancelamento` e `log` sanitizado.

## Fase 2.5.6.0 - Matriz comparativa do proximo bloco

Revalidacao oficial em 2026-06-22: credito usa `finalidade=5`, debito usa `finalidade=6`; ambos usam `POST /1/nfe/emissao/`, `codigo_cfop` na raiz do produto e somente `produtos[].impostos.ibs_cbs`. Para debito tipos 3 e 4, `dfe_referenciado.chave` e obrigatorio em cada produto e `dfe_referenciado.item` identifica o item quando aplicavel. A regra preventiva da rejeicao 1001 continua proibindo tributos tradicionais nessas finalidades. Cancelamento continua pelo fluxo NF-e padrao.

| Bloco | Candidato | Fonte local existe? | Reaproveita base atual? | Dependencia externa | Risco fiscal | Recomendacao |
| --- | --- | ---: | ---: | --- | ---: | --- |
| Credito | Tipo 2 - credito presumido ZFM | Parcial | Parcial | Apuracao e contexto ZFM | Alto | Adiar |
| Credito | Tipo 3 - recusa/nao localizacao | Nao | Parcial | Evidencia logistica | Alto | Adiar |
| Credito | Tipo 4 - reducao de valores | Parcial | Parcial | Regra fiscal da reducao | Medio/alto | Adiar |
| Credito | Tipo 5 - sucessao | Nao | Baixo | Sucessao e transferencia fiscal | Alto | Adiar |
| Debito | Tipo 1 - transferencia a cooperativas | Nao | Baixo | Cooperativa e transferencia fiscal | Alto | Adiar |
| Debito | Tipo 2 - anulacao por saidas imunes/isentas | Nao | Parcial | Apuracao e qualificacao das saidas | Alto | Adiar |
| Debito | Tipo 3 - notas nao processadas na apuracao | Parcial | Alto | Apuracao fiscal externa; exige `dfe_referenciado` | Alto | Adiar |
| Debito | Tipo 4 - multa/juros | Sim, quase completa | Alto | Validacao fiscal da intencao de debito | Medio | **Preparar preview irma sem transmissao** |
| Debito | Tipo 5 - sucessao | Nao | Baixo | Sucessao e transferencia fiscal | Alto | Adiar |
| Debito | Tipo 6 - pagamento antecipado | Nao | Parcial | Vinculo financeiro-item | Alto | Adiar; pre-requisito de `112140` |
| Debito | Tipo 7 - perda em estoque | Nao | Parcial | Evento fiscal de estoque | Alto | Adiar |
| Debito | Tipo 8 - desenquadramento do SN | Nao | Baixo | Regime/apuracao fiscal externa | Alto | Adiar |
| Evento | `112120` | Nao | Parcial | Importacao ALC/ZFM validada | Alto | Adiar |
| Evento | `112140` | Nao | Parcial | Debito/pagamento antecipado e nao fornecimento | Alto | Adiar |
| Eventos | `211xxx` | Nao suficiente | Baixo/parcial | Papel destinatario, entrada, estoque ou apuracao | Alto | Adiar |
| NFS-e | Expansao | Legado parcial | Baixo | Municipio/provedor e IBS/CBS NFS-e | Alto | Auditoria propria futura |
| CT-e | Primeira implementacao | Nao | Baixo | Dominio de transporte e API v2 | Alto | Adiar |

### Eventos oficiais pendentes revalidados

| Codigo | Descricao oficial resumida | Papel | Bloqueio local |
| --- | --- | --- | --- |
| `112120` | Importacao ALC/ZFM nao convertida em isencao | Emitente | Sem importacao/contexto ALC/ZFM |
| `112140` | Fornecimento nao realizado com pagamento antecipado | Emitente | Sem nota de debito/pagamento antecipado por item |
| `211110` | Apropriacao de credito presumido | Destinatario | Sem apuracao/entrada fiscal |
| `211120` | Destinacao para consumo pessoal | Emitente/destinatario | Sem classificacao operacional auditavel |
| `211124` | Perecimento sob responsabilidade do adquirente | Destinatario | Sem entrada/estoque fiscal do adquirente |
| `211128` | Aceite de debito por nota de credito | Destinatario | Exige fluxo de credito/debito e apuracao |
| `211130` | Imobilizacao de item | Destinatario | Sem ativo imobilizado fiscal |
| `211140` | Apropriacao de credito de combustivel | Destinatario | Sem dominio fiscal de combustivel |
| `211150` | Credito dependente da atividade do adquirente | Destinatario | Sem apuracao/atividade fiscal |

O OpenAPI validado ja contem enums, `nfe_referenciada`, `dfe_referenciado`, regra exclusiva de IBS/CBS e os codigos de evento. Nenhuma correcao foi necessaria nesta fase.

Implementacao 2.5.6P: somente pre-payload local com `modelo=1`, `finalidade=6`, `tipo_debito=4` e `produtos[].dfe_referenciado`; nenhum endpoint remoto foi chamado ou exposto.

## Fase 2.5.7.0 - Contrato final planejado para debito tipo 4

### Contrato implementado na Fase 2.5.7

`POST /1/nfe/emissao/` com `modelo=1`, `finalidade=6`, `tipo_debito=4`, cliente, pedido e produtos vindos da preview. Cada produto inclui `codigo_cfop`, `dfe_referenciado` e somente `impostos.ibs_cbs`. Nao sao enviados `nfe_referenciada`, `tipo_credito`, tributos tradicionais ou campos de evento. O OpenAPI validado nao exigiu correcao.

### Contrato revalidado para Fase 2.5.8

`PUT /1/nfe/cancelar/` recebe somente `chave` ou `uuid` e `motivo` entre 15 e 255 caracteres. O ambiente permanece auditado localmente e nao integra o body oficial. Nao enviar `nfce_referenciada`, finalidade, tipo de debito, produto, imposto, DF-e referenciado ou campo de evento IBS/CBS. Resposta confirmada: `status`, `xml`, `xml_cancelamento` e `log`.
Fonte oficial revalidada em 2026-06-22: `POST /1/nfe/emissao/`, `finalidade=6`, `tipo_debito=4`, `codigo_cfop` na raiz do produto, `dfe_referenciado.chave` obrigatorio por produto e `dfe_referenciado.item` para o sequencial fiscal. Cada produto envia somente `impostos.ibs_cbs`.

`nfe_referenciada` **nao sera enviada**: a documentacao a define na secao de credito; para debito tipos 3/4, a referencia operacional documentada e `produtos[].dfe_referenciado`.

Payload futuro:

```json
{
  "ID": "debit-preview-{preview_id}",
  "operacao": 1,
  "natureza_operacao": "Debito por multa e juros",
  "modelo": 1,
  "finalidade": 6,
  "tipo_debito": 4,
  "ambiente": 2,
  "cliente": {},
  "produtos": [{
    "nome": "snapshot aprovado",
    "codigo": "snapshot aprovado",
    "ncm": "snapshot aprovado",
    "quantidade": "valor explicito da preview",
    "unidade": "snapshot aprovado",
    "subtotal": "unitario explicito da preview",
    "total": "total explicito da preview",
    "codigo_cfop": "CFOP aprovado",
    "dfe_referenciado": {"chave": "44 digitos", "item": 1},
    "impostos": {"ibs_cbs": {}}
  }],
  "pedido": {}
}
```

Campos proibidos: `nfe_referenciada`, `tipo_credito`, `nfe_credito`, `evento_ibs_cbs`, `cod_evento`, `imposto_devolvido` e qualquer grupo em `impostos` diferente de `ibs_cbs`, incluindo ICMS, IPI, PIS, COFINS, ISSQN e II.

Resposta e notificacao seguem NF-e padrao: UUID, status/motivo, numero, serie, recibo, chave, XML, DANFE e log sanitizado. Cancelamento futuro usa `PUT /1/nfe/cancelar/`, nunca cancelamento de evento IBS/CBS.

O OpenAPI validado ja representa todos esses campos e condicoes; nenhuma alteracao foi necessaria.

## Fase 2.6.0 - Matriz comparativa do roadmap

Revalidacao oficial em 2026-06-23: NF-e/NFC-e mantem finalidades 5/6, tipos oficiais, IBS/CBS exclusivo e eventos pendentes; NFS-e v2 documenta emissao, consulta, cancelamento, substituicao, manifestacao, capacidades municipais e IBS/CBS; CT-e, MDF-e, NFCom e DC-e possuem APIs v2 delimitadas. NFCom e DC-e agora aparecem como versao 2.0.0, sem marcador beta oficial.

| Bloco | Candidato | Fonte local existe? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| --- | --- | ---: | ---: | --- | --- | --- | --- |
| Credito | Tipo 2 - credito presumido ZFM | Nao suficiente | Alta | Apuracao IBS e contexto ZFM | Alto | Baixo | Adiar |
| Credito | Tipo 3 - recusa/nao localizacao | Parcial | Alta | Evidencia logistica auditavel | Alto | Medio | Fase preparatoria futura |
| Credito | Tipo 4 - reducao de valores | Parcial | Alta | Regra fiscal e valores aprovados | Medio/alto | Medio | Adiar |
| Credito | Tipo 5 - sucessao | Nao | Media | Sucessao juridica/fiscal | Alto | Baixo | Adiar |
| Debito | Tipo 1 - cooperativas | Nao | Media | Credito/cooperativa | Alto | Baixo | Adiar |
| Debito | Tipo 2 - saidas imunes/isentas | Nao | Media | Apuracao fiscal | Alto | Baixo | Adiar |
| Debito | Tipo 3 - notas fora da apuracao | Parcial | Alta | Apuracao externa e DF-e por item | Alto | Medio | Adiar |
| Debito | Tipo 5 - sucessao | Nao | Media | Sucessao juridica/fiscal | Alto | Baixo | Adiar |
| Debito | Tipo 6 - pagamento antecipado | Nao suficiente | Media | Vinculo financeiro-item e nao fornecimento | Alto | Medio | Fase preparatoria futura; desbloqueia `112140` |
| Debito | Tipo 7 - perda em estoque | Parcial | Media | Evidencia fiscal de estoque | Alto | Medio | Fase preparatoria futura |
| Debito | Tipo 8 - desenquadramento SN | Nao | Baixa | Regime e apuracao externa | Alto | Baixo | Adiar |
| Evento | `112120` | Nao | Alta | Importacao ALC/ZFM validada | Alto | Baixo | Adiar |
| Evento | `112140` | Nao | Alta | Debito tipo 6 e pagamento antecipado por item | Alto | Medio | Adiar |
| Eventos | `211xxx` | Nao suficiente | Alta tecnica, baixa de dominio | Papel destinatario, entrada, ativo, combustivel ou apuracao | Alto | Baixo/medio | Adiar |
| NF-e | Complementar tributaria | Parcial | Alta | Base tributaria aprovada por imposto | Alto | Medio | Auditoria preparatoria posterior |
| NFS-e | Expansao e conformidade | Sim, legado operacional | Alta | Municipio/provedor, Padrao Nacional e IBS/CBS | Medio/alto | **Muito alto** | **Proxima Fase 3.0 documental** |
| CT-e | Emissao/operacao | Nao | Media tecnica | Dominio de transporte, tomadores e cargas | Alto | Baixo | Adiar |
| MDF-e | Emissao/encerramento | Nao | Baixa | CT-e, veiculos, condutores e percurso | Alto | Baixo | Adiar apos CT-e |
| NFCom | Emissao v2.0.0 | Nao | Media tecnica | Dominio de telecomunicacoes | Alto | Muito baixo | Adiar; flag interna |
| DC-e | Emissao v2.0.0 | Nao | Media tecnica | Dominio especifico sem demanda confirmada | Alto | Muito baixo | Adiar; flag interna |

### Decisao

Escolher **Opcao D com fase preparatoria**: `Fase 3.0 - Auditoria e Planejamento Tecnico da NFS-e Expandida`. O OpenAPI foi corrigido somente para remover a classificacao beta desatualizada de NFCom/DC-e e registrar API v2.0.0; os schemas e endpoints permanecem suficientes para planejamento.

## Fase 3.0 - Matriz operacional NFS-e

Documentacao oficial revalidada em 2026-06-23: Webmania NFS-e v3.1.1 e Portal Nacional NFS-e, documentacao de producao vigente. A API Webmania usa Bearer API 2.0 e `Content-Type`/`Accept: application/json`.

| Operacao | Endpoint/contrato | Metodo | Existe no Hunter? | Qualidade atual | Lacunas | Proxima acao |
| --- | --- | --- | ---: | --- | --- | --- |
| Emissao | `/2/nfse/emissao` | POST | Sim | Tentativa persistida, RPS, lote/item e `uncertain` | Acoplada a OS; sem capacidade municipal persistida; operation type generico | 3.1 estabilizar e bloquear por capacidade |
| Consulta | `/2/nfse/consulta/{uuid}` | GET | Sim | Consulta por UUID e reconciliacao sem emissao | Sem trilha de consulta/lote e sem timestamp remoto canonico | 3.2 ampliar reconciliacao |
| Cancelamento/agendamento | `/2/nfse/cancelar` com `uuid`, `motivo` 1/2/4 | PUT | Sim | UI e endpoint funcionais | Sem tentativa/idempotencia/`uncertain`; confirma cancelamento cedo demais | 3.3 reimplementar sobre evento/tentativa |
| Substituicao | `/2/nfse/substituir` com `ambiente`, `codigo_verificacao`, `motivo`, `rps` objeto | POST | Nao | Ausente | Capacidade municipal, documento substituto, link e idempotencia | 3.4 apos 3.1-3.3 |
| Manifestacao | `/2/nfse/manifestar`; somente Padrao Nacional | POST | Nao | Ausente | Papel tomador/intermediario, evento, rejeicao, permissao e capacidade | 3.6.x apos planejamento 3.6.0 |
| Status municipal | `/2/nfse/status` | GET | Nao | Configuracao local estatica | Falta persistir `status`, modelo, versao, ambientes, autenticacao, emissao, funcoes, servicos e parametros | 3.1 criar snapshot de capacidade |
| Agendamento | `data_agendamento` na emissao; cancelamento pelo endpoint padrao | POST/PUT | Nao na UI/payload | Status local possui `scheduled` | Falta capacidade, timezone, idempotencia e UX | Adiar para subfase propria apos 3.3 |
| XML/PDF | URLs `xml`, `pdf_nfse`, `pdf_rps`; acesso autenticado/token/IP/painel | GET por URL retornada | Sim | Proxy autenticado e permissao legada | Permissoes granulares e politica de disponibilidade/senha | fase posterior consolidar |
| Webhook | POST em `url_notificacao`, modelos `nfse`/`lote_rps` | POST inbound | Sim | Fingerprint, UUID e anti-regressao por rank | Ordem nao garantida; falta usar `atualizado_em` canonico | 3.1 estabilizar |
| Reconciliacao | consulta por UUID | GET | Sim | Itens pendentes e tentativas incertas, sem POST | Cobertura limitada a item; falta lote/eventos futuros | 3.2 ampliar |

### Contratos confirmados

- Emissao aceita `ID`, `ambiente`, `rps` (1 a 50), `url_notificacao` e `data_agendamento`; lote em massa depende de `lote_rps` no status municipal.
- Retorno pode ser `nfse` ou `lote_rps`; estados documentados incluem processamento/processando, aprovado/processado, agendado, reprovado, cancelado e contingencia conforme modelo.
- Webhooks nao garantem ordem. `atualizado_em` ISO-8601 e a referencia canonica; atualizacoes mais antigas do mesmo UUID devem ser descartadas.
- Substituicao referencia a nota por `codigo_verificacao`, nao por `uuid` no body oficial atual, e recebe um unico objeto `rps`.
- Manifestacao exige `ambiente`, `chave|uuid`, `manifestador` 1/2 e `evento` 1/2; rejeicao exige motivo e, para motivo 9, justificativa de 15 a 255 caracteres.
- O Padrao Nacional vigente publica manuais de contribuinte, APIs ADN, anexos DPS/NFS-e e eventos. DPS e o artefato nacional; RPS/lote permanecem contratos Webmania/provedores municipais e nao devem ser tratados como sinonimos automaticos. Hunter continuara integrando pela Webmania; esses documentos sao referencia semantica, nao um segundo gateway.

### Resultado operacional da Fase 3.1

Emissao legada passou a consultar capacidade municipal antes do POST; webhook e consulta persistem `atualizado_em` e rejeitam retorno antigo/regressivo; reconciliacao continua usando somente `GET /2/nfse/consulta/{uuid}`. Nao houve mudanca adicional no OpenAPI validado nesta implementacao.

### Matriz implementada na Fase 3.2

| Operacao | Endpoint | Resultado local | Garantia |
| --- | --- | --- | --- |
| Consultar NFS-e | `GET /2/nfse/consulta/{uuid}` | `NfseItem`, request, XML/PDF/RPS e auditoria | UUID/modelo unicos; rank + `atualizado_em`; sem POST/PUT |
| Consultar lote RPS | `GET /2/nfse/consulta/{uuid}` | `NfseBatch` e itens de `info_nfse` em transacao | rollback integral em ambiguidade; sem reemissao |
| Status municipal | `GET /2/nfse/status` | `remote_status`, payload sanitizado, horario e erro | nao altera provider, versao ou flags administrativas |

O OpenAPI validado ja representava os dois GETs e nao precisou de alteracao na Fase 3.2.
## NFS-e - cancelamento idempotente legado

| Operacao | Endpoint | Metodo | Body confirmado | Persistencia Hunter |
| --- | --- | --- | --- | --- |
| Cancelar NFS-e | `/2/nfse/cancelar` | `PUT` | somente `uuid` e `motivo` (`1`, `2` ou `4`) | `NfseCancellation` e tentativa `nfse_cancellation` |

O retorno confirmado pode conter `uuid`, `status=cancelado`, `xml` e `log`. O XML de cancelamento pertence a trilha de cancelamento e nao substitui o XML original da NFS-e.

## Fase 3.4.0 - contrato oficial de substituicao NFS-e

Fonte revalidada em 2026-06-23: [documentacao oficial Webmania NFS-e](https://webmania.com.br/docs/rest-api-nfse/).

| Aspecto | Contrato confirmado | Decisao Hunter |
| --- | --- | --- |
| Endpoint | `POST /2/nfse/substituir` | sem chamada na 3.4.0/3.4P |
| Identificacao original | o texto introdutorio cita `uuid` e `motivo`; tabela/exemplo usam `codigo_verificacao` e nao exibem `uuid` | tratar como inconsistencia oficial; congelar UUID e codigo de verificacao, transmitir somente apos nova confirmacao de contrato |
| Body da tabela/exemplo | `ambiente`, `codigo_verificacao`, `motivo` (`1`, `2`, `4`) e `rps` objeto | preview deve conter exatamente esses blocos e manter UUID original como metadado interno |
| Novo documento | `rps` e convertido na NFS-e substituta | exige snapshot novo, completo e aprovado; nao reutilizar dados mutaveis automaticamente |
| Retorno | UUID/status/numero/codigo de verificacao/serie e numero RPS da substituta, `nfse_substituida`, XML e log | criar item substituto e relacionar original somente na fase funcional |
| Webhook | notificacao NFS-e padrao por UUID, com `atualizado_em`; ordem nao garantida | resolver substituta por UUID, tentativa e referencia original; ambiguidade bloqueia |
| Capacidade | `/2/nfse/status` inclui funcao `substituir` | exigir capability e feature flag; status remoto nao altera flag administrativa |

O OpenAPI validado ja representa a tabela/exemplo oficial com `ambiente`, `codigo_verificacao`, `motivo` e `rps` objeto. Nenhuma alteracao foi necessaria nesta fase.

Na Fase 3.4P o contrato e apenas pre-payload local: `{ambiente, codigo_verificacao, motivo, rps}`. Nao existe chamada HTTP, `uuid` enviado, `url_notificacao`, webhook ou consulta remota de substituicao.

Na Fase 3.4.1 o mesmo objeto congelado e enviado por `POST /2/nfse/substituir`. Nao se envia `uuid`, `url_notificacao` ou campos livres. Resposta mapeada: `uuid`, `status`, `numero`, `codigo_verificacao`, `serie_rps`, `numero_rps`, `nfse_substituida`, `xml`, `pdf`/`pdf_nfse` e `log`. O OpenAPI validado permaneceu suficiente e nao foi alterado.

## Fase 3.5.0 - Matriz comparativa do proximo bloco apos NFS-e legada

Reavaliacao em 2026-06-26: a NFS-e legada ja possui estabilizacao, consulta/reconciliacao, cancelamento idempotente, preview de substituicao e substituicao remota idempotente. O codigo atual confirma `NfseCancellation`, `NfseSubstitutionPreview`, `NfseSubstitution`, `NfseMunicipalCapability.manifestation_enabled`, reconciliacao GET-only e bloqueios para operacoes incertas. Nao existe ainda service de manifestacao NFS-e nem emissao manual fiscal nova fora do fluxo legado por OS.

| Bloco | Fonte local existe? | Reaproveita infraestrutura atual? | Dependencia externa | Risco fiscal | Valor de negocio | Recomendacao |
| ----- | ------------------: | --------------------------------: | ------------------- | ------------ | ---------------- | ------------ |
| Manifestacao de NFS-e | Parcial: UUID/chave/capacidade e selecao administrativa | Alta: capacidade municipal, webhook, tentativa, payload sanitizado e reconciliacao consultiva | Padrao Nacional, papel do manifestador e evento/motivo | Medio/alto | Alto | **Priorizar Fase 3.5.1 em subfase propria** |
| Emissao manual nova de NFS-e | Parcial: RPS/servico/tomador existem no legado, mas acoplados a OS | Media | Municipio/provedor, ISS/IBS-CBS, serie/RPS, rollout por oficina | Alto | Muito alto | Adiar para fase posterior apos manifestacao ou nova decisao |
| NFS-e expandida | Parcial | Media | Padrao Nacional, DPS, municipio/provedor e modelagem `FiscalDocument(nfse)` | Alto | Muito alto | Nao executar como bloco amplo; quebrar em subfases |
| CT-e | Nao | Media tecnica | Dominio de transporte, tomador/remetente/destinatario, carga e API v2 | Alto | Baixo/medio | Adiar |
| MDF-e | Nao | Baixa | CT-e/NF-e vinculados, veiculo, condutor, percurso e encerramento | Alto | Baixo | Adiar apos CT-e |
| NFCom | Nao | Media tecnica | Dominio de telecomunicacoes e habilitacao administrativa | Alto | Muito baixo | Adiar; manter feature flag interna |
| DC-e | Nao | Media tecnica | Dominio especifico sem demanda confirmada | Alto | Muito baixo | Adiar; manter feature flag interna |
| Eventos `112120` | Nao | Alta tecnica | Importacao ALC/ZFM validada | Alto | Baixo | Adiar |
| Eventos `112140` | Nao suficiente | Alta tecnica | Debito tipo 6, pagamento antecipado e nao fornecimento por item | Alto | Medio | Adiar ate base de debito/pagamento |
| Eventos `211xxx` | Nao suficiente | Alta tecnica, baixa de dominio | Papel destinatario, entrada fiscal, estoque, ativo, combustivel ou apuracao | Alto | Baixo/medio | Adiar |
| Credito tipo 2 | Nao suficiente | Alta tecnica | Credito presumido ZFM e apuracao IBS/CBS | Alto | Baixo | Adiar |
| Credito tipo 3 | Parcial | Alta tecnica | Evidencia de recusa/nao localizacao e logistica auditavel | Alto | Medio | Fase preparatoria futura |
| Credito tipo 4 | Parcial | Alta tecnica | Regra de reducao de valores e base aprovada | Medio/alto | Medio | Adiar |
| Credito tipo 5 | Nao | Media | Sucessao juridica/fiscal | Alto | Baixo | Adiar |
| Debito tipo 1 | Nao | Media | Cooperativa e transferencia fiscal | Alto | Baixo | Adiar |
| Debito tipo 2 | Nao | Media | Saidas imunes/isentas e apuracao fiscal | Alto | Baixo | Adiar |
| Debito tipo 3 | Parcial | Alta tecnica | Notas fora da apuracao e DF-e por item | Alto | Medio | Adiar |
| Debito tipo 5 | Nao | Media | Sucessao juridica/fiscal | Alto | Baixo | Adiar |
| Debito tipo 6 | Nao suficiente | Media | Pagamento antecipado, vinculo financeiro-item e nao fornecimento | Alto | Medio | Preparar antes de `112140`, nao agora |
| Debito tipo 7 | Parcial | Media | Perda em estoque e evidencia fiscal operacional | Alto | Medio | Fase preparatoria futura |
| Debito tipo 8 | Nao | Baixa | Desenquadramento Simples Nacional e apuracao externa | Alto | Baixo | Adiar |
| Complementar tributaria | Parcial | Alta | Base tributaria aprovada por imposto e regra IBS/CBS aplicavel | Alto | Medio | Auditoria preparatoria posterior |

### Decisao

Escolher **manifestacao de NFS-e Padrao Nacional** como proximo bloco, em fase propria e pequena. Ela reaproveita as garantias ja validadas na NFS-e legada sem criar nova NFS-e, sem reconstruir RPS, sem alterar XML original e sem abrir uma familia fiscal nova. A fase funcional deve ser restrita a NFS-e local elegivel, capacidade municipal com `manifestation_enabled`, permissao propria, payload congelado, tentativa antes do POST, timeout `uncertain`, webhook sem ambiguidade e reconciliacao somente consultiva.

### Escopo proposto da proxima fase

- Implementar somente `POST /2/nfse/manifestar` para NFS-e local existente e elegivel.
- Exigir capacidade municipal, feature flag/permissao especifica, papel do manifestador (`1` ou `2`), evento (`1` ou `2`) e motivo/justificativa quando aplicavel.
- Criar trilha auditavel propria, sem `FiscalDocument(nfse)` generalizado e sem alterar a NFS-e original exceto por evento confirmado.
- Preservar XML/PDF/RPS originais; qualquer XML/evento de manifestacao deve ficar separado.
- Reconciliar apenas por GET quando houver identificador remoto suficiente; nunca repetir POST em `uncertain`.

O OpenAPI validado ja contem o endpoint de manifestacao NFS-e e nao exigiu alteracao nesta fase.

## Fase 3.6.0 - Contrato e planejamento da manifestacao NFS-e Padrao Nacional

Fonte oficial revalidada em 2026-06-26: [documentacao oficial Webmania NFS-e](https://webmania.com.br/docs/rest-api-nfse/).

### Contrato oficial encontrado

| Aspecto | Contrato revalidado | Decisao Hunter |
| --- | --- | --- |
| Endpoint | `POST /2/nfse/manifestar` | planejar somente; sem codigo funcional nesta fase |
| Autenticacao | API v2 Bearer com `Content-Type: application/json` e `Accept: application/json` | reaproveitar gateway NFS-e v2 futuramente |
| Escopo | Manifestacao de participacao na NFS-e para documentos no Padrao Nacional | bloquear se Padrao Nacional nao estiver confirmado |
| Identificador | `chave` ou `uuid` da NFS-e | exigir um identificador remoto nao ambiguo; preferir UUID local quando existir |
| Ambiente | `ambiente` (`1` producao, `2` homologacao) | derivar da empresa/oficina e congelar no payload |
| Manifestador | `manifestador=1` tomador; `manifestador=2` intermediario | exigir selecao explicita e permissao propria |
| Evento | `evento=1` confirmacao; `evento=2` rejeicao | implementar por tipo em fase funcional; nao inferir evento automaticamente |
| Rejeicao | `motivo_rejeicao` `1..5` ou `9`; `justificativa_rejeicao` obrigatoria para motivo `9`, 15 a 255 caracteres | validar antes do gateway |
| Resposta | estrutura NFS-e padrao com status/log e possivel UUID/modelo de manifestacao | persistir retorno sanitizado em trilha propria |
| Artefatos | documentacao nao garante XML proprio de manifestacao em todos os retornos | tratar XML/artefato como opcional e separado do XML da NFS-e |
| Webhook | notificacao fiscal padrao pode usar `modelo=manifestacao_nfse`; webhooks podem chegar fora de ordem | resolver sem ambiguidade; nao alterar NFS-e original indevidamente |
| Consulta/reconciliacao | nao ha endpoint especifico de consulta de manifestacao separado do contrato NFS-e geral | usar somente GET seguro quando houver UUID remoto suficiente; nunca repetir POST |
| Cancelamento/retificacao | nenhum endpoint oficial claro para desfazer/cancelar manifestacao foi encontrado | nao implementar desfazer; nova manifestacao do mesmo tipo fica bloqueada ate confirmacao oficial |

Divergencia/lacuna: a secao de `/2/nfse/status` documenta funcoes municipais como `consultar`, `cancelar` e `substituir`, mas nao confirma claramente `manifestar` no exemplo de `funcoes`. Portanto, a disponibilidade local deve exigir `NfseMunicipalCapability.manifestation_enabled` e confirmacao administrativa/nacional; se o sistema nao confirmar Padrao Nacional, bloquear antes do gateway.

### Matriz de tipos de manifestacao

| Tipo de manifestacao | Descricao oficial | Quem pode manifestar | Documento elegivel | Payload especifico | Pode desfazer? | Risco | Recomendacao |
| -------------------- | ----------------- | -------------------- | ------------------ | ------------------ | -------------: | ----- | ------------ |
| Confirmacao | Confirmar participacao na NFS-e | Tomador (`manifestador=1`) ou intermediario (`manifestador=2`) conforme relacao fiscal | NFS-e Padrao Nacional identificada por `uuid` ou `chave` | `ambiente`, `uuid|chave`, `manifestador`, `evento=1` | Nao confirmado | Medio | Implementavel apos fase funcional com capability/flag |
| Rejeicao | Rejeitar participacao na NFS-e | Tomador (`manifestador=1`) ou intermediario (`manifestador=2`) conforme relacao fiscal | NFS-e Padrao Nacional identificada por `uuid` ou `chave` | `ambiente`, `uuid|chave`, `manifestador`, `evento=2`, `motivo_rejeicao`; `justificativa_rejeicao` se motivo `9` | Nao confirmado | Medio/alto | Implementavel com validacao forte e confirmacao explicita |

Motivos oficiais revalidados para rejeicao: `1`, `2`, `3`, `4`, `5` e `9`. A documentacao consultada nao apresentou endpoint de cancelamento/retificacao da manifestacao; desfazer deve ficar bloqueado ate confirmacao oficial.

### Matriz de documentos elegiveis

| Documento | Elegivel? | Motivo | Bloqueio |
| --------- | --------: | ------ | -------- |
| NFS-e emitida localmente | Sim, condicionado | Existe `NfseItem`, UUID/chave/codigo e oficina; deve ser Padrao Nacional confirmado | bloquear se municipal legada, sem Padrao Nacional ou sem relacao de manifestador |
| NFS-e substituta | Sim, condicionado | E nova NFS-e com UUID/status proprios apos substituicao confirmada | bloquear se substituicao incerta ou sem identificador remoto |
| NFS-e cancelada | Nao | Documento terminal; manifestacao posterior pode conflitar com estado fiscal | bloquear por status cancelado |
| NFS-e substituida | Nao por padrao | Original foi encerrada por substituicao; manifestar a substituta quando aplicavel | bloquear por status substituido |
| NFS-e recebida/importada de terceiro | Adiar | Endpoint aceita chave/UUID, mas nao existe dominio local de entrada/importacao NFS-e | bloquear ate fase de importacao/projecao externa |
| NFS-e sem XML | Sim, condicionado | Manifestacao depende de identificador, nao necessariamente de XML local | bloquear se tambem faltar identificador ou Padrao Nacional |
| NFS-e sem UUID | Parcial | Contrato aceita `chave`, mas o legado local trabalha melhor por UUID | permitir somente com chave remota unica e sem ambiguidade; caso contrario bloquear |
| NFS-e sem codigo de verificacao | Sim, condicionado | Manifestacao oficial usa `uuid` ou `chave`, nao `codigo_verificacao` | bloquear se ausencia indicar documento local incompleto/nao reconciliado |
| NFS-e `uncertain` | Nao | Estado remoto inconclusivo nao permite evento seguro | bloquear ate reconciliacao |

### Decisao final

Recomendar implementacao direta em fase funcional pequena, **sem preview previa**, porque a manifestacao nao cria novo RPS nem documento substituto e o payload e pequeno. A excecao e rejeicao: a UI futura deve ter confirmacao explicita, motivo e justificativa quando aplicavel. A fase funcional continua bloqueada ate aprovacao propria.

### Contrato implementado na Fase 3.6.1

`POST /2/nfse/manifestar` com `ambiente`, `uuid`, `manifestador`, `evento` e, para rejeicao, `motivo_rejeicao` e `justificativa_rejeicao` quando motivo `9`. Nao enviar RPS, servico, tomador, payload de emissao, payload de cancelamento, payload de substituicao ou campos livres.

Webhook esperado: `modelo=manifestacao_nfse` com UUID remoto da manifestacao. Sem UUID suficiente, o evento fica pendente. Reconciliacao futura usa somente GET consultivo por UUID remoto, sem repetir POST.

## Fase 3.7.0 - Reavaliacao de matriz API apos manifestacao NFS-e

A Fase 3.6.1 validou `POST /2/nfse/manifestar` no checkpoint `da3b2b48`. A proxima API de maior valor para produto e `POST /2/nfse/emissao`, mas a matriz atual recomenda **fase preparatoria sem HTTP** antes de abrir emissao manual nova.

| Candidato | Endpoint Webmania | Clareza do contrato | Fonte local | Reaproveitamento | Decisao |
| --- | --- | --- | --- | --- | --- |
| Emissao manual nova de NFS-e | `POST /2/nfse/emissao` | Clara em alto nivel, variavel por municipio/provedor | Preview imutavel aprovada na 3.7P | Medio/alto | 3.7.1 transmite somente payload congelado |
| NFS-e recebida/importada | `GET /2/nfse/consulta/{identifier}` e futura manifestacao | Parcial para documento de terceiro | Insuficiente | Medio | Adiar ate XML/identidade/papel fiscal seguro |
| CT-e/MDF-e/NFCom/DC-e | APIs v2 correspondentes | Clara em alto nivel | Ausente | Baixo/medio | Adiar por falta de dominio local |
| Eventos IBS/CBS pendentes | `/1/nfe/evento-ibs-cbs/` | Clara por codigo, dependente de campos especificos | Insuficiente | Alto tecnico | Adiar ate fonte fiscal por evento |
| Creditos/debitos restantes | `/1/nfe/emissao/` | Clara em alto nivel, condicional por tipo | Insuficiente | Alto tecnico | Adiar |

### Fase 3.7.1 - contrato usado para emissao manual NFS-e

Endpoint: `POST /2/nfse/emissao`, Bearer v2. O OpenAPI local validado descreve emissao por RPS/lote e suporte a varios RPS. Por isso, a 3.7.1 envia exatamente o `request_payload` congelado na preview aprovada, atualmente no formato:

```json
{"ambiente": 2, "rps": [{"numero": 4001, "serie": "MAN", "servico": {}, "tomador": {}}]}
```

Nao ha transformacao para `rps` objeto, nem recalculo de tomador, servico, valores, tributacao, retencoes ou IBS/CBS. A resposta NFS-e aprovada cria `NfseItem` manual; respostas em processamento permanecem como intencao `sent`; timeout ou identidade insegura fica `uncertain`.
| Complementar tributaria | `/1/nfe/complementar/` | Parcial para imposto/IBS-CBS | Parcial | Alto tecnico | Adiar para auditoria propria |

OpenAPI: o schema validado permanece suficiente; nao houve correcao oficial nova que justifique alterar `api/webmania_fiscal_openapi_validated.json`.

## Fase 3.8.0 - Reavaliacao do ciclo pos-emissao manual NFS-e

Fonte oficial revalidada em 2026-06-28: [documentacao oficial Webmania NFS-e](https://webmania.com.br/docs/rest-api-nfse/). Os endpoints `POST /2/nfse/emissao`, `PUT /2/nfse/cancelar`, `POST /2/nfse/substituir`, `POST /2/nfse/manifestar`, `GET /2/nfse/consulta/{identifier}` e `GET /2/nfse/status` permanecem compatíveis com o OpenAPI local validado.

Decisao de contrato: a NFS-e manual nova, apos retorno aprovado, e uma `NfseItem` com UUID/codigo/artefatos. Cancelamento, substituicao e manifestacao usam os mesmos contratos externos ja planejados/implementados para NFS-e local; a restricao local e preservar `NfseManualEmissionPreview` e `NfseManualEmission` como trilhas imutaveis de origem.

| Operacao futura sobre NFS-e manual | Endpoint | Contrato | Reaproveitamento | Decisao |
| --- | --- | --- | --- | --- |
| Cancelamento | `PUT /2/nfse/cancelar` | `{uuid, motivo}` | `NfseCancellation`, tentativa `nfse_cancellation`, webhook/reconciliacao por UUID | Priorizar Fase 3.8.1 |
| Substituicao | `POST /2/nfse/substituir` | `{ambiente, codigo_verificacao, motivo, rps}` | `NfseSubstitutionPreview` e `NfseSubstitution` | Adiar apos cancelamento; adaptar elegibilidade da origem manual |
| Manifestacao | `POST /2/nfse/manifestar` | `{ambiente, uuid|chave, manifestador, evento}` | `NfseManifestation` | Fase separada; exigir Padrao Nacional/capability |
| Consulta/reconciliacao | `GET /2/nfse/consulta/{identifier}` | identificador remoto | `NfseItem`/emissao manual, sem POST | Usar apenas de forma consultiva |

OpenAPI: nenhuma alteracao aplicada; o schema atual ja representa os endpoints e request bodies necessarios.

### Contrato implementado na Fase 3.8.1

O cancelamento da NFS-e manual nova usa o mesmo contrato remoto ja validado para NFS-e:

```json
{"uuid": "UUID-DA-NFSE", "motivo": 2}
```

Endpoint efetivo: `PUT /2/nfse/cancelar`. Nao sao enviados RPS, tomador, servico, valores, tributacao, payload da preview, payload de emissao, dados de substituicao ou dados de manifestacao. O OpenAPI validado permaneceu suficiente e nao foi alterado.

## Fase 3.9.0 - Reavaliacao API apos ciclo minimo da NFS-e manual

A Fase 3.8.1 foi validada no checkpoint `29f3f3a9`. A NFS-e manual nova agora possui ciclo minimo completo: preview imutavel, emissao por `POST /2/nfse/emissao` a partir do payload aprovado e cancelamento por `PUT /2/nfse/cancelar` com `{uuid, motivo}`. O cancelamento preserva o XML original e armazena XML de cancelamento separado em `NfseCancellation`.

Fonte oficial reconsultada em 2026-06-28: a documentacao Webmania NFS-e v3.1.1 continua listando `/2/nfse/emissao`, `/2/nfse/substituir`, `/2/nfse/manifestar`, `/2/nfse/consulta`, `/2/nfse/status` e `/2/nfse/cancelar`, com API v2 e Bearer Token.

Matriz API para o proximo bloco:

| Bloco | Endpoint/API | Contrato local disponivel | Risco API | Decisao |
| --- | --- | --- | --- | --- |
| Substituicao da NFS-e manual | `POST /2/nfse/substituir` | `NfseSubstitutionPreview` + `NfseSubstitution`; original manual possui `NfseItem`, UUID e codigo de verificacao quando autorizada | Medio: novo RPS e resposta da substituta | Priorizar extensao segura |
| Manifestacao da NFS-e manual | `POST /2/nfse/manifestar` | `NfseManifestation`; requer Padrao Nacional e papel fiscal | Medio/alto: papel tomador/intermediario | Adiar |
| NFS-e recebida/importada | `GET /2/nfse/consulta/{identifier}` e XML recebido | Sem dominio de importacao/identidade local | Alto | Planejar depois |
| NFS-e expandida | multiplos endpoints NFS-e | Legado/manual coexistem, sem generalizacao `FiscalDocument(nfse)` | Alto | Quebrar em subfases |
| CT-e/MDF-e/NFCom/DC-e | APIs v2 correspondentes | Sem dominio operacional local | Alto | Adiar |
| IBS/CBS, creditos/debitos, complementar tributaria | APIs v1 NF-e/NFC-e ja mapeadas | Fontes fiscais insuficientes para tipos restantes | Alto | Adiar |

Decisao API: a proxima fase funcional recomendada e substituicao da NFS-e manual, porque o endpoint e o schema ja estao representados no OpenAPI validado e a infraestrutura local de substituicao ja existe. Nenhuma correcao oficial nova foi confirmada; `api/webmania_fiscal_openapi_validated.json` permanece suficiente.

## Fase 3.9.1 - contrato implementado para substituicao da NFS-e manual

A Fase 3.9.0 foi validada no checkpoint `21d684e7`. A Fase 3.9.1 implementa a decisao aprovada como extensao segura do fluxo atual de substituicao NFS-e.

Contrato remoto efetivo:

```json
{
  "ambiente": 2,
  "codigo_verificacao": "CODIGO-ORIGINAL",
  "motivo": 1,
  "rps": {
    "numero": 5013,
    "serie": "MSUB",
    "servico": {},
    "tomador": {}
  }
}
```

Endpoint: `POST /2/nfse/substituir`.

O payload enviado e exatamente o `request_payload` aprovado em `NfseSubstitutionPreview`. Nao envia `uuid`, XML original, payload da emissao manual, payload de cancelamento, payload de manifestacao, dados livres da `NfseManualEmissionPreview` ou dados livres da `NfseManualEmission`.

OpenAPI: nenhuma alteracao aplicada; o schema validado ja cobre `/2/nfse/substituir` com `ambiente`, `codigo_verificacao`, `motivo` e `rps`.
