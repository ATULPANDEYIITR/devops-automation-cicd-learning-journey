-- Dockerfile optimization relational model.
--
-- The schema separates image structure from build context, cache behavior,
-- multi-stage builds, and optimization policy. PostgreSQL constraints are
-- used so invalid optimization states cannot be silently recorded.

DROP VIEW IF EXISTS docker_image_optimization_report;
DROP VIEW IF EXISTS docker_layer_report;

DROP FUNCTION IF EXISTS validate_docker_image(BIGINT);
DROP FUNCTION IF EXISTS calculate_image_size(BIGINT);
DROP FUNCTION IF EXISTS set_updated_at();

DROP TABLE IF EXISTS optimization_violations CASCADE;
DROP TABLE IF EXISTS optimization_policies CASCADE;
DROP TABLE IF EXISTS image_layers CASCADE;
DROP TABLE IF EXISTS image_stages CASCADE;
DROP TABLE IF EXISTS docker_images CASCADE;

CREATE TABLE docker_images (
    image_id BIGSERIAL PRIMARY KEY,
    repository_name TEXT NOT NULL,
    image_tag TEXT NOT NULL,
    build_context_mb NUMERIC(12,2) NOT NULL
        CHECK (build_context_mb >= 0),
    ignored_context_mb NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (ignored_context_mb >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (repository_name, image_tag),
    CHECK (ignored_context_mb <= build_context_mb)
);

CREATE TABLE image_stages (
    stage_id BIGSERIAL PRIMARY KEY,
    image_id BIGINT NOT NULL
        REFERENCES docker_images(image_id)
        ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    stage_order INTEGER NOT NULL
        CHECK (stage_order > 0),
    runtime_stage BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (image_id, stage_name),
    UNIQUE (image_id, stage_order)
);

CREATE TABLE image_layers (
    layer_id BIGSERIAL PRIMARY KEY,
    stage_id BIGINT NOT NULL
        REFERENCES image_stages(stage_id)
        ON DELETE CASCADE,
    layer_order INTEGER NOT NULL
        CHECK (layer_order > 0),
    layer_name TEXT NOT NULL,
    role TEXT NOT NULL
        CHECK (
            role IN (
                'base',
                'dependencies',
                'application',
                'configuration',
                'build-tooling',
                'package-cache'
            )
        ),
    size_mb NUMERIC(12,2) NOT NULL
        CHECK (size_mb >= 0),
    cache_key TEXT NOT NULL,
    cache_stable BOOLEAN NOT NULL DEFAULT FALSE,
    build_only BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (stage_id, layer_order)
);

CREATE TABLE optimization_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    policy_name TEXT NOT NULL UNIQUE,
    maximum_runtime_image_mb NUMERIC(12,2) NOT NULL
        CHECK (maximum_runtime_image_mb > 0),
    maximum_context_mb NUMERIC(12,2) NOT NULL
        CHECK (maximum_context_mb > 0),
    require_stable_dependency_cache BOOLEAN NOT NULL DEFAULT TRUE,
    forbid_build_tooling_in_runtime BOOLEAN NOT NULL DEFAULT TRUE,
    require_multi_stage_when_build_tools_present BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE optimization_violations (
    violation_id BIGSERIAL PRIMARY KEY,
    image_id BIGINT NOT NULL
        REFERENCES docker_images(image_id)
        ON DELETE CASCADE,
    policy_id BIGINT NOT NULL
        REFERENCES optimization_policies(policy_id)
        ON DELETE CASCADE,
    violation_code TEXT NOT NULL,
    detail TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_image_stages_runtime
    ON image_stages (image_id, runtime_stage);

CREATE INDEX idx_layers_stage_role
    ON image_layers (stage_id, role);

CREATE INDEX idx_layers_cache_key
    ON image_layers (cache_key);

CREATE INDEX idx_violations_image
    ON optimization_violations (image_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_docker_images_updated_at
BEFORE UPDATE ON docker_images
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

INSERT INTO optimization_policies (
    policy_name,
    maximum_runtime_image_mb,
    maximum_context_mb,
    require_stable_dependency_cache,
    forbid_build_tooling_in_runtime,
    require_multi_stage_when_build_tools_present
)
VALUES (
    'production-container-policy',
    180,
    150,
    TRUE,
    TRUE,
    TRUE
);

INSERT INTO docker_images (
    repository_name,
    image_tag,
    build_context_mb,
    ignored_context_mb
)
VALUES
    ('orders-api', 'optimized', 420, 295),
    ('orders-api', 'poorly-optimized', 420, 80),
    ('orders-api', 'build-tooling-runtime', 420, 300);

INSERT INTO image_stages (
    image_id,
    stage_name,
    stage_order,
    runtime_stage
)
SELECT image_id, 'runtime', 1, TRUE
FROM docker_images
WHERE image_tag = 'optimized';

INSERT INTO image_stages (
    image_id,
    stage_name,
    stage_order,
    runtime_stage
)
SELECT image_id, 'builder', 1, FALSE
FROM docker_images
WHERE image_tag = 'poorly-optimized';

INSERT INTO image_stages (
    image_id,
    stage_name,
    stage_order,
    runtime_stage
)
SELECT image_id, 'runtime', 2, TRUE
FROM docker_images
WHERE image_tag = 'poorly-optimized';

INSERT INTO image_stages (
    image_id,
    stage_name,
    stage_order,
    runtime_stage
)
SELECT image_id, 'runtime', 1, TRUE
FROM docker_images
WHERE image_tag = 'build-tooling-runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    1,
    'Python slim runtime',
    'base',
    92,
    'python-slim-3.12',
    TRUE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE repository_name = 'orders-api'
  AND image_tag = 'optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    2,
    'Locked production dependencies',
    'dependencies',
    46,
    'requirements-lock-v4',
    TRUE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    3,
    'Application source',
    'application',
    20,
    'application-source',
    FALSE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    4,
    'Runtime configuration',
    'configuration',
    4,
    'runtime-config-v2',
    TRUE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    1,
    'Compiler toolchain',
    'build-tooling',
    95,
    'compiler-v1',
    TRUE,
    TRUE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'poorly-optimized'
  AND stage_name = 'builder';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    2,
    'Application compilation',
    'application',
    20,
    'application-source',
    FALSE,
    TRUE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'poorly-optimized'
  AND stage_name = 'builder';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    1,
    'Runtime base',
    'base',
    92,
    'python-slim-3.12',
    TRUE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'poorly-optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    2,
    'Production dependencies',
    'dependencies',
    46,
    'requirements-lock-v4',
    TRUE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'poorly-optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    3,
    'Compiled application',
    'application',
    20,
    'compiled-output',
    FALSE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'poorly-optimized'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    1,
    'Runtime base',
    'base',
    92,
    'python-slim-3.12',
    TRUE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'build-tooling-runtime'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    2,
    'Compiler retained in runtime',
    'build-tooling',
    70,
    'compiler-v1',
    TRUE,
    TRUE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'build-tooling-runtime'
  AND stage_name = 'runtime';

INSERT INTO image_layers (
    stage_id,
    layer_order,
    layer_name,
    role,
    size_mb,
    layer_name,
    cache_key,
    cache_stable,
    build_only
)
SELECT
    stage_id,
    3,
    'Application source',
    'application',
    22,
    'application-source',
    FALSE,
    FALSE
FROM image_stages
JOIN docker_images USING (image_id)
WHERE image_tag = 'build-tooling-runtime'
  AND stage_name = 'runtime';

CREATE OR REPLACE FUNCTION calculate_image_size(p_image_id BIGINT)
RETURNS NUMERIC
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(SUM(il.size_mb), 0)
    FROM image_layers il
    JOIN image_stages ist
      ON ist.stage_id = il.stage_id
    WHERE ist.image_id = p_image_id
      AND ist.runtime_stage = TRUE;
$$;

CREATE OR REPLACE FUNCTION validate_docker_image(p_image_id BIGINT)
RETURNS TABLE (
    violation_code TEXT,
    detail TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_image RECORD;
    v_policy RECORD;
    v_size NUMERIC;
    v_context NUMERIC;
    v_dependency_order INTEGER;
    v_application_order INTEGER;
BEGIN
    SELECT *
    INTO v_image
    FROM docker_images
    WHERE image_id = p_image_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Docker image % does not exist', p_image_id;
    END IF;

    SELECT *
    INTO v_policy
    FROM optimization_policies
    ORDER BY policy_id
    LIMIT 1;

    v_size := calculate_image_size(p_image_id);
    v_context :=
        v_image.build_context_mb - v_image.ignored_context_mb;

    IF v_size > v_policy.maximum_runtime_image_mb THEN
        violation_code := 'IMAGE_TOO_LARGE';
        detail :=
            format(
                'Runtime image is %.2f MB; policy limit is %.2f MB',
                v_size,
                v_policy.maximum_runtime_image_mb
            );
        RETURN NEXT;
    END IF;

    IF v_context > v_policy.maximum_context_mb THEN
        violation_code := 'CONTEXT_TOO_LARGE';
        detail :=
            format(
                'Effective context is %.2f MB; policy limit is %.2f MB',
                v_context,
                v_policy.maximum_context_mb
            );
        RETURN NEXT;
    END IF;

    SELECT MIN(il.layer_order)
    INTO v_dependency_order
    FROM image_layers il
    JOIN image_stages ist ON ist.stage_id = il.stage_id
    WHERE ist.image_id = p_image_id
      AND ist.runtime_stage = TRUE
      AND il.role = 'dependencies';

    SELECT MIN(il.layer_order)
    INTO v_application_order
    FROM image_layers il
    JOIN image_stages ist ON ist.stage_id = il.stage_id
    WHERE ist.image_id = p_image_id
      AND ist.runtime_stage = TRUE
      AND il.role = 'application';

    IF v_policy.require_stable_dependency_cache
       AND v_dependency_order IS NOT NULL
       AND v_application_order IS NOT NULL
       AND v_dependency_order > v_application_order THEN
        violation_code := 'DEPENDENCY_ORDER';
        detail :=
            'Dependency installation occurs after application content and is vulnerable to unnecessary cache invalidation';
        RETURN NEXT;
    END IF;

    IF v_policy.forbid_build_tooling_in_runtime
       AND EXISTS (
            SELECT 1
            FROM image_layers il
            JOIN image_stages ist ON ist.stage_id = il.stage_id
            WHERE ist.image_id = p_image_id
              AND ist.runtime_stage = TRUE
              AND il.role = 'build-tooling'
       ) THEN
        violation_code := 'BUILD_TOOLING_IN_RUNTIME';
        detail :=
            'Build-only compiler or packaging tooling is retained in the runtime image';
        RETURN NEXT;
    END IF;

    IF v_policy.require_stable_dependency_cache
       AND EXISTS (
            SELECT 1
            FROM image_layers il
            JOIN image_stages ist ON ist.stage_id = il.stage_id
            WHERE ist.image_id = p_image_id
              AND ist.runtime_stage = TRUE
              AND il.role = 'dependencies'
              AND il.cache_stable = FALSE
       ) THEN
        violation_code := 'UNSTABLE_DEPENDENCY_CACHE';
        detail :=
            'Dependency layer does not use a stable dependency-input cache key';
        RETURN NEXT;
    END IF;

    RETURN;
END;
$$;

CREATE VIEW docker_layer_report AS
SELECT
    di.repository_name,
    di.image_tag,
    ist.stage_name,
    ist.runtime_stage,
    il.layer_order,
    il.layer_name,
    il.role,
    il.size_mb,
    il.cache_key,
    il.cache_stable,
    il.build_only
FROM docker_images di
JOIN image_stages ist
  ON ist.image_id = di.image_id
JOIN image_layers il
  ON il.stage_id = ist.stage_id;

CREATE VIEW docker_image_optimization_report AS
WITH runtime_sizes AS (
    SELECT
        di.image_id,
        di.repository_name,
        di.image_tag,
        di.build_context_mb,
        di.ignored_context_mb,
        di.build_context_mb - di.ignored_context_mb
            AS effective_context_mb,
        calculate_image_size(di.image_id)
            AS runtime_image_mb
    FROM docker_images di
),
cache_layers AS (
    SELECT
        ist.image_id,
        COUNT(*) FILTER (
            WHERE il.cache_stable
        ) AS stable_layers,
        COUNT(*) AS runtime_layers
    FROM image_stages ist
    JOIN image_layers il
      ON il.stage_id = ist.stage_id
    WHERE ist.runtime_stage
    GROUP BY ist.image_id
)
SELECT
    rs.repository_name,
    rs.image_tag,
    rs.runtime_image_mb,
    rs.effective_context_mb,
    cl.stable_layers,
    cl.runtime_layers,
    ROUND(
        CASE
            WHEN cl.runtime_layers = 0 THEN 0
            ELSE cl.stable_layers::NUMERIC
                 / cl.runtime_layers * 100
        END,
        2
    ) AS stable_cache_percentage
FROM runtime_sizes rs
JOIN cache_layers cl
  ON cl.image_id = rs.image_id;

-- Transactional validation: all violations for an image are replaced
-- atomically, so reports cannot expose a partially evaluated state.
BEGIN;

INSERT INTO optimization_violations (
    image_id,
    policy_id,
    violation_code,
    detail
)
SELECT
    di.image_id,
    op.policy_id,
    validation.violation_code,
    validation.detail
FROM docker_images di
CROSS JOIN optimization_policies op
CROSS JOIN LATERAL validate_docker_image(di.image_id) validation;

COMMIT;

-- A realistic reporting query comparing optimized and poorly optimized images.
SELECT
    repository_name,
    image_tag,
    runtime_image_mb,
    effective_context_mb,
    stable_cache_percentage
FROM docker_image_optimization_report
ORDER BY runtime_image_mb ASC;

-- Show policy failures with their actual measured values.
SELECT
    di.repository_name,
    di.image_tag,
    ov.violation_code,
    ov.detail
FROM optimization_violations ov
JOIN docker_images di
  ON di.image_id = ov.image_id
ORDER BY di.image_tag, ov.violation_code;

-- Identify runtime layers that should normally belong only to a builder stage.
SELECT
    repository_name,
    image_tag,
    stage_name,
    layer_name,
    size_mb
FROM docker_layer_report
WHERE runtime_stage = TRUE
  AND build_only = TRUE
ORDER BY size_mb DESC;

-- Identify expensive dependency layers and their cache stability.
SELECT
    repository_name,
    image_tag,
    layer_name,
    size_mb,
    cache_key,
    cache_stable
FROM docker_layer_report
WHERE role = 'dependencies'
ORDER BY size_mb DESC;

-- CTE-based estimate of how much image size consists of build tooling.
WITH tooling AS (
    SELECT
        repository_name,
        image_tag,
        SUM(size_mb) AS tooling_mb
    FROM docker_layer_report
    WHERE runtime_stage = TRUE
      AND role = 'build-tooling'
    GROUP BY repository_name, image_tag
)
SELECT
    di.repository_name,
    di.image_tag,
    COALESCE(t.tooling_mb, 0) AS runtime_tooling_mb,
    calculate_image_size(di.image_id) AS runtime_image_mb,
    ROUND(
        COALESCE(t.tooling_mb, 0)
        / NULLIF(calculate_image_size(di.image_id), 0)
        * 100,
        2
    ) AS tooling_percentage
FROM docker_images di
LEFT JOIN tooling t
  ON t.repository_name = di.repository_name
 AND t.image_tag = di.image_tag
ORDER BY tooling_percentage DESC;
