# Financeiro e DRE

[Voltar ao README principal](../README.md) | [Indice da documentacao](README.md) | [Anterior: Estoque e catalogo](07-estoque-e-catalogo.md) | [Proximo: Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md)

## Escopo do modulo financeiro

O app `apps.finance` cobre uma area ampla do sistema. Pelo arquivo `apps/finance/urls.py`, ele engloba:

- grupos financeiros
- meios de pagamento
- contas bancarias
- movimentacoes financeiras
- fluxo de caixa
- DRE
- classes de imposto e presets
- emissao fiscal
- empresas Webmania
- webhook da Webmania
- arquivos/documentos emitidos

Em outras palavras: `apps.finance` nao e apenas um modulo de contas a pagar/receber. Ele tambem e a espinha fiscal do sistema.

## Blocos principais do dominio

### Grupos financeiros

Organizam receitas, despesas e custos. Sao a base para classificacao e leitura gerencial.

### Meios de pagamento

Permitem modelar forma de recebimento/pagamento, incluindo taxas e parcelamento em alguns casos.

### Contas bancarias

Representam os canais financeiros da operacao.

### Movimentacoes financeiras

Registram creditos e debitos com contexto suficiente para leitura operacional e gerencial.

A tela de relatorio (`finance:reports_home`, `/finance/reports/`) permite filtrar por valor exato e ordenar a listagem por qualquer coluna:

- `?valor=` aceita formatos pt-BR/en (`R$ 121,00`, `121,00`, `121.00`, `121`) e compara o valor liquido em duas casas decimais. Em linhas de OS, o valor considerado e o `total_paid` de cada pagamento.
- `?ordering=<coluna>` / `?ordering=-<coluna>` alterna ascendente/descendente. Chaves validas: `pago`, `conciliado`, `tipo`, `lancamento`, `vencimento`, `agente`, `descricao`, `plano`, `pagamento`, `total`. Valor ausente ou invalido mantem o padrao `-pk`.
- A ordenacao e aplicada apos a expansao das linhas de OS (em memoria) e antes da paginacao, e o PDF de exportacao reutiliza a mesma logica.

### Fluxo de caixa

Consolida visao temporal da operacao financeira.

### DRE

Entrega leitura gerencial do resultado, com suporte a PDF e Excel pelo mapa de rotas atual.

## Financeiro manual x automatico

Nem toda movimentacao nasce de digitacao manual. O repositorio tambem possui services como:

- `apps/finance/services/workorder_financial_movements.py`
- `apps/finance/services/dre.py`
- `apps/finance/services/reports.py`

Isso sugere que parte da camada financeira e alimentada por eventos ou transicoes de outros dominios, especialmente da ordem de servico.

## DRE no contexto do produto

O DRE ajuda a transformar o sistema em ferramenta de gestao, nao apenas de operacao. Ele responde perguntas do tipo:

- quanto a oficina vendeu
- quanto gastou
- como custos e despesas se distribuem
- qual o resultado do periodo

## Emissao unificada dentro do financeiro

O modulo financeiro possui endpoints para preview de emissao e criacao de requisicoes fiscais. Isso reforca que a camada fiscal foi acoplada ao financeiro, e nao isolada em um app separado.

## Cuidados ao alterar esse dominio

### Dinheiro exige mais contexto

Antes de mudar qualquer regra financeira, confirme:

- oficina/conta correta
- classificacao correta em grupo financeiro
- impacto em fluxo de caixa
- impacto em DRE
- impacto em emissao/documentacao

### Nao confunda financeiro com fiscal

Estao no mesmo app, mas nem toda mudanca financeira deve mexer em emissao. Ao mesmo tempo, mudancas de emissao podem depender de dados financeiros auxiliares.

## Bugs comuns nessa area

### Numero fecha no detalhe, mas nao no agregado

- revise classificacao por grupo financeiro
- revise periodo/filtro aplicado no relatorio
- confirme se movimentos automaticos foram criados

### DRE nao bate com expectativa da operacao

- confira se receitas, custos e despesas estao classificados no grupo correto
- revise origem dos movimentos
- confira filtros de oficina e periodo

### Pagamento ou recebimento nao aparece

- valide conta bancaria, forma de pagamento e grupo financeiro
- confira se o movimento foi realmente persistido

## Arquivos e areas para investigar

- `apps/finance/urls.py`
- `apps/finance/models/`
- `apps/finance/services/`
- `apps/finance/views/`

## Relacao com outros dominios

O financeiro conversa com:

- `apps.workorder`
- `apps.stock`
- `apps.workshops`
- `apps.catalog`
- `apps.budget`

Isso acontece porque vender, executar, consumir e emitir documento sao eventos diferentes da mesma operacao.

[Anterior: Estoque e catalogo](07-estoque-e-catalogo.md) | [Indice da documentacao](README.md) | [Proximo: Fiscal, NFe/NFSe e Webmania](09-fiscal-nfe-nfse-e-webmania.md) | [Voltar ao README principal](../README.md)
