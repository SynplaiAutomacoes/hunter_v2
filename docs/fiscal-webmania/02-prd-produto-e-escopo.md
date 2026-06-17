# PRD produto e escopo fiscal

## Visao do produto

O modulo fiscal deve permitir que oficinas emitam, acompanhem e administrem documentos fiscais de forma segura, auditavel e compatível com a Webmania, sem limitar a emissao a uma unica origem operacional.

## Problema atual

O Hunter V2 ja emite NF-e e NFS-e, mas o fluxo atual e centrado em `WorkOrder`, usa idempotencia baseada em cache e nao possui dominio unificado para documentos, tentativas, eventos, vinculos entre documentos e origens futuras.

## Objetivo final

Suportar NF-e, NFC-e, NFS-e, CT-e, CT-e OS, MDF-e, NFCom e DC-e com operacoes de emissao, consulta, cancelamento, downloads, eventos e reconciliacao conforme disponibilidade oficial Webmania e relevancia do produto.

## Personas e permissoes

- Owner: administra conta, oficinas e configuracoes fiscais sensiveis.
- Diretor: administra fiscal da oficina quando autorizado.
- Gerente: executa operacoes fiscais dentro da oficina quando autorizado.
- Colaborador: visualiza ou opera apenas acoes explicitamente liberadas.
- Time tecnico: opera reconciliacao, logs e suporte sem expor segredos.

## Fluxos de emissao

- Emissao manual avulsa.
- Emissao por orcamento.
- Emissao por OS.
- Emissao por movimentacao financeira.
- Emissao a partir de cliente ou veiculo.
- Emissao vinculada a documento fiscal anterior.
- Emissao parcial por itens.
- Multiplos documentos por origem.

Regras:

- Uma OS pode gerar NF-e e NFS-e separadamente.
- Uma OS pode futuramente gerar multiplos documentos.
- Emissao fiscal nao pode depender obrigatoriamente de OS.
- Documentos devem estar vinculados a oficina correta.
- Acoes fiscais exigem permissoes especificas.

## Operacoes posteriores

Quando suportado pelo documento e pela Webmania:

- Consulta.
- Cancelamento.
- Download XML e PDF auxiliar.
- Carta de correcao.
- Inutilizacao.
- Devolucao, estorno, complemento, ajuste e substituicao.
- Manifestacao.
- Eventos IBS/CBS.
- Eventos de pagamento.
- Confirmacao/cancelamento de entrega.
- Encerramento.
- Inclusao de condutor.
- Consulta de capacidades municipais/provedor.
- Contingencia.
- Reconciliacao local/remota.

## Central fiscal

A central fiscal deve reunir:

- filtros por periodo, oficina, documento, status, origem, cliente, OS/orcamento, chave/UUID;
- KPIs de pendencias, processamento, rejeicoes, contingencia e MDF-e nao encerrado;
- acoes condicionais por status/permissao/capacidade;
- downloads individuais e em lote;
- acesso restrito a payloads/logs.

## Homologacao versus producao

O ambiente deve ser explicito na UI e nos payloads. Homologacao e producao nao podem compartilhar numeracao, credenciais ou status sem sinalizacao clara.

## Criterios de aceite funcionais

- Nenhum usuario acessa documento de outra oficina.
- Uma intencao fiscal nao gera duas chamadas remotas.
- Webhook e reconciliacao atualizam o mesmo documento local.
- Documento em estado remoto incerto bloqueia reenvio automatico.
- Downloads e payloads exigem permissao.
- OS com produtos e servicos pode gerar NF-e e NFS-e sem conflito.

## Escopo planejado da Fase 2 - NF-e/NFC-e

A Fase 2 expande somente a familia NF-e/NFC-e da API v1 Webmania. Ela nao deve incluir CT-e, MDF-e, NFS-e avancada, NFCom ou DC-e.

Operacoes de produto planejadas:

- CC-e: evento de correcao textual vinculado a uma NF-e autorizada, sem alterar valores fiscais.
- Devolucao/estorno: novo documento fiscal referenciando obrigatoriamente a nota anterior por chave, com suporte a devolucao parcial por produtos/quantidades e ao cenario de estorno tratado pelo endpoint de devolucao.
- Complementar: novo documento fiscal que complementa preco, quantidade, imposto ou informacao suportada pela Webmania, referenciando obrigatoriamente a nota original por chave ou UUID.
- Ajuste: novo documento fiscal para situacoes de ajuste fiscal. A documentacao oficial do endpoint `/1/nfe/ajuste/` nao exige chave/UUID da nota original; portanto vinculo com documento original e opcional e so deve existir quando houver relacao de negocio real ou exigencia futura confirmada.
- Nota Fiscal de Credito: NF-e emitida por `/1/nfe/emissao/` com `finalidade=5` e `tipo_credito`, planejada para subfase posterior.
- Nota Fiscal de Debito: NF-e emitida por `/1/nfe/emissao/` com `finalidade=6` e `tipo_debito`, planejada para subfase posterior.
- NFC-e: emissao modelo consumidor para venda direta, com configuracao propria por oficina e distincao visual de NF-e.
- Manifestacao do destinatario: evento vinculado a uma chave NF-e recebida ou documento monitorado.
- Eventos IBS/CBS: eventos vinculados a NF-e/NFC-e em contexto da Reforma Tributaria.
- Cancelamento de evento IBS/CBS: evento de reversao vinculado ao evento IBS/CBS original.
- Consulta, downloads e historico: devem operar sobre documentos e eventos sem reemitir.

Regras de produto:

- Eventos fiscais nao sao notas comuns e devem aparecer no historico/timeline do documento original.
- Documentos derivados sao notas novas. Devolucao/estorno e complementar devem manter vinculo auditavel obrigatorio com a nota original; ajuste pode existir sem nota original local ou externa quando a operacao fiscal nao exigir referencia.
- Acoes de Fase 2 devem partir de uma NF-e/NFC-e da oficina ativa ou de emissao manual autorizada quando a operacao permitir.
- Quando devolucao ou complemento referenciarem NF-e externa nao emitida pelo Hunter, o sistema deve permitir informar chave de acesso manual de 44 digitos, validar apenas o formato da chave, criar um `FiscalDocument` externo minimo como original referenciado, registrar que a origem nao foi emitida localmente e exigir confirmacao explicita do usuario autorizado. `GET /1/nfe/consulta/` nao deve ser tratado como validador garantido de NF-e de outro emissor; importacao/validacao por XML ou API fiscal especifica fica no backlog.
- Nenhuma operacao Fase 2 pode depender exclusivamente de `WorkOrder`.
- NFC-e deve exigir configuracao fiscal adequada de serie/modelo e ambiente antes de aparecer como acao disponivel.

## Subfases da Fase 2

| Subfase | Produto | Resultado esperado |
| ------- | ------- | ------------------ |
| 2.1 | CC-e | Emitir e consultar CC-e como evento vinculado a NF-e autorizada. |
| 2.2A | Devolucao e estorno | Emitir devolucao parcial/total ou estorno via `/1/nfe/devolucao/`, com vinculo obrigatorio a NF-e original ou externa. |
| 2.2B | Nota complementar | Emitir complementar de preco/quantidade, imposto ou documento de adicao/importacao, com vinculo obrigatorio a NF-e original ou externa. |
| 2.2C | Nota de ajuste | Emitir ajuste fiscal sem exigir documento original, com vinculo opcional quando houver relacao real. |
| 2.3 | NFC-e | Emitir NFC-e pelo endpoint v1 existente, com configuracao e permissoes proprias. |
| 2.4 | Conformidade IBS/CBS | Adequar classes fiscais, NF-e/NFC-e normais, documentos derivados e depois eventos IBS/CBS. |
| 2.5 | Nota Fiscal de Credito e Debito | Implementar finalidades 5 e 6 somente depois da base IBS/CBS validada. |

## Fora de escopo por fase

- Fase 0: qualquer mudanca funcional.
- Fase 1: novos modelos documentais alem de NF-e/NFS-e existentes.
- Fase 2/3: CT-e, MDF-e, NFCom e DC-e.
- Fase 6: NFCom sem feature flag, permissao e habilitacao administrativa por oficina.
- Fase 7: DC-e sem feature flag, permissao e habilitacao administrativa por oficina.

## Fase 2.2B.0 - PRD Funcional da Nota Fiscal Complementar

Objetivo: planejar a Nota Fiscal Complementar da familia NF-e sem implementar codigo funcional. A operacao futura usara `POST /1/nfe/complementar/` e criara uma NF-e derivada para acrescentar dados, valores ou impostos nao informados corretamente na nota original.

Subtipos obrigatorios:

| Subtipo | Uso no Hunter V2 | Regra de produto |
| ------- | ---------------- | ---------------- |
| `complementary_price_quantity` | Complemento de preco e/ou quantidade de itens da NF-e original | Primeira entrega recomendada da 2.2B para NF-e local com itens fiscais conhecidos. |
| `complementary_tax` | Complemento de ICMS, ICMS-ST, IPI, ISSQN, IBS ou CBS | Deve ter formulario separado de produto; exige permissao fiscal mais restrita e payload auditavel. |
| `complementary_import_addition` | Documento de adicao/importacao | Baixa prioridade para oficina; planejar, mas adiar salvo aprovacao explicita. |

Status da Fase 2.2B.1: validada somente para `complementary_price_quantity` de NF-e original local. NF-e externa minima continua bloqueada para preco/quantidade; complemento tributario, IBS/CBS e adicao/importacao continuam fora de escopo ate nova autorizacao.

Fluxo funcional futuro:

1. Usuario abre detalhe da NF-e original local ou informa chave de NF-e externa.
2. Sistema valida oficina, permissao e elegibilidade.
3. Usuario seleciona subtipo da complementar.
4. Sistema cria documento derivado local em estado inicial e link `complements`.
5. Sistema congela payload sanitizado e cria tentativa idempotente.
6. Gateway envia uma unica chamada `POST /1/nfe/complementar/`.
7. Retorno, webhook e reconciliacao atualizam somente o documento complementar.

NF-e externa:

- Chave manual de 44 digitos permitida como referencia minima.
- `/1/nfe/consulta/` nao e garantia de validacao para nota de outro emissor.
- `complementary_price_quantity` deve ficar bloqueada sem XML/importacao validada dos itens fiscais originais.
- `complementary_tax` externa pode ser planejada com entrada manual auditada, confirmacao forte e permissao restrita.
- `complementary_import_addition` externa deve ser adiada ate existir importacao/validacao adequada.

Aceite funcional da fase futura:

- A NF-e original nao muda status quando uma complementar e emitida, reconciliada ou atualizada por webhook.
- A complementar fica vinculada por `FiscalDocumentLink(role="complements")`.
- Complemento de produto e complemento tributario nao compartilham o mesmo formulario nem a mesma regra de idempotencia operacional.
- Downloads XML/DANFE da complementar exigem oficina e permissao.

## Politica beta NFCom e DC-e

NFCom e DC-e sao tratadas como APIs beta no planejamento do Hunter V2. Ambas so podem ser implementadas futuramente atras de:

- feature flag global;
- habilitacao administrativa por oficina;
- permissao especifica;
- sinalizacao visual de beta;
- testes isolados;
- capacidade de desativacao sem afetar os demais modelos fiscais.

## Fase 2.2C - Nota Fiscal de Ajuste validada

Objetivo implementado: emitir Nota Fiscal de Ajuste por `POST /1/nfe/ajuste/` como documento fiscal proprio, sem exigir documento original.

Regras funcionais validadas:

- Ajuste cria `FiscalDocument(document_type="nfe", purpose="adjustment", origin="manual")` antes da chamada remota.
- `FiscalDocumentLink(role="adjusts")` e opcional e usado somente quando ha documento relacionado no contexto.
- A NF-e relacionada opcional nao muda status, chave, XML ou DANFE por causa do ajuste.
- Regime tributario usa `WebmaniaCompany.regime_tributario`; Lucro Real/Normal e Lucro Presumido permitem emissao; Simples Nacional, MEI e regime ausente/desconhecido bloqueiam antes do gateway.
- O payload remoto fica limitado a campos de ajuste: operacao, natureza, CFOP, ICMS, ICMS-ST opcional, ambiente, cliente, situacao tributaria, informacoes opcionais e notificacao.
- Produtos, pedido, complemento tributario separado, IBS/CBS, agropecuario, importacao e adicao permanecem fora de escopo.
- Cenarios de estorno SC/ES tratados por devolucao/estorno nao devem usar `/1/nfe/ajuste/`; a Fase 2.2C implementa aviso e confirmacao operacional, mantendo deteccao automatica como backlog quando houver dados suficientes.

Aceite funcional validado:

- Permissao `issue_nfe_adjustment` e exigida antes do gateway.
- Idempotencia e por documento de ajuste persistido e tentativa `operation_type="adjustment"`.
- Timeout apos envio marca `uncertain` e bloqueia reenvio automatico.
- Webhook e reconciliacao atualizam somente o ajuste.
- Downloads XML/DANFE exigem oficina e permissao.

## Fase 2.3.0 - PRD tecnico documental da NFC-e

Objetivo: planejar NFC-e sem implementar codigo funcional. A implementacao futura deve usar a familia NF-e/NFC-e v1 da Webmania, mantendo isolamento por oficina e sem reutilizar fluxos NF-e de forma que confunda modelo, numeracao, permissao ou downloads.

Escopo futuro recomendado para a Fase 2.3:

- Emissao NFC-e normal por `POST /1/nfe/emissao/` com `modelo=2`.
- Consulta por `GET /1/nfe/consulta/`.
- Cancelamento por `PUT /1/nfe/cancelar/`.
- Inutilizacao de numeracao NFC-e por `PUT /1/nfe/inutilizar/` com `modelo=2`, se aprovada na subfase.
- Downloads XML e DANFE NFC-e por URLs retornadas.
- Reconciliacao e webhook para `modelo=nfce`.
- UI minima para emissao manual/operacional de venda consumidor, sem criar central fiscal completa.

Fora de escopo da Fase 2.3 inicial:

- NFC-e offline/contingencia offline com fila local.
- Cancelamento por substituicao, salvo confirmacao oficial e aprovacao especifica.
- Integracao PDV completa.
- TEF, SAT/MFE ou impressao fiscal avancada.
- Credito/debito, manifestacao, IBS/CBS e complementar tributaria.

Configuracao:

- Reutilizar `WebmaniaCompany.nfce_enabled`, `nfce_serie`, `nfce_numero`, `nfce_id_csc`, `nfce_codigo_csc`, `nfce_numero_dev`, `nfce_id_csc_dev` e `nfce_codigo_csc_dev`.
- `nfce_enabled=False` bloqueia emissao e oculta acao operacional mesmo quando serie/CSC estiverem preenchidos.
- Em producao, exigir serie, proximo numero e CSC de producao.
- Em homologacao, exigir serie, numero de homologacao e CSC de homologacao quando o ambiente de teste estiver habilitado.
- Nao criar configuracao paralela sem provar lacuna real no codigo atual.

Origem de emissao:

- Primeira entrega recomendada: emissao manual avulsa e emissao a partir de itens/produtos da OS com pagamento simples.
- NFC-e nao deve depender obrigatoriamente de OS.
- Uma mesma origem operacional pode futuramente gerar NF-e e NFC-e, mas a UI deve evitar dupla emissao acidental e exigir escolha explicita do modelo.

Aceite funcional futuro:

- Oficina sem configuracao NFC-e completa nao ve acao de emissao e nao chama Webmania.
- NFC-e usa `FiscalDocument(document_type="nfce", purpose="normal")`.
- Idempotencia cria documento local antes do gateway.
- Timeout marca `uncertain` e bloqueia reenvio automatico.
- Webhook/reconciliacao atualizam somente o documento NFC-e.
- Downloads exigem oficina ativa e permissao especifica.
## Atualizacao Fase 2.3.2 - Cancelamento padrao NFC-e

- Implementado somente cancelamento padrao de NFC-e manual simples emitida pelo Hunter.
- A operacao usa `PUT /1/nfe/cancelar/` com `chave` ou `uuid` e `motivo` entre 15 e 255 caracteres.
- Cancelamento por substituicao permanece fora de escopo: o payload nao envia `nfce_referenciada`.
- A NFC-e original muda para `cancelado` somente apos resposta, webhook ou reconciliacao valida de cancelamento.
- O cancelamento e registrado como evento fiscal, com XML de cancelamento protegido por permissao e oficina ativa.
- Permanecem fora de escopo: contingencia/offline, inutilizacao NFC-e, PDV/TEF/SAT/MFE, IBS/CBS, manifestacao, credito/debito e complementar tributaria.

## Atualizacao Fase 2.3.3 - Inutilizacao de Numeracao NFC-e

A Fase 2.3.3 implementa inutilizacao manual de numeracao NFC-e para comunicar quebra de sequencia por `PUT /1/nfe/inutilizar/` com `modelo=2`.

Escopo funcional:
- usuario autorizado informa ambiente, serie, numero unico ou intervalo e motivo;
- sistema valida configuracao NFC-e da oficina, formato de faixa e conflitos locais;
- sistema cria registro proprio de inutilizacao antes da chamada remota;
- tentativa idempotente impede dupla transmissao por retry/concorrencia;
- `uncertain` reserva a faixa ate decisao administrativa segura;
- historico/listagem de inutilizacoes fica separado das NFC-e emitidas.

Fora de escopo:
- inutilizacao funcional de NF-e (`modelo=1`);
- cancelamento por substituicao;
- contingencia/offline;
- validacao global de uso da faixa fora do Hunter;
- webhook/reconciliacao remota de inutilizacao sem contrato oficial confirmado.

## Fase 2.5.0 - Planejamento tecnico da Nota Fiscal de Credito e Nota Fiscal de Debito

Status: planejamento documental em andamento apos validacao da Fase 2.3.3 no checkpoint `08b9bf2e`. O ciclo simples NFC-e fica encerrado neste ciclo com emissao manual simples, cancelamento padrao e inutilizacao de numeracao.

Objetivo: planejar NF-e de credito e NF-e de debito sem implementar codigo funcional. Ambas usam `POST /1/nfe/emissao/`, mas nao devem ser tratadas como variacao visual de NF-e normal.

Escopo planejado:

- Nota Fiscal de Credito: `FiscalDocument(document_type="nfe", purpose="credit")`, `finalidade=5`, `tipo_credito` obrigatorio.
- Nota Fiscal de Debito: `FiscalDocument(document_type="nfe", purpose="debit")`, `finalidade=6`, `tipo_debito` obrigatorio.
- Persistir o tipo remoto em campo planejado `fiscal_purpose_type` ou equivalente, mantendo tambem o payload sanitizado bruto para auditoria.
- Operacao manual administrativa/fiscal, nao vinculada por padrao a OS, orcamento ou NFC-e.
- `FiscalDocumentLink` opcional/condicional, nunca obrigatorio sem exigencia oficial ou regra de negocio aprovada.

Decisao de produto:

- Valor para oficina automotiva: baixo a medio, majoritariamente contabil/fiscal e administrativo.
- Risco fiscal: alto, pois a documentacao e a central de ajuda Webmania relacionam finalidades 5/6 a IBS/CBS/Reforma Tributaria.
- Recomendacao: nao implementar codigo funcional de credito/debito imediatamente. A implementacao deve ficar atras de habilitacao administrativa por oficina e feature flag, e so avancar apos fase tributaria IBS/CBS ou aprovacao explicita de um subconjunto oficialmente seguro.

Fora de escopo ate nova aprovacao:

- qualquer transmissao real de credito/debito;
- IBS/CBS funcional;
- manifestacao;
- complementar tributaria;
- credito/debito sem feature flag/habilitacao administrativa;
- vinculo obrigatorio a documento anterior sem evidencia oficial por tipo.

## Fase 2.4.0 - Auditoria e conformidade IBS/CBS NF-e/NFC-e

Motivo da prioridade: a documentacao oficial Webmania NF-e/NFC-e descreve `produtos[].impostos.ibs_cbs` e informa obrigatoriedade em producao para NF-e/NFC-e com data de emissao maior ou igual a `05/01/2026`. A central de ajuda Webmania tambem confirma que NF-e com `finalidade=5` ou `finalidade=6` deve se relacionar somente a IBS/CBS; enviar ICMS, ISSQN, IPI, II, PIS, COFINS e correlatos nessas finalidades gera rejeicao 1001.

Diagnostico dos fluxos atuais:

| Fluxo atual | Monta IBS/CBS hoje? | Fonte dos dados | Risco atual | Correcao necessaria | Prioridade |
| ----------- | ------------------: | --------------- | ----------- | ------------------- | ---------- |
| NF-e legada | Nao diretamente | Produtos usam `classe_imposto`; classes NF-e locais nao persistem `ibs_cbs` | Rejeicao ou emissao incompleta em producao quando IBS/CBS for obrigatorio | Modelar IBS/CBS em classe fiscal/produto e bloquear emissao sem configuracao minima | Critica |
| NFC-e manual simples | Nao | Produtos usam `classe_imposto`; payload atual nao envia `impostos.ibs_cbs` | NFC-e manual simples pode ficar fiscalmente incompatível em producao | Atualizar base fiscal e emissao normal NFC-e com IBS/CBS | Critica |
| Devolucao/estorno | Nao explicitamente | Chave original, sequenciais e quantidades | Tributacao derivada pode divergir sem regra documentada | Revalidar payload de devolucao/estorno na Fase 2.4C | Alta |
| Complementar preco/quantidade | Nao; filtros removem IBS/CBS | Produto complementar derivado do item original, sem `impostos` | Complementar de produto pode exigir IBS/CBS e hoje o payload bloqueia campos | Revalidar complementar de preco/quantidade na Fase 2.4C | Alta |
| Ajuste | Nao | Payload de ajuste usa ICMS/ICMS-ST e remove IBS/CBS | Regra de ajuste precisa ser confirmada para a transicao | Documentar aplicabilidade e bloqueio/ajuste de payload na Fase 2.4C | Alta |
| Classes fiscais NF-e | Nao | `TaxClassNfe` guarda ICMS/IPI/PIS/COFINS | Fonte atual de tributacao NF-e/NFC-e nao tem IBS/CBS local | Fase 2.4A deve ser a primeira implementacao funcional | Critica |
| Credito/debito | Nao implementado | Planejamento Fase 2.5.0 | Nao pode ser implementado com tributos antigos | Manter bloqueado ate 2.4E | Critica |

Resultado implementado na Fase 2.4A+B:

- `TaxClassNfe` passou a armazenar configuracao IBS/CBS auditavel e sincronizar `ibs_cbs` na classe fiscal Webmania.
- NF-e normal e NFC-e manual simples continuam usando `classe_imposto`; a emissao e bloqueada antes do gateway quando a classe local nao estiver IBS/CBS-ready.
- Homologacao tambem exige configuracao valida por padrao; nenhum bypass silencioso foi criado.
- Derivados ja implementados permanecem pendentes da Fase 2.4C.

Regras de bloqueio seguro:

- Bloquear NF-e/NFC-e em producao quando a regra vigente exigir IBS/CBS e a classe fiscal/produto nao possuir configuracao minima validada.
- Nao calcular `situacao_tributaria`, `classificacao_tributaria` ou valores IBS/CBS automaticamente sem fonte fiscal confiavel.
- Homologacao deve usar configuracao IBS/CBS valida ou modo explicitamente controlado e documentado; nao mascarar ausencia de configuracao como emissao valida.
- Fluxos de credito/debito, eventos IBS/CBS e complementar tributaria permanecem bloqueados ate a base 2.4A/2.4B estar validada.

Subfases planejadas da Fase 2.4:

| Subfase | Objetivo | Resultado esperado |
| ------- | -------- | ------------------ |
| 2.4A | Base IBS/CBS em classes fiscais e produtos | Modelagem local, UI/configuracao fiscal, serializers e bloqueio seguro quando ausente. |
| 2.4B | Emissao NF-e/NFC-e normal conforme IBS/CBS | Payload normal com `produtos[].impostos.ibs_cbs` ou classe fiscal validada, coexistindo com tributos antigos quando aplicavel. |
| 2.4C | Documentos derivados ja implementados | Revisar devolucao/estorno, complementar preco/quantidade e ajuste sem presumir payload unico. |
| 2.4D | Eventos IBS/CBS | Planejar/implementar eventos e cancelamentos IBS/CBS somente depois da base de emissao. |
| 2.4E | Credito e debito | Implementar finalidades 5/6 apenas com IBS/CBS validado, reaproveitando Fase 2.5.0. |

## Fase 2.4C.0 - Planejamento tecnico dos derivados com IBS/CBS

Status: em planejamento documental apos validacao da Fase 2.4A+B no checkpoint `9eb217f2b5de2f834eb137305de1216d47e4b36e`. NF-e normal e NFC-e manual simples estao adequadas ou bloqueadas com seguranca por classe fiscal IBS/CBS-ready; documentos derivados continuam pendentes de regra propria.

Escopo desta fase documental:

- Devolucao e estorno emitidos por `/1/nfe/devolucao/`.
- Nota complementar de preco/quantidade emitida por `/1/nfe/complementar/`.
- Nota de ajuste emitida por `/1/nfe/ajuste/`.
- Decisoes de snapshot tributario original, NF-e externa e bloqueios seguros antes do gateway.

Fora de escopo funcional e documental de implementacao:

- Eventos IBS/CBS por `/1/nfe/evento-ibs-cbs/`.
- Nota Fiscal de Credito/Debito.
- Complementar tributaria ampla, IBS/CBS de complemento tributario, adicao/importacao.
- NFS-e, CT-e, MDF-e, NFCom, DC-e e demais familias.

### Matriz de decisao 2.4C.0

| Documento derivado | Endpoint | IBS/CBS deve ser tratado como | Fonte preferencial | NF-e externa minima | Decisao recomendada |
| ------------------ | -------- | ----------------------------- | ------------------ | ------------------- | ------------------- |
| Devolucao parcial/total | `POST /1/nfe/devolucao/` | Tributacao derivada da nota original e dos itens devolvidos; nao e evento IBS/CBS | Snapshot fiscal do item original local; classe atual apenas com confirmacao fiscal | Bloquear parcial; permitir avaliar total somente com confirmacao forte e sem afirmar validacao externa | Implementar primeiro na 2.4C.1, preservando sequenciais fiscais e saldo |
| Estorno | `POST /1/nfe/devolucao/` | Fluxo proprio de estorno, nao devolucao parcial comum | Dados do documento original local e regras de estorno ja aprovadas | Bloquear quando nao houver dados suficientes para regra fiscal segura | Implementar junto da devolucao na 2.4C.1, sem duplicar ajuste |
| Complementar preco/quantidade | `POST /1/nfe/complementar/` | IBS/CBS aplicavel ao acrescimo de preco/quantidade, sem abrir complementar tributaria | Snapshot do item original local e valor/quantidade complementar | Bloquear sem XML/importacao validada dos itens | Implementar na 2.4C.2 apos devolucao/estorno |
| Ajuste | `POST /1/nfe/ajuste/` | Reavaliacao fiscal separada; endpoint atual nao usa `produtos[].impostos.ibs_cbs` no fluxo implementado | `WebmaniaCompany.regime_tributario` e payload de ajuste validado; eventual regra IBS/CBS depende de contrato oficial | Nao aplicavel por padrao, pois ajuste pode ser avulso | Planejar na 2.4C.3 com bloqueio seguro se a operacao exigir Reforma Tributaria |

Decisao 2.4C.3: Nota Fiscal de Ajuste permanece uma operacao avulsa de ICMS/ICMS-ST, sem produtos e sem `produtos[].impostos.ibs_cbs`. O produto deve bloquear uso de ajuste como credito/debito, evento IBS/CBS, complementar tributaria ou estorno. Estorno segue em devolucao/estorno; credito/debito e eventos IBS/CBS seguem bloqueados ate fases proprias.

### Snapshot original versus classe atual

Decisao: nao reutilizar cegamente a classe fiscal atual do produto para documentos derivados. Uma devolucao ou complementar deve refletir a tributacao da NF-e original, nao necessariamente a configuracao vigente no dia do derivado.

Ordem recomendada de fonte:

1. Snapshot fiscal persistido no `FiscalDocument.request_payload_sanitized`, payload legado do `NfeItem` ou resposta remota da nota original.
2. Classe fiscal local `TaxClassNfe` IBS/CBS-ready vinculada ao item original, somente como apoio quando o snapshot nao tiver o bloco e o usuario fiscal confirmar a equivalencia.
3. Bloqueio antes do gateway quando nenhuma fonte auditavel existir.

### NF-e externa

Para NF-e externa minima criada apenas por chave de 44 digitos, o Hunter nao conhece itens, sequenciais fiscais nem tributacao original. Portanto:

- devolucao parcial com IBS/CBS permanece bloqueada ate importacao/validacao por XML ou fonte fiscal equivalente;
- complementar preco/quantidade permanece bloqueada;
- estorno ou devolucao total so podem avancar em fase funcional se houver confirmacao forte, permissao restrita e regra oficial que nao exija detalhe de itens/IBS-CBS local;
- `/1/nfe/consulta/` nao deve ser usado como garantia de validade de NF-e de outro emissor.

### Observacao sobre datas oficiais

Os PRDs registram a obrigatoriedade aprovada pelo usuario para NF-e/NFC-e de producao com data de emissao maior ou igual a `05/01/2026`. A consulta atual da pagina oficial REST NF-e/NFC-e exibiu cronograma textual com producao obrigatoria a partir de `01/01/2026`. Antes de qualquer codigo da 2.4C, a data aplicavel deve ser revalidada e, em caso de divergencia, deve prevalecer o bloqueio mais conservador ou decisao fiscal explicita.

## Fase 2.4C.1 - Devolucao e estorno com IBS/CBS

Resultado implementado: devolucao total, devolucao parcial e estorno por `/1/nfe/devolucao/` passam a usar snapshot IBS/CBS da NF-e original local quando o documento original esta em producao e a regra conservadora de obrigatoriedade esta ativa desde `01/01/2026`.

Regras implementadas:

- Snapshot fiscal original e lido de `FiscalDocument.request_payload`, `FiscalDocument.response_payload`, `NfeItem.raw_payload` e `NfeItem.log_payload`.
- Para devolucao parcial, o payload preserva os sequenciais fiscais selecionados e associa `impostos.ibs_cbs` ao item correspondente.
- Para devolucao total e estorno em producao, o payload usa todos os itens do snapshot original local com suas quantidades originais e IBS/CBS validado.
- Quando snapshot IBS/CBS estiver ausente ou incompleto em producao, a operacao bloqueia antes do gateway.
- `TaxClassNfe` atual nao e consultada como fallback automatico; divergencia entre classe atual e snapshot original nao altera o payload derivado.
- NF-e externa minima continua bloqueada para devolucao parcial sem XML/importacao validada e nao presume IBS/CBS.
- Complementar preco/quantidade com IBS/CBS, ajuste com IBS/CBS, eventos IBS/CBS e credito/debito permanecem fora de escopo.

Nao houve migration. A estrategia usa payloads/snapshots ja persistidos e helpers de validacao IBS/CBS existentes.

## Fase 2.4D.0 - Planejamento tecnico dos Eventos IBS/CBS

Status: documentada em 2026-06-02, apos validacao da Fase 2.4C.3 no checkpoint `dd740d1fccbf692b95720a0b0de36fee1f294827`. Nenhum codigo funcional esta autorizado nesta etapa.

Objetivo: planejar eventos IBS/CBS vinculados a NF-e/NFC-e por `POST /1/nfe/evento-ibs-cbs/`, mantendo-os separados de emissao normal, derivados, ajuste, credito/debito e complementar tributaria.

Escopo futuro planejado:

- Registrar eventos oficiais IBS/CBS sobre `FiscalDocument(document_type="nfe"|"nfce")` ja emitido e elegivel.
- Modelar eventos como `FiscalDocumentEvent(event_type="ibs_cbs")`, nao como novo `FiscalDocument`.
- Planejar cancelamento de evento IBS/CBS por `PUT /1/nfe/evento-ibs-cbs/cancelar/` em subfase propria.
- Preservar relacionamento com credito/debito sem liberar `finalidade=5/6`: evento `211128` depende de nota de credito, mas nao autoriza implementar credito/debito nesta fase.

Fora de escopo funcional:

- Qualquer codigo de service, model, migration, view, form, template ou teste.
- Eventos IBS/CBS sem documento base local elegivel.
- Nota Fiscal de Credito/Debito.
- Complementar tributaria.
- Alterar `/1/nfe/ajuste/`; ajuste permanece sem IBS/CBS por ausencia de contrato seguro nesse endpoint.

### Elegibilidade planejada por documento

| Documento Hunter | Pode receber evento IBS/CBS? | Condicao minima | Observacao |
| ---------------- | ---------------------------- | --------------- | ---------- |
| NF-e normal local | Sim | `FiscalDocument(document_type="nfe")` autorizado, com chave, oficina correta e payload base IBS/CBS conforme 2.4A+B | Principal alvo da primeira subfase funcional. |
| NFC-e normal local | Sim, quando o evento oficial aceitar NF-e/NFC-e | `FiscalDocument(document_type="nfce")` autorizado, com chave e oficina correta | Exigir validacao por `cod_evento` antes de expor na UI. |
| Devolucao/estorno | Pendente | Documento derivado autorizado e regra oficial do evento confirmada | Nao presumir que todos os eventos se aplicam a derivados. |
| Complementar preco/quantidade | Pendente | Documento complementar autorizado e regra oficial confirmada | Nao misturar com complementar tributaria. |
| Ajuste | Nao nesta fase | `/1/nfe/ajuste/` permanece separado e sem IBS/CBS | Eventos nao devem ser enviados pelo service de ajuste. |
| Credito/debito | Bloqueado | Depende de Fase 2.4E/2.5 funcional | Evento `211128` sera tratado somente apos credito/debito aprovado. |

Recomendacao de primeira subfase funcional: implementar somente evento `112110` para NF-e/NFC-e normal local autorizada, porque a documentacao oficial informa que ele nao possui campos especificos alem de `chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao`. Eventos com itens, valores, controle de estoque, `dfe_referenciado` ou relacao com nota de credito devem vir depois.

Resultado da Fase 2.4D.1: o Hunter passou a suportar somente o evento IBS/CBS `112110`, modelado como `FiscalDocumentEvent(event_type="ibs_cbs")` vinculado ao `FiscalDocument` base. O evento nao cria novo documento fiscal, nao altera o status da NF-e/NFC-e original e envia apenas o envelope oficial confirmado (`chave`, `ambiente`, `cod_evento`, `evento` e `url_notificacao` quando aplicavel). Cancelamento de evento IBS/CBS, demais codigos, credito/debito, complementar tributaria, NFS-e e CT-e permanecem fora do escopo.

Resultado da Fase 2.4D.2: o Hunter passou a suportar somente cancelamento do evento IBS/CBS `112110` ja autorizado, por `PUT /1/nfe/evento-ibs-cbs/cancelar/`. O cancelamento e registrado como `FiscalDocumentEvent(event_type="ibs_cbs_cancellation")` vinculado ao evento original, usa apenas UUID remoto do evento, ambiente e URL de notificacao quando aplicavel, e nao altera o status fiscal da NF-e/NFC-e base. Demais cancelamentos de eventos IBS/CBS, novos codigos de evento, credito/debito, complementar tributaria, NFS-e e CT-e permanecem fora do escopo.

## Fase 2.4D.3.0 - Priorizacao dos demais Eventos IBS/CBS

Status: planejamento documental apos validacao da Fase 2.4D.2 no checkpoint `dab3d559238954878259c1ad57cd503424f93d47`.

Decisao de produto: a proxima subfase funcional recomendada e implementar somente o evento `112150`, de atualizacao da data de previsao de entrega. Esse evento e o menor incremento util porque possui payload especifico estreito (`data_previsao_entrega`), nao depende de credito/debito, nao exige papel destinatario e nao exige `itens[]`.

Resultado da Fase 2.4D.3: o Hunter passou a suportar somente o evento IBS/CBS `112150`, de atualizacao da data de previsao de entrega, como `FiscalDocumentEvent(event_type="ibs_cbs", event_code="112150")` vinculado a uma NF-e normal local autorizada. A revalidacao oficial confirmou que o payload usa `data_previsao_entrega` no topo do envelope junto de `chave`, `ambiente`, `cod_evento` e `evento` numerico; nao foi enviado `ibs_cbs`, `itens`, `produtos`, credito/debito ou cancelamento. NFC-e, devolucao, complementar, ajuste, credito/debito, cancelamento do `112150`, demais eventos IBS/CBS, NFS-e e CT-e permanecem fora do escopo.

Resultado da Fase 2.4D.4: o Hunter passou a suportar somente o cancelamento do evento IBS/CBS `112150` autorizado, por `PUT /1/nfe/evento-ibs-cbs/cancelar/`. O cancelamento e registrado como `FiscalDocumentEvent(event_type="ibs_cbs_cancellation", event_code="112150")` vinculado ao evento original, usa apenas UUID remoto do evento, ambiente e URL de notificacao quando aplicavel, e nao altera o status fiscal da NF-e base. Cancelamento generico, demais eventos IBS/CBS, credito/debito, complementar tributaria, NFS-e e CT-e permanecem fora do escopo.

Eventos adiados:

- `112120`, `112130` e `112140`: exigem itens fiscais, valores IBS/CBS, controle operacional/estoque/transporte ou pagamento antecipado.
- `211128`: depende de nota de credito/debito e apuracao assistida.
- `211110`, `211120`, `211124`, `211130`, `211140` e `211150`: dependem de papel destinatario, documento de aquisicao, apuracao externa, estoque ou contabilidade.
- Cancelamento dos demais eventos IBS/CBS: nao generalizar sem subfase propria e testes especificos.
