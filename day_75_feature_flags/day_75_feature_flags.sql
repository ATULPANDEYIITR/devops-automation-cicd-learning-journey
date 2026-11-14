/*
===============================================================================
FEATURE FLAG MANAGEMENT AND GOVERNANCE PLATFORM
PostgreSQL 15+

Capabilities:
- Feature flag registration and configuration
- Environment-specific availability
- User and group targeting
- Deterministic percentage rollout
- Version-controlled configuration
- Release approval workflow
- Emergency kill switches
- Evaluation history
- Audit records
- Expiration
- Rollout reporting
- Transactional configuration changes

Execution:
Run the complete script using psql against a PostgreSQL database.
===============================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS feature_management;

SET search_path TO feature_management, public;

-- ============================================================================
-- 1. ENUM TYPES
-- ============================================================================

CREATE TYPE environment_type AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE flag_type AS ENUM (
    'boolean',
    'percentage',
    'targeted'
);

CREATE TYPE flag_status AS ENUM (
    'active',
    'disabled',
    'archived'
);

CREATE TYPE approval_status AS ENUM (
    'pending',
    'approved',
    'rejected'
);

CREATE TYPE change_status AS ENUM (
    'pending',
    'approved',
    'rejected',
    'applied'
);

-- ============================================================================
-- 2. ORGANIZATIONAL IDENTITIES
-- ============================================================================

CREATE TABLE teams (
    team_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_user_id VARCHAR(150) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(150) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_groups (
    group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE user_group_memberships (
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    group_id BIGINT NOT NULL REFERENCES user_groups(group_id),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (user_id, group_id)
);

CREATE TABLE team_members (
    team_id BIGINT NOT NULL REFERENCES teams(team_id),
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    team_role VARCHAR(50) NOT NULL,

    PRIMARY KEY (team_id, user_id),

    CHECK (
        team_role IN (
            'owner',
            'release_manager',
            'developer',
            'viewer'
        )
    )
);

-- ============================================================================
-- 3. FEATURE FLAGS
-- ============================================================================

CREATE TABLE feature_flags (
    flag_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    flag_key VARCHAR(120) NOT NULL UNIQUE,
    description TEXT NOT NULL,

    flag_type flag_type NOT NULL,
    status flag_status NOT NULL DEFAULT 'active',

    default_value BOOLEAN NOT NULL DEFAULT FALSE,

    rollout_percentage NUMERIC(5,2) NOT NULL DEFAULT 0,

    owner_team_id BIGINT NOT NULL REFERENCES teams(team_id),
    created_by BIGINT NOT NULL REFERENCES users(user_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    expires_at TIMESTAMPTZ,

    version BIGINT NOT NULL DEFAULT 1,

    CONSTRAINT valid_flag_key CHECK (
        flag_key ~ '^[a-zA-Z][a-zA-Z0-9_-]*$'
    ),

    CONSTRAINT valid_rollout CHECK (
        rollout_percentage BETWEEN 0 AND 100
    ),

    CONSTRAINT valid_version CHECK (version > 0),

    CONSTRAINT valid_expiration CHECK (
        expires_at IS NULL OR expires_at > created_at
    )
);

-- ============================================================================
-- 4. ENVIRONMENT CONFIGURATION
-- ============================================================================

CREATE TABLE flag_environments (
    flag_id BIGINT NOT NULL REFERENCES feature_flags(flag_id),
    environment environment_type NOT NULL,

    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    PRIMARY KEY (flag_id, environment)
);

-- ============================================================================
-- 5. TARGETING CONFIGURATION
-- ============================================================================

CREATE TABLE flag_user_targets (
    flag_id BIGINT NOT NULL REFERENCES feature_flags(flag_id),
    user_id BIGINT NOT NULL REFERENCES users(user_id),

    PRIMARY KEY (flag_id, user_id)
);

CREATE TABLE flag_group_targets (
    flag_id BIGINT NOT NULL REFERENCES feature_flags(flag_id),
    group_id BIGINT NOT NULL REFERENCES user_groups(group_id),

    PRIMARY KEY (flag_id, group_id)
);

-- ============================================================================
-- 6. RELEASE APPROVAL POLICY
-- ============================================================================

CREATE TABLE flag_approval_policies (
    flag_id BIGINT PRIMARY KEY REFERENCES feature_flags(flag_id),

    required_approvals INTEGER NOT NULL DEFAULT 1,

    require_owner_approval BOOLEAN NOT NULL DEFAULT FALSE,

    require_separation_of_duties BOOLEAN NOT NULL DEFAULT TRUE,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (required_approvals >= 0)
);

CREATE TABLE flag_change_requests (
    request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    flag_id BIGINT NOT NULL REFERENCES feature_flags(flag_id),

    requested_by BIGINT NOT NULL REFERENCES users(user_id),

    change_description TEXT NOT NULL,

    proposed_type flag_type NOT NULL,

    proposed_status flag_status NOT NULL,

    proposed_percentage NUMERIC(5,2) NOT NULL,

    proposed_default_value BOOLEAN NOT NULL,

    status change_status NOT NULL DEFAULT 'pending',

    expected_version BIGINT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    applied_at TIMESTAMPTZ,

    CHECK (
        proposed_percentage BETWEEN 0 AND 100
    )
);

CREATE TABLE flag_change_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    request_id BIGINT NOT NULL
        REFERENCES flag_change_requests(request_id),

    reviewer_id BIGINT NOT NULL REFERENCES users(user_id),

    decision approval_status NOT NULL,

    comments TEXT,

    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (request_id, reviewer_id)
);

-- ============================================================================
-- 7. FLAG EVALUATION HISTORY
-- ============================================================================

CREATE TABLE flag_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    flag_id BIGINT NOT NULL REFERENCES feature_flags(flag_id),

    user_id BIGINT REFERENCES users(user_id),

    environment environment_type NOT NULL,

    enabled BOOLEAN NOT NULL,

    evaluation_reason VARCHAR(100) NOT NULL,

    evaluated_version BIGINT NOT NULL,

    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 8. AUDIT HISTORY
-- ============================================================================

CREATE TABLE flag_audit_log (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    flag_id BIGINT REFERENCES feature_flags(flag_id),

    actor_id BIGINT REFERENCES users(user_id),

    action VARCHAR(80) NOT NULL,

    previous_state JSONB,

    new_state JSONB,

    details JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 9. INDEXES
-- ============================================================================

CREATE INDEX idx_flags_status
ON feature_flags(status);

CREATE INDEX idx_flags_owner
ON feature_flags(owner_team_id);

CREATE INDEX idx_flags_expiration
ON feature_flags(expires_at)
WHERE expires_at IS NOT NULL;

CREATE INDEX idx_flag_evaluations_flag_time
ON flag_evaluations(flag_id, evaluated_at DESC);

CREATE INDEX idx_flag_evaluations_user
ON flag_evaluations(user_id, flag_id);

CREATE INDEX idx_flag_audit_time
ON flag_audit_log(created_at DESC);

CREATE INDEX idx_pending_change_requests
ON flag_change_requests(status, created_at)
WHERE status = 'pending';

CREATE INDEX idx_approval_requests
ON flag_change_approvals(request_id, decision);

-- ============================================================================
-- 10. AUTOMATIC UPDATED_AT MANAGEMENT
-- ============================================================================

CREATE OR REPLACE FUNCTION update_flag_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_flag_updated_at
BEFORE UPDATE ON feature_flags
FOR EACH ROW
EXECUTE FUNCTION update_flag_timestamp();

-- ============================================================================
-- 11. AUTOMATIC AUDIT LOGGING
-- ============================================================================

CREATE OR REPLACE FUNCTION audit_flag_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN

        INSERT INTO flag_audit_log (
            flag_id,
            actor_id,
            action,
            new_state
        )
        VALUES (
            NEW.flag_id,
            NEW.created_by,
            'FLAG_CREATED',
            to_jsonb(NEW)
        );

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN

        INSERT INTO flag_audit_log (
            flag_id,
            action,
            previous_state,
            new_state
        )
        VALUES (
            NEW.flag_id,
            'FLAG_UPDATED',
            to_jsonb(OLD),
            to_jsonb(NEW)
        );

        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_flag_audit
AFTER INSERT OR UPDATE ON feature_flags
FOR EACH ROW
EXECUTE FUNCTION audit_flag_changes();

-- ============================================================================
-- 12. FLAG EVALUATION FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION evaluate_flag(
    p_flag_key VARCHAR,
    p_external_user_id VARCHAR,
    p_environment environment_type,
    p_bucket NUMERIC
)
RETURNS TABLE (
    enabled BOOLEAN,
    reason VARCHAR,
    configuration_version BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_flag feature_flags%ROWTYPE;
    v_user_id BIGINT;
    v_environment_enabled BOOLEAN;
    v_targeted BOOLEAN;
    v_result BOOLEAN;
    v_reason VARCHAR(100);
BEGIN

    IF p_bucket IS NULL OR p_bucket < 0 OR p_bucket >= 100 THEN
        RAISE EXCEPTION 'Bucket must be in [0, 100)';
    END IF;

    IF p_external_user_id IS NULL OR
       LENGTH(TRIM(p_external_user_id)) = 0 THEN
        RAISE EXCEPTION 'User identifier is required';
    END IF;

    SELECT u.user_id
    INTO v_user_id
    FROM users u
    WHERE u.external_user_id = p_external_user_id
      AND u.is_active = TRUE;

    SELECT f.*
    INTO v_flag
    FROM feature_flags f
    WHERE f.flag_key = p_flag_key;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'UNKNOWN_FLAG'::VARCHAR, 0::BIGINT;

        RETURN;
    END IF;

    IF v_user_id IS NULL THEN
        RETURN QUERY
        SELECT FALSE, 'UNKNOWN_OR_INACTIVE_USER'::VARCHAR,
               v_flag.version;

        RETURN;
    END IF;

    IF v_flag.status <> 'active' THEN
        v_result := FALSE;
        v_reason := 'FLAG_INACTIVE';

    ELSIF v_flag.expires_at IS NOT NULL
       AND NOW() >= v_flag.expires_at THEN

        v_result := FALSE;
        v_reason := 'FLAG_EXPIRED';

    ELSE

        SELECT COALESCE(
            (
                SELECT fe.is_enabled
                FROM flag_environments fe
                WHERE fe.flag_id = v_flag.flag_id
                  AND fe.environment = p_environment
            ),
            FALSE
        )
        INTO v_environment_enabled;

        IF NOT v_environment_enabled THEN

            v_result := FALSE;
            v_reason := 'ENVIRONMENT_DISABLED';

        ELSE

            SELECT EXISTS (
                SELECT 1
                FROM flag_user_targets fut
                WHERE fut.flag_id = v_flag.flag_id
                  AND fut.user_id = v_user_id

                UNION ALL

                SELECT 1
                FROM flag_group_targets fgt
                JOIN user_group_memberships ugm
                  ON ugm.group_id = fgt.group_id
                WHERE fgt.flag_id = v_flag.flag_id
                  AND ugm.user_id = v_user_id
            )
            INTO v_targeted;

            IF v_targeted THEN

                v_result := TRUE;
                v_reason := 'EXPLICIT_TARGET_MATCH';

            ELSE

                CASE v_flag.flag_type

                    WHEN 'boolean' THEN
                        v_result := v_flag.default_value;
                        v_reason := 'BOOLEAN_DEFAULT';

                    WHEN 'targeted' THEN
                        v_result := FALSE;
                        v_reason := 'NO_TARGET_MATCH';

                    WHEN 'percentage' THEN
                        v_result :=
                            p_bucket < v_flag.rollout_percentage;

                        v_reason := 'PERCENTAGE_ROLLOUT';

                END CASE;

            END IF;

        END IF;

    END IF;

    INSERT INTO flag_evaluations (
        flag_id,
        user_id,
        environment,
        enabled,
        evaluation_reason,
        evaluated_version
    )
    VALUES (
        v_flag.flag_id,
        v_user_id,
        p_environment,
        v_result,
        v_reason,
        v_flag.version
    );

    RETURN QUERY
    SELECT v_result, v_reason, v_flag.version;

END;
$$;

-- ============================================================================
-- 13. APPROVAL ELIGIBILITY FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION is_change_eligible(
    p_request_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_request flag_change_requests%ROWTYPE;
    v_policy flag_approval_policies%ROWTYPE;
    v_approval_count INTEGER;
    v_rejected_count INTEGER;
    v_owner_approval_count INTEGER;
BEGIN

    SELECT *
    INTO v_request
    FROM flag_change_requests
    WHERE request_id = p_request_id;

    IF NOT FOUND OR v_request.status <> 'pending' THEN
        RETURN FALSE;
    END IF;

    SELECT *
    INTO v_policy
    FROM flag_approval_policies
    WHERE flag_id = v_request.flag_id;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    SELECT
        COUNT(*) FILTER (
            WHERE fca.decision = 'approved'
        ),
        COUNT(*) FILTER (
            WHERE fca.decision = 'rejected'
        ),
        COUNT(*) FILTER (
            WHERE fca.decision = 'approved'
              AND tm.team_role = 'owner'
        )
    INTO
        v_approval_count,
        v_rejected_count,
        v_owner_approval_count
    FROM flag_change_approvals fca
    JOIN users u
      ON u.user_id = fca.reviewer_id
     AND u.is_active = TRUE
    JOIN feature_flags f
      ON f.flag_id = v_request.flag_id
    LEFT JOIN team_members tm
      ON tm.user_id = fca.reviewer_id
     AND tm.team_id = f.owner_team_id
    WHERE fca.request_id = p_request_id
      AND fca.reviewer_id <> v_request.requested_by;

    IF v_rejected_count > 0 THEN
        RETURN FALSE;
    END IF;

    IF v_approval_count < v_policy.required_approvals THEN
        RETURN FALSE;
    END IF;

    IF v_policy.require_owner_approval
       AND v_owner_approval_count = 0 THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$;

-- ============================================================================
-- 14. APPLY APPROVED CHANGE REQUEST
-- ============================================================================

CREATE OR REPLACE PROCEDURE apply_flag_change(
    p_request_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_request flag_change_requests%ROWTYPE;
    v_flag feature_flags%ROWTYPE;
BEGIN

    SELECT *
    INTO v_request
    FROM flag_change_requests
    WHERE request_id = p_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Change request not found';
    END IF;

    IF v_request.status <> 'pending' THEN
        RAISE EXCEPTION 'Request is not pending';
    END IF;

    IF NOT is_change_eligible(p_request_id) THEN
        RAISE EXCEPTION 'Approval policy not satisfied';
    END IF;

    SELECT *
    INTO v_flag
    FROM feature_flags
    WHERE flag_id = v_request.flag_id
    FOR UPDATE;

    IF v_flag.version <> v_request.expected_version THEN
        RAISE EXCEPTION 'Configuration version conflict';
    END IF;

    UPDATE feature_flags
    SET
        flag_type = v_request.proposed_type,
        status = v_request.proposed_status,
        rollout_percentage = v_request.proposed_percentage,
        default_value = v_request.proposed_default_value,
        version = version + 1
    WHERE flag_id = v_request.flag_id;

    UPDATE flag_change_requests
    SET
        status = 'applied',
        applied_at = NOW()
    WHERE request_id = p_request_id;

    INSERT INTO flag_audit_log (
        flag_id,
        actor_id,
        action,
        previous_state,
        new_state,
        details
    )
    VALUES (
        v_request.flag_id,
        v_request.requested_by,
        'CHANGE_REQUEST_APPLIED',
        to_jsonb(v_flag),
        (
            SELECT to_jsonb(f)
            FROM feature_flags f
            WHERE f.flag_id = v_request.flag_id
        ),
        jsonb_build_object(
            'request_id', p_request_id
        )
    );

END;
$$;

-- ============================================================================
-- 15. REPORTING VIEW
-- ============================================================================

CREATE VIEW feature_flag_inventory AS
SELECT
    f.flag_id,
    f.flag_key,
    f.description,
    f.flag_type,
    f.status,
    f.rollout_percentage,
    f.version,
    t.team_name AS owner_team,
    f.expires_at,
    f.created_at,
    f.updated_at,
    COUNT(DISTINCT ev.evaluation_id) AS evaluation_count,
    COUNT(DISTINCT ev.evaluation_id)
        FILTER (WHERE ev.enabled) AS enabled_evaluations
FROM feature_flags f
JOIN teams t
  ON t.team_id = f.owner_team_id
LEFT JOIN flag_evaluations ev
  ON ev.flag_id = f.flag_id
GROUP BY
    f.flag_id,
    t.team_name;

-- ============================================================================
-- 16. REPORTING VIEW: ENVIRONMENT AVAILABILITY
-- ============================================================================

CREATE VIEW flag_environment_inventory AS
SELECT
    f.flag_key,
    f.status,
    fe.environment,
    fe.is_enabled AS environment_enabled,
    f.rollout_percentage,
    f.version
FROM feature_flags f
JOIN flag_environments fe
  ON fe.flag_id = f.flag_id;

COMMIT;

-- ============================================================================
-- 17. SAMPLE ORGANIZATIONAL DATA
-- ============================================================================

INSERT INTO teams (team_name)
VALUES
    ('payments-team'),
    ('search-team'),
    ('platform-team');

INSERT INTO users (
    external_user_id,
    email,
    full_name
)
VALUES
    ('admin_001', 'admin@example.com', 'Platform Administrator'),
    ('user_001', 'user1@example.com', 'Standard User'),
    ('user_002', 'user2@example.com', 'Beta User'),
    ('user_003', 'user3@example.com', 'Staging User'),
    ('manager_001', 'manager@example.com', 'Release Manager'),
    ('reviewer_001', 'reviewer1@example.com', 'Platform Reviewer'),
    ('reviewer_002', 'reviewer2@example.com', 'Payments Reviewer');

INSERT INTO user_groups (group_name, description)
VALUES
    ('standard', 'Standard customer cohort'),
    ('beta_testers', 'Approved beta testing cohort');

INSERT INTO user_group_memberships (user_id, group_id)
SELECT u.user_id, g.group_id
FROM users u
JOIN user_groups g
  ON (
      (u.external_user_id = 'user_001' AND g.group_name = 'standard')
      OR
      (u.external_user_id = 'user_002' AND g.group_name = 'beta_testers')
      OR
      (u.external_user_id = 'user_003' AND g.group_name = 'standard')
  );

INSERT INTO team_members (team_id, user_id, team_role)
SELECT t.team_id, u.user_id, mapping.team_role
FROM (
    VALUES
        ('payments-team', 'admin_001', 'owner'),
        ('payments-team', 'manager_001', 'release_manager'),
        ('payments-team', 'reviewer_001', 'developer'),
        ('payments-team', 'reviewer_002', 'developer'),
        ('platform-team', 'admin_001', 'owner'),
        ('search-team', 'manager_001', 'owner')
) AS mapping(team_name, external_user_id, team_role)
JOIN teams t ON t.team_name = mapping.team_name
JOIN users u ON u.external_user_id = mapping.external_user_id;

-- ============================================================================
-- 18. REGISTER FEATURE FLAGS
-- ============================================================================

INSERT INTO feature_flags (
    flag_key,
    description,
    flag_type,
    status,
    default_value,
    rollout_percentage,
    owner_team_id,
    created_by,
    expires_at
)
SELECT
    'new_checkout',
    'New checkout implementation',
    'percentage',
    'active',
    FALSE,
    25.00,
    t.team_id,
    u.user_id,
    NOW() + INTERVAL '90 days'
FROM teams t
JOIN users u
  ON u.external_user_id = 'admin_001'
WHERE t.team_name = 'payments-team';

INSERT INTO feature_flags (
    flag_key,
    description,
    flag_type,
    status,
    default_value,
    rollout_percentage,
    owner_team_id,
    created_by
)
SELECT
    'new_search',
    'New search engine',
    'boolean',
    'active',
    TRUE,
    0,
    t.team_id,
    u.user_id
FROM teams t
JOIN users u
  ON u.external_user_id = 'admin_001'
WHERE t.team_name = 'search-team';

INSERT INTO feature_flags (
    flag_key,
    description,
    flag_type,
    status,
    default_value,
    rollout_percentage,
    owner_team_id,
    created_by
)
SELECT
    'emergency_payment_route',
    'Alternative payment routing kill switch',
    'boolean',
    'disabled',
    FALSE,
    0,
    t.team_id,
    u.user_id
FROM teams t
JOIN users u
  ON u.external_user_id = 'admin_001'
WHERE t.team_name = 'payments-team';

-- ============================================================================
-- 19. ENVIRONMENT CONFIGURATION
-- ============================================================================

INSERT INTO flag_environments (
    flag_id,
    environment,
    is_enabled
)
SELECT
    f.flag_id,
    env.environment,
    env.is_enabled
FROM feature_flags f
CROSS JOIN (
    VALUES
        ('development'::environment_type, TRUE),
        ('staging'::environment_type, TRUE),
        ('production'::environment_type, TRUE)
) AS env(environment, is_enabled)
WHERE f.flag_key = 'new_checkout';

INSERT INTO flag_environments (
    flag_id,
    environment,
    is_enabled
)
SELECT
    f.flag_id,
    env.environment,
    env.is_enabled
FROM feature_flags f
CROSS JOIN (
    VALUES
        ('development'::environment_type, TRUE),
        ('staging'::environment_type, TRUE),
        ('production'::environment_type, FALSE)
) AS env(environment, is_enabled)
WHERE f.flag_key = 'new_search';

INSERT INTO flag_environments (
    flag_id,
    environment,
    is_enabled
)
SELECT
    f.flag_id,
    'production',
    TRUE
FROM feature_flags f
WHERE f.flag_key = 'emergency_payment_route';

-- ============================================================================
-- 20. EXPLICIT USER AND GROUP TARGETING
-- ============================================================================

INSERT INTO flag_user_targets (flag_id, user_id)
SELECT f.flag_id, u.user_id
FROM feature_flags f
CROSS JOIN users u
WHERE f.flag_key = 'new_checkout'
  AND u.external_user_id = 'admin_001';

INSERT INTO flag_group_targets (flag_id, group_id)
SELECT f.flag_id, g.group_id
FROM feature_flags f
CROSS JOIN user_groups g
WHERE f.flag_key = 'new_checkout'
  AND g.group_name = 'beta_testers';

-- ============================================================================
-- 21. APPROVAL POLICIES
-- ============================================================================

INSERT INTO flag_approval_policies (
    flag_id,
    required_approvals,
    require_owner_approval,
    require_separation_of_duties
)
SELECT
    f.flag_id,
    2,
    FALSE,
    TRUE
FROM feature_flags f;

-- ============================================================================
-- 22. CREATE CHANGE REQUESTS
-- ============================================================================

INSERT INTO flag_change_requests (
    flag_id,
    requested_by,
    change_description,
    proposed_type,
    proposed_status,
    proposed_percentage,
    proposed_default_value,
    expected_version
)
SELECT
    f.flag_id,
    u.user_id,
    'Increase checkout rollout from 25 to 50 percent',
    'percentage',
    'active',
    50.00,
    FALSE,
    f.version
FROM feature_flags f
CROSS JOIN users u
WHERE f.flag_key = 'new_checkout'
  AND u.external_user_id = 'manager_001';

-- ============================================================================
-- 23. REVIEW CHANGE REQUEST
-- ============================================================================

INSERT INTO flag_change_approvals (
    request_id,
    reviewer_id,
    decision,
    comments
)
SELECT
    r.request_id,
    u.user_id,
    'approved',
    'Technical validation completed'
FROM flag_change_requests r
CROSS JOIN users u
WHERE u.external_user_id = 'reviewer_001';

INSERT INTO flag_change_approvals (
    request_id,
    reviewer_id,
    decision,
    comments
)
SELECT
    r.request_id,
    u.user_id,
    'approved',
    'Release risk reviewed'
FROM flag_change_requests r
CROSS JOIN users u
WHERE u.external_user_id = 'reviewer_002';

-- ============================================================================
-- 24. EVALUATION EXAMPLES
-- ============================================================================
-- The bucket is supplied by the caller. Production clients should calculate
-- it deterministically using a consistent hash of flag key and user ID.
-- The bucket must be in [0,100).

SELECT *
FROM evaluate_flag(
    'new_checkout',
    'user_001',
    'production',
    15.0
);

SELECT *
FROM evaluate_flag(
    'new_checkout',
    'user_002',
    'production',
    85.0
);

SELECT *
FROM evaluate_flag(
    'new_checkout',
    'admin_001',
    'production',
    99.0
);

SELECT *
FROM evaluate_flag(
    'new_search',
    'user_003',
    'production',
    10.0
);

-- ============================================================================
-- 25. APPROVAL ELIGIBILITY
-- ============================================================================

SELECT
    request_id,
    change_description,
    status,
    is_change_eligible(request_id) AS eligible
FROM flag_change_requests;

-- ============================================================================
-- 26. APPLY AN APPROVED CHANGE TRANSACTIONALLY
-- ============================================================================

DO $$
DECLARE
    v_request_id BIGINT;
BEGIN

    SELECT request_id
    INTO v_request_id
    FROM flag_change_requests
    WHERE change_description =
        'Increase checkout rollout from 25 to 50 percent'
      AND status = 'pending'
    ORDER BY request_id DESC
    LIMIT 1;

    IF v_request_id IS NOT NULL THEN
        CALL apply_flag_change(v_request_id);
    END IF;

END;
$$;

-- ============================================================================
-- 27. EMERGENCY KILL SWITCH
-- ============================================================================
-- A direct emergency operation is separate from normal approved rollout
-- changes. Restrict execution privileges in production deployments.

BEGIN;

UPDATE feature_flags
SET
    status = 'disabled',
    version = version + 1
WHERE flag_key = 'emergency_payment_route'
  AND status <> 'archived';

COMMIT;

-- ============================================================================
-- 28. VALIDATION QUERIES
-- ============================================================================

-- Flags with invalid or missing environment configuration.
SELECT
    f.flag_key
FROM feature_flags f
LEFT JOIN flag_environments fe
  ON fe.flag_id = f.flag_id
GROUP BY f.flag_id, f.flag_key
HAVING COUNT(fe.environment) = 0;

-- Expired active flags.
SELECT
    flag_key,
    expires_at
FROM feature_flags
WHERE status = 'active'
  AND expires_at IS NOT NULL
  AND expires_at <= NOW();

-- Pending changes without enough approvals.
SELECT
    r.request_id,
    r.change_description,
    is_change_eligible(r.request_id) AS eligible
FROM flag_change_requests r
WHERE r.status = 'pending';

-- ============================================================================
-- 29. ROLLOUT AGGREGATION
-- ============================================================================

SELECT
    f.flag_key,
    e.environment,
    COUNT(*) AS total_evaluations,
    COUNT(*) FILTER (WHERE e.enabled) AS enabled_count,
    COUNT(*) FILTER (WHERE NOT e.enabled) AS disabled_count,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE e.enabled)
        / NULLIF(COUNT(*), 0),
        2
    ) AS observed_enabled_percentage
FROM flag_evaluations e
JOIN feature_flags f
  ON f.flag_id = e.flag_id
GROUP BY
    f.flag_key,
    e.environment
ORDER BY
    f.flag_key,
    e.environment;

-- ============================================================================
-- 30. FEATURE FLAG INVENTORY
-- ============================================================================

SELECT *
FROM feature_flag_inventory
ORDER BY flag_key;

-- ============================================================================
-- 31. ENVIRONMENT REPORT
-- ============================================================================

SELECT *
FROM flag_environment_inventory
ORDER BY flag_key, environment;

-- ============================================================================
-- 32. AUDIT REPORT
-- ============================================================================

SELECT
    a.audit_id,
    f.flag_key,
    u.external_user_id AS actor,
    a.action,
    a.created_at,
    a.details
FROM flag_audit_log a
LEFT JOIN feature_flags f
  ON f.flag_id = a.flag_id
LEFT JOIN users u
  ON u.user_id = a.actor_id
ORDER BY a.created_at DESC;

-- ============================================================================
-- 33. CHANGE REQUEST REPORT
-- ============================================================================

SELECT
    r.request_id,
    f.flag_key,
    r.change_description,
    r.status,
    COUNT(a.approval_id) FILTER (
        WHERE a.decision = 'approved'
    ) AS approvals,
    COUNT(a.approval_id) FILTER (
        WHERE a.decision = 'rejected'
    ) AS rejections
FROM flag_change_requests r
JOIN feature_flags f
  ON f.flag_id = r.flag_id
LEFT JOIN flag_change_approvals a
  ON a.request_id = r.request_id
GROUP BY
    r.request_id,
    f.flag_key
ORDER BY r.request_id;

-- ============================================================================
-- 34. CTE: FEATURE FLAG RELEASE READINESS
-- ============================================================================

WITH approval_summary AS (
    SELECT
        r.request_id,
        COUNT(*) FILTER (
            WHERE a.decision = 'approved'
        ) AS approvals,
        COUNT(*) FILTER (
            WHERE a.decision = 'rejected'
        ) AS rejections
    FROM flag_change_requests r
    LEFT JOIN flag_change_approvals a
      ON a.request_id = r.request_id
    GROUP BY r.request_id
),
readiness AS (
    SELECT
        r.request_id,
        f.flag_key,
        r.status,
        r.expected_version,
        f.version AS current_version,
        COALESCE(s.approvals, 0) AS approvals,
        COALESCE(s.rejections, 0) AS rejections,
        CASE
            WHEN r.status <> 'pending'
                THEN 'NOT_PENDING'
            WHEN r.expected_version <> f.version
                THEN 'VERSION_CONFLICT'
            WHEN COALESCE(s.rejections, 0) > 0
                THEN 'REJECTED'
            WHEN is_change_eligible(r.request_id)
                THEN 'READY'
            ELSE 'AWAITING_APPROVAL'
        END AS readiness_status
    FROM flag_change_requests r
    JOIN feature_flags f
      ON f.flag_id = r.flag_id
    LEFT JOIN approval_summary s
      ON s.request_id = r.request_id
)
SELECT *
FROM readiness
ORDER BY request_id;

-- ============================================================================
-- 35. EXPIRED FLAG INVENTORY
-- ============================================================================

SELECT
    flag_key,
    status,
    owner_team_id,
    expires_at,
    NOW() - expires_at AS overdue_duration
FROM feature_flags
WHERE expires_at IS NOT NULL
  AND expires_at <= NOW()
ORDER BY expires_at;

-- ============================================================================
-- 36. DATA INTEGRITY CHECKS
-- ============================================================================

-- Detect evaluations recorded against outdated configuration versions.
SELECT
    f.flag_key,
    e.evaluation_id,
    e.evaluated_version,
    f.version AS current_version
FROM flag_evaluations e
JOIN feature_flags f
  ON f.flag_id = e.flag_id
WHERE e.evaluated_version < f.version
ORDER BY e.evaluated_at DESC;

-- Detect feature flags with no configured approval policy.
SELECT
    f.flag_key
FROM feature_flags f
LEFT JOIN flag_approval_policies p
  ON p.flag_id = f.flag_id
WHERE p.flag_id IS NULL;

-- Detect production-enabled flags with zero rollout.
SELECT
    f.flag_key,
    f.rollout_percentage
FROM feature_flags f
JOIN flag_environments e
  ON e.flag_id = f.flag_id
WHERE e.environment = 'production'
  AND e.is_enabled = TRUE
  AND f.flag_type = 'percentage'
  AND f.rollout_percentage = 0;

-- ============================================================================
-- 37. OPERATIONAL CLEANUP PREVIEW
-- ============================================================================
-- Retention policies should be enforced by a scheduled operational process.
-- This query identifies evaluation history older than 180 days.

SELECT
    COUNT(*) AS records_eligible_for_retention
FROM flag_evaluations
WHERE evaluated_at < NOW() - INTERVAL '180 days';
