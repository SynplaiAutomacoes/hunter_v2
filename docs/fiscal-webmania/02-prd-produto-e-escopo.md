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

## Politica beta NFCom e DC-e

NFCom e DC-e sao tratadas como APIs beta no planejamento do Hunter V2. Ambas so podem ser implementadas futuramente atras de:

- feature flag global;
- habilitacao administrativa por oficina;
- permissao especifica;
- sinalizacao visual de beta;
- testes isolados;
- capacidade de desativacao sem afetar os demais modelos fiscais.
