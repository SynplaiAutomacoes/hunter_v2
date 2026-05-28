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
