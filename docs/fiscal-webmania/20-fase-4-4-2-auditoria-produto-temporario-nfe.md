# Fase 4.4.2 — Auditoria técnica para produto temporário na emissão manual de NF-e

## 1. Escopo e método

Esta auditoria avalia como permitir que um item de produto exista somente dentro de uma emissão manual de NF-e, sem criar um registro permanente no catálogo da oficina.

Foram analisados:

- `catalog.Product` e o efeito automático de criação de estoque;
- `finance.NfeRequestManualItem`;
- formulário e view da emissão manual;
- cadastro rápido de produto existente;
- `build_nfe_payload` e o contrato enviado à Webmania;
- validação da classe tributária;
- `FiscalEmissionAttempt` e o momento em que o payload é congelado;
- o padrão de item local usado em orçamento, apenas como referência arquitetural.

Esta fase é exclusivamente documental. Nenhum model, migration, builder, payload, serviço fiscal, endpoint ou regra foi alterado.

## 2. Conclusão executiva

O fluxo atual **não suporta produto temporário com segurança**.

Neste contexto, “temporário” deve significar **não cadastrado no catálogo e não reutilizável**, e não “descartado do banco”. Os dados que efetivamente compõem uma NF-e precisam permanecer vinculados à requisição para auditoria, retry, idempotência, histórico e explicação do documento emitido.

`NfeRequestManualItem` armazena somente:

- uma FK obrigatória para `Product`;
- quantidade;
- valor unitário.

Todos os demais dados fiscais são lidos do `Product` no momento em que `build_nfe_payload` é executado. Portanto, um item sem produto persistido não pode ser salvo nem convertido no payload atual.

Não é recomendável criar um `Product` permanente e marcá-lo informalmente como temporário. A criação de `Product` também cria um `StockProduct` por signal, expõe o registro no catálogo e deixa uma FK protegida em `NfeRequestManualItem`. Isso produz exatamente o efeito colateral que o requisito pretende evitar.

A recomendação técnica é:

1. evoluir `NfeRequestManualItem`, sem criar um segundo model de item;
2. tornar `product` opcional somente para itens de origem temporária;
3. registrar no item um snapshot fiscal imutável;
4. usar o mesmo snapshot também para produtos cadastrados;
5. adaptar apenas a extração da linha manual dentro do builder existente;
6. preservar integralmente `build_nfe_payload`, `FiscalEmissionAttempt`, o contrato Webmania e o serviço de emissão.

Essa solução exige migration em uma futura fase de implementação, mas **não exige novo model, novo builder, payload paralelo ou serviço fiscal paralelo**.

## 3. Estado atual

### 3.1 `Product`

O cadastro permanente contém, entre outros, os campos usados na emissão:

- `code`;
- `name`;
- `unit`;
- `ncm`;
- `cest`;
- `origin_cst`;
- `selling_price`.

Também contém dados que não participam diretamente do payload fiscal atual:

- grupo;
- custo;
- marca e modelo;
- SKU e código de barras;
- localização;
- finalidade interna (`purpose`);
- imagem e aplicação.

Ao criar um `Product`, o signal `create_stock_product` executa `StockProduct.objects.get_or_create(...)`. Não há movimentação de estoque, mas há criação permanente de estrutura de catálogo e estoque.

### 3.2 `NfeRequestManualItem`

O model atual possui:

```text
request      → NfeRequest
product      → Product obrigatório, PROTECT
quantity     → decimal maior que zero
unit_price   → decimal maior que zero
```

As validações atuais garantem:

- uso somente em `NfeRequest` de origem `MANUAL`;
- produto pertencente à mesma oficina;
- um mesmo produto apenas uma vez na requisição.

Ele não armazena descrição, código, NCM, CEST, unidade ou origem CST. Consequentemente, não é autossuficiente para representar uma linha fiscal.

### 3.3 Builder NF-e

O fluxo manual chega ao mesmo builder produtivo:

```text
NfeRequest MANUAL
    ↓
_extract_manual_product_lines
    ↓
_build_manual_product_line
    ↓
ProductEmissionLine
    ↓
_build_nfe_products_payload
    ↓
build_nfe_payload
    ↓
FiscalEmissionAttempt
    ↓
Webmania
```

`_build_manual_product_line` acessa `item.product` e obtém do cadastro:

- nome;
- código;
- NCM;
- CEST;
- unidade;
- origem CST.

Quantidade e valor são obtidos de `NfeRequestManualItem`.

O builder rejeita produto sem código ou sem NCM de oito dígitos. Depois normaliza a linha em `ProductEmissionLine` e monta o mesmo payload usado pelo motor existente.

### 3.4 Cadastro rápido atual

O botão de cadastro rápido utiliza `QuickProductForm` e `NfeManualQuickProductCreateView`.

Ele solicita:

- código;
- unidade;
- nome;
- grupo;
- custo;
- valor de venda;
- NCM.

No fluxo manual, NCM é tornado obrigatório. Ao confirmar, a view executa `product.save()`, cria o produto no catálogo e dispara a criação automática de `StockProduct`.

Logo, o cadastro rápido atual representa corretamente a opção **“cadastrar e reutilizar”**, mas não deve ser reaproveitado sem separação explícita para a opção **“usar somente nesta NF-e”**.

### 3.5 `FiscalEmissionAttempt`

`FiscalEmissionAttempt.request_payload` preserva o payload efetivamente enviado. Entretanto, o attempt nasce somente depois de o builder conseguir montar o payload.

Ele não resolve a persistência anterior à emissão porque:

- o item temporário precisa sobreviver à validação do formulário;
- o builder precisa ler seus dados antes de criar o attempt;
- falhas anteriores ao envio precisam permitir revisão e nova tentativa;
- o `NfeRequest` deve continuar auditável independentemente do attempt.

Portanto, `FiscalEmissionAttempt` permanece como registro da tentativa e não deve ser usado como armazenamento primário do produto temporário.

## 4. Campos necessários para uma linha de produto NF-e

Pelo contrato montado atualmente, uma linha precisa dos seguintes dados:

| Dado | Obrigatoriedade atual | Origem atual | Destino no payload |
|---|---:|---|---|
| Nome/descrição | Obrigatório na prática | `Product.name` | `nome`, limitado a 120 caracteres |
| Código | Obrigatório | `Product.code` | `codigo`, limitado a 60 caracteres |
| NCM | Obrigatório | `Product.ncm` | `ncm`, normalizado para 8 dígitos |
| Unidade | Necessária | `Product.unit` | `unidade`; `UND` vira `UN` |
| Origem CST | Necessária | `Product.origin_cst` | `origem` |
| CEST | Condicional/opcional | `Product.cest` | `cest`, somente quando preenchido |
| Quantidade | Obrigatória e maior que zero | `NfeRequestManualItem.quantity` | `quantidade` |
| Valor unitário | Obrigatório e maior que zero | `NfeRequestManualItem.unit_price` | usado em `subtotal` e `total` |
| Classe tributária | Obrigatória por requisição | `NfeRequest.tax_class` | `classe_imposto` em cada produto |

Não são necessários para o payload de produto atual:

- grupo de catálogo;
- custo;
- estoque ou saldo;
- marca/modelo;
- SKU;
- código de barras;
- localização;
- imagem;
- finalidade interna do cadastro.

CFOP e regras tributárias detalhadas não são informados diretamente pela linha manual atual. O fluxo usa a classe de imposto da requisição, validada contra as credenciais Webmania e contra a configuração local IBS/CBS antes do envio.

## 5. Respostas objetivas

### 5.1 `NfeRequestManualItem` já suporta armazenar os dados temporários?

**Não.** Ele depende obrigatoriamente de `Product` e armazena apenas quantidade e valor unitário.

### 5.2 É necessário criar novo model?

**Não é recomendado.** Um segundo model, como `NfeRequestTemporaryItem`, duplicaria quantidade, preço, validações, ordenação, montagem do payload e regras de exclusividade. Isso aumentaria o risco de dois caminhos fiscais divergentes.

O item temporário tem o mesmo ciclo de vida da linha manual. Portanto, seu proprietário natural continua sendo `NfeRequestManualItem`.

### 5.3 É possível reutilizar a estrutura sem impactar o cadastro?

**Sim, mediante uma pequena evolução de schema em `NfeRequestManualItem`.** Não é possível fazer isso apenas com a estrutura atual.

A evolução deve permitir uma linha com:

- origem `CATALOG` e FK para `Product`; ou
- origem `TEMPORARY`, sem FK para `Product`;
- snapshot fiscal em ambos os casos.

O fluxo temporário não chama `Product.save()`, não cria `StockProduct`, não aparece no catálogo e não cria movimentação de estoque.

## 6. Alternativas avaliadas

### Alternativa A — Criar `Product` com marcação temporária

Exemplos: campo `is_temporary`, nome prefixado ou grupo especial.

Vantagens:

- builder atual funcionaria sem adaptação estrutural;
- FK atual permaneceria obrigatória.

Problemas:

- polui o catálogo;
- cria `StockProduct` automaticamente;
- exige política de ocultação e limpeza;
- a FK `PROTECT` impede remoção enquanto a nota existir;
- exclusão destruiria a referência histórica ou exigiria retenção permanente;
- mistura entidade reutilizável com snapshot fiscal de uma emissão.

**Conclusão:** não recomendada.

### Alternativa B — Manter dados apenas no POST ou na sessão

Vantagens:

- nenhuma migration.

Problemas:

- perde dados em recarregamento, falha ou retry;
- não permite auditoria do `NfeRequest`;
- o builder não recebe uma fonte persistente;
- enfraquece idempotência e reconciliação;
- induz caminho paralelo ou builder especial.

**Conclusão:** incompatível com a segurança do fluxo fiscal.

### Alternativa C — Criar `NfeRequestTemporaryItem`

Vantagens:

- separação explícita entre catálogo e temporário.

Problemas:

- dois relacionamentos de itens na mesma requisição;
- duplicação de quantidade, preço e validações;
- ramificações adicionais no builder e na UI;
- maior custo de testes e manutenção;
- risco de payloads divergentes.

**Conclusão:** somente faria sentido se o item temporário tivesse ciclo de vida próprio, o que contradiz o requisito.

### Alternativa D — Evoluir `NfeRequestManualItem` com snapshot fiscal

Vantagens:

- mantém uma coleção única de itens;
- preserva o mesmo builder e payload final;
- não cria cadastro nem estoque para item temporário;
- oferece rastreabilidade antes e depois da emissão;
- permite congelar também os dados de produtos cadastrados;
- mantém `FiscalEmissionAttempt` no papel atual.

Impacto:

- exige migration futura;
- exige validação clara do snapshot;
- exige compatibilidade com itens históricos que possuem somente FK.

**Conclusão:** alternativa recomendada.

## 7. Recomendação técnica

### 7.1 Representação sugerida

Evoluir `NfeRequestManualItem` com:

- `item_origin`: enum `CATALOG` / `TEMPORARY`;
- `product`: FK nullable;
- `product_snapshot`: JSON estruturado e validado.

Estrutura conceitual do snapshot:

```json
{
  "description": "Filtro de óleo",
  "code": "TEMP-001",
  "ncm": "84212300",
  "cest": "",
  "unit": "UN",
  "origin_cst": 0
}
```

Quantidade e valor unitário devem permanecer nas colunas existentes.

O JSON é indicado aqui como snapshot, não como payload Webmania. Ele deve ter schema interno tipado e validação de domínio; o builder continua responsável por produzir o contrato externo.

### 7.2 Regras sugeridas

Para `CATALOG`:

- `product` obrigatório;
- produto da mesma oficina;
- snapshot capturado no momento da criação do item;
- alterações futuras no catálogo não mudam a intenção fiscal já registrada.

Para `TEMPORARY`:

- `product` nulo;
- snapshot obrigatório e completo;
- código, NCM, unidade, origem CST, descrição, quantidade e valor validados;
- nenhum `Product` ou `StockProduct` criado.

Compatibilidade:

- itens históricos sem snapshot continuam usando `product` como fallback;
- novos itens sempre recebem snapshot;
- após migração de dados opcional, o fallback pode ser mantido por segurança.

### 7.3 Builder

Não criar novo builder.

Alterar somente o adaptador `_build_manual_product_line` para obter os dados nesta ordem:

1. snapshot fiscal do item;
2. fallback para `Product` em registros históricos.

O resultado continua sendo o mesmo `ProductEmissionLine`. A partir desse ponto, desconto, totais, classe tributária, payload, attempt, envio e sincronização permanecem iguais.

### 7.4 Formulário e permissões

A linha manual deve oferecer escolha explícita:

```text
Produto cadastrado
ou
Produto somente para esta NF-e
```

Produto cadastrado:

- usa o seletor atual;
- pode continuar oferecendo “Novo produto” mediante `catalog.add_product`.

Produto temporário:

- apresenta somente os campos fiscais necessários;
- não exige `catalog.add_product`, pois não altera o catálogo;
- continua exigindo a permissão de emissão/acesso à NF-e manual;
- deve informar claramente “Este produto não será salvo no catálogo nem movimentará estoque”.

## 8. Impacto esperado de uma futura implementação

### Banco

- uma migration em `finance`;
- FK `product` passa a aceitar nulo;
- novos campos de origem e snapshot;
- check constraint garantindo coerência entre origem e presença da FK.

### Domínio

- nenhuma alteração em `Product`;
- nenhuma alteração em `StockProduct`;
- nenhum novo domínio de catálogo;
- `NfeRequestManualItem` passa a ser o snapshot completo da intenção fiscal manual.

### Emissão

- mesma `NfeRequest`;
- mesmo `ProductEmissionLine`;
- mesmo `build_nfe_payload`;
- mesmo `FiscalEmissionAttempt`;
- mesmo endpoint e contrato Webmania;
- mesmo fluxo de sincronização, webhook e reconciliação.

### UX

- escolha entre produto cadastrado e temporário em cada linha;
- formulário fiscal mínimo para temporário;
- opção separada de cadastro rápido permanente;
- revisão deve identificar visualmente itens temporários.

### Riscos a controlar

- garantir imutabilidade do snapshot após início da emissão;
- impedir snapshot vazio ou inconsistente;
- normalizar NCM e unidade antes do builder;
- evitar códigos temporários duplicados na mesma nota;
- manter fallback para dados históricos;
- garantir que retries produzam o mesmo payload mesmo após edição do catálogo.

## 9. Testes recomendados para a implementação

1. emissão manual somente com produto cadastrado permanece igual;
2. produto temporário não cria `Product`;
3. produto temporário não cria `StockProduct` nem movimentação;
4. nota pode misturar produtos cadastrados e temporários;
5. múltiplos temporários são preservados na ordem;
6. código obrigatório;
7. NCM deve possuir oito dígitos;
8. unidade e origem CST válidas;
9. quantidade e valor maiores que zero;
10. CEST opcional é incluído somente quando informado;
11. payload do temporário é idêntico ao contrato de um produto cadastrado equivalente;
12. classe tributária continua vindo de `NfeRequest`;
13. edição posterior do `Product` não altera o snapshot já registrado;
14. retry gera o mesmo hash/payload;
15. itens históricos sem snapshot continuam emitindo pelo fallback;
16. permissões de catálogo continuam aplicadas apenas ao cadastro permanente.

## 10. Decisão recomendada

Adotar a **Alternativa D: evoluir `NfeRequestManualItem` com origem e snapshot fiscal**.

Não criar produto temporário no catálogo. Não criar model paralelo. Não persistir dados apenas em sessão. Não alterar o contrato Webmania.

A solução mantém uma única entrada para o motor fiscal:

```text
Produto cadastrado ── snapshot ──┐
                                 ├─ NfeRequestManualItem ─ build_nfe_payload ─ FiscalEmissionAttempt ─ Webmania
Produto temporário ─ snapshot ───┘
```

Essa é a menor alteração que preserva rastreabilidade, idempotência, compatibilidade e ausência de efeitos colaterais no catálogo e no estoque.
