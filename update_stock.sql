-- ============================================================
-- Script de atualizacao de estoque
-- Gerado a partir do Relatorio de Produtos em Estoque
-- ============================================================

-- CONFIGURE O WORKSHOP_ID AQUI:
SET session my.workshop_id = '1';

BEGIN;

-- Garantir que o grupo 'Estoque Geral' existe
INSERT INTO catalog_cataloggroup (workshop_id, name)
SELECT CAST(current_setting('my.workshop_id') AS BIGINT), 'Estoque Geral'
WHERE NOT EXISTS (
    SELECT 1 FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
);

-- Produto: 55227802 - REPARO DE BICOS INJETORES
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55227802',
        'REPARO DE BICOS INJETORES',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        18.46,
        'BRL',
        28.65,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KTPCTF72 - KIT PISTÃO CAMBIO TF72
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KTPCTF72',
        'KIT PISTÃO CAMBIO TF72',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KTCAT7F2 - KIT VEDAÇÕES CAMBIO AUTOMATICO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KTCAT7F2',
        'KIT VEDAÇÕES CAMBIO AUTOMATICO',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CRC52001 - CUBO RODA TRASEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CRC52001',
        'CUBO RODA TRASEIRA',
        '',
        '',
        '',
        '',
        'H2',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        440.28,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KTDME18 - KIT DISTRIBUIÇÃO MOTOR E-TORQ  1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KTDME18',
        'KIT DISTRIBUIÇÃO MOTOR E-TORQ  1.8',
        '',
        '',
        '',
        '',
        '',
        'TORO  (2015 A 2021 )  - RENEGADE ( 2015 A 2020)    REF PEÇAS    55280700  55226611  55226613  46348199  55284366  46343389',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        186.44,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KTCCT13 - KIT CORRENTE COMANDO T270 1.3 TURBO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KTCCT13',
        'KIT CORRENTE COMANDO T270 1.3 TURBO',
        '',
        '',
        '',
        '',
        'A9',
        'GUIA CORRENTE COD 55267969  TENSOR COD 5528226  CORRENTE 55282222  TENSOR CORRENTE 55282750  TENSOR CORRENTE 55282225',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        500.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: A022V175 - MODULO DIREÇÃO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'A022V175',
        'MODULO DIREÇÃO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1300.00,
        'BRL',
        4300.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 68249614AA - MODULO TCM DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '68249614AA',
        'MODULO TCM DIESEL',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1300.00,
        'BRL',
        4300.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55258488 - CAPA CORREIA DIESEL SEMI NOVA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55258488',
        'CAPA CORREIA DIESEL SEMI NOVA',
        '',
        '',
        '',
        '',
        '',
        'DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        399.99,
        'BRL',
        799.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46352132 - DIFERENCIAL TRASEIRO REMANUFATURADO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46352132',
        'DIFERENCIAL TRASEIRO REMANUFATURADO',
        '',
        '',
        '',
        '',
        '',
        'TODOS 4X4',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1011.75,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 0204J0152D - HIDROVACUO FREIO COMPASS DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '0204J0152D',
        'HIDROVACUO FREIO COMPASS DIESEL',
        '',
        '',
        '',
        '',
        '',
        'COMPASS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1340.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52166261 - PIVO INFERIOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52166261',
        'PIVO INFERIOR',
        '',
        '',
        '',
        '',
        '',
        'TORO DIESEL 4X4 A PARTIR 2022    PIVO DE 21MM',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        223.01,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52239746 - MANGUEIRA RADIADOR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52239746',
        'MANGUEIRA RADIADOR T270',
        '',
        '',
        '',
        '',
        '',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        490.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 0001170422 SEG - MOTOR DE PARTIDA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '0001170422 SEG',
        'MOTOR DE PARTIDA',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1210.14,
        'BRL',
        1927.57,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1002233 - VALVULA TERMOSTATICA COM CARCAÇA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1002233',
        'VALVULA TERMOSTATICA COM CARCAÇA',
        '',
        '',
        '',
        '',
        'E3',
        'COMPASS 2.0 FLEX',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        194.50,
        'BRL',
        727.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2728 - CHAVE DE IMPACTO - SGT-7503A - 0703750301
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2728',
        'CHAVE DE IMPACTO - SGT-7503A - 0703750301',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1460.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 3094 - ROLAMENTO SEMI EIXO TULIPA 35X55X10
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '3094',
        'ROLAMENTO SEMI EIXO TULIPA 35X55X10',
        '',
        '',
        '',
        '',
        '',
        '35X55X10 COMPASS 2.0',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        75.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 3613 - SVA-003613 MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '3613',
        'SVA-003613 MM',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        6.14,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    10,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 8958 - KIT VEDAÇÕES CAMBIO AUTOMATICO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '8958',
        'KIT VEDAÇÕES CAMBIO AUTOMATICO',
        '',
        '',
        '',
        '',
        '',
        '',
        'SUL VEDACOES',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        10.32,
        'BRL',
        1309.70,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 10100 - PASTA DE ESMIRILHAR VALV.
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '10100',
        'PASTA DE ESMIRILHAR VALV.',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        30.40,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1,04E+11 - RETENTOR DO VOLANTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1,04E+11',
        'RETENTOR DO VOLANTE',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'VEICULO DIESEL',
        'BASTOS',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        138.29,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 17802 - COLA ADESIVO ELIMINA JUNTAS ALTA TEMP - PRETO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '17802',
        'COLA ADESIVO ELIMINA JUNTAS ALTA TEMP - PRETO',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        67.42,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 19790 - RADIADOR AR QUENTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '19790',
        'RADIADOR AR QUENTE',
        '',
        '',
        '',
        '',
        'A12',
        'COMPASS  RENEGADE  TORO DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        399.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 27306 - BOMBA D AGUA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '27306',
        'BOMBA D AGUA',
        '',
        '',
        '',
        '',
        'C16',
        'COMPASS FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        217.80,
        'BRL',
        315.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 29573 - KIT BATENTE AMORTECEDOR TRASEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '29573',
        'KIT BATENTE AMORTECEDOR TRASEIRO',
        '',
        '',
        '',
        '',
        'G2',
        'COMPASS, RENEGADE',
        'SAMPEL',
        'KIT',
        '',
        '',
        0,
        'REVENDA',
        0,
        229.36,
        'BRL',
        1260.88,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 34486 - BOMBA D AGUA COMPLETA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '34486',
        'BOMBA D AGUA COMPLETA',
        '',
        '',
        '',
        '',
        'PARTE CIMA PRATELEIRA',
        'TORO RENEGADE FLEX 1.8 NAO APLICA NO DIESEL NEM 1.3 TURBO',
        'GENUINE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        453.36,
        'BRL',
        930.06,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 05047529ac - POLIA VARIAVEL DE ESCAPE JEEP COMPASS 2.0 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '05047529ac',
        'POLIA VARIAVEL DE ESCAPE JEEP COMPASS 2.0 FLEX',
        '',
        '',
        '',
        '',
        'H5',
        'MOTOR 2.0 FLEX',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        250.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 05047531ab - POLIA VARIAVEL ADMISSãO COMPASS 2.0 FLEX 2017
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '05047531ab',
        'POLIA VARIAVEL ADMISSãO COMPASS 2.0 FLEX 2017',
        '',
        '',
        '',
        '',
        'H5',
        'MOTOR 2.0 FLEX',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        250.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5178 - NUCLEO DE VALVULA AR CONDICIONADO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5178',
        'NUCLEO DE VALVULA AR CONDICIONADO',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        3.00,
        'BRL',
        4.15,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    20,
    5,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 9,24E+11 - JOGO DE JUNTAS DO MOTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '9,24E+11',
        'JOGO DE JUNTAS DO MOTOR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        586.00,
        'BRL',
        1082.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 0W30 - OLEO DO MOTOR MOPAR MAXPRO SYNTHETIC 0W30
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '0W30',
        'OLEO DO MOTOR MOPAR MAXPRO SYNTHETIC 0W30',
        '',
        '',
        '',
        '',
        'E12',
        'TORO, COMPASS E RENAGADE MOTOR 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        10.98,
        'BRL',
        98.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    12,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1000523 - CHAVE PARA CODFICAÇÃO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1000523',
        'CHAVE PARA CODFICAÇÃO',
        '',
        '',
        '',
        '',
        'GAVETA MESA',
        'SOMENTE CHAVE DE PRESENÇA',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        300.00,
        'BRL',
        600.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 100230654 - FRISO EXTENSAO L/D FIAT TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '100230654',
        'FRISO EXTENSAO L/D FIAT TORO',
        '',
        '',
        '',
        '',
        '',
        'FIAT TORO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        220.00,
        'BRL',
        490.80,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 100248574 - PAINEL DE RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '100248574',
        'PAINEL DE RENEGADE',
        '',
        '',
        '',
        '',
        '',
        'P TESTE',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        700.00,
        'BRL',
        700.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1124 - ROLAMENTO DO TENSOR DA CORREIA  AUXILIAR 65MM FIXO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1124',
        'ROLAMENTO DO TENSOR DA CORREIA  AUXILIAR 65MM FIXO',
        '',
        '',
        '',
        '',
        'B4',
        'TODOS',
        'NYTRON',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        44.72,
        'BRL',
        131.55,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 117PT.0001 - PASTA DE MONTAGEM DE MOTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '117PT.0001',
        'PASTA DE MONTAGEM DE MOTOR',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        58.05,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 12000745 - BATERIA VEICULOS 70AH MOURA ( BMW)
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '12000745',
        'BATERIA VEICULOS 70AH MOURA ( BMW)',
        '',
        '',
        '',
        '',
        '',
        'COMPASS E RENEGADE DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1734.00,
        'BRL',
        681.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 123466 - FLUIDO DE TRANSMISSAO AUTOMATICA DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '123466',
        'FLUIDO DE TRANSMISSAO AUTOMATICA DIESEL',
        '',
        '',
        '',
        '',
        'E10',
        'TORO, COMPASS E RENAGADE TODOS',
        'VALVOLINE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        73.03,
        'BRL',
        145.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    12,
    24,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1234666 - FLUIDO DE TRANSMISSÃO AUTOMATICA ATF
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1234666',
        'FLUIDO DE TRANSMISSÃO AUTOMATICA ATF',
        '',
        '',
        '',
        '',
        'E11',
        'CARROS FLEX',
        'MOBIL',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        40.15,
        'BRL',
        142.16,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    58,
    9,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 12762 - POLIA CORREIA  ALTERNADOR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '12762',
        'POLIA CORREIA  ALTERNADOR T270',
        '',
        '',
        '',
        '',
        'B1',
        'COMPASS, TORO E RENEGADE T270',
        'ZEM',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        31.62,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1330Z3 - DEP  CENTRAL  WM COMPLETO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1330Z3',
        'DEP  CENTRAL  WM COMPLETO',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        469.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 13383 - ROLAMENTO DE APOIO DA CORREIA AUXILIAR (FIXO)
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '13383',
        'ROLAMENTO DE APOIO DA CORREIA AUXILIAR (FIXO)',
        '',
        '',
        '',
        '',
        'B2',
        'TORO E RENEGADE 1.8 FLEX',
        'ZEN',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        101.27,
        'BRL',
        205.46,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 13574 - ROLAMENTO DE APOIO DA CORREIA AUXILIAR 70MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '13574',
        'ROLAMENTO DE APOIO DA CORREIA AUXILIAR 70MM',
        '',
        '',
        '',
        '',
        'B3',
        'COMPASS   2.0 FLEX',
        'ZEN',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        40.96,
        'BRL',
        158.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 13602 - ROLAMENTO DE APOIO DA CORREIA AUXILIAR ESTRIADO 6PK (FIXO)
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '13602',
        'ROLAMENTO DE APOIO DA CORREIA AUXILIAR ESTRIADO 6PK (FIXO)',
        '',
        '',
        '',
        '',
        'B2',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL (NÃO APLICA VEÍCULOS FLEX)',
        'ZEN',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        83.22,
        'BRL',
        170.32,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 142191 - JUNTA DO COLETOR DE ADMISSÃO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '142191',
        'JUNTA DO COLETOR DE ADMISSÃO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        'BASTOS',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        101.67,
        'BRL',
        225.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 143794 - KIT JUNTA TROCADOR CALOR MOTOR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '143794',
        'KIT JUNTA TROCADOR CALOR MOTOR DIESEL',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.99,
        'BRL',
        59.90,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 1507705 - TERMINAL NEGATIVO DE BATERIA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '1507705',
        'TERMINAL NEGATIVO DE BATERIA',
        '',
        '',
        '',
        '',
        'ARMÁRIO DE MADEIRA',
        'RENEGADE 1.8',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        10.02,
        'BRL',
        65.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    11,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 15173411SL - JUNTA DA TAMPA DE VALVULA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '15173411SL',
        'JUNTA DA TAMPA DE VALVULA',
        '',
        '',
        '',
        '',
        'E15',
        'COMPASS FLEX',
        'JUNTAS LIMA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        256.10,
        'BRL',
        582.22,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 155252942 - JUNTA CABECOTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '155252942',
        'JUNTA CABECOTE',
        '',
        '',
        '',
        '',
        'E13',
        'TORO, COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        697.38,
        'BRL',
        1638.90,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 16013 - RADIADOR CONDENSADOR DO AR CONDICIONADO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '16013',
        'RADIADOR CONDENSADOR DO AR CONDICIONADO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE FLEX',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        620.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 16221 - RADIADOR AQUECIMENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '16221',
        'RADIADOR AQUECIMENTO',
        '',
        '',
        '',
        '',
        '',
        'TORO / JEEP COMPASS / RENEGADE 2016',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        377.99,
        'BRL',
        809.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 172030 - RETENTOR POLIA VIRABREQUIM 1.3 TURBO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '172030',
        'RETENTOR POLIA VIRABREQUIM 1.3 TURBO',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'T270',
        'BASTOS',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        73.91,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 173 - KIT DE DISCO COMPOSITE CAMBIO TF72
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '173',
        'KIT DE DISCO COMPOSITE CAMBIO TF72',
        '',
        '',
        '',
        '',
        'H3',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        734.44,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 177 - RETENTOR DO DIFERECIAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '177',
        'RETENTOR DO DIFERECIAL',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'VEICULOS 4X4    MEDIDAS 30x47x7',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.20,
        'BRL',
        36.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 178956 - BIELETA DIANTEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '178956',
        'BIELETA DIANTEIRA',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENEGADE',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        43.04,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    10,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 18.18 24 - ARRUELA VEDAÇAO DE BUJÃO DE CARTER DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '18.18 24',
        'ARRUELA VEDAÇAO DE BUJÃO DE CARTER DIESEL',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS VEICULOS DIESEL',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1.16,
        'BRL',
        25.57,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    49,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 184823 - COXIM AMORTECEDOR SUSPENSAO TRASEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '184823',
        'COXIM AMORTECEDOR SUSPENSAO TRASEIRO',
        '',
        '',
        '',
        '',
        'G4',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        282.28,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 19X27MM - ABRAÇADEIRA 19X27MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '19X27MM',
        'ABRAÇADEIRA 19X27MM',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TROCADOR DE CALOR E BOMBA DAGUA',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.79,
        'BRL',
        10.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    31,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2.K68218057LB - FLUIDO TRANSMISSAO AUTOMATICA ATF+4 MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2.K68218057LB',
        'FLUIDO TRANSMISSAO AUTOMATICA ATF+4 MOPAR',
        '',
        '',
        '',
        '',
        '',
        'CARROS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        64.00,
        'BRL',
        200.32,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2,00E+12 - JOGO DE BRONZINA DE MANCAL E BIELA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2,00E+12',
        'JOGO DE BRONZINA DE MANCAL E BIELA',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1000.00,
        'BRL',
        1300.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2,00E+12 - BOMBA DE OLEO COM SOLENOIDE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2,00E+12',
        'BOMBA DE OLEO COM SOLENOIDE',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        900.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2,00E+12 - ESTOPA MISTA 10KG
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2,00E+12',
        'ESTOPA MISTA 10KG',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        85.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 200731 - RETENTOR DA BOMBA DE ALTA PRESSAO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '200731',
        'RETENTOR DA BOMBA DE ALTA PRESSAO DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL (MEDIDA 19,4X31X7 )    31x41x7',
        'SAV',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        21.07,
        'BRL',
        378.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    10,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 205241 - BRAÇO AXIAL ELETRICO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '205241',
        'BRAÇO AXIAL ELETRICO',
        '',
        '',
        '',
        '',
        '',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        61.47,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 205318 - BRAÇO AXIAL ELETRICO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '205318',
        'BRAÇO AXIAL ELETRICO',
        '',
        '',
        '',
        '',
        '',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        39.35,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 20W50 - OLEO DE MOTOR PARA LIMPEZA  20W50
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '20W50',
        'OLEO DE MOTOR PARA LIMPEZA  20W50',
        '',
        '',
        '',
        '',
        '',
        'TODOS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        21.68,
        'BRL',
        43.36,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 20W50 PREMIUM - OLEO DO MOTOR 20W50
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '20W50 PREMIUM',
        'OLEO DO MOTOR 20W50',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.96,
        'BRL',
        21.86,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 211S02 - FLUIDO DE FREIO DOT4 TIRRENO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '211S02',
        'FLUIDO DE FREIO DOT4 TIRRENO',
        '',
        '',
        '',
        '',
        'E5',
        'COMPASS, TORO E RENEGADE',
        'TIRRENO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        52.17,
        'BRL',
        56.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 219876 - FILTRO CABINE -
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '219876',
        'FILTRO CABINE -',
        '',
        '',
        '',
        '',
        'D2',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        14.04,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 226504 - CUBO RODA DIANTEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '226504',
        'CUBO RODA DIANTEIRA',
        '',
        '',
        '',
        '',
        '',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        371.47,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 22X32MM - ABRAÇADEIRA 22X32MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '22X32MM',
        'ABRAÇADEIRA 22X32MM',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        '1 BOMBA DA AGUA 1 VALVULA TERMOSTATICA',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        3.47,
        'BRL',
        10.31,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    25,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2323 - REPARO DE BICOS INJETORES FLEX MARELLI TORO E RENEGADE 1.8 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2323',
        'REPARO DE BICOS INJETORES FLEX MARELLI TORO E RENEGADE 1.8 FLEX',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'MARELLI',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        10.83,
        'BRL',
        45.12,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 23600165 - JUNTA HOMOCINETICA COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '23600165',
        'JUNTA HOMOCINETICA COMPASS',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        221.64,
        'BRL',
        222.77,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 237616 - TRIZETA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '237616',
        'TRIZETA',
        '',
        '',
        '',
        '',
        'A16',
        '22 DENTES ELO 32',
        'AUTOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        45.41,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 240000 - PALHETA LIMPADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '240000',
        'PALHETA LIMPADOR',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        25.83,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2525131 - LAMPADA FAROL 12V 55W H4 HELLA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2525131',
        'LAMPADA FAROL 12V 55W H4 HELLA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        10.76,
        'BRL',
        54.32,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 265613 - COXIM MOTOR LD DIR - AMX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '265613',
        'COXIM MOTOR LD DIR - AMX',
        '',
        '',
        '',
        '',
        '',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        297.63,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 2827NA - LAMPADA DE SETA DOS RETROVISORES DIANTEIRO (PINGO)
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '2827NA',
        'LAMPADA DE SETA DOS RETROVISORES DIANTEIRO (PINGO)',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        4.97,
        'BRL',
        25.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 303FU1 - ADTIVO RADIADOR LARANJA ORIGINAL TIRRENO JEEP OTC
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '303FU1',
        'ADTIVO RADIADOR LARANJA ORIGINAL TIRRENO JEEP OTC',
        '',
        '',
        '',
        '',
        'E6',
        'TORO, COMPASS E RENAGADE TODOS',
        'TIRRENO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        38.31,
        'BRL',
        84.86,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    49,
    12,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 304446 - SL50099 SILICONE OXIMICO CINZA 85G - AMX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '304446',
        'SL50099 SILICONE OXIMICO CINZA 85G - AMX',
        '',
        '',
        '',
        '',
        '',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        23.86,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 321PT (E-01) - ESTRADO PRETO 13X41X82
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '321PT (E-01)',
        'ESTRADO PRETO 13X41X82',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        99.35,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 322789 - FORRO PORTA DIANTEIRA LE (USADO - FIATOROT
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '322789',
        'FORRO PORTA DIANTEIRA LE (USADO - FIATOROT',
        '',
        '',
        '',
        '',
        '',
        'FIAT TORO',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        395.00,
        'BRL',
        490.80,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 32X44MM - ABRAÇADEIRA 32X44MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '32X44MM',
        'ABRAÇADEIRA 32X44MM',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'USO GERAL',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        4.60,
        'BRL',
        12.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    15,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 332511 - KIT PASTILHA DE FREIO DIANTEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '332511',
        'KIT PASTILHA DE FREIO DIANTEIRA',
        '',
        '',
        '',
        '',
        'A14',
        'TODOS OS VEICULOS',
        'COBREG',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        164.87,
        'BRL',
        458.87,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 333011408 - SEMI EIXO COMPLETO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '333011408',
        'SEMI EIXO COMPLETO',
        '',
        '',
        '',
        '',
        'PARTE BAIXO PRATELEIRA',
        'RENEGADE 1.8',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        949.57,
        'BRL',
        768.92,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 37081 - BROZINAS DE BIELETA STANDER
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '37081',
        'BROZINAS DE BIELETA STANDER',
        '',
        '',
        '',
        '',
        'B8',
        'RENEGADE 1.8',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        171.72,
        'BRL',
        343.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 39172 - JOGO DE ANEIS DOS PISTOES STANDER
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '39172',
        'JOGO DE ANEIS DOS PISTOES STANDER',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        135.81,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46340481 - JUNTA DA BOMBA DE VACUO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46340481',
        'JUNTA DA BOMBA DE VACUO',
        '',
        '',
        '',
        '',
        '',
        '1.3 TURBO FLEX',
        'Marinho Parts',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        220.00,
        'BRL',
        369.56,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 41070600 - KIT PISTÃO STD
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '41070600',
        'KIT PISTÃO STD',
        '',
        '',
        '',
        '',
        'F7',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 41070620 - KIT PISTÃO 040
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '41070620',
        'KIT PISTÃO 040',
        '',
        '',
        '',
        '',
        'F6',
        'COMPASS, TORO E RENEGADE DIESEL',
        'RHEINMETAL',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        2473.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 44X57MM - ABRAÇADEIRA 44X57MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '44X57MM',
        'ABRAÇADEIRA 44X57MM',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'USO GERAL',
        'IMPORTADO',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        3.52,
        'BRL',
        12.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46336064 - BOMBA OLEO MOTOR DIESEL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46336064',
        'BOMBA OLEO MOTOR DIESEL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS, RENEGADE, TORO DIESEL',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        1499.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46336109 - SOLENOIDE DE PRESSAO DA BOMBA DE OLEO DO MOTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46336109',
        'SOLENOIDE DE PRESSAO DA BOMBA DE OLEO DO MOTOR',
        '',
        '',
        '',
        '',
        'A9',
        'COMPASS E TORO DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1002.27,
        'BRL',
        1320.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46336161 - VELA IGNICAO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46336161',
        'VELA IGNICAO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B4',
        'RENE / COMPASS / TORO 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        107.40,
        'BRL',
        230.57,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46337579 - SENSOR DE PRESSAO OLEO DE ALTA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46337579',
        'SENSOR DE PRESSAO OLEO DE ALTA',
        '',
        '',
        '',
        '',
        'C8',
        'TODOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        195.35,
        'BRL',
        596.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46338361 - TURBINA DO MOTOR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46338361',
        'TURBINA DO MOTOR T270',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS 1.3 TURBO',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.00,
        'BRL',
        3500.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46339032 - ATUADOR VALVULA MULTI AIR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46339032',
        'ATUADOR VALVULA MULTI AIR T270',
        '',
        '',
        '',
        '',
        '',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        389.99,
        'BRL',
        750.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46343389 - RODA FONICA COMANDO E-TORQ 1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46343389',
        'RODA FONICA COMANDO E-TORQ 1.8',
        '',
        '',
        '',
        '',
        '',
        'C/FURO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        299.99,
        'BRL',
        599.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46344869 - BOBINA IGNICAO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46344869',
        'BOBINA IGNICAO',
        '',
        '',
        '',
        '',
        'C4',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        85.50,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46345319 - JUNTA DO CABEÇOTE ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46345319',
        'JUNTA DO CABEÇOTE ORIGINAL',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.3 TURBO',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        219.22,
        'BRL',
        470.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46345895 - RETENTOR BOMBA OLEO  T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46345895',
        'RETENTOR BOMBA OLEO  T270',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        96.20,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46346172 - TROCADOR DE CALOR DO MOTOR 1.3
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46346172',
        'TROCADOR DE CALOR DO MOTOR 1.3',
        '',
        '',
        '',
        '',
        'A10',
        'Renegade Compass Toro 1.3 Original',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        389.99,
        'BRL',
        779.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46346508 - VALVULA TERMOSTATICA 1.3  TURBO T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46346508',
        'VALVULA TERMOSTATICA 1.3  TURBO T270',
        '',
        '',
        '',
        '',
        'A8',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        610.00,
        'BRL',
        920.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46347164 - SENSOR FASE COMANDO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46347164',
        'SENSOR FASE COMANDO',
        '',
        '',
        '',
        '',
        'B7',
        'RENEGADE',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        225.00,
        'BRL',
        225.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46347605 - FILTRO DE OLEO MOTOR T270 ORIGINAL MOPAR 1.3 T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46347605',
        'FILTRO DE OLEO MOTOR T270 ORIGINAL MOPAR 1.3 T270',
        '',
        '',
        '',
        '',
        'C3',
        'MOTOR JEEP 1.3 T270 COMPASS/RENEGADE',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        73.99,
        'BRL',
        159.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46348528 - KIT PISTAO ANEIS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46348528',
        'KIT PISTAO ANEIS',
        '',
        '',
        '',
        '',
        '',
        'VEICULO T270 COMANDER, COMPASS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        297.50,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46348552 - BOMBA AGUA MOTOR T270 ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46348552',
        'BOMBA AGUA MOTOR T270 ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'E4',
        'RENEGADE 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        270.99,
        'BRL',
        639.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46348565 - JOGO DE BRONZINA BIELA 1.3
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46348565',
        'JOGO DE BRONZINA BIELA 1.3',
        '',
        '',
        '',
        '',
        '',
        'COD 46348565 AZUL  COD 46348562 AZUL',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        39.98,
        'BRL',
        1300.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46348572 - TENSOR CORREIA  ALTERNADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46348572',
        'TENSOR CORREIA  ALTERNADOR',
        '',
        '',
        '',
        '',
        'A7',
        'T270',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        189.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46348847 - VELA IGNICAO ORIGINAL MOPAR RENEGADE FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46348847',
        'VELA IGNICAO ORIGINAL MOPAR RENEGADE FLEX',
        '',
        '',
        '',
        '',
        'B1',
        'RENEGADE FLEX 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        80.68,
        'BRL',
        196.36,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46349166 - TAMPA BOMBA AGUA T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46349166',
        'TAMPA BOMBA AGUA T270',
        '',
        '',
        '',
        '',
        'A14',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        155.22,
        'BRL',
        129.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46349214 - BOMBA DE VACUO MOTOR DIESEL ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46349214',
        'BOMBA DE VACUO MOTOR DIESEL ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'A11',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1052.28,
        'BRL',
        1795.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46350754 - PARAFUSO DO CABEÇOTE  1.3 TURBO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46350754',
        'PARAFUSO DO CABEÇOTE  1.3 TURBO',
        '',
        '',
        '',
        '',
        'B13',
        'RENEGADE 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        22.69,
        'BRL',
        430.60,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    20,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46350837 - SENSOR TEMPERATURA GASES DE ESCAPA MENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46350837',
        'SENSOR TEMPERATURA GASES DE ESCAPA MENTO',
        '',
        '',
        '',
        '',
        'A8',
        'VEICULOS DIESEL',
        'IGUAÇU',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        210.96,
        'BRL',
        450.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46350907001 - KIT CORREIA DENTADA COMPLETO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46350907001',
        'KIT CORREIA DENTADA COMPLETO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'E2',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        629.97,
        'BRL',
        1450.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46352317 - SONDA LAMBDA PRE CATALISADORA T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46352317',
        'SONDA LAMBDA PRE CATALISADORA T270',
        '',
        '',
        '',
        '',
        '',
        '1.3 TURBO',
        'NTK',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        558.00,
        'BRL',
        558.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 463527330 - CHICOTE DA CAIXA DE TRASFERENCIA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '463527330',
        'CHICOTE DA CAIXA DE TRASFERENCIA',
        '',
        '',
        '',
        '',
        'G8',
        'TODOS 4X4',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        34.59,
        'BRL',
        220.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46357204 - JUNTA DE CABEÇOTE T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46357204',
        'JUNTA DE CABEÇOTE T270',
        '',
        '',
        '',
        '',
        'E16',
        'COMPASS E RENEGADE T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        229.71,
        'BRL',
        439.80,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 46360230 - BICO INJETOR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '46360230',
        'BICO INJETOR T270',
        '',
        '',
        '',
        '',
        '',
        'T270 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        489.99,
        'BRL',
        939.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 4884483AA - VáLVULA VVT SOLENOIDE ADMISSãO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '4884483AA',
        'VáLVULA VVT SOLENOIDE ADMISSãO',
        '',
        '',
        '',
        '',
        'A9',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        250.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 4884695AA - VáLVULA VVT SOLENOIDE ESCAPE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '4884695AA',
        'VáLVULA VVT SOLENOIDE ESCAPE',
        '',
        '',
        '',
        '',
        'A9',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        559.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 50047057 - BUJÃO CARTER 1.3 TURBO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '50047057',
        'BUJÃO CARTER 1.3 TURBO',
        '',
        '',
        '',
        '',
        'ARMÁRIO',
        'TORO 1.3 TURBO',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        26.78,
        'BRL',
        55.56,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5007 - LAMPADA 12V
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5007',
        'LAMPADA 12V',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'CX',
        '',
        '',
        0,
        'REVENDA',
        0,
        15.06,
        'BRL',
        27.10,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    19,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 50160503 - BODY COMPUTER
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '50160503',
        'BODY COMPUTER',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2022 P/ CIMA',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1580.00,
        'BRL',
        6050.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5048119 - TROCADOR DE CALOR DO MOTOR COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5048119',
        'TROCADOR DE CALOR DO MOTOR COMPASS',
        '',
        '',
        '',
        '',
        'E1',
        'COMPASS 2.0 FLEX E TORO 2.4 FLEX',
        'RAKTAS',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        322.10,
        'BRL',
        1489.14,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 50512681 - INTERRUPTOR DO PEDAL DE FREIO MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '50512681',
        'INTERRUPTOR DO PEDAL DE FREIO MOPAR',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        50.00,
        'BRL',
        180.75,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51757132 - COMUTADOR 5 PINOS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51757132',
        'COMUTADOR 5 PINOS',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        133.00,
        'BRL',
        4300.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51890258 - ANTENA RADIO AM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51890258',
        'ANTENA RADIO AM',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE, FIA TORO',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        164.50,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51959809 - BUCHA DA BARRA TRASEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51959809',
        'BUCHA DA BARRA TRASEIRA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'RENEGADE 2.0 DIESEL',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        32.50,
        'BRL',
        82.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51959953 - RESERVATORIO DE PARTIDA A FRIO ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51959953',
        'RESERVATORIO DE PARTIDA A FRIO ORIGINAL',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS 1.8',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        312.00,
        'BRL',
        930.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51961569 - BOMBA DE COMBUSTIVEL ORGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51961569',
        'BOMBA DE COMBUSTIVEL ORGINAL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1299.99,
        'BRL',
        1949.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51963989 - SENSOR DO OCUPANTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51963989',
        'SENSOR DO OCUPANTE',
        '',
        '',
        '',
        '',
        'H3',
        'TODOS OS VEICULOS',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        300.00,
        'BRL',
        1250.31,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51965906 - RADIADOR AGUA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51965906',
        'RADIADOR AGUA',
        '',
        '',
        '',
        '',
        '',
        'COMPASS DIESEL',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        1299.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51966254 - MANGUEIRA AR QUENTE DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51966254',
        'MANGUEIRA AR QUENTE DIESEL',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        246.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51966321 - MANGUEIRA DO INTERCOOLE LADO ESQUERDO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51966321',
        'MANGUEIRA DO INTERCOOLE LADO ESQUERDO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        683.32,
        'BRL',
        649.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51973250 - CAIXA DE FILTRO DE AR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51973250',
        'CAIXA DE FILTRO DE AR',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        299.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51975617 - CONDUTO AR (TUBO DE AR DA TUBINA) ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51975617',
        'CONDUTO AR (TUBO DE AR DA TUBINA) ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'D14',
        'COMPASS RENEGADE TORO TODOS MENOS 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        260.28,
        'BRL',
        1243.04,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51977574 - FILTRO DE AR DO MOTOR ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51977574',
        'FILTRO DE AR DO MOTOR ORIGINAL',
        '',
        '',
        '',
        '',
        'D1',
        'TODOS RENEGADE, TORO E COMPASS EXCETO MOTORES 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        66.91,
        'BRL',
        185.26,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51977753 - RADIADOR DO CAMBIO AUTOMATICO MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51977753',
        'RADIADOR DO CAMBIO AUTOMATICO MOPAR',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE E COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2283.68,
        'BRL',
        1911.60,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51979493 - SUPORTE PARACHOQUE FIAT TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51979493',
        'SUPORTE PARACHOQUE FIAT TORO',
        '',
        '',
        '',
        '',
        '',
        'FIAT TORO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        78.00,
        'BRL',
        490.80,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 51987829 - RADIADOR AGUA 1.8 E-TORQ RENEGADE TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '51987829',
        'RADIADOR AGUA 1.8 E-TORQ RENEGADE TORO',
        '',
        '',
        '',
        '',
        'PARTE DE CIMA PRATELEIRA',
        'RENEGADE E TORO 1.8 FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        844.29,
        'BRL',
        1450.65,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52004316 - COXIM BIELA CAMBIO INFERIOR FLEX ORIGINAL 1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52004316',
        'COXIM BIELA CAMBIO INFERIOR FLEX ORIGINAL 1.8',
        '',
        '',
        '',
        '',
        'C15',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        121.93,
        'BRL',
        767.10,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52008239 - RESERVATORIO AGUA LIMPADOR PARABRISA RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52008239',
        'RESERVATORIO AGUA LIMPADOR PARABRISA RENEGADE',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        139.99,
        'BRL',
        160.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52016558 - BARRA ESTABILIZADORA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52016558',
        'BARRA ESTABILIZADORA',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        475.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52017651 - AMORTECEDOR PORTA MALAS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52017651',
        'AMORTECEDOR PORTA MALAS',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        99.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52019353 - ANTENA RADIO FREQUENCIA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52019353',
        'ANTENA RADIO FREQUENCIA',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE DIESEL',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        30.00,
        'BRL',
        470.31,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52024641 - MANGUEIRA SAIDA AR QUENTE DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52024641',
        'MANGUEIRA SAIDA AR QUENTE DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TODOS VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        514.39,
        'BRL',
        501.59,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52024644 - MANGUEIRA RETORNO RESERVATÓRIO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52024644',
        'MANGUEIRA RETORNO RESERVATÓRIO',
        '',
        '',
        '',
        '',
        'D13',
        'FLEX',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        149.99,
        'BRL',
        149.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52042925 - COXIM DO CAMBIO SUPERIOR LADO ESQUERDO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52042925',
        'COXIM DO CAMBIO SUPERIOR LADO ESQUERDO',
        '',
        '',
        '',
        '',
        'B9',
        'COMPASS RENEGADE TORO 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        371.86,
        'BRL',
        1154.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52043358 - SEMI EIXO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52043358',
        'SEMI EIXO DIESEL',
        '',
        '',
        '',
        '',
        'PARTE BAIXO PRATELEIRA',
        'FIAT TORO',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        520.00,
        'BRL',
        900.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52043705 - AMORTECEDOR TRASEIRO RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52043705',
        'AMORTECEDOR TRASEIRO RENEGADE',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE DIESEL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        444.41,
        'BRL',
        460.84,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52044907 - MANGUEIRA INFERIOR DE TURBINA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52044907',
        'MANGUEIRA INFERIOR DE TURBINA',
        '',
        '',
        '',
        '',
        'D13',
        'TORO, COMPASS E RENEGADE',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        226.31,
        'BRL',
        226.31,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52046009 - MANGUEIRA RETORNO RESERVATÓRIO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52046009',
        'MANGUEIRA RETORNO RESERVATÓRIO DIESEL',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        79.99,
        'BRL',
        79.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52049745 - COXIM HIDRAULICO MOTOR LADO DIREITO ORIGINAL MOPAR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52049745',
        'COXIM HIDRAULICO MOTOR LADO DIREITO ORIGINAL MOPAR DIESEL',
        '',
        '',
        '',
        '',
        'B10',
        'TORO E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        716.79,
        'BRL',
        1680.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52049747 - COXIM DO MOTOR LADO DIREITO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52049747',
        'COXIM DO MOTOR LADO DIREITO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'TORO 2.0',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        333.33,
        'BRL',
        980.36,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52052623 - COXIM HIDRAULICO MOTOR TORO/RENEGADE LADO DIREITO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52052623',
        'COXIM HIDRAULICO MOTOR TORO/RENEGADE LADO DIREITO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B12',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        410.37,
        'BRL',
        1134.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52065538 - RADIADOR AGUA TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52065538',
        'RADIADOR AGUA TORO',
        '',
        '',
        '',
        '',
        'PARTE CIMA PRATELEIRA',
        'TORO DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        970.00,
        'BRL',
        990.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52068337 - SENSOR PEDAL DE EMBREAGEM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52068337',
        'SENSOR PEDAL DE EMBREAGEM',
        '',
        '',
        '',
        '',
        '',
        'TORO E RENEGADE',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        275.29,
        'BRL',
        790.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52068553 - COXIM DO MOTOR LADO DIREITO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52068553',
        'COXIM DO MOTOR LADO DIREITO',
        '',
        '',
        '',
        '',
        'D9',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        894.05,
        'BRL',
        1780.36,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52078032 - COXIM DO MOTOR DIREITO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52078032',
        'COXIM DO MOTOR DIREITO',
        '',
        '',
        '',
        '',
        '',
        'FIAT TORO JEEP, RENEGADE 2.0 DISEL',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        399.66,
        'BRL',
        1600.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52080841 - FILTRO DE AR DO MOTOR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52080841',
        'FILTRO DE AR DO MOTOR T270',
        '',
        '',
        '',
        '',
        'B1',
        'RENEGADE  COMPASS TORO 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        75.76,
        'BRL',
        166.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52083749 - COXIM MOTOR LADO  ESQUERDO RENEGADE 1.8 MANUAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52083749',
        'COXIM MOTOR LADO  ESQUERDO RENEGADE 1.8 MANUAL',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        396.00,
        'BRL',
        1154.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52119552 - MANGUEIRA AR QUENTE RENEGADE 1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52119552',
        'MANGUEIRA AR QUENTE RENEGADE 1.8',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        48.65,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52129210 - MANGUEIRA INFERIOR RADIADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52129210',
        'MANGUEIRA INFERIOR RADIADOR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        456.30,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52129212 - MANGUEIRA INFERIOR RADIADOR DE AGUA MOTOR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52129212',
        'MANGUEIRA INFERIOR RADIADOR DE AGUA MOTOR DIESEL',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        156.79,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52136597 - MODULO AIRBAG
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52136597',
        'MODULO AIRBAG',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8 FLEX',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1300.00,
        'BRL',
        4300.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52156638 - PARAFUSO RODA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52156638',
        'PARAFUSO RODA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.71,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    13,
    5,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52157822 - COXIM SUPERIOR DO CAMBIO LADO ESQUERDO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52157822',
        'COXIM SUPERIOR DO CAMBIO LADO ESQUERDO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'C10',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        446.27,
        'BRL',
        1198.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52162685 - FILTRO DE COMBUSTIVEL ORIGINAL TORO/COMPASS/RENEGADE FLEX MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52162685',
        'FILTRO DE COMBUSTIVEL ORIGINAL TORO/COMPASS/RENEGADE FLEX MOPAR',
        '',
        '',
        '',
        '',
        'C1',
        'TORO, COMPASS E RENEGADE FLEX, NÃO APLICA VEÍCULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        24.13,
        'BRL',
        70.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52181779 - BOLSA DE AR BAG
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52181779',
        'BOLSA DE AR BAG',
        '',
        '',
        '',
        '',
        '',
        'FIAT TORO',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        2437.90,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52195041 - RESERVATORIO DE AGUA C/ TAMPA ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52195041',
        'RESERVATORIO DE AGUA C/ TAMPA ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'D12',
        'TORO, COMPASS E RENAGADE TODOS EXCETO VEÍCULOS 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        86.74,
        'BRL',
        271.17,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52197299 - BOMBA DE COMBUSTIVEL FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52197299',
        'BOMBA DE COMBUSTIVEL FLEX',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE, COMPASS E TORO FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1168.32,
        'BRL',
        1676.64,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52201888 - BIELETA DIANTEIRA MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52201888',
        'BIELETA DIANTEIRA MOPAR',
        '',
        '',
        '',
        '',
        'C5',
        'TODOS VEICULOS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        92.57,
        'BRL',
        200.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52205208 - COXIM DO MOTOR DIREITO T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52205208',
        'COXIM DO MOTOR DIREITO T270',
        '',
        '',
        '',
        '',
        '',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1248.00,
        'BRL',
        1600.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52205209 - COXIM DO MOTOR ESQUERDO T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52205209',
        'COXIM DO MOTOR ESQUERDO T270',
        '',
        '',
        '',
        '',
        '',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1042.50,
        'BRL',
        1600.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52205212 - COXIM BIELA INFERIOR ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52205212',
        'COXIM BIELA INFERIOR ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'C14',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL 68253029AC',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        308.98,
        'BRL',
        870.15,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 52225313 - LANTERNA MARCHA RE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '52225313',
        'LANTERNA MARCHA RE',
        '',
        '',
        '',
        '',
        '',
        'TORO DIESEL',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        193.55,
        'BRL',
        390.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53105718 - ELETROBOMBA PARTIDA A FRIO FIAT RENEGADE FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53105718',
        'ELETROBOMBA PARTIDA A FRIO FIAT RENEGADE FLEX',
        '',
        '',
        '',
        '',
        'A12',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        73.00,
        'BRL',
        315.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53106513 - ALTERNADOR FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53106513',
        'ALTERNADOR FLEX',
        '',
        '',
        '',
        '',
        'H5',
        'COMPASS FLEX',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        550.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53221241 - GRADE INTERNA PARACHOQUE COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53221241',
        'GRADE INTERNA PARACHOQUE COMPASS',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2017 - 2021',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        556.94,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53221407 - SENSOR DE ESTACIONAMENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53221407',
        'SENSOR DE ESTACIONAMENTO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS RENEGADE E TORO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        230.00,
        'BRL',
        399.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53331932 - MANGUEIRA SUPERIOR DO RADIADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53331932',
        'MANGUEIRA SUPERIOR DO RADIADOR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        354.02,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53345186 - SEMI EIXO COMPASS LADO ESQUERDO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53345186',
        'SEMI EIXO COMPASS LADO ESQUERDO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        520.00,
        'BRL',
        2560.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53353162 - MANGUEIRA DE RETORNO AR QUENTE COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53353162',
        'MANGUEIRA DE RETORNO AR QUENTE COMPASS',
        '',
        '',
        '',
        '',
        'D14',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        246.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53353723 - RADIADOR DE AGUA COMPLETO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53353723',
        'RADIADOR DE AGUA COMPLETO',
        '',
        '',
        '',
        '',
        '',
        'FIAT TORO  FLEX COMPASS 2.0 FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        860.70,
        'BRL',
        1790.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53406882 - SEMI EIXO COMPASS LADO DIREITO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53406882',
        'SEMI EIXO COMPASS LADO DIREITO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1280.00,
        'BRL',
        2560.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53416008 - COXIM DO MOTOR COMPASS FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53416008',
        'COXIM DO MOTOR COMPASS FLEX',
        '',
        '',
        '',
        '',
        'C11',
        'COMPASS FLEX',
        'TOTAL TECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        500.33,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53449429 - ELETROVENTILADO 5 HASTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53449429',
        'ELETROVENTILADO 5 HASTE',
        '',
        '',
        '',
        '',
        'PARTE DE CIMA PRATELEIRA',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1800.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53458653 - COXIM BIELA INFERIOR 2.0 FLEX ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53458653',
        'COXIM BIELA INFERIOR 2.0 FLEX ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'COMPAS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        291.83,
        'BRL',
        556.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53474795 - SENSOR DE PRESSAO PNEU TPMS ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53474795',
        'SENSOR DE PRESSAO PNEU TPMS ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B13',
        'TORO, COMPASS E RENAGADE TODOS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        156.29,
        'BRL',
        394.44,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53475747 - SENSOR ABS RODA DIANTEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53475747',
        'SENSOR ABS RODA DIANTEIRA',
        '',
        '',
        '',
        '',
        'A2',
        'TODOS OS VEICULOS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        68.30,
        'BRL',
        210.33,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53479013 - SENSOR ABS RODA TRASEIRA RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53479013',
        'SENSOR ABS RODA TRASEIRA RENEGADE',
        '',
        '',
        '',
        '',
        'A3',
        'RENEGADE 1.8 E DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        89.48,
        'BRL',
        231.80,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53480388/k68253002ae - COXIM DO MOTOR LADO DIREITO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53480388/k68253002ae',
        'COXIM DO MOTOR LADO DIREITO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'D10',
        'COMPASS DIESEL',
        'TOTAL TECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        390.83,
        'BRL',
        1685.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53484013 - RESERVATORIO D AGUA COM TAMPA ORIGINAL MOPAR VEICULOS 1.3 TURBO T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53484013',
        'RESERVATORIO D AGUA COM TAMPA ORIGINAL MOPAR VEICULOS 1.3 TURBO T270',
        '',
        '',
        '',
        '',
        'D11',
        'VEICULOS 1.3 TURBO T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        98.56,
        'BRL',
        280.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53489632 - MANGUEIRA ARLA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53489632',
        'MANGUEIRA ARLA',
        '',
        '',
        '',
        '',
        'PARTE CIMA PRATELEIRA',
        'VEICULOS COM ARLA',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        689.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53489782 - BARRA ESTABILIZADORA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53489782',
        'BARRA ESTABILIZADORA',
        '',
        '',
        '',
        '',
        'PARTE DEBAIXO PRATELEIRA',
        'VEICULO DIESEL 4X4',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        758.33,
        'BRL',
        775.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 53490207 - MANGUEIRA SUPERIOR DO RADIADOR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '53490207',
        'MANGUEIRA SUPERIOR DO RADIADOR DIESEL',
        '',
        '',
        '',
        '',
        'D13',
        'COMPASS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        241.49,
        'BRL',
        544.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5418208968 - MOTORZINHO REGULAGEM FAROL L.E RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5418208968',
        'MOTORZINHO REGULAGEM FAROL L.E RENEGADE',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        99.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55000827AB - BOBINA IGNICAO COMPASS 2.0 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55000827AB',
        'BOBINA IGNICAO COMPASS 2.0 FLEX',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MAGNETI MARELLI',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        216.47,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55196505 - BUJÃO CARTER
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55196505',
        'BUJÃO CARTER',
        '',
        '',
        '',
        '',
        '',
        'COMPASS DIESEL',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        23.96,
        'BRL',
        20.61,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55200755 - VELA AQUECEDORA ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55200755',
        'VELA AQUECEDORA ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B2',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        139.99,
        'BRL',
        394.44,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55202374 - SENSOR DE PRESSAO OLEO DE BAIXA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55202374',
        'SENSOR DE PRESSAO OLEO DE BAIXA',
        '',
        '',
        '',
        '',
        'B8',
        'TODOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        41.92,
        'BRL',
        295.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55206749 - VEDACAO DA VARETA DE OLEO ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55206749',
        'VEDACAO DA VARETA DE OLEO ORIGINAL',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        46.80,
        'BRL',
        179.38,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    12,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55212608 - VEDACAO DO BOCAL DE ENCHIMENTO DE OLEO DO MOTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55212608',
        'VEDACAO DO BOCAL DE ENCHIMENTO DE OLEO DO MOTOR',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        21.18,
        'BRL',
        59.90,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55214216 - PARAFUSO DO CABEÇOTE 2.0 DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55214216',
        'PARAFUSO DO CABEÇOTE 2.0 DIESEL',
        '',
        '',
        '',
        '',
        'E13',
        'TORO E COMPASS DIESEL 2.0',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        41.49,
        'BRL',
        20.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    19,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55214638 - ELETRO VALVULA CANISTER
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55214638',
        'ELETRO VALVULA CANISTER',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        148.97,
        'BRL',
        467.67,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55219298 - SENSOR DE MAP MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55219298',
        'SENSOR DE MAP MOPAR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        160.92,
        'BRL',
        139.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55222403 - JUNTA COLETOR ESCAPE DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55222403',
        'JUNTA COLETOR ESCAPE DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TODOS MOTORES 2.0 DIESEL',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        100.00,
        'BRL',
        225.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55224457 - JUNTA DO COLETOR ESCAPE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55224457',
        'JUNTA DO COLETOR ESCAPE',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8 E-TORQ',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        50.33,
        'BRL',
        225.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55226613 - TENSOR CORRENTE DE COMANDO ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55226613',
        'TENSOR CORRENTE DE COMANDO ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE TORO 1.8 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        123.31,
        'BRL',
        189.06,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55241404 - VALVULA TERMOSTATICA ORIGINAL MOPAR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55241404',
        'VALVULA TERMOSTATICA ORIGINAL MOPAR DIESEL',
        '',
        '',
        '',
        '',
        'A3',
        '2.0 DIESEL, TORO COMPASS E RENEGADE',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        480.86,
        'BRL',
        943.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55243599 - TAMPAO DE ALUMINIO DO BLOCO DO MOTOR ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55243599',
        'TAMPAO DE ALUMINIO DO BLOCO DO MOTOR ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B16',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'FIAT',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.26,
        'BRL',
        67.34,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55247720 - TAMPA DE VALVULAS ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55247720',
        'TAMPA DE VALVULAS ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'ETORQ 1.8',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        249.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55247723 - PARAFUSO DA POLIA VARIADORA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55247723',
        'PARAFUSO DA POLIA VARIADORA',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        286.25,
        'BRL',
        519.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55247740 - SENSOR FASE E-TORQ 1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55247740',
        'SENSOR FASE E-TORQ 1.8',
        '',
        '',
        '',
        '',
        'C6',
        'RENEGADE 2015 a 2021  FIAT TORO 2016 A 2021',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        53.00,
        'BRL',
        53.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55247743 - VALVULA TERMOSTATICA ORIGINAL MOPAR RENEGADE / TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55247743',
        'VALVULA TERMOSTATICA ORIGINAL MOPAR RENEGADE / TORO',
        '',
        '',
        '',
        '',
        'A2',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        102.80,
        'BRL',
        456.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55247746 - BOMBA OLEO MOTOR  1.8 E-TORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55247746',
        'BOMBA OLEO MOTOR  1.8 E-TORQ',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        899.99,
        'BRL',
        1799.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55248941 - JUNTA DA GAIOLA DOS COMANDOS DE VÁLVULAS DIESL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55248941',
        'JUNTA DA GAIOLA DOS COMANDOS DE VÁLVULAS DIESL',
        '',
        '',
        '',
        '',
        'I6',
        'VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        97.93,
        'BRL',
        257.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55255434 - SUPORTE DO FILTRO DE OLEO DO MOTOR 1.8 E-TORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55255434',
        'SUPORTE DO FILTRO DE OLEO DO MOTOR 1.8 E-TORQ',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        340.00,
        'BRL',
        750.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55257414 - BICO INJETOR FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55257414',
        'BICO INJETOR FLEX',
        '',
        '',
        '',
        '',
        'B13',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        197.12,
        'BRL',
        597.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55259712 - CARCAÇA REFRIADOR EGR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55259712',
        'CARCAÇA REFRIADOR EGR',
        '',
        '',
        '',
        '',
        'I2',
        'TODOS DIESEL',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        189.00,
        'BRL',
        727.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55259913 - SENSOR TEMPERATURA GASES DE ESCAPA MENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55259913',
        'SENSOR TEMPERATURA GASES DE ESCAPA MENTO',
        '',
        '',
        '',
        '',
        'B16',
        'VEICULOS DIESEL',
        'IGUAÇU',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        216.83,
        'BRL',
        450.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55261865 - SENSOR DE ROTAÇÃO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55261865',
        'SENSOR DE ROTAÇÃO',
        '',
        '',
        '',
        '',
        'B8',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        168.00,
        'BRL',
        588.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55262116 - MANGUEIRA TROCADOR CALOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55262116',
        'MANGUEIRA TROCADOR CALOR',
        '',
        '',
        '',
        '',
        'D13',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        253.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55262874 - JUNTA DO CABEÇOTE 1.8 E-TORQ MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55262874',
        'JUNTA DO CABEÇOTE 1.8 E-TORQ MOPAR',
        '',
        '',
        '',
        '',
        'E14',
        'RENEGADE E TORO 1.8 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        147.16,
        'BRL',
        200.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55263233 - BICO INJETOR DE ALTA PRESSAO DIESEL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55263233',
        'BICO INJETOR DE ALTA PRESSAO DIESEL MOPAR',
        '',
        '',
        '',
        '',
        'C8',
        'COMPASS 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1065.53,
        'BRL',
        1799.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 552660610 - MODULO AQUECIMENTO COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '552660610',
        'MODULO AQUECIMENTO COMPASS',
        '',
        '',
        '',
        '',
        '',
        'COMPASS - FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        199.50,
        'BRL',
        920.56,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55269957 - MANGUEIRA TROCADOR CALOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55269957',
        'MANGUEIRA TROCADOR CALOR',
        '',
        '',
        '',
        '',
        'D13',
        'VEICULOS 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        313.26,
        'BRL',
        1330.42,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55269958 - MANGUEIRA DE TROCADOR DE CALOR DO MOTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55269958',
        'MANGUEIRA DE TROCADOR DE CALOR DO MOTOR',
        '',
        '',
        '',
        '',
        'D16',
        'DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        486.43,
        'BRL',
        1330.42,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55270293 - RESPIRO MOTOR ANTICHAMAS DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55270293',
        'RESPIRO MOTOR ANTICHAMAS DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TODOS VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1899.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55271703 - SENSOR TEMPERATURA GASES DE ESCAPA MENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55271703',
        'SENSOR TEMPERATURA GASES DE ESCAPA MENTO',
        '',
        '',
        '',
        '',
        'C8',
        'VEICULOS DIESEL',
        'IGUAÇU',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        210.97,
        'BRL',
        450.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55271704 - SENSOR TEMPERATURA GASES DE ESCAPA MENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55271704',
        'SENSOR TEMPERATURA GASES DE ESCAPA MENTO',
        '',
        '',
        '',
        '',
        'A14',
        'VEICULOS DIESEL',
        'IGUAÇU',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        210.97,
        'BRL',
        450.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55271716 - SENSOR TEMPERATURA GASES DE ESCAPA MENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55271716',
        'SENSOR TEMPERATURA GASES DE ESCAPA MENTO',
        '',
        '',
        '',
        '',
        'B5',
        'VEICULOS DIESEL',
        'IGUAÇU',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        210.97,
        'BRL',
        450.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55273036 - SUPORTE DO FILTRO DE OLEO DO MOTOR COMPLETO LONGO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55273036',
        'SUPORTE DO FILTRO DE OLEO DO MOTOR COMPLETO LONGO',
        '',
        '',
        '',
        '',
        'F5',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL (CHECAR MODELO EXISTE LONGO E CURTO)',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1199.00,
        'BRL',
        2038.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55273759 - SUPORTE DO FILTRO DE OLEO DO MOTOR COMPLETO CURTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55273759',
        'SUPORTE DO FILTRO DE OLEO DO MOTOR COMPLETO CURTO',
        '',
        '',
        '',
        '',
        'F5',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL (CHECAR MODELO EXISTE LONGO E CURTO)',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        750.50,
        'BRL',
        750.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55277926 - POLIA VIRABREQUIM E-TORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55277926',
        'POLIA VIRABREQUIM E-TORQ',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        260.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55278308 - PARAFUSO DO CABEÇOTE  1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55278308',
        'PARAFUSO DO CABEÇOTE  1.8',
        '',
        '',
        '',
        '',
        'E16',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        7.99,
        'BRL',
        680.96,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    30,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55282087 - BOBINA IGNIÇÃO T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55282087',
        'BOBINA IGNIÇÃO T270',
        '',
        '',
        '',
        '',
        'A6',
        'COMPASS E RENEGADE T270',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        199.99,
        'BRL',
        459.43,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55282225 - TENSOR CORRENTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55282225',
        'TENSOR CORRENTE',
        '',
        '',
        '',
        '',
        '',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        250.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 552822583 - FILTRO OLEO MULTIAIR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '552822583',
        'FILTRO OLEO MULTIAIR',
        '',
        '',
        '',
        '',
        '',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        389.99,
        'BRL',
        750.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55282321 - TENSOR DA CORREIA DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55282321',
        'TENSOR DA CORREIA DIESEL',
        '',
        '',
        '',
        '',
        'A10',
        'DIESEL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        318.62,
        'BRL',
        465.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55282719 - BUJAO INTERRUPTOR PRESSAO OLEO E-TORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55282719',
        'BUJAO INTERRUPTOR PRESSAO OLEO E-TORQ',
        '',
        '',
        '',
        '',
        'C5',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        70.00,
        'BRL',
        20.61,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55283717 - JUNTA DO CABEÇOTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55283717',
        'JUNTA DO CABEÇOTE',
        '',
        '',
        '',
        '',
        'E15',
        'RENEGADE DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        194.79,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55283962 - SONDA LAMBDA POS CATALIZADORA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55283962',
        'SONDA LAMBDA POS CATALIZADORA',
        '',
        '',
        '',
        '',
        'B8',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL ORIGINAL APÓS CATALIZADOR',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        530.95,
        'BRL',
        1074.58,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55284050 - SONDA LAMBDA POS CATALIZADORA ETORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55284050',
        'SONDA LAMBDA POS CATALIZADORA ETORQ',
        '',
        '',
        '',
        '',
        'B6',
        'TORO E RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        275.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55284366 - POLIA VARIADORA FASE RENEGADE TORO 1.8
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55284366',
        'POLIA VARIADORA FASE RENEGADE TORO 1.8',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE TORO 1.8 16V',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        534.15,
        'BRL',
        1574.46,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55284989 - RETENTOR VOLANTE T270 1.3
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55284989',
        'RETENTOR VOLANTE T270 1.3',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'VEICULOS 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        74.74,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 55571993 - COLETOR ADMISSAO COMPLETO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '55571993',
        'COLETOR ADMISSAO COMPLETO',
        '',
        '',
        '',
        '',
        'PRATELEIRA PARTE DE CIMA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'TOTAL TECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        602.39,
        'BRL',
        2411.78,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    6,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5707 - POLIA CATRACA DO ALTERNADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5707',
        'POLIA CATRACA DO ALTERNADOR',
        '',
        '',
        '',
        '',
        'B6',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'ZEN',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        170.25,
        'BRL',
        413.24,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5708 - POLIA CATRACA DO ALTERNADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5708',
        'POLIA CATRACA DO ALTERNADOR',
        '',
        '',
        '',
        '',
        'B5',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'ZEN',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        173.09,
        'BRL',
        415.90,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5795481580 - MANGUEIRA FLUXO AR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5795481580',
        'MANGUEIRA FLUXO AR',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        180.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5838 - ANEL DE VEDACAO DO RESPIRO 1 DA BOMBA DVACUO 14X2
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5838',
        'ANEL DE VEDACAO DO RESPIRO 1 DA BOMBA DVACUO 14X2',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'SUL VEDACOES',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        15.64,
        'BRL',
        23.43,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5PK1130 - CORREIA AUXILIAR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5PK1130',
        'CORREIA AUXILIAR T270',
        '',
        '',
        '',
        '',
        'B3',
        'COMPASS, TORO E RENEGADE',
        'DAYCO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        52.51,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 5w30 - OLEO DO MOTOR 5W30
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '5w30',
        'OLEO DO MOTOR 5W30',
        '',
        '',
        '',
        '',
        'TAMBOR OFICINA',
        'TODOS RENEGADE, TORO E COMPASS EXCETO MOTORES 1.3 TURBO',
        'VALVOLINE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        34.61,
        'BRL',
        85.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    254,
    15,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6000628644 - JUNTA DOS FUROS DA TAMPA VALVULA T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6000628644',
        'JUNTA DOS FUROS DA TAMPA VALVULA T270',
        '',
        '',
        '',
        '',
        '',
        'TORO COMPASS RENEGADE T270 1.3',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        149.99,
        'BRL',
        149.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6000628650 - JUNTA TUBO RIGIDO TROCADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6000628650',
        'JUNTA TUBO RIGIDO TROCADOR',
        '',
        '',
        '',
        '',
        'B13',
        'VEICULOS 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        70.00,
        'BRL',
        240.10,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 600628690 - JUNTA DA TAMPA VALVULA T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '600628690',
        'JUNTA DA TAMPA VALVULA T270',
        '',
        '',
        '',
        '',
        'E16',
        'TORO COMPASS RENEGADE T270 1.3',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        133.99,
        'BRL',
        239.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 600634166 - BOMBA DAGUA MOTOR DIESEL ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '600634166',
        'BOMBA DAGUA MOTOR DIESEL ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B5',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        381.30,
        'BRL',
        1227.90,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 60949365 - SENSOR DE ESTACIONAMENTO DIANTEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '60949365',
        'SENSOR DE ESTACIONAMENTO DIANTEIRO',
        '',
        '',
        '',
        '',
        'B7',
        'COMPASS, RENEGADE 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        410.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6295 - KIT RADIADOR PARA TRASMISSÃO AUTOMATICA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6295',
        'KIT RADIADOR PARA TRASMISSÃO AUTOMATICA',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1925.94,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 63832 - BATENTE REGULAGEM CAPO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '63832',
        'BATENTE REGULAGEM CAPO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        67.90,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6653 - KIT DE EMBREAGEM DO COMPRESSOR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6653',
        'KIT DE EMBREAGEM DO COMPRESSOR DIESEL',
        '',
        '',
        '',
        '',
        'I1',
        'TORO, COMPASS E RENAGADE TODOS',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        387.69,
        'BRL',
        685.15,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6795 - MOTOR ELETRICO DIFERENCIAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6795',
        'MOTOR ELETRICO DIFERENCIAL',
        '',
        '',
        '',
        '',
        'I1',
        'CAIXA DE TRANSFERENCIA E DIFERENCIAL    TODOS VEICULOS 4X4',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        950.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 68292767AF - CAIXA DE TRANFERENCIA REMANUFATURADO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '68292767AF',
        'CAIXA DE TRANFERENCIA REMANUFATURADO',
        '',
        '',
        '',
        '',
        '',
        'TODOS 4X4',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1011.75,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6940AG - COIFA LADO ESQUERDO LADO CAMBIO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6940AG',
        'COIFA LADO ESQUERDO LADO CAMBIO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        80.00,
        'BRL',
        46.15,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6HP19 - BUCHA DA BOMBA DE OLEO DO CAMBIO 9HP48 DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6HP19',
        'BUCHA DA BOMBA DE OLEO DO CAMBIO 9HP48 DIESEL',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS DIESEL',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        550.00,
        'BRL',
        1074.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6PK1345 - CORREIA AUXLIAR JEEP DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6PK1345',
        'CORREIA AUXLIAR JEEP DIESEL',
        '',
        '',
        '',
        '',
        'D4',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'DAYCO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        42.87,
        'BRL',
        150.35,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6PK1450 - CORREIA AUXILIAR JEEP FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6PK1450',
        'CORREIA AUXILIAR JEEP FLEX',
        '',
        '',
        '',
        '',
        'C3',
        'TORO E RENEGADE 1.8 FLEX, NÃO APLICA NO DIESEL NEM COMPASS 2.0 FLEX',
        'DAYCO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        55.52,
        'BRL',
        113.57,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 6PK2005 - CORREIA AUXILIAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '6PK2005',
        'CORREIA AUXILIAR',
        '',
        '',
        '',
        '',
        'B4',
        'COMPASS FLEX 2.0',
        'DAYCO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        77.61,
        'BRL',
        155.33,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7089720 - TROCADOR DE CALOR TRANSMISSAO AUTOMATICA MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7089720',
        'TROCADOR DE CALOR TRANSMISSAO AUTOMATICA MOPAR',
        '',
        '',
        '',
        '',
        'A4',
        'TORO, COMPASS E RENAGADE TODOS (NÃO USA EM VEÍCULOS DIESEL)',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        627.07,
        'BRL',
        1390.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7090012 - JG JUNTA  COLETOR DE ADMISSÃO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7090012',
        'JG JUNTA  COLETOR DE ADMISSÃO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        62.12,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7090700 - SENSOR DE NIVEL DE COMBUSTIVEL ORIGINAL MOPAR / BOIA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7090700',
        'SENSOR DE NIVEL DE COMBUSTIVEL ORIGINAL MOPAR / BOIA',
        '',
        '',
        '',
        '',
        '',
        'TORO RENEGADE 1.8 COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        361.41,
        'BRL',
        759.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7091886 - FILTRO DE OLEO DO MOTOR 1.8 ETORQ ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7091886',
        'FILTRO DE OLEO DO MOTOR 1.8 ETORQ ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'C2',
        'TORO REBEGADE FLEX 1.8',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        27.76,
        'BRL',
        73.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7092455 - COLUNA DE DIREÇÃO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7092455',
        'COLUNA DE DIREÇÃO',
        '',
        '',
        '',
        '',
        'G5',
        'TORO, COMPASS, RENEGADE TODOS',
        'MOPAR',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        1699.99,
        'BRL',
        4270.32,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7092809 - BLOCO MOTOR T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7092809',
        'BLOCO MOTOR T270',
        '',
        '',
        '',
        '',
        '',
        '',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        4600.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7092921 - COLETOR ADMISSÃO 1.3 TURBO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7092921',
        'COLETOR ADMISSÃO 1.3 TURBO',
        '',
        '',
        '',
        '',
        '',
        'TODOS 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        300.00,
        'BRL',
        900.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094135 - ALTERNADOR REMA 1.8 ETORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094135',
        'ALTERNADOR REMA 1.8 ETORQ',
        '',
        '',
        '',
        '',
        'G7',
        'FIAT TORO 1.8',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        630.48,
        'BRL',
        1421.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094181 - TURBINA COMPLETA REMANUFATURADA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094181',
        'TURBINA COMPLETA REMANUFATURADA',
        '',
        '',
        '',
        '',
        'G6',
        'COMPASS, TORO E RENEGADE 2.0',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2170.00,
        'BRL',
        1650.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094208 - REPADOR PINÇA FREIO DIANTEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094208',
        'REPADOR PINÇA FREIO DIANTEIRO',
        '',
        '',
        '',
        '',
        'B13',
        '',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        198.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094530 - PASTILHA DE FREIO DIANTEIRA MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094530',
        'PASTILHA DE FREIO DIANTEIRA MOPAR',
        '',
        '',
        '',
        '',
        'A13',
        'TORO, COMPASS E RENAGADE TODOS EXCETO VEÍCULOS 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        409.99,
        'BRL',
        799.96,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094701 - BOMBA DE ALTA PRESSÃO T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094701',
        'BOMBA DE ALTA PRESSÃO T270',
        '',
        '',
        '',
        '',
        'A11',
        'COMPASS T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1366.49,
        'BRL',
        1999.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094706 - KIT DE FLAUTA COM BICOS INJETORES
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094706',
        'KIT DE FLAUTA COM BICOS INJETORES',
        '',
        '',
        '',
        '',
        'A6',
        'T270',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2239.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7094916 - KIT DE DISCO E PASTILHA ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7094916',
        'KIT DE DISCO E PASTILHA ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1459.12,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7095718 - SENSOR INTELIGENTE BATERIA IBS ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7095718',
        'SENSOR INTELIGENTE BATERIA IBS ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'B13',
        'TORO, COMPASS E RENAGADE TODOS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        451.63,
        'BRL',
        412.22,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7095723 - SONDA LAMBDA PRE CATALISADOR  (SENSOR DE OXIGENIO)
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7095723',
        'SONDA LAMBDA PRE CATALISADOR  (SENSOR DE OXIGENIO)',
        '',
        '',
        '',
        '',
        'B8',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        650.97,
        'BRL',
        1480.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7095725 - MANGUEIRA SUPERIOR DO RADIADOR RENEGADE DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7095725',
        'MANGUEIRA SUPERIOR DO RADIADOR RENEGADE DIESEL',
        '',
        '',
        '',
        '',
        'D13',
        'RENEGADE DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        427.49,
        'BRL',
        850.71,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7095727 - VEDAÇÃO DO DPF
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7095727',
        'VEDAÇÃO DO DPF',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'VEICULOS 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.22,
        'BRL',
        75.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7095730 - COPO DO FILTRO DE COMBUSTIVEL DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7095730',
        'COPO DO FILTRO DE COMBUSTIVEL DIESEL',
        '',
        '',
        '',
        '',
        'H7',
        'TODOS OS VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        540.00,
        'BRL',
        1050.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7095920 - MOTOR COMPLETO T270 MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7095920',
        'MOTOR COMPLETO T270 MOPAR',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS 1.3 TURBO',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        16199.99,
        'BRL',
        39449.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7096402 - TURBO COMPRESSOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7096402',
        'TURBO COMPRESSOR',
        '',
        '',
        '',
        '',
        '',
        'COMPAS, RENEGADE E TORO 2.0 MODELO C/ARLA',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        3399.99,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7098068 - FILTRO DE COMBUSTIVEL DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7098068',
        'FILTRO DE COMBUSTIVEL DIESEL',
        '',
        '',
        '',
        '',
        'D4',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'EUROREPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        82.52,
        'BRL',
        270.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7120 - ANEL DE VEDACAO DO RESPIRO 2 DA BOMBA DVACUO 5X1,20
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7120',
        'ANEL DE VEDACAO DO RESPIRO 2 DA BOMBA DVACUO 5X1,20',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'SUL VEDACOES',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.31,
        'BRL',
        27.12,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7157121 - LAMPADA FAROL 12V 55W H7 HELLA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7157121',
        'LAMPADA FAROL 12V 55W H7 HELLA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.52,
        'BRL',
        45.21,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 71754237 - FILTRO DE OLEO DO MOTOR ORIGINAL MOPAR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '71754237',
        'FILTRO DE OLEO DO MOTOR ORIGINAL MOPAR',
        '',
        '',
        '',
        '',
        'C2',
        'RENEGADE, TORO E COMPASS 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        53.37,
        'BRL',
        143.76,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 71779194 - JUNTA DA BOMBA DE VACUO ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '71779194',
        'JUNTA DA BOMBA DE VACUO ORIGINAL',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        92.27,
        'BRL',
        240.10,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 72721 - BOMBA OLEO MOTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '72721',
        'BOMBA OLEO MOTOR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        890.00,
        'BRL',
        890.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 735636560 - COMANDO DE FREIO DE MÃO ELETRICO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '735636560',
        'COMANDO DE FREIO DE MÃO ELETRICO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        200.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7416L6 - SUPORTE   AUTOMOTIVO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7416L6',
        'SUPORTE   AUTOMOTIVO',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        300.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7506 - LAMPADA 12V 1 POLO FREIO E RÉ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7506',
        'LAMPADA 12V 1 POLO FREIO E RÉ',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        16.76,
        'BRL',
        14.27,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    11,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7507 - LAMPADA DE SETA LARANJA HELLA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7507',
        'LAMPADA DE SETA LARANJA HELLA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.00,
        'BRL',
        51.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7528 - LAMPADA 12V 2 POLOS FREIO E RÉ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7528',
        'LAMPADA 12V 2 POLOS FREIO E RÉ',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.25,
        'BRL',
        14.27,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    13,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 75w90 - OLEO DE DIFERENCIAL 75W90 GL5 LS JEEP
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '75w90',
        'OLEO DE DIFERENCIAL 75W90 GL5 LS JEEP',
        '',
        '',
        '',
        '',
        'E8',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'VALVOLINE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        119.39,
        'BRL',
        242.60,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    6,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 7689903 - VEDAÇÃO PARA TAMPA DO BOCAL DE ENCHIMENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '7689903',
        'VEDAÇÃO PARA TAMPA DO BOCAL DE ENCHIMENTO',
        '',
        '',
        '',
        '',
        '',
        'TORO E RENEGADE 1.8',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        100.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 78 - ADTIVO PARA LIMPEZA DO FILTRO DPF MOTORES DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '78',
        'ADTIVO PARA LIMPEZA DO FILTRO DPF MOTORES DIESEL',
        '',
        '',
        '',
        '',
        'D8',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'EXCEL AUTOMOTIVE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        96.26,
        'BRL',
        249.97,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    15,
    6,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 8099 - SILICONE DE ALTA TEMPERATURA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '8099',
        'SILICONE DE ALTA TEMPERATURA',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'CAR 80',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        20.51,
        'BRL',
        59.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    31,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 816 - KIT DE EMBREAGEM DO COMPRESSOR FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '816',
        'KIT DE EMBREAGEM DO COMPRESSOR FLEX',
        '',
        '',
        '',
        '',
        'I2',
        'TORO, COMPASS E RENAGADE TODOS',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        383.33,
        'BRL',
        685.15,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 87.70 87 - ABRAÇADEIRA RETORNO BICO 7MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '87.70 87',
        'ABRAÇADEIRA RETORNO BICO 7MM',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.90,
        'BRL',
        2.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    50,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 8958 - ANEL DE VEDACAO DA TRASEIRA DA BOMBA DE VACUO 88X3
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '8958',
        'ANEL DE VEDACAO DA TRASEIRA DA BOMBA DE VACUO 88X3',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'SUL VEDACOES',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        34.64,
        'BRL',
        83.30,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 917 - ANEL DE VEDACAO DA BOMBA DE VACUO 40X1,50
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '917',
        'ANEL DE VEDACAO DA BOMBA DE VACUO 40X1,50',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'SUL VEDACOES',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        9.75,
        'BRL',
        79.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 921NA - LAMPADA DE SETA 12V LARANJA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '921NA',
        'LAMPADA DE SETA 12V LARANJA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TORO, COMPASS E RENAGADE TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        51.97,
        'BRL',
        112.12,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 93474202 - MODULO SENSOR TEMPERATURA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '93474202',
        'MODULO SENSOR TEMPERATURA',
        '',
        '',
        '',
        '',
        '',
        'COMPASS',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        239.90,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 99.38 51 - ABRAÇADEIRA 38 X 51
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '99.38 51',
        'ABRAÇADEIRA 38 X 51',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS OS VEICULOS',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        4.41,
        'BRL',
        2.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    10,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 99.44 57 - ABRAÇADEIRA 44 X 57
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '99.44 57',
        'ABRAÇADEIRA 44 X 57',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS OS VEICULOS',
        'IMPORTADO',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        4.60,
        'BRL',
        2.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    20,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: 9X13MM - ABRAÇADEIRA 9X13MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        '9X13MM',
        'ABRAÇADEIRA 9X13MM',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS OS VEICULOS',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.51,
        'BRL',
        12.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    20,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ABRAÇADEIRA 11.3 - ABRAÇADEIRA 11.3
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ABRAÇADEIRA 11.3',
        'ABRAÇADEIRA 11.3',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS VEICULOS',
        'IMPORTADO',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        25.00,
        'BRL',
        2.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ABRAÇADEIRA 12 X 44 - ABRAÇADEIRA 12 X 44
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ABRAÇADEIRA 12 X 44',
        'ABRAÇADEIRA 12 X 44',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS VEICULOS',
        'IMPORTADO',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.40,
        'BRL',
        2.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ABRAÇADEIRA DE HOMOCINETICA ABC60 - ABRAÇADEIRA DE HOMOCINETICA EIXO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ABRAÇADEIRA DE HOMOCINETICA ABC60',
        'ABRAÇADEIRA DE HOMOCINETICA EIXO',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS OS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        6.48,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ABRAÇADEIRA DE HOMOCINETICA AC70 - ABRAÇADEIRA DE HOMOCINETICA COIFA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ABRAÇADEIRA DE HOMOCINETICA AC70',
        'ABRAÇADEIRA DE HOMOCINETICA COIFA',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS OS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        13.75,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ACT0001 - ATUADOR FIAT
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ACT0001',
        'ATUADOR FIAT',
        '',
        '',
        '',
        '',
        '',
        'TORO 2.0, JEEP COMPASS 2.0, RENEGADE 2.0',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        570.84,
        'BRL',
        570.84,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ADPT M9/16 - ADAPTADOR MACHO 9/16
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ADPT M9/16',
        'ADAPTADOR MACHO 9/16',
        '',
        '',
        '',
        '',
        '',
        'KIT RADIADOR',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        11.20,
        'BRL',
        22.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: AKX2108 - FILTRO DE CABINE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'AKX2108',
        'FILTRO DE CABINE',
        '',
        '',
        '',
        '',
        'D2',
        'TORO, COMPASS E RENEGADE TODOS',
        'WEGA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.15,
        'BRL',
        70.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: AL57IMA - TRIZETA 23 DENTE POR 40MM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'AL57IMA',
        'TRIZETA 23 DENTE POR 40MM',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE     23 DENTES POR 40MM',
        'IMA',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        123.00,
        'BRL',
        530.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ATD03037 / ATD03038 - TERMINAL DE DIRECAO JEEP
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ATD03037 / ATD03038',
        'TERMINAL DE DIRECAO JEEP',
        '',
        '',
        '',
        '',
        'C6',
        'RENEGADE TORO COMPASS TODOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        60.27,
        'BRL',
        82.88,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BA0216203040RC - PORTA ESCOVA ALTERNADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BA0216203040RC',
        'PORTA ESCOVA ALTERNADOR',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        35.00,
        'BRL',
        35.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BAU 10.0332 - ELETROVENTILADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BAU 10.0332',
        'ELETROVENTILADOR',
        '',
        '',
        '',
        '',
        'PARTE CIMA PRATELEIRA',
        'RENEGADE DIESEL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        923.08,
        'BRL',
        907.07,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BC63724 - COIFA UNIVERSAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BC63724',
        'COIFA UNIVERSAL',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        61.07,
        'BRL',
        46.15,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BD3608 - DISCO DE FREIO DIANTEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BD3608',
        'DISCO DE FREIO DIANTEIRO',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENAGADE TODOS',
        'FREMAXX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        189.27,
        'BRL',
        50.91,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BDJ 1733R - BANDEJA DA SUSPENSAO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BDJ 1733R',
        'BANDEJA DA SUSPENSAO',
        '',
        '',
        '',
        '',
        'PARTE BAIXO PRATELEIRA',
        'RENEGADE',
        'GENUINE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        338.88,
        'BRL',
        755.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    10,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BOMBA TRANSFERENCIA BRINDE - BOMBA TRANSFERENCIA BRINDE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BOMBA TRANSFERENCIA BRINDE',
        'BOMBA TRANSFERENCIA BRINDE',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        150.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: BTCR032 - BATERIA DA CHAVE CR2032
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'BTCR032',
        'BATERIA DA CHAVE CR2032',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        14.00,
        'BRL',
        32.87,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: C89860-200 - MOTOR ELETRICO DO VIDRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'C89860-200',
        'MOTOR ELETRICO DO VIDRO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 2023',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        200.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CAR 8040 - TRAVA ROSCA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CAR 8040',
        'TRAVA ROSCA',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        9.39,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CAR CARRO NOVO - LIMPA AR CONDICIONADO HIGIENIZADOR GRANADA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CAR CARRO NOVO',
        'LIMPA AR CONDICIONADO HIGIENIZADOR GRANADA',
        '',
        '',
        '',
        '',
        'D5',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.08,
        'BRL',
        37.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CARFLUSH - CARFLUSH LIMPA CARTER
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CARFLUSH',
        'CARFLUSH LIMPA CARTER',
        '',
        '',
        '',
        '',
        '',
        'TODOS CARROS',
        'CAR80',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        24.25,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CBT-3300A - ABRASIVO VEGETAL HRAD (CASCA NOZ)
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CBT-3300A',
        'ABRASIVO VEGETAL HRAD (CASCA NOZ)',
        '',
        '',
        '',
        '',
        '',
        'CASCA DE NOZ PARA MAQUINA DESCARBNIZAÇÃO',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        192.06,
        'BRL',
        56.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CFOP5102 - CORPO DE VÁLVULA DO RENEGADE/ COMPASS DO CÂMBIO AUTOMÁTICO TF72
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CFOP5102',
        'CORPO DE VÁLVULA DO RENEGADE/ COMPASS DO CÂMBIO AUTOMÁTICO TF72',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE/COMPASS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        3650.00,
        'BRL',
        4297.67,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CI11412 - COXIM SUPERIOR DO CAMBIO LD ESQUERDO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CI11412',
        'COXIM SUPERIOR DO CAMBIO LD ESQUERDO',
        '',
        '',
        '',
        '',
        'C12',
        'COMPASS 2.0 FLEX',
        'TOTAL TECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        570.82,
        'BRL',
        1978.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CI11595 - COXIM SUPERIOR MOTOR COMPASS 2.0 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CI11595',
        'COXIM SUPERIOR MOTOR COMPASS 2.0 FLEX',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'TOTALTECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        467.64,
        'BRL',
        1480.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CI11927 - KIT DE JUNTAS TROCADOR DE CALOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CI11927',
        'KIT DE JUNTAS TROCADOR DE CALOR',
        '',
        '',
        '',
        '',
        '',
        'COMPASS TORO E RENEGADE 2.0',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        61.00,
        'BRL',
        61.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CL112098KIT - KIT RADIADOR PADRAO ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CL112098KIT',
        'KIT RADIADOR PADRAO ORIGINAL',
        '',
        '',
        '',
        '',
        '',
        'TODOS VEICULOS FLEX',
        'TOTALTECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        742.64,
        'BRL',
        1522.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CL11402 - COXIM BIELA INFERIOR COMPASS 2.0 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CL11402',
        'COXIM BIELA INFERIOR COMPASS 2.0 FLEX',
        '',
        '',
        '',
        '',
        'C13',
        'COMPASS FLEX',
        'TOTAL TECH',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        267.47,
        'BRL',
        760.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CL11554 - KIT ANEIS VEDAÇÃO BOMBA VACUO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CL11554',
        'KIT ANEIS VEDAÇÃO BOMBA VACUO',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'CAPRICHO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        59.00,
        'BRL',
        428.78,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    5,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CMB0001 - CAMBIO AUTOMATICO TF72
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CMB0001',
        'CAMBIO AUTOMATICO TF72',
        '',
        '',
        '',
        '',
        '',
        '| RENEGADE TORO COMPASS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        8750.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: CR-9022F - CONJUNTO ROTATIVO TURBINA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'CR-9022F',
        'CONJUNTO ROTATIVO TURBINA',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        717.64,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: DNI 0105 - RELE AUXILIAR 20A
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'DNI 0105',
        'RELE AUXILIAR 20A',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        155.68,
        'BRL',
        65.77,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: DNI 5064 - ABRAÇADEIRA NYLON
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'DNI 5064',
        'ABRAÇADEIRA NYLON',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        'NY',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.22,
        'BRL',
        2.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    100,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: DP180099 - BOMBA D AGUA COMPASS TORO RENEGADE DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'DP180099',
        'BOMBA D AGUA COMPASS TORO RENEGADE DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'DAYCO',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        315.00,
        'BRL',
        970.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: DSC 20230 - MANGUEIRA P/BOMBA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'DSC 20230',
        'MANGUEIRA P/BOMBA',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        8.89,
        'BRL',
        22.57,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: DSC 5606 - CONECTOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'DSC 5606',
        'CONECTOR',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        20.97,
        'BRL',
        18.75,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    12,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: EAATA010-BR - EAATA 90
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'EAATA010-BR',
        'EAATA 90',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        2500.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FITA ISO 5M - FITA ISOLANTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FITA ISO 5M',
        'FITA ISOLANTE',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        4.46,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FLU/DS/357SO1 - ADTIVO DE LIMPEZA DE RADIADOR TIRRENO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FLU/DS/357SO1',
        'ADTIVO DE LIMPEZA DE RADIADOR TIRRENO',
        '',
        '',
        '',
        '',
        'E9',
        'TORO, COMPASS E RENAGADE TODOS',
        'TIRRENO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.18,
        'BRL',
        42.55,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    33,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FUCHS ATF 6009 - FLUIDO DE TRANSMISSÃO AUTOMATICA 9HP VERDE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FUCHS ATF 6009',
        'FLUIDO DE TRANSMISSÃO AUTOMATICA 9HP VERDE',
        '',
        '',
        '',
        '',
        '',
        'CARROS DIESEL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        88.14,
        'BRL',
        195.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FUZ H 3040 - FUZIVEL DE LAMINA 40A
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FUZ H 3040',
        'FUZIVEL DE LAMINA 40A',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        'FUZ',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        4.39,
        'BRL',
        26.89,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FUZ H 7040 - FUZIVEL MIDI 40A
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FUZ H 7040',
        'FUZIVEL MIDI 40A',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        'FUZ',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        9.71,
        'BRL',
        19.61,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FUZ H 7050 - FUZIVEL DE LAMINA 15A
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FUZ H 7050',
        'FUZIVEL DE LAMINA 15A',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        15.81,
        'BRL',
        26.89,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    37,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: FUZ H 7080 - FUZIVEL MIDI 80A
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'FUZ H 7080',
        'FUZIVEL MIDI 80A',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        'FUZ',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        10.39,
        'BRL',
        20.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GF 363 - FITA TEXTIL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GF 363',
        'FITA TEXTIL',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        17.52,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GI001 - AGUA DESMINERALIZADA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GI001',
        'AGUA DESMINERALIZADA',
        '',
        '',
        '',
        '',
        'E7',
        'TORO, COMPASS E RENAGADE TODOS',
        'GITANES',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        7.25,
        'BRL',
        11.45,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    66,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GL5 75W80 ULTRA - FLUIDO DE TRANSMISSAO AUTOMATICA 75W80
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GL5 75W80 ULTRA',
        'FLUIDO DE TRANSMISSAO AUTOMATICA 75W80',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        25.08,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GP0447 - BUCHA DA BARRA ESTABILIZADORA DIANTEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GP0447',
        'BUCHA DA BARRA ESTABILIZADORA DIANTEIRA',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'RENEGADE 2.0 DIESEL TAMANHO 23MM  COMPASS FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        50.49,
        'BRL',
        212.94,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GP0448 - BUCHA DA BARRA ESTABILIZADORA DIANTEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GP0448',
        'BUCHA DA BARRA ESTABILIZADORA DIANTEIRA',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TAMANHO 21MM',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        47.00,
        'BRL',
        212.94,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GRUD 824 - ESPAGUETE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GRUD 824',
        'ESPAGUETE',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2.19,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: GS 211 - ESPUMA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'GS 211',
        'ESPUMA',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        24.40,
        'BRL',
        24.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: H7 5LT - DESENGRAXANTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'H7 5LT',
        'DESENGRAXANTE',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        'H7',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        31.12,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    68,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA 2825 - LAMPADA 12V PINGO/ PLACA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA 2825',
        'LAMPADA 12V PINGO/ PLACA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'COMPASS RENEGADE TORO TODOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1.97,
        'BRL',
        20.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    30,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA 7440 - LAMPADA 12V
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA 7440',
        'LAMPADA 12V',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        101.96,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    10,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA 7440 NA LARANJA - LAMPADA 12V
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA 7440 NA LARANJA',
        'LAMPADA 12V',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS VEICULOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        15.46,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    19,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA H11 12V - LAMPADA 12V
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA H11 12V',
        'LAMPADA 12V',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        '',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        44.26,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA H8 12V - LAMPADA 12V
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA H8 12V',
        'LAMPADA 12V',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        45.64,
        'BRL',
        87.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA HB3 12V - LAMPADA 12V
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA HB3 12V',
        'LAMPADA 12V',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS VEICULOS',
        'HELLA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        27.85,
        'BRL',
        87.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HELLA PSX24W - LAMPADA 12V DRL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HELLA PSX24W',
        'LAMPADA 12V DRL',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        51.53,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HF613 - DISCO DE FREIO TRASEIRO JEEP
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HF613',
        'DISCO DE FREIO TRASEIRO JEEP',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENAGADE TODOS',
        'HIPPER FREIOS',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        183.45,
        'BRL',
        439.67,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HG41172 / HG41173 - AMORTECEDOR DIANTEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HG41172 / HG41173',
        'AMORTECEDOR DIANTEIRO',
        '',
        '',
        '',
        '',
        '',
        '',
        'NAKATA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        424.82,
        'BRL',
        837.94,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HG41174 / HG41175 - AMORTECEDOR TRASEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HG41174 / HG41175',
        'AMORTECEDOR TRASEIRO',
        '',
        '',
        '',
        '',
        '',
        'COMPASS',
        'NAKATA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        443.81,
        'BRL',
        890.58,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: HG41196 / HG41197 - AMORTECEDOR TRASEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'HG41196 / HG41197',
        'AMORTECEDOR TRASEIRO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        'NAKATA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        449.36,
        'BRL',
        869.96,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: IWDR-FPM - RETENTOR DO VOLANTE ELRING
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'IWDR-FPM',
        'RETENTOR DO VOLANTE ELRING',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        '93X172/139,7X12 VEICULOS DIESEL',
        'ELRING',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        113.38,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: IZKR8C10D 93162 - JOGO VELA DE IGNICAO  RENEGADE 1.8 FLEX / TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'IZKR8C10D 93162',
        'JOGO VELA DE IGNICAO  RENEGADE 1.8 FLEX / TORO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8 FLEX',
        'NGK',
        'JG',
        '',
        '',
        0,
        'REVENDA',
        0,
        92.84,
        'BRL',
        742.72,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: JCB2215 - ANTENA RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'JCB2215',
        'ANTENA RENEGADE',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8 ETORQ',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: JEP059 - COXIM DO AMORTECEDOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'JEP059',
        'COXIM DO AMORTECEDOR',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE E COMPASS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        310.00,
        'BRL',
        310.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: JL40481K - KIT DE JUNTAS CAVALETE DA EGR DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'JL40481K',
        'KIT DE JUNTAS CAVALETE DA EGR DIESEL',
        '',
        '',
        '',
        '',
        'B15',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'JUNTAS LIMA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        143.99,
        'BRL',
        421.44,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: K04892339BE - FILTRO DE OLEO DO MOTOR ORIGINAL MOPAR COMPASS FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'K04892339BE',
        'FILTRO DE OLEO DO MOTOR ORIGINAL MOPAR COMPASS FLEX',
        '',
        '',
        '',
        '',
        'C4',
        'COMPASS 2.0 FLEx',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        75.73,
        'BRL',
        175.89,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: K05047861AD - VALVULA TERMOSTATICA ORIGINAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'K05047861AD',
        'VALVULA TERMOSTATICA ORIGINAL',
        '',
        '',
        '',
        '',
        'E3',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        400.00,
        'BRL',
        999.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: K06508858AA - PARAFUSO DO CABEÇOTE 2.0 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'K06508858AA',
        'PARAFUSO DO CABEÇOTE 2.0 FLEX',
        '',
        '',
        '',
        '',
        'B8',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        36.22,
        'BRL',
        173.71,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    19,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: K68253029AC - COXIM BIELA INFERIOR  T270
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'K68253029AC',
        'COXIM BIELA INFERIOR  T270',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS T270',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        199.99,
        'BRL',
        199.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: K68258709AF - CHICOTE INJEÇAO JEEP COMPASS FLEX 2.0
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'K68258709AF',
        'CHICOTE INJEÇAO JEEP COMPASS FLEX 2.0',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        250.00,
        'BRL',
        220.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: K68634788AC - MODULO DA BCM
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'K68634788AC',
        'MODULO DA BCM',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2022 P/ CIMA',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2618.37,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KRL109292AD - CONVERSOR CAMBIO RENEGADE E COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KRL109292AD',
        'CONVERSOR CAMBIO RENEGADE E COMPASS',
        '',
        '',
        '',
        '',
        'KRL109292AD',
        'COMPASS RENEGADE',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        1200.00,
        'BRL',
        1200.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KSP261405AB - JOGO VELA IGNICAO ORIGINAL MOPAR COMPASS FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KSP261405AB',
        'JOGO VELA IGNICAO ORIGINAL MOPAR COMPASS FLEX',
        '',
        '',
        '',
        '',
        'B3',
        'COMPASS 2.0 FLEX',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        84.28,
        'BRL',
        834.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: KTB759 - KIT CORREIA DENTADA COMPLETO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'KTB759',
        'KIT CORREIA DENTADA COMPLETO DIESEL',
        '',
        '',
        '',
        '',
        'D3',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'DAYCO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        521.53,
        'BRL',
        1234.98,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: LC001 - FLANGE ADAPTADOR ALUMINIO 10MM LC
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'LC001',
        'FLANGE ADAPTADOR ALUMINIO 10MM LC',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE, TOR, COMPASS COM TRANMISSÃO AUTOMATICA , UTILIZADO PARA ADAPTAR O RADIADOR DE OLEO',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        175.00,
        'BRL',
        350.06,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    3,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: LC002 - MANGUEIRA HIDRAULICA PARA SISTEMA RADIADOR DE OLEO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'LC002',
        'MANGUEIRA HIDRAULICA PARA SISTEMA RADIADOR DE OLEO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE TORO COMPASS FLEX QUE PRECISA DA ADPTAÇÃO DO RADIADOR DE OLEO',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        55.00,
        'BRL',
        245.31,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: LIT920916 - POLIA CATRACA DO ALTERNADOR LITENS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'LIT920916',
        'POLIA CATRACA DO ALTERNADOR LITENS',
        '',
        '',
        '',
        '',
        'B5',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'LITENS',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        238.04,
        'BRL',
        415.90,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MA64062 - HOMOCINETICA  25/27
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MA64062',
        'HOMOCINETICA  25/27',
        '',
        '',
        '',
        '',
        'G3',
        'COMPASS 2.0 FLEX / RENEGADE E COMPASS DIESEL',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        251.69,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    5,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MF72LD - BATERIA VEICULOS C/START STOP 72AH MOURA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MF72LD',
        'BATERIA VEICULOS C/START STOP 72AH MOURA',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE E  COMPASS',
        'MOURA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        687.31,
        'BRL',
        1444.21,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MF75LD - BATERIA VEICULOS S/START STOP 72AH MOURA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MF75LD',
        'BATERIA VEICULOS S/START STOP 72AH MOURA',
        '',
        '',
        '',
        '',
        '',
        'COMPASS E RENEGADE DIESEL',
        'MOURA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        681.67,
        'BRL',
        681.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MLB3901140665 - COMANDO DE AR CONDICIONADO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MLB3901140665',
        'COMANDO DE AR CONDICIONADO',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        350.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MLB4233906692 - VALVULA EGR TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MLB4233906692',
        'VALVULA EGR TORO',
        '',
        '',
        '',
        '',
        'H6',
        'TORO COMPASS RENEGADE 2.0 DIESEL 5 PINOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        604.69,
        'BRL',
        1910.89,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MLB5124832100 - FECHADURA TRAVA ELETRICA JEEP RENEGADE DIANTEIRA ESQUERDA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MLB5124832100',
        'FECHADURA TRAVA ELETRICA JEEP RENEGADE DIANTEIRA ESQUERDA',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        249.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: MO5260 - CALCO  DE MOLA DIANTERA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'MO5260',
        'CALCO  DE MOLA DIANTERA',
        '',
        '',
        '',
        '',
        '',
        'TORO COMPASS RENEGADE',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        27.60,
        'BRL',
        55.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: N1777C - PASTILHA DE FREIO TRASEIRA TORO, COMPASS E RENAGADE TODOS EXCETO VEÍCULOS 1.3 TURBO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'N1777C',
        'PASTILHA DE FREIO TRASEIRA TORO, COMPASS E RENAGADE TODOS EXCETO VEÍCULOS 1.3 TURBO',
        '',
        '',
        '',
        '',
        'A15',
        'TORO, COMPASS E RENAGADE TODOS EXCETO VEÍCULOS 1.3 TURBO',
        'COBREQ',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        181.09,
        'BRL',
        471.70,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: N99250 - PIVO INFERIOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'N99250',
        'PIVO INFERIOR',
        '',
        '',
        '',
        '',
        'G4',
        'VEICULOS 4X4',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        69.62,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: NBJ4015D - BANDEJA DA SUSPENSAO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'NBJ4015D',
        'BANDEJA DA SUSPENSAO',
        '',
        '',
        '',
        '',
        'PARTE BAIXO PRATELEIRA',
        'COMPASS FLEX E RENEGADE DIESEL',
        'GENUINI',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        358.42,
        'BRL',
        755.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: NT40708KNX - KIT JUNTA TAMPA VALVULA COMPASS FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'NT40708KNX',
        'KIT JUNTA TAMPA VALVULA COMPASS FLEX',
        '',
        '',
        '',
        '',
        '',
        'COMPASS FLEX',
        'JUNTAS LIMA',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        445.99,
        'BRL',
        891.96,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: NTR924015 - RETENTOR COMANDO VALVULA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'NTR924015',
        'RETENTOR COMANDO VALVULA',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO RENEGADE 2.0 DIESEL    MEDIDAS 30X45X7',
        'MOPAR',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        95.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: OLEO 5W30 - OLEO DO MOTOR DIESEL 5W30 COM DPF
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'OLEO 5W30',
        'OLEO DO MOTOR DIESEL 5W30 COM DPF',
        '',
        '',
        '',
        '',
        'TAMBOR OFICINA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'VALVOLINE',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        61.29,
        'BRL',
        85.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    138,
    15,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ON153 - FILME PROTETOR DE VOLANTE E CAMBIO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ON153',
        'FILME PROTETOR DE VOLANTE E CAMBIO',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.09,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    77,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ON168 - CAPA PLASTICA BOBINA 5 KG
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ON168',
        'CAPA PLASTICA BOBINA 5 KG',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        165.30,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ON622 - LIMPA CONTATO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ON622',
        'LIMPA CONTATO',
        '',
        '',
        '',
        '',
        'D6',
        'TORO, COMPASS E RENAGADE TODOS',
        'ONIX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        13.05,
        'BRL',
        56.12,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    18,
    5,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ONYX-ON605 - DESCARBONIZANTE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ONYX-ON605',
        'DESCARBONIZANTE',
        '',
        '',
        '',
        '',
        'D6',
        'TORO, COMPASS E RENAGADE TODOS',
        'ONYX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        13.00,
        'BRL',
        56.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    18,
    10,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ov1000115 - CONECTOR TRAVA RETORNO BICO TORO COMPASS RENEGADE 2.0 DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ov1000115',
        'CONECTOR TRAVA RETORNO BICO TORO COMPASS RENEGADE 2.0 DIESEL',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TODOS VEICULOS DIESEL 2.0',
        'OXYXX',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        133.60,
        'BRL',
        33.40,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    8,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: OZA629-A11 - SONDA LAMBDA PRE CATALISADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'OZA629-A11',
        'SONDA LAMBDA PRE CATALISADOR',
        '',
        '',
        '',
        '',
        'B7',
        'RENEGADE 1.8',
        'NTK',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        230.73,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: OZA664-C1 - SONDA LAMBDA POS CATALISADORA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'OZA664-C1',
        'SONDA LAMBDA POS CATALISADORA',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'NTK',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        622.95,
        'BRL',
        622.95,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: OZA664-C4 - SONDA LAMBDA PRE CATALISADORA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'OZA664-C4',
        'SONDA LAMBDA PRE CATALISADORA',
        '',
        '',
        '',
        '',
        '',
        'COMPASS 2.0 FLEX',
        'NTK',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        607.31,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: PD6406 / PD6409 - TERMINAL DE DIRECAO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'PD6406 / PD6409',
        'TERMINAL DE DIRECAO DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TORO COMPASS DIESEL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        108.83,
        'BRL',
        82.88,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: PDX 20565 - BRAÇO AXIAIS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'PDX 20565',
        'BRAÇO AXIAIS',
        '',
        '',
        '',
        '',
        'B14',
        'RENEGADE 1.8 FLEX',
        'PDX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        58.44,
        'BRL',
        155.70,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: PDX 217.10 - BIELETA DIANTEIRA RENEGADE / COMPASS
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'PDX 217.10',
        'BIELETA DIANTEIRA RENEGADE / COMPASS',
        '',
        '',
        '',
        '',
        'C7',
        'RENEGADE COMPASS TORO',
        'PDX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        32.38,
        'BRL',
        100.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: PDX 271.10 - BIELETA TRASEIRA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'PDX 271.10',
        'BIELETA TRASEIRA',
        '',
        '',
        '',
        '',
        '',
        '',
        'PDX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        37.05,
        'BRL',
        157.38,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: PDX 27110 - BIELETA TRASEIRA TORO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'PDX 27110',
        'BIELETA TRASEIRA TORO DIESEL',
        '',
        '',
        '',
        '',
        '',
        'TORO DIESEL',
        'PDX',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        59.62,
        'BRL',
        157.38,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: PR13182 - MANGUEIRA RETORNO BICO DIESEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'PR13182',
        'MANGUEIRA RETORNO BICO DIESEL',
        '',
        '',
        '',
        '',
        '',
        'VEICULOS DIESEL',
        'MOPAR',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        163.19,
        'BRL',
        23.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: R-134a - GAS PARA AR CONDICIONADO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'R-134a',
        'GAS PARA AR CONDICIONADO',
        '',
        '',
        '',
        '',
        '',
        'TODOS OS VEICULOS',
        'EOS',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        0.38,
        'BRL',
        0.38,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    88,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: R04433CP - POLIA LISA C/ PARAFUSO ALTERNADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'R04433CP',
        'POLIA LISA C/ PARAFUSO ALTERNADOR',
        '',
        '',
        '',
        '',
        'A16',
        '',
        'AUTHOMIX',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        63.40,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    15,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: RERENTOR BOMBA OLEO 40x55x7 - RETENTOR BOMBA OLEO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'RERENTOR BOMBA OLEO 40x55x7',
        'RETENTOR BOMBA OLEO',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'COMPASS FLEX 40x55x7 mm',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        95.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: RETENTOR  55X39X13,5 - RETENTOR DO SEMI EIXO CAMBIO 55X39X13,5
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'RETENTOR  55X39X13,5',
        'RETENTOR DO SEMI EIXO CAMBIO 55X39X13,5',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'RENEGADE 1.8',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        255.55,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: s6000f - CAMERA ENDOSCOPIA CBT-600F
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        's6000f',
        'CAMERA ENDOSCOPIA CBT-600F',
        '',
        '',
        '',
        '',
        '',
        '',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        1250.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SAB75404 - JUNTA DA TAMPA DE VALVULA  ETORQ
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SAB75404',
        'JUNTA DA TAMPA DE VALVULA  ETORQ',
        '',
        '',
        '',
        '',
        'E14',
        'RENEGADE TORO 1.8 FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        150.29,
        'BRL',
        699.04,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    6,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SK928S - KIT BATENTE DE AMORTECEDOR DIANTEIRO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SK928S',
        'KIT BATENTE DE AMORTECEDOR DIANTEIRO',
        '',
        '',
        '',
        '',
        'G1',
        'COMPASS TORO RENEGADE',
        'SAMPEL',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        313.58,
        'BRL',
        659.66,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SVA-00034 - ANEL DE VEDACAO CAVALETE OLEO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SVA-00034',
        'ANEL DE VEDACAO CAVALETE OLEO',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'SUL VEDACOES',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        7.90,
        'BRL',
        79.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SVA-000990 - ANEL DE VEDACAO CAVALETE OLEO CENTRAL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SVA-000990',
        'ANEL DE VEDACAO CAVALETE OLEO CENTRAL',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'SUL VEDACOES',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        29.75,
        'BRL',
        79.23,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    4,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SVA-003683 - JUNTA DO SENSOR VARIADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SVA-003683',
        'JUNTA DO SENSOR VARIADOR',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        5.72,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    14,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SVKIT - 006917 - KIT VEDAÇOES BOMBA DE ALTA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SVKIT - 006917',
        'KIT VEDAÇOES BOMBA DE ALTA',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'VEICULOS 2.0 DIESEL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        80.81,
        'BRL',
        239.50,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: SVRT-009163 - VEDAÇÃO SENSOR FASE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'SVRT-009163',
        'VEDAÇÃO SENSOR FASE',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        'CAPRICHO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        30.00,
        'BRL',
        90.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: T-010250 - SENSOR NIVEL/BOIA TSA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'T-010250',
        'SENSOR NIVEL/BOIA TSA',
        '',
        '',
        '',
        '',
        'A5',
        'RENEGADE E TORO 1.8 FLEX',
        'NGK',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        71.63,
        'BRL',
        328.62,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: TC 105.1729 - CONECTOR CHICOTE TURBINA PEQUENO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'TC 105.1729',
        'CONECTOR CHICOTE TURBINA PEQUENO',
        '',
        '',
        '',
        '',
        'ARMARIO MADEIRA',
        'VEICULOS DIESEL',
        'IMPORTADO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        26.05,
        'BRL',
        48.96,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: TC 106.1139 - CONECTOR CHICOTE TAMPA DE COMBUSTIVEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'TC 106.1139',
        'CONECTOR CHICOTE TAMPA DE COMBUSTIVEL',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        18.20,
        'BRL',
        48.96,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: TC-9021-ATF - TURBO COMPRESSOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'TC-9021-ATF',
        'TURBO COMPRESSOR',
        '',
        '',
        '',
        '',
        '',
        'COMPAS, RENEGADE E TORO 2.0',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        2282.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: TC-9021-ATF. - TURBINA COMPLETA NOVA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'TC-9021-ATF.',
        'TURBINA COMPLETA NOVA',
        '',
        '',
        '',
        '',
        '',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'ESTRON',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        2356.16,
        'BRL',
        4712.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    3,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: TRAVA AMARELA - TRAVA AMARELA MANGUEIRA COMBUSTIVEL MOBI TORO RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'TRAVA AMARELA',
        'TRAVA AMARELA MANGUEIRA COMBUSTIVEL MOBI TORO RENEGADE',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'BIS',
        '',
        '',
        0,
        'REVENDA',
        0,
        36.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: TZPO704 - TRIZETA 28 DENTES
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'TZPO704',
        'TRIZETA 28 DENTES',
        '',
        '',
        '',
        '',
        '',
        'COMPASS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        194.65,
        'BRL',
        530.99,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: VADJE13 - VALVULA DE ADMISSAO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'VADJE13',
        'VALVULA DE ADMISSAO',
        '',
        '',
        '',
        '',
        'A15',
        '1.3 TURBO',
        'TAKAO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        53.62,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    7,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: VC253A - COTOVELO DA BOMBA D AGUA TORO E RENEGADE 1.8 FLEX
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'VC253A',
        'COTOVELO DA BOMBA D AGUA TORO E RENEGADE 1.8 FLEX',
        '',
        '',
        '',
        '',
        'B15',
        'TORO RENEGADE 1.8 FLEX',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        76.75,
        'BRL',
        245.28,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    2,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: VESJE13 - VALVULA DE ESCAPE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'VESJE13',
        'VALVULA DE ESCAPE',
        '',
        '',
        '',
        '',
        '',
        '1.3 TURBO',
        'TAKAO',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        115.58,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    9,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: VP 7207 - TAMPA DA BOMBA DE COMBUSTIVEL
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'VP 7207',
        'TAMPA DA BOMBA DE COMBUSTIVEL',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        51.90,
        'BRL',
        146.28,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: VQF0031 - FILTRO 9HP48 BOCAL RETANGULO  CAMBIO AUT.  FIAT TORO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'VQF0031',
        'FILTRO 9HP48 BOCAL RETANGULO  CAMBIO AUT.  FIAT TORO',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        186.67,
        'BRL',
        250.77,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    2,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: VTO B0023 - CUBO RODA COMPASS RENEGADE
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'VTO B0023',
        'CUBO RODA COMPASS RENEGADE',
        '',
        '',
        '',
        '',
        '',
        'COMPASS',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        507.38,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: WAL-1004-01 - JOGO DE VIGA U ELEVADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'WAL-1004-01',
        'JOGO DE VIGA U ELEVADOR',
        '',
        '',
        '',
        '',
        '',
        '',
        'MAHOVI',
        'JG',
        '',
        '',
        0,
        'REVENDA',
        0,
        650.00,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: WD ON620 - WD  ANTICORROSIVO ONYX 408 ML / 252 GR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'WD ON620',
        'WD  ANTICORROSIVO ONYX 408 ML / 252 GR',
        '',
        '',
        '',
        '',
        'D5',
        'USO GERAL',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        12.35,
        'BRL',
        26.20,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    37,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: WE0708 - FILTRO DE CAMBIO AUTOMATICO ZF 9HP48 JK 4645
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'WE0708',
        'FILTRO DE CAMBIO AUTOMATICO ZF 9HP48 JK 4645',
        '',
        '',
        '',
        '',
        'A1',
        'VEICULO FLEX',
        'WEGA',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        129.80,
        'BRL',
        396.87,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: WE1489 - WFC942  FILTRO DE CAMBIO AUTOMATICO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'WE1489',
        'WFC942  FILTRO DE CAMBIO AUTOMATICO',
        '',
        '',
        '',
        '',
        'A1',
        'TODOS VEICULOS',
        '',
        'PC',
        '',
        '',
        0,
        'REVENDA',
        0,
        145.13,
        'BRL',
        296.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: WR4393 - JUNTAS DO COLETOR DE ADMISSAO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'WR4393',
        'JUNTAS DO COLETOR DE ADMISSAO',
        '',
        '',
        '',
        '',
        'ARMARIO DE MADEIRA',
        'TORO, COMPASS E RENEGADE 2.0 DIESEL',
        'CAPRICHO IMPORTS',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        81.45,
        'BRL',
        271.32,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    4,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ZEN 5826 - POLIA CATRACA DO ALTERNADOR
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ZEN 5826',
        'POLIA CATRACA DO ALTERNADOR',
        '',
        '',
        '',
        '',
        'C4',
        'COMPASS 2.0 FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        234.88,
        'BRL',
        438.81,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    1,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ZEN 60303 - ROLAMENTO
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ZEN 60303',
        'ROLAMENTO',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        14.36,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    1,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

-- Produto: ZEN 72665 - RELE DE PARTIDA
WITH grp AS (
    SELECT id FROM catalog_cataloggroup
    WHERE workshop_id = CAST(current_setting('my.workshop_id') AS BIGINT)
    AND name = 'Estoque Geral'
    LIMIT 1
),
upsert_product AS (
    INSERT INTO catalog_product (
        workshop_id, code, name, description, model, sku, barcode, location,
        application, brand, unit, ncm, cest, origin_cst, purpose, profit_margin,
        cost_price, cost_price_currency, selling_price, selling_price_currency,
        group_id, is_active, criado_em, atualizado_em
    )
    SELECT
        CAST(current_setting('my.workshop_id') AS BIGINT),
        'ZEN 72665',
        'RELE DE PARTIDA',
        '',
        '',
        '',
        '',
        '',
        'RENEGADE 1.8 FLEX',
        '',
        'UND',
        '',
        '',
        0,
        'REVENDA',
        0,
        148.52,
        'BRL',
        0.00,
        'BRL',
        grp.id,
        TRUE,
        NOW(),
        NOW()
    FROM grp
    ON CONFLICT (workshop_id, code) DO UPDATE SET
        name = EXCLUDED.name,
        application = EXCLUDED.application,
        brand = EXCLUDED.brand,
        unit = EXCLUDED.unit,
        location = EXCLUDED.location,
        cost_price = EXCLUDED.cost_price,
        selling_price = EXCLUDED.selling_price,
        atualizado_em = NOW()
    RETURNING id
)
INSERT INTO stock_stockproduct (
    workshop_id, product_id, current_quantity, minimum_quantity, restock_quantity, criado_em, atualizado_em
)
SELECT
    CAST(current_setting('my.workshop_id') AS BIGINT),
    upsert_product.id,
    0,
    0,
    0,
    NOW(),
    NOW()
FROM upsert_product
ON CONFLICT (product_id) DO UPDATE SET
    current_quantity = EXCLUDED.current_quantity,
    minimum_quantity = EXCLUDED.minimum_quantity,
    atualizado_em = NOW();

COMMIT;