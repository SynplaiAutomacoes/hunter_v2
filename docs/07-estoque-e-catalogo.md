# Estoque e catalogo

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md) | [Proximo: Financeiro e DRE](08-financeiro-e-dre.md)

## Visao geral

Catalogo e estoque formam a base material do produto. O catalogo define o que pode ser vendido/executado; o estoque controla o que existe fisicamente e o que pode ser consumido sem quebrar o fluxo operacional.

## Catalogo

O catalogo do projeto cobre pelo menos tres tipos principais de entidade:

- produtos
- servicos
- kits

Esses itens sao usados fortemente em orcamentos e, por consequencia, na ordem de servico e na emissao fiscal.

## Produtos

Produtos tem relevancia operacional e fiscal. Eles nao sao apenas linhas de preco; carregam atributos que podem impactar:

- estoque
- validacao de NCM
- emissao de NF-e
- montagem de kits

## Servicos

Servicos participam do orcamento, da precificacao e tambem da emissao, especialmente no caminho de NFS-e.

## Kits

Kits agrupam produtos e servicos para acelerar composicao comercial. O app de orcamento possui rotas especificas para editar kit e recalcular seus componentes.

## Itens locais e criacao rapida

O modulo de orcamento permite criar itens locais/rapidos durante o atendimento. Isso e util para flexibilidade comercial, mas aumenta a necessidade de cuidado ao analisar impacto em:

- estoque
- fiscal
- consistencia de dados

## Estoque

O app `apps.stock` concentra saldos e movimentacoes. Embora este documento nao substitua a leitura do codigo, ha alguns comportamentos claros no projeto:

- produtos possuem representacao de saldo por oficina
- existem movimentacoes de entrada e saida
- a aprovacao da OS pode consumir estoque
- o sistema possui fluxos de importacao/transferencia em torno do dominio de estoque

## O que acontece na aprovacao da OS

`apps/workorder/approval.py` mostra a regra mais importante desse eixo:

- identifica os produtos necessarios
- bloqueia aprovacao quando nao ha saldo suficiente
- bloqueia aprovacao quando ha NCM invalido em produto relevante
- cria `StockMovement` de saida
- debita a quantidade aprovada do saldo atual

Isso torna o estoque parte do fluxo critico, nao apenas uma feature auxiliar.

## Relacao entre catalogo, estoque e fiscal

Esses tres temas andam juntos:

- catalogo define o item
- estoque informa disponibilidade e movimento
- fiscal depende de metadados corretos, como NCM, para emissao

Uma alteracao em produto aparentemente simples pode quebrar aprovacao de OS ou emissao fiscal mais a frente.

## Quando investigar `apps.catalog`

Abra `apps.catalog` quando houver demanda relacionada a:

- criacao ou manutencao de produtos
- servicos e tempos/duracoes
- kits e seus componentes
- grupos de catalogo
- atributos fiscais/comerciais de item

## Quando investigar `apps.stock`

Abra `apps.stock` quando a demanda envolver:

- saldo de item por oficina
- entrada/saida de estoque
- transferencia
- importacao de documentos/itens
- divergencia entre item vendido e item disponivel

## Checklist para mudancas nesse dominio

- o item precisa existir no catalogo ou pode ser local?
- ele afeta saldo de estoque?
- ele precisa de NCM/atributo fiscal valido?
- ele participa de kit?
- ele pode ser usado em orcamento e OS sem quebrar fluxo?

## Arquivos bons para abrir

- `apps/catalog/`
- `apps/stock/`
- `apps/budget/urls.py`
- `apps/workorder/approval.py`

## Relacao com outros docs

- [Fluxo principal do sistema](04-fluxo-principal-do-sistema.md)
- [Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md)
- [Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md)

[Anterior: Orcamentos, assinatura e webhooks](06-orcamentos-assinatura-e-webhooks.md) | [Indice da documentacao](README.md) | [Proximo: Financeiro e DRE](08-financeiro-e-dre.md) | [Voltar ao README principal](../README.md)
