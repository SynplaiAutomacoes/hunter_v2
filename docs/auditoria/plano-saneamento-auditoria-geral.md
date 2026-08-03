# Plano de saneamento da Auditoria Geral de Integridade

**Fase:** 5.0 — priorização dos achados  
**Data:** 01/08/2026  
**Documento de origem:** `docs/auditoria/auditoria-geral-integridade-sistema.md`  
**Escopo:** classificação e planejamento; nenhuma correção, migration ou alteração de código

## 1. Decisão executiva

Os 49 achados permanecem válidos como constatações de código, gaps de integridade ou riscos conceituais. Isso não significa que todos já tenham produzido registros incorretos. A priorização separa três perguntas:

1. **a condição existe no sistema?** — validada pelo código, schema ou consulta;
2. **há incidência em dados?** — medida somente na base PostgreSQL local de desenvolvimento;
3. **qual é a urgência real?** — avaliada separadamente sob a ótica técnica e de negócio.

A ordem recomendada começa por impedir novas inconsistências em OS/estoque e fronteiras de oficina. Em seguida, deve reconciliar totais já divergentes, redefinir a semântica financeira/DRE e então tratar estoque, fiscal, folha e indicadores.

Não se recomenda iniciar correções simultâneas em todos os módulos. Os fluxos compartilham os mesmos fatos econômicos, e corrigir uma tela antes de definir a fonte canônica apenas transfere a divergência para outro relatório.

## 2. Evidência disponível

### 2.1 Escopo da amostra de dados

Foi feita consulta **somente leitura** à base PostgreSQL local configurada no ambiente. Ela contém:

| Entidade | Registros |
|---|---:|
| Oficinas | 16 |
| Orçamentos | 20 |
| Ordens de serviço | 14 |
| Produtos em estoque | 144 |
| Movimentos de estoque | 8 |
| Importações de estoque | 12, sendo 4 concluídas |
| Movimentos financeiros | 35 |
| Folhas | 4 |
| Solicitações NFe/NFSe | 0 |

Essa base é pequena, local e não representa produção. Evidência local positiva aumenta a confiança de que o problema se materializa; evidência local zero **não elimina** o risco.

### 2.2 Resultados relevantes da amostra

| Validação somente leitura | Resultado |
|---|---:|
| Orçamentos com total armazenado diferente do recalculado | **7 de 20** |
| OS com total armazenado diferente do recalculado | **8 de 14** |
| Movimentos de OS pagos e não conciliados | **4** |
| Grupos duplicados de movimento por parcela de OS | **1** |
| Usuários membros de mais de uma oficina | 1 |
| Desses usuários, com perfil de colaborador global | 0 |
| OS aprovada com produto e nenhuma baixa de estoque | 0 |
| OS aprovada com quantidade total de baixa divergente | 0 |
| Orçamentos com mais de uma OS | 0 |
| OS rascunho com `delivered_at` | 0 |
| Cruzamentos de oficina nas relações principais consultadas | 0 |
| Produtos com saldo negativo | 0 |
| Chaves de importação duplicadas | 0 |
| Movimentos financeiros com valor negativo ou direção ausente | 0 |
| Movimentos financeiros de reversão | 0 |
| Folhas no modelo componentizado sem vínculo legado | 0 |

O teste bruto `saldo = entradas - saídas` divergiu para 43 produtos, mas o modelo não registra de forma inequívoca o saldo inicial. Portanto, esse resultado prova a **impossibilidade atual de reconciliação integral pelo razão**, não prova, isoladamente, que 43 saldos estejam errados.

### 2.3 Legenda da matriz

**Validação**

- **PC:** problema confirmado — a lógica executada produz a condição descrita.
- **GE:** gap estrutural confirmado — falta uma garantia; a ocorrência de dado inválido depende do uso.
- **RC:** risco conceitual confirmado — a definição do indicador/evento é ambígua ou incompatível com o rótulo.
- **DM:** dívida de manutenção confirmada — baixo impacto direto no estado atual.

**Evidência de dados**

- **L+:** incidência encontrada na base local.
- **L0:** incidência não encontrada na base local consultada.
- **LI:** base local insuficiente ou validação inconclusiva.
- **NA:** a falha é determinística na fórmula/query e não precisa de um registro inválido para existir.
- **PR:** produção/staging ainda precisa ser consultada.

**Impacto**

- **F:** financeiro — pode alterar valores ou produzir perda financeira.
- **O:** operacional — pode impedir ou desorganizar o processo.
- **G:** gerencial — pode produzir indicador/relatório errado.
- **D:** dados — pode corromper vínculo, saldo ou histórico.
- Intensidade: **A** alta, **M** média, **B** baixa, **—** não material.

## 3. Matriz dos 49 achados

| ID | Domínio | Validação e evidência técnica | Evidência de dados / dependência | Impacto F/O/G/D | Prioridade técnica / negócio | Recomendação | Ordem |
|---|---|---|---|---|---|---|---:|
| AUD-01 | Permissões | **GE.** Não existe uma invariante geral de mesma oficina entre FKs correlatas; `Appointment.clean()` é uma proteção local, não global. | **L0/PR.** Quatro relações críticas consultadas deram zero. Depende de escrita direta, importação ou fluxo sem validação. | F:A O:A G:A D:A | **P0 / P0** | Inventariar todas as FKs com oficina; medir produção; centralizar validação; só depois adicionar barreiras no serviço e banco onde possível. | 2 |
| AUD-02 | RH/Folha | **GE.** `WorkshopCollaborator.user` é OneToOne global, incompatível com colaborador por oficina. | **LI/PR.** Há 1 usuário multi-oficina, mas nenhum conflito local de colaborador. Depende de o mesmo usuário trabalhar em duas oficinas. | F:M O:M G:M D:M | **P1 / P2** | Confirmar regra comercial; se colaborador for por oficina, planejar relação por oficina e migração de vínculos sem duplicar folha/comissão. | 33 |
| AUD-03 | Arquitetura | **GE.** Normalização e unicidade canônica não são uniformes entre model, form e importação. | **LI/PR.** Requer varredura normalizada de CPF/CNPJ/placa/código/nome por oficina. | F:B O:M G:M D:M | **P2 / P2** | Definir formato canônico por entidade, medir colisões e aplicar normalização numa única fronteira antes de reforçar unicidade. | 38 |
| AUD-04 | Financeiro | **PC.** Constraint de conta bancária omite agência. | **LI/PR.** Há 3 contas locais, sem tentativa de cadastrar colisão. Depende de números iguais em agências diferentes. | F:B O:M G:B D:B | **P2 / P3** | Validar com negócio a identidade da conta; incluir agência na chave lógica apenas após detectar colisões existentes. | 39 |
| AUD-05 | Permissões | **GE.** Membro, usuário, oficina e papel não têm garantia completa de pertencer à mesma conta. | **LI/PR.** Não foi feita matriz integral de IAM local; ocorrência depende de associação administrativa inconsistente. | F:M O:A G:M D:A | **P2 / P1** | Auditar todas as associações IAM; bloquear atribuição cross-account na camada de aplicação e criar check recorrente. | 34 |
| AUD-06 | Arquitetura | **GE.** Checklist, perguntas e configurações não têm unicidade semântica/ordenação forte em todos os pontos. | **LI/PR.** Depende de cadastro repetido e uso do template. | F:— O:M G:B D:M | **P3 / P3** | Definir identidade e ordenação funcional; detectar duplicatas antes de qualquer constraint. | 45 |
| AUD-07 | Comercial | **PC.** Exclusão em lote ignora callbacks que recompõem `stored_total_amount`. | **L+/PR.** Há 7/20 orçamentos com total armazenado divergente. A amostra confirma o sintoma, não atribui todos os casos a essa rota específica. | F:A O:M G:A D:A | **P1 / P1** | Congelar correção automática; primeiro exportar diferenças e valores. Depois unificar mutações de item e recomposição transacional do total. | 4 |
| AUD-08 | Comercial | **PC.** Atualização de snapshot de kit por `update()` pode não recompor o total do orçamento/OS. | **L+/PR.** 7 orçamentos e 8 OS apresentam drift; causa individual ainda deve ser rastreada. Depende de edição de kit/item. | F:A O:M G:A D:A | **P1 / P1** | Definir um único serviço de recálculo/sincronização e registrar origem da alteração; reconciliar casos existentes com relatório antes/depois. | 5 |
| AUD-09 | Comercial | **GE.** `WorkOrder.budget` não é único e `get_or_create` não elimina corrida concorrente. | **L0/PR.** Zero orçamento com múltiplas OS localmente. Depende de concorrência ou escrita direta. | F:A O:A G:A D:A | **P1 / P1** | Medir produção; definir OS principal por orçamento; eliminar duplicatas com regra de negócio e então garantir unicidade. | 19 |
| AUD-10 | Comercial | **PC.** Taxa de aprovação usa numerador e denominador de coortes diferentes. | **NA/PR.** A fórmula é inconsistente sempre que há garantia/cortesia aprovada; magnitude depende dos dados. | F:B O:B G:A D:B | **P2 / P2** | Formalizar coorte de conversão e usar exatamente os mesmos filtros no numerador/denominador; criar cenários de borda. | 28 |
| AUD-11 | Comercial | **RC.** Conversão é reconstruída do status atual, sem evento comercial imutável. | **LI/PR.** Depende de reabertura/cancelamento posterior e do conceito escolhido para histórico. | F:B O:B G:A D:M | **P2 / P2** | Definir o evento “convertido” e sua data; decidir se cancelamento reescreve ou complementa o histórico. | 40 |
| AUD-12 | Ordem de Serviço | **PC.** Exceção na baixa de estoque é suprimida após a aprovação da OS. | **L0/PR.** Nenhuma OS aprovada sem baixa na amostra; risco depende de falha no serviço/caminho alternativo. | F:A O:A G:A D:A | **P0 / P0** | Primeiro impedir novas aprovações não atômicas; preservar erro e rollback; depois localizar e reconciliar OS históricas. | 1 |
| AUD-13 | Ordem de Serviço | **PC.** Idempotência considera “existe alguma saída”, sem conferir todos os itens/quantidades. | **L0/PR.** Zero divergência na amostra. Depende de baixa parcial ou edição posterior. | F:A O:A G:A D:A | **P1 / P1** | Trocar existência por reconciliação item a item; definir política para diferença positiva/negativa e reversões. | 3 |
| AUD-14 | Ordem de Serviço | **PC.** Reabertura não limpa `delivered_at`. | **L0/PR.** Zero OS local nesse estado. Depende de reabertura de OS entregue. | F:M O:M G:A D:M | **P1 / P1** | Separar data de entrega de histórico de transição; definir restauração/reversão antes de limpar dados antigos. | 20 |
| AUD-15 | Ordem de Serviço | **RC.** Aprovação preenche data de entrega e combina eventos operacionais diferentes. | **NA/PR.** O comportamento existe em toda aprovação; impacto depende de haver execução posterior à aprovação. | F:M O:A G:A D:M | **P1 / P1** | Acordar máquina de estados e datas canônicas: aprovado, em execução, faturado, concluído e entregue. | 21 |
| AUD-16 | Arquitetura | **GE.** Budget e WorkOrder duplicam fórmulas e estruturas de item/kit/desconto. | **L+/PR.** Drift de totais demonstra divergência entre representações, embora não prove qual fórmula divergiu. | F:A O:M G:A D:A | **P2 / P1** | Definir componente de cálculo canônico e testes de contrato entre orçamento e OS; evitar refatoração ampla antes da reconciliação. | 41 |
| AUD-17 | Financeiro | **PC.** Parcelas previstas de OS viram movimentos `is_paid=True`. | **L+/PR.** Há 4 movimentos de OS pagos e não conciliados. Depende da interpretação dos relatórios, não da existência da flag. | F:A O:M G:A D:A | **P1 / P1** | Definir estados separados para previsto, faturado, liquidado e conciliado; mapear todos os consumidores antes de migrar semântica. | 6 |
| AUD-18 | Financeiro | **PC.** Visão geral e fluxo de caixa usam critérios diferentes para “pago”. | **L+/PR.** Os mesmos 4 movimentos podem entrar no primeiro universo e ficar fora do segundo. | F:A O:M G:A D:M | **P1 / P1** | Criar glossário e DTOs explícitos por visão; renomear cards quando a diferença for intencional. | 14 |
| AUD-19 | Financeiro | **GE + L+.** Faltam constraints completas para movimentos de OS; não há unicidade por parcela. | **L+/PR.** Há 1 agrupamento duplicado por `workorder_payment`; valores negativos/direção ausente deram zero. | F:A O:A G:A D:A | **P1 / P1** | Investigar o duplicado e impacto financeiro; definir chave idempotente; limpar antes de adicionar qualquer constraint. | 13 |
| AUD-20 | Financeiro | **GE.** Consultas tratam original e reversão com filtros diferentes. | **LI/PR.** Não há reversões locais; precisa de cenários de estorno e amostra real. | F:A O:M G:A D:A | **P2 / P1** | Definir ledger de reversão único e contrato de inclusão para extrato, cards, caixa e DRE. | 25 |
| AUD-21 | Relatórios/Dashboards | **PC.** “Meses anteriores” é calculado como qualquer mês diferente, incluindo futuro. | **NA/PR.** Falha determinística quando existem parcelas futuras fora do mês selecionado. | F:M O:B G:A D:B | **P2 / P2** | Trocar o conceito por limite temporal estrito e testar virada de ano/futuro. | 29 |
| AUD-22 | Financeiro | **PC.** Identidades e rótulos da DRE não correspondem: “receita líquida” subtrai CMV/CSP e resultado operacional ignora o resultado bruto. | **NA/PR.** A fórmula é determinística; valores locais/produção precisam ser recalculados para medir diferença. | F:A O:M G:A D:M | **P1 / P1** | Homologar estrutura contábil com responsável financeiro; criar equações canônicas e comparar DRE antiga/nova por período. | 7 |
| AUD-23 | Financeiro | **PC.** Filtro pago/não pago não é aplicado à receita bruta baseada em parcelas. | **NA/PR.** Toda consulta com `tipo_data` sofre o problema quando há parcelas. | F:A O:M G:A D:B | **P1 / P1** | Escolher dimensão temporal e propagá-la a todas as linhas; proibir mistura silenciosa de competência, vencimento e caixa. | 8 |
| AUD-24 | Financeiro | **PC.** Receita aceita OS rascunho/aprovada por vencimento; custos exigem entrega. | **NA/PR.** A diferença ocorre quando a OS ainda não foi entregue ou datas pertencem a períodos distintos. | F:A O:M G:A D:M | **P1 / P1** | Definir coorte única de reconhecimento e datas para receita/CMV/CSP; reconciliar períodos anteriores. | 9 |
| AUD-25 | Financeiro | **PC.** DRE resolve grupos por nomes editáveis exatos. | **LI/PR.** Depende de renomeação/reorganização do plano; precisa comparar nomes reais de produção. | F:A O:M G:A D:M | **P2 / P1** | Criar identidade semântica imutável para grupos e relatório de grupos não mapeados. | 26 |
| AUD-26 | Arquitetura | **DM.** Função residual referencia campo antigo de DRE e não é caminho principal. | **NA.** Dívida existe no código; não há incidência funcional atual identificada. | F:B O:B G:B D:— | **P3 / P3** | Remover ou adaptar somente após cobertura de testes e conclusão da nova DRE. | 49 |
| AUD-27 | Estoque | **PC.** Aprovação manual altera saldo sem lock pessimista e sem política contra estoque negativo. | **L0/PR.** Nenhum saldo negativo local. Depende de concorrência ou saída maior que saldo. | F:A O:A G:A D:A | **P1 / P1** | Unificar mutações de saldo num serviço transacional; definir bloqueio, política de negativo e mensagem operacional. | 11 |
| AUD-28 | Estoque | **GE.** Importação não tem idempotência forte por NF/hash nem vínculo entre importação e movimentos. | **L0/PR.** Há 12 importações, 4 concluídas e zero chave duplicada local. Depende de reenvio/reprocessamento. | F:A O:A G:A D:A | **P1 / P1** | Definir identidade fiscal/hash e rastreabilidade da importação; medir duplicados antes de bloquear. | 12 |
| AUD-29 | Estoque | **PC.** Exclusão de importação altera saldo/financeiro sem reverter as entradas de estoque correspondentes. | **LI/PR.** Há 4 importações concluídas, mas sem vínculo não é possível provar exclusões históricas pelo razão. | F:A O:A G:A D:A | **P1 / P1** | Suspender conceitualmente exclusão destrutiva; modelar estorno rastreável e reconciliar importações concluídas com saldo/movimentos. | 10 |
| AUD-30 | Estoque | **GE.** Quantidades inteiras conflitam com KG/LT e XML decimal. | **LI/PR.** Depende de a oficina comercializar/importar frações; requer análise de unidades e payloads reais. | F:A O:A G:M D:A | **P1 / P2** | Levantar unidades usadas e regra de arredondamento; definir precisão por produto antes de converter campos/dados. | 22 |
| AUD-31 | Estoque | **RC.** Relatório e movimento histórico usam custo atual, sem snapshot/método de valoração. | **LI/PR.** Depende de variação de custo; precisa comparar histórico de compras com custo atual. | F:A O:M G:A D:A | **P2 / P1** | Homologar custo médio/FIFO/padrão; congelar custo por movimento e recalcular relatórios comparativos. | 27 |
| AUD-32 | Estoque | **GE.** Saldo materializado e razão não têm reconciliação obrigatória em todos os fluxos. | **LI/PR.** 43 saldos diferem de entradas-saídas assumindo saldo inicial zero; como não há abertura canônica, o teste é inconclusivo e confirma a lacuna de rastreabilidade. | F:A O:A G:A D:A | **P2 / P1** | Criar conceito de saldo de abertura e consulta de reconciliação; só então medir e corrigir divergências reais. | 23 |
| AUD-33 | Arquitetura | **DM.** Campos são declarados duas vezes em models, com mascaramento da primeira definição. | **NA.** Existe no código; não foi observada diferença de schema funcional. | F:— O:B G:— D:B | **P3 / P3** | Remover duplicidade em mudança isolada, depois de comparar estado de migrations/model. | 48 |
| AUD-34 | Fiscal | **PC.** ID de solicitação fiscal em sessão pode ser reutilizado e reatribuído a outra OS. | **LI/PR.** Base local não possui NFe/NFSe; depende de sessão antiga e retomada em outra OS. | F:A O:A G:A D:A | **P1 / P1** | Vincular sessão à oficina+OS+operação; impedir reatribuição de solicitação emitida/terminal; auditar produção. | 17 |
| AUD-35 | Fiscal | **GE.** Não há unicidade geral de solicitação por OS/operação. | **LI/PR.** Zero solicitações locais; incidência só pode ser medida em staging/produção. | F:A O:A G:A D:A | **P1 / P1** | Definir chave idempotente de negócio e estados que permitem nova tentativa; reconciliar duplicatas antes de constraint. | 18 |
| AUD-36 | Fiscal | **PC.** Lista de emitidos filtra criação da solicitação, não autorização/emissão. | **NA/PR.** A query é determinística; efeito depende de autorização em dia/período diferente. | F:M O:M G:A D:M | **P2 / P2** | Definir data fiscal canônica e expor separadamente solicitação, autorização e cancelamento. | 32 |
| AUD-37 | Fiscal | **GE.** Solicitação e OS repetem oficina sem garantia relacional. | **LI/PR.** Não há dados fiscais locais; depende de escrita fora das views protegidas. | F:A O:A G:A D:A | **P2 / P1** | Incluir no programa geral de integridade cross-workshop; auditar antes de bloquear. | 24 |
| AUD-38 | RH/Folha | **PC.** Resumo da folha usa somente o vínculo financeiro legado. | **LI/PR.** As 4 folhas locais têm vínculo legado e nenhuma usa movimentos componentizados; cenário novo não está representado. | F:A O:M G:A D:M | **P1 / P1** | Tornar `paid_amount/status` ou componentes a fonte canônica; comparar resumo, detalhe e recibo. | 15 |
| AUD-39 | RH/Folha | **PC.** Relatório financeiro de folha também ignora componentes/parcelas atuais. | **LI/PR.** Mesma limitação da amostra: nenhuma folha componentizada local. | F:A O:M G:A D:M | **P1 / P1** | Reutilizar o mesmo DTO/fonte canônica do AUD-38 em tela, relatório e recibo. | 16 |
| AUD-40 | RH/Folha | **PC.** Quinto dia útil considera apenas segunda a sexta e ignora feriados. | **L+/PR.** 38 colaboradores locais usam essa regra; divergência depende do calendário do mês/localidade. | F:M O:A G:B D:M | **P2 / P1** | Homologar regra jurídica/operacional e fonte de feriados; gerar comparação de vencimentos antes de alterar. | 36 |
| AUD-41 | RH/Folha | **PC.** Comissão muda a dimensão de data conforme o tipo de filtro. | **LI/PR.** Não há lançamentos locais de comissão; depende de datas de criação/referência diferentes. | F:A O:M G:A D:M | **P2 / P1** | Definir competência única da comissão e aplicar a todos os filtros/saídas. | 35 |
| AUD-42 | RH/Folha | **GE.** Valores/vigências de remuneração e benefícios não têm todas as garantias no banco. | **LI/PR.** Depende de escrita fora dos forms; requer consulta de negativos e vigências em produção. | F:A O:M G:M D:A | **P2 / P2** | Medir dados inválidos; centralizar validação e só depois considerar checks de banco. | 37 |
| AUD-43 | Relatórios/Dashboards | **PC.** Segmento por “valor de orçamento” usa soma histórica do cliente, não maior orçamento individual. | **NA/PR.** A query produz essa semântica sempre; impacto depende do uso do segmento. | F:M O:M G:M D:B | **P2 / P2** | Confirmar intenção do produto; renomear para acumulado ou calcular máximo por orçamento com total/desconto canônico. | 42 |
| AUD-44 | Relatórios/Dashboards | **PC.** “Última visita” usa criação da OS, inclusive rascunho. | **NA/PR.** O erro ocorre quando criação e entrega diferem ou a OS não é executada. | F:B O:M G:M D:M | **P2 / P2** | Usar evento operacional homologado — conclusão/entrega — e definir tratamento de OS cancelada. | 43 |
| AUD-45 | Arquitetura | **GE.** `Appointment.save()` não força `full_clean()`, permitindo que escrita direta ignore validações. | **LI/PR.** Depende de admin, ORM, importação ou serviço que não use form. | F:B O:M G:B D:M | **P3 / P3** | Garantir validação no serviço de agenda e adicionar auditoria de sobreposição/coerência; evitar `full_clean` indiscriminado sem avaliar performance. | 46 |
| AUD-46 | Arquitetura | **GE.** Histórico de checklist/questionário pode depender de configuração mutável sem snapshot integral. | **LI/PR.** Depende de editar/remover template já respondido. | F:— O:M G:M D:A | **P3 / P2** | Definir quais textos/opções devem ser congelados por resposta e preservar versão histórica. | 47 |
| AUD-47 | Relatórios/Dashboards | **PC.** Rentabilidade usa média simples de percentuais, não rentabilidade consolidada ponderada. | **NA/PR.** Sempre diverge quando OS têm receitas diferentes e margens distintas. | F:M O:B G:A D:B | **P2 / P2** | Homologar indicador simples versus ponderado; nomear claramente e manter fórmula reproduzível. | 30 |
| AUD-48 | Relatórios/Dashboards | **RC.** Retorno em garantia mistura OS/eventos com vendas raiz no denominador. | **NA/PR.** Magnitude depende de retornos repetidos e vínculos pai. | F:M O:M G:A D:B | **P2 / P2** | Escolher unidade — venda, veículo, cliente ou evento — e usar a mesma nos dois lados. | 31 |
| AUD-49 | Relatórios/Dashboards | **PC.** Mês/ano não são validados uniformemente e podem gerar erro 500. | **NA.** Reproduzível com parâmetro fora da faixa/texto; não depende de dado específico. | F:— O:M G:B D:— | **P2 / P3** | Criar parser compartilhado e resposta controlada; cobrir 0, 13, texto e virada de ano. | 44 |

## 4. Agrupamento por domínio

| Domínio | Achados | Quantidade | Foco |
|---|---|---:|---|
| Financeiro | AUD-04, 17–20, 22–25 | 9 | Semântica de pagamento, movimentos, reversões e DRE. |
| Comercial | AUD-07–11 | 5 | Totais, sincronização orçamento/OS e conversão. |
| Ordem de Serviço | AUD-12–15 | 4 | Aprovação, baixa, reabertura e estados operacionais. |
| Estoque | AUD-27–32 | 6 | Concorrência, importação, razão, quantidade e custo. |
| Fiscal | AUD-34–37 | 4 | Idempotência, vínculo com OS/oficina e período fiscal. |
| RH/Folha | AUD-02, 38–42 | 6 | Multi-oficina, componentes, comissão e vencimento. |
| Relatórios/Dashboards | AUD-21, 43, 44, 47–49 | 6 | Coortes, datas, médias e resiliência de filtro. |
| Permissões | AUD-01, 05 | 2 | Isolamento de oficina/conta e coerência de papéis. |
| Arquitetura | AUD-03, 06, 16, 26, 33, 45, 46 | 7 | Fontes canônicas, normalização, histórico e dívida estrutural. |
| **Total** |  | **49** |  |

## 5. Prioridade consolidada

### 5.1 Prioridade técnica

Mantém a classificação da auditoria original:

| Prioridade | Quantidade | Achados |
|---|---:|---|
| P0 | 2 | AUD-01, AUD-12 |
| P1 | 21 | AUD-02, 07–09, 13–15, 17–19, 22–24, 27–30, 34, 35, 38, 39 |
| P2 | 21 | AUD-03–05, 10, 11, 16, 20, 21, 25, 31, 32, 36, 37, 40–44, 47–49 |
| P3 | 5 | AUD-06, 26, 33, 45, 46 |

### 5.2 Prioridade de negócio

| Prioridade | Quantidade | Achados |
|---|---:|---|
| P0 | 2 | AUD-01, AUD-12 |
| P1 | 28 | AUD-05, 07–09, 13–20, 22–25, 27–29, 31, 32, 34, 35, 37–41 |
| P2 | 13 | AUD-02, 03, 10, 11, 21, 30, 36, 42–44, 46–48 |
| P3 | 6 | AUD-04, 06, 26, 33, 45, 49 |

O aumento de prioridade de negócio em AUD-16, 20, 25, 31, 32, 37, 40 e 41 decorre do potencial de afetar valores ou decisões mesmo quando a correção técnica isolada não é complexa. AUD-02 cai para P2 de negócio porque a amostra possui usuário multi-oficina, mas ainda não demonstrou a necessidade de um mesmo perfil de colaborador em duas oficinas.

## 6. Plano de execução proposto

### Fase 5.1 — Contenção crítica e medição de produção

**Achados:** AUD-12, AUD-01, AUD-13, AUD-05 e AUD-37.

Objetivos:

- impedir geração de novas OS aprovadas sem estoque consistente;
- definir o conjunto completo de relações que precisam respeitar oficina/conta;
- executar, em réplica ou transação read-only, as consultas de incidência P0/P1;
- quantificar por oficina: registros, valor financeiro, período e origem do fluxo.

Critério de saída:

- nenhum caminho conhecido aprova OS ignorando falha de estoque;
- relatório cross-workshop zerado ou plano individual de correção aprovado;
- rollback e trilha de auditoria definidos antes de qualquer saneamento de dado.

### Fase 5.2 — Fonte canônica de orçamento e OS

**Achados:** AUD-07, AUD-08, AUD-09, AUD-14, AUD-15 e AUD-16.

Objetivos:

- definir fórmula canônica de total e sincronização;
- medir e reconciliar os totais divergentes, preservando relatório antes/depois;
- garantir uma OS principal por orçamento;
- separar estados e datas de aprovação, execução, conclusão e entrega.

Critério de saída:

- total armazenado igual ao recalculado em 100% da base tratada;
- zero orçamento com mais de uma OS principal;
- máquina de estados homologada pelo negócio.

### Fase 5.3 — Financeiro e DRE

**Achados:** AUD-17–20, AUD-22–25 e AUD-04.

Objetivos:

- separar previsto, faturado, liquidado e conciliado;
- eliminar duplicidade de movimento por parcela e tornar sincronização idempotente;
- definir reversões e suas regras em todos os relatórios;
- homologar estrutura, sinais, grupos e dimensões temporais da DRE.

Critério de saída:

- soma de parcelas, movimentos, liquidações e reversões reconciliada por OS;
- DRE fecha suas identidades matemáticas;
- comparativo antigo/novo aprovado pelo responsável financeiro.

### Fase 5.4 — Estoque e importações

**Achados:** AUD-27–32 e AUD-33.

Objetivos:

- centralizar alteração de saldo com lock e regra de negativo;
- definir saldo de abertura e tornar saldo reconciliável pelo razão;
- dar idempotência e rastreabilidade a importações e estornos;
- homologar quantidade decimal e método de valoração.

Critério de saída:

- saldo materializado igual ao razão canônico;
- toda importação/estorno aponta aos movimentos correspondentes;
- custo histórico é reproduzível e quantidades respeitam unidade/precisão.

### Fase 5.5 — Fiscal

**Achados:** AUD-34–36, complementado por AUD-37 tratado na 5.1.

Objetivos:

- tornar solicitação idempotente por oficina+OS+operação;
- impedir reaproveitamento de sessão entre OS;
- definir data fiscal dos relatórios e reconciliar estados com o provider.

Critério de saída:

- nenhuma solicitação/documento órfão, duplicado ou cross-workshop;
- listagem por período reproduz a data fiscal homologada;
- reprocessamento não cria nova operação econômica inadvertidamente.

### Fase 5.6 — RH, folha e comissão

**Achados:** AUD-02, AUD-38–42.

Objetivos:

- escolher a fonte canônica de pagamento da folha;
- migrar resumos e relatórios do vínculo legado para os componentes;
- definir competência da comissão e calendário do quinto dia útil;
- homologar o modelo de colaborador multi-oficina.

Critério de saída:

- total, pago, pendente e status iguais em lista, recibo e relatório;
- competência de comissão única;
- vencimentos validados contra calendário definido.

### Fase 5.7 — Relatórios e dashboards

**Achados:** AUD-10, AUD-11, AUD-21, AUD-36, AUD-41, AUD-43, AUD-44 e AUD-47–49.

Objetivos:

- formalizar dicionário dos indicadores;
- alinhar coortes, datas e unidades de numerador/denominador;
- diferenciar média simples e ponderada;
- garantir a mesma fonte para tela, PDF e Excel;
- validar todos os filtros de período.

Critério de saída:

- cada indicador possui nome, fórmula, fonte, data, filtros e exemplos homologados;
- tela/PDF/Excel produzem o mesmo resultado no mesmo instante de corte;
- suíte de cenários de borda aprovada.

### Fase 5.8 — Dados mestres, agenda e histórico

**Achados:** AUD-03, AUD-06, AUD-26, AUD-45 e AUD-46.

Objetivos:

- uniformizar chaves canônicas e tratar duplicatas;
- definir identidade/versionamento de checklist e questionário;
- proteger agenda em todas as fronteiras de escrita;
- remover dívida residual somente depois da estabilização funcional.

Critério de saída:

- zero duplicata semântica não justificada;
- respostas históricas preservam contexto original;
- validações de agenda independem da origem da escrita.

### Fase 5.9 — Reconciliação final e monitoramento contínuo

**Abrangência:** todos os achados.

Objetivos:

- repetir as consultas de incidência antes/depois;
- registrar valores corrigidos, registros ignorados e justificativas;
- criar checks recorrentes de invariantes por oficina;
- definir owner e SLA para alertas P0/P1.

Critério de saída:

- invariantes críticas zeradas;
- diferenças aceitas formalmente documentadas;
- nenhuma correção depende de comando manual sem auditoria e idempotência.

## 7. Regras de governança para as fases seguintes

1. **Produção deve ser medida antes de corrigida.** Toda consulta precisa registrar timestamp, oficina, contagem e soma financeira.
2. **Nenhum dado histórico deve ser sobrescrito sem trilha.** Preferir estorno, versão ou registro de reconciliação.
3. **Toda correção de dado deve ser idempotente, reversível e testada em cópia.**
4. **Mudanças de fórmula precisam de homologação de negócio.** Teste técnico não decide sozinho o significado de “vendido”, “pago”, “entregue” ou “receita líquida”.
5. **Constraint vem depois da limpeza.** Caso contrário, migration pode falhar ou congelar uma inconsistência sem plano de resolução.
6. **Relatórios devem compartilhar fonte canônica.** Corrigir apenas template/PDF não resolve divergência.
7. **Cada fase deve produzir um relatório de reconciliação.** Incluir contagem antes/depois, valor afetado e exceções aceitas.

## 8. Próxima decisão recomendada

Autorizar primeiro uma etapa operacional de **consultas read-only em staging/produção** para AUD-01, AUD-07–09, AUD-12–14, AUD-17–20, AUD-27–29, AUD-32, AUD-34–35 e AUD-38–39. Esses itens combinam alto impacto com necessidade de medir registros existentes.

Com essa medição será possível transformar a ordem sugerida deste documento em backlog executável, estimar esforço e separar:

- contenção para impedir novos erros;
- correção de código;
- migration estrutural;
- saneamento de dados históricos;
- mudança de definição gerencial/contábil.

Até essa medição, não deve haver correção automática dos 7 orçamentos, 8 OS ou do movimento duplicado encontrados localmente, porque ainda é necessário confirmar a fórmula canônica e a origem de cada diferença.
