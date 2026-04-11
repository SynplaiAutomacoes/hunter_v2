# Visao geral do produto

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Proximo: Arquitetura e apps](02-arquitetura-e-apps.md)

## O que e o Hunter V2

O Hunter V2 e um sistema interno de gestao para oficinas automotivas. Ele nao foi modelado como um simples CRUD de clientes ou como um emissor fiscal isolado. O produto organiza a operacao ponta a ponta, da entrada do cliente ate a entrega do servico com reflexo comercial, operacional, financeiro e fiscal.

Em termos praticos, o sistema conecta:

- conta e oficinas
- equipe e papeis
- cliente e veiculo
- triagem e diagnostico
- checklist tecnico
- catalogo e precificacao
- aprovacao e assinatura
- ordem de servico
- estoque
- financeiro gerencial
- emissao de documentos fiscais

## Perfil de uso

Os principais atores do sistema sao:

- dono da conta, que administra a conta e as oficinas
- gestores/diretores de oficina, com escopo operacional e financeiro
- colaboradores da oficina, envolvidos em atendimento, execucao e acompanhamento
- time tecnico do produto, que evolui, integra e opera a plataforma

## O que e central no dominio

Estas entidades aparecem com bastante frequencia na leitura do codigo e na modelagem funcional:

| Entidade | Papel no dominio |
| --- | --- |
| `Account` | unidade raiz de tenancy |
| `User` | usuario autenticado do sistema |
| `Workshop` | unidade operacional principal |
| `Customer` | cliente final ou empresa contratante |
| veiculo | ativo atendido no fluxo de manutencao |
| `Budget` | fluxo central de triagem, itens, precificacao e aprovacao |
| `WorkOrder` | execucao do trabalho aprovado |
| `StockProduct` | saldo fisico/logico do estoque |
| `FinancialMovement` | registro financeiro de entrada/saida |
| requisicoes fiscais | emissao, cancelamento e download de documentos |

## Jornada principal do sistema

### 1. Conta, usuario e oficina

Tudo comeca em uma `Account`. O usuario pertence a uma conta e opera em uma ou mais oficinas. A oficina ativa na sessao e o contexto que escopa boa parte das telas e operacoes.

### 2. Entrada do atendimento

O fluxo pode comecar com um agendamento, com um cliente/veiculo ja existente ou com um novo cadastro iniciado durante o atendimento.

### 3. Orcamento tecnico-comercial

O modulo de orcamento e o centro do produto. Ele organiza a jornada de atendimento, diagnostico e montagem de proposta. Nao se trata apenas de somar pecas e servicos: o fluxo inclui checklist, observacoes, colaboradores, imagens e regras de precificacao.

### 4. Aprovacao e assinatura

Depois de consolidado, o orcamento pode gerar PDF, seguir para assinatura digital e mudar de status conforme a decisao do cliente.

### 5. Ordem de servico

Quando o atendimento avanca, a ordem de servico passa a representar a execucao. Ela carrega itens, status e validacoes necessarias para o trabalho acontecer de forma controlada.

### 6. Estoque

A aprovacao da OS pode consumir estoque. Esse ponto e relevante porque o sistema valida disponibilidade e tambem cruza dados fiscais de produto, como NCM.

### 7. Financeiro e fiscal

A camada financeira registra movimentos, grupos, contas, pagamentos, fluxo de caixa e DRE. Em paralelo, a camada fiscal cuida de NF-e/NFS-e e da comunicacao com a Webmania.

## Diferenciais funcionais importantes

### Multi-oficina de verdade

O sistema nao trata oficina como um campo decorativo. Oficina ativa, membership, papeis e filtros por oficina afetam o funcionamento do produto inteiro.

### Precificacao orientada a custo

Existe uma estrutura de custo da oficina que participa de calculos importantes do negocio. Isso impacta orcamento, rentabilidade e leitura gerencial da operacao.

### Integracoes fazem parte do core

Webmania, SuperSign e o bucket S3 compativel nao sao anexos isolados. Eles fazem parte do caminho feliz de varias funcionalidades.

## O que um dev precisa entender cedo

- o fluxo principal mora entre `apps.budget`, `apps.workorder`, `apps.stock` e `apps.finance`
- `apps.core` concentra muita infraestrutura reutilizavel
- `config/settings.py` define boa parte das integracoes e toggles de comportamento
- boa parte das features depende de oficina ativa e escopo correto
- o produto e orientado a fluxo de negocio, nao a CRUDs independentes

## Leitura recomendada depois deste arquivo

- [Arquitetura e apps](02-arquitetura-e-apps.md)
- [Fluxo principal do sistema](04-fluxo-principal-do-sistema.md)
- [Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md)
- [Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md)

[Indice da documentacao](README.md) | [Proximo: Arquitetura e apps](02-arquitetura-e-apps.md) | [Voltar ao README principal](../README.md)
