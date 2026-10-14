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

## Importacao de NF-e via SEFAZ (stock)

Fluxo de entrada por nota fiscal de compra (`SEFAZ → Fornecedor → Itens → Pagamento → Revisao`):

- **Manual:** `StockImportCreateView` + botao "Atualizar Lista" (`RefreshSefazListView`) consultam a Distribuicao DF-e (`consulta_distribuicao` com certificado A1 via `pynfe`) e populam o cache `SefazZipCache`. O usuario escolhe a NF no wizard e so entao baixa o XML completo e cria o `StockImport`.
- **Automatico:** `manage.py sync_stock_sefaz_distribuicao` (Cron externo, ver [Deploy](10-deploy-build-e-operacao.md)) executa a mesma sincronizacao de lista via `apps/stock/services/sefaz_distribution.py::sync_sefaz_distribution_for_workshop`. Persiste **somente** `SefazZipCache` + carimbos `Workshop.last_nsu_sefaz` / `last_sefaz_search_date`. **Nunca** cria `StockImport`, `StockMovement`, `StockProduct`, `FinancialMovement` ou `FiscalDocument`.
- **Throttle compartilhado:** 1 consulta/hora por oficina (`Workshop.can_search_sefaz`), valido para manual e automatico. Se o Cron rodou ha menos de 1h, o botao manual exibe "Aguarde..." e vice-versa (lock transacional com `select_for_update` no comando).
- **Janela do automatico:** default ~12:00 (±15min) + 19h–06h (`America/Sao_Paulo`), configuravel via `SEFAZ_AUTO_SYNC_*`. Fora da janela o comando encerra com `skipped_outside_window` sem chamar o SEFAZ.
- **Resumos sem itens:** `resNFe` continua gerando `SefazZipCache` e exige manifestacao/download manual posterior (fora do escopo da automacao).
- **Nao confundir:** `apps/scheduling` e agendamento de servicos da oficina (dominio), nao infraestrutura de scheduler. O auto-sync usa Cron externo, nao `apps/scheduling`.

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
