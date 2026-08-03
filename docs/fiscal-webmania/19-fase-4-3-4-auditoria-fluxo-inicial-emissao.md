# Fase 4.3.4 — Auditoria UX do fluxo inicial de Emitir Nota

## 1. Escopo e método

Esta auditoria avalia o fluxo inicial acionado por `Financeiro → Emitir nota`, o roteamento das modalidades fiscais e a compreensão das decisões apresentadas ao usuário.

A análise foi realizada sobre as rotas, views, forms, templates e testes existentes na branch `staging`, no commit `05ca6fa5204fb88d2fca589a501447d1cdec683b`.

Esta fase é exclusivamente documental. Nenhum código, tela, regra fiscal, permissão, model, migration, builder, payload, serviço ou integração foi alterado.

## 2. Conclusão executiva

O menu `Emitir nota` abre corretamente o gateway fiscal e não entra diretamente no wizard de Ordem de Serviço. O usuário encontra seis opções em cards, com ícones, descrições e seleção por rádio:

- Nota Fiscal de Saída;
- Devolução;
- Carta de Correção;
- Nota Complementar;
- Nota de Ajuste;
- Transporte.

O gateway funciona tecnicamente como ponto central para os fluxos de NF-e cobertos pelo ciclo 4.2. As operações que dependem de uma nota anterior são direcionadas ao modo seleção da Central de Notas, e a emissão de saída permite escolher entre Ordem de Serviço e emissão manual.

Contudo, a resposta para a pergunta “o usuário entende imediatamente qual nota quer emitir?” é **parcial**. A tela mistura, no mesmo nível visual:

1. criação de uma nova NF-e;
2. criação de documentos derivados de uma NF-e anterior;
3. registro de um evento sobre uma NF-e existente;
4. configuração de transporte que pertence à própria NF-e.

Além disso:

- NFS-e não aparece como modalidade na primeira tela, embora existam tanto o ramo histórico por OS quanto rotas separadas de emissão manual baseadas em preview aprovado;
- `Nota Fiscal de Saída` leva, no ramo por OS, a um wizard que volta a oferecer `Nota Fiscal de Produto`, `Nota Fiscal de Serviço` ou `Ambas`;
- `Transporte` parece uma modalidade fiscal autônoma, embora seja apenas uma configuração da NF-e por OS;
- a emissão manual atende pessoa cadastrada como cliente e produtos, mas não oferece serviços nem fornecedor como destinatário diretamente.

Portanto, `Emitir Nota` já é a entrada canônica do conjunto de NF-e implementado, mas ainda não representa de forma coerente **qualquer tipo de emissão fiscal** nem atende integralmente a emissão sem OS para qualquer pessoa, produto ou serviço.

## 3. Entrada principal

### 3.1 Menu

O item `Financeiro → Emitir nota` aponta para:

```text
/finance/emissao/
    ↓
FiscalOperationGatewayView
    ↓
finance/fiscal_operation_gateway.html
```

Não há desvio direto para `EmissionRequestCreateView` quando o acesso ocorre pelo menu sem parâmetros legados.

### 3.2 Primeira tela apresentada

A tela possui:

- título `Emitir Nota`;
- subtítulo `Escolha a operação fiscal que deseja realizar`;
- marcador `Etapa inicial`;
- título de seção `Tipo de operação`;
- seis cards em grade de duas colunas em telas grandes;
- uma seleção por rádio obrigatória;
- botão único `Continuar`.

### 3.3 Avaliação da hierarquia visual

Pontos positivos:

- o objetivo geral da tela é visível;
- cards inteiros são clicáveis;
- estado selecionado possui borda, fundo e foco visual;
- cada opção tem ícone, nome e descrição;
- o botão `Continuar` mantém uma ação principal única;
- operações sem permissão deixam de ser exibidas e POST manipulado continua bloqueado.

Pontos de atenção:

- todos os cards têm o mesmo peso, embora representem categorias diferentes;
- não existem títulos como `Criar nova nota` e `Operações sobre uma nota emitida`;
- `Carta de Correção` não é uma nova nota, mas aparece ao lado de notas novas;
- `Transporte` não é um documento separado, mas aparece como modalidade equivalente;
- o usuário precisa ler todas as descrições para compreender quais opções exigem NF-e anterior;
- selecionar o card e depois clicar em `Continuar` exige duas ações, embora não exista revisão da escolha nessa tela.

## 4. Mapa completo dos fluxos atuais

## 4.1 Nota Fiscal de Saída

```text
Entrada
Emitir Nota → Nota Fiscal de Saída

Tela apresentada
Origem da emissão

Decisão necessária
Ordem de Serviço ou Emissão Manual

Próximo passo
Wizard por OS ou wizard manual

Resultado
NF-e transmitida pelo fluxo fiscal existente
```

O segundo gateway é uma aplicação adequada de divulgação progressiva: a escolha da origem só é solicitada depois que o usuário escolhe a emissão de saída.

Problema de linguagem nos cards da origem:

- `Continua no wizard atual` descreve a implementação, não a tarefa do usuário;
- `usando o mesmo motor fiscal` é linguagem técnica sem benefício operacional;
- `Emissão Manual` pode ser menos clara que `Sem Ordem de Serviço` para usuários não fiscais.

Textos orientados à tarefa seriam mais compreensíveis:

- `Por Ordem de Serviço — use cliente, produtos e serviços já registrados na OS`;
- `Sem Ordem de Serviço — escolha destinatário e produtos diretamente`.

## 4.2 Nota Fiscal de Saída por Ordem de Serviço

```text
Entrada
Nota Fiscal de Saída → Ordem de Serviço

Tela apresentada
Wizard “Emissão de nota”

Decisões e etapas
1. Selecionar OS
2. Conferir cliente
3. Conferir produtos e serviços
4. Revisar resumo e distribuição de valores
5. Escolher Nota Fiscal de Produto, Nota Fiscal de Serviço ou Ambas
6. Configurar a nota escolhida

Próximo passo
Transmitir a NF-e, a NFS-e ou ambas

Resultado
NfeRequest e/ou NfseRequest vinculada à OS
```

O fluxo produtivo por OS está preservado e possui contexto, stepper e revisão. Entretanto, há uma inconsistência de promessa:

```text
Gateway: Nota Fiscal de Saída
    ↓
Origem: Ordem de Serviço
    ↓
Wizard: Produto, Serviço ou Ambas
```

O usuário escolheu uma modalidade apresentada como NF-e de saída, mas precisa decidir novamente qual documento emitir. Isso pode ser interpretado como redundância ou mudança de escopo durante o processo.

A situação decorre da reutilização correta do wizard histórico unificado, mas o rótulo e o roteamento inicial não explicam esse comportamento.

## 4.3 Nota Fiscal de Saída manual

```text
Entrada
Nota Fiscal de Saída → Emissão Manual

Tela apresentada
Wizard “Emitir NF-e sem Ordem de Serviço”

Decisões e etapas
1. Destinatário
2. Produtos
3. Revisar e emitir

Próximo passo
Confirmar classe fiscal, informações complementares e transmissão

Resultado
NfeRequest MANUAL sem OS, transmitida pelo motor fiscal existente
```

### Destinatário

- seleciona `Customer` ativo da oficina;
- permite `Nova pessoa` quando o usuário possui permissão de cadastro;
- não exige orçamento nem OS;
- não oferece seleção direta de `Supplier`.

### Produtos

- permite produto existente;
- permite cadastro rápido de produto com permissão adequada;
- permite múltiplos itens;
- solicita quantidade e valor unitário;
- impede produto repetido;
- não movimenta estoque.

### Revisão

- apresenta classe de imposto;
- informações complementares;
- destinatário;
- quantidade de itens;
- tabela com produtos, quantidades e valores unitários;
- confirmação explícita antes de `Emitir NF-e`.

O fluxo manual atual está mais claro que a versão auditada no início do ciclo: agora possui três etapas visuais e resumo antes da transmissão.

Lacunas:

- o resumo não apresenta total por item nem total geral;
- a ação final usa `NF-e`, enquanto a entrada usa `Nota Fiscal de Saída`;
- fornecedor cadastrado não pode ser usado diretamente como destinatário;
- serviços são explicitamente excluídos e remetidos ao fluxo de NFS-e;
- a emissão manual de NFS-e existente não está disponível no gateway inicial e segue um workflow técnico separado, baseado em preview e aprovação.

## 4.4 Devolução

```text
Entrada
Emitir Nota → Devolução

Tela apresentada
Central de Notas em modo “Selecionar NF-e de referência”

Decisão necessária
Localizar e selecionar a NF-e original

Próximo passo
Confirmar a referência → Continuar operação → preencher devolução/estorno

Resultado
Novo documento fiscal vinculado à NF-e original
```

Campos principais:

- finalidade: devolução ou estorno, conforme permissão;
- devolução total ou parcial;
- CFOP;
- classe de imposto opcional;
- natureza da operação;
- volumes;
- itens e quantidades a devolver;
- informações complementares e ao Fisco;
- confirmação explícita.

Após a Fase 4.3.2, a seleção é clara e não compete com checkboxes ou downloads. A distinção de que a devolução cria um novo documento e não altera a NF-e original aparece no formulário.

## 4.5 Carta de Correção

```text
Entrada
Emitir Nota → Carta de Correção

Tela apresentada
Central de Notas em modo seleção

Decisão necessária
Selecionar a NF-e autorizada que receberá a correção

Próximo passo
Confirmar a referência → Continuar operação → informar a correção

Resultado
Evento CC-e registrado sobre a NF-e existente
```

Campos principais:

- texto da correção entre 15 e 1.000 caracteres;
- confirmação das restrições legais.

A UX do formulário diferencia corretamente um evento de uma alteração direta: há aviso com restrições e o botão final é `Enviar CC-e`.

Ponto de linguagem inicial: na primeira tela, CC-e ainda possui o mesmo peso visual das modalidades que criam uma nova nota.

## 4.6 Nota Complementar

```text
Entrada
Emitir Nota → Nota Complementar

Tela apresentada
Central de Notas em modo seleção

Decisão necessária
Selecionar a NF-e que será complementada

Próximo passo
Confirmar a referência → Continuar operação → informar complementos

Resultado
Nova NF-e complementar vinculada à original
```

Campos principais:

- operação;
- CFOP geral;
- natureza da operação;
- quantidade e/ou valor complementar por item;
- CFOP e situação tributária por item;
- confirmação explícita.

A dependência técnica de JSON permanece interna em campos ocultos. O usuário interage com linhas e campos estruturados, sem editar JSON bruto.

Ponto de atenção: o campo `Operação` apresenta o valor técnico `1` em um input de texto, enquanto outros fluxos exibem `Entrada` ou `Saída`. Esse campo exige conhecimento interno e pode induzir erro.

## 4.7 Nota de Ajuste

```text
Entrada
Emitir Nota → Nota de Ajuste

Tela apresentada
Central de Notas em modo seleção

Decisão necessária
Selecionar a NF-e de referência

Próximo passo
Confirmar a referência → Continuar operação → preencher o ajuste

Resultado
Nova Nota de Ajuste vinculada à referência
```

Campos principais:

- operação de entrada ou saída;
- CFOP;
- natureza da operação;
- ICMS e ICMS-ST;
- situação tributária;
- dados estruturados de destinatário e produto;
- confirmação fiscal.

O JSON permanece oculto e a interface oferece campos convencionais. O formulário, porém, é tecnicamente denso e destinado a usuário com conhecimento fiscal. O aviso inicial é longo, sem hierarquia entre restrição principal e exceções.

## 4.8 Transporte

```text
Entrada
Emitir Nota → Transporte

Tela apresentada
Wizard por Ordem de Serviço

Decisão necessária
Selecionar OS e concluir o fluxo de NF-e

Próximo passo
Preencher modalidade, transportador, veículo, volumes e reboques na configuração da NF-e

Resultado
NF-e por OS com transport_snapshot
```

O fluxo preserva corretamente transporte como parte da NF-e e não cria CT-e ou documento separado.

Problema de UX: o nome isolado `Transporte` pode ser interpretado como emissão de CT-e, MDF-e ou outro documento fiscal de transporte. A descrição reduz a ambiguidade, mas exige leitura completa.

Rótulo mais preciso: `NF-e com transporte`, acompanhado de badge `Somente por OS`.

## 5. Quantidade de decisões

| Modalidade | Decisões antes de entrar no formulário específico | Avaliação |
|---|---:|---|
| Nota Fiscal de Saída manual | Operação + origem | Adequado; duas decisões conceitualmente diferentes |
| Nota Fiscal de Saída por OS | Operação + origem + tipo de nota novamente no step 5 | Redundância/inconsistência |
| Devolução | Operação + NF-e de referência + confirmação da seleção | Adequado para operação de risco |
| Carta de Correção | Operação + NF-e de referência + confirmação da seleção | Adequado para evento fiscal |
| Nota Complementar | Operação + NF-e de referência + confirmação da seleção | Adequado para documento derivado |
| Nota de Ajuste | Operação + NF-e de referência + confirmação da seleção | Adequado para documento derivado |
| Transporte | Operação + OS | Curto, porém a modalidade está classificada de forma ambígua |

## 6. Problemas encontrados e prioridades

### P1 — Falta agrupamento entre criação e operação sobre nota existente

Todos os cards aparecem em uma grade plana. A diferença existe somente nas descrições.

Melhoria sugerida:

```text
Criar nova nota
- Nota Fiscal de Saída (NF-e de produtos)
- Nota Fiscal de Serviço (NFS-e)
- NF-e com transporte — somente por OS

Operações sobre uma NF-e emitida
- Devolução
- Carta de Correção
- Nota Complementar
- Nota de Ajuste
```

O agrupamento pode ser feito na mesma tela e com os mesmos cards, sem criar nova view.

### P1 — NFS-e não está representada no gateway

O sistema emite NFS-e dentro do wizard por OS e também possui um subsistema separado de preview e emissão manual de NFS-e. Mesmo assim, a primeira tela não oferece `Nota Fiscal de Serviço`. A lista de NFS-e ainda usa parâmetros legados para entrar diretamente no wizard por OS, enquanto as rotas de emissão manual ficam fora desta entrada central.

Impacto:

- `Emitir Nota` não apresenta todas as emissões disponíveis;
- o usuário de serviços precisa descobrir a modalidade dentro do ramo de NF-e/saída ou por atalho externo;
- a promessa de ponto central não é cumprida integralmente.

Melhoria sugerida: conectar as modalidades NFS-e existentes ao gateway, distinguindo o workflow por OS do workflow manual baseado em preview, sem criar novo motor.

### P1 — Ramo por OS repete a escolha do tipo de nota

Depois de escolher `Nota Fiscal de Saída`, o wizard permite Produto, Serviço ou Ambas.

Alternativas a avaliar em fase de implementação:

1. o gateway define o tipo e o wizard respeita essa escolha;
2. o card inicial é renomeado para representar o wizard unificado por OS;
3. NF-e e NFS-e recebem cards próprios, ambos reutilizando o mesmo wizard com modo inicial definido.

A terceira alternativa oferece a melhor correspondência entre intenção e resultado, mas deve preservar a opção histórica `Ambas` para o fluxo por OS.

### P1 — Regra “qualquer pessoa/produto/serviço sem OS” está incompleta

O ramo manual suporta:

- cliente existente;
- cadastro rápido de cliente/pessoa;
- produto existente;
- cadastro rápido de produto;
- múltiplos produtos.

Não suporta diretamente:

- fornecedor existente como destinatário;
- serviço;
- NFS-e sem OS dentro do workflow principal de `Emitir Nota`.

Esse é um gap funcional identificado pela UX, não apenas um problema de texto. Sua correção deve ser planejada em fase própria, porque envolve domínio e regras fiscais além de apresentação.

### P1 — Transporte parece documento fiscal autônomo

Melhoria sugerida:

- renomear para `NF-e com transporte`;
- indicar `Somente por Ordem de Serviço`;
- agrupar com criação de nova nota;
- manter o mesmo redirecionamento e `transport_snapshot`.

### P2 — Linguagem técnica na escolha de origem

Expressões como `wizard atual` e `mesmo motor fiscal` comunicam arquitetura, não benefício.

Melhoria sugerida: explicar de onde virão destinatário e itens e quais vínculos serão criados.

### P2 — `Nota Fiscal de Saída` ainda precisa de qualificador

O rótulo aprovado é melhor que `NF-e Normal`, mas pode ser associado a qualquer saída fiscal. A descrição deve explicitar `NF-e de produtos` e não somente mencionar NF-e manual.

### P2 — Campo técnico na Nota Complementar

O campo `Operação` exibe `1` em vez de um seletor legível `Entrada/Saída`. A correção futura deve manter o valor enviado, alterando apenas a representação do formulário.

### P2 — Resumo manual não mostra totais monetários

O usuário revisa quantidade e valor unitário, mas não vê subtotal por item nem total geral antes da transmissão.

Melhoria sugerida: calcular apenas para apresentação e manter o backend como autoridade dos valores.

### P2 — Nomenclatura varia entre telas

São usados:

- Nota Fiscal de Saída;
- NF-e;
- Nota Fiscal de Produto;
- Emissão de nota;
- Nota Fiscal de Serviço;
- NFS-e.

Melhoria sugerida: definir um vocabulário de interface:

- `Nota Fiscal de Saída (NF-e)`;
- `Nota Fiscal de Serviço (NFS-e)`;
- `Por Ordem de Serviço`;
- `Sem Ordem de Serviço`;
- `Operações sobre nota emitida`.

### P3 — Ação card + Continuar adiciona um clique

É possível avaliar cards que submetem diretamente a escolha, mantendo foco, teclado, CSRF e validação de permissão. Esta é uma otimização secundária; o padrão atual é previsível e seguro.

## 7. Comparação com o objetivo original

### 7.1 Algumas notas podem ser emitidas diretamente pela própria nota

**Atendido com ressalvas.**

- Devolução, Complementar e Ajuste criam documentos derivados depois da seleção da referência.
- CC-e registra evento sobre a NF-e existente.
- Os atalhos do detalhe permanecem disponíveis.
- O gateway centraliza a entrada e a Central fornece o modo seleção.

Ressalva: a primeira tela não diferencia visualmente evento, documento derivado e documento novo.

### 7.2 Algumas operações dependem de uma nota anterior

**Atendido.**

Devolução, CC-e, Complementar e Ajuste seguem:

```text
Emitir Nota
    ↓
Escolher operação
    ↓
Selecionar NF-e de referência
    ↓
Confirmar seleção
    ↓
Preencher e concluir operação
```

A validação final continua nos endpoints existentes.

### 7.3 Emitir para qualquer pessoa/produto/serviço sem depender de OS

**Parcialmente atendido.**

- sem OS: atendido para NF-e manual;
- sem orçamento: atendido;
- sem dependência de estoque: atendido;
- cliente/pessoa: atendido por `Customer` existente ou cadastro rápido;
- produto: atendido, inclusive cadastro rápido e múltiplos itens;
- fornecedor existente: não atendido diretamente;
- serviço sem OS: não atendido;
- NFS-e manual no gateway: não atendido; existem rotas técnicas separadas, mas não integração com a entrada principal.

## 8. Arquivos envolvidos em futuras melhorias

### Gateway e nomenclatura

- `apps/finance/views/fiscal_gateway.py`
- `apps/finance/forms/fiscal_gateway.py`
- `apps/finance/templates/finance/fiscal_operation_gateway.html`
- `apps/finance/templates/finance/nfe_emission_origin_gateway.html`
- `apps/finance/test_fiscal_operation_gateway.py`

Possíveis ajustes: agrupamento, textos orientados à tarefa, modalidade NFS-e e roteamento com tipo explícito.

### Roteamento

- `apps/finance/urls.py`
- `apps/finance/views/emission.py`
- `apps/finance/views/navigation.py`
- `apps/core/presentation/navigation.py`
- `apps/finance/templates/finance/nfe_request_list.html`
- `apps/finance/templates/finance/fse_request_list.html`

Possíveis ajustes: alinhar menu, listas, entradas legadas e modo inicial do wizard.

### Wizard por OS

- `apps/finance/views/emission.py`
- `apps/finance/forms/emission.py`
- `apps/finance/templates/finance/emission_request_form.html`
- `apps/finance/templates/finance/partials/emission_step_content.html`
- testes do wizard unificado.

Possíveis ajustes: preservar tipo escolhido no gateway, explicar `Ambas` e alinhar títulos.

### Fluxos NFS-e existentes fora do gateway

- `apps/finance/views/nfse_manual_emission.py`
- `apps/finance/views/nfse_manual_emission_preview.py`
- `apps/finance/forms/nfse_manual_emission_preview.py`
- templates `finance/nfse_manual_emission_*`
- testes correspondentes de preview e emissão manual de NFS-e.

Possíveis ajustes: avaliar uma entrada segura pelo gateway respeitando capacidades municipais, preview aprovado e permissões próprias. A auditoria não recomenda simplificar ou contornar essas etapas.

### Emissão manual

- `apps/finance/views/nfe_manual.py`
- `apps/finance/forms/nfe_manual.py`
- `apps/finance/templates/finance/nfe_manual_emission_form.html`
- `apps/finance/test_nfe_manual_emission.py`

Possíveis ajustes: totais de revisão e consistência de nomenclatura. Suporte a fornecedor ou serviço exige fase funcional própria e não deve ser tratado como simples mudança de template.

### Operações referenciadas

- `apps/finance/templates/finance/nfe_request_detail.html`
- `apps/finance/views/nfe.py`
- testes de devolução, CC-e, complementar e ajuste.

Possíveis ajustes: campo legível da Nota Complementar e simplificação textual da Nota de Ajuste. A seleção na Central já foi corrigida na Fase 4.3.2.

## 9. Ordem recomendada das melhorias

1. **P1 — Agrupar a primeira tela por intenção:** nova nota versus operação sobre nota emitida.
2. **P1 — Representar NFS-e no gateway**, reutilizando o wizard existente.
3. **P1 — Alinhar a escolha do gateway com o tipo efetivamente emitido no ramo OS.**
4. **P1 — Renomear Transporte para NF-e com transporte**, sem criar documento separado.
5. **P1 — Planejar separadamente fornecedor e serviço sem OS**, pois são gaps funcionais.
6. **P2 — Reescrever textos técnicos da origem e uniformizar nomenclatura.**
7. **P2 — Melhorar revisão monetária do fluxo manual.**
8. **P2 — Substituir o valor técnico da operação na Nota Complementar por escolha legível.**
9. **P3 — Avaliar navegação direta ao clicar no card.**

## 10. Critérios sugeridos para uma futura fase de implementação

1. O acesso pelo menu continua abrindo `FiscalOperationGatewayView`.
2. A primeira tela diferencia visualmente nova emissão de operação sobre nota existente.
3. NF-e e NFS-e disponíveis possuem nomes e resultados previsíveis.
4. O ramo por OS não contradiz a modalidade escolhida no gateway.
5. Transporte permanece configuração da NF-e e não é apresentado como CT-e.
6. Devolução, CC-e, Complementar e Ajuste continuam usando o modo seleção existente.
7. Permissões ocultam opções não autorizadas e POST manipulado permanece bloqueado.
8. Nenhum builder, payload, serviço ou endpoint externo é duplicado.
9. O fluxo histórico por OS permanece disponível, inclusive a emissão de ambas quando aplicável.
10. Gaps funcionais de fornecedor e serviço sem OS não são mascarados por mudanças apenas textuais.

## 11. Estado da fase

- Documento criado: `docs/fiscal-webmania/19-fase-4-3-4-auditoria-fluxo-inicial-emissao.md`.
- Código alterado: nenhum.
- Testes executados: não aplicável a uma auditoria documental.
- Commit criado: não.
- Push realizado: não.
