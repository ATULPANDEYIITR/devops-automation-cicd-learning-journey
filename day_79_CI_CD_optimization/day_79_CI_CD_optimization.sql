-- ============================================================
-- CI/CD OPTIMIZATION AND ARTIFACT GOVERNANCE
-- PostgreSQL 15+
--
-- Parallel execution, caching, artifact reuse, build tracking,
-- pipeline dependencies, execution attempts, and release policy.
-- ============================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS cicd;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

SET search_path TO cicd, public;

-- ------------------------------------------------------------
-- 1. Domain types
-- ------------------------------------------------------------

CREATE TYPE pipeline_status AS ENUM (
    'pending',
    'running',
    'success',
    'failed',
    'cancelled'
);

CREATE TYPE stage_status AS ENUM (
    'pending',
    'running',
    'success',
    'cached',
    'failed',
    'blocked',
    'skipped'
);

CREATE TYPE artifact_status AS ENUM (
    'available',
    'expired',
    'quarantined'
);

CREATE TYPE execution_status AS ENUM (
    'running',
    'success',
    'failed'
);

CREATE TYPE cache_status AS ENUM (
    'hit',
    'miss',
    'invalidated'
);

-- ------------------------------------------------------------
-- 2. Repositories and source revisions
-- ------------------------------------------------------------

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_name VARCHAR(150) NOT NULL UNIQUE,
    default_branch VARCHAR(100) NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    branch_name VARCHAR(150) NOT NULL,
    head_commit VARCHAR(64) NOT NULL,
    base_branch_id BIGINT REFERENCES branches(branch_id),
    protected BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, branch_name)
);

CREATE TABLE commits (
    commit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    commit_sha VARCHAR(64) NOT NULL,
    parent_sha VARCHAR(64),
    author_name VARCHAR(150) NOT NULL,
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, commit_sha)
);

CREATE INDEX idx_commits_repository_date
    ON commits(repository_id, committed_at DESC);

-- ------------------------------------------------------------
-- 3. Pipeline definitions
-- ------------------------------------------------------------

CREATE TABLE pipelines (
    pipeline_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    pipeline_name VARCHAR(150) NOT NULL,
    pipeline_version INTEGER NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    max_parallelism INTEGER NOT NULL DEFAULT 4
        CHECK (max_parallelism BETWEEN 1 AND 256),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(repository_id, pipeline_name, pipeline_version)
);

CREATE TABLE pipeline_stages (
    stage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
    stage_name VARCHAR(100) NOT NULL,
    command TEXT NOT NULL,
    cache_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    retry_limit INTEGER NOT NULL DEFAULT 1
        CHECK (retry_limit BETWEEN 0 AND 10),
    resource_class VARCHAR(50) NOT NULL DEFAULT 'standard',
    estimated_duration_seconds INTEGER NOT NULL DEFAULT 60
        CHECK (estimated_duration_seconds > 0),
    UNIQUE(pipeline_id, stage_name)
);

CREATE TABLE stage_dependencies (
    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id) ON DELETE CASCADE,
    dependency_stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id) ON DELETE CASCADE,
    PRIMARY KEY(stage_id, dependency_stage_id),
    CHECK(stage_id <> dependency_stage_id)
);

CREATE INDEX idx_stage_dependencies_parent
    ON stage_dependencies(dependency_stage_id);

-- ------------------------------------------------------------
-- 4. Pipeline executions
-- ------------------------------------------------------------

CREATE TABLE pipeline_runs (
    run_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id),
    commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id),
    branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    status pipeline_status NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    triggered_by VARCHAR(150) NOT NULL,
    CHECK (
        completed_at IS NULL OR
        started_at IS NULL OR
        completed_at >= started_at
    )
);

CREATE INDEX idx_pipeline_runs_repository_status
    ON pipeline_runs(pipeline_id, status, started_at DESC);

CREATE INDEX idx_pipeline_runs_commit
    ON pipeline_runs(commit_id);

CREATE TABLE stage_executions (
    execution_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id BIGINT NOT NULL
        REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id),
    status stage_status NOT NULL DEFAULT 'pending',
    worker_id VARCHAR(100),
    attempt_number INTEGER NOT NULL DEFAULT 1
        CHECK (attempt_number > 0),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    UNIQUE(run_id, stage_id, attempt_number),
    CHECK (
        completed_at IS NULL OR
        started_at IS NULL OR
        completed_at >= started_at
    )
);

CREATE INDEX idx_stage_execution_schedule
    ON stage_executions(status, run_id, stage_id);

CREATE INDEX idx_stage_execution_run
    ON stage_executions(run_id, status);

-- ------------------------------------------------------------
-- 5. Content-addressed artifact storage
-- ------------------------------------------------------------

CREATE TABLE artifacts (
    artifact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_name VARCHAR(200) NOT NULL,
    content_digest CHAR(64) NOT NULL UNIQUE,
    storage_uri TEXT NOT NULL,
    artifact_size_bytes BIGINT NOT NULL
        CHECK (artifact_size_bytes >= 0),
    status artifact_status NOT NULL DEFAULT 'available',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    CHECK (
        expires_at IS NULL OR expires_at > created_at
    )
);

CREATE INDEX idx_artifacts_digest_status
    ON artifacts(content_digest, status);

CREATE TABLE execution_artifacts (
    execution_id BIGINT NOT NULL
        REFERENCES stage_executions(execution_id) ON DELETE CASCADE,
    artifact_id BIGINT NOT NULL
        REFERENCES artifacts(artifact_id),
    artifact_role VARCHAR(50) NOT NULL,
    PRIMARY KEY(execution_id, artifact_id, artifact_role)
);

-- ------------------------------------------------------------
-- 6. Cache entries
-- ------------------------------------------------------------

CREATE TABLE cache_entries (
    cache_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_key CHAR(64) NOT NULL UNIQUE,
    artifact_id BIGINT NOT NULL
        REFERENCES artifacts(artifact_id),
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id),
    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id),
    input_fingerprint CHAR(64) NOT NULL,
    toolchain_fingerprint CHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    access_count BIGINT NOT NULL DEFAULT 0
        CHECK (access_count >= 0),
    valid BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_cache_lookup
    ON cache_entries(
        cache_key,
        valid,
        last_accessed_at DESC
    );

CREATE INDEX idx_cache_artifact
    ON cache_entries(artifact_id);

CREATE TABLE cache_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pipeline_id BIGINT NOT NULL
        REFERENCES pipelines(pipeline_id),
    stage_id BIGINT NOT NULL
        REFERENCES pipeline_stages(stage_id),
    cache_key CHAR(64) NOT NULL,
    result cache_status NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_cache_events_time
    ON cache_events(occurred_at DESC, result);

-- ------------------------------------------------------------
-- 7. Pull Requests and repository governance
-- ------------------------------------------------------------

CREATE TABLE pull_requests (
    pull_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL
        REFERENCES repositories(repository_id),
    source_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    target_branch_id BIGINT NOT NULL
        REFERENCES branches(branch_id),
    source_commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id),
    target_commit_id BIGINT NOT NULL
        REFERENCES commits(commit_id),
    is_open BOOLEAN NOT NULL DEFAULT TRUE,
    is_draft BOOLEAN NOT NULL DEFAULT FALSE,
    has_conflicts BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK(source_branch_id <> target_branch_id)
);

CREATE TABLE reviewers (
    reviewer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reviewer_name VARCHAR(150) NOT NULL UNIQUE,
    eligible BOOLEAN NOT NULL DEFAULT TRUE,
    is_administrator BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE code_reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id) ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL
        REFERENCES reviewers(reviewer_id),
    review_state VARCHAR(30) NOT NULL
        CHECK (
            review_state IN (
                'approved',
                'changes_requested',
                'commented',
                'dismissed'
            )
        ),
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reviews_pull_request
    ON code_reviews(pull_request_id, review_state, stale);

CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id BIGINT NOT NULL
        REFERENCES code_reviews(review_id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER CHECK(line_number > 0),
    comment_text TEXT NOT NULL,
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE branch_protection (
    protection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch_id BIGINT NOT NULL UNIQUE
        REFERENCES branches(branch_id),
    required_approvals INTEGER NOT NULL DEFAULT 1
        CHECK(required_approvals >= 0),
    require_up_to_date BOOLEAN NOT NULL DEFAULT TRUE,
    require_resolved_conversations BOOLEAN NOT NULL DEFAULT TRUE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    allow_direct_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_force_push BOOLEAN NOT NULL DEFAULT FALSE,
    allow_deletion BOOLEAN NOT NULL DEFAULT FALSE,
    administrator_bypass BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE required_status_checks (
    protection_id BIGINT NOT NULL
        REFERENCES branch_protection(protection_id) ON DELETE CASCADE,
    check_name VARCHAR(100) NOT NULL,
    PRIMARY KEY(protection_id, check_name)
);

CREATE TABLE status_checks (
    check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL
        REFERENCES pull_requests(pull_request_id) ON DELETE CASCADE,
    check_name VARCHAR(100) NOT NULL,
    passed BOOLEAN NOT NULL,
    commit_sha VARCHAR(64) NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(pull_request_id, check_name, commit_sha)
);

CREATE TABLE merge_records (
    merge_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL UNIQUE
        REFERENCES pull_requests(pull_request_id),
    strategy VARCHAR(30) NOT NULL
        CHECK(strategy IN ('merge_commit', 'squash', 'rebase')),
    merged_by VARCHAR(150) NOT NULL,
    merged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- 8. Data integrity triggers
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION validate_stage_dependency()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    child_pipeline BIGINT;
    parent_pipeline BIGINT;
BEGIN
    SELECT pipeline_id INTO child_pipeline
    FROM pipeline_stages
    WHERE stage_id = NEW.stage_id;

    SELECT pipeline_id INTO parent_pipeline
    FROM pipeline_stages
    WHERE stage_id = NEW.dependency_stage_id;

    IF child_pipeline IS NULL OR parent_pipeline IS NULL THEN
        RAISE EXCEPTION 'Stage does not exist';
    END IF;

    IF child_pipeline <> parent_pipeline THEN
        RAISE EXCEPTION
            'Stage dependencies must belong to the same pipeline';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_stage_dependency
BEFORE INSERT OR UPDATE ON stage_dependencies
FOR EACH ROW
EXECUTE FUNCTION validate_stage_dependency();

CREATE OR REPLACE FUNCTION validate_pull_request_branches()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    source_repository BIGINT;
    target_repository BIGINT;
BEGIN
    SELECT repository_id INTO source_repository
    FROM branches
    WHERE branch_id = NEW.source_branch_id;

    SELECT repository_id INTO target_repository
    FROM branches
    WHERE branch_id = NEW.target_branch_id;

    IF source_repository <> NEW.repository_id
       OR target_repository <> NEW.repository_id THEN
        RAISE EXCEPTION
            'Pull Request branches must belong to its repository';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_pull_request_branches
BEFORE INSERT OR UPDATE ON pull_requests
FOR EACH ROW
EXECUTE FUNCTION validate_pull_request_branches();

CREATE OR REPLACE FUNCTION update_cache_access()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.valid AND NOT OLD.valid THEN
        RAISE EXCEPTION
            'Invalidated cache entries cannot be revalidated in place';
    END IF;

    NEW.last_accessed_at = now();
    NEW.access_count = OLD.access_count + 1;

    RETURN NEW;
END;
$$;

-- ------------------------------------------------------------
-- 9. Cache lookup function
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION lookup_cache(
    p_cache_key CHAR(64)
)
RETURNS TABLE (
    found BOOLEAN,
    artifact_id BIGINT,
    storage_uri TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    selected_cache cache_entries%ROWTYPE;
BEGIN
    SELECT * INTO selected_cache
    FROM cache_entries
    WHERE cache_key = p_cache_key
      AND valid = TRUE
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN QUERY
        SELECT FALSE, NULL::BIGINT, NULL::TEXT;

        RETURN;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM artifacts
        WHERE artifacts.artifact_id = selected_cache.artifact_id
          AND artifacts.status = 'available'
          AND (
              artifacts.expires_at IS NULL OR
              artifacts.expires_at > now()
          )
    ) THEN
        UPDATE cache_entries
        SET valid = FALSE
        WHERE cache_id = selected_cache.cache_id;

        RETURN QUERY
        SELECT FALSE, NULL::BIGINT, NULL::TEXT;

        RETURN;
    END IF;

    UPDATE cache_entries
    SET access_count = access_count + 1,
        last_accessed_at = now()
    WHERE cache_id = selected_cache.cache_id;

    RETURN QUERY
    SELECT
        TRUE,
        a.artifact_id,
        a.storage_uri
    FROM artifacts a
    WHERE a.artifact_id = selected_cache.artifact_id;
END;
$$;

-- ------------------------------------------------------------
-- 10. Cache invalidation
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE invalidate_stage_cache(
    p_stage_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE cache_entries
    SET valid = FALSE
    WHERE stage_id = p_stage_id
      AND valid = TRUE;

    INSERT INTO cache_events(
        pipeline_id,
        stage_id,
        cache_key,
        result
    )
    SELECT
        pipeline_id,
        stage_id,
        cache_key,
        'invalidated'
    FROM cache_entries
    WHERE stage_id = p_stage_id
      AND NOT valid;
END;
$$;

-- ------------------------------------------------------------
-- 11. Dependency-aware execution scheduling
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION ready_stages(
    p_run_id BIGINT
)
RETURNS TABLE (
    stage_id BIGINT,
    stage_name VARCHAR,
    estimated_duration_seconds INTEGER
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        s.stage_id,
        s.stage_name,
        s.estimated_duration_seconds
    FROM pipeline_stages s
    JOIN pipeline_runs r
      ON r.pipeline_id = s.pipeline_id
    LEFT JOIN stage_executions e
      ON e.stage_id = s.stage_id
     AND e.run_id = r.run_id
     AND e.attempt_number = (
         SELECT MAX(e2.attempt_number)
         FROM stage_executions e2
         WHERE e2.run_id = r.run_id
           AND e2.stage_id = s.stage_id
     )
    WHERE r.run_id = p_run_id
      AND r.status IN ('pending', 'running')
      AND COALESCE(e.status, 'pending'::stage_status) = 'pending'
      AND NOT EXISTS (
          SELECT 1
          FROM stage_dependencies d
          LEFT JOIN stage_executions parent
            ON parent.stage_id = d.dependency_stage_id
           AND parent.run_id = r.run_id
           AND parent.attempt_number = (
               SELECT MAX(parent2.attempt_number)
               FROM stage_executions parent2
               WHERE parent2.run_id = r.run_id
                 AND parent2.stage_id = d.dependency_stage_id
           )
          WHERE d.stage_id = s.stage_id
            AND COALESCE(
                parent.status,
                'pending'::stage_status
            ) NOT IN ('success', 'cached')
      )
    ORDER BY s.estimated_duration_seconds DESC;
$$;

-- ------------------------------------------------------------
-- 12. Execution initialization
-- ------------------------------------------------------------

CREATE OR REPLACE PROCEDURE initialize_pipeline_run(
    p_run_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    run_pipeline BIGINT;
    existing_status pipeline_status;
BEGIN
    SELECT pipeline_id, status
    INTO run_pipeline, existing_status
    FROM pipeline_runs
    WHERE run_id = p_run_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Pipeline run not found';
    END IF;

    IF existing_status <> 'pending' THEN
        RAISE EXCEPTION
            'Only pending pipeline runs can be initialized';
    END IF;

    INSERT INTO stage_executions(
        run_id,
        stage_id,
        status,
        attempt_number
    )
    SELECT
        p_run_id,
        stage_id,
        'pending',
        1
    FROM pipeline_stages
    WHERE pipeline_id = run_pipeline;

    UPDATE pipeline_runs
    SET status = 'running',
        started_at = now()
    WHERE run_id = p_run_id;
END;
$$;

-- ------------------------------------------------------------
-- 13. Merge eligibility evaluation
-- ------------------------------------------------------------

CREATE OR REPLACE FUNCTION evaluate_merge_eligibility(
    p_pull_request_id BIGINT
)
RETURNS TABLE (
    eligible BOOLEAN,
    violation TEXT
)
LANGUAGE sql
STABLE
AS $$
    WITH pr AS (
        SELECT *
        FROM pull_requests
        WHERE pull_request_id = p_pull_request_id
    ),
    protection AS (
        SELECT bp.*
        FROM branch_protection bp
        JOIN pr ON pr.target_branch_id = bp.branch_id
    ),
    approval_count AS (
        SELECT COUNT(DISTINCT cr.reviewer_id) AS total
        FROM code_reviews cr
        JOIN reviewers rv
          ON rv.reviewer_id = cr.reviewer_id
        WHERE cr.pull_request_id = p_pull_request_id
          AND cr.review_state = 'approved'
          AND cr.stale = FALSE
          AND rv.eligible = TRUE
          AND rv.is_administrator = FALSE
    ),
    unresolved AS (
        SELECT COUNT(*) AS total
        FROM review_comments rc
        JOIN code_reviews cr
          ON cr.review_id = rc.review_id
        WHERE cr.pull_request_id = p_pull_request_id
          AND rc.resolved = FALSE
    ),
    missing_checks AS (
        SELECT rsc.check_name
        FROM protection bp
        JOIN required_status_checks rsc
          ON rsc.protection_id = bp.protection_id
        LEFT JOIN status_checks sc
          ON sc.pull_request_id = p_pull_request_id
         AND sc.check_name = rsc.check_name
         AND sc.passed = TRUE
         AND sc.commit_sha = (
             SELECT c.commit_sha
             FROM commits c
             JOIN pr ON pr.source_commit_id = c.commit_id
         )
        WHERE sc.check_id IS NULL
    ),
    violations AS (
        SELECT 'Pull Request does not exist'::TEXT AS reason
        WHERE NOT EXISTS (SELECT 1 FROM pr)

        UNION ALL

        SELECT 'Pull Request is closed'
        FROM pr WHERE NOT is_open

        UNION ALL

        SELECT 'Draft Pull Request cannot be merged'
        FROM pr WHERE is_draft

        UNION ALL

        SELECT 'Merge conflicts exist'
        FROM pr WHERE has_conflicts

        UNION ALL

        SELECT 'Insufficient eligible approvals'
        FROM protection bp, approval_count ac
        WHERE ac.total < bp.required_approvals

        UNION ALL

        SELECT 'Unresolved review conversations'
        FROM protection bp, unresolved u
        WHERE bp.require_resolved_conversations
          AND u.total > 0

        UNION ALL

        SELECT 'Required status check failed: ' || check_name
        FROM missing_checks

        UNION ALL

        SELECT 'Source branch is behind target'
        FROM pr
        JOIN commits source_commit
          ON source_commit.commit_id = pr.source_commit_id
        JOIN commits target_commit
          ON target_commit.commit_id = pr.target_commit_id
        JOIN protection bp ON TRUE
        WHERE bp.require_up_to_date
          AND source_commit.committed_at < target_commit.committed_at
    )
    SELECT
        NOT EXISTS (SELECT 1 FROM violations),
        reason
    FROM violations

    UNION ALL

    SELECT TRUE, NULL::TEXT
    WHERE NOT EXISTS (SELECT 1 FROM violations);
$$;

-- ------------------------------------------------------------
-- 14. Reporting views
-- ------------------------------------------------------------

CREATE OR REPLACE VIEW pipeline_performance AS
SELECT
    p.pipeline_id,
    p.pipeline_name,
    COUNT(DISTINCT r.run_id) AS total_runs,
    COUNT(DISTINCT r.run_id)
        FILTER (WHERE r.status = 'success') AS successful_runs,
    COUNT(DISTINCT r.run_id)
        FILTER (WHERE r.status = 'failed') AS failed_runs,
    ROUND(
        100.0 *
        COUNT(DISTINCT r.run_id)
            FILTER (WHERE r.status = 'success') /
        NULLIF(COUNT(DISTINCT r.run_id), 0),
        2
    ) AS success_percentage
FROM pipelines p
LEFT JOIN pipeline_runs r
  ON r.pipeline_id = p.pipeline_id
GROUP BY p.pipeline_id, p.pipeline_name;

CREATE OR REPLACE VIEW stage_performance AS
SELECT
    s.stage_id,
    s.stage_name,
    COUNT(e.execution_id) AS total_executions,
    COUNT(*) FILTER (
        WHERE e.status = 'cached'
    ) AS cached_executions,
    COUNT(*) FILTER (
        WHERE e.status = 'success'
    ) AS successful_executions,
    COUNT(*) FILTER (
        WHERE e.status = 'failed'
    ) AS failed_executions,
    ROUND(
        100.0 *
        COUNT(*) FILTER (WHERE e.status = 'cached') /
        NULLIF(COUNT(e.execution_id), 0),
        2
    ) AS cache_hit_percentage
FROM pipeline_stages s
LEFT JOIN stage_executions e
  ON e.stage_id = s.stage_id
GROUP BY s.stage_id, s.stage_name;

CREATE OR REPLACE VIEW cache_performance AS
SELECT
    pipeline_id,
    COUNT(*) AS total_events,
    COUNT(*) FILTER (
        WHERE result = 'hit'
    ) AS cache_hits,
    COUNT(*) FILTER (
        WHERE result = 'miss'
    ) AS cache_misses,
    COUNT(*) FILTER (
        WHERE result = 'invalidated'
    ) AS invalidations,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE result = 'hit') /
        NULLIF(COUNT(*), 0),
        2
    ) AS hit_percentage
FROM cache_events
GROUP BY pipeline_id;

COMMIT;

-- ============================================================
-- 15. REALISTIC SAMPLE DATA
-- ============================================================

BEGIN;

INSERT INTO repositories(repository_name, default_branch)
VALUES ('enterprise-platform', 'main');

INSERT INTO branches(
    repository_id,
    branch_name,
    head_commit,
    protected
)
VALUES
    (1, 'main', repeat('a', 40), TRUE),
    (1, 'feature/parallel-build', repeat('b', 40), FALSE);

INSERT INTO commits(
    repository_id,
    commit_sha,
    parent_sha,
    author_name
)
VALUES
    (1, repeat('a', 40), NULL, 'release-manager'),
    (1, repeat('b', 40), repeat('a', 40), 'developer-1');

INSERT INTO pipelines(
    repository_id,
    pipeline_name,
    pipeline_version,
    max_parallelism
)
VALUES (1, 'production-ci', 1, 4);

INSERT INTO pipeline_stages(
    pipeline_id,
    stage_name,
    command,
    cache_enabled,
    retry_limit,
    estimated_duration_seconds
)
VALUES
    (1, 'checkout', 'git checkout', FALSE, 0, 5),
    (1, 'build', 'compile application', TRUE, 1, 120),
    (1, 'lint', 'static analysis', TRUE, 0, 40),
    (1, 'unit-tests', 'run unit tests', TRUE, 1, 90),
    (1, 'integration-tests', 'run integration tests', TRUE, 1, 180),
    (1, 'security', 'dependency and source scan', TRUE, 1, 100),
    (1, 'package', 'create immutable package', TRUE, 1, 60),
    (1, 'deploy', 'deploy to staging', FALSE, 0, 45);

INSERT INTO stage_dependencies(stage_id, dependency_stage_id)
VALUES
    (2, 1),
    (3, 1),
    (4, 2),
    (5, 2),
    (6, 1),
    (7, 3),
    (7, 4),
    (7, 5),
    (7, 6),
    (8, 7);

INSERT INTO pipeline_runs(
    pipeline_id,
    commit_id,
    branch_id,
    status,
    started_at,
    triggered_by
)
VALUES
    (1, 2, 2, 'success', now() - interval '15 minutes', 'developer-1'),
    (1, 2, 2, 'failed', now() - interval '5 minutes', 'developer-1');

INSERT INTO stage_executions(
    run_id,
    stage_id,
    status,
    attempt_number,
    started_at,
    completed_at
)
VALUES
    (1, 1, 'success', 1, now() - interval '15 minutes',
        now() - interval '14 minutes'),
    (1, 2, 'success', 1, now() - interval '14 minutes',
        now() - interval '12 minutes'),
    (1, 3, 'success', 1, now() - interval '14 minutes',
        now() - interval '13 minutes'),
    (1, 4, 'success', 1, now() - interval '12 minutes',
        now() - interval '11 minutes'),
    (1, 5, 'success', 1, now() - interval '12 minutes',
        now() - interval '9 minutes'),
    (1, 6, 'success', 1, now() - interval '14 minutes',
        now() - interval '12 minutes'),
    (1, 7, 'success', 1, now() - interval '9 minutes',
        now() - interval '8 minutes'),
    (1, 8, 'success', 1, now() - interval '8 minutes',
        now() - interval '7 minutes'),
    (2, 1, 'success', 1, now() - interval '5 minutes',
        now() - interval '4 minutes'),
    (2, 2, 'failed', 1, now() - interval '4 minutes',
        now() - interval '3 minutes');

INSERT INTO artifacts(
    artifact_name,
    content_digest,
    storage_uri,
    artifact_size_bytes
)
VALUES
    ('application-binary',
     encode(digest('binary-v1', 'sha256'), 'hex'),
     's3://enterprise-artifacts/build/binary-v1',
     2048000),
    ('release-package',
     encode(digest('package-v1', 'sha256'), 'hex'),
     's3://enterprise-artifacts/release/package-v1',
     4096000);

INSERT INTO execution_artifacts(
    execution_id,
    artifact_id,
    artifact_role
)
VALUES
    (2, 1, 'build-output'),
    (8, 2, 'release-package');

INSERT INTO cache_entries(
    cache_key,
    artifact_id,
    pipeline_id,
    stage_id,
    input_fingerprint,
    toolchain_fingerprint
)
VALUES
    (
        encode(digest('build-key-v1', 'sha256'), 'hex'),
        1,
        1,
        2,
        encode(digest('source-b', 'sha256'), 'hex'),
        encode(digest('gcc-14-release', 'sha256'), 'hex')
    ),
    (
        encode(digest('package-key-v1', 'sha256'), 'hex'),
        2,
        1,
        7,
        encode(digest('package-inputs', 'sha256'), 'hex'),
        encode(digest('tar-v1', 'sha256'), 'hex')
    );

INSERT INTO cache_events(
    pipeline_id,
    stage_id,
    cache_key,
    result
)
VALUES
    (1, 2, encode(digest('build-key-v1', 'sha256'), 'hex'), 'hit'),
    (1, 3, encode(digest('lint-key-v1', 'sha256'), 'hex'), 'miss'),
    (1, 4, encode(digest('unit-key-v1', 'sha256'), 'hex'), 'hit'),
    (1, 5, encode(digest('integration-key-v1', 'sha256'), 'hex'), 'miss'),
    (1, 7, encode(digest('package-key-v1', 'sha256'), 'hex'), 'hit');

INSERT INTO reviewers(reviewer_name, eligible, is_administrator)
VALUES
    ('reviewer-1', TRUE, FALSE),
    ('reviewer-2', TRUE, FALSE),
    ('developer-1', TRUE, FALSE),
    ('admin-1', TRUE, TRUE);

INSERT INTO pull_requests(
    repository_id,
    source_branch_id,
    target_branch_id,
    source_commit_id,
    target_commit_id,
    is_open,
    is_draft,
    has_conflicts
)
VALUES
    (1, 2, 1, 2, 1, TRUE, FALSE, FALSE);

INSERT INTO branch_protection(
    branch_id,
    required_approvals,
    require_up_to_date,
    require_resolved_conversations,
    require_linear_history,
    allow_direct_push,
    allow_force_push,
    allow_deletion,
    administrator_bypass
)
VALUES (1, 2, TRUE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE);

INSERT INTO required_status_checks(protection_id, check_name)
VALUES
    (1, 'build'),
    (1, 'unit-tests'),
    (1, 'integration-tests'),
    (1, 'security');

INSERT INTO code_reviews(
    pull_request_id,
    reviewer_id,
    review_state,
    stale
)
VALUES
    (1, 1, 'approved', FALSE),
    (1, 2, 'approved', FALSE),
    (1, 3, 'approved', FALSE);

INSERT INTO review_comments(
    review_id,
    file_path,
    line_number,
    comment_text,
    resolved
)
VALUES
    (1, 'src/build.cpp', 42, 'Build configuration verified', TRUE),
    (2, 'src/pipeline.cpp', 85, 'Dependency ordering verified', TRUE);

INSERT INTO status_checks(
    pull_request_id,
    check_name,
    passed,
    commit_sha
)
VALUES
    (1, 'build', TRUE, repeat('b', 40)),
    (1, 'unit-tests', TRUE, repeat('b', 40)),
    (1, 'integration-tests', TRUE, repeat('b', 40)),
    (1, 'security', TRUE, repeat('b', 40));

COMMIT;

-- ============================================================
-- 16. RETRIEVAL AND VALIDATION QUERIES
-- ============================================================

-- Inspect pipeline stages and dependency relationships.

SELECT
    s.stage_name,
    d.stage_name AS dependency,
    s.estimated_duration_seconds
FROM pipeline_stages s
LEFT JOIN stage_dependencies sd
    ON sd.stage_id = s.stage_id
LEFT JOIN pipeline_stages d
    ON d.stage_id = sd.dependency_stage_id
ORDER BY s.stage_id, d.stage_id;

-- Find stages that can start immediately.

SELECT *
FROM ready_stages(1);

-- Find failed executions and their errors.

SELECT
    run_id,
    stage_id,
    attempt_number,
    status,
    error_message
FROM stage_executions
WHERE status = 'failed'
ORDER BY run_id, stage_id;

-- Inspect reusable artifacts.

SELECT
    a.artifact_name,
    a.content_digest,
    a.storage_uri,
    a.status,
    ce.valid,
    ce.access_count
FROM artifacts a
JOIN cache_entries ce
    ON ce.artifact_id = a.artifact_id
ORDER BY ce.last_accessed_at DESC;

-- ============================================================
-- 17. AGGREGATION AND PERFORMANCE REPORTING
-- ============================================================

SELECT * FROM pipeline_performance;

SELECT * FROM stage_performance;

SELECT * FROM cache_performance;

-- Identify expensive stages and parallelization candidates.

SELECT
    stage_name,
    estimated_duration_seconds,
    retry_limit,
    resource_class
FROM pipeline_stages
WHERE pipeline_id = 1
ORDER BY estimated_duration_seconds DESC;

-- Calculate theoretical sequential workload duration.

SELECT
    SUM(estimated_duration_seconds)
        AS sequential_duration_seconds
FROM pipeline_stages
WHERE pipeline_id = 1;

-- ============================================================
-- 18. CACHE LOOKUP DEMONSTRATION
-- ============================================================

SELECT *
FROM lookup_cache(
    encode(digest('build-key-v1', 'sha256'), 'hex')
);

SELECT *
FROM lookup_cache(
    encode(digest('unknown-key', 'sha256'), 'hex')
);

-- ============================================================
-- 19. MERGE ELIGIBILITY REPORT
-- ============================================================

SELECT *
FROM evaluate_merge_eligibility(1);

-- Show reviewer decisions separately from branch enforcement.

SELECT
    rv.reviewer_name,
    rv.eligible,
    rv.is_administrator,
    cr.review_state,
    cr.stale
FROM code_reviews cr
JOIN reviewers rv
    ON rv.reviewer_id = cr.reviewer_id
WHERE cr.pull_request_id = 1;

-- ============================================================
-- 20. TRANSACTIONAL CACHE INVALIDATION
-- ============================================================

BEGIN;

CALL invalidate_stage_cache(2);

SELECT
    cache_key,
    valid
FROM cache_entries
WHERE stage_id = 2;

COMMIT;

-- ============================================================
-- 21. SECURITY AND DATA INTEGRITY EXAMPLES
-- ============================================================

-- The following invalid records are intentionally not inserted.
-- Their constraints demonstrate rejected operations:
--
-- 1. Negative retry limits.
-- 2. Zero or negative worker concurrency.
-- 3. Self-dependent pipeline stages.
-- 4. Cross-pipeline stage dependencies.
-- 5. Pull Requests with branches from another repository.
-- 6. Negative artifact sizes.
-- 7. Duplicate cache keys.
-- 8. Invalid review states.
-- 9. Duplicate merge records.
--
-- Production deployment should also enforce:
-- - Separate CI execution and database service accounts.
-- - Least-privilege database permissions.
-- - Encrypted artifact storage.
-- - Signed artifact provenance.
-- - External secret management.
-- - Retention and cleanup policies.
-- - Atomic cache publication.
-- - Isolation of untrusted build workers.
-- - Database backups and audit retention.
