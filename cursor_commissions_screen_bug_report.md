# Commissions screen bug report
_Exported on 9/2/2026 at 11:39:57 GMT-3 from Cursor (3.17.8)_

---

**User**

Parte 1: Apontamentos iniciais de bugs na tela de comissão

"Ó, vamos lá. Então beleza. Eu tô aqui, né, vou ver aqui as situações, por exemplo. Ordens de serviços. Vamos ver aqui no dash. Vamos pegar o mês de agosto. Deixa eu carregar. Ó, nós tivemos 9 serviços de garantia e cortesia. Nove. Esse é um ponto. E nós tivemos 58 OSs de venda, né. 58 OSs de venda.

Então, né, se eu vir aqui na folha de pagamento, e pegar o caso do Júnior, que aí foi colocar comissão em cima de todas as ordens de serviço. Aqui tá dando um bugzinho que, ó, quer ver, que ele vai, depois ele pisca a tela de novo, quer ver? Ó, não apareceu porque tá setembro, deixa eu voltar pra agosto aqui. Aqui, este aqui. Ó, então eu venho aqui em histórico de comissões, então aqui, imagino que tem todas as OSs que tão lá. Aí, Lucas, tem que fazer essa conferência, se todas as OSs tão apontando aqui certinho de venda.

Mas as de cortesia e garantia, só tem duas, né, e eu tive 9 ordens de serviço de cortesia e garantia no mês 8, e elas não aparecem aqui, entendeu? Foram 9 OS de cortesia e garantia, e elas não estão aparecendo aqui. Então, tem que ver por que que não tá aparecendo.

E também não tá falando, aparecendo os valores, né, os valores aqui que... que nem tá acontecendo, por exemplo, olha o do Edmundo aqui, ó. O do Edmundo, se eu clicar aqui, aqui, ó, no histórico de comissão, ó o valor. Tá aqui, ó, 55 e 20... 55 e 20, aqui apareceu. Eu não sei por qual motivo o do Osvaldo não tá aparecendo. E tá meio bugado, que eu clico e demora pra abrir. Ó. Então... ó lá. Aí dá esse bug aí.

Então aqui, essa base... 'base bruto', isso aqui pra mim não precisa de aparecer, não tem necessidade de escrever isso aqui base bruto aqui não. Só tá deixando a tabela maior, pra mim não precisa de aparecer. Ele tem que seguir o mesmo padrão que a gente já tinha validado lá na... do... dos outros aqui, que era do... por exemplo, o do Edmundo aqui, ó. Esse padrãozinho aqui tá top, tá top, bem... bem resumidinho. E aí, sempre mostrar o valor total, né, o valor total, soma tudo, valor total aqui embaixo. Soma tudo, valor total aqui embaixo. Tá faltando o valor total e a quantidade de OS também. Se você conseguir trazer a quantidade de ordem de serviço aqui embaixo, que aí a gente já bate se tá fechando com o dash a quantidade que tem aqui, né. Por exemplo, o caso do Osvaldo, que ganha no global.

Então, se eu tenho aqui no dash, aqui no mês de agosto, eu tive... Deixa eu voltar aqui. Agosto. Eu tive 58 OSs de venda, eu tenho que ter 58 OSs aqui apontando a comissão, exceto alguma OS que não tenha serviço zerado, aí ele não vai ter comissão em cima do serviço zerado, né. Mas OS que tenha serviço, elas tem que aparecer ali.

Então é isso. Vou voltar aqui de novo, vou mostrar aqui a folha de pagamento, o que que tem que fazer aqui. Deixa eu abrir o Osvaldo Júnior aqui. Opa, deixa eu por aqui mês de agosto. Osvaldo Júnior. Nossa, o dele demora pra carregar. Então, é tirar esse base bruto, aqui não precisa. Aqui tá a OS, né, bonitinho, ter uma contagem, eu acho que vai facilitar a vida, né. Aqui tem o valor total, aqui tem o valor total. Aqui tá certinho, só as dos meninos que não tá aparecendo, dos meninos não foi alterado. Dos meninos ainda não tá desse jeito que tá aqui, né, com o valor total. E aí aparecendo o valor total e a contagem das OS pra gente conferir. Tem que ter 58 OSs aqui no do Júnior e as 9 OS de comissão teria que estar aparecendo aqui também, né, não sei por que não tá aparecendo. Beleza?"

Parte 2: Complemento sobre a divergência de valores

"Ó, e aqui fazendo um complemento do chamado, até a Rose me mostrou aqui. Ó. Se eu vir aqui na apuração de comissões, no mês de agosto. Tá dando aqui, ó: 94 mil de comissão... de serviços. 5% de 94 mil... ó. 94.691,43 menos 95% daria 4.734,57, né? Eu pegando aqui pelo total de serviços que tá mostrando aqui pra mim. Né, e imagino que esse valor aqui já tá considerando os descontos, tudo certinho, né. Se é o valor líquido da ordem de serviço, imagino que seja.

Então, tá dando 4.700. Aí você vai aqui na folha de pagamento, e você entra aqui nas comissões da mesma pessoa, que é o Osvaldo Júnior, e você vai vir aqui em histórico de comissões. Opa, é o mês de agosto. Demora pra carregar o dele, né? Ó. Tá dando apenas 3.800... tá dando uma diferença... aí, ó. Tá dando apenas 3.800. Tá dando uma diferença de 900 reais aqui.

E aí o que eu queria entender: se lá tá errado, né, o total de serviços, ou se aqui tá faltando OS, tá bom? Aí vocês cons... fazem essas conferências certinho pra bater direitinho. Ou se tem alguma OS que não foi apontada aqui, tá bom?"

esse é o relato do cliente, o meu banco local é uma copia da produção, o q vc ver aqui é como esta la.

---

**Cursor**

Investigando o fluxo de comissões e folha de pagamento para mapear os bugs relatados e montar um plano de correção.


Lendo os arquivos centrais e consultando o banco local para validar as divergências de agosto.


Com o mapeamento do código concluído, vou montar o plano. Há uma decisão de produto importante sobre o critério de reconciliação com o dashboard.


**Critério de reconciliação com o dashboard**

> **O dashboard conta O.S. de venda por **data de entrega** (`delivered_at`), mas a comissão usa **competência do pagamento** (vencimento do plano de pagamento). Para bater os 58 O.S. de venda, qual critério devemos priorizar no histórico da folha?**
> - Manter competência por pagamento (regra atual) e mostrar contagem + nota explicativa quando divergir do dashboard
> - Alinhar o histórico ao dashboard usando data de entrega para listagem/contagem (mesmo que a comissão continue na competência do pagamento)
> - Mostrar as duas visões: O.S. na competência do pagamento + O.S. entregues no mês (para conferência)
>
> Answer: manter a competência por pagamento, mas mostrar como previsão essas que entregues no mês

---

**User**

Implement the plan as specified, it is attached for your reference. Do NOT edit the plan file itself.

To-do's from the plan have already been created. Do not create them again. Mark them as in_progress as you work, starting with the first one. Don't stop until you have completed all the to-dos.

---

**Cursor**

Implementando o plano completo. Começando pela auditoria de dados de agosto e, em seguida, as correções de código.


Auditoria concluída: 58 vendas entregues, 59 entradas de comissão, 10 garantias/cortesias (5+5 nas tabelas). Implementando as correções.


Implementando as mudanças principais no serviço de histórico e nos templates.


Escrevendo a versão completa do serviço de histórico de comissões com todas as melhorias.


Ajustando o lazy-load para disparar ao clicar na aba, já que `x-show` impede o `intersect`.


Auto-carregando o histórico quando a aba já estiver selecionada ao abrir o modal.


Implementação concluída. Resumo do que foi feito:

## Auditoria (agosto/2026 — Osvaldo Júnior)
- **58** O.S. de venda entregues no mês
- **59** entradas de comissão na competência (1 a mais: entregue fora de agosto, pagamento em agosto)
- **10** garantias/cortesias root entregues (dashboard mostrava 9 — diferença de 1 O.S.)
- Comissão na folha: **R$ 4.431,72** (alinhada ao histórico)

## Correções implementadas

### UI do histórico
- Removido o sub-label **"Base: Bruto"** — tabela mais compacta, como no layout do Edmundo
- **Total + contagem de O.S.** no rodapé (global e legado)
- Valor total da folha exibido no layout global

### Garantias/cortesias
- Nova seção **"Garantias/Cortesias entregues no mês"** (regra do dashboard: O.S. raiz + `delivered_at`)
- Seção **"Motivo não informado"** para O.S. sem `courtesy_reason_type`
- Queries otimizadas (bulk fetch de entradas da O.S. origem, sem N+1)

### Previsão
- Seção **"Previsão — O.S. de venda entregues neste mês"** para O.S. entregues no mês com competência de pagamento em outro mês

### Apuração de comissões
- Card **"Total de serviços"** agora soma apenas bases de origem **service** (`Sum` por O.S., não `Max` misturando produto)

### Performance
- Histórico carregado via **lazy-load HTMX** ao clicar na aba (não bloqueia mais a abertura do modal)
- Novo endpoint: `folha-pagamento/<pk>/historico-comissoes/`

## Arquivos principais
- [`apps/finance/services/payroll_commission_history.py`](apps/finance/services/payroll_commission_history.py)
- [`apps/finance/templates/finance/payroll/partials/commission_history_global.html`](apps/finance/templates/finance/payroll/partials/commission_history_global.html)
- [`apps/finance/templates/finance/payroll/partials/commission_history_legacy.html`](apps/finance/templates/finance/payroll/partials/commission_history_legacy.html)
- [`apps/finance/views/commissions.py`](apps/finance/views/commissions.py)
- [`apps/finance/views/payroll.py`](apps/finance/views/payroll.py)

## Validação
- `ruff check` passou nos arquivos alterados
- Dados de produção local verificados: `sale_count=59`, `benefit_delivered=10`
- Testes adicionados em `test_payroll_commission_history.py` e `test_commissions.py`
- Suite de testes Django não rodou — migration `0021` falha ao criar o banco de teste (`warranty_origin_id` ausente); problema pré-existente do ambiente de teste, não desta mudança

Para validar na UI: abra a folha do Júnior em agosto → aba **Histórico de comissões** → deve carregar rápido, mostrar totais/contagens e as 10 garantias/cortesias na seção dedicada.

---
