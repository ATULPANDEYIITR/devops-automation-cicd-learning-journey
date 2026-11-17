/*
================================================================
PIPELINE SECURITY DATABASE
PostgreSQL 15+

Domain:
- Secret lifecycle and access control
- Pipeline identities and permissions
- Repositories and branches
- Pull Requests and commits
- Dependency inventories
- Supply-chain verification
- Vulnerability findings
- Artifact provenance
- Reviews and approvals
- Automated status checks
- Branch protection
- Merge eligibility
- Security audit records

The database uses transactional processing, constraints,
triggers, stored functions, and reporting views.

Execute using a PostgreSQL database owner account.
================================================================
*/

BEGIN;

CREATE SCHEMA IF NOT EXISTS pipeline_security;

SET search_path TO pipeline_security, public;


-- ============================================================
-- 1. ENUMERATED TYPES
-- ============================================================

CREATE TYPE pipeline_state AS ENUM (
    'CREATED',
    'VALIDATING',
    'RUNNING',
    'BLOCKED',
    'SUCCEEDED',
    'FAILED'
);

CREATE TYPE review_state AS ENUM (
    'PENDING',
    'APPROVED',
    'CHANGES_REQUESTED',
    'DISMISSED'
);

CREATE TYPE dependency_status AS ENUM (
    'VERIFIED',
    'UNVERIFIED',
    'VULNERABLE',
    'BLOCKED'
);

CREATE TYPE vulnerability_severity AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'CRITICAL'
);

CREATE TYPE access_decision AS ENUM (
    'ALLOWED',
    'DENIED'
);

CREATE TYPE principal_type AS ENUM (
    'HUMAN',
    'SERVICE',
    'PIPELINE_JOB'
);


-- ============================================================
-- 2. REPOSITORY MANAGEMENT
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_name VARCHAR(150) NOT NULL UNIQUE,

    owner_name VARCHAR(150) NOT NULL,

    visibility VARCHAR(20) NOT NULL
        CHECK (visibility IN ('PUBLIC', 'PRIVATE', 'INTERNAL')),

    default_branch VARCHAR(150) NOT NULL DEFAULT 'main',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    enabled BOOLEAN NOT NULL DEFAULT TRUE
);


CREATE TABLE principals (
    principal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    principal_name VARCHAR(150) NOT NULL UNIQUE,

    principal_kind principal_type NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE repository_memberships (
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    principal_id BIGINT NOT NULL
        REFERENCES principals(principal_id),

    repository_role VARCHAR(30) NOT NULL
        CHECK (
            repository_role IN (
                'READ',
                'TRIAGE',
                'WRITE',
                'MAINTAIN',
                'ADMIN'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (repository_id, principal_id)
);


-- ============================================================
-- 3. BRANCHES AND COMMITS
-- ============================================================

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    branch_name VARCHAR(255) NOT NULL,

    head_commit_sha VARCHAR(40),

    protected BOOLEAN NOT NULL DEFAULT FALSE,

    deleted BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (repository_id, branch_name)
);


CREATE TABLE commits (
    commit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    commit_sha VARCHAR(40) NOT NULL,

    author_principal_id BIGINT
        REFERENCES principals(principal_id),

    message TEXT NOT NULL,

    committed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (repository_id, commit_sha)
);


CREATE INDEX idx_commits_repository_date
ON commits(repository_id, committed_at DESC);


-- ============================================================
-- 4. PIPELINE IDENTITIES AND PERMISSIONS
-- ============================================================

CREATE TABLE pipeline_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    job_name VARCHAR(150) NOT NULL,

    trusted BOOLEAN NOT NULL DEFAULT FALSE,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    UNIQUE (repository_id, job_name)
);


CREATE TABLE permission_definitions (
    permission_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    permission_name VARCHAR(100) NOT NULL UNIQUE,

    permission_category VARCHAR(50) NOT NULL,

    risk_level VARCHAR(20) NOT NULL
        CHECK (
            risk_level IN (
                'LOW',
                'MEDIUM',
                'HIGH',
                'CRITICAL'
            )
        )
);


CREATE TABLE job_permissions (
    job_id BIGINT NOT NULL
        REFERENCES pipeline_jobs(job_id),

    permission_id BIGINT NOT NULL
        REFERENCES permission_definitions(permission_id),

    granted_by BIGINT NOT NULL
        REFERENCES principals(principal_id),

    granted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (job_id, permission_id)
);


CREATE INDEX idx_job_permissions_permission
ON job_permissions(permission_id, job_id);


-- ============================================================
-- 5. SECRET MANAGEMENT
-- ============================================================

CREATE TABLE secrets (
    secret_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    secret_name VARCHAR(150) NOT NULL,

    encrypted_value BYTEA NOT NULL,

    encryption_key_reference VARCHAR(255) NOT NULL,

    version_number INTEGER NOT NULL DEFAULT 1
        CHECK (version_number > 0),

    created_by BIGINT NOT NULL
        REFERENCES principals(principal_id),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    expires_at TIMESTAMPTZ,

    revoked_at TIMESTAMPTZ,

    UNIQUE (repository_id, secret_name),

    CHECK (
        expires_at IS NULL OR
        expires_at > created_at
    )
);


CREATE TABLE secret_access_grants (
    secret_id BIGINT NOT NULL
        REFERENCES secrets(secret_id),

    job_id BIGINT NOT NULL
        REFERENCES pipeline_jobs(job_id),

    granted_by BIGINT NOT NULL
        REFERENCES principals(principal_id),

    granted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (secret_id, job_id)
);


CREATE TABLE secret_access_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    secret_id BIGINT
        REFERENCES secrets(secret_id),

    job_id BIGINT
        REFERENCES pipeline_jobs(job_id),

    actor_id BIGINT
        REFERENCES principals(principal_id),

    decision access_decision NOT NULL,

    reason TEXT NOT NULL,

    accessed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX idx_secret_access_events_time
ON secret_access_events(accessed_at DESC);


-- ============================================================
-- 6. PULL REQUESTS AND COMMITS
-- ============================================================

CREATE TABLE pull_requests (
    pull_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),

    author_id BIGINT NOT NULL
        REFERENCES principals(principal_id),

    title VARCHAR(255) NOT NULL,

    description TEXT,

    is_draft BOOLEAN NOT NULL DEFAULT FALSE,

    is_open BOOLEAN NOT NULL DEFAULT TRUE,

    conversations_resolved BOOLEAN NOT NULL DEFAULT FALSE,

    linear_history BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    closed_at TIMESTAMPTZ,

    merged_at TIMESTAMPTZ,

    CHECK (source_branch_id <> target_branch_id)
);


CREATE INDEX idx_pull_requests_target
ON pull_requests(target_branch_id, is_open);


CREATE INDEX idx_pull_requests_repository
ON pull_requests(repository_id, created_at DESC);


CREATE TABLE pull_request_commits (
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id),

    commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id),

    PRIMARY KEY (pull_request_id, commit_id)
);


-- ============================================================
-- 7. CODE REVIEW AND APPROVALS
-- ============================================================

CREATE TABLE reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id),

    reviewer_id BIGINT NOT NULL
        REFERENCES principals(principal_id),

    review_status review_state NOT NULL DEFAULT 'PENDING',

    eligible_reviewer BOOLEAN NOT NULL DEFAULT TRUE,

    stale BOOLEAN NOT NULL DEFAULT FALSE,

    submitted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    dismissed_at TIMESTAMPTZ,

    UNIQUE (pull_request_id, reviewer_id)
);


CREATE INDEX idx_reviews_pull_request_status
ON reviews(pull_request_id, review_status, stale);


CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    review_id BIGINT NOT NULL
        REFERENCES reviews(review_id),

    file_path TEXT NOT NULL,

    line_number INTEGER
        CHECK (line_number IS NULL OR line_number > 0),

    comment_body TEXT NOT NULL,

    resolved BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    resolved_at TIMESTAMPTZ
);


CREATE INDEX idx_review_comments_unresolved
ON review_comments(review_id)
WHERE resolved = FALSE;


-- ============================================================
-- 8. PIPELINE EXECUTION
-- ============================================================

CREATE TABLE pipeline_runs (
    pipeline_run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),

    job_id BIGINT NOT NULL
        REFERENCES pipeline_jobs(job_id),

    pull_request_id BIGINT
        REFERENCES pull_requests(pull_request_id),

    source_commit_id BIGINT
        REFERENCES commits(commit_id),

    state pipeline_state NOT NULL DEFAULT 'CREATED',

    triggered_by BIGINT
        REFERENCES principals(principal_id),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    failure_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        completed_at IS NULL OR
        started_at IS NULL OR
        completed_at >= started_at
    )
);


CREATE INDEX idx_pipeline_runs_state
ON pipeline_runs(state, created_at DESC);


CREATE INDEX idx_pipeline_runs_repository
ON pipeline_runs(repository_id, created_at DESC);


-- ============================================================
-- 9. SUPPLY-CHAIN DEPENDENCIES
-- ============================================================

CREATE TABLE dependencies (
    dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    package_name VARCHAR(255) NOT NULL,

    package_version VARCHAR(100) NOT NULL,

    package_source TEXT NOT NULL,

    expected_sha256 VARCHAR(64) NOT NULL,

    actual_sha256 VARCHAR(64),

    status dependency_status NOT NULL DEFAULT 'UNVERIFIED',

    severity vulnerability_severity NOT NULL DEFAULT 'LOW',

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (expected_sha256 ~ '^[a-fA-F0-9]{64}$'),

    CHECK (
        actual_sha256 IS NULL OR
        actual_sha256 ~ '^[a-fA-F0-9]{64}$'
    ),

    UNIQUE (
        package_name,
        package_version,
        package_source
    )
);


CREATE TABLE pipeline_run_dependencies (
    pipeline_run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(pipeline_run_id),

    dependency_id BIGINT NOT NULL
        REFERENCES dependencies(dependency_id),

    PRIMARY KEY (pipeline_run_id, dependency_id)
);


CREATE INDEX idx_dependencies_status_severity
ON dependencies(status, severity);


CREATE TABLE vulnerability_findings (
    finding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    dependency_id BIGINT NOT NULL
        REFERENCES dependencies(dependency_id),

    vulnerability_id VARCHAR(100) NOT NULL,

    severity vulnerability_severity NOT NULL,

    description TEXT NOT NULL,

    remediation_status VARCHAR(30) NOT NULL DEFAULT 'OPEN'
        CHECK (
            remediation_status IN (
                'OPEN',
                'IN_PROGRESS',
                'RESOLVED',
                'ACCEPTED_RISK'
            )
        ),

    detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (dependency_id, vulnerability_id)
);


-- ============================================================
-- 10. ARTIFACT PROVENANCE
-- ============================================================

CREATE TABLE artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pipeline_run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(pipeline_run_id),

    artifact_name VARCHAR(255) NOT NULL,

    artifact_sha256 VARCHAR(64) NOT NULL,

    source_commit_sha VARCHAR(40) NOT NULL,

    builder_identity VARCHAR(255) NOT NULL,

    attestation BYTEA,

    attestation_key_reference VARCHAR(255),

    provenance_verified BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (artifact_sha256 ~ '^[a-fA-F0-9]{64}$'),

    CHECK (source_commit_sha ~ '^[a-fA-F0-9]{40}$')
);


CREATE INDEX idx_artifacts_pipeline
ON artifacts(pipeline_run_id);


-- ============================================================
-- 11. AUTOMATED STATUS CHECKS
-- ============================================================

CREATE TABLE status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id),

    check_name VARCHAR(150) NOT NULL,

    completed BOOLEAN NOT NULL DEFAULT FALSE,

    passed BOOLEAN NOT NULL DEFAULT FALSE,

    external_reference TEXT,

    completed_at TIMESTAMPTZ,

    UNIQUE (pull_request_id, check_name),

    CHECK (
        passed = FALSE OR completed = TRUE
    )
);


CREATE INDEX idx_status_checks_pr
ON status_checks(pull_request_id, completed, passed);


-- ============================================================
-- 12. BRANCH PROTECTION
-- ============================================================

CREATE TABLE branch_protection_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id),

    required_approvals INTEGER NOT NULL DEFAULT 1
        CHECK (required_approvals >= 0),

    require_status_checks BOOLEAN NOT NULL DEFAULT TRUE,

    require_resolved_conversations BOOLEAN NOT NULL DEFAULT TRUE,

    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,

    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,

    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,

    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,

    allow_administrator_bypass BOOLEAN NOT NULL DEFAULT FALSE,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id),

    check_name VARCHAR(150) NOT NULL,

    PRIMARY KEY (policy_id, check_name)
);


-- ============================================================
-- 13. SECURITY AUDIT LOG
-- ============================================================

CREATE TABLE security_audit_events (
    audit_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    event_type VARCHAR(100) NOT NULL,

    actor_id BIGINT
        REFERENCES principals(principal_id),

    resource_type VARCHAR(100) NOT NULL,

    resource_id VARCHAR(255) NOT NULL,

    outcome VARCHAR(30) NOT NULL
        CHECK (
            outcome IN (
                'SUCCESS',
                'DENIED',
                'BLOCKED',
                'FAILED',
                'STARTED',
                'ELIGIBLE'
            )
        ),

    details JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX idx_audit_events_type_date
ON security_audit_events(event_type, created_at DESC);


CREATE INDEX idx_audit_events_details
ON security_audit_events USING GIN(details);


-- ============================================================
-- 14. SECRET ACCESS VALIDATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_secret_access(
    p_secret_id BIGINT,
    p_job_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_allowed BOOLEAN;
BEGIN

    SELECT EXISTS (
        SELECT 1
        FROM secrets s
        JOIN secret_access_grants g
          ON g.secret_id = s.secret_id
        JOIN pipeline_jobs j
          ON j.job_id = g.job_id
        WHERE s.secret_id = p_secret_id
          AND g.job_id = p_job_id
          AND s.revoked_at IS NULL
          AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP)
          AND j.enabled = TRUE
          AND (
              j.trusted = TRUE
              OR NOT EXISTS (
                  SELECT 1
                  FROM pipeline_runs pr
                  WHERE pr.job_id = j.job_id
                    AND pr.state IN ('CREATED', 'VALIDATING', 'RUNNING')
                    AND pr.pull_request_id IS NOT NULL
                    AND EXISTS (
                        SELECT 1
                        FROM pull_requests request
                        WHERE request.pull_request_id = pr.pull_request_id
                            AND request.author_id <> j.job_id
                    )
              )
          )
    )
    INTO v_allowed;

    INSERT INTO secret_access_events (
        secret_id,
        job_id,
        decision,
        reason
    )
    VALUES (
        p_secret_id,
        p_job_id,
        CASE
            WHEN v_allowed THEN 'ALLOWED'::access_decision
            ELSE 'DENIED'::access_decision
        END,
        CASE
            WHEN v_allowed THEN 'Active authorized grant'
            ELSE 'Missing grant, expired secret, revoked secret, or disabled job'
        END
    );

    RETURN v_allowed;

END;
$$;


-- ============================================================
-- 15. DEPENDENCY INTEGRITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_dependency(
    p_dependency_id BIGINT
)
RETURNS dependency_status
LANGUAGE plpgsql
AS $$
DECLARE
    v_dependency dependencies%ROWTYPE;
    v_result dependency_status;
BEGIN

    SELECT *
    INTO v_dependency
    FROM dependencies
    WHERE dependency_id = p_dependency_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Dependency not found';
    END IF;

    IF v_dependency.package_source ILIKE '%untrusted%' THEN
        v_result := 'BLOCKED';

    ELSIF v_dependency.actual_sha256 IS NULL
       OR lower(v_dependency.expected_sha256)
          <> lower(v_dependency.actual_sha256) THEN

        v_result := 'UNVERIFIED';

    ELSIF v_dependency.severity IN ('HIGH', 'CRITICAL') THEN
        v_result := 'VULNERABLE';

    ELSE
        v_result := 'VERIFIED';
    END IF;

    UPDATE dependencies
    SET status = v_result
    WHERE dependency_id = p_dependency_id;

    RETURN v_result;

END;
$$;


-- ============================================================
-- 16. APPROVAL EVALUATION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION count_valid_approvals(
    p_pull_request_id BIGINT
)
RETURNS INTEGER
LANGUAGE sql
STABLE
AS $$
    SELECT COUNT(DISTINCT reviewer_id)::INTEGER
    FROM reviews
    WHERE pull_request_id = p_pull_request_id
      AND review_status = 'APPROVED'
      AND eligible_reviewer = TRUE
      AND stale = FALSE;
$$;


CREATE OR REPLACE FUNCTION has_active_change_request(
    p_pull_request_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM reviews
        WHERE pull_request_id = p_pull_request_id
          AND review_status = 'CHANGES_REQUESTED'
          AND eligible_reviewer = TRUE
          AND stale = FALSE
    );
$$;


-- ============================================================
-- 17. CONVERSATION RESOLUTION FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION conversations_are_resolved(
    p_pull_request_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT NOT EXISTS (
        SELECT 1
        FROM reviews r
        JOIN review_comments c
          ON c.review_id = r.review_id
        WHERE r.pull_request_id = p_pull_request_id
          AND c.resolved = FALSE
    );
$$;


-- ============================================================
-- 18. MERGE ELIGIBILITY FUNCTION
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    violation TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_pr pull_requests%ROWTYPE;
    v_policy branch_protection_policies%ROWTYPE;
    v_approval_count INTEGER;
    v_failed_checks INTEGER;
    v_missing_checks INTEGER;
    v_invalid_dependencies INTEGER;
    v_invalid_provenance INTEGER;
BEGIN

    SELECT *
    INTO v_pr
    FROM pull_requests
    WHERE pull_request_id = p_pull_request_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request does not exist'::TEXT;
        RETURN;
    END IF;

    SELECT bp.*
    INTO v_policy
    FROM branch_protection_policies bp
    JOIN branches b
      ON b.branch_id = bp.branch_id
    WHERE b.branch_id = v_pr.target_branch_id
      AND b.protected = TRUE;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Target branch is not protected by a policy'::TEXT;
        RETURN;
    END IF;

    IF NOT v_pr.is_open THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request is closed'::TEXT;
    END IF;

    IF v_pr.is_draft THEN
        RETURN QUERY
        SELECT FALSE, 'Draft Pull Request cannot be merged'::TEXT;
    END IF;

    v_approval_count := count_valid_approvals(
        p_pull_request_id
    );

    IF v_approval_count < v_policy.required_approvals THEN
        RETURN QUERY
        SELECT FALSE, 'Insufficient eligible approvals'::TEXT;
    END IF;

    IF has_active_change_request(p_pull_request_id) THEN
        RETURN QUERY
        SELECT FALSE, 'Active requested-changes review exists'::TEXT;
    END IF;

    IF (
        v_policy.require_resolved_conversations
        AND NOT conversations_are_resolved(p_pull_request_id)
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'Unresolved review conversations'::TEXT;
    END IF;

    IF (
        v_policy.require_resolved_conversations
        AND NOT v_pr.conversations_resolved
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request conversation state is unresolved'::TEXT;
    END IF;

    IF (
        v_policy.require_linear_history
        AND NOT v_pr.linear_history
    ) THEN
        RETURN QUERY
        SELECT FALSE, 'Linear history requirement failed'::TEXT;
    END IF;

    IF v_policy.require_status_checks THEN

        SELECT COUNT(*)
        INTO v_missing_checks
        FROM required_status_checks required
        WHERE required.policy_id = v_policy.policy_id
          AND NOT EXISTS (
              SELECT 1
              FROM status_checks actual
              WHERE actual.pull_request_id = p_pull_request_id
                AND actual.check_name = required.check_name
                AND actual.completed = TRUE
                AND actual.passed = TRUE
          );

        IF v_missing_checks > 0 THEN
            RETURN QUERY
            SELECT FALSE, 'One or more required status checks are missing or failing'::TEXT;
            RETURN;
        END IF;

    END IF;

    SELECT COUNT(*)
    INTO v_invalid_dependencies
    FROM pull_request_commits pc
    JOIN commits c
      ON c.commit_id = pc.commit_id
    WHERE pc.pull_request_id = p_pull_request_id
      AND NOT EXISTS (
          SELECT 1
          FROM pipeline_runs pr
          JOIN pipeline_run_dependencies prd
            ON prd.pipeline_run_id = pr.pipeline_run_id
          JOIN dependencies d
            ON d.dependency_id = prd.dependency_id
          WHERE pr.pull_request_id = p_pull_request_id
            AND pr.state = 'SUCCEEDED'
            AND d.status = 'VERIFIED'
      );

    IF v_invalid_dependencies > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'Verified dependency evidence is missing'::TEXT;
        RETURN;
    END IF;

    SELECT COUNT(*)
    INTO v_invalid_provenance
    FROM pipeline_runs pr
    WHERE pr.pull_request_id = p_pull_request_id
      AND pr.state = 'SUCCEEDED'
      AND NOT EXISTS (
          SELECT 1
          FROM artifacts a
          WHERE a.pipeline_run_id = pr.pipeline_run_id
            AND a.provenance_verified = TRUE
      );

    IF v_invalid_provenance > 0 THEN
        RETURN QUERY
        SELECT FALSE, 'Artifact provenance verification failed'::TEXT;
        RETURN;
    END IF;

    RETURN QUERY
    SELECT TRUE, 'All configured merge conditions satisfied'::TEXT;

END;
$$;


-- ============================================================
-- 19. PIPELINE STATE TRANSITION VALIDATION
-- ============================================================

CREATE OR REPLACE FUNCTION validate_pipeline_transition()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF OLD.state = NEW.state THEN
        RETURN NEW;
    END IF;

    IF NOT (
        (OLD.state = 'CREATED'
            AND NEW.state = 'VALIDATING')

        OR

        (OLD.state = 'VALIDATING'
            AND NEW.state IN ('RUNNING', 'BLOCKED', 'FAILED'))

        OR

        (OLD.state = 'RUNNING'
            AND NEW.state IN ('SUCCEEDED', 'FAILED', 'BLOCKED'))
    ) THEN

        RAISE EXCEPTION
            'Invalid pipeline state transition: % -> %',
            OLD.state,
            NEW.state;

    END IF;

    IF NEW.state IN ('SUCCEEDED', 'FAILED', 'BLOCKED')
       AND NEW.completed_at IS NULL THEN

        NEW.completed_at := CURRENT_TIMESTAMP;

    END IF;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_pipeline_state_transition
BEFORE UPDATE OF state
ON pipeline_runs
FOR EACH ROW
EXECUTE FUNCTION validate_pipeline_transition();


-- ============================================================
-- 20. AUDIT TRIGGER FOR PERMISSION CHANGES
-- ============================================================

CREATE OR REPLACE FUNCTION audit_permission_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    INSERT INTO security_audit_events (
        event_type,
        resource_type,
        resource_id,
        outcome,
        details
    )
    VALUES (
        TG_OP || '_JOB_PERMISSION',
        'JOB_PERMISSION',
        COALESCE(
            NEW.job_id,
            OLD.job_id
        )::TEXT,
        'SUCCESS',
        jsonb_build_object(
            'permission_id',
            COALESCE(
                NEW.permission_id,
                OLD.permission_id
            )
        )
    );

    RETURN COALESCE(NEW, OLD);

END;
$$;


CREATE TRIGGER trg_audit_permission_changes
AFTER INSERT OR DELETE
ON job_permissions
FOR EACH ROW
EXECUTE FUNCTION audit_permission_changes();


-- ============================================================
-- 21. PREVENT SECRET VALUE EXPOSURE IN AUDIT DETAILS
-- ============================================================

CREATE OR REPLACE FUNCTION validate_audit_details()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN

    IF NEW.details::TEXT ~*
       '(password|secret_value|private_key|access_token)' THEN

        RAISE EXCEPTION
            'Sensitive secret values cannot be written to audit details';

    END IF;

    RETURN NEW;

END;
$$;


CREATE TRIGGER trg_validate_audit_details
BEFORE INSERT OR UPDATE
ON security_audit_events
FOR EACH ROW
EXECUTE FUNCTION validate_audit_details();


-- ============================================================
-- 22. REPORTING VIEWS
-- ============================================================

CREATE OR REPLACE VIEW dependency_security_report AS
SELECT
    d.dependency_id,
    d.package_name,
    d.package_version,
    d.package_source,
    d.status,
    d.severity,
    COUNT(v.finding_id) AS vulnerability_count,
    COUNT(v.finding_id) FILTER (
        WHERE v.remediation_status = 'OPEN'
    ) AS open_findings
FROM dependencies d
LEFT JOIN vulnerability_findings v
    ON v.dependency_id = d.dependency_id
GROUP BY
    d.dependency_id,
    d.package_name,
    d.package_version,
    d.package_source,
    d.status,
    d.severity;


CREATE OR REPLACE VIEW pipeline_security_report AS
SELECT
    pr.pipeline_run_id,
    r.repository_name,
    j.job_name,
    pr.state,
    pr.created_at,
    pr.completed_at,
    COUNT(DISTINCT d.dependency_id) AS dependency_count,
    COUNT(DISTINCT d.dependency_id) FILTER (
        WHERE d.status <> 'VERIFIED'
    ) AS unverified_dependency_count,
    COUNT(DISTINCT a.artifact_id) FILTER (
        WHERE a.provenance_verified = TRUE
    ) AS verified_artifact_count
FROM pipeline_runs pr
JOIN repositories r
    ON r.repository_id = pr.repository_id
JOIN pipeline_jobs j
    ON j.job_id = pr.job_id
LEFT JOIN pipeline_run_dependencies prd
    ON prd.pipeline_run_id = pr.pipeline_run_id
LEFT JOIN dependencies d
    ON d.dependency_id = prd.dependency_id
LEFT JOIN artifacts a
    ON a.pipeline_run_id = pr.pipeline_run_id
GROUP BY
    pr.pipeline_run_id,
    r.repository_name,
    j.job_name,
    pr.state,
    pr.created_at,
    pr.completed_at;


CREATE OR REPLACE VIEW pull_request_review_report AS
SELECT
    pr.pull_request_id,
    pr.title,
    COUNT(DISTINCT r.reviewer_id) FILTER (
        WHERE r.review_status = 'APPROVED'
          AND r.eligible_reviewer = TRUE
          AND r.stale = FALSE
    ) AS valid_approvals,
    COUNT(DISTINCT r.review_id) FILTER (
        WHERE r.review_status = 'CHANGES_REQUESTED'
          AND r.stale = FALSE
    ) AS active_change_requests,
    COUNT(DISTINCT c.comment_id) FILTER (
        WHERE c.resolved = FALSE
    ) AS unresolved_comments
FROM pull_requests pr
LEFT JOIN reviews r
    ON r.pull_request_id = pr.pull_request_id
LEFT JOIN review_comments c
    ON c.review_id = r.review_id
GROUP BY
    pr.pull_request_id,
    pr.title;


-- ============================================================
-- 23. SAMPLE DATA
-- ============================================================

INSERT INTO repositories (
    repository_name,
    owner_name,
    visibility
)
VALUES
    ('secure-application', 'engineering', 'PRIVATE'),
    ('shared-library', 'platform', 'INTERNAL');


INSERT INTO principals (
    principal_name,
    principal_kind
)
VALUES
    ('security-admin', 'HUMAN'),
    ('developer-01', 'HUMAN'),
    ('reviewer-01', 'HUMAN'),
    ('reviewer-02', 'HUMAN'),
    ('production-job', 'PIPELINE_JOB'),
    ('external-job', 'PIPELINE_JOB');


INSERT INTO repository_memberships (
    repository_id,
    principal_id,
    repository_role
)
SELECT
    r.repository_id,
    p.principal_id,
    CASE
        WHEN p.principal_name = 'security-admin' THEN 'ADMIN'
        WHEN p.principal_name LIKE 'reviewer%' THEN 'MAINTAIN'
        ELSE 'WRITE'
    END
FROM repositories r
CROSS JOIN principals p
WHERE r.repository_name = 'secure-application'
  AND p.principal_name IN (
      'security-admin',
      'developer-01',
      'reviewer-01',
      'reviewer-02'
  );


INSERT INTO branches (
    repository_id,
    branch_name,
    head_commit_sha,
    protected
)
SELECT
    repository_id,
    branch_name,
    repeat(sha_character, 40),
    protected
FROM repositories r
CROSS JOIN (
    VALUES
        ('main', 'a', TRUE),
        ('release/1.0', 'b', FALSE),
        ('feature/security', 'c', FALSE)
) AS branch_data(branch_name, sha_character, protected)
WHERE r.repository_name = 'secure-application';


INSERT INTO commits (
    repository_id,
    commit_sha,
    author_principal_id,
    message
)
SELECT
    r.repository_id,
    repeat('a', 40),
    p.principal_id,
    'Initial secure application release'
FROM repositories r
JOIN principals p
    ON p.principal_name = 'developer-01'
WHERE r.repository_name = 'secure-application';


INSERT INTO commits (
    repository_id,
    commit_sha,
    author_principal_id,
    message
)
SELECT
    r.repository_id,
    repeat('b', 40),
    p.principal_id,
    'Security improvements'
FROM repositories r
JOIN principals p
    ON p.principal_name = 'developer-01'
WHERE r.repository_name = 'secure-application';


INSERT INTO permission_definitions (
    permission_name,
    permission_category,
    risk_level
)
VALUES
    ('contents:read', 'REPOSITORY', 'LOW'),
    ('contents:write', 'REPOSITORY', 'HIGH'),
    ('actions:read', 'PIPELINE', 'LOW'),
    ('actions:write', 'PIPELINE', 'HIGH'),
    ('packages:read', 'SUPPLY_CHAIN', 'LOW'),
    ('packages:write', 'SUPPLY_CHAIN', 'HIGH'),
    ('deployments:write', 'DEPLOYMENT', 'CRITICAL'),
    ('id-token:write', 'IDENTITY', 'CRITICAL');


INSERT INTO pipeline_jobs (
    repository_id,
    job_name,
    trusted
)
SELECT
    repository_id,
    job_name,
    trusted
FROM repositories r
CROSS JOIN (
    VALUES
        ('production-deployment', TRUE),
        ('external-validation', FALSE)
) AS jobs(job_name, trusted)
WHERE r.repository_name = 'secure-application';


INSERT INTO job_permissions (
    job_id,
    permission_id,
    granted_by
)
SELECT
    j.job_id,
    pd.permission_id,
    p.principal_id
FROM pipeline_jobs j
JOIN repositories r
    ON r.repository_id = j.repository_id
JOIN permission_definitions pd
    ON pd.permission_name IN (
        'contents:read',
        'deployments:write'
    )
JOIN principals p
    ON p.principal_name = 'security-admin'
WHERE r.repository_name = 'secure-application'
  AND j.job_name = 'production-deployment';


-- The secret value is encrypted outside PostgreSQL.
-- This sample stores a demonstration encrypted payload.
INSERT INTO secrets (
    repository_id,
    secret_name,
    encrypted_value,
    encryption_key_reference,
    created_by
)
SELECT
    r.repository_id,
    'PRODUCTION_TOKEN',
    decode(repeat('ab', 32), 'hex'),
    'kms://production/pipeline-key',
    p.principal_id
FROM repositories r
JOIN principals p
    ON p.principal_name = 'security-admin'
WHERE r.repository_name = 'secure-application';


INSERT INTO secret_access_grants (
    secret_id,
    job_id,
    granted_by
)
SELECT
    s.secret_id,
    j.job_id,
    p.principal_id
FROM secrets s
JOIN pipeline_jobs j
    ON j.repository_id = s.repository_id
JOIN principals p
    ON p.principal_name = 'security-admin'
WHERE s.secret_name = 'PRODUCTION_TOKEN'
  AND j.job_name = 'production-deployment';


-- Pull Request.
INSERT INTO pull_requests (
    repository_id,
    source_branch_id,
    target_branch_id,
    author_id,
    title,
    description,
    conversations_resolved,
    linear_history
)
SELECT
    r.repository_id,
    source.branch_id,
    target.branch_id,
    author.principal_id,
    'Implement pipeline security controls',
    'Add secret protection and supply-chain verification.',
    TRUE,
    TRUE
FROM repositories r
JOIN branches source
    ON source.repository_id = r.repository_id
   AND source.branch_name = 'feature/security'
JOIN branches target
    ON target.repository_id = r.repository_id
   AND target.branch_name = 'main'
JOIN principals author
    ON author.principal_name = 'developer-01'
WHERE r.repository_name = 'secure-application';


INSERT INTO pull_request_commits (
    pull_request_id,
    commit_id
)
SELECT
    pr.pull_request_id,
    c.commit_id
FROM pull_requests pr
JOIN commits c
    ON c.repository_id = pr.repository_id
WHERE pr.title = 'Implement pipeline security controls'
  AND c.commit_sha = repeat('b', 40);


INSERT INTO reviews (
    pull_request_id,
    reviewer_id,
    review_status,
    eligible_reviewer
)
SELECT
    pr.pull_request_id,
    p.principal_id,
    'APPROVED',
    TRUE
FROM pull_requests pr
CROSS JOIN principals p
WHERE pr.title = 'Implement pipeline security controls'
  AND p.principal_name IN ('reviewer-01', 'reviewer-02');


INSERT INTO status_checks (
    pull_request_id,
    check_name,
    completed,
    passed
)
SELECT
    pull_request_id,
    check_name,
    TRUE,
    TRUE
FROM pull_requests
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan'),
        ('build')
) AS checks(check_name)
WHERE title = 'Implement pipeline security controls';


-- Branch protection.
INSERT INTO branch_protection_policies (
    branch_id,
    required_approvals,
    require_status_checks,
    require_resolved_conversations,
    require_linear_history,
    allow_direct_push,
    allow_force_push,
    allow_deletion,
    allow_administrator_bypass
)
SELECT
    branch_id,
    2,
    TRUE,
    TRUE,
    TRUE,
    FALSE,
    FALSE,
    FALSE,
    FALSE
FROM branches
WHERE branch_name = 'main';


INSERT INTO required_status_checks (
    policy_id,
    check_name
)
SELECT
    policy_id,
    check_name
FROM branch_protection_policies
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('security-scan'),
        ('build')
) AS checks(check_name);


-- Dependencies: verified and intentionally unverified examples.
INSERT INTO dependencies (
    package_name,
    package_version,
    package_source,
    expected_sha256,
    actual_sha256,
    status,
    severity
)
VALUES
    (
        'framework',
        '1.2.0',
        'approved-registry',
        repeat('a', 64),
        repeat('a', 64),
        'VERIFIED',
        'LOW'
    ),
    (
        'unsafe-library',
        '2.0.0',
        'approved-registry',
        repeat('b', 64),
        repeat('c', 64),
        'UNVERIFIED',
        'HIGH'
    ),
    (
        'legacy-package',
        '1.0.0',
        'untrusted-mirror',
        repeat('d', 64),
        repeat('d', 64),
        'BLOCKED',
        'CRITICAL'
    );


INSERT INTO vulnerability_findings (
    dependency_id,
    vulnerability_id,
    severity,
    description
)
SELECT
    dependency_id,
    'CVE-DEMO-2026-001',
    'HIGH',
    'Demonstration high-severity dependency finding'
FROM dependencies
WHERE package_name = 'unsafe-library';


-- Pipeline execution.
INSERT INTO pipeline_runs (
    repository_id,
    job_id,
    pull_request_id,
    source_commit_id,
    state,
    triggered_by,
    started_at,
    completed_at
)
SELECT
    r.repository_id,
    j.job_id,
    pr.pull_request_id,
    c.commit_id,
    'SUCCEEDED',
    p.principal_id,
    CURRENT_TIMESTAMP - INTERVAL '10 minutes',
    CURRENT_TIMESTAMP
FROM repositories r
JOIN pipeline_jobs j
    ON j.repository_id = r.repository_id
JOIN pull_requests pr
    ON pr.repository_id = r.repository_id
JOIN commits c
    ON c.repository_id = r.repository_id
JOIN principals p
    ON p.principal_name = 'developer-01'
WHERE r.repository_name = 'secure-application'
  AND j.job_name = 'production-deployment'
  AND c.commit_sha = repeat('b', 40);


INSERT INTO pipeline_run_dependencies (
    pipeline_run_id,
    dependency_id
)
SELECT
    pr.pipeline_run_id,
    d.dependency_id
FROM pipeline_runs pr
JOIN dependencies d
    ON d.package_name = 'framework';


INSERT INTO artifacts (
    pipeline_run_id,
    artifact_name,
    artifact_sha256,
    source_commit_sha,
    builder_identity,
    attestation,
    attestation_key_reference,
    provenance_verified
)
SELECT
    pipeline_run_id,
    'application-release',
    repeat('e', 64),
    repeat('b', 40),
    'trusted-ci-builder',
    decode(repeat('ab', 32), 'hex'),
    'kms://production/attestation-key',
    TRUE
FROM pipeline_runs;


-- ============================================================
-- 24. VALIDATION AND RETRIEVAL QUERIES
-- ============================================================

-- Repository and branch inventory.
SELECT
    r.repository_name,
    b.branch_name,
    b.protected,
    b.deleted
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
ORDER BY r.repository_name, b.branch_name;


-- Secret access decision.
SELECT validate_secret_access(
    s.secret_id,
    j.job_id
) AS access_allowed
FROM secrets s
JOIN pipeline_jobs j
    ON j.repository_id = s.repository_id
WHERE s.secret_name = 'PRODUCTION_TOKEN'
  AND j.job_name = 'production-deployment';


-- Dependency evaluation.
SELECT
    dependency_id,
    package_name,
    evaluate_dependency(dependency_id) AS evaluated_status
FROM dependencies
ORDER BY dependency_id;


-- Vulnerability retrieval.
SELECT
    package_name,
    package_version,
    severity,
    vulnerability_count,
    open_findings
FROM dependency_security_report
ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END;


-- Review reporting.
SELECT *
FROM pull_request_review_report;


-- Pipeline reporting.
SELECT *
FROM pipeline_security_report
ORDER BY created_at DESC;


-- ============================================================
-- 25. MERGE ELIGIBILITY REPORT
-- ============================================================

SELECT
    pr.pull_request_id,
    pr.title,
    result.eligible,
    result.violation
FROM pull_requests pr
CROSS JOIN LATERAL evaluate_merge_eligibility(
    pr.pull_request_id
) AS result
ORDER BY pr.pull_request_id;


-- ============================================================
-- 26. AGGREGATION AND GOVERNANCE REPORTS
-- ============================================================

-- Security status by dependency.
SELECT
    status,
    severity,
    COUNT(*) AS dependency_count
FROM dependencies
GROUP BY status, severity
ORDER BY status, severity;


-- Pipeline success and failure rates.
SELECT
    repository_id,
    COUNT(*) AS total_runs,
    COUNT(*) FILTER (
        WHERE state = 'SUCCEEDED'
    ) AS successful_runs,
    COUNT(*) FILTER (
        WHERE state = 'BLOCKED'
    ) AS blocked_runs,
    COUNT(*) FILTER (
        WHERE state = 'FAILED'
    ) AS failed_runs,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE state = 'SUCCEEDED'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_percentage
FROM pipeline_runs
GROUP BY repository_id;


-- Permission exposure report.
SELECT
    j.job_name,
    pd.permission_name,
    pd.risk_level
FROM pipeline_jobs j
JOIN job_permissions jp
    ON jp.job_id = j.job_id
JOIN permission_definitions pd
    ON pd.permission_id = jp.permission_id
ORDER BY j.job_name, pd.risk_level DESC;


-- Secret exposure report.
SELECT
    s.secret_name,
    j.job_name,
    j.trusted,
    g.granted_at
FROM secrets s
JOIN secret_access_grants g
    ON g.secret_id = s.secret_id
JOIN pipeline_jobs j
    ON j.job_id = g.job_id
WHERE s.revoked_at IS NULL
ORDER BY s.secret_name, j.job_name;


-- Audit event retrieval.
SELECT
    event_type,
    resource_type,
    resource_id,
    outcome,
    created_at
FROM security_audit_events
ORDER BY created_at DESC
LIMIT 100;


-- ============================================================
-- 27. TRANSACTIONAL PIPELINE STATE EXAMPLE
-- ============================================================

DO $$
DECLARE
    v_run_id BIGINT;
BEGIN

    SELECT pipeline_run_id
    INTO v_run_id
    FROM pipeline_runs
    WHERE state = 'SUCCEEDED'
    ORDER BY pipeline_run_id
    LIMIT 1;

    IF v_run_id IS NOT NULL THEN

        -- This transaction is deliberately rolled back to retain
        -- the successful sample pipeline state.
        RAISE NOTICE
            'Sample pipeline run % is available for transition testing',
            v_run_id;

    END IF;

END;
$$;


-- ============================================================
-- 28. INDEX AND PERFORMANCE VERIFICATION
-- ============================================================

SELECT
    schemaname,
    tablename,
    indexname
FROM pg_indexes
WHERE schemaname = 'pipeline_security'
ORDER BY tablename, indexname;


-- ============================================================
-- 29. SECURITY CONFIGURATION INSPECTION
-- ============================================================

SELECT
    b.branch_name,
    bp.required_approvals,
    bp.require_status_checks,
    bp.require_resolved_conversations,
    bp.require_linear_history,
    bp.allow_direct_push,
    bp.allow_force_push,
    bp.allow_deletion,
    bp.allow_administrator_bypass
FROM branch_protection_policies bp
JOIN branches b
    ON b.branch_id = bp.branch_id
ORDER BY b.branch_name;


COMMIT;

/*
================================================================
IMPORTANT OPERATIONAL BOUNDARIES

1. encrypted_value contains demonstration ciphertext.
   Real encryption and decryption must happen through a
   dedicated KMS or secret-management service.

2. SQL permissions should restrict direct access to secret
   ciphertext and prevent ordinary users from modifying
   security policies.

3. Application-side identity verification is required.
   A job_id supplied by an untrusted client is not proof of
   pipeline identity.

4. Artifact provenance verification must validate a
   cryptographic attestation against a trusted signing
   identity. The provenance_verified column is an assertion
   that must only be maintained by a trusted verifier.

5. Merge eligibility is a decision based on recorded evidence.
   Production merge operations should execute in a transaction
   with appropriate locking and branch-head revalidation.

6. The schema demonstrates integrity and reporting mechanisms.
   It does not replace database role design, encryption key
   management, infrastructure isolation, or external CI
   platform enforcement.
================================================================
*/
