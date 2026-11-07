-- ============================================================
-- JENKINS + GITHUB INTEGRATION
-- PostgreSQL 15+
--
-- Models:
-- Repositories, branches, commits, pull requests,
-- reviews, approvals, discussions, status checks,
-- Jenkins jobs, builds, webhook deliveries,
-- SCM polling observations, branch protection,
-- and merge eligibility.
--
-- All objects are contained in the ci_cd schema.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS ci_cd;

SET search_path TO ci_cd, public;


-- ============================================================
-- 1. ENUM TYPES
-- ============================================================

CREATE TYPE branch_kind AS ENUM (
    'PROTECTED',
    'UNPROTECTED'
);

CREATE TYPE pr_state AS ENUM (
    'OPEN',
    'DRAFT',
    'CLOSED',
    'MERGED'
);

CREATE TYPE review_state AS ENUM (
    'APPROVED',
    'CHANGES_REQUESTED',
    'COMMENTED',
    'DISMISSED'
);

CREATE TYPE check_state AS ENUM (
    'SUCCESS',
    'FAILURE',
    'PENDING',
    'ERROR'
);

CREATE TYPE trigger_type AS ENUM (
    'WEBHOOK',
    'SCM_POLL',
    'MANUAL'
);

CREATE TYPE build_state AS ENUM (
    'QUEUED',
    'RUNNING',
    'SUCCESS',
    'FAILURE',
    'ABORTED'
);

CREATE TYPE webhook_state AS ENUM (
    'RECEIVED',
    'PROCESSING',
    'PROCESSED',
    'FAILED',
    'IGNORED'
);

CREATE TYPE merge_method AS ENUM (
    'MERGE_COMMIT',
    'SQUASH',
    'REBASE'
);


-- ============================================================
-- 2. REPOSITORIES
-- ============================================================

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    owner_name VARCHAR(150) NOT NULL,
    repository_name VARCHAR(200) NOT NULL,

    github_repository_id BIGINT UNIQUE,

    default_branch VARCHAR(255) NOT NULL DEFAULT 'main',

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_repository_owner_name
        UNIQUE (owner_name, repository_name),

    CONSTRAINT ck_repository_name
        CHECK (
            repository_name ~ '^[A-Za-z0-9._-]+$'
        )
);


-- ============================================================
-- 3. USERS AND REPOSITORY ROLES
-- ============================================================

CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    github_username VARCHAR(150) NOT NULL UNIQUE,

    display_name VARCHAR(200),

    active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE repository_members (
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    role_name VARCHAR(30) NOT NULL,

    eligible_reviewer BOOLEAN NOT NULL DEFAULT FALSE,

    is_code_owner BOOLEAN NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (repository_id, user_id),

    CONSTRAINT ck_repository_role
        CHECK (
            role_name IN (
                'ADMIN',
                'MAINTAIN',
                'WRITE',
                'TRIAGE',
                'READ'
            )
        )
);


-- ============================================================
-- 4. BRANCHES
-- ============================================================

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    branch_name VARCHAR(255) NOT NULL,

    head_sha VARCHAR(64) NOT NULL,

    branch_type branch_kind NOT NULL DEFAULT 'UNPROTECTED',

    allows_direct_push BOOLEAN NOT NULL DEFAULT TRUE,

    allows_force_push BOOLEAN NOT NULL DEFAULT FALSE,

    allows_deletion BOOLEAN NOT NULL DEFAULT TRUE,

    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_repository_branch
        UNIQUE (repository_id, branch_name),

    CONSTRAINT ck_branch_sha
        CHECK (head_sha ~ '^[0-9a-f]{7,64}$'),

    CONSTRAINT ck_branch_name
        CHECK (
            branch_name !~ '(^-|\\.\\.| )'
        )
);


CREATE INDEX idx_branches_repository
    ON branches(repository_id, is_active);


-- ============================================================
-- 5. COMMITS
-- ============================================================

CREATE TABLE commits (
    commit_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    commit_sha VARCHAR(64) NOT NULL,

    message TEXT NOT NULL,

    author_id BIGINT
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    parent_sha VARCHAR(64),

    committed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_repository_commit
        UNIQUE (repository_id, commit_sha),

    CONSTRAINT ck_commit_sha
        CHECK (commit_sha ~ '^[0-9a-f]{7,64}$'),

    CONSTRAINT ck_parent_sha
        CHECK (
            parent_sha IS NULL OR
            parent_sha ~ '^[0-9a-f]{7,64}$'
        ),

    CONSTRAINT ck_commit_message
        CHECK (LENGTH(TRIM(message)) > 0)
);


CREATE INDEX idx_commits_repository_date
    ON commits(repository_id, committed_at DESC);


-- ============================================================
-- 6. PULL REQUESTS
-- ============================================================

CREATE TABLE pull_requests (
    pr_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    github_pr_number INTEGER NOT NULL,

    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id)
        ON DELETE RESTRICT,

    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id)
        ON DELETE RESTRICT,

    source_sha VARCHAR(64) NOT NULL,

    target_sha VARCHAR(64) NOT NULL,

    state pr_state NOT NULL DEFAULT 'OPEN',

    is_draft BOOLEAN NOT NULL DEFAULT FALSE,

    merge_conflict BOOLEAN NOT NULL DEFAULT FALSE,

    base_synchronized BOOLEAN NOT NULL DEFAULT TRUE,

    author_id BIGINT
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    title VARCHAR(300) NOT NULL,

    description TEXT,

    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    closed_at TIMESTAMPTZ,

    merged_at TIMESTAMPTZ,

    CONSTRAINT uq_github_pull_request
        UNIQUE (repository_id, github_pr_number),

    CONSTRAINT ck_pr_number
        CHECK (github_pr_number > 0),

    CONSTRAINT ck_pr_sha
        CHECK (
            source_sha ~ '^[0-9a-f]{7,64}$'
            AND target_sha ~ '^[0-9a-f]{7,64}$'
        ),

    CONSTRAINT ck_pr_branches_differ
        CHECK (source_branch_id <> target_branch_id),

    CONSTRAINT ck_pr_draft_state
        CHECK (
            NOT is_draft OR state = 'DRAFT'
        )
);


CREATE INDEX idx_pr_repository_state
    ON pull_requests(repository_id, state, updated_at DESC);


CREATE INDEX idx_pr_target_state
    ON pull_requests(target_branch_id, state);


-- ============================================================
-- 7. PULL REQUEST COMMITS
-- ============================================================

CREATE TABLE pull_request_commits (
    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id)
        ON DELETE CASCADE,

    commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id)
        ON DELETE RESTRICT,

    sequence_number INTEGER NOT NULL,

    PRIMARY KEY (pr_id, commit_id),

    CONSTRAINT uq_pr_commit_sequence
        UNIQUE (pr_id, sequence_number),

    CONSTRAINT ck_pr_commit_sequence
        CHECK (sequence_number > 0)
);


-- ============================================================
-- 8. REVIEW REQUESTS
-- ============================================================

CREATE TABLE review_requests (
    review_request_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id)
        ON DELETE CASCADE,

    reviewer_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    requested_by BIGINT
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    fulfilled_at TIMESTAMPTZ,

    CONSTRAINT uq_pr_review_request
        UNIQUE (pr_id, reviewer_id)
);


-- ============================================================
-- 9. CODE REVIEWS
-- ============================================================

CREATE TABLE reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id)
        ON DELETE CASCADE,

    reviewer_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    review_state review_state NOT NULL,

    reviewed_commit_sha VARCHAR(64) NOT NULL,

    review_body TEXT,

    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    dismissed_at TIMESTAMPTZ,

    dismissed_by BIGINT
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    CONSTRAINT ck_review_sha
        CHECK (
            reviewed_commit_sha ~ '^[0-9a-f]{7,64}$'
        )
);


CREATE INDEX idx_reviews_pr_reviewer
    ON reviews(pr_id, reviewer_id, submitted_at DESC);


CREATE INDEX idx_reviews_approval
    ON reviews(pr_id, review_state, reviewed_commit_sha);


-- ============================================================
-- 10. REVIEW COMMENTS AND CONVERSATIONS
-- ============================================================

CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id)
        ON DELETE CASCADE,

    review_id BIGINT
        REFERENCES reviews(review_id)
        ON DELETE SET NULL,

    author_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE RESTRICT,

    parent_comment_id BIGINT
        REFERENCES review_comments(comment_id)
        ON DELETE CASCADE,

    file_path TEXT NOT NULL,

    line_number INTEGER,

    comment_body TEXT NOT NULL,

    resolved BOOLEAN NOT NULL DEFAULT FALSE,

    resolved_by BIGINT
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    resolved_at TIMESTAMPTZ,

    CONSTRAINT ck_review_comment_line
        CHECK (line_number IS NULL OR line_number > 0),

    CONSTRAINT ck_review_comment_body
        CHECK (LENGTH(TRIM(comment_body)) > 0)
);


CREATE INDEX idx_review_comments_unresolved
    ON review_comments(pr_id, resolved)
    WHERE resolved = FALSE;


-- ============================================================
-- 11. JENKINS STATUS CHECKS
-- ============================================================

CREATE TABLE status_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL
        REFERENCES pull_requests(pr_id)
        ON DELETE CASCADE,

    check_name VARCHAR(150) NOT NULL,

    commit_sha VARCHAR(64) NOT NULL,

    state check_state NOT NULL,

    jenkins_build_number BIGINT,

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    duration_ms BIGINT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_status_check_sha
        CHECK (commit_sha ~ '^[0-9a-f]{7,64}$'),

    CONSTRAINT ck_check_duration
        CHECK (
            duration_ms IS NULL OR duration_ms >= 0
        ),

    CONSTRAINT ck_check_times
        CHECK (
            completed_at IS NULL OR
            started_at IS NULL OR
            completed_at >= started_at
        )
);


CREATE INDEX idx_status_checks_pr_name
    ON status_checks(pr_id, check_name, created_at DESC);


CREATE INDEX idx_status_checks_current
    ON status_checks(pr_id, commit_sha, state);


-- ============================================================
-- 12. JENKINS JOBS
-- ============================================================

CREATE TABLE jenkins_jobs (
    job_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    job_name VARCHAR(200) NOT NULL,

    jenkins_job_path TEXT NOT NULL,

    enabled BOOLEAN NOT NULL DEFAULT TRUE,

    webhook_enabled BOOLEAN NOT NULL DEFAULT TRUE,

    scm_polling_enabled BOOLEAN NOT NULL DEFAULT FALSE,

    polling_interval_seconds INTEGER NOT NULL DEFAULT 300,

    pipeline_definition VARCHAR(30) NOT NULL DEFAULT 'JENKINSFILE',

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_repository_job
        UNIQUE (repository_id, job_name),

    CONSTRAINT ck_poll_interval
        CHECK (polling_interval_seconds >= 30),

    CONSTRAINT ck_pipeline_definition
        CHECK (
            pipeline_definition IN (
                'JENKINSFILE',
                'PIPELINE_SCRIPT'
            )
        )
);


-- ============================================================
-- 13. JENKINS BUILDS
-- ============================================================

CREATE TABLE jenkins_builds (
    build_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    job_id BIGINT NOT NULL
        REFERENCES jenkins_jobs(job_id)
        ON DELETE CASCADE,

    build_number BIGINT NOT NULL,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    branch_id BIGINT
        REFERENCES branches(branch_id)
        ON DELETE SET NULL,

    commit_sha VARCHAR(64) NOT NULL,

    pr_id BIGINT
        REFERENCES pull_requests(pr_id)
        ON DELETE SET NULL,

    trigger trigger_type NOT NULL,

    state build_state NOT NULL DEFAULT 'QUEUED',

    queued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    started_at TIMESTAMPTZ,

    completed_at TIMESTAMPTZ,

    failure_reason TEXT,

    CONSTRAINT uq_job_build_number
        UNIQUE (job_id, build_number),

    CONSTRAINT ck_build_sha
        CHECK (commit_sha ~ '^[0-9a-f]{7,64}$'),

    CONSTRAINT ck_build_times
        CHECK (
            completed_at IS NULL OR
            started_at IS NULL OR
            completed_at >= started_at
        )
);


CREATE INDEX idx_builds_repository_date
    ON jenkins_builds(repository_id, queued_at DESC);


CREATE INDEX idx_builds_pr_state
    ON jenkins_builds(pr_id, state);


-- ============================================================
-- 14. GITHUB WEBHOOK DELIVERIES
-- ============================================================

CREATE TABLE webhook_deliveries (
    delivery_id VARCHAR(150)
        PRIMARY KEY,

    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id)
        ON DELETE CASCADE,

    event_name VARCHAR(100) NOT NULL,

    action_name VARCHAR(100),

    payload_sha256 VARCHAR(64) NOT NULL,

    state webhook_state NOT NULL DEFAULT 'RECEIVED',

    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    processed_at TIMESTAMPTZ,

    attempt_count INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,

    CONSTRAINT ck_webhook_hash
        CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),

    CONSTRAINT ck_webhook_attempts
        CHECK (attempt_count >= 0)
);


CREATE INDEX idx_webhook_state_received
    ON webhook_deliveries(state, received_at);


-- ============================================================
-- 15. SCM POLLING OBSERVATIONS
-- ============================================================

CREATE TABLE scm_poll_observations (
    observation_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,

    observed_sha VARCHAR(64) NOT NULL,

    changed BOOLEAN NOT NULL,

    polled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_observed_sha
        CHECK (observed_sha ~ '^[0-9a-f]{7,64}$')
);


CREATE INDEX idx_scm_observation_branch_time
    ON scm_poll_observations(branch_id, polled_at DESC);


-- ============================================================
-- 16. BRANCH PROTECTION POLICIES
-- ============================================================

CREATE TABLE branch_protection_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id)
        ON DELETE CASCADE,

    required_approvals INTEGER NOT NULL DEFAULT 1,

    require_conversation_resolution BOOLEAN
        NOT NULL DEFAULT TRUE,

    require_up_to_date BOOLEAN
        NOT NULL DEFAULT TRUE,

    require_code_owner_review BOOLEAN
        NOT NULL DEFAULT FALSE,

    require_linear_history BOOLEAN
        NOT NULL DEFAULT FALSE,

    allow_direct_push BOOLEAN
        NOT NULL DEFAULT FALSE,

    allow_force_push BOOLEAN
        NOT NULL DEFAULT FALSE,

    allow_deletion BOOLEAN
        NOT NULL DEFAULT FALSE,

    dismiss_stale_approvals BOOLEAN
        NOT NULL DEFAULT TRUE,

    administrator_bypass BOOLEAN
        NOT NULL DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_required_approvals
        CHECK (required_approvals >= 0)
);


-- ============================================================
-- 17. REQUIRED STATUS CHECK POLICIES
-- ============================================================

CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL
        REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,

    check_name VARCHAR(150) NOT NULL,

    PRIMARY KEY (policy_id, check_name)
);


-- ============================================================
-- 18. MERGE AUDIT
-- ============================================================

CREATE TABLE merge_audit (
    merge_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,

    pr_id BIGINT NOT NULL UNIQUE
        REFERENCES pull_requests(pr_id)
        ON DELETE RESTRICT,

    merge_commit_sha VARCHAR(64) NOT NULL,

    merge_strategy merge_method NOT NULL,

    merged_by BIGINT
        REFERENCES users(user_id)
        ON DELETE SET NULL,

    merged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_merge_sha
        CHECK (
            merge_commit_sha ~ '^[0-9a-f]{7,64}$'
        )
);


-- ============================================================
-- 19. INTEGRITY TRIGGER: BRANCH OWNERSHIP
-- ============================================================

CREATE OR REPLACE FUNCTION validate_pull_request_branches()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_repository BIGINT;
    target_repository BIGINT;
BEGIN
    SELECT repository_id
    INTO source_repository
    FROM branches
    WHERE branch_id = NEW.source_branch_id;

    SELECT repository_id
    INTO target_repository
    FROM branches
    WHERE branch_id = NEW.target_branch_id;

    IF source_repository IS NULL OR target_repository IS NULL THEN
        RAISE EXCEPTION 'Source or target branch does not exist';
    END IF;

    IF source_repository <> NEW.repository_id
       OR target_repository <> NEW.repository_id THEN
        RAISE EXCEPTION
            'Both branches must belong to the Pull Request repository';
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_validate_pr_branches
BEFORE INSERT OR UPDATE OF
    repository_id,
    source_branch_id,
    target_branch_id
ON pull_requests
FOR EACH ROW
EXECUTE FUNCTION validate_pull_request_branches();


-- ============================================================
-- 20. INTEGRITY TRIGGER: REVIEWER ELIGIBILITY
-- ============================================================

CREATE OR REPLACE FUNCTION validate_review_reviewer()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    eligible BOOLEAN;
    active_user BOOLEAN;
BEGIN
    SELECT
        rm.eligible_reviewer,
        u.active
    INTO
        eligible,
        active_user
    FROM pull_requests pr
    JOIN repository_members rm
        ON rm.repository_id = pr.repository_id
    JOIN users u
        ON u.user_id = rm.user_id
    WHERE pr.pr_id = NEW.pr_id
      AND rm.user_id = NEW.reviewer_id;

    IF NOT COALESCE(eligible, FALSE)
       OR NOT COALESCE(active_user, FALSE) THEN
        RAISE EXCEPTION
            'Reviewer is not eligible for this repository';
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_validate_reviewer
BEFORE INSERT OR UPDATE OF pr_id, reviewer_id
ON reviews
FOR EACH ROW
EXECUTE FUNCTION validate_review_reviewer();


-- ============================================================
-- 21. TRIGGER: REVIEW COMMENT RESOLUTION AUDIT
-- ============================================================

CREATE OR REPLACE FUNCTION audit_comment_resolution()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.resolved = FALSE AND NEW.resolved = TRUE THEN
        NEW.resolved_at = NOW();
    END IF;

    IF OLD.resolved = TRUE AND NEW.resolved = FALSE THEN
        NEW.resolved_at = NULL;
    END IF;

    RETURN NEW;
END;
$$;


CREATE TRIGGER trg_comment_resolution
BEFORE UPDATE OF resolved
ON review_comments
FOR EACH ROW
EXECUTE FUNCTION audit_comment_resolution();


-- ============================================================
-- 22. VIEW: LATEST REVIEW DECISIONS
-- ============================================================

CREATE OR REPLACE VIEW latest_review_decisions AS
SELECT DISTINCT ON (r.pr_id, r.reviewer_id)
    r.pr_id,
    r.reviewer_id,
    r.review_state,
    r.reviewed_commit_sha,
    r.submitted_at,
    r.dismissed_at
FROM reviews r
ORDER BY
    r.pr_id,
    r.reviewer_id,
    r.submitted_at DESC,
    r.review_id DESC;


-- ============================================================
-- 23. VIEW: CURRENT STATUS CHECKS
-- ============================================================

CREATE OR REPLACE VIEW current_pr_status_checks AS
SELECT
    pr.pr_id,
    sc.check_name,
    sc.state,
    sc.commit_sha,
    sc.created_at
FROM pull_requests pr
JOIN LATERAL (
    SELECT DISTINCT ON (check_name)
        check_name,
        state,
        commit_sha,
        created_at
    FROM status_checks
    WHERE pr_id = pr.pr_id
    ORDER BY check_name, created_at DESC, check_id DESC
) sc ON TRUE
WHERE sc.commit_sha = pr.source_sha;


-- ============================================================
-- 24. FUNCTION: MERGE ELIGIBILITY
-- ============================================================

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_pr_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    reason TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    pr RECORD;
    policy RECORD;

    approval_count INTEGER := 0;
    owner_approved BOOLEAN := FALSE;

    required_check TEXT;
    current_check RECORD;

    unresolved_count INTEGER := 0;
BEGIN

    SELECT
        p.*,
        target.branch_name AS target_branch_name
    INTO pr
    FROM pull_requests p
    JOIN branches target
        ON target.branch_id = p.target_branch_id
    WHERE p.pr_id = p_pr_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request not found'::TEXT;
        RETURN;
    END IF;

    IF pr.state <> 'OPEN' THEN
        RETURN QUERY
        SELECT FALSE, 'Pull Request is not open'::TEXT;
    END IF;

    IF pr.is_draft THEN
        RETURN QUERY
        SELECT FALSE, 'Draft Pull Request cannot be merged'::TEXT;
    END IF;

    IF pr.merge_conflict THEN
        RETURN QUERY
        SELECT FALSE, 'Merge conflict exists'::TEXT;
    END IF;

    SELECT bp.*
    INTO policy
    FROM branch_protection_policies bp
    WHERE bp.branch_id = pr.target_branch_id;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT TRUE, 'No branch protection policy applies'::TEXT;
        RETURN;
    END IF;

    IF policy.require_up_to_date
       AND NOT pr.base_synchronized THEN
        RETURN QUERY
        SELECT FALSE, 'Source branch is not synchronized'::TEXT;
    END IF;

    IF policy.require_conversation_resolution THEN
        SELECT COUNT(*)
        INTO unresolved_count
        FROM review_comments rc
        WHERE rc.pr_id = p_pr_id
          AND NOT rc.resolved;

        IF unresolved_count > 0 THEN
            RETURN QUERY
            SELECT FALSE, 'Unresolved review discussions exist'::TEXT;
        END IF;
    END IF;

    -- Only the latest eligible reviewer decision is counted.
    SELECT COUNT(*)
    INTO approval_count
    FROM latest_review_decisions latest
    JOIN repository_members rm
        ON rm.user_id = latest.reviewer_id
       AND rm.repository_id = pr.repository_id
    JOIN users u
        ON u.user_id = latest.reviewer_id
    WHERE latest.pr_id = p_pr_id
      AND latest.review_state = 'APPROVED'
      AND rm.eligible_reviewer
      AND u.active
      AND (
          NOT policy.dismiss_stale_approvals
          OR latest.reviewed_commit_sha = pr.source_sha
      );

    IF approval_count < policy.required_approvals THEN
        RETURN QUERY
        SELECT
            FALSE,
            FORMAT(
                'Insufficient approvals: %s/%s',
                approval_count,
                policy.required_approvals
            );
    END IF;

    IF policy.require_code_owner_review THEN

        SELECT EXISTS (
            SELECT 1
            FROM latest_review_decisions latest
            JOIN repository_members rm
                ON rm.repository_id = pr.repository_id
               AND rm.user_id = latest.reviewer_id
            JOIN users u
                ON u.user_id = latest.reviewer_id
            WHERE latest.pr_id = p_pr_id
              AND latest.review_state = 'APPROVED'
              AND rm.is_code_owner
              AND rm.eligible_reviewer
              AND u.active
              AND (
                  NOT policy.dismiss_stale_approvals
                  OR latest.reviewed_commit_sha = pr.source_sha
              )
        )
        INTO owner_approved;

        IF NOT owner_approved THEN
            RETURN QUERY
            SELECT FALSE, 'Code owner approval required'::TEXT;
        END IF;
    END IF;

    FOR required_check IN
        SELECT rsc.check_name
        FROM required_status_checks rsc
        WHERE rsc.policy_id = policy.policy_id
    LOOP

        SELECT *
        INTO current_check
        FROM current_pr_status_checks c
        WHERE c.pr_id = p_pr_id
          AND c.check_name = required_check;

        IF NOT FOUND THEN
            RETURN QUERY
            SELECT
                FALSE,
                FORMAT('Missing required check: %s', required_check);
            CONTINUE;
        END IF;

        IF current_check.state <> 'SUCCESS' THEN
            RETURN QUERY
            SELECT
                FALSE,
                FORMAT(
                    'Required check %s is %s',
                    required_check,
                    current_check.state
                );
        END IF;

    END LOOP;

    RETURN QUERY
    SELECT TRUE, 'All merge conditions satisfied'::TEXT;

END;
$$;


-- ============================================================
-- 25. PROCEDURE: MERGE PULL REQUEST
-- ============================================================

CREATE OR REPLACE PROCEDURE merge_pull_request(
    p_pr_id BIGINT,
    p_merge_sha VARCHAR(64),
    p_strategy merge_method,
    p_user_id BIGINT DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    pr RECORD;
    decision RECORD;
    blocker TEXT;
BEGIN

    IF p_merge_sha !~ '^[0-9a-f]{7,64}$' THEN
        RAISE EXCEPTION 'Invalid merge commit SHA';
    END IF;

    -- Serialize competing merge operations for this PR.
    SELECT *
    INTO pr
    FROM pull_requests
    WHERE pr_id = p_pr_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pull Request does not exist';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM commits
        WHERE repository_id = pr.repository_id
          AND commit_sha = p_merge_sha
    ) THEN
        RAISE EXCEPTION 'Merge commit already exists';
    END IF;

    SELECT *
    INTO decision
    FROM evaluate_merge_eligibility(p_pr_id)
    WHERE eligible = FALSE
    LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'Merge blocked: %',
            decision.reason;
    END IF;

    INSERT INTO commits (
        repository_id,
        commit_sha,
        message,
        author_id
    )
    VALUES (
        pr.repository_id,
        p_merge_sha,
        FORMAT('Merge pull request #%s', pr.github_pr_number),
        p_user_id
    );

    UPDATE branches
    SET
        head_sha = p_merge_sha,
        updated_at = NOW()
    WHERE branch_id = pr.target_branch_id;

    UPDATE pull_requests
    SET
        state = 'MERGED',
        merged_at = NOW(),
        updated_at = NOW()
    WHERE pr_id = p_pr_id;

    INSERT INTO merge_audit (
        pr_id,
        merge_commit_sha,
        merge_strategy,
        merged_by
    )
    VALUES (
        p_pr_id,
        p_merge_sha,
        p_strategy,
        p_user_id
    );

END;
$$;


-- ============================================================
-- 26. FUNCTION: PROCESS WEBHOOK DELIVERY
-- ============================================================

CREATE OR REPLACE FUNCTION register_webhook_delivery(
    p_delivery_id VARCHAR(150),
    p_repository_id BIGINT,
    p_event_name VARCHAR(100),
    p_action_name VARCHAR(100),
    p_payload_sha256 VARCHAR(64)
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    inserted_count INTEGER;
BEGIN
    IF p_delivery_id IS NULL OR LENGTH(TRIM(p_delivery_id)) = 0 THEN
        RAISE EXCEPTION 'Delivery ID is required';
    END IF;

    IF p_payload_sha256 !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Invalid payload SHA-256';
    END IF;

    INSERT INTO webhook_deliveries (
        delivery_id,
        repository_id,
        event_name,
        action_name,
        payload_sha256
    )
    VALUES (
        p_delivery_id,
        p_repository_id,
        p_event_name,
        p_action_name,
        p_payload_sha256
    )
    ON CONFLICT (delivery_id) DO NOTHING;

    GET DIAGNOSTICS inserted_count = ROW_COUNT;

    RETURN inserted_count = 1;
END;
$$;


-- ============================================================
-- 27. FUNCTION: RECORD SCM POLLING
-- ============================================================

CREATE OR REPLACE FUNCTION record_scm_poll(
    p_branch_id BIGINT,
    p_remote_sha VARCHAR(64)
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    previous_sha VARCHAR(64);
    changed BOOLEAN;
BEGIN
    IF p_remote_sha !~ '^[0-9a-f]{7,64}$' THEN
        RAISE EXCEPTION 'Invalid remote SHA';
    END IF;

    SELECT head_sha
    INTO previous_sha
    FROM branches
    WHERE branch_id = p_branch_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Branch not found';
    END IF;

    changed := previous_sha <> p_remote_sha;

    INSERT INTO scm_poll_observations (
        branch_id,
        observed_sha,
        changed
    )
    VALUES (
        p_branch_id,
        p_remote_sha,
        changed
    );

    IF changed THEN
        UPDATE branches
        SET updated_at = NOW()
        WHERE branch_id = p_branch_id;
    END IF;

    RETURN changed;
END;
$$;


-- ============================================================
-- 28. FUNCTION: CREATE JENKINS BUILD
-- ============================================================

CREATE OR REPLACE FUNCTION create_jenkins_build(
    p_job_id BIGINT,
    p_repository_id BIGINT,
    p_branch_id BIGINT,
    p_commit_sha VARCHAR(64),
    p_trigger trigger_type,
    p_pr_id BIGINT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    next_number BIGINT;
    new_build_id BIGINT;
BEGIN
    IF p_commit_sha !~ '^[0-9a-f]{7,64}$' THEN
        RAISE EXCEPTION 'Invalid build commit SHA';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM jenkins_jobs
        WHERE job_id = p_job_id
          AND repository_id = p_repository_id
          AND enabled
    ) THEN
        RAISE EXCEPTION 'Jenkins job is unavailable';
    END IF;

    -- A per-job advisory lock serializes build-number allocation.
    PERFORM pg_advisory_xact_lock(p_job_id);

    SELECT COALESCE(MAX(build_number), 0) + 1
    INTO next_number
    FROM jenkins_builds
    WHERE job_id = p_job_id;

    INSERT INTO jenkins_builds (
        job_id,
        build_number,
        repository_id,
        branch_id,
        commit_sha,
        pr_id,
        trigger,
        state
    )
    VALUES (
        p_job_id,
        next_number,
        p_repository_id,
        p_branch_id,
        p_commit_sha,
        p_pr_id,
        p_trigger,
        'QUEUED'
    )
    RETURNING build_id INTO new_build_id;

    RETURN new_build_id;
END;
$$;


-- ============================================================
-- 29. VIEW: MERGE ELIGIBILITY REPORT
-- ============================================================

CREATE OR REPLACE VIEW pull_request_merge_report AS
SELECT
    pr.pr_id,
    pr.github_pr_number,
    repo.repository_name,
    source.branch_name AS source_branch,
    target.branch_name AS target_branch,
    pr.state,
    pr.is_draft,
    pr.merge_conflict,
    pr.base_synchronized,
    evaluation.eligible,
    evaluation.reason
FROM pull_requests pr
JOIN repositories repo
    ON repo.repository_id = pr.repository_id
JOIN branches source
    ON source.branch_id = pr.source_branch_id
JOIN branches target
    ON target.branch_id = pr.target_branch_id
LEFT JOIN LATERAL (
    SELECT
        BOOL_AND(result.eligible) AS eligible,
        STRING_AGG(
            result.reason,
            '; ' ORDER BY result.reason
        ) AS reason
    FROM evaluate_merge_eligibility(pr.pr_id) result
) evaluation ON TRUE;


-- ============================================================
-- 30. SAMPLE DATA
-- ============================================================

INSERT INTO repositories (
    owner_name,
    repository_name,
    github_repository_id,
    default_branch
)
VALUES (
    'engineering',
    'payment-service',
    900001,
    'main'
);


INSERT INTO users (
    github_username,
    display_name
)
VALUES
    ('platform-admin', 'Platform Administrator'),
    ('developer-alice', 'Alice Developer'),
    ('reviewer-alice', 'Alice Reviewer'),
    ('reviewer-bob', 'Bob Reviewer'),
    ('reviewer-charlie', 'Charlie Reviewer');


INSERT INTO repository_members (
    repository_id,
    user_id,
    role_name,
    eligible_reviewer,
    is_code_owner
)
SELECT
    r.repository_id,
    u.user_id,
    CASE
        WHEN u.github_username = 'platform-admin' THEN 'ADMIN'
        WHEN u.github_username = 'developer-alice' THEN 'WRITE'
        ELSE 'WRITE'
    END,
    u.github_username IN (
        'reviewer-alice',
        'reviewer-bob',
        'reviewer-charlie'
    ),
    u.github_username IN (
        'reviewer-alice',
        'reviewer-charlie'
    )
FROM repositories r
CROSS JOIN users u
WHERE r.repository_name = 'payment-service';


INSERT INTO branches (
    repository_id,
    branch_name,
    head_sha,
    branch_type,
    allows_direct_push,
    allows_force_push,
    allows_deletion
)
SELECT
    repository_id,
    'main',
    REPEAT('a', 40),
    'PROTECTED',
    FALSE,
    FALSE,
    FALSE
FROM repositories
WHERE repository_name = 'payment-service';


INSERT INTO branches (
    repository_id,
    branch_name,
    head_sha,
    branch_type
)
SELECT
    repository_id,
    'feature/payment-validation',
    REPEAT('b', 40),
    'UNPROTECTED'
FROM repositories
WHERE repository_name = 'payment-service';


INSERT INTO commits (
    repository_id,
    commit_sha,
    message,
    author_id
)
SELECT
    r.repository_id,
    REPEAT('a', 40),
    'Initial production release',
    u.user_id
FROM repositories r
JOIN users u
    ON u.github_username = 'platform-admin'
WHERE r.repository_name = 'payment-service';


INSERT INTO commits (
    repository_id,
    commit_sha,
    message,
    author_id,
    parent_sha
)
SELECT
    r.repository_id,
    REPEAT('b', 40),
    'Add payment validation',
    u.user_id,
    REPEAT('a', 40)
FROM repositories r
JOIN users u
    ON u.github_username = 'developer-alice'
WHERE r.repository_name = 'payment-service';


-- ============================================================
-- 31. BRANCH PROTECTION CONFIGURATION
-- ============================================================

INSERT INTO branch_protection_policies (
    branch_id,
    required_approvals,
    require_conversation_resolution,
    require_up_to_date,
    require_code_owner_review,
    require_linear_history,
    allow_direct_push,
    allow_force_push,
    allow_deletion,
    dismiss_stale_approvals,
    administrator_bypass
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
    FALSE,
    TRUE,
    FALSE
FROM branches
WHERE branch_name = 'main';


INSERT INTO required_status_checks (
    policy_id,
    check_name
)
SELECT
    policy_id,
    required.check_name
FROM branch_protection_policies policy
CROSS JOIN (
    VALUES
        ('unit-tests'),
        ('integration-tests'),
        ('security-scan')
) AS required(check_name);


-- ============================================================
-- 32. JENKINS JOB CONFIGURATION
-- ============================================================

INSERT INTO jenkins_jobs (
    repository_id,
    job_name,
    jenkins_job_path,
    enabled,
    webhook_enabled,
    scm_polling_enabled,
    polling_interval_seconds
)
SELECT
    repository_id,
    'payment-service-ci',
    'engineering/payment-service-ci',
    TRUE,
    TRUE,
    TRUE,
    300
FROM repositories
WHERE repository_name = 'payment-service';


-- ============================================================
-- 33. SAMPLE PULL REQUEST
-- ============================================================

INSERT INTO pull_requests (
    repository_id,
    github_pr_number,
    source_branch_id,
    target_branch_id,
    source_sha,
    target_sha,
    state,
    title,
    author_id
)
SELECT
    r.repository_id,
    101,
    source.branch_id,
    target.branch_id,
    REPEAT('b', 40),
    REPEAT('a', 40),
    'OPEN',
    'Add payment validation',
    author.user_id
FROM repositories r
JOIN branches source
    ON source.repository_id = r.repository_id
   AND source.branch_name = 'feature/payment-validation'
JOIN branches target
    ON target.repository_id = r.repository_id
   AND target.branch_name = 'main'
JOIN users author
    ON author.github_username = 'developer-alice'
WHERE r.repository_name = 'payment-service';


INSERT INTO pull_request_commits (
    pr_id,
    commit_id,
    sequence_number
)
SELECT
    pr.pr_id,
    c.commit_id,
    1
FROM pull_requests pr
JOIN commits c
    ON c.repository_id = pr.repository_id
   AND c.commit_sha = REPEAT('b', 40)
WHERE pr.github_pr_number = 101;


-- ============================================================
-- 34. SAMPLE REVIEWS
-- ============================================================

INSERT INTO reviews (
    pr_id,
    reviewer_id,
    review_state,
    reviewed_commit_sha,
    review_body
)
SELECT
    pr.pr_id,
    u.user_id,
    'APPROVED',
    REPEAT('b', 40),
    'Payment validation logic reviewed'
FROM pull_requests pr
JOIN users u
    ON u.github_username IN (
        'reviewer-alice',
        'reviewer-bob'
    )
WHERE pr.github_pr_number = 101;


-- ============================================================
-- 35. SAMPLE REVIEW DISCUSSION
-- ============================================================

INSERT INTO review_comments (
    pr_id,
    author_id,
    file_path,
    line_number,
    comment_body,
    resolved
)
SELECT
    pr.pr_id,
    u.user_id,
    'src/payment.py',
    45,
    'Validate transaction amount before processing',
    TRUE
FROM pull_requests pr
JOIN users u
    ON u.github_username = 'reviewer-alice'
WHERE pr.github_pr_number = 101;


-- ============================================================
-- 36. SAMPLE STATUS CHECKS
-- ============================================================

INSERT INTO status_checks (
    pr_id,
    check_name,
    commit_sha,
    state,
    jenkins_build_number,
    duration_ms
)
SELECT
    pr.pr_id,
    checks.check_name,
    REPEAT('b', 40),
    'SUCCESS',
    1,
    checks.duration_ms
FROM pull_requests pr
CROSS JOIN (
    VALUES
        ('unit-tests', 12500::BIGINT),
        ('integration-tests', 22000::BIGINT),
        ('security-scan', 18000::BIGINT)
) AS checks(check_name, duration_ms)
WHERE pr.github_pr_number = 101;


-- ============================================================
-- 37. SAMPLE JENKINS BUILD
-- ============================================================

INSERT INTO jenkins_builds (
    job_id,
    build_number,
    repository_id,
    branch_id,
    commit_sha,
    pr_id,
    trigger,
    state,
    started_at,
    completed_at
)
SELECT
    job.job_id,
    1,
    r.repository_id,
    branch.branch_id,
    REPEAT('b', 40),
    pr.pr_id,
    'WEBHOOK',
    'SUCCESS',
    NOW() - INTERVAL '3 minutes',
    NOW() - INTERVAL '1 minute'
FROM jenkins_jobs job
JOIN repositories r
    ON r.repository_id = job.repository_id
JOIN branches branch
    ON branch.repository_id = r.repository_id
   AND branch.branch_name = 'feature/payment-validation'
JOIN pull_requests pr
    ON pr.repository_id = r.repository_id
   AND pr.github_pr_number = 101
WHERE job.job_name = 'payment-service-ci';


-- ============================================================
-- 38. SAMPLE WEBHOOK DELIVERY
-- ============================================================

INSERT INTO webhook_deliveries (
    delivery_id,
    repository_id,
    event_name,
    action_name,
    payload_sha256,
    state,
    processed_at,
    attempt_count
)
SELECT
    'github-delivery-001',
    repository_id,
    'pull_request',
    'opened',
    REPEAT('c', 64),
    'PROCESSED',
    NOW(),
    1
FROM repositories
WHERE repository_name = 'payment-service';


-- ============================================================
-- 39. SCM POLLING SAMPLE
-- ============================================================

INSERT INTO scm_poll_observations (
    branch_id,
    observed_sha,
    changed
)
SELECT
    branch_id,
    REPEAT('a', 40),
    FALSE
FROM branches
WHERE branch_name = 'main';


-- ============================================================
-- 40. RETRIEVAL QUERIES
-- ============================================================

-- Repository and active branches.
SELECT
    r.repository_name,
    b.branch_name,
    b.head_sha,
    b.branch_type,
    b.allows_direct_push,
    b.allows_force_push
FROM repositories r
JOIN branches b
    ON b.repository_id = r.repository_id
WHERE r.repository_name = 'payment-service'
ORDER BY b.branch_name;


-- Pull Request changesets.
SELECT
    pr.github_pr_number,
    c.commit_sha,
    c.message,
    pc.sequence_number
FROM pull_requests pr
JOIN pull_request_commits pc
    ON pc.pr_id = pr.pr_id
JOIN commits c
    ON c.commit_id = pc.commit_id
WHERE pr.github_pr_number = 101
ORDER BY pc.sequence_number;


-- Latest review decisions.
SELECT
    pr.github_pr_number,
    u.github_username,
    latest.review_state,
    latest.reviewed_commit_sha
FROM latest_review_decisions latest
JOIN pull_requests pr
    ON pr.pr_id = latest.pr_id
JOIN users u
    ON u.user_id = latest.reviewer_id
WHERE pr.github_pr_number = 101;


-- Jenkins build history.
SELECT
    job.job_name,
    build.build_number,
    build.trigger,
    build.state,
    build.commit_sha,
    build.queued_at,
    build.completed_at
FROM jenkins_builds build
JOIN jenkins_jobs job
    ON job.job_id = build.job_id
ORDER BY build.queued_at DESC;


-- ============================================================
-- 41. VALIDATION QUERIES
-- ============================================================

-- Identify stale approvals.
SELECT
    pr.github_pr_number,
    u.github_username,
    latest.reviewed_commit_sha,
    pr.source_sha AS current_source_sha
FROM latest_review_decisions latest
JOIN pull_requests pr
    ON pr.pr_id = latest.pr_id
JOIN users u
    ON u.user_id = latest.reviewer_id
WHERE latest.review_state = 'APPROVED'
  AND latest.reviewed_commit_sha <> pr.source_sha;


-- Identify unresolved review conversations.
SELECT
    pr.github_pr_number,
    COUNT(*) AS unresolved_discussions
FROM pull_requests pr
JOIN review_comments rc
    ON rc.pr_id = pr.pr_id
WHERE rc.resolved = FALSE
GROUP BY pr.github_pr_number;


-- Identify failed or pending status checks.
SELECT
    pr.github_pr_number,
    sc.check_name,
    sc.state
FROM pull_requests pr
JOIN current_pr_status_checks sc
    ON sc.pr_id = pr.pr_id
WHERE sc.state <> 'SUCCESS';


-- Identify inactive or ineligible reviewers.
SELECT
    pr.github_pr_number,
    u.github_username,
    rm.eligible_reviewer,
    u.active
FROM reviews r
JOIN pull_requests pr
    ON pr.pr_id = r.pr_id
JOIN users u
    ON u.user_id = r.reviewer_id
LEFT JOIN repository_members rm
    ON rm.repository_id = pr.repository_id
   AND rm.user_id = u.user_id
WHERE NOT COALESCE(rm.eligible_reviewer, FALSE)
   OR NOT u.active;


-- ============================================================
-- 42. AGGREGATION AND REPORTING
-- ============================================================

-- Jenkins build success rate.
SELECT
    job.job_name,
    COUNT(*) AS total_builds,
    COUNT(*) FILTER (
        WHERE build.state = 'SUCCESS'
    ) AS successful_builds,
    COUNT(*) FILTER (
        WHERE build.state = 'FAILURE'
    ) AS failed_builds,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE build.state = 'SUCCESS'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_percentage
FROM jenkins_builds build
JOIN jenkins_jobs job
    ON job.job_id = build.job_id
GROUP BY job.job_name;


-- Average Jenkins build duration.
SELECT
    job.job_name,
    ROUND(
        AVG(
            EXTRACT(
                EPOCH FROM (
                    build.completed_at - build.started_at
                )
            )
        )::NUMERIC,
        2
    ) AS average_duration_seconds
FROM jenkins_builds build
JOIN jenkins_jobs job
    ON job.job_id = build.job_id
WHERE build.started_at IS NOT NULL
  AND build.completed_at IS NOT NULL
GROUP BY job.job_name;


-- Pull Request lifecycle statistics.
SELECT
    repository_id,
    state,
    COUNT(*) AS pull_request_count
FROM pull_requests
GROUP BY repository_id, state
ORDER BY repository_id, state;


-- Webhook processing reliability.
SELECT
    event_name,
    state,
    COUNT(*) AS delivery_count,
    AVG(attempt_count) AS average_attempts
FROM webhook_deliveries
GROUP BY event_name, state
ORDER BY event_name, state;


-- ============================================================
-- 43. CTE: MERGE ELIGIBILITY EVALUATION
-- ============================================================

WITH eligibility AS (
    SELECT
        pr.pr_id,
        pr.github_pr_number,
        result.eligible,
        result.reason
    FROM pull_requests pr
    CROSS JOIN LATERAL
        evaluate_merge_eligibility(pr.pr_id) result
)
SELECT
    github_pr_number,
    BOOL_AND(eligible) AS merge_eligible,
    STRING_AGG(
        reason,
        '; ' ORDER BY reason
    ) FILTER (
        WHERE NOT eligible
    ) AS blocking_reasons
FROM eligibility
GROUP BY github_pr_number
ORDER BY github_pr_number;


-- ============================================================
-- 44. CTE: BRANCH GOVERNANCE REPORT
-- ============================================================

WITH branch_review_counts AS (
    SELECT
        pr.target_branch_id,
        COUNT(DISTINCT pr.pr_id) AS open_pull_requests
    FROM pull_requests pr
    WHERE pr.state IN ('OPEN', 'DRAFT')
    GROUP BY pr.target_branch_id
),
branch_check_counts AS (
    SELECT
        pr.target_branch_id,
        COUNT(DISTINCT sc.check_id) AS total_checks,
        COUNT(DISTINCT sc.check_id) FILTER (
            WHERE sc.state = 'SUCCESS'
        ) AS successful_checks
    FROM pull_requests pr
    LEFT JOIN status_checks sc
        ON sc.pr_id = pr.pr_id
    WHERE pr.state IN ('OPEN', 'DRAFT')
    GROUP BY pr.target_branch_id
)
SELECT
    b.branch_name,
    COALESCE(r.open_pull_requests, 0) AS open_pull_requests,
    COALESCE(c.total_checks, 0) AS total_checks,
    COALESCE(c.successful_checks, 0) AS successful_checks
FROM branches b
LEFT JOIN branch_review_counts r
    ON r.target_branch_id = b.branch_id
LEFT JOIN branch_check_counts c
    ON c.target_branch_id = b.branch_id
ORDER BY b.branch_name;


-- ============================================================
-- 45. WORKFLOW PROCESSING: WEBHOOK REGISTRATION
-- ============================================================

SELECT register_webhook_delivery(
    'github-delivery-002',
    repository_id,
    'push',
    NULL,
    REPEAT('d', 64)
)
FROM repositories
WHERE repository_name = 'payment-service';


-- Duplicate delivery returns FALSE.
SELECT register_webhook_delivery(
    'github-delivery-002',
    repository_id,
    'push',
    NULL,
    REPEAT('d', 64)
)
FROM repositories
WHERE repository_name = 'payment-service';


-- ============================================================
-- 46. WORKFLOW PROCESSING: SCM POLLING
-- ============================================================

SELECT record_scm_poll(
    branch_id,
    REPEAT('a', 40)
)
FROM branches
WHERE branch_name = 'main';


-- Changed remote commit.
SELECT record_scm_poll(
    branch_id,
    REPEAT('e', 40)
)
FROM branches
WHERE branch_name = 'main';


-- ============================================================
-- 47. WORKFLOW PROCESSING: JENKINS BUILD QUEUE
-- ============================================================

SELECT create_jenkins_build(
    job.job_id,
    job.repository_id,
    branch.branch_id,
    REPEAT('b', 40),
    'WEBHOOK',
    pr.pr_id
) AS queued_build_id
FROM jenkins_jobs job
JOIN branches branch
    ON branch.repository_id = job.repository_id
   AND branch.branch_name = 'feature/payment-validation'
JOIN pull_requests pr
    ON pr.repository_id = job.repository_id
   AND pr.github_pr_number = 101
WHERE job.job_name = 'payment-service-ci';


-- ============================================================
-- 48. ELIGIBILITY DETERMINATION
-- ============================================================

SELECT *
FROM pull_request_merge_report
ORDER BY github_pr_number;


-- Detailed blockers for PR #101.
SELECT *
FROM evaluate_merge_eligibility(
    (
        SELECT pr_id
        FROM pull_requests
        WHERE github_pr_number = 101
    )
);


-- ============================================================
-- 49. TRANSACTIONAL MERGE
-- ============================================================

-- The sample merge is deliberately not executed automatically.
-- Execute this transaction when the application has authorized
-- the merge and the PR remains eligible.
--
-- The procedure locks the PR and checks all conditions again.

-- BEGIN;
--
-- CALL merge_pull_request(
--     (
--         SELECT pr_id
--         FROM pull_requests
--         WHERE github_pr_number = 101
--     ),
--     REPEAT('f', 40),
--     'SQUASH',
--     (
--         SELECT user_id
--         FROM users
--         WHERE github_username = 'platform-admin'
--     )
-- );
--
-- COMMIT;


-- ============================================================
-- 50. FAILURE CASE DEMONSTRATION
-- ============================================================

-- The following query creates a failed check for a separate
-- PR evaluation scenario without changing the successful sample.

-- UPDATE status_checks
-- SET state = 'FAILURE'
-- WHERE pr_id = (
--     SELECT pr_id
--     FROM pull_requests
--     WHERE github_pr_number = 101
-- )
-- AND check_name = 'security-scan';


-- ============================================================
-- 51. OPERATIONAL DIAGNOSTICS
-- ============================================================

-- Failed builds.
SELECT
    job.job_name,
    build.build_number,
    build.commit_sha,
    build.failure_reason,
    build.completed_at
FROM jenkins_builds build
JOIN jenkins_jobs job
    ON job.job_id = build.job_id
WHERE build.state = 'FAILURE'
ORDER BY build.completed_at DESC;


-- Failed webhook deliveries.
SELECT
    delivery_id,
    event_name,
    attempt_count,
    error_message,
    received_at
FROM webhook_deliveries
WHERE state = 'FAILED'
ORDER BY received_at DESC;


-- Long-running builds.
SELECT
    build_id,
    build_number,
    state,
    started_at
FROM jenkins_builds
WHERE state = 'RUNNING'
  AND started_at < NOW() - INTERVAL '30 minutes';


-- ============================================================
-- 52. FINAL VALIDATION
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM repositories
        WHERE repository_name = 'payment-service'
    ) THEN
        RAISE EXCEPTION 'Sample repository missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM branch_protection_policies
    ) THEN
        RAISE EXCEPTION 'Branch protection policy missing';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pull_requests
        WHERE github_pr_number = 101
    ) THEN
        RAISE EXCEPTION 'Sample Pull Request missing';
    END IF;

    RAISE NOTICE
        'Jenkins + GitHub database initialization validated';
END;
$$;


COMMIT;

-- ============================================================
-- END OF SCRIPT
-- ============================================================
