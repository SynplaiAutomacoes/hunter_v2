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
| DC-e         | Emissao beta              | POST            | `/2/dce/emissao`                      | Bearer v2    | remetente/destinatario/itens/transporte     | uuid, chave, status             | XML/DACE          | Sim     | 7    |
| DC-e         | Consulta beta             | GET             | `/2/dce/consulta/{identifier}`        | Bearer v2    | uuid/chave                                  | status, URLs                    | XML/DACE          | Nao     | 7    |
| DC-e         | Cancelamento beta         | PUT             | `/2/dce/cancelar`                     | Bearer v2    | uuid/chave, motivo                          | status/xml_cancelamento         | XML               | Sim     | 7    |

## Uso no Hunter V2

- NF-e: produtos e pecas de OS, venda avulsa, NFC-e futura para consumidor.
- NFS-e: servicos de OS, servico avulso, substituicao quando municipio suportar.
- CT-e/CT-e OS: uso medio, manual ou vinculado a documentos de transporte.
- MDF-e: manifesto de documentos, pendencia operacional quando autorizado e nao encerrado.
- NFCom: beta, uso manual de baixa prioridade, isolada por feature flag e habilitacao administrativa por oficina.
- DC-e: beta, isolada por feature flag e habilitacao administrativa por oficina.

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
- NF-e externa: quando devolucao ou complemento referenciarem chave nao emitida pelo Hunter, criar projecao externa minima antes da emissao derivada, marcar `origin=external`, preservar chave informada e exigir confirmacao do usuario. A consulta padrao `/1/nfe/consulta/` pode ser usada para notas Webmania/Hunter da propria oficina, mas nao e garantia de validacao de NF-e de outro emissor.
- Para NFC-e, cancelamento por substituicao deve ser tratado como variacao de cancelamento somente se a documentacao vigente e a configuracao da oficina confirmarem suporte; ate la, registrar como pendencia de validacao.
- A matriz OpenAPI validada ja contem os endpoints da Fase 2.0; nenhuma correcao no JSON foi necessaria nesta etapa documental.

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
| NFCom                  | Marcada beta                           | Docs indicam versao 0.1.2 beta                    | Sinalizar risco e baixa prioridade       |
| DC-e downloads         | Nao endpoints dedicados no guia rapido | Payload retorna `xml`, `xml_cancelamento`, `dace` | Tratar downloads por URL retornada       |

## Divergencias oficiais registradas na Fase 0.1

| Operacao | Documentacao/listagem | Exemplo oficial | Decisao de modelagem |
| -------- | --------------------- | --------------- | -------------------- |
| Consulta NFS-e | `/2/nfse/consulta` | `GET /2/nfse/consulta/{uuid}` | O OpenAPI validado modela `/2/nfse/consulta/{identifier}` porque e a forma operacional demonstrada no exemplo oficial. |
| Consulta MDF-e | `/2/mdfe/consulta` | `GET /2/mdfe/consulta/{uuid-ou-chave}` | O OpenAPI validado modela `/2/mdfe/consulta/{identifier}` porque e a forma operacional demonstrada no exemplo oficial. |
| CT-e simplificado | CT-e simplificado listado | CT-e OS simplificado indicado como nao disponivel/condicional | O Hunter nao deve habilitar CT-e OS simplificado sem nova confirmacao oficial. |
| NFCom | Documentacao beta | API v0.1.2 beta | Implementar somente com feature flag e habilitacao administrativa por oficina. |
| DC-e | Documentacao beta | API beta | Implementar somente com feature flag e habilitacao administrativa por oficina. |

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
