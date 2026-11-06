/*
    JENKINS CREDENTIALS MANAGEMENT
    PostgreSQL 14+

    Models:
      - Credential metadata
      - Credential stores
      - Credential types and scopes
      - Credential ownership
      - Pipeline credential bindings
      - Secret rotation and revocation
      - Expiration management
      - Access policies
      - Audit events
      - Pipeline validation

    SECURITY DESIGN:
      Secret material is deliberately NOT stored in these tables.
      Actual secret values belong in Jenkins Credentials Providers
      or an appropriately secured external secret manager.

    All sample values are simulated metadata.
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS jenkins_security;

SET search_path TO jenkins_security, public;

-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

CREATE TYPE credential_type AS ENUM (
    'SECRET_TEXT',
    'USERNAME_PASSWORD',
    'SSH_PRIVATE_KEY',
    'SECRET_FILE',
    'CERTIFICATE'
);

CREATE TYPE credential_scope AS ENUM (
    'GLOBAL',
    'SYSTEM'
);

CREATE TYPE credential_status AS ENUM (
    'ACTIVE',
    'EXPIRED',
    'REVOKED'
);

CREATE TYPE pipeline_status AS ENUM (
    'DRAFT',
    'VALIDATED',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'BLOCKED'
);

CREATE TYPE audit_action AS ENUM (
    'CREATE',
    'BIND',
    'ROTATE',
    'REVOKE',
    'VALIDATE',
    'EXECUTE',
    'ACCESS_DENIED'
);

-- ============================================================
-- 2. USERS AND ROLES
-- ============================================================

CREATE TABLE security_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    username VARCHAR(100) NOT NULL UNIQUE,

    email VARCHAR(255) NOT NULL UNIQUE,

    role_name VARCHAR(40) NOT NULL
        CHECK (
            role_name IN (
                'ADMIN',
                'SECURITY_ADMIN',
                'DEVOPS',
                'DEVELOPER',
                'BUILD_AGENT',
                'AUDITOR'
            )
        ),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE credential_stores (
    store_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    store_name VARCHAR(120) NOT NULL UNIQUE,

    scope credential_scope NOT NULL,

    description TEXT NOT NULL,

    owner_user_id BIGINT NOT NULL
        REFERENCES security_users(user_id),

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 3. CREDENTIAL METADATA
-- ============================================================

CREATE TABLE credentials (
    credential_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    credential_key VARCHAR(64) NOT NULL UNIQUE
        CHECK (
            credential_key ~ '^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$'
        ),

    display_name VARCHAR(150) NOT NULL,

    description TEXT NOT NULL,

    type credential_type NOT NULL,

    scope credential_scope NOT NULL,

    store_id BIGINT NOT NULL
        REFERENCES credential_stores(store_id),

    owner_user_id BIGINT NOT NULL
        REFERENCES security_users(user_id),

    status credential_status NOT NULL DEFAULT 'ACTIVE',

    secret_version INTEGER NOT NULL DEFAULT 1
        CHECK (secret_version > 0),

    fingerprint VARCHAR(64),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    expires_at TIMESTAMPTZ,

    last_rotated_at TIMESTAMPTZ,

    revoked_at TIMESTAMPTZ,

    CHECK (
        expires_at IS NULL OR expires_at > created_at
    ),

    CHECK (
        status <> 'REVOKED' OR revoked_at IS NOT NULL
    )
);

CREATE INDEX idx_credentials_active
    ON credentials(credential_key)
    WHERE status = 'ACTIVE';

CREATE INDEX idx_credentials_owner
    ON credentials(owner_user_id);

CREATE INDEX idx_credentials_expiration
    ON credentials(expires_at)
    WHERE status = 'ACTIVE' AND expires_at IS NOT NULL;

CREATE INDEX idx_credentials_store
    ON credentials(store_id, status);

-- ============================================================
-- 4. PIPELINE DEFINITIONS
-- ============================================================

CREATE TABLE pipelines (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pipeline_name VARCHAR(150) NOT NULL UNIQUE,

    repository_name VARCHAR(200) NOT NULL,

    branch_name VARCHAR(200) NOT NULL,

    created_by BIGINT NOT NULL
        REFERENCES security_users(user_id),

    status pipeline_status NOT NULL DEFAULT 'DRAFT',

    configuration_hash VARCHAR(64),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 5. PIPELINE CREDENTIAL BINDINGS
-- ============================================================

CREATE TABLE pipeline_credential_bindings (
    binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id)
        ON DELETE CASCADE,

    credential_id BIGINT NOT NULL
        REFERENCES credentials(credential_id),

    environment_name VARCHAR(40) NOT NULL
        CHECK (
            environment_name IN (
                'DEVELOPMENT',
                'TESTING',
                'STAGING',
                'PRODUCTION'
            )
        ),

    variable_name VARCHAR(100) NOT NULL
        CHECK (
            variable_name ~ '^[A-Za-z_][A-Za-z0-9_]*$'
        ),

    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (pipeline_id, credential_id, variable_name)
);

CREATE INDEX idx_bindings_pipeline
    ON pipeline_credential_bindings(pipeline_id, is_enabled);

CREATE INDEX idx_bindings_credential
    ON pipeline_credential_bindings(credential_id);

-- ============================================================
-- 6. ACCESS POLICIES
-- ============================================================

CREATE TABLE credential_access_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    policy_name VARCHAR(150) NOT NULL UNIQUE,

    role_name VARCHAR(40) NOT NULL
        CHECK (
            role_name IN (
                'ADMIN',
                'SECURITY_ADMIN',
                'DEVOPS',
                'DEVELOPER',
                'BUILD_AGENT',
                'AUDITOR'
            )
        ),

    allowed_scope credential_scope NOT NULL,

    allowed_type credential_type,

    can_read BOOLEAN NOT NULL DEFAULT FALSE,

    can_create BOOLEAN NOT NULL DEFAULT FALSE,

    can_rotate BOOLEAN NOT NULL DEFAULT FALSE,

    can_revoke BOOLEAN NOT NULL DEFAULT FALSE,

    can_use_in_pipeline BOOLEAN NOT NULL DEFAULT FALSE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================
-- 7. AUDIT EVENTS
-- ============================================================

CREATE TABLE credential_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    credential_id BIGINT
        REFERENCES credentials(credential_id)
        ON DELETE SET NULL,

    pipeline_id BIGINT
        REFERENCES pipelines(pipeline_id)
        ON DELETE SET NULL,

    actor_id BIGINT
        REFERENCES security_users(user_id)
        ON DELETE SET NULL,

    action audit_action NOT NULL,

    outcome VARCHAR(20) NOT NULL
        CHECK (
            outcome IN (
                'SUCCESS',
                'DENIED',
                'FAILURE'
            )
        ),

    details TEXT NOT NULL DEFAULT '',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_credential_time
    ON credential_audit(credential_id, created_at DESC);

CREATE INDEX idx_audit_actor_time
    ON credential_audit(actor_id, created_at DESC);

CREATE INDEX idx_audit_action
    ON credential_audit(action, outcome);

-- ============================================================
-- 8. CREDENTIAL INTEGRITY TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_credential_store_scope()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actual_scope credential_scope;
BEGIN
    SELECT scope
    INTO actual_scope
    FROM credential_stores
    WHERE store_id = NEW.store_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Credential store does not exist or is inactive';
    END IF;

    IF NEW.scope <> actual_scope THEN
        RAISE EXCEPTION
            'Credential scope must match its credential store scope';
    END IF;

    IF NEW.status = 'REVOKED' AND NEW.revoked_at IS NULL THEN
        NEW.revoked_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_credential_store_scope
BEFORE INSERT OR UPDATE OF store_id, scope, status
ON credentials
FOR EACH ROW
EXECUTE FUNCTION enforce_credential_store_scope();

-- ============================================================
-- 9. CREDENTIAL VERSION MANAGEMENT
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_credential_version()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.secret_version < OLD.secret_version THEN
        RAISE EXCEPTION 'Credential version cannot decrease';
    END IF;

    IF NEW.secret_version > OLD.secret_version THEN
        NEW.last_rotated_at := NOW();
    END IF;

    IF OLD.status = 'REVOKED' AND NEW.status <> 'REVOKED' THEN
        RAISE EXCEPTION
            'Revoked credentials cannot be reactivated';
    END IF;

    IF NEW.status = 'REVOKED' THEN
        NEW.revoked_at := COALESCE(NEW.revoked_at, NOW());
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_credential_version
BEFORE UPDATE
ON credentials
FOR EACH ROW
EXECUTE FUNCTION enforce_credential_version();

-- ============================================================
-- 10. PIPELINE BINDING VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_pipeline_binding()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    credential_record RECORD;
    pipeline_record RECORD;
BEGIN
    SELECT *
    INTO credential_record
    FROM credentials
    WHERE credential_id = NEW.credential_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Credential does not exist';
    END IF;

    SELECT *
    INTO pipeline_record
    FROM pipelines
    WHERE pipeline_id = NEW.pipeline_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline does not exist';
    END IF;

    IF credential_record.status <> 'ACTIVE' THEN
        RAISE EXCEPTION 'Inactive credential cannot be bound';
    END IF;

    IF (
        credential_record.expires_at IS NOT NULL
        AND credential_record.expires_at <= NOW()
    ) THEN
        RAISE EXCEPTION 'Expired credential cannot be bound';
    END IF;

    IF credential_record.scope = 'SYSTEM' THEN
        RAISE EXCEPTION
            'System credentials cannot be bound through this pipeline interface';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_pipeline_binding
BEFORE INSERT OR UPDATE
ON pipeline_credential_bindings
FOR EACH ROW
EXECUTE FUNCTION validate_pipeline_binding();

-- ============================================================
-- 11. CREDENTIAL REGISTRATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION register_credential(
    p_key VARCHAR(64),
    p_name VARCHAR(150),
    p_description TEXT,
    p_type credential_type,
    p_scope credential_scope,
    p_store_id BIGINT,
    p_owner_id BIGINT,
    p_fingerprint VARCHAR(64),
    p_expires_at TIMESTAMPTZ DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    new_id BIGINT;
BEGIN
    IF p_key !~ '^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$' THEN
        RAISE EXCEPTION 'Invalid credential key';
    END IF;

    IF p_name IS NULL OR LENGTH(TRIM(p_name)) = 0 THEN
        RAISE EXCEPTION 'Credential name is required';
    END IF;

    IF p_description IS NULL OR LENGTH(TRIM(p_description)) = 0 THEN
        RAISE EXCEPTION 'Credential description is required';
    END IF;

    IF (
        p_expires_at IS NOT NULL
        AND p_expires_at <= NOW()
    ) THEN
        RAISE EXCEPTION 'Expiration must be in the future';
    END IF;

    INSERT INTO credentials (
        credential_key,
        display_name,
        description,
        type,
        scope,
        store_id,
        owner_user_id,
        fingerprint,
        expires_at
    )
    VALUES (
        p_key,
        p_name,
        p_description,
        p_type,
        p_scope,
        p_store_id,
        p_owner_id,
        p_fingerprint,
        p_expires_at
    )
    RETURNING credential_id INTO new_id;

    INSERT INTO credential_audit (
        credential_id,
        actor_id,
        action,
        outcome,
        details
    )
    VALUES (
        new_id,
        p_owner_id,
        'CREATE',
        'SUCCESS',
        'Credential metadata registered'
    );

    RETURN new_id;
END;
$$;

-- ============================================================
-- 12. ROTATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE rotate_credential(
    p_credential_id BIGINT,
    p_actor_id BIGINT,
    p_new_fingerprint VARCHAR(64)
)
LANGUAGE plpgsql
AS $$
DECLARE
    current_status credential_status;
BEGIN
    SELECT status
    INTO current_status
    FROM credentials
    WHERE credential_id = p_credential_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Credential not found';
    END IF;

    IF current_status = 'REVOKED' THEN
        RAISE EXCEPTION 'Revoked credential cannot be rotated';
    END IF;

    IF p_new_fingerprint IS NULL OR LENGTH(TRIM(p_new_fingerprint)) = 0 THEN
        RAISE EXCEPTION 'New fingerprint is required';
    END IF;

    UPDATE credentials
    SET
        secret_version = secret_version + 1,
        fingerprint = p_new_fingerprint,
        status = 'ACTIVE',
        expires_at = NULL
    WHERE credential_id = p_credential_id;

    INSERT INTO credential_audit (
        credential_id,
        actor_id,
        action,
        outcome,
        details
    )
    VALUES (
        p_credential_id,
        p_actor_id,
        'ROTATE',
        'SUCCESS',
        'Credential version incremented'
    );
END;
$$;

-- ============================================================
-- 13. REVOCATION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE revoke_credential(
    p_credential_id BIGINT,
    p_actor_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE credentials
    SET
        status = 'REVOKED',
        revoked_at = NOW()
    WHERE credential_id = p_credential_id
      AND status <> 'REVOKED';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Credential not found or already revoked';
    END IF;

    UPDATE pipeline_credential_bindings
    SET is_enabled = FALSE
    WHERE credential_id = p_credential_id;

    INSERT INTO credential_audit (
        credential_id,
        actor_id,
        action,
        outcome,
        details
    )
    VALUES (
        p_credential_id,
        p_actor_id,
        'REVOKE',
        'SUCCESS',
        'Credential revoked and bindings disabled'
    );
END;
$$;

-- ============================================================
-- 14. PIPELINE ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_pipeline(
    p_pipeline_id BIGINT
)
RETURNS TABLE (
    pipeline_id BIGINT,
    pipeline_name VARCHAR(150),
    eligible BOOLEAN,
    credential_count BIGINT,
    invalid_count BIGINT,
    decision TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        p.pipeline_id,
        p.pipeline_name,

        (
            COUNT(b.binding_id) > 0
            AND COUNT(b.binding_id) FILTER (
                WHERE
                    c.credential_id IS NULL
                    OR c.status <> 'ACTIVE'
                    OR (
                        c.expires_at IS NOT NULL
                        AND c.expires_at <= NOW()
                    )
                    OR c.scope <> 'GLOBAL'
            ) = 0
        ) AS eligible,

        COUNT(b.binding_id) AS credential_count,

        COUNT(b.binding_id) FILTER (
            WHERE
                c.credential_id IS NULL
                OR c.status <> 'ACTIVE'
                OR (
                    c.expires_at IS NOT NULL
                    AND c.expires_at <= NOW()
                )
                OR c.scope <> 'GLOBAL'
        ) AS invalid_count,

        CASE
            WHEN COUNT(b.binding_id) = 0
                THEN 'NO_CREDENTIAL_BINDINGS'
            WHEN COUNT(b.binding_id) FILTER (
                WHERE
                    c.credential_id IS NULL
                    OR c.status <> 'ACTIVE'
                    OR (
                        c.expires_at IS NOT NULL
                        AND c.expires_at <= NOW()
                    )
                    OR c.scope <> 'GLOBAL'
            ) > 0
                THEN 'BLOCKED'
            ELSE 'ELIGIBLE'
        END AS decision

    FROM pipelines p

    LEFT JOIN pipeline_credential_bindings b
        ON b.pipeline_id = p.pipeline_id
       AND b.is_enabled = TRUE

    LEFT JOIN credentials c
        ON c.credential_id = b.credential_id

    WHERE p.pipeline_id = p_pipeline_id

    GROUP BY p.pipeline_id, p.pipeline_name;
$$;

-- ============================================================
-- 15. EXPIRATION VIEW
-- ============================================================

CREATE VIEW credential_expiration_report AS
SELECT
    c.credential_id,
    c.credential_key,
    c.display_name,
    c.type,
    c.scope,
    c.status,
    c.secret_version,
    u.username AS owner,
    c.expires_at,

    CASE
        WHEN c.status = 'REVOKED'
            THEN 'REVOKED'
        WHEN c.expires_at IS NULL
            THEN 'NO_EXPIRATION'
        WHEN c.expires_at <= NOW()
            THEN 'EXPIRED'
        WHEN c.expires_at <= NOW() + INTERVAL '7 days'
            THEN 'EXPIRING_SOON'
        ELSE 'VALID'
    END AS expiration_state

FROM credentials c

JOIN security_users u
    ON u.user_id = c.owner_user_id;

-- ============================================================
-- 16. ACCESS POLICY EVALUATION
-- ============================================================

CREATE OR REPLACE FUNCTION check_credential_access(
    p_user_id BIGINT,
    p_credential_id BIGINT,
    p_pipeline_usage BOOLEAN DEFAULT FALSE
)
RETURNS TABLE (
    allowed BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    user_record RECORD;
    credential_record RECORD;
BEGIN
    SELECT *
    INTO user_record
    FROM security_users
    WHERE user_id = p_user_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'User missing or inactive'::TEXT;
        RETURN;
    END IF;

    SELECT *
    INTO credential_record
    FROM credentials
    WHERE credential_id = p_credential_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Credential not found'::TEXT;
        RETURN;
    END IF;

    IF credential_record.status <> 'ACTIVE' THEN
        RETURN QUERY
        SELECT FALSE, 'Credential inactive'::TEXT;
        RETURN;
    END IF;

    IF (
        credential_record.expires_at IS NOT NULL
        AND credential_record.expires_at <= NOW()
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'Credential expired'::TEXT;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        EXISTS (
            SELECT 1
            FROM credential_access_policies policy
            WHERE policy.role_name = user_record.role_name
              AND policy.allowed_scope = credential_record.scope
              AND (
                  policy.allowed_type IS NULL
                  OR policy.allowed_type = credential_record.type
              )
              AND policy.is_active = TRUE
              AND (
                  CASE
                      WHEN p_pipeline_usage
                          THEN policy.can_use_in_pipeline
                      ELSE policy.can_read
                  END
              )
        ),
        CASE
            WHEN EXISTS (
                SELECT 1
                FROM credential_access_policies policy
                WHERE policy.role_name = user_record.role_name
                  AND policy.allowed_scope = credential_record.scope
                  AND (
                      policy.allowed_type IS NULL
                      OR policy.allowed_type = credential_record.type
                  )
                  AND policy.is_active = TRUE
                  AND (
                      CASE
                          WHEN p_pipeline_usage
                              THEN policy.can_use_in_pipeline
                          ELSE policy.can_read
                      END
                  )
            )
            THEN 'Access granted'::TEXT
            ELSE 'No matching access policy'::TEXT
        END;
END;
$$;

-- ============================================================
-- 17. SAMPLE USERS
-- ============================================================

INSERT INTO security_users (
    username,
    email,
    role_name
)
VALUES
(
    'security-admin',
    'security@example.com',
    'SECURITY_ADMIN'
),
(
    'devops-engineer',
    'devops@example.com',
    'DEVOPS'
),
(
    'build-agent',
    'build@example.com',
    'BUILD_AGENT'
),
(
    'developer',
    'developer@example.com',
    'DEVELOPER'
),
(
    'auditor',
    'auditor@example.com',
    'AUDITOR'
);

-- ============================================================
-- 18. SAMPLE CREDENTIAL STORES
-- ============================================================

INSERT INTO credential_stores (
    store_name,
    scope,
    description,
    owner_user_id
)
SELECT
    'global-credentials',
    'GLOBAL',
    'Shared Jenkins credential store',
    user_id
FROM security_users
WHERE username = 'security-admin';

INSERT INTO credential_stores (
    store_name,
    scope,
    description,
    owner_user_id
)
SELECT
    'system-credentials',
    'SYSTEM',
    'Controller-level system credentials',
    user_id
FROM security_users
WHERE username = 'security-admin';

-- ============================================================
-- 19. SAMPLE CREDENTIALS
-- ============================================================

SELECT register_credential(
    'github-deploy-token',
    'GitHub Deployment Token',
    'Deployment access token metadata',
    'SECRET_TEXT',
    'GLOBAL',
    (
        SELECT store_id
        FROM credential_stores
        WHERE store_name = 'global-credentials'
    ),
    (
        SELECT user_id
        FROM security_users
        WHERE username = 'security-admin'
    ),
    'SIMULATED-FINGERPRINT-GITHUB'
);

SELECT register_credential(
    'docker-registry',
    'Docker Registry Account',
    'Container registry username/password metadata',
    'USERNAME_PASSWORD',
    'GLOBAL',
    (
        SELECT store_id
        FROM credential_stores
        WHERE store_name = 'global-credentials'
    ),
    (
        SELECT user_id
        FROM security_users
        WHERE username = 'devops-engineer'
    ),
    'SIMULATED-FINGERPRINT-DOCKER',
    NOW() + INTERVAL '30 days'
);

SELECT register_credential(
    'production-ssh',
    'Production SSH Key',
    'Restricted deployment SSH key metadata',
    'SSH_PRIVATE_KEY',
    'SYSTEM',
    (
        SELECT store_id
        FROM credential_stores
        WHERE store_name = 'system-credentials'
    ),
    (
        SELECT user_id
        FROM security_users
        WHERE username = 'security-admin'
    ),
    'SIMULATED-FINGERPRINT-SSH'
);

SELECT register_credential(
    'expired-api-token',
    'Expired API Token',
    'Credential metadata with past expiration',
    'SECRET_TEXT',
    'GLOBAL',
    (
        SELECT store_id
        FROM credential_stores
        WHERE store_name = 'global-credentials'
    ),
    (
        SELECT user_id
        FROM security_users
        WHERE username = 'security-admin'
    ),
    'SIMULATED-FINGERPRINT-EXPIRED'
);

UPDATE credentials
SET expires_at = NOW() - INTERVAL '2 days'
WHERE credential_key = 'expired-api-token';

-- ============================================================
-- 20. SAMPLE PIPELINES
-- ============================================================

INSERT INTO pipelines (
    pipeline_name,
    repository_name,
    branch_name,
    created_by
)
SELECT
    'release-pipeline',
    'company/payment-service',
    'main',
    user_id
FROM security_users
WHERE username = 'devops-engineer';

INSERT INTO pipelines (
    pipeline_name,
    repository_name,
    branch_name,
    created_by
)
SELECT
    'production-deployment',
    'company/payment-service',
    'production',
    user_id
FROM security_users
WHERE username = 'devops-engineer';

-- ============================================================
-- 21. SAMPLE PIPELINE BINDINGS
-- ============================================================

INSERT INTO pipeline_credential_bindings (
    pipeline_id,
    credential_id,
    environment_name,
    variable_name
)
SELECT
    p.pipeline_id,
    c.credential_id,
    'STAGING',
    'GITHUB_TOKEN'
FROM pipelines p
CROSS JOIN credentials c
WHERE p.pipeline_name = 'release-pipeline'
  AND c.credential_key = 'github-deploy-token';

INSERT INTO pipeline_credential_bindings (
    pipeline_id,
    credential_id,
    environment_name,
    variable_name
)
SELECT
    p.pipeline_id,
    c.credential_id,
    'STAGING',
    'DOCKER_AUTH'
FROM pipelines p
CROSS JOIN credentials c
WHERE p.pipeline_name = 'release-pipeline'
  AND c.credential_key = 'docker-registry';

-- ============================================================
-- 22. SAMPLE ACCESS POLICIES
-- ============================================================

INSERT INTO credential_access_policies (
    policy_name,
    role_name,
    allowed_scope,
    allowed_type,
    can_read,
    can_create,
    can_rotate,
    can_revoke,
    can_use_in_pipeline
)
VALUES
(
    'Security administrator global access',
    'SECURITY_ADMIN',
    'GLOBAL',
    NULL,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    TRUE
),
(
    'Security administrator system access',
    'SECURITY_ADMIN',
    'SYSTEM',
    NULL,
    TRUE,
    TRUE,
    TRUE,
    TRUE,
    FALSE
),
(
    'DevOps global pipeline access',
    'DEVOPS',
    'GLOBAL',
    NULL,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    TRUE
),
(
    'Build agent global secret usage',
    'BUILD_AGENT',
    'GLOBAL',
    NULL,
    FALSE,
    FALSE,
    FALSE,
    FALSE,
    TRUE
),
(
    'Auditor metadata access',
    'AUDITOR',
    'GLOBAL',
    NULL,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    FALSE
);

-- ============================================================
-- 23. RETRIEVAL: CREDENTIAL INVENTORY
-- ============================================================

SELECT
    credential_key,
    display_name,
    type,
    scope,
    status,
    secret_version,
    owner_user_id
FROM credentials
ORDER BY credential_key;

-- ============================================================
-- 24. RETRIEVAL: PIPELINE BINDINGS
-- ============================================================

SELECT
    p.pipeline_name,
    p.repository_name,
    p.branch_name,
    b.environment_name,
    b.variable_name,
    c.credential_key,
    c.type,
    c.status
FROM pipeline_credential_bindings b
JOIN pipelines p
    ON p.pipeline_id = b.pipeline_id
JOIN credentials c
    ON c.credential_id = b.credential_id
ORDER BY p.pipeline_name, b.variable_name;

-- ============================================================
-- 25. VALIDATION: INVALID AND EXPIRED CREDENTIALS
-- ============================================================

SELECT
    credential_key,
    status,
    expires_at,
    CASE
        WHEN status = 'REVOKED'
            THEN 'REVOKED'
        WHEN expires_at <= NOW()
            THEN 'EXPIRED'
        ELSE 'VALID'
    END AS validation_result
FROM credentials
WHERE status <> 'ACTIVE'
   OR expires_at <= NOW();

-- ============================================================
-- 26. EVALUATION: PIPELINE ELIGIBILITY
-- ============================================================

SELECT *
FROM evaluate_pipeline(
    (
        SELECT pipeline_id
        FROM pipelines
        WHERE pipeline_name = 'release-pipeline'
    )
);

-- ============================================================
-- 27. EVALUATION: USER ACCESS
-- ============================================================

SELECT *
FROM check_credential_access(
    (
        SELECT user_id
        FROM security_users
        WHERE username = 'build-agent'
    ),
    (
        SELECT credential_id
        FROM credentials
        WHERE credential_key = 'github-deploy-token'
    ),
    TRUE
);

-- ============================================================
-- 28. AGGREGATION: CREDENTIAL DISTRIBUTION
-- ============================================================

SELECT
    type,
    scope,
    status,
    COUNT(*) AS credential_count
FROM credentials
GROUP BY type, scope, status
ORDER BY type, scope, status;

-- ============================================================
-- 29. REPORTING: EXPIRATION
-- ============================================================

SELECT *
FROM credential_expiration_report
ORDER BY expires_at NULLS LAST;

-- ============================================================
-- 30. REPORTING: AUDIT STATISTICS
-- ============================================================

SELECT
    action,
    outcome,
    COUNT(*) AS event_count,
    MAX(created_at) AS latest_event
FROM credential_audit
GROUP BY action, outcome
ORDER BY action, outcome;

-- ============================================================
-- 31. WORKFLOW: ROTATE A CREDENTIAL
-- ============================================================

DO $$
DECLARE
    target_credential BIGINT;
    administrator BIGINT;
BEGIN
    SELECT credential_id
    INTO target_credential
    FROM credentials
    WHERE credential_key = 'docker-registry';

    SELECT user_id
    INTO administrator
    FROM security_users
    WHERE username = 'security-admin';

    CALL rotate_credential(
        target_credential,
        administrator,
        'SIMULATED-NEW-DOCKER-FINGERPRINT'
    );
END;
$$;

-- ============================================================
-- 32. WORKFLOW: REVOKE A CREDENTIAL
-- ============================================================

DO $$
DECLARE
    target_credential BIGINT;
    administrator BIGINT;
BEGIN
    SELECT credential_id
    INTO target_credential
    FROM credentials
    WHERE credential_key = 'expired-api-token';

    SELECT user_id
    INTO administrator
    FROM security_users
    WHERE username = 'security-admin';

    CALL revoke_credential(
        target_credential,
        administrator
    );
END;
$$;

-- ============================================================
-- 33. FAILURE CASE: SYSTEM CREDENTIAL BINDING
-- ============================================================

-- This query is rejected by the binding trigger.
-- Run separately inside an exception-handling transaction if testing:
--
-- INSERT INTO pipeline_credential_bindings (
--     pipeline_id,
--     credential_id,
--     environment_name,
--     variable_name
-- )
-- SELECT
--     p.pipeline_id,
--     c.credential_id,
--     'PRODUCTION',
--     'PRODUCTION_SSH'
-- FROM pipelines p
-- CROSS JOIN credentials c
-- WHERE p.pipeline_name = 'production-deployment'
--   AND c.credential_key = 'production-ssh';

-- ============================================================
-- 34. FAILURE CASE: INVALID CREDENTIAL REGISTRATION
-- ============================================================

-- Invalid credential keys are rejected by register_credential().
--
-- SELECT register_credential(
--     'invalid credential key',
--     'Invalid',
--     'Invalid key example',
--     'SECRET_TEXT',
--     'GLOBAL',
--     1,
--     1,
--     'INVALID'
-- );

-- ============================================================
-- 35. PERFORMANCE: PIPELINE CREDENTIAL USAGE
-- ============================================================

SELECT
    c.credential_key,
    COUNT(DISTINCT b.pipeline_id) AS pipeline_count,
    COUNT(*) FILTER (
        WHERE b.is_enabled = TRUE
    ) AS enabled_bindings
FROM credentials c
LEFT JOIN pipeline_credential_bindings b
    ON b.credential_id = c.credential_id
GROUP BY c.credential_id, c.credential_key
ORDER BY pipeline_count DESC;

-- ============================================================
-- 36. FINAL AUDIT REPORT
-- ============================================================

SELECT
    a.audit_id,
    a.action,
    c.credential_key,
    p.pipeline_name,
    u.username AS actor,
    a.outcome,
    a.details,
    a.created_at
FROM credential_audit a
LEFT JOIN credentials c
    ON c.credential_id = a.credential_id
LEFT JOIN pipelines p
    ON p.pipeline_id = a.pipeline_id
LEFT JOIN security_users u
    ON u.user_id = a.actor_id
ORDER BY a.created_at DESC;

COMMIT;
