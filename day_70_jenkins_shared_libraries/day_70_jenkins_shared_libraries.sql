/*
 * Jenkins Shared Libraries
 * Reusable enterprise pipeline code.
 *
 * PostgreSQL 15+
 *
 * Models:
 * - Repositories and branches
 * - Shared library releases
 * - Library source modules and reusable steps
 * - Pipeline definitions and executions
 * - Pipeline stages
 * - Credentials references
 * - Release approvals
 * - Automated test results
 * - Environment deployment policies
 * - Pipeline execution events
 * - Release and deployment eligibility
 *
 * Execute as a database role with schema creation privileges.
 */

BEGIN;

CREATE SCHEMA IF NOT EXISTS jenkins_shared;

SET search_path TO jenkins_shared, public;

-- ============================================================
-- 1. DOMAIN TYPES
-- ============================================================

CREATE TYPE release_status AS ENUM (
    'DRAFT',
    'TESTED',
    'APPROVED',
    'REJECTED',
    'DEPRECATED'
);

CREATE TYPE pipeline_status AS ENUM (
    'CREATED',
    'QUEUED',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'ABORTED'
);

CREATE TYPE stage_status AS ENUM (
    'PENDING',
    'RUNNING',
    'SUCCESS',
    'FAILED',
    'SKIPPED'
);

CREATE TYPE deployment_environment AS ENUM (
    'DEVELOPMENT',
    'STAGING',
    'PRODUCTION'
);

CREATE TYPE approval_status AS ENUM (
    'PENDING',
    'APPROVED',
    'REJECTED',
    'REVOKED'
);

-- ============================================================
-- 2. REPOSITORIES AND BRANCHES
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name VARCHAR(120) NOT NULL UNIQUE,
    repository_url TEXT NOT NULL,
    default_branch VARCHAR(120) NOT NULL DEFAULT 'main',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT repository_name_valid
        CHECK (repository_name ~ '^[a-zA-Z0-9._-]+$'),

    CONSTRAINT repository_url_valid
        CHECK (
            repository_url LIKE 'https://%'
            OR repository_url LIKE 'ssh://%'
        )
);

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id) ON DELETE CASCADE,

    branch_name VARCHAR(150) NOT NULL,
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    latest_commit VARCHAR(40),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (repository_id, branch_name),

    CONSTRAINT branch_commit_valid
        CHECK (
            latest_commit IS NULL
            OR latest_commit ~ '^[a-fA-F0-9]{7,40}$'
        )
);

-- ============================================================
-- 3. SHARED LIBRARY DEFINITIONS
-- ============================================================

CREATE TABLE shared_libraries (
    library_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_name VARCHAR(120) NOT NULL UNIQUE,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    description TEXT NOT NULL,
    owner_team VARCHAR(120) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE library_releases (
    release_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    library_id BIGINT NOT NULL
        REFERENCES shared_libraries(library_id),

    version VARCHAR(30) NOT NULL,
    commit_hash VARCHAR(40) NOT NULL,
    release_status release_status NOT NULL DEFAULT 'DRAFT',

    tested_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    deprecated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (library_id, version),
    UNIQUE (release_id, library_id),

    CONSTRAINT semantic_version_valid
        CHECK (version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'),

    CONSTRAINT release_commit_valid
        CHECK (commit_hash ~ '^[a-fA-F0-9]{7,40}$'),

    CONSTRAINT tested_release_has_timestamp
        CHECK (
            release_status NOT IN ('TESTED', 'APPROVED', 'DEPRECATED')
            OR tested_at IS NOT NULL
        ),

    CONSTRAINT approved_release_has_timestamp
        CHECK (
            release_status <> 'APPROVED'
            OR approved_at IS NOT NULL
        )
);

CREATE TABLE library_modules (
    module_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id BIGINT NOT NULL
        REFERENCES library_releases(release_id) ON DELETE CASCADE,

    module_path VARCHAR(300) NOT NULL,
    module_type VARCHAR(30) NOT NULL,
    description TEXT NOT NULL,

    UNIQUE (release_id, module_path),

    CHECK (
        module_type IN (
            'VARS',
            'SRC',
            'RESOURCES',
            'TESTS'
        )
    ),

    CHECK (
        module_path NOT LIKE '/%'
        AND module_path NOT LIKE '%..%'
    )
);

CREATE TABLE reusable_steps (
    step_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    release_id BIGINT NOT NULL
        REFERENCES library_releases(release_id) ON DELETE CASCADE,

    step_name VARCHAR(120) NOT NULL,
    module_path VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,

    idempotent BOOLEAN NOT NULL DEFAULT FALSE,
    requires_credentials BOOLEAN NOT NULL DEFAULT FALSE,

    UNIQUE (release_id, step_name)
);

-- ============================================================
-- 4. RELEASE APPROVALS
-- ============================================================

CREATE TABLE library_approvals (
    approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    release_id BIGINT NOT NULL
        REFERENCES library_releases(release_id),

    reviewer VARCHAR(120) NOT NULL,
    reviewer_role VARCHAR(80) NOT NULL,

    decision approval_status NOT NULL,
    comments TEXT,

    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (reviewer <> '')
);

-- ============================================================
-- 5. PIPELINE DEFINITIONS
-- ============================================================

CREATE TABLE pipeline_definitions (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    pipeline_name VARCHAR(150) NOT NULL,

    release_id BIGINT NOT NULL,

    branch_name VARCHAR(150) NOT NULL,

    environment deployment_environment NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    require_production_approval BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    FOREIGN KEY (release_id)
        REFERENCES library_releases(release_id),

    FOREIGN KEY (repository_id, branch_name)
        REFERENCES branches(repository_id, branch_name),

    UNIQUE (pipeline_id, release_id)
);

-- ============================================================
-- 6. EXECUTION POLICY
-- ============================================================

CREATE TABLE environment_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    environment deployment_environment NOT NULL UNIQUE,

    require_approved_library BOOLEAN NOT NULL DEFAULT TRUE,
    require_successful_tests BOOLEAN NOT NULL DEFAULT TRUE,
    require_manual_approval BOOLEAN NOT NULL DEFAULT FALSE,

    minimum_tests INTEGER NOT NULL DEFAULT 1,

    max_retry_attempts INTEGER NOT NULL DEFAULT 3,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (minimum_tests >= 0),
    CHECK (max_retry_attempts BETWEEN 1 AND 10)
);

-- ============================================================
-- 7. PIPELINE EXECUTIONS
-- ============================================================

CREATE TABLE pipeline_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pipeline_id BIGINT NOT NULL
        REFERENCES pipeline_definitions(pipeline_id),

    release_id BIGINT NOT NULL
        REFERENCES library_releases(release_id),

    build_number INTEGER NOT NULL,

    triggered_by VARCHAR(120) NOT NULL,

    source_commit VARCHAR(40) NOT NULL,

    status pipeline_status NOT NULL DEFAULT 'CREATED',

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (pipeline_id, build_number),

    CHECK (build_number > 0),

    CHECK (source_commit ~ '^[a-fA-F0-9]{7,40}$'),

    CHECK (
        finished_at IS NULL
        OR started_at IS NOT NULL
    ),

    CHECK (
        finished_at IS NULL
        OR finished_at >= started_at
    ),

    CHECK (
        status <> 'SUCCESS'
        OR finished_at IS NOT NULL
    )
);

-- ============================================================
-- 8. PIPELINE STAGES
-- ============================================================

CREATE TABLE pipeline_stages (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,

    stage_name VARCHAR(120) NOT NULL,

    sequence_number INTEGER NOT NULL,

    status stage_status NOT NULL DEFAULT 'PENDING',

    attempt_count INTEGER NOT NULL DEFAULT 0,

    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,

    duration_ms BIGINT,

    error_message TEXT,

    UNIQUE (run_id, stage_name),
    UNIQUE (run_id, sequence_number),

    CHECK (sequence_number > 0),
    CHECK (attempt_count >= 0),
    CHECK (duration_ms IS NULL OR duration_ms >= 0),

    CHECK (
        finished_at IS NULL
        OR started_at IS NOT NULL
    )
);

-- ============================================================
-- 9. TEST RESULTS
-- ============================================================

CREATE TABLE pipeline_test_results (
    test_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,

    test_suite VARCHAR(150) NOT NULL,

    total_tests INTEGER NOT NULL,
    passed_tests INTEGER NOT NULL,
    failed_tests INTEGER NOT NULL,
    skipped_tests INTEGER NOT NULL DEFAULT 0,

    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (total_tests >= 0),
    CHECK (passed_tests >= 0),
    CHECK (failed_tests >= 0),
    CHECK (skipped_tests >= 0),

    CHECK (
        total_tests = passed_tests + failed_tests + skipped_tests
    )
);

-- ============================================================
-- 10. MANUAL DEPLOYMENT APPROVALS
-- ============================================================

CREATE TABLE deployment_approvals (
    deployment_approval_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,

    approver VARCHAR(120) NOT NULL,

    approver_role VARCHAR(80) NOT NULL,

    decision approval_status NOT NULL DEFAULT 'PENDING',

    comments TEXT,

    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (run_id, approver),

    CHECK (approver <> '')
);

-- ============================================================
-- 11. EXECUTION EVENT AUDIT
-- ============================================================

CREATE TABLE pipeline_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,

    event_type VARCHAR(100) NOT NULL,

    event_description TEXT NOT NULL,

    actor VARCHAR(120) NOT NULL,

    event_data JSONB NOT NULL DEFAULT '{}'::JSONB,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- 12. INDEXES
-- ============================================================

CREATE INDEX idx_library_release_status
    ON library_releases(library_id, release_status);

CREATE INDEX idx_pipeline_runs_status
    ON pipeline_runs(status, created_at DESC);

CREATE INDEX idx_pipeline_runs_pipeline
    ON pipeline_runs(pipeline_id, build_number DESC);

CREATE INDEX idx_pipeline_stages_run_status
    ON pipeline_stages(run_id, status);

CREATE INDEX idx_test_results_run
    ON pipeline_test_results(run_id);

CREATE INDEX idx_deployment_approvals_run
    ON deployment_approvals(run_id, decision);

CREATE INDEX idx_pipeline_events_run_time
    ON pipeline_events(run_id, created_at DESC);

CREATE INDEX idx_library_modules_release
    ON library_modules(release_id, module_type);

-- ============================================================
-- 13. RELEASE GOVERNANCE TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION enforce_library_release_governance()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.release_status = 'APPROVED' THEN
            RAISE EXCEPTION
                'Approved library releases cannot be deleted.';
        END IF;

        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' THEN

        IF OLD.release_status = 'APPROVED' THEN
            IF NEW.library_id <> OLD.library_id
               OR NEW.version <> OLD.version
               OR NEW.commit_hash <> OLD.commit_hash THEN

                RAISE EXCEPTION
                    'Approved release identity and commit are immutable.';
            END IF;

            IF NEW.release_status NOT IN ('APPROVED', 'DEPRECATED') THEN
                RAISE EXCEPTION
                    'Approved release cannot return to an earlier state.';
            END IF;
        END IF;

        IF NEW.release_status = 'TESTED'
           AND NEW.tested_at IS NULL THEN
            NEW.tested_at := NOW();
        END IF;

        IF NEW.release_status = 'APPROVED'
           AND NEW.approved_at IS NULL THEN
            NEW.approved_at := NOW();
        END IF;

        IF NEW.release_status = 'DEPRECATED'
           AND NEW.deprecated_at IS NULL THEN
            NEW.deprecated_at := NOW();
        END IF;

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_library_release_governance
BEFORE UPDATE OR DELETE ON library_releases
FOR EACH ROW
EXECUTE FUNCTION enforce_library_release_governance();

-- ============================================================
-- 14. PIPELINE STATE VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_pipeline_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status IN ('SUCCESS', 'FAILED', 'ABORTED')
       AND NEW.status <> OLD.status THEN
        RAISE EXCEPTION
            'Terminal pipeline state cannot be changed.';
    END IF;

    IF NEW.status = 'RUNNING' AND NEW.started_at IS NULL THEN
        NEW.started_at := NOW();
    END IF;

    IF NEW.status IN ('SUCCESS', 'FAILED', 'ABORTED')
       AND NEW.finished_at IS NULL THEN
        NEW.finished_at := NOW();
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pipeline_transition
BEFORE UPDATE ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION validate_pipeline_transition();

-- ============================================================
-- 15. PIPELINE EVENT TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION record_pipeline_status_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN

        INSERT INTO pipeline_events (
            run_id,
            event_type,
            event_description,
            actor,
            event_data
        )
        VALUES (
            NEW.run_id,
            'STATUS_CHANGED',
            'Pipeline status changed from '
                || OLD.status || ' to ' || NEW.status,
            'system',
            jsonb_build_object(
                'previous_status', OLD.status,
                'new_status', NEW.status
            )
        );

    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pipeline_status_event
AFTER UPDATE ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION record_pipeline_status_event();

-- ============================================================
-- 16. MERGE-LIKE RELEASE ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_pipeline_eligibility(
    p_run_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    library_approved BOOLEAN,
    tests_passed BOOLEAN,
    deployment_approved BOOLEAN,
    policy_environment deployment_environment,
    reasons TEXT[]
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_run pipeline_runs%ROWTYPE;
    v_pipeline pipeline_definitions%ROWTYPE;
    v_release library_releases%ROWTYPE;
    v_policy environment_policies%ROWTYPE;

    v_tests_passed BOOLEAN;
    v_deployment_approved BOOLEAN;
    v_library_approved BOOLEAN;

    v_reasons TEXT[] := ARRAY[]::TEXT[];
BEGIN
    SELECT *
    INTO v_run
    FROM pipeline_runs
    WHERE run_id = p_run_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline run % does not exist.', p_run_id;
    END IF;

    SELECT *
    INTO v_pipeline
    FROM pipeline_definitions
    WHERE pipeline_id = v_run.pipeline_id;

    SELECT *
    INTO v_release
    FROM library_releases
    WHERE release_id = v_run.release_id;

    SELECT *
    INTO v_policy
    FROM environment_policies
    WHERE environment = v_pipeline.environment;

    IF NOT FOUND THEN
        v_reasons := array_append(
            v_reasons,
            'No environment policy configured.'
        );

        RETURN QUERY SELECT
            FALSE, FALSE, FALSE, FALSE,
            v_pipeline.environment, v_reasons;

        RETURN;
    END IF;

    v_library_approved :=
        v_release.release_status = 'APPROVED';

    SELECT
        COALESCE(
            BOOL_AND(
                failed_tests = 0
                AND passed_tests >= v_policy.minimum_tests
            ),
            FALSE
        )
    INTO v_tests_passed
    FROM pipeline_test_results
    WHERE run_id = p_run_id;

    v_deployment_approved :=
        CASE
            WHEN NOT v_policy.require_manual_approval
                 AND NOT (
                     v_pipeline.environment = 'PRODUCTION'
                     AND v_pipeline.require_production_approval
                 )
            THEN TRUE

            ELSE EXISTS (
                SELECT 1
                FROM deployment_approvals
                WHERE run_id = p_run_id
                  AND decision = 'APPROVED'
            )
        END;

    IF v_policy.require_approved_library
       AND NOT v_library_approved THEN
        v_reasons := array_append(
            v_reasons,
            'Shared library release is not approved.'
        );
    END IF;

    IF v_policy.require_successful_tests
       AND NOT v_tests_passed THEN
        v_reasons := array_append(
            v_reasons,
            'Automated test requirements are not satisfied.'
        );
    END IF;

    IF NOT v_deployment_approved THEN
        v_reasons := array_append(
            v_reasons,
            'Required deployment approval is missing.'
        );
    END IF;

    IF v_run.status <> 'SUCCESS' THEN
        v_reasons := array_append(
            v_reasons,
            'Pipeline execution has not completed successfully.'
        );
    END IF;

    RETURN QUERY SELECT
        (
            cardinality(v_reasons) = 0
        ),
        v_library_approved,
        v_tests_passed,
        v_deployment_approved,
        v_pipeline.environment,
        v_reasons;
END;
$$;

-- ============================================================
-- 17. PIPELINE EXECUTION PROCEDURE
-- ============================================================

CREATE OR REPLACE PROCEDURE start_pipeline_run(
    p_run_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_run pipeline_runs%ROWTYPE;
    v_release library_releases%ROWTYPE;
    v_pipeline pipeline_definitions%ROWTYPE;
    v_policy environment_policies%ROWTYPE;
BEGIN
    SELECT *
    INTO v_run
    FROM pipeline_runs
    WHERE run_id = p_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline run not found.';
    END IF;

    IF v_run.status NOT IN ('CREATED', 'QUEUED') THEN
        RAISE EXCEPTION
            'Pipeline run cannot start from status %.',
            v_run.status;
    END IF;

    SELECT *
    INTO v_pipeline
    FROM pipeline_definitions
    WHERE pipeline_id = v_run.pipeline_id;

    SELECT *
    INTO v_release
    FROM library_releases
    WHERE release_id = v_run.release_id;

    SELECT *
    INTO v_policy
    FROM environment_policies
    WHERE environment = v_pipeline.environment;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Environment policy does not exist.';
    END IF;

    IF NOT v_pipeline.enabled THEN
        RAISE EXCEPTION 'Pipeline is disabled.';
    END IF;

    IF v_pipeline.release_id <> v_run.release_id THEN
        RAISE EXCEPTION
            'Pipeline run does not use its configured library release.';
    END IF;

    IF v_policy.require_approved_library
       AND v_release.release_status <> 'APPROVED' THEN
        RAISE EXCEPTION 'Library release is not approved.';
    END IF;

    UPDATE pipeline_runs
    SET status = 'RUNNING',
        started_at = NOW()
    WHERE run_id = p_run_id;

    INSERT INTO pipeline_events (
        run_id,
        event_type,
        event_description,
        actor
    )
    VALUES (
        p_run_id,
        'PIPELINE_STARTED',
        'Pipeline execution started.',
        'system'
    );

    RAISE NOTICE 'Pipeline run % started.', p_run_id;
END;
$$;

-- ============================================================
-- 18. SAMPLE REPOSITORIES
-- ============================================================

INSERT INTO repositories (
    repository_name,
    repository_url,
    default_branch
)
VALUES
(
    'enterprise-shared-library',
    'https://git.example.com/platform/enterprise-shared-library.git',
    'main'
),
(
    'payment-service',
    'https://git.example.com/platform/payment-service.git',
    'main'
),
(
    'inventory-service',
    'https://git.example.com/platform/inventory-service.git',
    'main'
);

INSERT INTO branches (
    repository_id,
    branch_name,
    protected,
    latest_commit
)
SELECT
    repository_id,
    'main',
    TRUE,
    'a1b2c3d4e5f6789'
FROM repositories;

INSERT INTO branches (
    repository_id,
    branch_name,
    protected,
    latest_commit
)
SELECT
    repository_id,
    'develop',
    FALSE,
    'b1c2d3e4f5a6789'
FROM repositories;

-- ============================================================
-- 19. SAMPLE SHARED LIBRARY
-- ============================================================

INSERT INTO shared_libraries (
    library_name,
    repository_id,
    description,
    owner_team
)
SELECT
    'enterprise-ci',
    repository_id,
    'Reusable enterprise Jenkins pipeline operations.',
    'Platform Engineering'
FROM repositories
WHERE repository_name = 'enterprise-shared-library';

INSERT INTO library_releases (
    library_id,
    version,
    commit_hash,
    release_status,
    tested_at,
    approved_at
)
SELECT
    library_id,
    '2.1.0',
    'a1b2c3d4e5f6789',
    'APPROVED',
    NOW(),
    NOW()
FROM shared_libraries
WHERE library_name = 'enterprise-ci';

INSERT INTO library_releases (
    library_id,
    version,
    commit_hash,
    release_status
)
SELECT
    library_id,
    '2.2.0',
    'b1b2c3d4e5f6789',
    'DRAFT'
FROM shared_libraries
WHERE library_name = 'enterprise-ci';

INSERT INTO library_modules (
    release_id,
    module_path,
    module_type,
    description
)
SELECT
    release_id,
    module_path,
    module_type,
    description
FROM library_releases r
CROSS JOIN (
    VALUES
    (
        'vars/standardPipeline.groovy',
        'VARS',
        'Reusable pipeline entry point.'
    ),
    (
        'vars/buildApplication.groovy',
        'VARS',
        'Reusable application build operation.'
    ),
    (
        'vars/runQualityChecks.groovy',
        'VARS',
        'Automated quality gate.'
    ),
    (
        'src/com/company/ci/DeploymentService.groovy',
        'SRC',
        'Deployment domain service.'
    ),
    (
        'resources/policies/production.json',
        'RESOURCES',
        'Production deployment policy.'
    ),
    (
        'test/SharedLibraryTest.groovy',
        'TESTS',
        'Shared library automated tests.'
    )
) AS modules(module_path, module_type, description)
WHERE r.version = '2.1.0';

INSERT INTO reusable_steps (
    release_id,
    step_name,
    module_path,
    description,
    idempotent,
    requires_credentials
)
SELECT
    release_id,
    step_name,
    module_path,
    description,
    idempotent,
    requires_credentials
FROM library_releases r
CROSS JOIN (
    VALUES
    (
        'checkoutSource',
        'vars/standardPipeline.groovy',
        'Checks out the requested source branch.',
        TRUE,
        FALSE
    ),
    (
        'buildApplication',
        'vars/buildApplication.groovy',
        'Builds the application artifact.',
        TRUE,
        FALSE
    ),
    (
        'runQualityChecks',
        'vars/runQualityChecks.groovy',
        'Runs unit and quality tests.',
        TRUE,
        FALSE
    ),
    (
        'deployArtifact',
        'src/com/company/ci/DeploymentService.groovy',
        'Deploys an approved artifact.',
        FALSE,
        TRUE
    )
) AS steps(
    step_name,
    module_path,
    description,
    idempotent,
    requires_credentials
)
WHERE r.version = '2.1.0';

-- ============================================================
-- 20. SAMPLE RELEASE APPROVAL
-- ============================================================

INSERT INTO library_approvals (
    release_id,
    reviewer,
    reviewer_role,
    decision,
    comments
)
SELECT
    release_id,
    'platform-lead',
    'LIBRARY_MAINTAINER',
    'APPROVED',
    'Release passed testing and compatibility review.'
FROM library_releases
WHERE version = '2.1.0';

-- ============================================================
-- 21. SAMPLE ENVIRONMENT POLICIES
-- ============================================================

INSERT INTO environment_policies (
    environment,
    require_approved_library,
    require_successful_tests,
    require_manual_approval,
    minimum_tests,
    max_retry_attempts
)
VALUES
(
    'DEVELOPMENT',
    TRUE,
    TRUE,
    FALSE,
    1,
    3
),
(
    'STAGING',
    TRUE,
    TRUE,
    FALSE,
    1,
    3
),
(
    'PRODUCTION',
    TRUE,
    TRUE,
    TRUE,
    10,
    2
);

-- ============================================================
-- 22. SAMPLE PIPELINE DEFINITIONS
-- ============================================================

INSERT INTO pipeline_definitions (
    repository_id,
    pipeline_name,
    release_id,
    branch_name,
    environment,
    require_production_approval
)
SELECT
    repo.repository_id,
    'payment-service-ci',
    release.release_id,
    'main',
    'STAGING',
    TRUE
FROM repositories repo
CROSS JOIN library_releases release
WHERE repo.repository_name = 'payment-service'
  AND release.version = '2.1.0';

INSERT INTO pipeline_definitions (
    repository_id,
    pipeline_name,
    release_id,
    branch_name,
    environment,
    require_production_approval
)
SELECT
    repo.repository_id,
    'inventory-service-production',
    release.release_id,
    'main',
    'PRODUCTION',
    TRUE
FROM repositories repo
CROSS JOIN library_releases release
WHERE repo.repository_name = 'inventory-service'
  AND release.version = '2.1.0';

-- ============================================================
-- 23. SAMPLE PIPELINE RUNS
-- ============================================================

INSERT INTO pipeline_runs (
    pipeline_id,
    release_id,
    build_number,
    triggered_by,
    source_commit,
    status,
    started_at,
    finished_at
)
SELECT
    pipeline_id,
    release_id,
    101,
    'developer-01',
    'c1d2e3f4a5b6789',
    'SUCCESS',
    NOW() - INTERVAL '15 minutes',
    NOW() - INTERVAL '10 minutes'
FROM pipeline_definitions
WHERE pipeline_name = 'payment-service-ci';

INSERT INTO pipeline_runs (
    pipeline_id,
    release_id,
    build_number,
    triggered_by,
    source_commit,
    status,
    failure_reason
)
SELECT
    pipeline_id,
    release_id,
    102,
    'developer-02',
    'd1e2f3a4b5c6789',
    'FAILED',
    'Automated quality gate failed.'
FROM pipeline_definitions
WHERE pipeline_name = 'payment-service-ci';

INSERT INTO pipeline_runs (
    pipeline_id,
    release_id,
    build_number,
    triggered_by,
    source_commit,
    status,
    started_at,
    finished_at
)
SELECT
    pipeline_id,
    release_id,
    103,
    'release-manager',
    'e1f2a3b4c5d6789',
    'SUCCESS',
    NOW() - INTERVAL '5 minutes',
    NOW()
FROM pipeline_definitions
WHERE pipeline_name = 'inventory-service-production';

-- ============================================================
-- 24. SAMPLE PIPELINE STAGES
-- ============================================================

INSERT INTO pipeline_stages (
    run_id,
    stage_name,
    sequence_number,
    status,
    attempt_count,
    duration_ms
)
SELECT
    run_id,
    stage_name,
    sequence_number,
    'SUCCESS',
    1,
    duration_ms
FROM pipeline_runs
CROSS JOIN (
    VALUES
    ('checkout', 1, 1200),
    ('build', 2, 8500),
    ('test', 3, 15000),
    ('package', 4, 2100),
    ('deploy', 5, 6000)
) AS stages(stage_name, sequence_number, duration_ms)
WHERE build_number IN (101, 103);

INSERT INTO pipeline_stages (
    run_id,
    stage_name,
    sequence_number,
    status,
    attempt_count,
    error_message
)
SELECT
    run_id,
    'test',
    3,
    'FAILED',
    2,
    'Integration test failure.'
FROM pipeline_runs
WHERE build_number = 102;

-- ============================================================
-- 25. SAMPLE TEST RESULTS
-- ============================================================

INSERT INTO pipeline_test_results (
    run_id,
    test_suite,
    total_tests,
    passed_tests,
    failed_tests,
    skipped_tests
)
SELECT
    run_id,
    'unit-tests',
    42,
    42,
    0,
    0
FROM pipeline_runs
WHERE build_number IN (101, 103);

INSERT INTO pipeline_test_results (
    run_id,
    test_suite,
    total_tests,
    passed_tests,
    failed_tests,
    skipped_tests
)
SELECT
    run_id,
    'integration-tests',
    20,
    17,
    3,
    0
FROM pipeline_runs
WHERE build_number = 102;

-- ============================================================
-- 26. SAMPLE DEPLOYMENT APPROVALS
-- ============================================================

INSERT INTO deployment_approvals (
    run_id,
    approver,
    approver_role,
    decision,
    comments
)
SELECT
    run_id,
    'release-manager',
    'PRODUCTION_APPROVER',
    'APPROVED',
    'Production deployment authorized.'
FROM pipeline_runs
WHERE build_number = 103;

-- ============================================================
-- 27. SAMPLE EXECUTION EVENTS
-- ============================================================

INSERT INTO pipeline_events (
    run_id,
    event_type,
    event_description,
    actor,
    event_data
)
SELECT
    run_id,
    'BUILD_CREATED',
    'Pipeline execution record created.',
    triggered_by,
    jsonb_build_object(
        'build_number', build_number,
        'source_commit', source_commit
    )
FROM pipeline_runs;

-- ============================================================
-- 28. LIBRARY RELEASE REPORT
-- ============================================================

CREATE OR REPLACE VIEW library_release_report AS
SELECT
    l.library_name,
    r.version,
    r.commit_hash,
    r.release_status,
    r.tested_at,
    r.approved_at,
    COUNT(DISTINCT m.module_id) AS module_count,
    COUNT(DISTINCT s.step_id) AS reusable_step_count
FROM shared_libraries l
JOIN library_releases r
    ON r.library_id = l.library_id
LEFT JOIN library_modules m
    ON m.release_id = r.release_id
LEFT JOIN reusable_steps s
    ON s.release_id = r.release_id
GROUP BY
    l.library_name,
    r.release_id,
    r.version,
    r.commit_hash,
    r.release_status,
    r.tested_at,
    r.approved_at;

-- ============================================================
-- 29. PIPELINE EXECUTION REPORT
-- ============================================================

CREATE OR REPLACE VIEW pipeline_execution_report AS
SELECT
    p.pipeline_name,
    r.run_id,
    r.build_number,
    r.status,
    repo.repository_name,
    l.library_name,
    lr.version AS library_version,
    r.triggered_by,
    r.source_commit,
    COUNT(DISTINCT s.stage_id) AS stage_count,
    COUNT(DISTINCT s.stage_id)
        FILTER (WHERE s.status = 'SUCCESS') AS successful_stages,
    COUNT(DISTINCT s.stage_id)
        FILTER (WHERE s.status = 'FAILED') AS failed_stages,
    r.created_at,
    r.finished_at
FROM pipeline_runs r
JOIN pipeline_definitions p
    ON p.pipeline_id = r.pipeline_id
JOIN repositories repo
    ON repo.repository_id = p.repository_id
JOIN library_releases lr
    ON lr.release_id = r.release_id
JOIN shared_libraries l
    ON l.library_id = lr.library_id
LEFT JOIN pipeline_stages s
    ON s.run_id = r.run_id
GROUP BY
    p.pipeline_name,
    r.run_id,
    r.build_number,
    r.status,
    repo.repository_name,
    l.library_name,
    lr.version,
    r.triggered_by,
    r.source_commit,
    r.created_at,
    r.finished_at;

-- ============================================================
-- 30. RETRIEVAL QUERIES
-- ============================================================

-- Retrieve approved shared library releases.
SELECT *
FROM library_release_report
WHERE release_status = 'APPROVED'
ORDER BY library_name, version;

-- Retrieve all reusable pipeline steps.
SELECT
    l.library_name,
    r.version,
    s.step_name,
    s.description,
    s.idempotent,
    s.requires_credentials
FROM reusable_steps s
JOIN library_releases r
    ON r.release_id = s.release_id
JOIN shared_libraries l
    ON l.library_id = r.library_id
ORDER BY l.library_name, r.version, s.step_name;

-- ============================================================
-- 31. AGGREGATION AND REPORTING
-- ============================================================

SELECT
    status,
    COUNT(*) AS execution_count
FROM pipeline_runs
GROUP BY status
ORDER BY status;

SELECT
    p.pipeline_name,
    COUNT(r.run_id) AS total_runs,
    COUNT(r.run_id) FILTER (
        WHERE r.status = 'SUCCESS'
    ) AS successful_runs,
    COUNT(r.run_id) FILTER (
        WHERE r.status = 'FAILED'
    ) AS failed_runs
FROM pipeline_definitions p
LEFT JOIN pipeline_runs r
    ON r.pipeline_id = p.pipeline_id
GROUP BY p.pipeline_id, p.pipeline_name
ORDER BY p.pipeline_name;

-- ============================================================
-- 32. CTE: FAILURE ANALYSIS
-- ============================================================

WITH failed_stages AS (
    SELECT
        run_id,
        stage_name,
        error_message,
        attempt_count
    FROM pipeline_stages
    WHERE status = 'FAILED'
),
failure_summary AS (
    SELECT
        stage_name,
        COUNT(*) AS failure_count,
        SUM(attempt_count) AS total_attempts
    FROM failed_stages
    GROUP BY stage_name
)
SELECT
    stage_name,
    failure_count,
    total_attempts
FROM failure_summary
ORDER BY failure_count DESC;

-- ============================================================
-- 33. RELEASE ELIGIBILITY REPORT
-- ============================================================

SELECT
    r.run_id,
    r.build_number,
    eligibility.*
FROM pipeline_runs r
CROSS JOIN LATERAL
    evaluate_pipeline_eligibility(r.run_id) AS eligibility
ORDER BY r.run_id;

-- ============================================================
-- 34. WORKFLOW PROCESSING
-- ============================================================

-- Create and start a fresh staging execution.
-- The procedure locks the run while validating its release.

DO $$
DECLARE
    v_pipeline_id BIGINT;
    v_release_id BIGINT;
    v_run_id BIGINT;
BEGIN
    SELECT
        pipeline_id,
        release_id
    INTO
        v_pipeline_id,
        v_release_id
    FROM pipeline_definitions
    WHERE pipeline_name = 'payment-service-ci';

    INSERT INTO pipeline_runs (
        pipeline_id,
        release_id,
        build_number,
        triggered_by,
        source_commit,
        status
    )
    VALUES (
        v_pipeline_id,
        v_release_id,
        104,
        'automation-service',
        'f1a2b3c4d5e6789',
        'CREATED'
    )
    RETURNING run_id INTO v_run_id;

    CALL start_pipeline_run(v_run_id);

    INSERT INTO pipeline_stages (
        run_id,
        stage_name,
        sequence_number,
        status,
        attempt_count
    )
    VALUES
        (v_run_id, 'checkout', 1, 'RUNNING', 1),
        (v_run_id, 'build', 2, 'PENDING', 0),
        (v_run_id, 'test', 3, 'PENDING', 0),
        (v_run_id, 'package', 4, 'PENDING', 0),
        (v_run_id, 'deploy', 5, 'PENDING', 0);

    UPDATE pipeline_stages
    SET status = 'SUCCESS',
        finished_at = NOW(),
        duration_ms = 1200
    WHERE run_id = v_run_id
      AND stage_name = 'checkout';

    UPDATE pipeline_runs
    SET status = 'SUCCESS',
        finished_at = NOW()
    WHERE run_id = v_run_id;

    RAISE NOTICE 'Created and completed pipeline run %.', v_run_id;
END;
$$;

-- ============================================================
-- 35. VALIDATION QUERIES
-- ============================================================

-- Find pipeline definitions using unapproved libraries.
SELECT
    p.pipeline_name,
    l.library_name,
    r.version,
    r.release_status
FROM pipeline_definitions p
JOIN library_releases r
    ON r.release_id = p.release_id
JOIN shared_libraries l
    ON l.library_id = r.library_id
WHERE p.enabled = TRUE
  AND r.release_status <> 'APPROVED';

-- Find successful executions with failed automated tests.
SELECT
    r.run_id,
    r.build_number,
    t.test_suite,
    t.failed_tests
FROM pipeline_runs r
JOIN pipeline_test_results t
    ON t.run_id = r.run_id
WHERE r.status = 'SUCCESS'
  AND t.failed_tests > 0;

-- Find runs with incomplete stages.
SELECT
    r.run_id,
    r.build_number,
    s.stage_name,
    s.status
FROM pipeline_runs r
JOIN pipeline_stages s
    ON s.run_id = r.run_id
WHERE r.status = 'SUCCESS'
  AND s.status NOT IN ('SUCCESS', 'SKIPPED');

-- ============================================================
-- 36. TRANSACTION FAILURE HANDLING EXAMPLE
-- ============================================================

-- This transaction demonstrates atomic creation.
-- The savepoint permits a failed optional insertion to be rolled back.

SAVEPOINT optional_pipeline_event;

INSERT INTO pipeline_events (
    run_id,
    event_type,
    event_description,
    actor
)
SELECT
    run_id,
    'AUDIT_NOTE',
    'Optional audit annotation.',
    'system'
FROM pipeline_runs
WHERE build_number = 101;

ROLLBACK TO SAVEPOINT optional_pipeline_event;

RELEASE SAVEPOINT optional_pipeline_event;

-- ============================================================
-- 37. AUDIT HISTORY
-- ============================================================

SELECT
    event_id,
    run_id,
    event_type,
    event_description,
    actor,
    created_at
FROM pipeline_events
ORDER BY created_at DESC, event_id DESC;

-- ============================================================
-- 38. FINAL DATABASE VALIDATION
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM library_releases
        WHERE version = '2.1.0'
          AND release_status = 'APPROVED'
    ) THEN
        RAISE EXCEPTION 'Approved shared library fixture is missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM reusable_steps
        WHERE step_name = 'buildApplication'
    ) THEN
        RAISE EXCEPTION 'Reusable build step is missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pipeline_definitions
    ) THEN
        RAISE EXCEPTION 'Pipeline definitions are missing.';
    END IF;

    RAISE NOTICE 'Database validation completed successfully.';
END;
$$;

COMMIT;
