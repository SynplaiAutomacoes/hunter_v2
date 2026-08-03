# Fase 4.2.11 — Organização final da branch `fase1/pessoa1` para entrega

Data da auditoria: 31/07/2026.

## 1. Resultado executivo

A branch `fase1/pessoa1` contém integralmente o ciclo fiscal 4.2.x no commit de consolidação `553b7ceb7380addafb0382ef5a0d7992c4dedf84`. Não existem modificações pendentes no código fiscal, nos serviços Webmania ou na navegação fiscal.

A working tree permanece intencionalmente suja por artefatos anteriores e documentos ainda não versionados. Nenhum arquivo foi removido, descartado, movido ou staged nesta fase. Nenhum commit e nenhum push foram realizados.

## 2. Auditoria Git

### Identidade da branch

- Branch: `fase1/pessoa1`.
- HEAD: `553b7ceb7380addafb0382ef5a0d7992c4dedf84`.
- Commit consolidado: `chore: merge fiscal workflow improvements into fase1`.
- Código fiscal pendente em `apps/finance`, `apps/core/infrastructure/services/webmania` e `apps/core/presentation/navigation.py`: nenhum.

### Resultado de `git status`

#### Staged

```text
A  script.ps1
```

O índice contém um arquivo vazio. A versão com conteúdo permanece apenas na working tree.

#### Modificados fora do índice

```text
 M .gitignore
 M docs/performance-phase-1-person-1-baseline.md
 M docs/performance-phase-1-person-1.md
 M script.ps1
```

#### Não rastreados antes deste relatório

```text
apps/workshops/migrations/0031_alter_workshopcost_total_monthly_costs_and_more.py
docs/fiscal-webmania/12-fase-4-1-0-inventario-tecnico-nfe-operacional.md
docs/fiscal-webmania/12-fase-4-2-0-inventario-central-emissao.md
docs/fiscal-webmania/15-fase-4-2-10-preparacao-entrega.md
docs/performance-phase-1-person-1-dashboard-metrics.md
docs/performance-phase-1-person-1-dashboard-post-merge-audit.md
docs/performance-results/person-one-dashboard-metrics-after-stability.json
docs/performance-results/person-one-dashboard-metrics-after.json
```

Após esta auditoria, o presente arquivo `docs/fiscal-webmania/16-fase-4-2-11-organizacao-entrega.md` também fica não rastreado.

## 3. Classificação de cada alteração

| Arquivo | Estado | Classificação | Pertence ao ciclo fiscal? |
|---|---|---|---|
| `.gitignore` | Modificado, não staged | Arquivo local/configuração de desenvolvimento | Não |
| `script.ps1` | Adicionado staged e modificado não staged (`AM`) | Helper local preexistente | Não |
| `docs/performance-phase-1-person-1-baseline.md` | Modificado, não staged | Documentação de performance preexistente | Não |
| `docs/performance-phase-1-person-1.md` | Modificado, não staged | Documentação de performance preexistente | Não |
| `apps/workshops/migrations/0031_alter_workshopcost_total_monthly_costs_and_more.py` | Não rastreado | Migration de custos de oficina preexistente | Não |
| `docs/fiscal-webmania/12-fase-4-1-0-inventario-tecnico-nfe-operacional.md` | Não rastreado | Inventário fiscal | Sim, documentação anterior do ciclo fiscal |
| `docs/fiscal-webmania/12-fase-4-2-0-inventario-central-emissao.md` | Não rastreado | Inventário fiscal | Sim, documentação anterior do ciclo fiscal |
| `docs/fiscal-webmania/15-fase-4-2-10-preparacao-entrega.md` | Não rastreado | Relatório fiscal/de entrega | Sim, somente documentação |
| `docs/fiscal-webmania/16-fase-4-2-11-organizacao-entrega.md` | Não rastreado após esta fase | Relatório fiscal/de entrega | Sim, somente documentação |
| `docs/performance-phase-1-person-1-dashboard-metrics.md` | Não rastreado | Relatório de performance | Não |
| `docs/performance-phase-1-person-1-dashboard-post-merge-audit.md` | Não rastreado | Auditoria de performance | Não |
| `docs/performance-results/person-one-dashboard-metrics-after-stability.json` | Não rastreado | Evidência/resultado de benchmark | Não |
| `docs/performance-results/person-one-dashboard-metrics-after.json` | Não rastreado | Evidência/resultado de benchmark | Não |

## 4. Investigação de `script.ps1`

### Conteúdo staged

- Modo: `100644`.
- Blob no índice: `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391`.
- Conteúdo: vazio, zero bytes.

### Conteúdo na working tree

- Tamanho: 691 bytes.
- Hash: `b68938374b6cb38a5bfe269c38b96c5fe7220f78`.
- Conteúdo: 26 linhas que leem `.env` e carregam os pares chave/valor na sessão PowerShell.
- Não há newline no final do arquivo.

### Origem

- `git log --all -- script.ps1` não encontrou histórico: o arquivo nunca foi commitado.
- O arquivo já estava no estado `AM` antes da consolidação fiscal e foi preservado pela operação de stash/restauração.
- A alteração de `.gitignore` adiciona `script.ps1`, reforçando que a intenção provável era mantê-lo como ferramenta pessoal.

### Recomendação

Não incluir em commit fiscal. Há duas decisões válidas, ambas dependentes de aprovação:

1. Se for ferramenta exclusivamente local, retirar do índice e usar `.git/info/exclude` para ignorá-la sem modificar o `.gitignore` compartilhado.
2. Se for ferramenta oficial do projeto, revisar segurança, parsing de `.env`, newline e documentação; então remover a regra de ignore e criar commit próprio de tooling.

No estado atual, um commit baseado apenas no índice registraria `script.ps1` vazio, o que é incorreto.

## 5. Investigação da migration `workshops.0031`

### Conteúdo e efeito

A migration altera somente dois campos de `WorkshopCost`:

- `total_monthly_costs`: label `Total Despesas Mensais`;
- `total_value`: label `Total Metas e Indicadores`.

Não há transformação de dados. Os campos continuam `MoneyField`, com `max_digits=14`, `decimal_places=2`, `default=0`, `null=True` e `blank=True`.

### Origem histórica

- A mudança dos labels dos models pertence ao commit `a40735ec` — `feat(workshop_costs): change total values verbose names`.
- Esse commit é ancestral do HEAD atual.
- Uma migration canônica para a mesma alteração existe em `main_otimizada`, commit `386873fe` — `feat: create migration to alter workshop cost total`.
- O commit `386873fe` não é ancestral de `fase1/pessoa1`.
- O arquivo local foi regenerado pelo Django 5.2.9 em 01/08/2026 e é semanticamente equivalente, mas não possui o mesmo blob/formatação da versão registrada em `main_otimizada`.
- A migration `workshops.0031` aparece como aplicada no banco local.
- `makemigrations workshops --check --dry-run`: nenhuma alteração adicional.
- `migrate --plan`: nenhuma operação pendente no banco atual.

### Pertencimento e recomendação

A migration pertence funcionalmente à branch oficial porque o model correspondente já está versionado nela. Ela não pertence ao ciclo fiscal.

Recomendação preferencial: integrar ou alinhar o commit canônico `386873fe` em commit separado, verificando antes a compatibilidade com o Django 5.2 e o conflito de nome `0031`. Não versionar simultaneamente a variante local e a canônica. A ausência dessa migration no repositório impediria que um banco novo reproduzisse formalmente o estado dos models, embora o banco local já a tenha aplicado.

## 6. Separação documental

### Inventários fiscais

- `12-fase-4-1-0-inventario-tecnico-nfe-operacional.md`.
- `12-fase-4-2-0-inventario-central-emissao.md`.

Antes do commit, revisar a duplicidade do prefixo `12-` e a convivência com os documentos fiscais já versionados. Não renomear automaticamente.

### Relatórios fiscais e de entrega

- `15-fase-4-2-10-preparacao-entrega.md`.
- `16-fase-4-2-11-organizacao-entrega.md`.

Podem ser versionados juntos após revisão final, sem código ou migrations.

### Relatórios de performance

- alterações nos relatórios base de Pessoa 1;
- relatório de métricas do dashboard;
- auditoria pós-merge;
- dois JSONs de benchmark, com aproximadamente 544 KiB e 686 KiB.

Devem ficar fora de qualquer commit fiscal. Os JSONs precisam de revisão de tamanho, reprodutibilidade e dados potencialmente sensíveis antes do versionamento.

## 7. Commits sugeridos

Nenhum commit foi criado. A ordem recomendada para uma etapa futura é:

1. **Migration de workshops**

   Mensagem sugerida: `fix: add missing workshop cost labels migration`

   Escopo exclusivo: versão canônica/alinhada de `workshops.0031`, após decisão entre integrar `386873fe` ou manter a versão Django 5.2.

2. **Inventários fiscais**

   Mensagem sugerida: `docs: add fiscal workflow technical inventories`

   Escopo: os dois inventários, somente após resolver a numeração duplicada.

3. **Relatórios finais fiscais**

   Mensagem sugerida: `docs: add fiscal delivery preparation reports`

   Escopo: relatórios 15 e 16.

4. **Documentação e evidências de performance**

   Mensagem sugerida: `docs: record dashboard performance audit results`

   Escopo: relatórios, atualizações dos baselines e, se aprovados, JSONs de benchmark.

5. **Tooling local, somente se aprovado como compartilhado**

   Mensagem sugerida: `chore: add local environment loader for PowerShell`

   Escopo: `script.ps1`, documentação e decisão explícita sobre `.gitignore`. Se permanecer pessoal, não deve haver commit.

## 8. Pendências para entrega controlada

1. Corrigir intencionalmente o estado `AM` de `script.ps1` antes de qualquer commit genérico.
2. Versionar a migration de workshops separadamente, usando uma única versão canônica.
3. Revisar a numeração dos dois inventários fiscais.
4. Decidir se os JSONs de benchmark devem integrar o repositório.
5. Manter documentação de performance fora dos commits fiscais.
6. Não usar `git add .` enquanto essas decisões estiverem abertas.

## 9. Conclusão

O código fiscal está pronto e integralmente commitado. A branch ainda exige organização de artefatos locais e documentais antes de uma entrega ampla. A separação proposta evita contaminar o histórico fiscal, preserva a migration necessária de workshops e impede o commit acidental do blob vazio de `script.ps1`.
