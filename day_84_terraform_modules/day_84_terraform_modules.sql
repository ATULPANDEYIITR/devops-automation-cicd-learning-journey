-- ================================================================
-- TERRAFORM MODULES: REUSABLE INFRASTRUCTURE MODULES
-- PostgreSQL 15+
--
-- Domain model:
-- Organizations
--   -> Module Registry
--      -> Module Versions
--         -> Module Inputs / Outputs / Resources
--   -> Infrastructure Projects
--      -> Environments
--         -> Module Instances
--            -> Deployments
--               -> Deployment Resources
--               -> Validation Checks
--               -> Approval Decisions
--               -> Deployment Events
--
-- Includes:
-- Constraints, indexes, triggers, functions, procedures,
-- deployment eligibility, version selection and drift reporting.
-- ================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS terraform_platform;

SET search_path TO terraform_platform, public;

-- ------------------------------------------------
-- ENUM TYPES
-- ------------------------------------------------

CREATE TYPE module_release_status AS ENUM (
    'draft',
    'validated',
    'published',
    'deprecated',
    'revoked'
);

CREATE TYPE deployment_status AS ENUM (
    'pending',
    'validating',
    'planned',
    'awaiting_approval',
    'applying',
    'succeeded',
    'failed',
    'cancelled'
);

CREATE TYPE resource_action AS ENUM (
    'create',
    'update',
    'delete',
    'no_change'
);

CREATE TYPE check_status AS ENUM (
    'pending',
    'passed',
    'failed',
    'skipped'
);

CREATE TYPE approval_decision AS ENUM (
    'approved',
    'rejected',
    'changes_requested'
);

-- ------------------------------------------------
-- ORGANIZATIONS AND USERS
-- ------------------------------------------------

CREATE TABLE organizations (
    organization_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    organization_name VARCHAR(150) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE platform_users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, username),
    UNIQUE (organization_id, email)
);

-- ------------------------------------------------
-- REUSABLE MODULE REGISTRY
-- ------------------------------------------------

CREATE TABLE modules (
    module_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    module_name VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    category VARCHAR(80) NOT NULL,
    owner_user_id BIGINT NOT NULL
        REFERENCES platform_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, module_name)
);

CREATE TABLE module_versions (
    module_version_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    module_id BIGINT NOT NULL
        REFERENCES modules(module_id) ON DELETE RESTRICT,
    version_major INTEGER NOT NULL CHECK (version_major >= 0),
    version_minor INTEGER NOT NULL CHECK (version_minor >= 0),
    version_patch INTEGER NOT NULL CHECK (version_patch >= 0),
    source_uri TEXT NOT NULL,
    source_commit VARCHAR(64),
    content_checksum VARCHAR(64) NOT NULL
        CHECK (content_checksum ~ '^[a-fA-F0-9]{64}$'),
    terraform_min_version VARCHAR(30) NOT NULL,
    terraform_max_version VARCHAR(30),
    release_status module_release_status NOT NULL DEFAULT 'draft',
    breaking_change BOOLEAN NOT NULL DEFAULT FALSE,
    published_by BIGINT REFERENCES platform_users(user_id),
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (
        module_id,
        version_major,
        version_minor,
        version_patch
    ),

    CHECK (
        source_commit IS NULL OR
        source_commit ~ '^[a-fA-F0-9]{40,64}$'
    ),

    CHECK (
        terraform_max_version IS NULL OR
        terraform_max_version <> ''
    ),

    CHECK (
        release_status <> 'published' OR
        published_at IS NOT NULL
    )
);

CREATE INDEX idx_module_versions_release
    ON module_versions (
        module_id,
        version_major DESC,
        version_minor DESC,
        version_patch DESC
    )
    WHERE release_status = 'published';

CREATE INDEX idx_module_versions_status
    ON module_versions(release_status, created_at DESC);

-- ------------------------------------------------
-- MODULE INPUT CONTRACTS
-- ------------------------------------------------

CREATE TABLE module_inputs (
    input_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    module_version_id BIGINT NOT NULL
        REFERENCES module_versions(module_version_id)
        ON DELETE CASCADE,
    input_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(30) NOT NULL
        CHECK (
            data_type IN (
                'string',
                'number',
                'boolean',
                'list',
                'map',
                'object'
            )
        ),
    required BOOLEAN NOT NULL DEFAULT TRUE,
    default_value JSONB,
    validation_rules JSONB NOT NULL DEFAULT '{}'::JSONB,
    sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT NOT NULL,
    UNIQUE (module_version_id, input_name),

    CHECK (
        NOT required OR default_value IS NULL
    )
);

CREATE TABLE module_outputs (
    output_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    module_version_id BIGINT NOT NULL
        REFERENCES module_versions(module_version_id)
        ON DELETE CASCADE,
    output_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(30) NOT NULL,
    sensitive BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT NOT NULL,
    UNIQUE (module_version_id, output_name)
);

-- ------------------------------------------------
-- MODULE RESOURCE DEFINITIONS
-- ------------------------------------------------

CREATE TABLE module_resources (
    resource_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    module_version_id BIGINT NOT NULL
        REFERENCES module_versions(module_version_id)
        ON DELETE CASCADE,
    resource_name VARCHAR(150) NOT NULL,
    resource_type VARCHAR(150) NOT NULL,
    configuration JSONB NOT NULL DEFAULT '{}'::JSONB,
    lifecycle_rules JSONB NOT NULL DEFAULT '{}'::JSONB,
    UNIQUE (module_version_id, resource_name)
);

-- ------------------------------------------------
-- MODULE DEPENDENCIES
-- ------------------------------------------------

CREATE TABLE module_dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    module_version_id BIGINT NOT NULL
        REFERENCES module_versions(module_version_id)
        ON DELETE CASCADE,
    depends_on_version_id BIGINT NOT NULL
        REFERENCES module_versions(module_version_id)
        ON DELETE RESTRICT,
    version_constraint VARCHAR(80) NOT NULL,
    UNIQUE (module_version_id, depends_on_version_id),
    CHECK (module_version_id <> depends_on_version_id)
);

CREATE INDEX idx_module_dependencies_parent
    ON module_dependencies(module_version_id);

-- ------------------------------------------------
-- PROJECTS AND ENVIRONMENTS
-- ------------------------------------------------

CREATE TABLE infrastructure_projects (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    organization_id BIGINT NOT NULL
        REFERENCES organizations(organization_id),
    project_name VARCHAR(150) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, project_name)
);

CREATE TABLE environments (
    environment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    project_id BIGINT NOT NULL
        REFERENCES infrastructure_projects(project_id),
    environment_name VARCHAR(50) NOT NULL
        CHECK (
            environment_name IN (
                'development',
                'staging',
                'production'
            )
        ),
    region VARCHAR(80) NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, environment_name)
);

-- ------------------------------------------------
-- MODULE INSTANCES
-- ------------------------------------------------

CREATE TABLE module_instances (
    instance_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    module_version_id BIGINT NOT NULL
        REFERENCES module_versions(module_version_id),
    instance_name VARCHAR(150) NOT NULL,
    input_values JSONB NOT NULL DEFAULT '{}'::JSONB,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_by BIGINT NOT NULL
        REFERENCES platform_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (environment_id, instance_name),

    CHECK (jsonb_typeof(input_values) = 'object')
);

CREATE INDEX idx_module_instances_environment
    ON module_instances(environment_id, enabled);

-- ------------------------------------------------
-- DEPLOYMENTS
-- ------------------------------------------------

CREATE TABLE deployments (
    deployment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    environment_id BIGINT NOT NULL
        REFERENCES environments(environment_id),
    requested_by BIGINT NOT NULL
        REFERENCES platform_users(user_id),
    deployment_number INTEGER NOT NULL CHECK (deployment_number > 0),
    status deployment_status NOT NULL DEFAULT 'pending',
    plan_checksum VARCHAR(64),
    state_revision BIGINT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (environment_id, deployment_number),

    CHECK (
        completed_at IS NULL OR started_at IS NOT NULL
    )
);

CREATE INDEX idx_deployments_environment
    ON deployments(environment_id, created_at DESC);

CREATE INDEX idx_deployments_status
    ON deployments(status, created_at DESC);

-- ------------------------------------------------
-- DEPLOYMENT RESOURCE CHANGES
-- ------------------------------------------------

CREATE TABLE deployment_resources (
    deployment_resource_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    instance_id BIGINT NOT NULL
        REFERENCES module_instances(instance_id),
    resource_address TEXT NOT NULL,
    action resource_action NOT NULL,
    desired_configuration JSONB NOT NULL,
    previous_configuration JSONB,
    UNIQUE (deployment_id, resource_address)
);

CREATE INDEX idx_deployment_resources_action
    ON deployment_resources(deployment_id, action);

-- ------------------------------------------------
-- VALIDATION AND SECURITY CHECKS
-- ------------------------------------------------

CREATE TABLE deployment_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    check_name VARCHAR(120) NOT NULL,
    status check_status NOT NULL DEFAULT 'pending',
    details JSONB NOT NULL DEFAULT '{}'::JSONB,
    executed_at TIMESTAMPTZ,
    UNIQUE (deployment_id, check_name)
);

CREATE INDEX idx_deployment_checks_status
    ON deployment_checks(deployment_id, status);

-- ------------------------------------------------
-- DEPLOYMENT APPROVALS
-- ------------------------------------------------

CREATE TABLE deployment_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES platform_users(user_id),
    decision approval_decision NOT NULL,
    comment TEXT,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (deployment_id, reviewer_id)
);

CREATE INDEX idx_deployment_approvals_decision
    ON deployment_approvals(deployment_id, decision);

-- ------------------------------------------------
-- ENVIRONMENT GOVERNANCE POLICIES
-- ------------------------------------------------

CREATE TABLE environment_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    environment_id BIGINT NOT NULL UNIQUE
        REFERENCES environments(environment_id),
    required_approvals INTEGER NOT NULL DEFAULT 0
        CHECK (required_approvals >= 0),
    require_passing_checks BOOLEAN NOT NULL DEFAULT TRUE,
    require_pinned_source BOOLEAN NOT NULL DEFAULT TRUE,
    require_resolved_discussions BOOLEAN NOT NULL DEFAULT TRUE,
    allow_destroy BOOLEAN NOT NULL DEFAULT FALSE,
    prohibit_unencrypted_resources BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ------------------------------------------------
-- DEPLOYMENT AUDIT EVENTS
-- ------------------------------------------------

CREATE TABLE deployment_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    deployment_id BIGINT NOT NULL
        REFERENCES deployments(deployment_id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,
    event_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    actor_id BIGINT REFERENCES platform_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_deployment_events_history
    ON deployment_events(deployment_id, created_at DESC);

-- ------------------------------------------------
-- TRIGGER: PREVENT MODIFICATION OF PUBLISHED RELEASES
-- ------------------------------------------------

CREATE FUNCTION prevent_published_release_modification()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.release_status IN ('published', 'revoked') THEN
        IF (
            NEW.module_id,
            NEW.version_major,
            NEW.version_minor,
            NEW.version_patch,
            NEW.source_uri,
            NEW.source_commit,
            NEW.content_checksum,
            NEW.terraform_min_version,
            NEW.terraform_max_version
        ) IS DISTINCT FROM (
            OLD.module_id,
            OLD.version_major,
            OLD.version_minor,
            OLD.version_patch,
            OLD.source_uri,
            OLD.source_commit,
            OLD.content_checksum,
            OLD.terraform_min_version,
            OLD.terraform_max_version
        ) THEN
            RAISE EXCEPTION
                'Published module release contents are immutable';
        END IF;
    END IF;

    IF OLD.release_status = 'revoked'
       AND NEW.release_status <> 'revoked' THEN
        RAISE EXCEPTION
            'A revoked module release cannot be restored';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_immutable_module_release
BEFORE UPDATE ON module_versions
FOR EACH ROW
EXECUTE FUNCTION prevent_published_release_modification();

-- ------------------------------------------------
-- TRIGGER: VALIDATE DEPLOYMENT STATE TRANSITIONS
-- ------------------------------------------------

CREATE FUNCTION validate_deployment_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = NEW.status THEN
        RETURN NEW;
    END IF;

    IF OLD.status IN ('succeeded', 'failed', 'cancelled') THEN
        RAISE EXCEPTION
            'Terminal deployment state cannot be changed';
    END IF;

    IF NOT (
        (OLD.status = 'pending'
            AND NEW.status IN ('validating', 'cancelled', 'failed'))
        OR
        (OLD.status = 'validating'
            AND NEW.status IN ('planned', 'failed', 'cancelled'))
        OR
        (OLD.status = 'planned'
            AND NEW.status IN (
                'awaiting_approval',
                'applying',
                'failed',
                'cancelled'
            ))
        OR
        (OLD.status = 'awaiting_approval'
            AND NEW.status IN ('applying', 'failed', 'cancelled'))
        OR
        (OLD.status = 'applying'
            AND NEW.status IN ('succeeded', 'failed'))
    ) THEN
        RAISE EXCEPTION
            'Invalid deployment transition: % -> %',
            OLD.status,
            NEW.status;
    END IF;

    IF NEW.status IN ('validating', 'applying')
       AND NEW.started_at IS NULL THEN
        NEW.started_at := NOW();
    END IF;

    IF NEW.status IN ('succeeded', 'failed', 'cancelled') THEN
        NEW.completed_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_deployment_transition
BEFORE UPDATE OF status ON deployments
FOR EACH ROW
EXECUTE FUNCTION validate_deployment_transition();

-- ------------------------------------------------
-- FUNCTION: VALIDATE MODULE INPUTS
-- ------------------------------------------------

CREATE FUNCTION validate_module_inputs(
    p_module_version_id BIGINT,
    p_values JSONB
)
RETURNS TABLE (
    input_name VARCHAR,
    valid BOOLEAN,
    validation_message TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    definition RECORD;
    supplied JSONB;
    actual_type TEXT;
    expected_type TEXT;
BEGIN
    IF jsonb_typeof(p_values) <> 'object' THEN
        RAISE EXCEPTION
            'Module inputs must be a JSON object';
    END IF;

    -- Reject unknown input keys.
    IF EXISTS (
        SELECT 1
        FROM jsonb_object_keys(p_values) supplied_key
        WHERE NOT EXISTS (
            SELECT 1
            FROM module_inputs mi
            WHERE mi.module_version_id = p_module_version_id
              AND mi.input_name = supplied_key
        )
    ) THEN
        RAISE EXCEPTION
            'Supplied values contain unknown module inputs';
    END IF;

    FOR definition IN
        SELECT *
        FROM module_inputs mi
        WHERE mi.module_version_id = p_module_version_id
        ORDER BY mi.input_name
    LOOP
        supplied := p_values -> definition.input_name;

        IF supplied IS NULL THEN
            IF definition.required THEN
                input_name := definition.input_name;
                valid := FALSE;
                validation_message := 'Required input missing';
                RETURN NEXT;
            ELSE
                input_name := definition.input_name;
                valid := TRUE;
                validation_message := 'Optional input';
                RETURN NEXT;
            END IF;

            CONTINUE;
        END IF;

        actual_type := jsonb_typeof(supplied);
        expected_type := definition.data_type;

        valid := CASE expected_type
            WHEN 'string' THEN actual_type = 'string'
            WHEN 'number' THEN actual_type = 'number'
            WHEN 'boolean' THEN actual_type = 'boolean'
            WHEN 'list' THEN actual_type = 'array'
            WHEN 'map' THEN actual_type = 'object'
            WHEN 'object' THEN actual_type = 'object'
            ELSE FALSE
        END;

        input_name := definition.input_name;

        validation_message := CASE
            WHEN valid THEN 'Valid'
            ELSE 'Expected ' || expected_type ||
                 ', received ' || COALESCE(actual_type, 'null')
        END;

        RETURN NEXT;
    END LOOP;
END;
$$;

-- ------------------------------------------------
-- FUNCTION: DETERMINE DEPLOYMENT ELIGIBILITY
-- ------------------------------------------------

CREATE FUNCTION deployment_eligibility(
    p_deployment_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    approval_count BIGINT,
    required_approval_count INTEGER,
    failed_check_count BIGINT,
    pending_check_count BIGINT,
    policy_reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    policy_record RECORD;
    deployment_record RECORD;
    approvals BIGINT;
    failures BIGINT;
    pending BIGINT;
    unresolved BIGINT;
    unpinned BIGINT;
BEGIN
    SELECT d.*, e.protected, e.environment_id
    INTO deployment_record
    FROM deployments d
    JOIN environments e
      ON e.environment_id = d.environment_id
    WHERE d.deployment_id = p_deployment_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment % does not exist',
            p_deployment_id;
    END IF;

    SELECT *
    INTO policy_record
    FROM environment_policies ep
    WHERE ep.environment_id = deployment_record.environment_id;

    IF NOT FOUND THEN
        -- Unconfigured environments use a conservative policy.
        required_approval_count :=
            CASE WHEN deployment_record.protected THEN 2 ELSE 0 END;
        policy_record.require_passing_checks := TRUE;
        policy_record.require_pinned_source := TRUE;
        policy_record.require_resolved_discussions := TRUE;
    ELSE
        required_approval_count := policy_record.required_approvals;
    END IF;

    SELECT COUNT(DISTINCT reviewer_id)
    INTO approvals
    FROM deployment_approvals
    WHERE deployment_id = p_deployment_id
      AND decision = 'approved';

    SELECT
        COUNT(*) FILTER (WHERE status = 'failed'),
        COUNT(*) FILTER (WHERE status IN ('pending', 'skipped'))
    INTO failures, pending
    FROM deployment_checks
    WHERE deployment_id = p_deployment_id;

    SELECT COUNT(*)
    INTO unresolved
    FROM deployment_checks
    WHERE deployment_id = p_deployment_id
      AND check_name = 'review_discussions'
      AND status <> 'passed';

    SELECT COUNT(*)
    INTO unpinned
    FROM deployment_resources dr
    JOIN module_instances mi
      ON mi.instance_id = dr.instance_id
    JOIN module_versions mv
      ON mv.module_version_id = mi.module_version_id
    WHERE dr.deployment_id = p_deployment_id
      AND mv.source_commit IS NULL;

    approval_count := approvals;
    failed_check_count := failures;
    pending_check_count := pending;

    eligible :=
        approvals >= required_approval_count
        AND failures = 0
        AND (
            NOT policy_record.require_passing_checks
            OR pending = 0
        )
        AND (
            NOT policy_record.require_resolved_discussions
            OR unresolved = 0
        )
        AND (
            NOT policy_record.require_pinned_source
            OR unpinned = 0
        );

    policy_reason := CASE
        WHEN approvals < required_approval_count
            THEN 'Insufficient approvals'
        WHEN failures > 0
            THEN 'Failed automated checks'
        WHEN policy_record.require_passing_checks AND pending > 0
            THEN 'Incomplete automated checks'
        WHEN policy_record.require_resolved_discussions
             AND unresolved > 0
            THEN 'Unresolved review discussions'
        WHEN policy_record.require_pinned_source AND unpinned > 0
            THEN 'Module source is not pinned'
        ELSE 'Deployment satisfies policy'
    END;

    RETURN NEXT;
END;
$$;

-- ------------------------------------------------
-- FUNCTION: MODULE VERSION REPORT
-- ------------------------------------------------

CREATE FUNCTION latest_published_modules(
    p_organization_id BIGINT
)
RETURNS TABLE (
    module_name VARCHAR,
    latest_version TEXT,
    source_uri TEXT,
    checksum VARCHAR,
    release_date TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        m.module_name,
        CONCAT(
            mv.version_major, '.',
            mv.version_minor, '.',
            mv.version_patch
        ),
        mv.source_uri,
        mv.content_checksum,
        mv.published_at
    FROM modules m
    JOIN LATERAL (
        SELECT *
        FROM module_versions candidate
        WHERE candidate.module_id = m.module_id
          AND candidate.release_status = 'published'
        ORDER BY
            candidate.version_major DESC,
            candidate.version_minor DESC,
            candidate.version_patch DESC
        LIMIT 1
    ) mv ON TRUE
    WHERE m.organization_id = p_organization_id
    ORDER BY m.module_name;
$$;

-- ------------------------------------------------
-- PROCEDURE: PROCESS A DEPLOYMENT
-- ------------------------------------------------

CREATE PROCEDURE process_deployment(
    p_deployment_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    decision RECORD;
    current_status deployment_status;
BEGIN
    SELECT status
    INTO current_status
    FROM deployments
    WHERE deployment_id = p_deployment_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Deployment not found';
    END IF;

    IF current_status <> 'planned' THEN
        RAISE EXCEPTION
            'Only planned deployments can enter approval processing';
    END IF;

    SELECT *
    INTO decision
    FROM deployment_eligibility(p_deployment_id);

    IF NOT decision.eligible THEN
        UPDATE deployments
        SET status = 'awaiting_approval'
        WHERE deployment_id = p_deployment_id;

        INSERT INTO deployment_events (
            deployment_id,
            event_type,
            event_details
        )
        VALUES (
            p_deployment_id,
            'deployment_blocked',
            jsonb_build_object(
                'reason', decision.policy_reason,
                'approvals', decision.approval_count,
                'required_approvals',
                    decision.required_approval_count,
                'failed_checks', decision.failed_check_count,
                'pending_checks', decision.pending_check_count
            )
        );

        RETURN;
    END IF;

    UPDATE deployments
    SET status = 'applying'
    WHERE deployment_id = p_deployment_id;

    INSERT INTO deployment_events (
        deployment_id,
        event_type,
        event_details
    )
    VALUES (
        p_deployment_id,
        'deployment_authorized',
        jsonb_build_object(
            'approval_count', decision.approval_count
        )
    );
END;
$$;

-- ------------------------------------------------
-- VIEW: DEPLOYMENT GOVERNANCE REPORT
-- ------------------------------------------------

CREATE VIEW deployment_governance_report AS
SELECT
    d.deployment_id,
    p.project_name,
    e.environment_name,
    d.deployment_number,
    d.status,
    u.username AS requested_by,
    COUNT(DISTINCT da.approval_id) AS approval_records,
    COUNT(DISTINCT dc.check_id)
        FILTER (WHERE dc.status = 'passed') AS passed_checks,
    COUNT(DISTINCT dc.check_id)
        FILTER (WHERE dc.status = 'failed') AS failed_checks,
    d.state_revision,
    d.created_at
FROM deployments d
JOIN environments e
    ON e.environment_id = d.environment_id
JOIN infrastructure_projects p
    ON p.project_id = e.project_id
JOIN platform_users u
    ON u.user_id = d.requested_by
LEFT JOIN deployment_approvals da
    ON da.deployment_id = d.deployment_id
LEFT JOIN deployment_checks dc
    ON dc.deployment_id = d.deployment_id
GROUP BY
    d.deployment_id,
    p.project_name,
    e.environment_name,
    d.deployment_number,
    d.status,
    u.username,
    d.state_revision,
    d.created_at;

-- ------------------------------------------------
-- VIEW: MODULE CONSUMPTION
-- ------------------------------------------------

CREATE VIEW module_consumption_report AS
SELECT
    m.module_name,
    CONCAT(
        mv.version_major, '.',
        mv.version_minor, '.',
        mv.version_patch
    ) AS version,
    COUNT(DISTINCT mi.instance_id) AS instance_count,
    COUNT(DISTINCT mi.environment_id) AS environment_count,
    COUNT(DISTINCT d.deployment_id) AS deployment_count
FROM modules m
JOIN module_versions mv
    ON mv.module_id = m.module_id
LEFT JOIN module_instances mi
    ON mi.module_version_id = mv.module_version_id
LEFT JOIN deployment_resources dr
    ON dr.instance_id = mi.instance_id
LEFT JOIN deployments d
    ON d.deployment_id = dr.deployment_id
GROUP BY
    m.module_name,
    mv.version_major,
    mv.version_minor,
    mv.version_patch;

-- ------------------------------------------------
-- SAMPLE DATA
-- ------------------------------------------------

INSERT INTO organizations (organization_name)
VALUES ('Platform Engineering Organization');

INSERT INTO platform_users (
    organization_id,
    username,
    email
)
SELECT
    organization_id,
    users.username,
    users.email
FROM organizations
CROSS JOIN (
    VALUES
        ('admin', 'admin@example.com'),
        ('architect', 'architect@example.com'),
        ('reviewer_alice', 'alice@example.com'),
        ('reviewer_bob', 'bob@example.com'),
        ('developer', 'developer@example.com')
) AS users(username, email)
WHERE organization_name = 'Platform Engineering Organization';

INSERT INTO modules (
    organization_id,
    module_name,
    description,
    category,
    owner_user_id
)
SELECT
    o.organization_id,
    m.module_name,
    m.description,
    m.category,
    u.user_id
FROM organizations o
JOIN platform_users u
    ON u.organization_id = o.organization_id
   AND u.username = 'architect'
CROSS JOIN (
    VALUES
        (
            'network',
            'Reusable cloud networking infrastructure',
            'networking'
        ),
        (
            'application',
            'Reusable application compute infrastructure',
            'compute'
        ),
        (
            'storage',
            'Reusable encrypted storage infrastructure',
            'storage'
        )
) AS m(module_name, description, category)
WHERE o.organization_name = 'Platform Engineering Organization';

-- Publish stable releases.
INSERT INTO module_versions (
    module_id,
    version_major,
    version_minor,
    version_patch,
    source_uri,
    source_commit,
    content_checksum,
    terraform_min_version,
    release_status,
    published_by,
    published_at
)
SELECT
    module_id,
    1,
    2,
    0,
    'registry.example.com/platform/' || module_name,
    repeat('a', 40),
    repeat('a', 64),
    '1.5.0',
    'published',
    (
        SELECT user_id
        FROM platform_users
        WHERE username = 'architect'
    ),
    NOW()
FROM modules
WHERE module_name = 'network';

INSERT INTO module_versions (
    module_id,
    version_major,
    version_minor,
    version_patch,
    source_uri,
    source_commit,
    content_checksum,
    terraform_min_version,
    release_status,
    published_by,
    published_at
)
SELECT
    module_id,
    2,
    1,
    0,
    'registry.example.com/platform/' || module_name,
    repeat('b', 40),
    repeat('b', 64),
    '1.5.0',
    'published',
    (
        SELECT user_id
        FROM platform_users
        WHERE username = 'architect'
    ),
    NOW()
FROM modules
WHERE module_name = 'application';

-- An unpublished draft demonstrates release isolation.
INSERT INTO module_versions (
    module_id,
    version_major,
    version_minor,
    version_patch,
    source_uri,
    content_checksum,
    terraform_min_version,
    release_status
)
SELECT
    module_id,
    2,
    0,
    0,
    'registry.example.com/platform/' || module_name,
    repeat('c', 64),
    '1.5.0',
    'draft'
FROM modules
WHERE module_name = 'storage';

-- Module inputs.
INSERT INTO module_inputs (
    module_version_id,
    input_name,
    data_type,
    required,
    description
)
SELECT
    mv.module_version_id,
    input_definition.input_name,
    input_definition.data_type,
    input_definition.required,
    input_definition.description
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
CROSS JOIN (
    VALUES
        ('environment', 'string', TRUE, 'Deployment environment'),
        ('cidr', 'string', TRUE, 'Network address range'),
        ('region', 'string', TRUE, 'Cloud deployment region')
) AS input_definition(
    input_name,
    data_type,
    required,
    description
)
WHERE m.module_name = 'network'
  AND mv.release_status = 'published';

INSERT INTO module_inputs (
    module_version_id,
    input_name,
    data_type,
    required,
    default_value,
    description
)
SELECT
    mv.module_version_id,
    'instance_type',
    'string',
    FALSE,
    '"t3.small"'::JSONB,
    'Application compute instance type'
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
WHERE m.module_name = 'application'
  AND mv.release_status = 'published';

INSERT INTO module_inputs (
    module_version_id,
    input_name,
    data_type,
    required,
    description
)
SELECT
    mv.module_version_id,
    'environment',
    'string',
    TRUE,
    'Deployment environment'
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
WHERE m.module_name = 'application'
  AND mv.release_status = 'published';

-- Module outputs.
INSERT INTO module_outputs (
    module_version_id,
    output_name,
    data_type,
    description
)
SELECT
    mv.module_version_id,
    'network_id',
    'string',
    'Identifier of the created network'
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
WHERE m.module_name = 'network';

INSERT INTO module_outputs (
    module_version_id,
    output_name,
    data_type,
    description
)
SELECT
    mv.module_version_id,
    'application_id',
    'string',
    'Identifier of the application deployment'
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
WHERE m.module_name = 'application';

-- Module resources.
INSERT INTO module_resources (
    module_version_id,
    resource_name,
    resource_type,
    configuration
)
SELECT
    mv.module_version_id,
    resource.resource_name,
    resource.resource_type,
    resource.configuration::JSONB
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
CROSS JOIN (
    VALUES
        (
            'main',
            'aws_vpc',
            '{"enable_dns_support": true,
              "enable_dns_hostnames": true}'
        )
) AS resource(resource_name, resource_type, configuration)
WHERE m.module_name = 'network';

INSERT INTO module_resources (
    module_version_id,
    resource_name,
    resource_type,
    configuration
)
SELECT
    mv.module_version_id,
    'web',
    'aws_instance',
    '{"encrypted_volume": true,
      "monitoring": true}'::JSONB
FROM module_versions mv
JOIN modules m ON m.module_id = mv.module_id
WHERE m.module_name = 'application';

-- Application depends on the network module.
INSERT INTO module_dependencies (
    module_version_id,
    depends_on_version_id,
    version_constraint
)
SELECT
    app.module_version_id,
    network.module_version_id,
    '~> 1.2.0'
FROM module_versions app
JOIN modules app_module
    ON app_module.module_id = app.module_id
JOIN module_versions network
    ON network.version_major = 1
   AND network.version_minor = 2
   AND network.version_patch = 0
JOIN modules network_module
    ON network_module.module_id = network.module_id
WHERE app_module.module_name = 'application'
  AND network_module.module_name = 'network';

-- Projects.
INSERT INTO infrastructure_projects (
    organization_id,
    project_name,
    description
)
SELECT
    organization_id,
    'enterprise-platform',
    'Enterprise cloud infrastructure platform'
FROM organizations
WHERE organization_name = 'Platform Engineering Organization';

-- Environments.
INSERT INTO environments (
    project_id,
    environment_name,
    region,
    protected
)
SELECT
    project_id,
    env.environment_name,
    'ap-south-1',
    env.protected
FROM infrastructure_projects
CROSS JOIN (
    VALUES
        ('development', FALSE),
        ('staging', FALSE),
        ('production', TRUE)
) AS env(environment_name, protected)
WHERE project_name = 'enterprise-platform';

-- Policies.
INSERT INTO environment_policies (
    environment_id,
    required_approvals,
    require_passing_checks,
    require_pinned_source,
    require_resolved_discussions,
    allow_destroy,
    prohibit_unencrypted_resources
)
SELECT
    environment_id,
    CASE
        WHEN environment_name = 'production' THEN 2
        ELSE 0
    END,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    TRUE
FROM environments;

-- Module instances in production.
INSERT INTO module_instances (
    environment_id,
    module_version_id,
    instance_name,
    input_values,
    created_by
)
SELECT
    e.environment_id,
    mv.module_version_id,
    instance.instance_name,
    instance.input_values::JSONB,
    u.user_id
FROM environments e
JOIN modules m ON m.module_name = 'network'
JOIN module_versions mv
    ON mv.module_id = m.module_id
   AND mv.release_status = 'published'
JOIN platform_users u ON u.username = 'developer'
CROSS JOIN (
    VALUES (
        'production-network',
        '{"environment":"production",
          "cidr":"10.60.0.0/16",
          "region":"ap-south-1"}'
    )
) AS instance(instance_name, input_values)
WHERE e.environment_name = 'production';

INSERT INTO module_instances (
    environment_id,
    module_version_id,
    instance_name,
    input_values,
    created_by
)
SELECT
    e.environment_id,
    mv.module_version_id,
    'production-application',
    '{"environment":"production",
      "instance_type":"t3.medium"}'::JSONB,
    u.user_id
FROM environments e
JOIN modules m ON m.module_name = 'application'
JOIN module_versions mv
    ON mv.module_id = m.module_id
   AND mv.release_status = 'published'
JOIN platform_users u ON u.username = 'developer'
WHERE e.environment_name = 'production';

-- ------------------------------------------------
-- DEPLOYMENT SAMPLE RECORDS
-- ------------------------------------------------

INSERT INTO deployments (
    environment_id,
    requested_by,
    deployment_number,
    status,
    plan_checksum,
    state_revision,
    started_at
)
SELECT
    e.environment_id,
    u.user_id,
    1,
    'planned',
    repeat('d', 64),
    0,
    NOW()
FROM environments e
JOIN platform_users u ON u.username = 'developer'
WHERE e.environment_name = 'production';

-- Deployment checks.
INSERT INTO deployment_checks (
    deployment_id,
    check_name,
    status,
    details,
    executed_at
)
SELECT
    deployment_id,
    checks.check_name,
    checks.status::check_status,
    checks.details::JSONB,
    NOW()
FROM deployments
CROSS JOIN (
    VALUES
        (
            'terraform_validate',
            'passed',
            '{"message":"Configuration is valid"}'
        ),
        (
            'terraform_plan',
            'passed',
            '{"message":"Execution plan generated"}'
        ),
        (
            'security_scan',
            'passed',
            '{"message":"Security policy passed"}'
        ),
        (
            'review_discussions',
            'passed',
            '{"message":"All discussions resolved"}'
        )
) AS checks(check_name, status, details);

-- Two independent approval decisions.
INSERT INTO deployment_approvals (
    deployment_id,
    reviewer_id,
    decision,
    comment
)
SELECT
    d.deployment_id,
    u.user_id,
    'approved',
    'Infrastructure architecture reviewed'
FROM deployments d
CROSS JOIN platform_users u
WHERE u.username IN ('reviewer_alice', 'reviewer_bob');

-- Deployment resource plan.
INSERT INTO deployment_resources (
    deployment_id,
    instance_id,
    resource_address,
    action,
    desired_configuration
)
SELECT
    d.deployment_id,
    mi.instance_id,
    CASE
        WHEN m.module_name = 'network'
            THEN 'module.network.aws_vpc.main'
        ELSE 'module.application.aws_instance.web'
    END,
    'create',
    mr.configuration
FROM deployments d
JOIN environments e ON e.environment_id = d.environment_id
JOIN module_instances mi
    ON mi.environment_id = e.environment_id
JOIN module_versions mv
    ON mv.module_version_id = mi.module_version_id
JOIN modules m ON m.module_id = mv.module_id
JOIN module_resources mr
    ON mr.module_version_id = mv.module_version_id;

-- ------------------------------------------------
-- RETRIEVAL QUERIES
-- ------------------------------------------------

-- Query 1: Published module releases.
SELECT
    m.module_name,
    CONCAT(
        mv.version_major, '.',
        mv.version_minor, '.',
        mv.version_patch
    ) AS version,
    mv.source_uri,
    mv.source_commit,
    mv.release_status
FROM modules m
JOIN module_versions mv
    ON mv.module_id = m.module_id
WHERE mv.release_status = 'published'
ORDER BY m.module_name, mv.version_major DESC,
         mv.version_minor DESC, mv.version_patch DESC;

-- Query 2: Module input and output contracts.
SELECT
    m.module_name,
    mv.version_major,
    mv.version_minor,
    mi.input_name,
    mi.data_type,
    mi.required,
    mi.sensitive
FROM modules m
JOIN module_versions mv
    ON mv.module_id = m.module_id
JOIN module_inputs mi
    ON mi.module_version_id = mv.module_version_id
ORDER BY m.module_name, mi.input_name;

-- Query 3: Module dependency relationships.
SELECT
    parent.module_name AS module,
    dependency.module_name AS dependency,
    CONCAT(
        dependency_version.version_major, '.',
        dependency_version.version_minor, '.',
        dependency_version.version_patch
    ) AS dependency_version,
    md.version_constraint
FROM module_dependencies md
JOIN module_versions parent_version
    ON parent_version.module_version_id = md.module_version_id
JOIN modules parent
    ON parent.module_id = parent_version.module_id
JOIN module_versions dependency_version
    ON dependency_version.module_version_id =
       md.depends_on_version_id
JOIN modules dependency
    ON dependency.module_id = dependency_version.module_id;

-- ------------------------------------------------
-- VALIDATION QUERIES
-- ------------------------------------------------

-- Query 4: Validate network module inputs.
SELECT *
FROM validate_module_inputs(
    (
        SELECT mv.module_version_id
        FROM module_versions mv
        JOIN modules m ON m.module_id = mv.module_id
        WHERE m.module_name = 'network'
          AND mv.release_status = 'published'
        LIMIT 1
    ),
    '{
        "environment": "production",
        "cidr": "10.60.0.0/16",
        "region": "ap-south-1"
    }'::JSONB
);

-- Query 5: Check for required module inputs missing from instances.
SELECT
    mi.instance_name,
    definition.input_name
FROM module_instances mi
JOIN module_inputs definition
    ON definition.module_version_id = mi.module_version_id
WHERE definition.required
  AND NOT (
      mi.input_values ? definition.input_name
  );

-- ------------------------------------------------
-- AGGREGATION AND REPORTING
-- ------------------------------------------------

-- Query 6: Latest published module releases.
SELECT *
FROM latest_published_modules(
    (
        SELECT organization_id
        FROM organizations
        WHERE organization_name =
            'Platform Engineering Organization'
    )
);

-- Query 7: Module usage.
SELECT *
FROM module_consumption_report
ORDER BY instance_count DESC;

-- Query 8: Deployment governance report.
SELECT *
FROM deployment_governance_report
ORDER BY created_at DESC;

-- ------------------------------------------------
-- ELIGIBILITY EVALUATION
-- ------------------------------------------------

-- Query 9: Determine whether the sample deployment can proceed.
SELECT *
FROM deployment_eligibility(
    (SELECT MIN(deployment_id) FROM deployments)
);

-- ------------------------------------------------
-- TRANSACTIONAL WORKFLOW
-- ------------------------------------------------

-- The deployment procedure locks and checks the deployment.
-- A blocked deployment enters awaiting_approval.
-- An eligible deployment enters applying.
-- Actual infrastructure execution is performed by an external
-- deployment worker, not by PostgreSQL itself.

COMMIT;

BEGIN;

CALL process_deployment(
    (SELECT MIN(deployment_id) FROM terraform_platform.deployments)
);

COMMIT;

-- ------------------------------------------------
-- FINAL WORKFLOW REPORT
-- ------------------------------------------------

SELECT
    deployment_id,
    deployment_number,
    status,
    started_at,
    completed_at,
    error_message
FROM terraform_platform.deployments
ORDER BY deployment_id;

SELECT
    deployment_id,
    event_type,
    event_details,
    created_at
FROM terraform_platform.deployment_events
ORDER BY event_id;

-- ------------------------------------------------
-- EXAMPLE POLICY-FAILURE CASES
-- ------------------------------------------------

-- This query deliberately creates a failed-check evaluation
-- without modifying the published module registry.

SELECT
    d.deployment_id,
    COUNT(*) FILTER (
        WHERE c.status = 'failed'
    ) AS failed_checks
FROM terraform_platform.deployments d
LEFT JOIN terraform_platform.deployment_checks c
    ON c.deployment_id = d.deployment_id
GROUP BY d.deployment_id;

-- ------------------------------------------------
-- SECURITY AND PERFORMANCE NOTES
-- ------------------------------------------------

-- 1. Never store cloud credentials or secret values in
--    module_inputs, input_values, configuration or event_details.
--
-- 2. Use a secret manager and retrieve credentials at runtime.
--
-- 3. Restrict database access using role-based permissions.
--
-- 4. Published module versions are immutable.
--
-- 5. Production deployments require explicit policy evaluation.
--
-- 6. Indexes support version resolution, environment lookup,
--    deployment history and validation reporting.
--
-- 7. Deployment workers should use external locking and state
--    backend locking for concurrent Terraform operations.
--
-- 8. Database transactions do not make cloud API operations
--    transactional. Failed infrastructure operations require
--    explicit recovery and state reconciliation.
