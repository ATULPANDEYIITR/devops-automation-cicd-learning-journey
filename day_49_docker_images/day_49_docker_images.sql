-- PostgreSQL 16+ compatible Docker image inventory and lifecycle model.
--
-- The schema separates:
--   image layers       -> immutable content building blocks
--   image manifests   -> ordered layer collections
--   tags              -> mutable names pointing to image manifests
--   build cache       -> reusable build-step results
--   lifecycle events  -> creation, publication, tagging, and retirement
--
-- A registry is modeled as a publication target. The database does not
-- pretend to replace a real OCI registry or Docker Engine.

DROP SCHEMA IF EXISTS docker_image_lab CASCADE;
CREATE SCHEMA docker_image_lab;
SET search_path TO docker_image_lab;

CREATE TYPE image_state AS ENUM (
    'LOCAL',
    'PUBLISHED',
    'RETIRED'
);

CREATE TYPE lifecycle_event_type AS ENUM (
    'CREATED',
    'TAGGED',
    'UNTAGGED',
    'PUBLISHED',
    'RETIRED'
);

CREATE TYPE cache_result AS ENUM (
    'HIT',
    'MISS'
);

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(name)) > 0)
);

CREATE TABLE image_layers (
    layer_id BIGSERIAL PRIMARY KEY,
    digest TEXT NOT NULL UNIQUE,
    parent_layer_id BIGINT REFERENCES image_layers(layer_id),
    instruction TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (digest LIKE 'sha256:%'),
    CHECK (length(trim(instruction)) > 0),
    CHECK (size_bytes >= 0),
    CHECK (parent_layer_id IS NULL OR parent_layer_id <> layer_id)
);

CREATE INDEX idx_image_layers_parent
    ON image_layers(parent_layer_id);

CREATE TABLE images (
    image_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    content_digest TEXT NOT NULL UNIQUE,
    state image_state NOT NULL DEFAULT 'LOCAL',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    CHECK (content_digest LIKE 'sha256:%'),
    CHECK (
        (state = 'PUBLISHED' AND published_at IS NOT NULL)
        OR state <> 'PUBLISHED'
    ),
    CHECK (
        (state = 'RETIRED' AND retired_at IS NOT NULL)
        OR state <> 'RETIRED'
    )
);

CREATE TABLE image_manifest_layers (
    image_id BIGINT NOT NULL
        REFERENCES images(image_id)
        ON DELETE CASCADE,
    layer_id BIGINT NOT NULL
        REFERENCES image_layers(layer_id),
    layer_order INTEGER NOT NULL,
    PRIMARY KEY (image_id, layer_order),
    UNIQUE (image_id, layer_id),
    CHECK (layer_order >= 0)
);

CREATE INDEX idx_manifest_layers_layer
    ON image_manifest_layers(layer_id);

CREATE TABLE image_tags (
    tag_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    tag TEXT NOT NULL,
    image_id BIGINT NOT NULL
        REFERENCES images(image_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, tag),
    CHECK (length(trim(tag)) > 0)
);

CREATE INDEX idx_image_tags_image
    ON image_tags(image_id);

CREATE TABLE registries (
    registry_id BIGSERIAL PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    CHECK (length(trim(hostname)) > 0)
);

CREATE TABLE registry_publications (
    publication_id BIGSERIAL PRIMARY KEY,
    registry_id BIGINT NOT NULL
        REFERENCES registries(registry_id)
        ON DELETE CASCADE,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    image_id BIGINT NOT NULL
        REFERENCES images(image_id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (registry_id, repository_id, image_id)
);

CREATE TABLE build_cache (
    cache_id BIGSERIAL PRIMARY KEY,
    cache_key TEXT NOT NULL UNIQUE,
    instruction TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    parent_layer_id BIGINT
        REFERENCES image_layers(layer_id),
    resulting_layer_id BIGINT NOT NULL
        REFERENCES image_layers(layer_id),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(cache_key)) > 0),
    CHECK (length(trim(input_fingerprint)) > 0)
);

CREATE INDEX idx_build_cache_last_used
    ON build_cache(last_used_at DESC);

CREATE TABLE build_executions (
    build_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    image_id BIGINT
        REFERENCES images(image_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    successful BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE build_steps (
    build_step_id BIGSERIAL PRIMARY KEY,
    build_id BIGINT NOT NULL
        REFERENCES build_executions(build_id)
        ON DELETE CASCADE,
    step_order INTEGER NOT NULL,
    instruction TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    cache_result cache_result NOT NULL,
    resulting_layer_id BIGINT
        REFERENCES image_layers(layer_id),
    UNIQUE (build_id, step_order),
    CHECK (step_order >= 0)
);

CREATE TABLE image_lifecycle_events (
    event_id BIGSERIAL PRIMARY KEY,
    image_id BIGINT NOT NULL
        REFERENCES images(image_id),
    event_type lifecycle_event_type NOT NULL,
    tag_id BIGINT
        REFERENCES image_tags(tag_id),
    event_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_lifecycle_image_time
    ON image_lifecycle_events(image_id, event_time DESC);

CREATE OR REPLACE FUNCTION touch_tag_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_touch_tag_timestamp
BEFORE UPDATE ON image_tags
FOR EACH ROW
EXECUTE FUNCTION touch_tag_timestamp();

CREATE OR REPLACE FUNCTION validate_image_publication()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'PUBLISHED' AND NEW.published_at IS NULL THEN
        NEW.published_at := now();
    END IF;

    IF NEW.state = 'RETIRED' AND NEW.retired_at IS NULL THEN
        NEW.retired_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_image_publication
BEFORE INSERT OR UPDATE ON images
FOR EACH ROW
EXECUTE FUNCTION validate_image_publication();

CREATE OR REPLACE FUNCTION tag_image(
    p_repository TEXT,
    p_tag TEXT,
    p_image_digest TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_repository_id BIGINT;
    v_image_id BIGINT;
    v_tag_id BIGINT;
BEGIN
    SELECT repository_id
    INTO v_repository_id
    FROM repositories
    WHERE name = p_repository;

    IF v_repository_id IS NULL THEN
        RAISE EXCEPTION 'repository does not exist: %', p_repository;
    END IF;

    SELECT image_id
    INTO v_image_id
    FROM images
    WHERE content_digest = p_image_digest;

    IF v_image_id IS NULL THEN
        RAISE EXCEPTION 'image does not exist: %', p_image_digest;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM images
        WHERE image_id = v_image_id
          AND state = 'RETIRED'
    ) THEN
        RAISE EXCEPTION 'retired images cannot receive new tags';
    END IF;

    INSERT INTO image_tags (
        repository_id,
        tag,
        image_id
    )
    VALUES (
        v_repository_id,
        p_tag,
        v_image_id
    )
    ON CONFLICT (repository_id, tag)
    DO UPDATE SET
        image_id = EXCLUDED.image_id,
        updated_at = now()
    RETURNING tag_id INTO v_tag_id;

    INSERT INTO image_lifecycle_events (
        image_id,
        event_type,
        tag_id,
        details
    )
    VALUES (
        v_image_id,
        'TAGGED',
        v_tag_id,
        jsonb_build_object(
            'repository', p_repository,
            'tag', p_tag
        )
    );

    RETURN v_tag_id;
END;
$$;

CREATE OR REPLACE FUNCTION image_total_size(
    p_image_id BIGINT
)
RETURNS BIGINT
LANGUAGE sql
STABLE
AS $$
    SELECT COALESCE(SUM(il.size_bytes), 0)
    FROM image_manifest_layers iml
    JOIN image_layers il
      ON il.layer_id = iml.layer_id
    WHERE iml.image_id = p_image_id;
$$;

CREATE OR REPLACE VIEW image_inventory AS
SELECT
    i.image_id,
    r.name AS repository,
    i.content_digest,
    i.state,
    i.created_at,
    i.published_at,
    i.retired_at,
    image_total_size(i.image_id) AS logical_layer_bytes,
    COUNT(iml.layer_id) AS layer_count
FROM images i
JOIN repositories r
  ON r.repository_id = i.repository_id
LEFT JOIN image_manifest_layers iml
  ON iml.image_id = i.image_id
GROUP BY
    i.image_id,
    r.name,
    i.content_digest,
    i.state,
    i.created_at,
    i.published_at,
    i.retired_at;

INSERT INTO repositories (name)
VALUES
    ('payments-api'),
    ('orders-api');

INSERT INTO registries (hostname)
VALUES
    ('registry.example.com');

INSERT INTO image_layers (
    digest,
    parent_layer_id,
    instruction,
    size_bytes
)
VALUES
    (
        'sha256:base-node24',
        NULL,
        'FROM node:24-alpine',
        8 * 1024 * 1024
    );

INSERT INTO image_layers (
    digest,
    parent_layer_id,
    instruction,
    size_bytes
)
SELECT
    'sha256:dependencies-v1',
    layer_id,
    'RUN npm ci --omit=dev',
    32 * 1024 * 1024
FROM image_layers
WHERE digest = 'sha256:base-node24';

INSERT INTO image_layers (
    digest,
    parent_layer_id,
    instruction,
    size_bytes
)
SELECT
    'sha256:payments-source-v1',
    layer_id,
    'COPY src/ /workspace/src/',
    180 * 1024
FROM image_layers
WHERE digest = 'sha256:dependencies-v1';

INSERT INTO image_layers (
    digest,
    parent_layer_id,
    instruction,
    size_bytes
)
SELECT
    'sha256:payments-source-v2',
    layer_id,
    'COPY src/ /workspace/src/',
    190 * 1024
FROM image_layers
WHERE digest = 'sha256:dependencies-v1';

INSERT INTO images (
    repository_id,
    content_digest,
    state
)
SELECT
    repository_id,
    'sha256:payments-image-v1',
    'LOCAL'
FROM repositories
WHERE name = 'payments-api';

INSERT INTO images (
    repository_id,
    content_digest,
    state
)
SELECT
    repository_id,
    'sha256:payments-image-v2',
    'PUBLISHED'
FROM repositories
WHERE name = 'payments-api';

INSERT INTO image_manifest_layers (
    image_id,
    layer_id,
    layer_order
)
SELECT
    i.image_id,
    l.layer_id,
    x.layer_order
FROM images i
JOIN LATERAL (
    VALUES
        ('sha256:base-node24', 0),
        ('sha256:dependencies-v1', 1),
        ('sha256:payments-source-v1', 2)
) AS x(digest, layer_order)
    ON TRUE
JOIN image_layers l
  ON l.digest = x.digest
WHERE i.content_digest = 'sha256:payments-image-v1';

INSERT INTO image_manifest_layers (
    image_id,
    layer_id,
    layer_order
)
SELECT
    i.image_id,
    l.layer_id,
    x.layer_order
FROM images i
JOIN LATERAL (
    VALUES
        ('sha256:base-node24', 0),
        ('sha256:dependencies-v1', 1),
        ('sha256:payments-source-v2', 2)
) AS x(digest, layer_order)
    ON TRUE
JOIN image_layers l
  ON l.digest = x.digest
WHERE i.content_digest = 'sha256:payments-image-v2';

INSERT INTO build_cache (
    cache_key,
    instruction,
    input_fingerprint,
    parent_layer_id,
    resulting_layer_id
)
SELECT
    'cache:base-node24',
    'FROM node:24-alpine',
    'node-24-alpine-digest',
    NULL,
    layer_id
FROM image_layers
WHERE digest = 'sha256:base-node24';

INSERT INTO build_cache (
    cache_key,
    instruction,
    input_fingerprint,
    parent_layer_id,
    resulting_layer_id
)
SELECT
    'cache:npm-dependencies-v1',
    'RUN npm ci --omit=dev',
    'package-lock-v1',
    parent_layer_id,
    layer_id
FROM image_layers
WHERE digest = 'sha256:dependencies-v1';

INSERT INTO build_executions (
    repository_id,
    image_id,
    completed_at,
    successful
)
SELECT
    r.repository_id,
    i.image_id,
    now(),
    TRUE
FROM repositories r
JOIN images i
  ON i.repository_id = r.repository_id
WHERE r.name = 'payments-api'
  AND i.content_digest = 'sha256:payments-image-v1';

INSERT INTO build_steps (
    build_id,
    step_order,
    instruction,
    input_fingerprint,
    cache_result,
    resulting_layer_id
)
SELECT
    b.build_id,
    x.step_order,
    x.instruction,
    x.input_fingerprint,
    x.cache_result::cache_result,
    l.layer_id
FROM build_executions b
JOIN LATERAL (
    VALUES
        (
            0,
            'FROM node:24-alpine',
            'node-24-alpine-digest',
            'HIT'
        ),
        (
            1,
            'RUN npm ci --omit=dev',
            'package-lock-v1',
            'HIT'
        ),
        (
            2,
            'COPY src/ /workspace/src/',
            'payments-source-v1',
            'MISS'
        )
) AS x(
    step_order,
    instruction,
    input_fingerprint,
    cache_result
)
ON TRUE
JOIN image_layers l
  ON l.digest = CASE
        WHEN x.step_order = 0
            THEN 'sha256:base-node24'
        WHEN x.step_order = 1
            THEN 'sha256:dependencies-v1'
        ELSE 'sha256:payments-source-v1'
      END
WHERE b.image_id = (
    SELECT image_id
    FROM images
    WHERE content_digest = 'sha256:payments-image-v1'
);

INSERT INTO image_lifecycle_events (
    image_id,
    event_type,
    details
)
SELECT
    image_id,
    'CREATED',
    jsonb_build_object(
        'reason', 'successful build'
    )
FROM images
WHERE content_digest = 'sha256:payments-image-v1';

SELECT tag_image(
    'payments-api',
    '1.0.0',
    'sha256:payments-image-v1'
);

SELECT tag_image(
    'payments-api',
    '1.1.0',
    'sha256:payments-image-v2'
);

SELECT tag_image(
    'payments-api',
    'production',
    'sha256:payments-image-v2'
);

INSERT INTO registry_publications (
    registry_id,
    repository_id,
    image_id
)
SELECT
    rg.registry_id,
    r.repository_id,
    i.image_id
FROM registries rg
JOIN repositories r
  ON r.name = 'payments-api'
JOIN images i
  ON i.content_digest = 'sha256:payments-image-v2'
WHERE rg.hostname = 'registry.example.com';

INSERT INTO image_lifecycle_events (
    image_id,
    event_type,
    details
)
SELECT
    i.image_id,
    'PUBLISHED',
    jsonb_build_object(
        'registry', 'registry.example.com',
        'repository', 'payments-api'
    )
FROM images i
WHERE i.content_digest = 'sha256:payments-image-v2';

-- Layer accounting shows why two images can share most of their storage.
SELECT
    i.content_digest,
    COUNT(*) AS layer_count,
    SUM(l.size_bytes) AS logical_layer_bytes
FROM images i
JOIN image_manifest_layers iml
  ON iml.image_id = i.image_id
JOIN image_layers l
  ON l.layer_id = iml.layer_id
GROUP BY i.content_digest
ORDER BY i.content_digest;

-- This query identifies layers shared by multiple image manifests.
SELECT
    l.digest,
    l.instruction,
    l.size_bytes,
    COUNT(DISTINCT iml.image_id) AS images_using_layer
FROM image_layers l
JOIN image_manifest_layers iml
  ON iml.layer_id = l.layer_id
GROUP BY
    l.digest,
    l.instruction,
    l.size_bytes
HAVING COUNT(DISTINCT iml.image_id) > 1
ORDER BY images_using_layer DESC, l.digest;

-- Tags are mutable references. This result shows that production and 1.1.0
-- currently resolve to the same immutable image digest.
SELECT
    r.name AS repository,
    t.tag,
    i.content_digest,
    i.state
FROM image_tags t
JOIN repositories r
  ON r.repository_id = t.repository_id
JOIN images i
  ON i.image_id = t.image_id
WHERE r.name = 'payments-api'
ORDER BY t.tag;

-- Cache reuse can be inspected by instruction and input fingerprint.
SELECT
    instruction,
    input_fingerprint,
    cache_result,
    COUNT(*) AS executions
FROM build_steps
GROUP BY
    instruction,
    input_fingerprint,
    cache_result
ORDER BY MIN(step_order);

-- The dependency layer is reusable across source-only changes because its
-- cache key is tied to the dependency input rather than application source.
SELECT
    cache_key,
    instruction,
    input_fingerprint,
    last_used_at
FROM build_cache
ORDER BY last_used_at DESC;

-- A safe garbage-collection candidate is a layer no current image references.
-- Real Docker garbage collection also considers containers, tags, build cache,
-- volumes, and registry-specific retention rules.
SELECT
    l.layer_id,
    l.digest,
    l.instruction,
    l.size_bytes
FROM image_layers l
LEFT JOIN image_manifest_layers iml
  ON iml.layer_id = l.layer_id
WHERE iml.layer_id IS NULL
ORDER BY l.size_bytes DESC;

-- Demonstrate a transaction for retagging a release.
BEGIN;

SELECT tag_image(
    'payments-api',
    'candidate',
    'sha256:payments-image-v2'
);

INSERT INTO image_lifecycle_events (
    image_id,
    event_type,
    details
)
SELECT
    image_id,
    'TAGGED',
    jsonb_build_object(
        'tag', 'candidate',
        'reason', 'release candidate promotion'
    )
FROM images
WHERE content_digest = 'sha256:payments-image-v2';

COMMIT;

-- The following intentionally invalid operation is commented out because an
-- executable teaching script should complete successfully:
--
-- INSERT INTO image_layers (
--     digest, instruction, size_bytes
-- )
-- VALUES ('invalid', 'COPY broken', -1);
--
-- The CHECK constraint on size_bytes rejects negative layer sizes.

SELECT *
FROM image_inventory
ORDER BY repository, image_id;
