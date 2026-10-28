DROP SCHEMA IF EXISTS container_cicd CASCADE;
CREATE SCHEMA container_cicd;

SET search_path = container_cicd, public;

CREATE TYPE pipeline_state AS ENUM (
    'created',
    'built',
    'tested',
    'scanned',
    'published',
    'failed'
);

CREATE TYPE check_status AS ENUM (
    'pending',
    'passed',
    'failed'
);

CREATE TYPE vulnerability_severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    registry TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (name ~ '^[a-z0-9][a-z0-9._/-]*$'),
    CHECK (default_branch ~ '^[A-Za-z0-9._/-]+$')
);

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    name TEXT NOT NULL,
    head_sha CHAR(40) NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, name),
    CHECK (head_sha ~ '^[0-9a-f]{40}$')
);

CREATE TABLE commits (
    commit_sha CHAR(40) PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    parent_sha CHAR(40),
    author_name TEXT NOT NULL,
    message TEXT NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    CHECK (parent_sha IS NULL OR parent_sha ~ '^[0-9a-f]{40}$')
);

CREATE TABLE pipeline_runs (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    source_branch_id BIGINT NOT NULL REFERENCES branches(branch_id),
    commit_sha CHAR(40) NOT NULL REFERENCES commits(commit_sha),
    state pipeline_state NOT NULL DEFAULT 'created',
    image_repository TEXT NOT NULL,
    image_tag TEXT NOT NULL,
    image_digest TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CHECK (image_repository ~ '^[a-z0-9][a-z0-9._/-]*$'),
    CHECK (image_tag ~ '^[A-Za-z0-9_.-]+$'),
    CHECK (
        image_tag NOT IN ('latest', 'prod', 'production')
    ),
    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE TABLE pipeline_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL REFERENCES pipeline_runs(pipeline_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    status check_status NOT NULL DEFAULT 'pending',
    details TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (pipeline_id, check_name),
    CHECK (
        completed_at IS NULL
        OR completed_at >= started_at
    )
);

CREATE TABLE image_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL REFERENCES pipeline_runs(pipeline_id)
        ON DELETE CASCADE,
    package_name TEXT NOT NULL,
    severity vulnerability_severity NOT NULL,
    fixed_version TEXT,
    description TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE registry_publications (
    publication_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL UNIQUE
        REFERENCES pipeline_runs(pipeline_id)
        ON DELETE CASCADE,
    image_digest TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    registry TEXT NOT NULL,
    immutable BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE pipeline_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL REFERENCES pipeline_runs(pipeline_id)
        ON DELETE CASCADE,
    old_state pipeline_state,
    new_state pipeline_state NOT NULL,
    event_message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_pipeline_runs_repository_state
    ON pipeline_runs(repository_id, state);

CREATE INDEX idx_pipeline_checks_status
    ON pipeline_checks(pipeline_id, status);

CREATE INDEX idx_image_findings_pipeline_severity
    ON image_findings(pipeline_id, severity)
    WHERE resolved = FALSE;

CREATE OR REPLACE FUNCTION prevent_unsafe_pipeline_state()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = 'published' THEN
        IF NEW.image_digest IS NULL OR NEW.image_digest = '' THEN
            RAISE EXCEPTION
                'Published pipeline % must have an immutable image digest',
                NEW.pipeline_id;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pipeline_checks pc
            WHERE pc.pipeline_id = NEW.pipeline_id
              AND pc.check_name = 'unit-tests'
              AND pc.status = 'passed'
        ) THEN
            RAISE EXCEPTION
                'Published pipeline % requires passing unit tests',
                NEW.pipeline_id;
        END IF;

        IF NOT EXISTS (
            SELECT 1
            FROM pipeline_checks pc
            WHERE pc.pipeline_id = NEW.pipeline_id
              AND pc.check_name = 'security-scan'
              AND pc.status = 'passed'
        ) THEN
            RAISE EXCEPTION
                'Published pipeline % requires passing security scan',
                NEW.pipeline_id;
        END IF;

        IF EXISTS (
            SELECT 1
            FROM image_findings f
            WHERE f.pipeline_id = NEW.pipeline_id
              AND f.resolved = FALSE
              AND f.severity IN ('high', 'critical')
        ) THEN
            RAISE EXCEPTION
                'Pipeline % contains unresolved high or critical findings',
                NEW.pipeline_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_prevent_unsafe_publication
BEFORE UPDATE OF state ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION prevent_unsafe_pipeline_state();

CREATE OR REPLACE FUNCTION record_pipeline_state_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.state IS DISTINCT FROM NEW.state THEN
        INSERT INTO pipeline_events (
            pipeline_id,
            old_state,
            new_state,
            event_message
        )
        VALUES (
            NEW.pipeline_id,
            OLD.state,
            NEW.state,
            format(
                'Pipeline transitioned from %s to %s',
                OLD.state,
                NEW.state
            )
        );
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pipeline_state_history
AFTER UPDATE OF state ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION record_pipeline_state_change();

CREATE OR REPLACE FUNCTION validate_check_completion()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IN ('passed', 'failed')
       AND NEW.completed_at IS NULL THEN
        NEW.completed_at := now();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_check_completion
BEFORE INSERT OR UPDATE ON pipeline_checks
FOR EACH ROW
EXECUTE FUNCTION validate_check_completion();

CREATE OR REPLACE VIEW pipeline_eligibility AS
WITH check_summary AS (
    SELECT
        pr.pipeline_id,
        bool_or(
            pc.check_name = 'unit-tests'
            AND pc.status = 'passed'
        ) AS tests_passed,
        bool_or(
            pc.check_name = 'security-scan'
            AND pc.status = 'passed'
        ) AS scan_passed
    FROM pipeline_runs pr
    LEFT JOIN pipeline_checks pc
        ON pc.pipeline_id = pr.pipeline_id
    GROUP BY pr.pipeline_id
),
finding_summary AS (
    SELECT
        pipeline_id,
        count(*) FILTER (
            WHERE resolved = FALSE
              AND severity IN ('high', 'critical')
        ) AS blocking_findings
    FROM image_findings
    GROUP BY pipeline_id
)
SELECT
    pr.pipeline_id,
    r.name AS repository,
    b.name AS source_branch,
    pr.commit_sha,
    pr.state,
    pr.image_repository,
    pr.image_tag,
    pr.image_digest,
    COALESCE(cs.tests_passed, FALSE) AS tests_passed,
    COALESCE(cs.scan_passed, FALSE) AS scan_passed,
    COALESCE(fs.blocking_findings, 0) AS blocking_findings,
    (
        pr.state = 'scanned'
        AND pr.image_digest IS NOT NULL
        AND COALESCE(cs.tests_passed, FALSE)
        AND COALESCE(cs.scan_passed, FALSE)
        AND COALESCE(fs.blocking_findings, 0) = 0
    ) AS eligible_for_publication
FROM pipeline_runs pr
JOIN repositories r
    ON r.repository_id = pr.repository_id
JOIN branches b
    ON b.branch_id = pr.source_branch_id
LEFT JOIN check_summary cs
    ON cs.pipeline_id = pr.pipeline_id
LEFT JOIN finding_summary fs
    ON fs.pipeline_id = pr.pipeline_id;

CREATE OR REPLACE FUNCTION publish_pipeline(p_pipeline_id BIGINT)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_registry TEXT;
    v_digest TEXT;
    v_eligible BOOLEAN;
BEGIN
    SELECT
        r.registry,
        pe.image_digest,
        pe.eligible_for_publication
    INTO
        v_registry,
        v_digest,
        v_eligible
    FROM pipeline_eligibility pe
    JOIN pipeline_runs pr
        ON pr.pipeline_id = pe.pipeline_id
    JOIN repositories r
        ON r.repository_id = pr.repository_id
    WHERE pe.pipeline_id = p_pipeline_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline % does not exist', p_pipeline_id;
    END IF;

    IF NOT v_eligible THEN
        RAISE EXCEPTION
            'Pipeline % is not eligible for publication',
            p_pipeline_id;
    END IF;

    UPDATE pipeline_runs
    SET state = 'published',
        completed_at = now()
    WHERE pipeline_id = p_pipeline_id;

    INSERT INTO registry_publications (
        pipeline_id,
        image_digest,
        registry
    )
    VALUES (
        p_pipeline_id,
        v_digest,
        v_registry
    );
END;
$$;

INSERT INTO repositories (name, default_branch, registry)
VALUES
    (
        'platform/payments-api',
        'main',
        'registry.example.com'
    ),
    (
        'platform/catalog-api',
        'main',
        'registry.example.com'
    );

INSERT INTO commits (
    commit_sha,
    repository_id,
    author_name,
    message
)
SELECT
    '1111111111111111111111111111111111111111',
    repository_id,
    'Build Engineer',
    'Add containerized payment service'
FROM repositories
WHERE name = 'platform/payments-api';

INSERT INTO commits (
    commit_sha,
    repository_id,
    author_name,
    message
)
SELECT
    '2222222222222222222222222222222222222222',
    repository_id,
    'Build Engineer',
    'Add catalog service security scan'
FROM repositories
WHERE name = 'platform/catalog-api';

INSERT INTO branches (
    repository_id,
    name,
    head_sha,
    protected
)
SELECT
    repository_id,
    'main',
    CASE
        WHEN name = 'platform/payments-api'
        THEN '1111111111111111111111111111111111111111'
        ELSE '2222222222222222222222222222222222222222'
    END,
    TRUE
FROM repositories;

INSERT INTO branches (
    repository_id,
    name,
    head_sha,
    protected
)
SELECT
    repository_id,
    'feature/container-pipeline',
    CASE
        WHEN name = 'platform/payments-api'
        THEN '1111111111111111111111111111111111111111'
        ELSE '2222222222222222222222222222222222222222'
    END,
    FALSE
FROM repositories;

INSERT INTO pipeline_runs (
    repository_id,
    source_branch_id,
    commit_sha,
    image_repository,
    image_tag,
    image_digest
)
SELECT
    r.repository_id,
    b.branch_id,
    '1111111111111111111111111111111111111111',
    'platform/payments-api',
    '2026.10.28-1111111',
    'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.name = 'platform/payments-api'
  AND b.name = 'feature/container-pipeline';

INSERT INTO pipeline_runs (
    repository_id,
    source_branch_id,
    commit_sha,
    image_repository,
    image_tag
)
SELECT
    r.repository_id,
    b.branch_id,
    '2222222222222222222222222222222222222222',
    'platform/catalog-api',
    '2026.10.28-2222222'
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.name = 'platform/catalog-api'
  AND b.name = 'feature/container-pipeline';

INSERT INTO pipeline_checks (
    pipeline_id,
    check_name,
    status,
    details
)
SELECT
    pipeline_id,
    'unit-tests',
    'passed',
    'All application tests passed'
FROM pipeline_runs
WHERE image_repository = 'platform/payments-api';

INSERT INTO pipeline_checks (
    pipeline_id,
    check_name,
    status,
    details
)
SELECT
    pipeline_id,
    'security-scan',
    'passed',
    'No high or critical findings'
FROM pipeline_runs
WHERE image_repository = 'platform/payments-api';

INSERT INTO pipeline_checks (
    pipeline_id,
    check_name,
    status,
    details
)
SELECT
    pipeline_id,
    'unit-tests',
    'passed',
    'Application tests passed'
FROM pipeline_runs
WHERE image_repository = 'platform/catalog-api';

INSERT INTO pipeline_checks (
    pipeline_id,
    check_name,
    status,
    details
)
SELECT
    pipeline_id,
    'security-scan',
    'failed',
    'High severity dependency vulnerability detected'
FROM pipeline_runs
WHERE image_repository = 'platform/catalog-api';

INSERT INTO image_findings (
    pipeline_id,
    package_name,
    severity,
    fixed_version,
    description
)
SELECT
    pipeline_id,
    'openssl',
    'high',
    '3.0.18',
    'Installed version contains a known high-severity vulnerability'
FROM pipeline_runs
WHERE image_repository = 'platform/catalog-api';

UPDATE pipeline_runs
SET state = 'scanned'
WHERE image_repository IN (
    'platform/payments-api',
    'platform/catalog-api'
);

-- Eligible pipeline.
SELECT
    pipeline_id,
    repository,
    image_tag,
    tests_passed,
    scan_passed,
    blocking_findings,
    eligible_for_publication
FROM pipeline_eligibility
ORDER BY pipeline_id;

-- Transactionally publish the clean pipeline.
BEGIN;

SELECT publish_pipeline(pipeline_id)
FROM pipeline_eligibility
WHERE image_repository = 'platform/payments-api'
  AND eligible_for_publication = TRUE;

COMMIT;

-- This transaction demonstrates rollback when publication prerequisites
-- are not satisfied.
BEGIN;

DO $$
DECLARE
    v_pipeline_id BIGINT;
BEGIN
    SELECT pipeline_id
    INTO v_pipeline_id
    FROM pipeline_runs
    WHERE image_repository = 'platform/catalog-api';

    BEGIN
        PERFORM publish_pipeline(v_pipeline_id);
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Expected publication rejection: %', SQLERRM;
    END;
END;
$$;

ROLLBACK;

-- Operational reporting.
SELECT
    r.name AS repository,
    pr.state,
    count(*) AS pipeline_count
FROM pipeline_runs pr
JOIN repositories r
    ON r.repository_id = pr.repository_id
GROUP BY r.name, pr.state
ORDER BY r.name, pr.state;

SELECT
    r.name AS repository,
    count(f.finding_id) AS unresolved_blocking_findings
FROM repositories r
JOIN pipeline_runs pr
    ON pr.repository_id = r.repository_id
LEFT JOIN image_findings f
    ON f.pipeline_id = pr.pipeline_id
   AND f.resolved = FALSE
   AND f.severity IN ('high', 'critical')
GROUP BY r.name
ORDER BY unresolved_blocking_findings DESC;

SELECT
    pe.pipeline_id,
    pe.repository,
    pe.image_tag,
    pe.eligible_for_publication
FROM pipeline_eligibility pe
WHERE pe.eligible_for_publication = FALSE
ORDER BY pe.pipeline_id;

SELECT
    pipeline_id,
    old_state,
    new_state,
    event_message,
    created_at
FROM pipeline_events
ORDER BY event_id;
