# Fase 4.1.3 - Inventario tecnico de dados de transporte na NF-e

Data do inventario: 2026-07-27.

Status: concluido documentalmente. Nenhum codigo funcional foi alterado.

## Objetivo e limite

Este inventario identifica o menor ponto de extensao seguro para incluir dados de transporte na NF-e normal ja emitida em producao. A decisao preserva emissao, preview, cancelamento, inutilizacao, CC-e, devolucao e contratos remotos existentes.

Transporte dentro da NF-e e uma extensao do documento atual. CT-e, MDF-e, NFCom e outros documentos fiscais sao dominios separados e nao fazem parte desta fase.

## Fluxo atual mapeado

### Entidades e persistencia

| Componente | Local | Papel atual | Achado sobre transporte |
| --- | --- | --- | --- |
| `NfeRequest` | `apps/finance/models/finance.py` | Intencao persistida da NF-e normal, vinculada a oficina e OS | Nao possui modalidade, transportador ou volumes |
| `NfeItem` | `apps/finance/models/finance.py` | Resultado remoto da emissao, com UUID, status, chave, protocolo, URLs e payload de resposta | Nao possui campos proprios de transporte |
| `FiscalEmissionAttempt` | `apps/finance/models/finance.py` | Tentativa idempotente com hash e copia sanitizada do payload enviado | Ja congela o payload final, portanto registrara transporte sem nova infraestrutura |
| `FiscalDocument` | `apps/finance/models/finance.py` | Projecao moderna da NF-e autorizada e base para eventos/derivados | Nao e a entidade primaria de criacao da NF-e normal |

Conclusao: a intencao de transporte deve pertencer a `NfeRequest`. Criar outro documento, request ou dominio duplicaria o fluxo normal.

### Builder e integracao Webmania

O caminho produtivo e:

1. `WebmaniaFiscalService.emit_nfe`;
2. `emit_nfe_request`;
3. `build_nfe_payload`;
4. `POST /1/nfe/emissao/`;
5. `sync_nfe_emission_response`.

Todos estao em `apps/core/infrastructure/services/fiscal/service.py` e `apps/core/infrastructure/services/webmania/nfe_emission.py`.

O builder atual monta `cliente`, `produtos` e `pedido`. `_build_payment_payload` fixa `pedido.modalidade_frete=9`, equivalente a operacao sem transporte. Nao existe hoje grupo `transporte` no payload normal.

`NfeRequest.additional_information` ja e aplicado de forma aditiva em `pedido.informacoes_complementares`. Esse campo deve continuar livre para observacoes; ele nao substitui dados estruturados de transporte.

### Preview e telas

Existem dois caminhos de entrada que convergem para a mesma persistencia e o mesmo builder:

- fluxo legado de tres etapas: `NfeRequestStep3Form` e `NfeRequestCreateView`/`NfeRequestUpdateView`;
- emissao unificada: `EmissionNfeConfigForm` e `EmissionRequestCreateView`.

Os dois caminhos persistem configuracao em `NfeRequest`. O fluxo unificado tambem mantem estado temporario em sessao antes dessa persistencia.

O preview usa `download_nfe_preview_document`, adiciona `previa_danfe=True` e chama o mesmo endpoint e o mesmo `build_nfe_payload` da emissao. Nao ha builder paralelo. Portanto, uma extensao no builder unico mantem preview e emissao coerentes.

### Idempotencia, timeout e rastreabilidade

Antes do POST real, `emit_nfe_request` cria `FiscalEmissionAttempt` com o payload sanitizado. A chave idempotente e o hash bloqueiam uma segunda intencao divergente. Timeout marca a tentativa como `uncertain`; resposta valida conclui a tentativa.

Adicionar transporte antes de `begin_emission_attempt` preserva automaticamente:

- payload congelado;
- hash/idempotencia;
- estado `uncertain`;
- auditoria do corpo efetivamente enviado;
- webhook e reconciliacao existentes, pois ambos operam sobre a identidade/status da nota e nao precisam interpretar transporte.

Nenhuma alteracao e necessaria em cancelamento, inutilizacao, webhook, consulta ou reconciliacao.

### Permissoes

O fluxo normal continua protegido pelo escopo da oficina e por `view_nferequest`, com permissoes dedicadas ja existentes para cancelamento, inutilizacao, downloads, payload e resposta remota. Transporte e parte da configuracao da mesma NF-e e nao exige permissao fiscal nova no primeiro recorte.

## Estruturas relacionadas encontradas

### Frete do orcamento e da OS

`BudgetItem.shipping`, `service_shipping` e os totais `total_products_shipping`/`total_services_shipping` representam custo ou composicao comercial da precificacao. Eles nao identificam responsabilidade pelo transporte da NF-e, transportadora, veiculo ou volumes.

Decisao: nao inferir `pedido.modalidade_frete` nem `pedido.frete` desses valores.

### Fornecedores

`Supplier` possui documento, razao social e endereco por oficina, mas e um cadastro de fornecedor. Nao possui todos os dados fiscais de transporte, como IE, RNTRC, placa, UF do veiculo, pesos e volumes, nem expressa o papel de transportador.

Decisao: nao converter `Supplier` em transportadora nem criar acoplamento automatico. Uma futura UI pode oferecer preenchimento assistido somente apos uma decisao de cadastro proprio; o snapshot fiscal enviado deve permanecer na `NfeRequest`.

### Volumes em devolucao

`apps/finance/services/nfe_returns.py` aceita um `volume` opcional como dicionario no endpoint de devolucao. Esse limite cru nao possui formulario/modelo reutilizavel e pertence a outro contrato remoto.

Decisao: nao reutilizar diretamente a chave `volume` da devolucao. Na NF-e normal, os volumes pertencem ao grupo estruturado `transporte`.

## Contrato Webmania confirmado

A documentacao oficial da API REST NF-e define:

- `pedido.modalidade_frete`: `0` emitente/CIF, `1` destinatario/FOB, `2` terceiros, `3` transporte proprio do emitente, `4` transporte proprio do destinatario e `9` sem transporte;
- `pedido.frete`: valor do frete que participa do total da nota;
- grupo superior `transporte`: quantidade de volumes, especie, peso bruto, peso liquido, marca, numeracao, lacres e dados opcionais de pessoa fisica ou juridica transportadora, endereco, veiculo, RNTRC e seguro;
- `reboque[]`: grupo adicional, fora do recorte minimo.

Fonte: [Documentacao oficial REST API NF-e da Webmania](https://webmania.com.br/docs/rest-api-nfe/).

O OpenAPI local validado documenta `pedido.modalidade_frete`, mas ainda nao descreve o grupo normal `transporte` nem `pedido.frete`. Ele foi mantido inalterado nesta fase. A atualizacao desse artefato exige revalidacao contratual propria durante a implementacao.

## Menor ponto de extensao seguro

### Persistencia recomendada

Adicionar futuramente a `NfeRequest`, sem novo dominio:

- `freight_mode`: escolha explicita `0`, `1`, `2`, `3`, `4` ou `9`, com default `9` para preservar integralmente notas existentes;
- `transport_information`: snapshot JSON opcional, validado pela aplicacao, contendo somente campos aceitos para transportador, veiculo e volumes.

Essa combinacao torna a modalidade principal explicita e consultavel, enquanto evita uma migration com muitos campos opcionais e preserva o snapshot exato da intencao. O JSON nao deve ser repassado cegamente: formulario e builder devem trabalhar com lista permitida, normalizacao e validacoes condicionais.

Alternativa descartada no primeiro recorte: entidade `Carrier`/`Transportadora`. Ela ampliaria cadastro, permissoes, escopo entre oficinas e sincronizacao de dados sem ser necessaria para emitir a NF-e.

### Builder recomendado

Manter `build_nfe_payload` como unico builder e adicionar um helper pequeno, por exemplo `_apply_transport_to_nfe_payload`, que:

1. substitua apenas o valor fixo de `pedido.modalidade_frete` pelo valor persistido;
2. omita `transporte` quando a modalidade for `9`;
3. inclua `payload["transporte"]` somente com campos preenchidos e validados;
4. preserve todo o restante do payload sem mudanca.

Preview e emissao receberao o mesmo grupo automaticamente. O payload final continuara sendo congelado na tentativa antes do POST.

### Formularios e UX

Os campos devem ser adicionados aos dois pontos de entrada existentes:

- `NfeRequestStep3Form`, no fluxo legado;
- `EmissionNfeConfigForm` e estado `nfe_config`, no fluxo unificado.

A UI minima pode usar uma secao condicional:

1. modalidade de frete;
2. identificacao PF ou PJ do transportador;
3. endereco e veiculo opcionais;
4. dados de volumes.

Selecionar `9 - sem transporte` deve limpar/ignorar o grupo estruturado. A oficina ativa continua sendo a fronteira de autorizacao.

## Recorte funcional recomendado

### Primeira entrega

- modalidade de frete;
- snapshot manual do transportador PF/PJ;
- endereco;
- placa, UF do veiculo e RNTRC opcionais;
- volume, especie, pesos, marca, numeracao e lacres;
- aplicacao no builder unico;
- preview e emissao usando o mesmo payload;
- testes de formulario, builder, preview, idempotencia e regressao da NF-e sem transporte.

### Fora da primeira entrega

- `pedido.frete` com valor monetario;
- inferencia a partir do frete de compra/precificacao;
- cadastro mestre de transportadora;
- multiplos volumes heterogeneos;
- reboque;
- seguro avancado;
- CT-e, MDF-e ou qualquer novo documento fiscal.

O valor `pedido.frete` altera o total fiscal. Inclui-lo sem uma regra explicita de composicao com produtos, desconto e total atual seria uma mudanca de maior risco. Ele deve ser tratado em subfase propria caso a operacao realmente cobre frete do cliente.

## Lacunas e cobertura necessaria

Nao foram encontrados testes diretos do `build_nfe_payload` normal que provem o default `modalidade_frete=9` ou um grupo de transporte. A implementacao deve criar cobertura para:

- request antigo/default continuar com modalidade `9` e sem grupo `transporte`;
- cada modalidade aceita e rejeicao de valor invalido;
- modalidade `9` impedir envio de dados residuais;
- pessoa fisica e juridica;
- validacao de documento, UF, placa, RNTRC, pesos e quantidade de volumes;
- preview e emissao montarem o mesmo transporte;
- tentativa congelar o grupo antes do POST;
- retry com payload divergente continuar bloqueado pela idempotencia;
- escopo entre oficinas;
- regressao de emissao normal, timeout, webhook, consulta e downloads.

## Decisao arquitetural

Adotar extensao incremental do fluxo atual:

`NfeRequest -> build_nfe_payload -> FiscalEmissionAttempt -> POST /1/nfe/emissao/`

Nao criar fluxo paralelo, entidade fiscal nova ou endpoint remoto. Persistir a intencao na mesma requisicao, aplicar um grupo opcional no builder unico e preservar o default atual para todas as notas existentes.

## Proxima fase proposta

**Fase 4.1.3A - Transporte basico na NF-e normal**

Implementar modalidade, transportador e volumes sem valor monetario de frete, com migration pequena, ambos os formularios, builder aditivo e testes dirigidos. A inclusao de `pedido.frete` deve depender de decisao operacional e fiscal posterior.
