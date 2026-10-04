-- PostgreSQL implementation of secure Actions secrets and configuration.
--
-- The schema separates repositories, environments, secret definitions,
-- credentials, workflow jobs, and access/audit information. Plaintext secret
-- values are intentionally NOT stored by this schema. A production deployment
-- should store credential material in a dedicated secret-management service
-- and persist only references, metadata, fingerprints, or provider IDs.
--
-- PostgreSQL-specific features used here:
--   * ENUM types
--   * UUID generation
--   * generated timestamps
--   * CHECK constraints
--   * partial indexes
--   * trigger-based lifecycle validation
--   * transactions
--   * common table expressions
--   * views

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP VIEW IF EXISTS deployment_secret_readiness;
DROP TABLE IF EXISTS secret_access_events CASCADE;
DROP TABLE IF EXISTS workflow_secret_requirements CASCADE;
DROP TABLE IF EXISTS workflow_runs CASCADE;
DROP TABLE IF EXISTS branch_environments CASCADE;
DROP TABLE IF EXISTS secret_versions CASCADE;
DROP TABLE IF EXISTS secrets CASCADE;
DROP TABLE IF EXISTS repository_members CASCADE;
DROP TABLE IF EXISTS environments CASCADE;
DROP TABLE IF EXISTS repositories CASCADE;

DROP TYPE IF EXISTS secret_scope CASCADE;
DROP TYPE IF EXISTS secret_state CASCADE;
DROP TYPE IF EXISTS member_role CASCADE;
DROP TYPE IF EXISTS workflow_state CASCADE;

CREATE TYPE secret_scope AS ENUM (
    'organization',
    'repository',
    'environment'
);

CREATE TYPE secret_state AS ENUM (
    'active',
    'disabled',
    'expired'
);

CREATE TYPE member_role AS ENUM (
    'developer',
    'maintainer',
    'security_admin',
    'actions_runner'
);

CREATE TYPE workflow_state AS ENUM (
    'queued',
    'running',
    'succeeded',
    'failed',
    'cancelled'
);

CREATE TABLE repositories (
    repository_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT repository_name_not_blank
        CHECK (length(trim(full_name)) > 0),
    CONSTRAINT default_branch_not_blank
        CHECK (length(trim(default_branch)) > 0)
);

CREATE TABLE environments (
    environment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    environment_name TEXT NOT NULL,
    production BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, environment_name)
);

CREATE TABLE repository_members (
    repository_id UUID NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    principal_name TEXT NOT NULL,
    role member_role NOT NULL,
    PRIMARY KEY (repository_id, principal_name)
);

CREATE TABLE secrets (
    secret_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    scope secret_scope NOT NULL,
    repository_id UUID REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    environment_id UUID REFERENCES environments(environment_id)
        ON DELETE CASCADE,
    provider_reference TEXT,
    current_fingerprint TEXT,
    state secret_state NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,

    CONSTRAINT secret_name_format
        CHECK (name ~ '^[A-Z][A-Z0-9_]{1,99}$'),

    CONSTRAINT secret_name_not_generic
        CHECK (
            name NOT IN ('PASSWORD', 'SECRET', 'TOKEN', 'KEY')
        ),

    CONSTRAINT scope_relationship_is_valid
        CHECK (
            (scope = 'organization'
                AND repository_id IS NULL
                AND environment_id IS NULL)
            OR
            (scope = 'repository'
                AND repository_id IS NOT NULL
                AND environment_id IS NULL)
            OR
            (scope = 'environment'
                AND repository_id IS NOT NULL
                AND environment_id IS NOT NULL)
        ),

    CONSTRAINT fingerprint_not_plaintext
        CHECK (
            current_fingerprint IS NULL
            OR length(current_fingerprint) >= 16
        ),

    CONSTRAINT expiration_after_creation
        CHECK (
            expires_at IS NULL
            OR expires_at > created_at
        )
);

-- The database deliberately has no plaintext secret_value column.
-- provider_reference can identify an external secret-store entry without
-- becoming a credential itself.
CREATE TABLE secret_versions (
    secret_version_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    secret_id UUID NOT NULL REFERENCES secrets(secret_id)
        ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    UNIQUE (secret_id, version_number),
    CONSTRAINT version_number_positive
        CHECK (version_number > 0),
    CONSTRAINT version_fingerprint_valid
        CHECK (length(fingerprint) >= 16)
);

CREATE TABLE branch_environments (
    repository_id UUID NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    environment_id UUID NOT NULL REFERENCES environments(environment_id)
        ON DELETE CASCADE,
    deployment_branch_pattern TEXT NOT NULL,
    requires_approval BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (repository_id, environment_id),
    CONSTRAINT deployment_pattern_not_blank
        CHECK (length(trim(deployment_branch_pattern)) > 0)
);

CREATE TABLE workflow_runs (
    workflow_run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    environment_id UUID REFERENCES environments(environment_id)
        ON DELETE SET NULL,
    workflow_name TEXT NOT NULL,
    actor_name TEXT NOT NULL,
    state workflow_state NOT NULL DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow_secret_requirements (
    workflow_run_id UUID NOT NULL REFERENCES workflow_runs(workflow_run_id)
        ON DELETE CASCADE,
    secret_id UUID NOT NULL REFERENCES secrets(secret_id)
        ON DELETE RESTRICT,
    required BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (workflow_run_id, secret_id)
);

CREATE TABLE secret_access_events (
    access_event_id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    repository_id UUID REFERENCES repositories(repository_id)
        ON DELETE SET NULL,
    environment_id UUID REFERENCES environments(environment_id)
        ON DELETE SET NULL,
    secret_id UUID REFERENCES secrets(secret_id)
        ON DELETE SET NULL,
    principal_name TEXT NOT NULL,
    action TEXT NOT NULL,
    result TEXT NOT NULL,
    reason TEXT,
    CONSTRAINT access_action_valid
        CHECK (
            action IN (
                'create',
                'rotate',
                'read',
                'disable',
                'validate'
            )
        ),
    CONSTRAINT access_result_valid
        CHECK (result IN ('allowed', 'denied'))
);

CREATE INDEX idx_secrets_repository_name
    ON secrets(repository_id, name)
    WHERE state = 'active';

CREATE INDEX idx_secrets_environment_name
    ON secrets(environment_id, name)
    WHERE state = 'active';

CREATE INDEX idx_secret_versions_secret_created
    ON secret_versions(secret_id, created_at DESC);

CREATE INDEX idx_access_events_repository_time
    ON secret_access_events(repository_id, occurred_at DESC);

CREATE INDEX idx_workflow_requirements_run
    ON workflow_secret_requirements(workflow_run_id);

CREATE UNIQUE INDEX ux_org_secret_name
    ON secrets(name)
    WHERE scope = 'organization';

CREATE UNIQUE INDEX ux_repo_secret_name
    ON secrets(repository_id, name)
    WHERE scope = 'repository';

CREATE UNIQUE INDEX ux_environment_secret_name
    ON secrets(environment_id, name)
    WHERE scope = 'environment';

-- A trigger prevents a repository/environment mismatch from being silently
-- accepted when an environment belongs to another repository.
CREATE OR REPLACE FUNCTION validate_secret_environment_repository()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    environment_repository UUID;
BEGIN
    IF NEW.scope = 'environment' THEN
        SELECT repository_id
        INTO environment_repository
        FROM environments
        WHERE environment_id = NEW.environment_id;

        IF environment_repository IS NULL THEN
            RAISE EXCEPTION 'Environment % does not exist', NEW.environment_id;
        END IF;

        IF environment_repository <> NEW.repository_id THEN
            RAISE EXCEPTION
                'Environment % does not belong to repository %',
                NEW.environment_id,
                NEW.repository_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_secret_environment
BEFORE INSERT OR UPDATE ON secrets
FOR EACH ROW
EXECUTE FUNCTION validate_secret_environment_repository();

-- Demonstration repositories.
INSERT INTO repositories (full_name, default_branch)
VALUES
    ('acme/payments', 'main'),
    ('acme/web', 'main');

INSERT INTO environments (
    repository_id,
    environment_name,
    production
)
SELECT
    repository_id,
    environment_name,
    production
FROM (
    VALUES
        ('acme/payments', 'development', false),
        ('acme/payments', 'staging', false),
        ('acme/payments', 'production', true),
        ('acme/web', 'staging', false)
) AS data(full_name, environment_name, production)
JOIN repositories r
    ON r.full_name = data.full_name;

INSERT INTO repository_members (
    repository_id,
    principal_name,
    role
)
SELECT
    r.repository_id,
    data.principal_name,
    data.role::member_role
FROM (
    VALUES
        ('acme/payments', 'security-admin', 'security_admin'),
        ('acme/payments', 'payments-maintainer', 'maintainer'),
        ('acme/payments', 'actions-production-runner', 'actions_runner'),
        ('acme/web', 'web-maintainer', 'maintainer')
) AS data(full_name, principal_name, role)
JOIN repositories r
    ON r.full_name = data.full_name;

INSERT INTO branch_environments (
    repository_id,
    environment_id,
    deployment_branch_pattern,
    requires_approval
)
SELECT
    e.repository_id,
    e.environment_id,
    CASE
        WHEN e.production THEN 'main'
        ELSE 'release/*'
    END,
    e.production
FROM environments e
WHERE e.repository_id = (
    SELECT repository_id
    FROM repositories
    WHERE full_name = 'acme/payments'
);

-- The following records contain metadata and external secret references only.
-- They do not contain plaintext passwords or tokens.
INSERT INTO secrets (
    name,
    scope,
    provider_reference,
    current_fingerprint,
    expires_at
)
VALUES (
    'PACKAGE_REGISTRY_TOKEN',
    'organization',
    'vault://ci/package-registry-token',
    'f0d6c2e4a9910c55',
    now() + interval '90 days'
);

INSERT INTO secrets (
    name,
    scope,
    repository_id,
    provider_reference,
    current_fingerprint,
    expires_at
)
SELECT
    'DATABASE_PASSWORD',
    'repository',
    repository_id,
    'vault://ci/acme-payments/database-password',
    'f1a2b3c4d5e6f789',
    now() + interval '60 days'
FROM repositories
WHERE full_name = 'acme/payments';

INSERT INTO secrets (
    name,
    scope,
    repository_id,
    environment_id,
    provider_reference,
    current_fingerprint,
    expires_at
)
SELECT
    'DATABASE_PASSWORD',
    'environment',
    r.repository_id,
    e.environment_id,
    'vault://ci/acme-payments/production/database-password',
    '8f4a2c91de77a010',
    now() + interval '30 days'
FROM repositories r
JOIN environments e
    ON e.repository_id = r.repository_id
WHERE r.full_name = 'acme/payments'
  AND e.environment_name = 'production';

INSERT INTO secrets (
    name,
    scope,
    repository_id,
    environment_id,
    provider_reference,
    current_fingerprint,
    expires_at
)
SELECT
    'DEPLOY_TOKEN',
    'environment',
    r.repository_id,
    e.environment_id,
    'vault://ci/acme-payments/production/deploy-token',
    'ab19d772ce3310a4f',
    now() + interval '14 days'
FROM repositories r
JOIN environments e
    ON e.repository_id = r.repository_id
WHERE r.full_name = 'acme/payments'
  AND e.environment_name = 'production';

INSERT INTO secret_versions (
    secret_id,
    version_number,
    fingerprint,
    expires_at
)
SELECT
    secret_id,
    1,
    current_fingerprint,
    expires_at
FROM secrets
WHERE name IN (
    'PACKAGE_REGISTRY_TOKEN',
    'DATABASE_PASSWORD',
    'DEPLOY_TOKEN'
);

-- A workflow requests named secrets without copying their values into the
-- workflow database.
INSERT INTO workflow_runs (
    repository_id,
    environment_id,
    workflow_name,
    actor_name,
    state,
    started_at
)
SELECT
    r.repository_id,
    e.environment_id,
    'production-deploy',
    'actions-production-runner',
    'running',
    now()
FROM repositories r
JOIN environments e
    ON e.repository_id = r.repository_id
WHERE r.full_name = 'acme/payments'
  AND e.environment_name = 'production';

INSERT INTO workflow_secret_requirements (
    workflow_run_id,
    secret_id,
    required
)
SELECT
    w.workflow_run_id,
    s.secret_id,
    true
FROM workflow_runs w
JOIN secrets s
    ON (
        s.repository_id = w.repository_id
        OR s.scope = 'organization'
    )
WHERE w.workflow_name = 'production-deploy'
  AND s.name IN (
      'DATABASE_PASSWORD',
      'DEPLOY_TOKEN',
      'PACKAGE_REGISTRY_TOKEN'
  );

-- Effective secret resolution prefers environment scope, then repository
-- scope, then organization scope.
CREATE OR REPLACE VIEW deployment_secret_readiness AS
WITH candidates AS (
    SELECT
        w.workflow_run_id,
        w.workflow_name,
        r.full_name AS repository,
        e.environment_name AS environment,
        s.name AS secret_name,
        s.scope,
        s.state,
        s.expires_at,
        s.provider_reference,
        ROW_NUMBER() OVER (
            PARTITION BY w.workflow_run_id, s.name
            ORDER BY
                CASE s.scope
                    WHEN 'environment' THEN 1
                    WHEN 'repository' THEN 2
                    WHEN 'organization' THEN 3
                END
        ) AS precedence
    FROM workflow_runs w
    JOIN repositories r
        ON r.repository_id = w.repository_id
    LEFT JOIN environments e
        ON e.environment_id = w.environment_id
    JOIN secrets s
        ON (
            s.scope = 'organization'
            OR (
                s.scope = 'repository'
                AND s.repository_id = w.repository_id
            )
            OR (
                s.scope = 'environment'
                AND s.environment_id = w.environment_id
            )
        )
    JOIN workflow_secret_requirements wr
        ON wr.workflow_run_id = w.workflow_run_id
       AND wr.secret_id = s.secret_id
       AND wr.required = true
)
SELECT
    workflow_run_id,
    workflow_name,
    repository,
    environment,
    secret_name,
    scope,
    state,
    expires_at,
    provider_reference,
    (
        state = 'active'
        AND (expires_at IS NULL OR expires_at > now())
    ) AS usable
FROM candidates
WHERE precedence = 1;

-- Inspect effective configuration without exposing credential values.
SELECT
    repository,
    environment,
    secret_name,
    scope,
    usable,
    expires_at,
    provider_reference
FROM deployment_secret_readiness
ORDER BY repository, environment, secret_name;

-- Detect required credentials that are missing, disabled, or expired.
SELECT
    workflow_run_id,
    workflow_name,
    repository,
    environment,
    COUNT(*) FILTER (WHERE usable) AS usable_required_secrets,
    COUNT(*) FILTER (WHERE NOT usable) AS unusable_required_secrets
FROM deployment_secret_readiness
GROUP BY
    workflow_run_id,
    workflow_name,
    repository,
    environment;

-- Demonstrate repository versus production configuration.
SELECT
    s.name,
    s.scope,
    r.full_name AS repository,
    e.environment_name AS environment,
    s.provider_reference,
    s.expires_at
FROM secrets s
LEFT JOIN repositories r
    ON r.repository_id = s.repository_id
LEFT JOIN environments e
    ON e.environment_id = s.environment_id
WHERE s.name = 'DATABASE_PASSWORD'
ORDER BY s.scope;

-- Record a successful validation without storing the credential itself.
INSERT INTO secret_access_events (
    repository_id,
    environment_id,
    secret_id,
    principal_name,
    action,
    result,
    reason
)
SELECT
    r.repository_id,
    e.environment_id,
    s.secret_id,
    'actions-production-runner',
    'validate',
    CASE
        WHEN s.state = 'active'
         AND (s.expires_at IS NULL OR s.expires_at > now())
        THEN 'allowed'
        ELSE 'denied'
    END,
    'Deployment preflight validation'
FROM repositories r
JOIN environments e
    ON e.repository_id = r.repository_id
JOIN secrets s
    ON (
        s.repository_id = r.repository_id
        OR s.scope = 'organization'
    )
WHERE r.full_name = 'acme/payments'
  AND e.environment_name = 'production'
  AND s.name = 'DEPLOY_TOKEN'
LIMIT 1;

-- Transactional credential rotation at the metadata layer.
-- The actual credential replacement would happen in the external secret
-- provider before the reference/fingerprint is committed.
BEGIN;

UPDATE secrets
SET
    provider_reference =
        'vault://ci/acme-payments/production/deploy-token-v2',
    current_fingerprint =
        'c8a7d5e41b2299ef',
    expires_at = now() + interval '14 days',
    updated_at = now(),
    state = 'active'
WHERE name = 'DEPLOY_TOKEN'
  AND scope = 'environment'
  AND repository_id = (
      SELECT repository_id
      FROM repositories
      WHERE full_name = 'acme/payments'
  )
  AND environment_id = (
      SELECT e.environment_id
      FROM environments e
      JOIN repositories r
        ON r.repository_id = e.repository_id
      WHERE r.full_name = 'acme/payments'
        AND e.environment_name = 'production'
  );

INSERT INTO secret_versions (
    secret_id,
    version_number,
    fingerprint,
    expires_at
)
SELECT
    s.secret_id,
    COALESCE(
        (
            SELECT MAX(version_number) + 1
            FROM secret_versions sv
            WHERE sv.secret_id = s.secret_id
        ),
        1
    ),
    s.current_fingerprint,
    s.expires_at
FROM secrets s
WHERE s.name = 'DEPLOY_TOKEN'
  AND s.scope = 'environment'
  AND s.repository_id = (
      SELECT repository_id
      FROM repositories
      WHERE full_name = 'acme/payments'
  );

INSERT INTO secret_access_events (
    repository_id,
    environment_id,
    secret_id,
    principal_name,
    action,
    result,
    reason
)
SELECT
    s.repository_id,
    s.environment_id,
    s.secret_id,
    'security-admin',
    'rotate',
    'allowed',
    'Credential reference and fingerprint rotated'
FROM secrets s
WHERE s.name = 'DEPLOY_TOKEN'
  AND s.scope = 'environment'
  AND s.repository_id = (
      SELECT repository_id
      FROM repositories
      WHERE full_name = 'acme/payments'
  );

COMMIT;

-- Show the final governance state.
SELECT
    r.full_name AS repository,
    e.environment_name,
    s.name AS secret_name,
    s.scope,
    s.state,
    s.expires_at,
    s.provider_reference
FROM secrets s
LEFT JOIN repositories r
    ON r.repository_id = s.repository_id
LEFT JOIN environments e
    ON e.environment_id = s.environment_id
ORDER BY
    r.full_name NULLS FIRST,
    e.environment_name NULLS FIRST,
    s.name;

-- Audit access without credential material.
SELECT
    occurred_at,
    principal_name,
    action,
    result,
    reason
FROM secret_access_events
ORDER BY occurred_at DESC;
