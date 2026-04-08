# Fluxo principal do sistema

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Configuracao do ambiente](03-configuracao-do-ambiente.md) | [Proximo: Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md)

## Visao geral

O Hunter V2 e orientado a fluxo. Para entender o sistema de verdade, nao basta abrir modelos isolados. O caminho mais util e acompanhar a jornada operacional da oficina.

Este documento descreve a trilha principal do produto do ponto de vista de negocio e de implementacao.

## Etapa 0: conta, usuario e oficina ativa

Antes de qualquer fluxo operacional relevante acontecer:

- o usuario precisa estar vinculado a uma `Account`
- a conta precisa ter oficina valida
- o request precisa resolver uma oficina ativa na sessao

Esse comportamento e sustentado principalmente por:

- `apps/accounts/models.py`
- `apps/core/middlewares.py`
- `apps/workshops/context_processors.py`

## Etapa 1: entrada do atendimento

O atendimento pode nascer de mais de um lugar:

- agendamento em `apps.scheduling`
- cliente/veiculo ja existente em `apps.customer`
- criacao de cliente/veiculo durante o fluxo de orcamento

Aqui o objetivo e formar o contexto do atendimento: quem e o cliente, qual e o veiculo e qual oficina esta executando a operacao.

## Etapa 2: orcamento como centro do fluxo

O modulo de orcamento e o coracao do produto. A propria organizacao de rotas em `apps/budget/urls.py` deixa isso claro: lista, criacao, itens, calculos, etapas, PDFs, assinatura, eventos e webhook estao todos no mesmo app.

### Passo 2.1: cliente e veiculo

O orcamento precisa associar cliente e veiculo. Existem endpoints auxiliares para detalhe e selecao desses dados.

### Passo 2.2: triagem e perguntas investigativas

O sistema captura relato principal e perguntas investigativas configuraveis. Isso da contexto tecnico antes da composicao de itens.

### Passo 2.3: checklist, diagnostico e imagens

O fluxo tecnico ganha corpo com:

- checklist
- observacoes de defeito
- colaboradores envolvidos
- imagens do atendimento

### Passo 2.4: composicao de itens

O orcamento pode receber:

- produtos
- servicos
- kits
- itens locais/rapidos criados no proprio fluxo

Esse trecho conversa com `apps.catalog` e, dependendo do caso, com estoque e regras fiscais de produto.

### Passo 2.5: precificacao

Aqui o sistema deixa de ser um formulario e vira ferramenta de negocio. O calculo usa informacoes da oficina e de seus custos para chegar a valores, rentabilidade e distribuicao entre peca/mao de obra.

Pontos importantes:

- slider de composicao
- desconto
- calculo por item
- calculo de kit e componentes
- custos de oficina e margem

### Passo 2.6: consolidacao, PDF e aprovacao

Ao final, o orcamento pode gerar PDF, salvar observacoes finais e mudar de status. Dependendo do caso, entra o fluxo de assinatura digital.

## Etapa 3: assinatura digital

O sistema possui suporte a envio para assinatura e a endpoints de webhook para conclusao do processo.

Elementos relevantes:

- envio para assinatura no app de orcamento
- preview e arquivo por token
- webhook SuperSign
- comando `manage.py webhook` para sincronizar o endpoint remoto

Sem `APP_BASE_URL` correto, esse fluxo costuma falhar ou ficar inconsistente em ambiente local.

## Etapa 4: ordem de servico

Quando o fluxo comercial avanca, a ordem de servico passa a representar a execucao. A OS herda ou espelha informacoes relevantes do orcamento aprovado.

Na pratica, a OS funciona como ponte entre:

- o que foi vendido
- o que sera executado
- o que consumira estoque
- o que podera gerar financeiro/fiscal

## Etapa 5: aprovacao da OS e baixa de estoque

O arquivo `apps/workorder/approval.py` mostra um comportamento importante do dominio:

- coleta os produtos obrigatorios da OS
- valida quantidade disponivel no estoque da oficina
- valida NCM de produtos
- cria movimentacoes de saida
- atualiza saldo de estoque
- so depois marca a OS como aprovada

Ou seja: a aprovacao da OS nao e um simples flip de status. Ela tem side effects importantes e pode falhar por bloqueios reais do negocio.

## Etapa 6: financeiro

O modulo financeiro cobre duas frentes:

- gestao financeira operacional
- camada fiscal/documental

No eixo gerencial entram, entre outros:

- grupos financeiros
- meios de pagamento
- contas bancarias
- movimentacoes financeiras
- fluxo de caixa
- DRE

Parte disso e manual, parte pode ser alimentada por fluxos do atendimento/OS.

## Etapa 7: emissao fiscal

Depois do fechamento operacional e financeiro, o sistema pode emitir:

- NF-e para produtos/pecas
- NFS-e para servicos

Essa etapa depende de combinacao correta entre:

- configuracao da oficina
- empresa vinculada na Webmania
- certificado e senha
- classes de imposto
- webhook de retorno

## Resumo do fluxo ponta a ponta

1. Usuario entra em uma conta e opera em uma oficina ativa.
2. Cliente e veiculo entram no contexto do atendimento.
3. O orcamento guia triagem, checklist, itens e precificacao.
4. O orcamento pode gerar PDF, aprovacao e assinatura digital.
5. A aprovacao alimenta a ordem de servico.
6. A aprovacao da OS valida estoque e baixa pecas.
7. O financeiro registra os reflexos do atendimento.
8. A camada fiscal emite e acompanha documentos via Webmania.

## Onde navegar no codigo para seguir esse fluxo

- `config/urls.py`
- `apps/budget/urls.py`
- `apps/workorder/approval.py`
- `apps/finance/urls.py`
- `apps/finance/views/webhook.py`

## O que um dev deve checar antes de alterar esse fluxo

- se a mudanca precisa respeitar oficina ativa
- se existe side effect em estoque
- se existe side effect financeiro
- se existe impacto fiscal
- se ha webhook, assinatura ou integracao externa envolvida

## Proxima leitura recomendada

- [Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md)
- [Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md)
- [Financeiro e DRE](08-financeiro-e-dre.md)
- [Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md)

[Anterior: Configuracao do ambiente](03-configuracao-do-ambiente.md) | [Indice da documentacao](README.md) | [Proximo: Multi-oficina e permissoes](05-multi-oficina-e-permissoes.md) | [Voltar ao README principal](../README.md)
