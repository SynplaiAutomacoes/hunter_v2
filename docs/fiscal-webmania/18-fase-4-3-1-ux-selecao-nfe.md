# Fase 4.3.1 — Melhoria UX da seleção de NF-e de referência

## 1. Objetivo e escopo da auditoria

Esta auditoria avalia exclusivamente a experiência de seleção de uma NF-e de referência para as operações:

- Devolução;
- Carta de Correção;
- Nota Complementar;
- Nota de Ajuste.

O diagnóstico foi realizado sobre o fluxo, as views, os templates e os testes existentes na branch atual. Nenhum código, regra fiscal, endpoint, permissão, model, migration, builder, payload Webmania ou serviço fiscal foi alterado nesta fase.

## 2. Resumo executivo

O sistema já possui parte importante do contexto de seleção: ao entrar por uma operação fiscal, o título da Central muda para `Selecionar NF-e para [operação]`, a orientação informa que uma nota de referência deve ser escolhida e o parâmetro `operacao` é preservado até o detalhe da NF-e.

Entretanto, o modo seleção ainda reutiliza quase integralmente a interface de consulta e download da Central de Notas. Isso cria três problemas principais:

1. Os checkboxes da primeira coluna parecem selecionar a NF-e para a operação, mas servem somente para download em lote.
2. A ação que realmente continua o fluxo é o pequeno botão `Selecionar`, posicionado na última coluna da tabela.
3. A elegibilidade fiscal é confirmada somente depois que o usuário abre o detalhe; uma nota incompatível pode levar a uma tela de aviso e obrigar o usuário a voltar e tentar outra.

Conclusão: o contexto textual existe, mas a hierarquia de ações ainda não transforma a Central em uma etapa inequívoca do workflow fiscal.

## 3. Fluxo atual

### 3.1 Entrada pelo gateway

O fluxo atual é:

```text
Emitir Nota
    ↓
Escolher Devolução, Carta de Correção, Nota Complementar ou Nota de Ajuste
    ↓
/finance/notas-emitidas/?tipo=nfe&operacao=[operação]
    ↓
Central de Notas em contexto de seleção
    ↓
Localizar a NF-e
    ↓
Clicar em "Selecionar" na coluna Ações
    ↓
Detalhe da NF-e com o parâmetro da operação preservado
    ↓
Formulário da operação aberto automaticamente em modal
```

O gateway preserva os motores existentes: ele apenas direciona o usuário para a lista e, depois, para o detalhe e o endpoint fiscal já existente.

### 3.2 Sinais de modo seleção já existentes

Quando o parâmetro `operacao` é reconhecido, a Central já apresenta:

- título `Selecionar NF-e para [operação]`;
- subtítulo orientando a escolher a referência, revisar e concluir;
- botão `Trocar operação`;
- filtro fixado em NF-e;
- ação de linha renomeada de `Abrir` para `Selecionar`;
- preservação do contexto nos filtros e no link para o detalhe.

No detalhe, o sistema já apresenta:

- alerta de `NF-e de referência selecionada` quando a operação está disponível;
- abertura automática do modal correspondente;
- aviso para selecionar outra nota quando a operação não está disponível ou quando a permissão não permite executá-la.

Esses elementos confirmam que não é necessário criar um novo motor ou endpoint. A lacuna é de apresentação, seleção e continuidade visual.

## 4. Problemas encontrados

### P0 — Nenhum bloqueio funcional crítico identificado

O fluxo consegue preservar a operação escolhida e chegar aos formulários fiscais existentes. Não foi identificado nesta auditoria um bloqueio que exija mudança de motor fiscal.

### P1 — Checkbox possui significado diferente do esperado no modo seleção

Na Central, cada linha possui um checkbox e o cabeçalho possui `Selecionar todas as notas`. Esses controles alimentam exclusivamente os downloads em lote de XML e PDF.

No contexto de uma operação fiscal, porém, o usuário está procurando uma única NF-e de referência. A interpretação natural é que o checkbox seleciona a nota para Devolução, CC-e, Complementar ou Ajuste. Marcar o checkbox não habilita uma ação `Continuar operação`; habilita apenas `Baixar XML` ou `Baixar PDFs`.

Impacto:

- alta probabilidade de tentativa no controle errado;
- falsa sensação de que a NF-e foi selecionada;
- conflito entre seleção unitária fiscal e seleção múltipla para download;
- aumento do tempo para descobrir a ação correta.

### P1 — A ação principal está visualmente subordinada

O link `Selecionar` utiliza estilo discreto (`btn-ghost btn-xs`) e fica na última coluna de uma tabela larga. Em telas menores, a coluna pode exigir rolagem horizontal. A ação essencial do workflow tem menos destaque do que busca, filtros e downloads.

Impacto:

- o usuário encontra a nota, mas não identifica imediatamente como avançar;
- a continuidade depende da coluna genérica `Ações`;
- a interface continua parecendo uma tela de consulta.

### P1 — Controles de consulta competem com o objetivo da etapa

No modo seleção permanecem visíveis:

- checkboxes de download;
- `Baixar XML`;
- `Baixar PDFs`;
- coluna `Documentos` com foco operacional de consulta;
- cards de resumo de filtro e resultado sem indicação visual de progresso do workflow.

Busca e filtros continuam necessários, mas download em lote é uma tarefa paralela. A presença desses controles reduz a clareza da única decisão necessária: escolher uma NF-e e continuar.

### P1 — Elegibilidade descoberta tarde demais

A lista considera a linha selecionável com base na existência de XML ou PDF. A disponibilidade real da operação é calculada no detalhe, considerando status, vínculos, eventos anteriores, saldos e permissões específicas.

Assim, o usuário pode clicar em `Selecionar`, abrir o detalhe e somente então receber a mensagem de que a operação não está disponível para aquela NF-e ou para sua permissão.

Impacto:

- tentativa e erro;
- retorno desnecessário à lista;
- dificuldade para entender se o problema é status, saldo, evento existente ou autorização;
- maior impacto em Devolução e CC-e, que possuem critérios específicos de elegibilidade.

### P2 — Continuidade é implícita e depende de abertura automática de modal

Após selecionar a linha, o usuário é levado ao detalhe completo da NF-e. Um alerta informa que a referência foi selecionada e um script abre automaticamente o modal da operação.

Embora funcional, a transição não possui uma etapa visual persistente com:

- identificação resumida da NF-e selecionada;
- nome da operação em andamento;
- ação clara para trocar a referência;
- noção de progresso `Selecionar NF-e → Preencher operação → Confirmar`.

Se o modal for fechado, o usuário retorna ao detalhe geral, onde os demais atalhos fiscais competem com a operação iniciada.

### P2 — A linha não funciona como área explícita de seleção

Somente o link na última coluna abre o detalhe no contexto da operação. Número, cliente, status e restante da linha não comunicam interatividade.

Transformar toda a linha em único link pode gerar problemas de acessibilidade e conflitos com controles internos. Porém, uma área clicável bem delimitada ou um botão primário junto aos dados principais diminuiria a dependência da coluna de ações.

### P2 — Orientação poderia informar critérios da referência

O subtítulo pede que o usuário escolha a NF-e, mas não antecipa critérios básicos, como documento autorizado e compatível com a operação. Também não explica por que algumas notas podem estar indisponíveis.

Essa informação deve ser curta e específica por operação, sem expor regras tributárias complexas.

### P3 — Terminologia da Central ainda é parcialmente inconsistente

Na mesma tela aparecem `NF-e`, `Nota Fiscal de Produto`, `Nota Fiscal Serviço`, `Nº da Nota` e textos sem acentuação em trechos auxiliares (`ate`, `periodo`). A inconsistência não impede a seleção, mas reduz acabamento e coerência.

## 5. Solução UX recomendada

### 5.1 Criar dois estados visuais explícitos na mesma Central

Manter a mesma view e o mesmo endpoint de consulta, mas renderizar a interface conforme o contexto:

#### Estado A — Consulta normal

Preservar integralmente:

- título `Central de Notas`;
- checkboxes de seleção múltipla;
- downloads de XML e PDF;
- ação `Abrir`;
- filtros e atalhos atuais.

#### Estado B — Seleção de referência

Quando houver uma `operacao` válida:

- exibir cabeçalho destacado `Selecionar NF-e para [operação]`;
- exibir indicador de etapa, por exemplo `1. Selecionar NF-e → 2. Preencher dados → 3. Confirmar`;
- manter busca e filtros;
- ocultar checkboxes e ações de download em lote;
- restringir visualmente a lista a NF-e;
- substituir a ação discreta por botão primário `Selecionar e continuar`;
- fornecer ação secundária `Trocar operação`;
- diferenciar notas elegíveis, inelegíveis e indisponíveis por permissão.

Essa estratégia preserva a Central de consulta e elimina a ambiguidade sem criar uma segunda tela ou duplicar consultas.

### 5.2 Padrão recomendado para selecionar uma única NF-e

Recomendação principal: botão primário por linha, com possibilidade de ampliar a área clicável da linha como conveniência.

```text
NF-e 1234 | Cliente | Emissão | Status | [Selecionar e continuar]
```

Motivos para não usar checkbox como controle principal:

- a operação aceita uma única NF-e de referência;
- checkbox sugere seleção múltipla;
- checkbox já possui significado consolidado de download em lote na Central;
- um botão com verbo e consequência comunica melhor a próxima ação.

A seleção pela linha pode ser adicionada como conveniência, desde que:

- exista foco de teclado visível;
- Enter e Espaço tenham comportamento previsível;
- links internos não acionem duas navegações;
- o botão permaneça visível como affordance principal;
- leitores de tela recebam um rótulo como `Selecionar NF-e 1234 para Devolução`.

### 5.3 Mostrar elegibilidade antes da seleção

Idealmente, a lista deve receber um estado de elegibilidade calculado no servidor para a operação solicitada:

- `Disponível` — botão `Selecionar e continuar` habilitado;
- `Indisponível` — botão desabilitado e motivo curto;
- `Sem permissão` — não oferecer a ação, preservando o endpoint como autoridade final.

Exemplos de mensagens curtas:

- `Carta de Correção já registrada para esta NF-e`;
- `NF-e sem saldo disponível para devolução`;
- `Status da NF-e não permite esta operação`;
- `Você não possui permissão para concluir esta operação`.

Essa melhoria deve reutilizar as mesmas funções de elegibilidade e permissão já utilizadas no detalhe. Não deve copiar regras fiscais para o template nem substituir a validação definitiva do endpoint.

Se a reutilização segura dos critérios exigir trabalho maior, a primeira entrega pode apenas manter o botão e apresentar o motivo genérico no detalhe. A elegibilidade antecipada deve permanecer como prioridade seguinte, pois reduz tentativa e erro.

### 5.4 Tornar a continuidade explícita

Ao clicar em `Selecionar e continuar`, manter o direcionamento atual para o detalhe da NF-e e os endpoints existentes, mas reforçar o contexto:

- título da área: `[Operação] — NF-e nº [número]`;
- resumo compacto: número, série, destinatário, data e status;
- ação `Trocar NF-e` que retorna à Central preservando busca e filtros;
- etapa atual: `Preencher dados da operação`;
- formulário correspondente em primeiro plano;
- botão final nomeado conforme a operação, por exemplo `Emitir Nota Complementar` ou `Registrar Carta de Correção`.

O modal atual pode ser preservado. Contudo, o contexto da operação deve continuar visível após o fechamento acidental do modal, com uma ação destacada `Continuar [operação]`.

### 5.5 Orientação específica por operação

#### Devolução

Texto sugerido: `Selecione a NF-e de saída que contém os produtos a devolver. Na próxima etapa você informará os itens e as quantidades.`

#### Carta de Correção

Texto sugerido: `Selecione a NF-e autorizada que receberá a correção. A carta não altera valores, impostos ou destinatário.`

A segunda frase deve ser confirmada pela regra fiscal vigente antes de implementação textual definitiva.

#### Nota Complementar

Texto sugerido: `Selecione a NF-e que terá valores ou quantidades complementados.`

#### Nota de Ajuste

Texto sugerido: `Selecione a NF-e que servirá de referência para o ajuste fiscal.`

## 6. Fluxo proposto

```text
Emitir Nota
    ↓
Escolher operação fiscal
    ↓
Central em MODO SELEÇÃO
    ├── operação e etapa visíveis
    ├── busca e filtros
    ├── somente NF-e de referência
    ├── sem checkboxes/downloads concorrentes
    └── botão "Selecionar e continuar"
            ↓
NF-e selecionada + resumo da referência
            ↓
Formulário fiscal existente
            ↓
Validação e endpoint fiscal existente
            ↓
Resultado e histórico existentes
```

## 7. Preservações obrigatórias

A futura implementação deve preservar:

- consulta normal da Central de Notas;
- seleção múltipla e downloads no modo de consulta;
- filtros, busca e estado de navegação;
- atalhos existentes do detalhe da NF-e;
- escopo por oficina;
- permissões existentes;
- bloqueio de manipulação de parâmetros e POST;
- endpoints finais como autoridade de autorização e elegibilidade;
- formulários e serviços fiscais existentes;
- models e migrations fiscais;
- builders e payloads Webmania;
- histórico, documentos, webhooks e reconciliação.

O parâmetro de URL é contexto de apresentação, não autorização. Uma `operacao` manipulada nunca deve habilitar ação que o usuário ou a NF-e não permitam.

## 8. Prioridades recomendadas

| Prioridade | Melhoria | Resultado esperado |
|---|---|---|
| P1 | Ocultar checkboxes e downloads no modo seleção | Elimina o controle com significado concorrente |
| P1 | Destacar `Selecionar e continuar` por NF-e | Torna a ação principal imediatamente reconhecível |
| P1 | Manter cabeçalho e indicador de etapa do workflow | Diferencia seleção fiscal de consulta normal |
| P1 | Antecipar elegibilidade e permissão, reutilizando regras existentes | Reduz tentativas em notas incompatíveis |
| P2 | Exibir resumo persistente da NF-e após a seleção | Mantém referência e operação visíveis |
| P2 | Oferecer `Trocar NF-e` preservando filtros | Facilita correção sem reiniciar o fluxo |
| P2 | Melhorar acessibilidade e comportamento em telas menores | Evita dependência da última coluna da tabela |
| P3 | Uniformizar terminologia e acentuação | Melhora acabamento e consistência |

## 9. Arquivos envolvidos em uma futura implementação

### Alterações principais

- `apps/finance/templates/finance/issued_documents_list.html`
  - cabeçalho e ações específicas do modo seleção;
  - ocultação dos downloads no contexto fiscal;
  - indicador de progresso e orientação específica.

- `apps/finance/templates/finance/partials/issued_documents_results.html`
  - remover checkboxes no modo seleção;
  - destacar a ação unitária;
  - apresentar elegibilidade e motivos;
  - adequar comportamento responsivo e acessível.

- `apps/finance/views/issued_documents.py`
  - fornecer ao template o estado explícito de modo seleção;
  - manter o tipo NF-e no contexto fiscal;
  - expor rótulos, URLs e, se viável, elegibilidade calculada por operação;
  - reutilizar regras de permissão e elegibilidade já existentes.

- `apps/finance/templates/finance/nfe_request_detail.html`
  - reforçar a NF-e selecionada e a operação em andamento;
  - oferecer `Trocar NF-e` e `Continuar operação` de forma persistente;
  - preservar os modais e formulários atuais.

- `apps/finance/views/nfe.py`
  - compartilhar com a lista os critérios já aplicados no detalhe, caso a elegibilidade seja antecipada;
  - manter a validação final e os endpoints existentes.

### Navegação e contexto

- `apps/finance/views/fiscal_gateway.py`
  - somente se forem necessários textos mais específicos por operação; os redirects atuais já carregam o contexto correto.

- `apps/finance/views/navigation.py`
  - revisar apenas se a navegação de retorno ou a preservação de busca/filtros precisar ser ampliada.

### Testes a ajustar ou criar futuramente

- `apps/finance/test_issued_documents.py`
  - consulta normal preserva checkboxes e downloads;
  - modo seleção oculta controles de lote;
  - operação, busca e filtros permanecem na navegação;
  - botão unitário possui rótulo e URL corretos;
  - comportamento para NF-e elegível e inelegível.

- `apps/finance/test_fiscal_operation_gateway.py`
  - cada operação continua direcionando para o modo seleção correto.

- `apps/finance/test_nfe_returns.py`
  - seleção e continuidade de Devolução.

- `apps/finance/test_nfe_correction.py`
  - seleção e continuidade de Carta de Correção.

- testes focados de Nota Complementar e Nota de Ajuste
  - disponibilidade, permissão, seleção e abertura do formulário correspondente.

## 10. Critérios de aceite sugeridos

1. A Central aberta pelo menu continua funcionando como consulta e download, sem regressão.
2. A Central aberta pelo gateway exibe inequivocamente o nome da operação e a etapa atual.
3. No modo seleção, os checkboxes e downloads em lote não aparecem.
4. Cada NF-e compatível apresenta ação primária `Selecionar e continuar`.
5. A ação permanece alcançável e compreensível em desktop, mobile e por teclado.
6. NF-e incompatível não induz o usuário a uma tentativa sem explicação.
7. Busca e filtros preservam `operacao=nfe` e o contexto correto durante atualizações HTMX e navegação.
8. Após a seleção, número, destinatário e operação permanecem visíveis.
9. `Trocar NF-e` retorna à lista preservando o contexto útil.
10. Permissões e endpoints finais continuam bloqueando qualquer acesso não autorizado, inclusive por parâmetros ou POST manipulados.
11. Devolução, CC-e, Complementar e Ajuste continuam usando seus formulários, serviços e motores existentes.
12. Nenhuma mudança é introduzida em builder, payload Webmania, integração externa ou domínio fiscal.

## 11. Conclusão

A base técnica para o workflow já existe e preserva corretamente a operação até o detalhe da NF-e. A melhoria necessária não é criar uma nova Central nem um novo fluxo fiscal, mas tornar explícito o estado de seleção na mesma Central.

A decisão UX recomendada é: **no modo fiscal, remover a seleção múltipla de download e usar uma ação primária unitária `Selecionar e continuar` por NF-e**. Com contexto persistente, elegibilidade antecipada e retorno para troca de referência, o usuário passa a compreender naturalmente a sequência `selecionar NF-e → preencher operação → confirmar`, enquanto a consulta normal e todos os motores fiscais permanecem preservados.

## 12. Estado desta fase

- Documento de auditoria criado: `docs/fiscal-webmania/18-fase-4-3-1-ux-selecao-nfe.md`.
- Código alterado: nenhum.
- Commit criado: não.
- Push realizado: não.
