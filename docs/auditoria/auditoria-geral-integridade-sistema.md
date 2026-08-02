# Auditoria geral de integridade lógica do sistema

**Sistema:** Hunter v2  
**Data da análise:** 01/08/2026  
**Tipo:** auditoria estática de código — primeira etapa, sem alteração funcional  
**Escopo:** todos os módulos Django instalados no projeto

## 1. Resumo executivo

A aplicação é um monólito Django orientado à oficina ativa. O fluxo principal é `Orçamento -> Ordem de Serviço -> Estoque/Financeiro -> Fiscal`, com módulos auxiliares de cadastros, agenda, colaboradores/folha, mensagens e indicadores. Há boas proteções locais — transações em fluxos críticos, bloqueio pessimista em parte da baixa de estoque, restrições únicas em diversos cadastros, contratos para integrações e scoping recorrente por oficina —, mas essas proteções não formam uma única fronteira transacional e nem todas as invariantes estão garantidas no banco.

Foram classificados **2 riscos P0, 21 P1, 21 P2 e 5 P3**. Os temas de maior impacto são:

1. uma OS pode permanecer aprovada mesmo se a baixa de estoque falhar, pois uma exceção é suprimida no modelo;
2. relações repetem `workshop_id` sem garantia geral de que todas as entidades relacionadas pertencem à mesma oficina;
3. DRE mistura competência, vencimento, pagamento e entrega, e contém identidades contábeis com nomenclatura/cálculo incompatíveis;
4. parcelas previstas de uma OS são materializadas como movimentos `is_paid=True`, o que pode fazer previsão parecer recebimento;
5. exclusões/atualizações em lote podem deixar totais materializados de orçamento e OS desatualizados;
6. importação e exclusão de entrada de estoque não mantêm vínculo completo entre documento, movimentos e saldo;
7. resumos de folha usam o vínculo financeiro legado e ignoram os movimentos componentizados atuais;
8. alguns indicadores usam numerador e denominador de universos diferentes ou interpretam “meses anteriores” como “qualquer mês diferente”.

Esta etapa não consultou dados de produção, não chamou provedores externos e não alterou código. Portanto, os achados marcados como **risco estrutural** demonstram uma lacuna de garantia, não necessariamente a existência de registros inválidos hoje. A incidência real deve ser medida com consultas somente leitura numa segunda etapa.

## 2. Critério de prioridade

| Prioridade | Critério |
|---|---|
| **P0 — crítico** | Pode aprovar ou expor dados logicamente inválidos entre oficinas, ou romper simultaneamente estoque/financeiro/OS sem uma barreira confiável. |
| **P1 — alto** | Pode alterar valores financeiros, fiscais, saldos, DRE, folha ou indicadores gerenciais de maneira material. |
| **P2 — médio** | Pode causar classificação, histórico, filtro ou métrica incorreta em cenários delimitados. |
| **P3 — baixo** | Fragilidade de manutenção, duplicidade estrutural ou inconsistência de baixa materialidade imediata. |

## 3. Metodologia e limites

Foram usados:

- inventário de apps, models, views, services, use cases, comandos e relatórios;
- rastreamento estático das escritas desde orçamento/OS até estoque, financeiro, folha e fiscal;
- comparação entre consultas de tela, PDF e Excel;
- revisão de filtros de oficina, status, período, pagamento e conciliação;
- identificação de campos materializados, callbacks de `save/delete`, operações em lote e restrições de banco;
- execução somente leitura de `manage.py check`, que terminou sem erros usando o Python do ambiente virtual.

Limites desta etapa:

- não houve amostragem da base de produção ou staging;
- não foram reconciliados documentos com Sefaz, Webmania, SuperSign, banco ou bucket;
- não foram executados testes que escrevessem no banco;
- não se avaliou precisão tributária legal; avaliou-se a consistência lógica interna;
- valores e frequências dos impactos permanecem a confirmar com consultas de dados.

## 4. Arquitetura e módulos analisados

| Área | Apps / componentes | Entidades e responsabilidades principais |
|---|---|---|
| Identidade e acesso | `accounts`, `iam` | `Account`, `User`, papéis, permissões, tokens e páginas favoritas. |
| Oficina e contexto | `workshops`, `collaborators` | `Workshop`, custos mensais, dias trabalhados, membros, colaboradores, benefícios, folha e comissões. |
| Dados mestres | `customer`, `suppliers`, `catalog`, `sources` | Cliente, veículo, fornecedor, origem, produto, serviço, kit, grupos e aplicações de kit. |
| Comercial | `budget`, `quote` | Orçamento, itens, descontos, kits, histórico, perguntas investigativas e respostas. |
| Operação | `workorder`, `checklist`, `scheduling` | OS, itens, pagamentos previstos, anexos, histórico, checklist e agendamentos. |
| Estoque | `stock` | Produto em estoque, movimentos, importações XML/Sefaz, transferências, alertas e relatórios. |
| Financeiro | `finance` | Movimentos, grupos/plano orçamentário, formas de pagamento, contas bancárias, visão financeira, fluxo de caixa e DRE. |
| Fiscal | `finance` e providers de `core` | NFe/NFSe, itens, lotes, cancelamentos, eventos, tentativas, documentos recebidos e conciliação. |
| Comunicação | `messaging` | Templates, segmentos, grupos, disparos, destinatários e avaliações de satisfação. |
| Plataforma compartilhada | `core` | Dashboard, relatórios, filtros, busca, tabelas, PDF, storage, assinatura e contratos de providers. |

### 4.1 Observações arquiteturais

- O sistema ainda está em transição para camadas. `core` concentra abstrações compartilhadas, enquanto regras de negócio continuam distribuídas entre models, services, views e signals.
- `Budget` e `WorkOrder` mantêm estruturas e fórmulas paralelas. A sincronização reduz divergência no caminho normal, mas aumenta o número de pontos que precisam permanecer equivalentes.
- Não existe uma entidade autônoma de “venda”. A venda é inferida de OS, status, parcelas e movimentos financeiros.
- Contas a pagar/receber usam `FinancialMovement` com direção e flags, não ledgers separados.
- Conciliação bancária é representada principalmente por `is_reconciled`; não foi encontrada uma entidade de sessão/extrato de conciliação que imponha fechamento por período.
- Folha é uma projeção operacional de colaborador + componentes financeiros, não um motor trabalhista/fiscal completo.

## 5. Dados mestres e fronteiras de oficina

### 5.1 Proteções encontradas

- Clientes, veículos, fornecedores, produtos, serviços, kits, fontes, colaboradores e diversas configurações possuem restrições únicas por oficina.
- `WorkshopScopedMixin` e helpers de oficina são utilizados em várias views.
- `Appointment.clean()` valida coerência entre oficina, cliente, veículo, orçamento e OS.
- Existem normalizadores para nomes, documentos, placa, telefone e busca sem acentos em partes dos cadastros.

### 5.2 Riscos de dados mestres

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-01 | **P0** | Risco estrutural | **Integridade entre oficinas não é uma invariante geral.** Muitos registros carregam `workshop` e também FKs para objetos que carregam sua própria oficina, sem `clean()`, constraint ou serviço único impondo igualdade. Exemplos: orçamento/cliente/veículo, OS/orçamento, item/OS/produto, movimento/produto de estoque, solicitações fiscais/OS e folha/colaborador. Escritas por ORM, importação ou `bulk_*` podem produzir cruzamento de tenant e contaminar relatórios filtrados apenas pela entidade externa. `Appointment` implementa a validação desejável, mas o padrão não é global (`apps/scheduling/models.py:136-238`). |
| AUD-02 | **P1** | Confirmado por modelo | `WorkshopCollaborator.user` é `OneToOneField` global. O mesmo usuário pode ser membro de várias oficinas, mas só pode ter um perfil de colaborador em uma (`apps/collaborators/models.py:54-70`). Isso conflita com o modelo multi-oficina e pode fragmentar folha, comissão e permissões. |
| AUD-03 | **P2** | Risco estrutural | Unicidades são em geral aplicadas ao texto/documento armazenado, não à forma canônica universal. Como a normalização varia entre form, model e fluxo de importação, caixa, pontuação e espaços podem permitir duplicados semanticamente iguais ou bloquear valores vazios equivalentes. Afeta clientes, fornecedores, códigos, serviços, categorias e placas. |
| AUD-04 | **P2** | Confirmado por constraint | Conta bancária é única por oficina, banco e número, sem considerar agência. Contas de agências diferentes com o mesmo número podem ser bloqueadas (`apps/finance/models/bank_account.py`). |
| AUD-05 | **P2** | Risco estrutural | `WorkshopMember` garante usuário+oficina únicos, mas não garante no modelo que usuário, oficina e papel pertençam à mesma conta (`apps/collaborators/models.py:20-48`). Uma associação inconsistente afeta autorização contextual. |
| AUD-06 | **P3** | Risco estrutural | Checklist, perguntas e alguns itens configuráveis não têm uma regra forte de unicidade semântica/ordenação. Duplicatas de template ou pergunta podem duplicar respostas e apresentação, embora não alterem diretamente o razão financeiro. |

## 6. Comercial e orçamento

### 6.1 Fluxo mapeado

1. orçamento associa oficina, cliente, veículo, tipo, itens e condições;
2. itens podem representar produto, serviço ou snapshot de kit;
3. total é calculado e também persistido em `stored_total_amount`;
4. aprovação do orçamento cria/sincroniza uma OS;
5. histórico e PDF são derivados do orçamento; conversão é inferida pela aprovação/OS.

### 6.2 Achados

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-07 | **P1** | Confirmado por código | **Totais materializados podem ficar obsoletos.** `BudgetItem.save/delete` atualiza o pai, mas exclusões em lote nas views usam `QuerySet.delete()`, que não chama `Model.delete()`. Em determinados passos o reset subsequente não salva o orçamento, deixando `stored_total_amount` antigo (`apps/budget/views/item_views.py:376`, `:413`, `:450`; `apps/budget/models.py:255-263`, `:1223-1230`). Dashboards e relatórios agregam esse campo. |
| AUD-08 | **P1** | Confirmado por código | Atualização de snapshot de kit usa `QuerySet.update()` para itens e não recompõe necessariamente o total materializado do orçamento/OS (`apps/budget/models.py:1283-1321`; `apps/workorder/models.py:1060-1099`). Alterar um kit já aplicado pode gerar diferença entre soma dos itens, orçamento, OS e relatórios. |
| AUD-09 | **P1** | Risco estrutural | `WorkOrder.budget` é FK, não OneToOne/unique. Na aprovação, `get_or_create(budget=...)` não impede duas transações concorrentes de criarem duas OS para o mesmo orçamento. Diversas telas usam `.first()`, ocultando a segunda (`apps/budget/models.py:230-247`; `apps/workorder/models.py:73-76`; `apps/customer/views.py:108-127`). |
| AUD-10 | **P2** | Confirmado por consulta | A taxa de aprovação usa numerador de aprovados que inclui todos os tipos, enquanto o denominador exclui garantia/cortesia e cancelados. A taxa pode ultrapassar 100% ou comparar coortes diferentes (`apps/core/infrastructure/services/dashboard_query_service.py:940-988`). |
| AUD-11 | **P2** | Risco conceitual | Conversão comercial não possui entidade/evento imutável próprio; é reconstruída de status atuais. Reabertura, cancelamento ou mudança posterior altera retroativamente a conversão histórica, salvo onde o histórico é consultado explicitamente. |

## 7. Ordem de Serviço

### 7.1 Fluxo mapeado

- criação automática a partir do orçamento aprovado;
- sincronização de itens, kits, cliente/veículo e valores;
- aprovação com tentativa de baixa de produto e geração financeira;
- execução/delivery representadas por status e `delivered_at`;
- reabertura com reversão de movimentos de estoque e remoção de movimentos financeiros associados;
- fiscal e comissões vinculados à OS.

### 7.2 Achados

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-12 | **P0** | Confirmado por código | **A OS pode ficar aprovada sem baixa completa de estoque.** `WorkOrder.approve()` persiste o status e chama `_ensure_stock_consumed_on_approve()`, que captura `Exception`, apenas registra log e não desfaz a aprovação (`apps/workorder/models.py:411-444`). O serviço transacional normal é seguro, mas caminhos diretos de `save/approve` aceitam falha. A existência de `fix_missing_stock_consumption` confirma que o desvio é uma classe operacional conhecida. |
| AUD-13 | **P1** | Confirmado por código | A idempotência da baixa verifica se existe **algum** movimento de saída da OS e então retorna, sem reconciliar todos os itens/quantidades. Uma baixa parcial ou itens alterados depois podem nunca ser completados (`apps/workorder/approval.py:110-121`). |
| AUD-14 | **P1** | Confirmado por código | Reabrir uma OS muda o status para rascunho, porém o método de modelo não limpa `delivered_at` (`apps/workorder/models.py:465-472`). A OS reaberta pode continuar em relatórios de entrega/custo e em consultas que aceitam rascunho. |
| AUD-15 | **P1** | Risco conceitual | Aprovação preenche `delivered_at`, combinando autorização comercial, início/execução, faturamento e entrega em um único evento. O dashboard de carros e o custo da DRE podem interpretar “aprovado” como “entregue”, mesmo antes da execução real. |
| AUD-16 | **P2** | Risco estrutural | OS e orçamento repetem fórmulas de itens, descontos, kits, rentabilidade e totais. Mudanças feitas em apenas um lado criam divergência silenciosa; os campos materializados tornam o problema persistente. |

## 8. Financeiro, contas e conciliação

### 8.1 Modelo observado

- `FinancialMovement` representa créditos e débitos, previstos/pagos e conciliados/não conciliados;
- movimentos de OS podem ter um pai agregado e filhos por parcela/forma de pagamento;
- movimentos de taxa de cartão, estoque e folha reutilizam a mesma tabela;
- grupos financeiros formam a classificação usada pela DRE;
- fluxo de caixa considera movimentos pagos e conciliados.

### 8.2 Achados

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-17 | **P1** | Confirmado por código | Parcelas previstas da OS são sincronizadas como movimentos `is_paid=True`; o movimento pai também nasce pago (`apps/finance/services/workorder_financial_movements.py:135-169`). Como `WorkOrderPaymentMethod` não registra liquidação real, algumas telas podem tratar venda/parcelamento como crédito pago antes da conciliação. |
| AUD-18 | **P1** | Confirmado por consulta | A visão financeira soma “créditos pagos” com base em `is_paid`, sem exigir conciliação em todos os cards. Já o fluxo de caixa exige `is_paid=True` e `is_reconciled=True`. As duas telas podem divergir para o mesmo período por definição, não por erro de soma. |
| AUD-19 | **P1** | Risco estrutural | Não há constraint completa exigindo direção, valor e data válidos/não negativos em todos os movimentos, nem unicidade de movimento pai/parcela de OS. O serviço remove extras no caminho normal, mas concorrência e escrita direta podem duplicar ou criar movimentos incompletos. |
| AUD-20 | **P2** | Risco de divergência | Reversões são filtradas de maneiras diferentes entre consultas. Algumas excluem originais revertidos e/ou os próprios estornos; outras usam somente flags de pagamento. O mesmo estorno pode aparecer no extrato, visão geral e DRE de forma distinta. |
| AUD-21 | **P2** | Confirmado por filtro | Cards de “meses anteriores” calculam total geral menos o mês selecionado ou usam `.exclude(mês/ano selecionado)`. Isso inclui meses **futuros**, e não somente períodos anteriores (`apps/core/infrastructure/services/dashboard_query_service.py:1006-1060`, `:1170-1175`). |

## 9. DRE

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-22 | **P1** | Confirmado por cálculo | A linha exibida como “Receita Líquida” subtrai CMV/CSP da receita bruta. Contabilmente essa operação representa lucro bruto, não receita líquida. Além da nomenclatura, o “Resultado Operacional” é calculado apenas como receitas financeiras menos despesas financeiras, sem incorporar o resultado bruto (`apps/finance/services/dre.py:232-320`). |
| AUD-23 | **P1** | Confirmado por filtro | O seletor pago/não pago (`tipo_data`) é aplicado aos `FinancialMovement`, mas a receita bruta de OS é sempre calculada de parcelas com status de OS rascunho/aprovado por vencimento. Assim, DRE “paga” e “não paga” podem exibir a mesma receita bruta (`apps/finance/services/dre.py:133-152`, `:572-590`). |
| AUD-24 | **P1** | Confirmado por filtro | Receita inclui OS em rascunho e aprovada por vencimento da parcela; custos de produtos/serviços exigem `delivered_at`. Universos e datas diferentes inflam ou comprimem margem conforme o estágio da OS (`apps/finance/services/dre.py:133-152`, `:418-457`). |
| AUD-25 | **P2** | Confirmado por configuração | Taxas e receitas dependem da resolução de grupos por nomes exatos, como “Taxa de Maquininhas”, “vendas” e “receitas”. Renomear ou reorganizar o plano pode retirar valores da DRE sem quebrar a gravação (`apps/finance/services/dre.py:162-170`, `:841-889`). |
| AUD-26 | **P3** | Confirmado por código | Há função residual que referencia o antigo `FinancialGroup.dre_type`. Atualmente não é o caminho principal, mas sinaliza dívida de migração e risco de reativação incorreta (`apps/finance/services/dre.py`). |

## 10. Estoque

### 10.1 Fluxos mapeados

- saldo atual materializado em `StockProduct.current_quantity`;
- razão de entradas/saídas em `StockMovement`;
- baixa automática na aprovação da OS e reversão na reabertura;
- entrada manual, importação XML/Sefaz e transferência entre oficinas;
- relatório por saldo atual e custo do catálogo.

### 10.2 Achados

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-27 | **P1** | Confirmado por código | Aprovação manual de movimento atualiza saldo sem `select_for_update` e sem impedir saída maior que o saldo. Aprovações concorrentes podem perder atualização e o saldo pode ficar negativo (`apps/stock/views.py:482-505`). |
| AUD-28 | **P1** | Confirmado por modelo/fluxo | `StockImport` não possui unicidade forte da chave da NF e os movimentos criados não guardam FK para a importação. O mesmo XML/NF pode ser importado mais de uma vez; o estado “importado” do cache é insuficiente como idempotência (`apps/stock/forms.py:883-963`; models de `stock`). |
| AUD-29 | **P1** | Confirmado por código | Excluir uma importação concluída subtrai saldo e remove movimentos financeiros, mas não remove/reverte as entradas de estoque porque não há vínculo. O `current_quantity` passa a divergir do razão; o `max(0)` ainda mascara quantidades já consumidas (`apps/stock/views.py:821-847`). |
| AUD-30 | **P1** | Confirmado por modelo | Quantidade é inteira em estoque e em itens de orçamento/OS, enquanto catálogo/XML suportam unidades como KG/LT e parsing decimal. Frações podem ser rejeitadas, arredondadas ou impossíveis de representar. |
| AUD-31 | **P2** | Confirmado por cálculo | Relatório de estoque calcula valor com saldo atual × `Product.cost_price` atual. Movimentos históricos também consultam custo atual em vez de snapshot. Alterar custo do produto reescreve economicamente o passado e reavalia todo o saldo sem método de custo médio/por lote (`apps/stock/reporting.py`; `apps/stock/models.py`). |
| AUD-32 | **P2** | Risco estrutural | Saldo materializado e razão não têm reconciliação obrigatória após toda escrita. O caminho de aprovação de OS usa transação e lock, mas importação, movimento manual, exclusão e possíveis escritas administrativas seguem garantias diferentes. |
| AUD-33 | **P3** | Confirmado por código | `StockMovement.stock_product` e `Service.shipping` aparecem declarados duas vezes nos respectivos models. A segunda declaração mascara a primeira; hoje os tipos são compatíveis, mas é uma fonte de divergência em migrations/manutenção. |

## 11. Fiscal

### 11.1 Estrutura encontrada

- solicitações e itens separados para NFe e NFSe;
- reserva de numeração/RPS, lotes, cancelamentos e documentos recebidos;
- camada unificada de `FiscalDocument`, vínculos, eventos e tentativas idempotentes;
- webhooks e comando de reconciliação com provider;
- lista de documentos emitidos e downloads de XML/PDF.

### 11.2 Achados

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-34 | **P1** | Confirmado por código | A emissão unificada reutiliza o ID guardado em sessão apenas pelo contexto da oficina e pode reatribuir a solicitação fiscal a outra OS, reescrevendo configuração/status, sem validar que a solicitação era da mesma OS (`apps/finance/views/emission.py:666-712`). Uma sessão antiga pode vincular documentos fiscais ao faturamento errado. |
| AUD-35 | **P1** | Risco estrutural | Não há unicidade geral de solicitação NFe/NFSe por OS/operação. Tentativas possuem chave de idempotência e documentos remotos têm unicidades úteis, mas múltiplas solicitações locais podem existir e inflar listagens ou reservar numeração repetidamente. |
| AUD-36 | **P2** | Confirmado por filtro | O período da lista de notas emitidas usa `request.criado_em`, não data de autorização/emissão do documento. Uma nota autorizada dias depois fica no período em que a solicitação nasceu (`apps/finance/views/issued_documents.py:181-215`). |
| AUD-37 | **P2** | Risco estrutural | Solicitação fiscal carrega oficina e OS sem constraint relacional de mesma oficina. O risco é coberto parcialmente pelas views, mas permanece para escrita direta e rotinas futuras. |

Pontos positivos: unicidade de UUID/chave de acesso, eventos, vínculos de documento e tentativas idempotentes reduzem duplicação no provider; cancelamento e estados incertos possuem serviços dedicados. Esses mecanismos devem ser usados como fonte canônica na reconciliação futura.

## 12. RH, folha e comissões

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-38 | **P1** | Confirmado por consulta | O resumo da lista de folha soma pagos usando somente `financial_movement`, vínculo legado OneToOne. A folha atual pode ter vários `financial_movements` componentizados; esses pagamentos e parciais são ignorados (`apps/finance/views/payroll.py:370-374`). |
| AUD-39 | **P1** | Confirmado por consulta | O relatório financeiro de folha também classifica pago pelo movimento legado, em vez de `payroll.status`, `paid_amount` e componentes. Contagem e total pago podem divergir dos próprios recibos/linhas de folha (`apps/finance/views/reports.py:568-607`). |
| AUD-40 | **P2** | Confirmado por cálculo | O quinto dia útil conta apenas segunda a sexta e ignora feriados (`apps/collaborators/models.py:137-152`), embora o módulo de custos possua dias trabalhados configuráveis. Vencimento pode diferir da prática legal/operacional. |
| AUD-41 | **P2** | Confirmado por filtro | Comissão usa `criado_em` quando há intervalo explícito e data de referência quando o filtro é mês/ano. O mesmo lançamento pode pertencer a períodos diferentes conforme o modo de consulta (`apps/finance/views/commissions.py`). |
| AUD-42 | **P2** | Risco estrutural | Salário, transporte e benefício não têm todas as constraints de não negatividade/coerência de vigência no banco. Forms podem proteger a UI, mas importações/admin/ORM podem gerar folha negativa ou benefício fora do vínculo. |

## 13. Agenda, checklist, quote e mensagens

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-43 | **P2** | Confirmado por consulta | Segmento de clientes por “valor de orçamento” agrupa e soma todos os itens de todos os orçamentos do cliente. O nome da anotação sugere máximo por orçamento, e o cálculo ignora a fronteira de cada orçamento e seus descontos (`apps/messaging/infrastructure/services/segment_query_builder.py:116-129`). Público de campanhas pode ser incorreto. |
| AUD-44 | **P2** | Confirmado por consulta | Regra de “última visita” usa criação da OS, não entrega/conclusão. Uma OS rascunho conta como visita e desloca segmentações de retorno (`apps/messaging/infrastructure/services/segment_query_builder.py`). |
| AUD-45 | **P3** | Risco estrutural | `Appointment.clean()` tem validações robustas, mas `save()` não chama `full_clean()`. Escritas diretas podem ignorar coerência e sobreposição verificadas no formulário (`apps/scheduling/models.py:136-240`). |
| AUD-46 | **P3** | Risco estrutural | Questionários/checklists dependem de ordenação e configuração mutável; sem snapshot integral, alterações em perguntas/templates podem mudar a interpretação histórica de respostas antigas. |

## 14. Dashboards, relatórios e indicadores

### 14.1 Inventário e rastreabilidade

| Tela/saída | Origem e filtros principais | Cálculo | Risco principal |
|---|---|---|---|
| Dashboard — carros no mês | `Budget` aprovado, oficina, mês/ano, somente orçamento raiz | contagem | “Carro” é aprovação comercial, não necessariamente entrega. |
| Garantia/cortesia | `Budget`/`WorkOrder`, tipos especiais e vínculos pai | contagem e taxa | numerador por OS e denominador por venda raiz não representam a mesma unidade. |
| Ticket médio | orçamentos/OS e `stored_total_amount` | soma ÷ contagem | total materializado pode estar obsoleto; coorte depende de status. |
| Projeção/faturamento/vendido | parcelas de OS por vencimento; OS rascunho/aprovada | soma | previsão de parcela é apresentada ao lado de venda/recebimento; não é liquidação. |
| Rentabilidade média | rentabilidade calculada por registro | média aritmética | não ponderada por receita; OS pequena e grande têm o mesmo peso. |
| Markup | itens/custos/preços do período | fórmula agregada | custo atual/snapshot e estágios podem divergir. |
| Taxa de aprovação | orçamento aprovado versus elegíveis | percentual | numerador e denominador têm exclusões diferentes (AUD-10). |
| A receber / pendentes | parcelas, status e período | soma | “anteriores” inclui futuro; flags de pagamento têm semântica ambígua. |
| Relatório de indicadores | configurações em `_INDICATOR_QUERIES` | mesmos cards em modal/PDF | herda filtros do dashboard; PDF não corrige a fonte. |
| Orçamentos por status | `Budget`, oficina/status/filtros | linhas e soma de `stored_total_amount` | total obsoleto e múltiplas OS por orçamento. |
| OS por status | `WorkOrder`, oficina/status/filtros | linhas e soma de total materializado | aprovação/entrega mescladas; total obsoleto. |
| Visão financeira | `FinancialMovement`, direção, pago, vencimento | cards e lista | pago pode significar parcela gerada; conciliação não é uniforme. |
| Fluxo de caixa | movimentos pagos e conciliados | entradas - saídas | universo propositalmente menor que visão geral; reversões precisam paridade. |
| DRE HTML/PDF/Excel | parcelas de OS + movimentos + custos de itens | linhas de resultado | AUD-22 a AUD-25. Saídas compartilham serviço, portanto tendem a divergir juntas. |
| Comissões HTML/PDF | `CommissionEntry`, colaborador e datas | base, percentual, pago | critério temporal muda pelo tipo de filtro. |
| Folha/lista/recibo | `CollaboratorPayroll`, itens e movimentos | previsto, parcial, pago | resumos usam vínculo legado; detalhe usa modelo atual. |
| Estoque HTML/PDF/Excel | `StockProduct`, saldo atual e custo atual | quantidade × custo | razão pode divergir; histórico é reavaliado por custo atual. |
| Movimentações de estoque | `StockMovement` | entradas/saídas/valor | ausência de snapshot de custo e vínculos de importação. |
| Documentos emitidos | `NfeRequest`/`NfseRequest` e último item | lista/download | período por criação da solicitação; solicitações duplicáveis. |
| Histórico de cliente/veículo | budgets e primeira OS vinculada | linha do tempo | `.first()` esconde OS duplicada; status atual pode reclassificar passado. |
| Segmentos de mensagens | subqueries de budget/OS/cliente | regras de público | valor acumulado chamado de orçamento e visita por criação. |

### 14.2 Outros riscos de indicador

| ID | Prioridade | Tipo | Achado, impacto e evidência |
|---|---|---|---|
| AUD-47 | **P2** | Confirmado por cálculo | Rentabilidade média é média simples dos percentuais individuais, não `lucro total / receita total`. Pode diferir materialmente da rentabilidade consolidada (`apps/core/infrastructure/services/dashboard_query_service.py:950-956`). |
| AUD-48 | **P2** | Confirmado por cálculo | Taxa de retorno em garantia conta OS de garantia e vendas raiz em unidades diferentes e inclui repetição de retornos. O indicador não mede claramente “clientes”, “veículos”, “vendas” ou “eventos” (`apps/core/infrastructure/services/dashboard_query_service.py:777-797`). |
| AUD-49 | **P2** | Confirmado por parsing | Parâmetros numéricos de mês/ano não são validados de forma uniforme. Mês fora de 1–12 ou texto em relatórios financeiros pode gerar erro 500 em vez de filtro inválido controlado. |

## 15. Regras de consistência propostas

Estas validações devem ser implementadas primeiro como consultas/auditoria somente leitura. Somente depois de medir incidência deve-se decidir por constraint, serviço, comando de correção ou alerta.

### 15.1 Oficina e dados mestres

1. Para toda FK entre entidades com oficina, validar `filho.workshop_id = relacionado.workshop_id`.
2. Para papel/membro, validar `user.account_id = workshop.account_id = role.account_id` quando aplicável.
3. Canonicalizar CPF/CNPJ/placa/código/email e procurar duplicados por oficina sobre a forma canônica.
4. Validar que veículo pertence ao cliente do orçamento/OS/agendamento.
5. Validar vigência, valor não negativo e oficina dos cadastros financeiros, benefícios e colaboradores.

### 15.2 Orçamento e OS

1. `Budget.stored_total_amount = round(sum(item.total) + fretes - descontos, 2)` conforme a regra canônica.
2. `WorkOrder.stored_total_amount = round(sum(item.total) + fretes - descontos, 2)`.
3. `WorkOrder.stored_paid_amount = sum(payment_method.amount)` — renomear conceitualmente se isso for valor parcelado, não liquidado.
4. Para OS sincronizada, comparar itens, quantidades, snapshots, descontos e total com o orçamento de origem.
5. Garantir no máximo uma OS principal por orçamento.
6. OS aprovada com produto deve ter uma saída aprovada por item/quantidade, sem aceitar apenas a existência de um movimento qualquer.
7. OS rascunho/reaberta não deve conservar `delivered_at`, salvo se houver estado histórico separado e explicitamente desejado.

### 15.3 Estoque

1. Para cada produto/oficina: `saldo atual = saldo inicial + entradas aprovadas - saídas aprovadas ± transferências/reversões`.
2. Toda saída de OS deve apontar à OS e corresponder a item e quantidade; toda reversão deve apontar a um único original.
3. Toda importação concluída deve possuir chave fiscal única e conjunto rastreável de movimentos; exclusão deve estornar, não apenas alterar saldo.
4. Transferência deve ter saída e entrada de mesma quantidade, produto canônico e operação, em oficinas distintas autorizadas.
5. Definir política explícita para saldo negativo e concorrência.
6. Definir unidade/precisão decimal por produto e proibir conversão silenciosa.
7. Congelar custo no movimento e definir método de valoração: custo médio, FIFO, lote ou custo padrão.

### 15.4 Financeiro e DRE

1. Separar matematicamente `previsto`, `vencido`, `pago` e `conciliado`.
2. Para cada OS: `total parcelado = soma das parcelas`; `total recebido = soma de liquidações reais`; `saldo a receber = total faturado - recebido - estornado`.
3. Um movimento pai de OS deve ser único; filhos devem somar o pai; uma parcela não pode ser duplicada.
4. Cada reversão deve ter um único original e valor/direção coerentes; o original revertido não pode entrar em totais correntes.
5. Validar `amount >= 0`, direção presente, datas necessárias e oficina coerente.
6. Usar a mesma dimensão temporal selecionada em todas as linhas da DRE: competência, vencimento ou pagamento.
7. Identidades mínimas da DRE:
   - `receita líquida = receita bruta - deduções/impostos/devoluções`;
   - `lucro bruto = receita líquida - CMV - CSP`;
   - `resultado operacional = lucro bruto + outras receitas operacionais - despesas operacionais`;
   - `resultado antes dos tributos = resultado operacional + resultado financeiro`;
   - `resultado líquido = resultado antes dos tributos - tributos sobre resultado`.
8. Grupos de DRE devem ser identificados por código/tipo imutável, não nome editável.

### 15.5 Fiscal

1. Solicitação, OS, destinatário e oficina devem pertencer ao mesmo tenant.
2. Uma tentativa idempotente deve resolver sempre para a mesma solicitação/operação/OS.
3. Chave de acesso/UUID/número+serie devem ser únicos no escopo fiscal aplicável.
4. Total de itens + frete - desconto + tributos deve reconciliar com total autorizado.
5. Rateio NFe/NFSe deve reconciliar com produtos/serviços da OS sem dupla tributação ou item omitido.
6. Cancelado/inutilizado/rejeitado não entra em faturamento emitido; documento autorizado entra pela data fiscal definida, não pela criação do wizard.
7. Documento local, evento/webhook e estado no provider devem convergir; estados incertos devem ficar explicitamente pendentes.

### 15.6 Folha e comissão

1. `folha total = salário/componente base + benefícios + transporte + comissões ± ajustes`.
2. Soma dos movimentos componentizados deve igualar o total da folha.
3. `paid_amount` deve vir de liquidação real; `status = PAID` somente quando pago >= total, `PARTIAL` entre zero e total.
4. Comissão: `valor = base elegível × percentual vigente`, com referência temporal única e snapshot da regra.
5. Vencimento por quinto dia útil deve usar calendário oficialmente definido pela oficina/região.

### 15.7 Relatórios e dashboards

1. Numerador e denominador devem compartilhar oficina, período, tipo e status.
2. “Mês anterior” deve usar limite `< primeiro dia do mês selecionado`, não exclusão do mês.
3. Média percentual gerencial deve declarar se é simples ou ponderada.
4. “Vendido”, “faturado”, “recebido”, “pago”, “conciliado”, “entregue” e “aprovado” devem ter definições distintas e visíveis.
5. Tela, PDF e Excel devem reutilizar a mesma query/DTO e o mesmo instante de corte.
6. Todo filtro de data deve validar intervalo e dimensão temporal; todo parâmetro mês deve aceitar apenas 1–12.

## 16. Consultas de incidência recomendadas para a próxima etapa

Executar em réplica ou transação read-only e registrar contagem, valor financeiro e amostra por oficina:

1. OS aprovadas com item de produto sem movimentos de saída correspondentes.
2. OS com movimento parcial: quantidade de saída diferente da quantidade dos itens.
3. Orçamentos com mais de uma OS.
4. Orçamentos/OS cujo total materializado difere do total recalculado.
5. OS rascunho com `delivered_at` preenchido.
6. Relações cujo `workshop_id` diverge entre pai e filho, cobrindo todos os FKs críticos.
7. Produtos cujo saldo materializado difere do razão de movimentos aprovados.
8. Importações repetidas por chave, número/série/fornecedor e hash do XML.
9. Importações removidas com movimentos de entrada órfãos.
10. Movimentos financeiros de OS duplicados, pais com soma diferente dos filhos e parcelas sem pai.
11. Movimentos pagos mas não conciliados que entram em cards de “pago”.
12. Originais revertidos ainda incluídos em relatórios e reversões órfãs/duplicadas.
13. DRE recalculada em três bases — competência, vencimento e caixa — para quantificar a diferença.
14. Folhas com componentes cuja soma difere do total; folhas pagas nos componentes mas pendentes no vínculo legado.
15. Solicitações fiscais múltiplas por OS/operação e solicitações/documentos associados a oficina diferente.
16. Notas cuja data da solicitação e data de autorização pertencem a períodos diferentes.
17. Clientes/fornecedores/produtos/serviços duplicados após normalização.
18. Segmentos de mensagem comparando maior orçamento individual versus soma histórica.

## 17. Ordem recomendada de tratamento após a medição

1. **Conter P0:** tornar aprovação+estoque indivisível e bloquear relações cross-workshop.
2. **Restabelecer fontes canônicas:** reconciliar saldo/razão, totais materializados e unicidade orçamento/OS.
3. **Separar eventos financeiros:** previsão, faturamento, liquidação e conciliação.
4. **Corrigir DRE e semântica temporal:** fórmulas, status, dimensões de data e grupos imutáveis.
5. **Reconciliar importação/fiscal:** idempotência, vínculos e período de emissão/autorização.
6. **Migrar relatórios de folha:** abandonar dependência do vínculo financeiro legado.
7. **Uniformizar indicadores:** coortes, definição dos rótulos, médias ponderadas e períodos anteriores.
8. **Adicionar auditorias recorrentes:** checks diários de invariantes e alertas com contagem/valor por oficina.

## 18. Conclusão

O maior risco sistêmico não está em uma única fórmula isolada, mas na existência de várias representações do mesmo fato: total calculado e total armazenado; parcela e movimento; saldo e razão; aprovação e entrega; solicitação e documento fiscal; folha e movimentos legados/componentizados. Enquanto essas representações não tiverem uma fonte canônica e reconciliação obrigatória, relatórios diferentes poderão estar internamente corretos em suas próprias queries e ainda assim divergir entre si.

A próxima etapa deve ser exclusivamente de **mensuração em dados**, começando pelos 18 testes de incidência acima. Nenhuma correção ou migração deve ser aplicada antes de produzir backup, contagem por oficina, valor financeiro afetado e plano de reconciliação reversível.
