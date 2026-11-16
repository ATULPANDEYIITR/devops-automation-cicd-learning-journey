/*
===============================================================================
RELEASE MANAGEMENT AND GOVERNANCE DATABASE
PostgreSQL 15+

Domain:
    Product
      -> Release
      -> Release Artifacts
      -> Version History
      -> Release Approvals
      -> Quality Checks
      -> Deployment Records
      -> Rollback Events
      -> Governance Policies
      -> Audit Events

Features:
    Semantic version validation
    Release lifecycle enforcement
    Approval authorization
    Quality gate evaluation
    Production deployment eligibility
    Version uniqueness
    Transactional deployment
    Rollback management
    Reporting and audit history

Execution:
    psql -d release_management -f release_management.sql

This script recreates its dedicated schema.
===============================================================================
*/

BEGIN;

DROP SCHEMA IF EXISTS release_governance CASCADE;

CREATE SCHEMA release_governance;

SET search_path TO release_governance, public;

-- ============================================================================
-- 1. ENUMERATED DOMAIN TYPES
-- ============================================================================

CREATE TYPE release_state AS ENUM (
    'draft',
    'candidate',
    'approved',
    'released',
    'rejected',
    'rolled_back'
);

CREATE TYPE approval_decision AS ENUM (
    'approved',
    'rejected',
    'pending'
);

CREATE TYPE check_status AS ENUM (
    'passed',
    'failed',
    'pending'
);

CREATE TYPE deployment_environment AS ENUM (
    'development',
    'staging',
    'production'
);

CREATE TYPE deployment_status AS ENUM (
    'initiated',
    'succeeded',
    'failed',
    'rolled_back'
);

-- ============================================================================
-- 2. USERS AND AUTHORIZATION
-- ============================================================================

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    role_name VARCHAR(60) NOT NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, role_name)
);

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL UNIQUE,
    description TEXT,
    owner_id BIGINT REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================================
-- 3. VERSION MANAGEMENT
-- ============================================================================

CREATE TABLE product_versions (
    version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    major_version INTEGER NOT NULL CHECK (major_version >= 0),
    minor_version INTEGER NOT NULL CHECK (minor_version >= 0),
    patch_version INTEGER NOT NULL CHECK (patch_version >= 0),
    prerelease VARCHAR(100),

    version_label TEXT GENERATED ALWAYS AS (
        major_version::TEXT || '.' ||
        minor_version::TEXT || '.' ||
        patch_version::TEXT ||
        CASE
            WHEN prerelease IS NOT NULL
            THEN '-' || prerelease
            ELSE ''
        END
    ) STORED,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (
        product_id,
        major_version,
        minor_version,
        patch_version,
        prerelease
    ),

    CHECK (
        prerelease IS NULL OR
        prerelease ~ '^[0-9A-Za-z.-]+$'
    )
);

CREATE INDEX idx_product_versions_product
ON product_versions(product_id, major_version, minor_version, patch_version);

-- ============================================================================
-- 4. RELEASE GOVERNANCE POLICIES
-- ============================================================================

CREATE TABLE governance_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    policy_name VARCHAR(150) NOT NULL,
    required_approvals INTEGER NOT NULL DEFAULT 2
        CHECK (required_approvals >= 1),
    require_release_notes BOOLEAN NOT NULL DEFAULT TRUE,
    require_artifact_digest BOOLEAN NOT NULL DEFAULT TRUE,
    allow_prerelease_production BOOLEAN NOT NULL DEFAULT FALSE,
    allow_emergency_override BOOLEAN NOT NULL DEFAULT FALSE,
    prohibit_version_regression BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, policy_name)
);

CREATE TABLE policy_required_checks (
    policy_id BIGINT NOT NULL
        REFERENCES governance_policies(policy_id) ON DELETE CASCADE,
    check_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (policy_id, check_name)
);

CREATE TABLE policy_eligible_roles (
    policy_id BIGINT NOT NULL
        REFERENCES governance_policies(policy_id) ON DELETE CASCADE,
    role_name VARCHAR(60) NOT NULL,
    PRIMARY KEY (policy_id, role_name)
);

-- ============================================================================
-- 5. RELEASE RECORDS
-- ============================================================================

CREATE TABLE releases (
    release_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    release_key VARCHAR(64) NOT NULL UNIQUE,

    product_id BIGINT NOT NULL REFERENCES products(product_id),

    version_id BIGINT NOT NULL REFERENCES product_versions(version_id),

    policy_id BIGINT NOT NULL REFERENCES governance_policies(policy_id),

    source_commit VARCHAR(64) NOT NULL,

    artifact_digest VARCHAR(64) NOT NULL,

    release_notes TEXT NOT NULL DEFAULT '',

    target_environment deployment_environment NOT NULL DEFAULT 'staging',

    state release_state NOT NULL DEFAULT 'draft',

    emergency_override BOOLEAN NOT NULL DEFAULT FALSE,

    created_by BIGINT NOT NULL REFERENCES users(user_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    submitted_at TIMESTAMPTZ,

    approved_at TIMESTAMPTZ,

    released_at TIMESTAMPTZ,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(product_id, version_id),

    CHECK (source_commit ~ '^[a-fA-F0-9]{7,64}$'),

    CHECK (
        artifact_digest = '' OR
        artifact_digest ~ '^[a-fA-F0-9]{64}$'
    ),

    CHECK (
        emergency_override = FALSE OR
        target_environment = 'production'
    )
);

CREATE INDEX idx_releases_product_state
ON releases(product_id, state);

CREATE INDEX idx_releases_created_at
ON releases(created_at DESC);

CREATE INDEX idx_releases_environment_state
ON releases(target_environment, state);

-- ============================================================================
-- 6. APPROVALS
-- ============================================================================

CREATE TABLE release_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    release_id BIGINT NOT NULL
        REFERENCES releases(release_id) ON DELETE CASCADE,

    reviewer_id BIGINT NOT NULL REFERENCES users(user_id),

    decision approval_decision NOT NULL DEFAULT 'pending',

    comment TEXT NOT NULL DEFAULT '',

    decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(release_id, reviewer_id)
);

CREATE INDEX idx_release_approvals_release_decision
ON release_approvals(release_id, decision);

-- ============================================================================
-- 7. AUTOMATED QUALITY CHECKS
-- ============================================================================

CREATE TABLE release_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    release_id BIGINT NOT NULL
        REFERENCES releases(release_id) ON DELETE CASCADE,

    check_name VARCHAR(100) NOT NULL,

    status check_status NOT NULL DEFAULT 'pending',

    details TEXT NOT NULL DEFAULT '',

    executed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(release_id, check_name)
);

CREATE INDEX idx_release_checks_status
ON release_checks(release_id, status);

-- ============================================================================
-- 8. DEPLOYMENT RECORDS
-- ============================================================================

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    release_id BIGINT NOT NULL REFERENCES releases(release_id),

    environment deployment_environment NOT NULL,

    status deployment_status NOT NULL DEFAULT 'initiated',

    deployed_by BIGINT NOT NULL REFERENCES users(user_id),

    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ,

    deployment_details TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_deployments_release_environment
ON deployments(release_id, environment, started_at DESC);

CREATE TABLE production_versions (
    product_id BIGINT PRIMARY KEY REFERENCES products(product_id),

    version_id BIGINT NOT NULL REFERENCES product_versions(version_id),

    deployment_id BIGINT REFERENCES deployments(deployment_id),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 9. ROLLBACK HISTORY
-- ============================================================================

CREATE TABLE rollback_events (
    rollback_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    product_id BIGINT NOT NULL REFERENCES products(product_id),

    failed_release_id BIGINT NOT NULL REFERENCES releases(release_id),

    restored_version_id BIGINT NOT NULL REFERENCES product_versions(version_id),

    initiated_by BIGINT NOT NULL REFERENCES users(user_id),

    reason TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 10. AUDIT EVENTS
-- ============================================================================

CREATE TABLE audit_events (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    release_id BIGINT REFERENCES releases(release_id),

    actor_id BIGINT REFERENCES users(user_id),

    event_type VARCHAR(100) NOT NULL,

    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_events_release_time
ON audit_events(release_id, occurred_at DESC);

CREATE INDEX idx_audit_events_details
ON audit_events USING GIN(event_details);

-- ============================================================================
-- 11. UPDATED TIMESTAMP TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_release_timestamp
BEFORE UPDATE ON releases
FOR EACH ROW
EXECUTE FUNCTION update_timestamp();

-- ============================================================================
-- 12. RELEASE STATE TRANSITION ENFORCEMENT
-- ============================================================================

CREATE OR REPLACE FUNCTION enforce_release_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.state = OLD.state THEN
        RETURN NEW;
    END IF;

    IF OLD.state = 'draft'
       AND NEW.state NOT IN ('candidate', 'rejected') THEN
        RAISE EXCEPTION 'Invalid transition: draft -> %', NEW.state;
    END IF;

    IF OLD.state = 'candidate'
       AND NEW.state NOT IN ('approved', 'rejected') THEN
        RAISE EXCEPTION 'Invalid transition: candidate -> %', NEW.state;
    END IF;

    IF OLD.state = 'approved'
       AND NEW.state NOT IN ('released', 'rejected') THEN
        RAISE EXCEPTION 'Invalid transition: approved -> %', NEW.state;
    END IF;

    IF OLD.state = 'released'
       AND NEW.state <> 'rolled_back' THEN
        RAISE EXCEPTION 'Invalid transition from released.';
    END IF;

    IF OLD.state IN ('rejected', 'rolled_back') THEN
        RAISE EXCEPTION 'Terminal release state cannot be changed.';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_release_transition
BEFORE UPDATE OF state ON releases
FOR EACH ROW
EXECUTE FUNCTION enforce_release_transition();

-- ============================================================================
-- 13. AUDIT TRIGGER
-- ============================================================================

CREATE OR REPLACE FUNCTION audit_release_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    actor BIGINT;
BEGIN
    actor := COALESCE(
        NEW.created_by,
        NULL
    );

    INSERT INTO audit_events (
        release_id,
        actor_id,
        event_type,
        event_details
    )
    VALUES (
        NEW.release_id,
        actor,
        'RELEASE_STATE_CHANGE',
        jsonb_build_object(
            'old_state', OLD.state,
            'new_state', NEW.state,
            'version_id', NEW.version_id
        )
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_release_audit
AFTER UPDATE OF state ON releases
FOR EACH ROW
WHEN (OLD.state IS DISTINCT FROM NEW.state)
EXECUTE FUNCTION audit_release_change();

-- ============================================================================
-- 14. RELEASE ELIGIBILITY FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION evaluate_release(
    p_release_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    approved_count BIGINT,
    required_approvals INTEGER,
    blockers TEXT[]
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    r releases%ROWTYPE;
    p governance_policies%ROWTYPE;
    v_version product_versions%ROWTYPE;
    v_approved BIGINT;
    v_rejected BIGINT;
    v_blockers TEXT[] := ARRAY[]::TEXT[];
    v_missing TEXT;
    v_failed TEXT;
BEGIN
    SELECT *
    INTO r
    FROM releases
    WHERE release_id = p_release_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Unknown release ID: %', p_release_id;
    END IF;

    SELECT *
    INTO p
    FROM governance_policies
    WHERE policy_id = r.policy_id
      AND is_active = TRUE;

    IF NOT FOUND THEN
        v_blockers := array_append(
            v_blockers,
            'No active governance policy.'
        );
    END IF;

    SELECT *
    INTO v_version
    FROM product_versions
    WHERE version_id = r.version_id;

    IF r.state <> 'candidate' THEN
        v_blockers := array_append(
            v_blockers,
            'Release must be in candidate state.'
        );
    END IF;

    IF p.require_release_notes AND btrim(r.release_notes) = '' THEN
        v_blockers := array_append(
            v_blockers,
            'Release notes are missing.'
        );
    END IF;

    IF p.require_artifact_digest
       AND r.artifact_digest !~ '^[a-fA-F0-9]{64}$' THEN
        v_blockers := array_append(
            v_blockers,
            'Artifact SHA-256 digest is invalid.'
        );
    END IF;

    IF r.emergency_override AND NOT p.allow_emergency_override THEN
        v_blockers := array_append(
            v_blockers,
            'Emergency override is prohibited.'
        );
    END IF;

    IF r.target_environment = 'production'
       AND v_version.prerelease IS NOT NULL
       AND NOT p.allow_prerelease_production THEN
        v_blockers := array_append(
            v_blockers,
            'Prerelease production deployment is prohibited.'
        );
    END IF;

    SELECT COUNT(*)
    INTO v_approved
    FROM release_approvals a
    JOIN users u ON u.user_id = a.reviewer_id
    JOIN user_roles ur ON ur.user_id = a.reviewer_id
    JOIN policy_eligible_roles per
      ON per.policy_id = r.policy_id
     AND per.role_name = ur.role_name
    WHERE a.release_id = p_release_id
      AND a.decision = 'approved'
      AND u.is_active = TRUE
    GROUP BY a.reviewer_id;

    -- Count distinct eligible reviewers rather than approval-role rows.
    SELECT COUNT(DISTINCT a.reviewer_id)
    INTO v_approved
    FROM release_approvals a
    JOIN users u ON u.user_id = a.reviewer_id
    WHERE a.release_id = p_release_id
      AND a.decision = 'approved'
      AND u.is_active = TRUE
      AND EXISTS (
          SELECT 1
          FROM user_roles ur
          JOIN policy_eligible_roles per
            ON per.role_name = ur.role_name
           AND per.policy_id = r.policy_id
          WHERE ur.user_id = a.reviewer_id
      );

    SELECT COUNT(*)
    INTO v_rejected
    FROM release_approvals
    WHERE release_id = p_release_id
      AND decision = 'rejected';

    IF v_rejected > 0 THEN
        v_blockers := array_append(
            v_blockers,
            'One or more reviewers rejected the release.'
        );
    END IF;

    IF v_approved < p.required_approvals THEN
        v_blockers := array_append(
            v_blockers,
            format(
                'Insufficient approvals: %s/%s',
                v_approved,
                p.required_approvals
            )
        );
    END IF;

    -- Every policy-required check must exist and have passed.
    SELECT string_agg(prc.check_name, ', ')
    INTO v_missing
    FROM policy_required_checks prc
    WHERE prc.policy_id = r.policy_id
      AND NOT EXISTS (
          SELECT 1
          FROM release_checks rc
          WHERE rc.release_id = p_release_id
            AND rc.check_name = prc.check_name
            AND rc.status = 'passed'
      );

    IF v_missing IS NOT NULL THEN
        v_blockers := array_append(
            v_blockers,
            'Missing or unsuccessful checks: ' || v_missing
        );
    END IF;

    IF p.prohibit_version_regression
       AND r.target_environment = 'production'
       AND EXISTS (
           SELECT 1
           FROM production_versions pv
           JOIN product_versions current_version
             ON current_version.version_id = pv.version_id
           WHERE pv.product_id = r.product_id
             AND (
                 v_version.major_version,
                 v_version.minor_version,
                 v_version.patch_version
             ) <= (
                 current_version.major_version,
                 current_version.minor_version,
                 current_version.patch_version
             )
       ) THEN
        v_blockers := array_append(
            v_blockers,
            'Production version regression detected.'
        );
    END IF;

    RETURN QUERY
    SELECT
        cardinality(v_blockers) = 0,
        COALESCE(v_approved, 0),
        COALESCE(p.required_approvals, 1),
        v_blockers;
END;
$$;

-- ============================================================================
-- 15. SUBMIT RELEASE FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION submit_release(
    p_release_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE releases
    SET state = 'candidate',
        submitted_at = CURRENT_TIMESTAMP
    WHERE release_id = p_release_id
      AND state = 'draft';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Release cannot be submitted.';
    END IF;

    INSERT INTO audit_events (
        release_id,
        event_type,
        event_details
    )
    VALUES (
        p_release_id,
        'CANDIDATE_SUBMITTED',
        jsonb_build_object('state', 'candidate')
    );
END;
$$;

-- ============================================================================
-- 16. APPROVAL FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION record_release_approval(
    p_release_id BIGINT,
    p_reviewer_id BIGINT,
    p_decision approval_decision,
    p_comment TEXT DEFAULT ''
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_release releases%ROWTYPE;
    v_policy_id BIGINT;
BEGIN
    SELECT *
    INTO v_release
    FROM releases
    WHERE release_id = p_release_id
    FOR UPDATE;

    IF NOT FOUND OR v_release.state <> 'candidate' THEN
        RAISE EXCEPTION 'Release is not awaiting approvals.';
    END IF;

    SELECT policy_id
    INTO v_policy_id
    FROM releases
    WHERE release_id = p_release_id;

    IF NOT EXISTS (
        SELECT 1
        FROM users u
        JOIN user_roles ur ON ur.user_id = u.user_id
        JOIN policy_eligible_roles per
          ON per.policy_id = v_policy_id
         AND per.role_name = ur.role_name
        WHERE u.user_id = p_reviewer_id
          AND u.is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'Reviewer is not eligible under this policy.';
    END IF;

    INSERT INTO release_approvals (
        release_id,
        reviewer_id,
        decision,
        comment
    )
    VALUES (
        p_release_id,
        p_reviewer_id,
        p_decision,
        p_comment
    );

    INSERT INTO audit_events (
        release_id,
        actor_id,
        event_type,
        event_details
    )
    VALUES (
        p_release_id,
        p_reviewer_id,
        'APPROVAL_RECORDED',
        jsonb_build_object(
            'decision', p_decision,
            'comment', p_comment
        )
    );
END;
$$;

-- ============================================================================
-- 17. APPROVE RELEASE FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION approve_release(
    p_release_id BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_eligible BOOLEAN;
    v_blockers TEXT[];
BEGIN
    SELECT eligible, blockers
    INTO v_eligible, v_blockers
    FROM evaluate_release(p_release_id);

    IF NOT v_eligible THEN
        RAISE EXCEPTION 'Release blocked: %',
            array_to_string(v_blockers, '; ');
    END IF;

    UPDATE releases
    SET state = 'approved',
        approved_at = CURRENT_TIMESTAMP
    WHERE release_id = p_release_id
      AND state = 'candidate';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invalid approval transition.';
    END IF;
END;
$$;

-- ============================================================================
-- 18. DEPLOYMENT PROCEDURE
-- ============================================================================

CREATE OR REPLACE PROCEDURE deploy_release(
    p_release_id BIGINT,
    p_deployer_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    r releases%ROWTYPE;
    v_current product_versions%ROWTYPE;
    v_target product_versions%ROWTYPE;
    v_deployment_id BIGINT;
BEGIN
    SELECT *
    INTO r
    FROM releases
    WHERE release_id = p_release_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Release does not exist.';
    END IF;

    IF r.state <> 'approved' THEN
        RAISE EXCEPTION 'Release must be approved before deployment.';
    END IF;

    IF r.target_environment <> 'production' THEN
        RAISE EXCEPTION 'Production deployment requires production target.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM users
        WHERE user_id = p_deployer_id
          AND is_active = TRUE
    ) THEN
        RAISE EXCEPTION 'Deployer is inactive or unknown.';
    END IF;

    -- Serialize deployments for a product.
    PERFORM 1
    FROM products
    WHERE product_id = r.product_id
    FOR UPDATE;

    SELECT *
    INTO v_target
    FROM product_versions
    WHERE version_id = r.version_id;

    SELECT pv.*
    INTO v_current
    FROM production_versions current_release
    JOIN product_versions pv
      ON pv.version_id = current_release.version_id
    WHERE current_release.product_id = r.product_id;

    IF FOUND AND (
        v_target.major_version,
        v_target.minor_version,
        v_target.patch_version
    ) <= (
        v_current.major_version,
        v_current.minor_version,
        v_current.patch_version
    ) THEN
        RAISE EXCEPTION 'Production version must advance.';
    END IF;

    INSERT INTO deployments (
        release_id,
        environment,
        status,
        deployed_by
    )
    VALUES (
        p_release_id,
        'production',
        'initiated',
        p_deployer_id
    )
    RETURNING deployment_id INTO v_deployment_id;

    UPDATE deployments
    SET status = 'succeeded',
        completed_at = CURRENT_TIMESTAMP,
        deployment_details = 'Governance-approved deployment completed.'
    WHERE deployment_id = v_deployment_id;

    INSERT INTO production_versions (
        product_id,
        version_id,
        deployment_id
    )
    VALUES (
        r.product_id,
        r.version_id,
        v_deployment_id
    )
    ON CONFLICT (product_id)
    DO UPDATE SET
        version_id = EXCLUDED.version_id,
        deployment_id = EXCLUDED.deployment_id,
        updated_at = CURRENT_TIMESTAMP;

    UPDATE releases
    SET state = 'released',
        released_at = CURRENT_TIMESTAMP
    WHERE release_id = p_release_id;
END;
$$;

-- ============================================================================
-- 19. ROLLBACK FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION rollback_release(
    p_release_id BIGINT,
    p_restored_version_id BIGINT,
    p_actor_id BIGINT,
    p_reason TEXT
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    r releases%ROWTYPE;
    v_target product_versions%ROWTYPE;
    v_deployment_id BIGINT;
BEGIN
    SELECT *
    INTO r
    FROM releases
    WHERE release_id = p_release_id
    FOR UPDATE;

    IF NOT FOUND OR r.state <> 'released' THEN
        RAISE EXCEPTION 'Only released versions can be rolled back.';
    END IF;

    IF btrim(p_reason) = '' THEN
        RAISE EXCEPTION 'Rollback reason is required.';
    END IF;

    SELECT *
    INTO v_target
    FROM product_versions
    WHERE version_id = p_restored_version_id
      AND product_id = r.product_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Rollback target belongs to another product or does not exist.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM deployments d
        JOIN releases old_release
          ON old_release.release_id = d.release_id
        WHERE old_release.product_id = r.product_id
          AND old_release.version_id = p_restored_version_id
          AND d.status = 'succeeded'
    ) THEN
        RAISE EXCEPTION 'Rollback target was not successfully deployed.';
    END IF;

    INSERT INTO rollback_events (
        product_id,
        failed_release_id,
        restored_version_id,
        initiated_by,
        reason
    )
    VALUES (
        r.product_id,
        p_release_id,
        p_restored_version_id,
        p_actor_id,
        p_reason
    );

    INSERT INTO deployments (
        release_id,
        environment,
        status,
        deployed_by,
        completed_at,
        deployment_details
    )
    VALUES (
        p_release_id,
        'production',
        'rolled_back',
        p_actor_id,
        CURRENT_TIMESTAMP,
        p_reason
    )
    RETURNING deployment_id INTO v_deployment_id;

    UPDATE production_versions
    SET version_id = p_restored_version_id,
        deployment_id = v_deployment_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE product_id = r.product_id;

    UPDATE releases
    SET state = 'rolled_back'
    WHERE release_id = p_release_id;
END;
$$;

-- ============================================================================
-- 20. RELEASE REPORTING VIEW
-- ============================================================================

CREATE OR REPLACE VIEW release_governance_report AS
SELECT
    r.release_id,
    r.release_key,
    p.product_name,
    pv.version_label,
    r.target_environment,
    r.state,

    COUNT(DISTINCT a.reviewer_id)
        FILTER (WHERE a.decision = 'approved')
        AS approval_count,

    COUNT(DISTINCT a.reviewer_id)
        FILTER (WHERE a.decision = 'rejected')
        AS rejection_count,

    COUNT(DISTINCT rc.check_id)
        FILTER (WHERE rc.status = 'passed')
        AS passed_checks,

    COUNT(DISTINCT rc.check_id)
        FILTER (WHERE rc.status = 'failed')
        AS failed_checks,

    gp.required_approvals,

    r.created_at,
    r.approved_at,
    r.released_at

FROM releases r

JOIN products p
    ON p.product_id = r.product_id

JOIN product_versions pv
    ON pv.version_id = r.version_id

JOIN governance_policies gp
    ON gp.policy_id = r.policy_id

LEFT JOIN release_approvals a
    ON a.release_id = r.release_id

LEFT JOIN release_checks rc
    ON rc.release_id = r.release_id

GROUP BY
    r.release_id,
    p.product_name,
    pv.version_label,
    gp.required_approvals;

-- ============================================================================
-- 21. SAMPLE USERS
-- ============================================================================

INSERT INTO users(username, email)
VALUES
('release_admin', 'release.admin@example.org'),
('security_reviewer', 'security@example.org'),
('engineering_reviewer', 'engineering@example.org'),
('qa_reviewer', 'qa@example.org'),
('product_owner', 'owner@example.org'),
('deployment_service', 'deployment@example.org');

INSERT INTO user_roles(user_id, role_name)
SELECT user_id, role_name
FROM (
    VALUES
        ('release_admin', 'release_manager'),
        ('security_reviewer', 'security_lead'),
        ('engineering_reviewer', 'engineering_lead'),
        ('qa_reviewer', 'qa_lead'),
        ('product_owner', 'product_owner'),
        ('deployment_service', 'deployment_operator')
) AS role_data(username, role_name)
JOIN users USING (username);

-- ============================================================================
-- 22. SAMPLE PRODUCTS
-- ============================================================================

INSERT INTO products(product_name, description, owner_id)
SELECT
    'EnterpriseBanking',
    'Enterprise transaction and account management platform.',
    user_id
FROM users
WHERE username = 'product_owner';

-- ============================================================================
-- 23. SAMPLE GOVERNANCE POLICY
-- ============================================================================

INSERT INTO governance_policies (
    product_id,
    policy_name,
    required_approvals,
    require_release_notes,
    require_artifact_digest,
    allow_prerelease_production
)
SELECT
    product_id,
    'Production Standard',
    2,
    TRUE,
    TRUE,
    FALSE
FROM products
WHERE product_name = 'EnterpriseBanking';

INSERT INTO policy_required_checks(policy_id, check_name)
SELECT policy_id, check_name
FROM governance_policies
CROSS JOIN (
    VALUES
        ('unit_tests'),
        ('integration_tests'),
        ('security_scan'),
        ('dependency_audit')
) AS checks(check_name);

INSERT INTO policy_eligible_roles(policy_id, role_name)
SELECT policy_id, role_name
FROM governance_policies
CROSS JOIN (
    VALUES
        ('security_lead'),
        ('engineering_lead'),
        ('qa_lead'),
        ('product_owner')
) AS roles(role_name);

-- ============================================================================
-- 24. SAMPLE RELEASE VERSIONS
-- ============================================================================

INSERT INTO product_versions (
    product_id,
    major_version,
    minor_version,
    patch_version
)
SELECT product_id, 5, 2, 0
FROM products
WHERE product_name = 'EnterpriseBanking';

INSERT INTO product_versions (
    product_id,
    major_version,
    minor_version,
    patch_version
)
SELECT product_id, 5, 3, 0
FROM products
WHERE product_name = 'EnterpriseBanking';

INSERT INTO product_versions (
    product_id,
    major_version,
    minor_version,
    patch_version,
    prerelease
)
SELECT product_id, 5, 4, 0, 'rc.1'
FROM products
WHERE product_name = 'EnterpriseBanking';

-- ============================================================================
-- 25. SAMPLE RELEASE RECORDS
-- ============================================================================

INSERT INTO releases (
    release_key,
    product_id,
    version_id,
    policy_id,
    source_commit,
    artifact_digest,
    release_notes,
    target_environment,
    state,
    created_by
)
SELECT
    'REL-2026-001',
    p.product_id,
    pv.version_id,
    gp.policy_id,
    repeat('a', 40),
    repeat('b', 64),
    'Production release containing security and transaction improvements.',
    'production',
    'draft',
    u.user_id
FROM products p
JOIN product_versions pv
    ON pv.product_id = p.product_id
   AND pv.major_version = 5
   AND pv.minor_version = 2
   AND pv.patch_version = 0
JOIN governance_policies gp
    ON gp.product_id = p.product_id
JOIN users u
    ON u.username = 'release_admin'
WHERE p.product_name = 'EnterpriseBanking';

INSERT INTO releases (
    release_key,
    product_id,
    version_id,
    policy_id,
    source_commit,
    artifact_digest,
    release_notes,
    target_environment,
    state,
    created_by
)
SELECT
    'REL-2026-002',
    p.product_id,
    pv.version_id,
    gp.policy_id,
    repeat('c', 40),
    repeat('d', 64),
    'Next release candidate with account-management improvements.',
    'production',
    'draft',
    u.user_id
FROM products p
JOIN product_versions pv
    ON pv.product_id = p.product_id
   AND pv.major_version = 5
   AND pv.minor_version = 3
   AND pv.patch_version = 0
JOIN governance_policies gp
    ON gp.product_id = p.product_id
JOIN users u
    ON u.username = 'release_admin'
WHERE p.product_name = 'EnterpriseBanking';

INSERT INTO releases (
    release_key,
    product_id,
    version_id,
    policy_id,
    source_commit,
    artifact_digest,
    release_notes,
    target_environment,
    state,
    created_by
)
SELECT
    'REL-2026-003',
    p.product_id,
    pv.version_id,
    gp.policy_id,
    repeat('e', 40),
    repeat('f', 64),
    'Prerelease candidate for integration validation.',
    'production',
    'draft',
    u.user_id
FROM products p
JOIN product_versions pv
    ON pv.product_id = p.product_id
   AND pv.prerelease = 'rc.1'
JOIN governance_policies gp
    ON gp.product_id = p.product_id
JOIN users u
    ON u.username = 'release_admin'
WHERE p.product_name = 'EnterpriseBanking';

-- ============================================================================
-- 26. SUBMIT CANDIDATES
-- ============================================================================

SELECT submit_release(
    (SELECT release_id FROM releases
     WHERE release_key = 'REL-2026-001')
);

SELECT submit_release(
    (SELECT release_id FROM releases
     WHERE release_key = 'REL-2026-002')
);

SELECT submit_release(
    (SELECT release_id FROM releases
     WHERE release_key = 'REL-2026-003')
);

-- ============================================================================
-- 27. SAMPLE APPROVAL DECISIONS
-- ============================================================================

SELECT record_release_approval(
    r.release_id,
    u.user_id,
    'approved',
    'Security review completed successfully.'
)
FROM releases r
CROSS JOIN users u
WHERE r.release_key = 'REL-2026-001'
  AND u.username = 'security_reviewer';

SELECT record_release_approval(
    r.release_id,
    u.user_id,
    'approved',
    'Engineering release validation completed.'
)
FROM releases r
CROSS JOIN users u
WHERE r.release_key = 'REL-2026-001'
  AND u.username = 'engineering_reviewer';

SELECT record_release_approval(
    r.release_id,
    u.user_id,
    'approved',
    'Security review completed.'
)
FROM releases r
CROSS JOIN users u
WHERE r.release_key = 'REL-2026-002'
  AND u.username = 'security_reviewer';

SELECT record_release_approval(
    r.release_id,
    u.user_id,
    'rejected',
    'Integration defects require remediation.'
)
FROM releases r
CROSS JOIN users u
WHERE r.release_key = 'REL-2026-002'
  AND u.username = 'qa_reviewer';

-- ============================================================================
-- 28. AUTOMATED QUALITY CHECK RESULTS
-- ============================================================================

INSERT INTO release_checks(release_id, check_name, status, details)
SELECT
    r.release_id,
    check_name,
    'passed',
    'Automated validation completed successfully.'
FROM releases r
CROSS JOIN (
    VALUES
        ('unit_tests'),
        ('integration_tests'),
        ('security_scan'),
        ('dependency_audit')
) AS checks(check_name)
WHERE r.release_key = 'REL-2026-001';

INSERT INTO release_checks(release_id, check_name, status, details)
SELECT
    r.release_id,
    check_name,
    CASE
        WHEN check_name = 'security_scan'
        THEN 'failed'::check_status
        ELSE 'passed'::check_status
    END,
    CASE
        WHEN check_name = 'security_scan'
        THEN 'Critical vulnerability detected.'
        ELSE 'Automated validation completed.'
    END
FROM releases r
CROSS JOIN (
    VALUES
        ('unit_tests'),
        ('integration_tests'),
        ('security_scan'),
        ('dependency_audit')
) AS checks(check_name)
WHERE r.release_key = 'REL-2026-002';

-- ============================================================================
-- 29. ELIGIBILITY EVALUATION
-- ============================================================================

SELECT
    r.release_key,
    e.eligible,
    e.approved_count,
    e.required_approvals,
    e.blockers
FROM releases r
CROSS JOIN LATERAL evaluate_release(r.release_id) e
ORDER BY r.release_key;

-- ============================================================================
-- 30. SUCCESSFUL APPROVAL AND DEPLOYMENT
-- ============================================================================

SELECT approve_release(
    (SELECT release_id
     FROM releases
     WHERE release_key = 'REL-2026-001')
);

CALL deploy_release(
    (SELECT release_id
     FROM releases
     WHERE release_key = 'REL-2026-001'),
    (SELECT user_id
     FROM users
     WHERE username = 'deployment_service')
);

-- ============================================================================
-- 31. REPORTING QUERIES
-- ============================================================================

-- Current release status and governance counts.
SELECT *
FROM release_governance_report
ORDER BY created_at DESC;

-- Releases that cannot satisfy all policy conditions.
SELECT
    r.release_key,
    e.blockers
FROM releases r
CROSS JOIN LATERAL evaluate_release(r.release_id) e
WHERE NOT e.eligible;

-- Product deployment history.
SELECT
    p.product_name,
    pv.version_label,
    d.environment,
    d.status,
    d.started_at,
    d.completed_at
FROM deployments d
JOIN releases r ON r.release_id = d.release_id
JOIN products p ON p.product_id = r.product_id
JOIN product_versions pv ON pv.version_id = r.version_id
ORDER BY d.started_at DESC;

-- Approval distribution by reviewer.
SELECT
    u.username,
    a.decision,
    COUNT(*) AS decisions
FROM release_approvals a
JOIN users u ON u.user_id = a.reviewer_id
GROUP BY u.username, a.decision
ORDER BY u.username, a.decision;

-- Quality check failure statistics.
SELECT
    check_name,
    COUNT(*) AS total_executions,
    COUNT(*) FILTER (WHERE status = 'passed') AS passed,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed
FROM release_checks
GROUP BY check_name
ORDER BY check_name;

-- Current production version.
SELECT
    p.product_name,
    pv.version_label,
    pv.created_at,
    production.updated_at
FROM production_versions production
JOIN products p ON p.product_id = production.product_id
JOIN product_versions pv ON pv.version_id = production.version_id;

-- ============================================================================
-- 32. CTE-BASED RELEASE READINESS REPORT
-- ============================================================================

WITH approval_summary AS (
    SELECT
        release_id,
        COUNT(*) FILTER (
            WHERE decision = 'approved'
        ) AS approved_count,
        COUNT(*) FILTER (
            WHERE decision = 'rejected'
        ) AS rejected_count
    FROM release_approvals
    GROUP BY release_id
),
check_summary AS (
    SELECT
        release_id,
        COUNT(*) FILTER (
            WHERE status = 'passed'
        ) AS passed_count,
        COUNT(*) FILTER (
            WHERE status <> 'passed'
        ) AS unsuccessful_count
    FROM release_checks
    GROUP BY release_id
)
SELECT
    r.release_key,
    pv.version_label,
    r.state,
    COALESCE(a.approved_count, 0) AS approved_count,
    COALESCE(a.rejected_count, 0) AS rejected_count,
    COALESCE(c.passed_count, 0) AS passed_checks,
    COALESCE(c.unsuccessful_count, 0) AS unsuccessful_checks
FROM releases r
JOIN product_versions pv ON pv.version_id = r.version_id
LEFT JOIN approval_summary a ON a.release_id = r.release_id
LEFT JOIN check_summary c ON c.release_id = r.release_id
ORDER BY r.created_at DESC;

-- ============================================================================
-- 33. AUDIT REPORT
-- ============================================================================

SELECT
    ae.audit_id,
    r.release_key,
    u.username AS actor,
    ae.event_type,
    ae.event_details,
    ae.occurred_at
FROM audit_events ae
LEFT JOIN releases r ON r.release_id = ae.release_id
LEFT JOIN users u ON u.user_id = ae.actor_id
ORDER BY ae.occurred_at DESC;

COMMIT;

-- ============================================================================
-- 34. EXAMPLE FAILURE HANDLING
-- ============================================================================
--
-- These statements are intentionally commented out because they should fail:
--
-- Duplicate approval:
-- SELECT record_release_approval(
--     (SELECT release_id FROM releases
--      WHERE release_key = 'REL-2026-001'),
--     (SELECT user_id FROM users
--      WHERE username = 'security_reviewer'),
--     'approved',
--     'Duplicate approval'
-- );
--
-- Ineligible deployment:
-- CALL deploy_release(
--     (SELECT release_id FROM releases
--      WHERE release_key = 'REL-2026-002'),
--     (SELECT user_id FROM users
--      WHERE username = 'deployment_service')
-- );
--
-- Prerelease production eligibility:
-- SELECT * FROM evaluate_release(
--     (SELECT release_id FROM releases
--      WHERE release_key = 'REL-2026-003')
-- );
--
-- Invalid state transition:
-- UPDATE releases
-- SET state = 'released'
-- WHERE release_key = 'REL-2026-002';
--
-- ============================================================================
-- END OF RELEASE MANAGEMENT DATABASE
-- ============================================================================
