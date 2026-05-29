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
| 2.4 | Manifestacao e IBS/CBS | Registrar eventos avancados com historico auditavel e revalidacao da Reforma Tributaria. |
| 2.5 | Nota Fiscal de Credito e Debito | Planejar e implementar finalidades 5 e 6 da NF-e com `tipo_credito` e `tipo_debito`. |

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
