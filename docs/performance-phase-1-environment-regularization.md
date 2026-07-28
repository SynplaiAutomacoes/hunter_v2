# Fase 1 — diagnóstico e plano de regularização do ambiente

Data: 2026-07-12.

Escopo desta rodada: diagnóstico somente leitura. Nenhuma migration foi aplicada, nenhum banco foi criado/restaurado e nenhum dado foi alterado.

Atualização posterior: a preparação foi executada exclusivamente em `hunter_v2_perf_4a57a015`; `meu_crm` permaneceu intocado. Consulte `docs/performance-phase-1-benchmark-environment.md`.

## Conclusão

O PostgreSQL local `meu_crm` **não pertence à mesma linha de migrations do checkout atual**. Ele não deve receber `manage.py migrate` a partir da branch `fase1/pessoa1`.

O ambiente confiável para benchmark deve ser um banco isolado, criado a partir do commit canônico que será medido. A alternativa de reconciliar o banco atual é mais arriscada, mais demorada e inadequada para iniciar a baseline.

## Evidências

### Código em execução

- branch: `fase1/pessoa1`;
- commit: `4a57a0157c5dd10f8ab65e051f35f46730d4abc9`;
- esse commit é também a ponta local de `main` e `main_otimizada`;
- PostgreSQL: 18.1;
- banco: `meu_crm`;
- tamanho atual: aproximadamente 23 MB;
- banco não está em modo recovery.

### Migrations pendentes no grafo do checkout

`MigrationExecutor.migration_plan()` encontrou 37 migrations do checkout ainda não registradas no banco:

- `budget`: 13;
- `catalog`: 3;
- `collaborators`: 1;
- `core`: 1;
- `finance`: 3;
- `messaging`: 1;
- `workorder`: 11;
- `workshops`: 4.

`manage.py migrate --check` retornou código 1, confirmando que o banco não está atualizado para o grafo atual.

### Drift entre modelos e migrations do próprio checkout

`manage.py makemigrations --check --dry-run` também retornou código 1. Mesmo em um banco vazio, o repositório atual ainda produziria uma migration adicional:

```text
budget.0056_alter_budgetpdfrenderjob_options_and_more
```

Ela ajustaria opções e os campos de timestamp de `BudgetPdfRenderJob`. Portanto, antes de criar o banco de benchmark, o grafo do próprio commit alvo precisa ser estabilizado e `makemigrations --check --dry-run` precisa retornar zero.

### Histórico registrado no banco que não existe no checkout

A comparação entre `django_migrations` e `MigrationLoader.disk_migrations` encontrou:

- 39 migrations registradas no banco, mas ausentes do checkout;
- 37 migrations presentes no checkout, mas não registradas no banco;
- nenhum conflito detectado apenas entre as migrations que ainda existem em disco.

As 39 migrations ausentes do checkout incluem:

- 34 migrations do ramo fiscal de `finance`, de `0041_fiscalemissionattempt_and_more` até `0074_alter_nfseexternalxmlinbox_options`;
- migrations alternativas de `customer` (`0013`, `0015` e merge `0017`);
- `collaborators.0008_alter_workshopcollaborator_rg`;
- `messaging.0003_customeralert`.

Os arquivos fiscais existem na branch `feat/notas-fiscais`. A migration `finance.0074` está contida nessa branch, mas não em `fase1/pessoa1`/`main`. O schema confirma essa procedência: o banco possui tabelas como `finance_fiscaldocument`, que não correspondem aos modelos do checkout atual.

### Coluna que expôs o problema

A tabela `workshops_workshop` termina atualmente em `logo_public_token`. Ela não possui:

- `whatsapp_instance_name`, criada por `workshops.0026` do checkout;
- `whatsapp_phone`, criada por `workshops.0027` do checkout.

Por isso a materialização ORM de `Workshop` falha com `UndefinedColumn`. Essa coluna é apenas o primeiro sintoma; não é a causa completa.

## Por que não executar `migrate` no banco atual

O plano exibido pelo Django parece aplicável porque os nomes completos das migrations são diferentes, mas isso não comprova compatibilidade semântica entre os ramos.

Há colisões de numeração com conteúdo diferente:

- `finance.0041...0043` do ramo fiscal já estão aplicadas, enquanto outras `finance.0041...0043` existem no checkout;
- `collaborators.0008` possui duas migrations diferentes;
- `messaging.0003` possui duas migrations diferentes;
- `customer` também teve ramos que não estão mais presentes no checkout.

Além disso, o plano pendente contém operações que exigem ensaio:

- conversão de feriados em dias trabalhados seguida de remoção da tabela antiga;
- backfills de snapshot, tipo de benefício e último preço de serviço;
- criação de constraints e índices financeiros;
- `SeparateDatabaseAndState` com SQL manual;
- migrations irreversíveis ou com reverso `noop`.

Aplicar esse conjunto no `meu_crm` misturaria estados de duas linhas de desenvolvimento e poderia produzir um banco que o Django considera migrado, mas cujo schema não corresponde a nenhuma revisão real do código.

## Plano recomendado — banco isolado para benchmark

Cada etapa abaixo possui um gate. Nenhuma ação de escrita deve começar sem autorização explícita.

### Gate 1 — definir o commit canônico

Responsável: equipe de código.

1. Confirmar se a baseline deve representar `main`/`4a57a015` ou outra revisão.
2. Congelar o SHA no relatório de benchmark.
3. Não usar uma branch móvel como identidade da amostra.

Saída esperada: um único SHA aprovado.

### Gate 2 — estabilizar migrations no código

Responsável: equipe de código; requer autorização para alteração de arquivos.

1. Gerar e revisar a migration detectada como `budget.0056`.
2. Executar `makemigrations --check --dry-run` até retornar zero.
3. Revisar o grafo com `showmigrations --plan` e `MigrationLoader.detect_conflicts()`.
4. Confirmar que nenhuma migration histórica necessária ao commit canônico está ausente.

Saída esperada: grafo versionado, sem alterações de modelo não representadas.

### Gate 3 — preservar o banco atual

Responsável: operação; requer autorização para backup.

1. Não renomear, apagar, migrar nem reutilizar `meu_crm`.
2. Gerar `pg_dump` com formato custom antes de qualquer experimento futuro.
3. Validar o dump com listagem do catálogo e registrar checksum, tamanho, data, versão do PostgreSQL e SHA do código de origem.
4. Se esse banco continuar sendo usado pela branch fiscal, identificar explicitamente sua branch/commit compatível.

Saída esperada: backup verificável e banco original intocado.

### Gate 4 — criar banco descartável alinhado ao SHA

Responsável: operação; requer autorização para criar banco/schema.

1. Criar um banco com nome inequívoco, por exemplo `hunter_v2_perf_<sha_curto>`.
2. Apontar `DB_NAME` somente no processo de benchmark, sem alterar o `.env` compartilhado.
3. Aplicar migrations do zero nesse banco.
4. Validar:
   - `manage.py check`;
   - `migrate --check` com saída zero;
   - `makemigrations --check --dry-run` com saída zero;
   - nenhum registro de migration ausente em disco;
   - smoke test das rotas críticas.

Saída esperada: banco reproduzível e compatível com um único SHA.

### Gate 5 — fornecer volume representativo

Responsável: aplicação/dados; requer decisão sobre origem dos dados.

Opção recomendada: dados sintéticos determinísticos, sem informações pessoais, dimensionados por oficina e com volumes registrados no relatório.

Se dados reais forem indispensáveis:

1. restaurar o dump em outro banco, nunca sobre o banco de benchmark vazio;
2. anonimizar dados pessoais e segredos;
3. reconciliar o schema apenas na cópia;
4. provar equivalência de contagens e invariantes antes de medir;
5. descartar a cópia se o histórico de migrations continuar divergente.

Saída esperada: dataset versionado ou receita determinística com cardinalidades conhecidas.

### Gate 6 — aceitar o ambiente para benchmark

O ambiente só deve ser aprovado quando todos os itens forem verdadeiros:

- SHA do código registrado;
- banco dedicado e identificável;
- `manage.py check` aprovado;
- `migrate --check` aprovado;
- `makemigrations --check --dry-run` aprovado;
- zero migrations registradas mas ausentes em disco;
- dataset e cardinalidades documentados;
- warm-up e parâmetros de medição definidos;
- integrações externas desabilitadas, simuladas ou identificadas explicitamente conforme o objetivo da rodada;
- banco original preservado.

## Alternativa não recomendada — reconciliar `meu_crm`

Essa alternativa só faz sentido se houver obrigação de preservar exatamente os dados atuais e se a equipe definir como alvo uma revisão que incorpore tanto o ramo fiscal quanto o ramo atual.

Ela exigiria, em uma cópia restaurada:

1. recuperar os 39 arquivos de migration registrados e ausentes;
2. recuperar o código/modelos compatíveis com o ramo fiscal;
3. criar migrations de merge para os ramos paralelos de `finance`, `customer`, `collaborators` e `messaging`;
4. revisar manualmente o estado produzido por `SeparateDatabaseAndState`;
5. ensaiar os backfills e constraints com contagens antes/depois;
6. executar testes funcionais e de integridade;
7. somente então considerar uma janela controlada no banco original.

Essa rota não é necessária para iniciar a Fase 1 de performance e aumenta o risco sem melhorar a reprodutibilidade do benchmark.

## Decisão solicitada antes de qualquer regularização

Confirmar apenas:

1. qual SHA deve representar a baseline;
2. se está autorizada a criação futura de uma migration para o drift de `BudgetPdfRenderJob`;
3. se está autorizada a criação futura de um banco descartável separado;
4. se o dataset será sintético ou uma cópia anonimizada.

Até essas decisões, o status correto é: **ambiente diagnosticado, regularização não iniciada**.
