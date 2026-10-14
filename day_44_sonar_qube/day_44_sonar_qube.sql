-- PostgreSQL 15+ compatible educational model.
-- SonarQube-inspired quality metrics, technical debt, quality gates,
-- analysis snapshots, and CI enforcement for protected branches.
--
-- Execute in a dedicated learning database. The script creates a schema
-- and replaces its objects so that repeated runs are deterministic.

BEGIN;

DROP SCHEMA IF EXISTS quality_lab CASCADE;
CREATE SCHEMA quality_lab;
SET search_path TO quality_lab, public;

CREATE TYPE issue_type AS ENUM (
    'BUG',
    'VULNERABILITY',
    'CODE_SMELL',
    'SECURITY_HOTSPOT'
);

CREATE TYPE issue_severity AS ENUM (
    'BLOCKER',
    'CRITICAL',
    'MAJOR',
    'MINOR',
    'INFO'
);

CREATE TYPE analysis_state AS ENUM (
    'SUCCESS',
    'FAILED',
    'IN_PROGRESS'
);

CREATE TYPE gate_state AS ENUM (
    'OK',
    'ERROR',
    'NO_ANALYSIS'
);

CREATE TYPE review_state AS ENUM (
    'COMMENTED',
    'APPROVED',
    'CHANGES_REQUESTED',
    'DISMISSED'
);

CREATE TYPE pull_request_state AS ENUM (
    'DRAFT',
    'OPEN',
    'CLOSED',
    'MERGED'
);

CREATE TABLE repositories (
    repository_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_key TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    default_branch TEXT NOT NULL DEFAULT 'main',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (btrim(repository_key) <> ''),
    CHECK (btrim(default_branch) <> '')
);

CREATE TABLE repository_branches (
    branch_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_name TEXT NOT NULL,
    head_commit TEXT NOT NULL,
    is_protected BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at TIMESTAMPTZ,
    UNIQUE (repository_id, branch_name),
    CHECK (btrim(branch_name) <> ''),
    CHECK (btrim(head_commit) <> '')
);

CREATE TABLE developers (
    developer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (btrim(username) <> '')
);

CREATE TABLE repository_members (
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    developer_id BIGINT NOT NULL REFERENCES developers(developer_id)
        ON DELETE CASCADE,
    can_review BOOLEAN NOT NULL DEFAULT TRUE,
    is_code_owner BOOLEAN NOT NULL DEFAULT FALSE,
    can_bypass_protection BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (repository_id, developer_id)
);

CREATE TABLE quality_profiles (
    profile_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    profile_name TEXT NOT NULL UNIQUE,
    language TEXT NOT NULL,
    version_label TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (btrim(profile_name) <> '')
);

CREATE TABLE analysis_runs (
    analysis_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    branch_id BIGINT NOT NULL REFERENCES repository_branches(branch_id),
    profile_id BIGINT NOT NULL REFERENCES quality_profiles(profile_id),
    commit_sha TEXT NOT NULL,
    base_commit_sha TEXT,
    state analysis_state NOT NULL DEFAULT 'IN_PROGRESS',
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_lines INTEGER NOT NULL,
    covered_lines INTEGER NOT NULL,
    duplicated_lines INTEGER NOT NULL,
    new_lines INTEGER NOT NULL,
    new_covered_lines INTEGER NOT NULL,
    new_duplicated_lines INTEGER NOT NULL,
    analysis_error TEXT,
    UNIQUE (repository_id, branch_id, commit_sha),
    CHECK (btrim(commit_sha) <> ''),
    CHECK (total_lines >= 0 AND covered_lines >= 0),
    CHECK (duplicated_lines >= 0 AND new_lines >= 0),
    CHECK (new_covered_lines >= 0 AND new_duplicated_lines >= 0),
    CHECK (covered_lines <= total_lines),
    CHECK (duplicated_lines <= total_lines),
    CHECK (new_covered_lines <= new_lines),
    CHECK (new_duplicated_lines <= new_lines),
    CHECK (
        (state = 'FAILED' AND analysis_error IS NOT NULL)
        OR state <> 'FAILED'
    )
);

CREATE INDEX idx_analysis_branch_latest
    ON analysis_runs(repository_id, branch_id, analyzed_at DESC);

CREATE TABLE quality_issues (
    issue_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    issue_key TEXT NOT NULL,
    component_path TEXT NOT NULL,
    rule_key TEXT NOT NULL,
    issue_kind issue_type NOT NULL,
    severity issue_severity NOT NULL,
    message TEXT NOT NULL,
    remediation_minutes INTEGER NOT NULL,
    first_analysis_id BIGINT NOT NULL REFERENCES analysis_runs(analysis_id),
    line_number INTEGER NOT NULL,
    introduced_in_change BOOLEAN NOT NULL DEFAULT TRUE,
    resolved_at TIMESTAMPTZ,
    UNIQUE (repository_id, issue_key),
    CHECK (btrim(issue_key) <> ''),
    CHECK (btrim(component_path) <> ''),
    CHECK (remediation_minutes >= 0),
    CHECK (line_number > 0)
);

CREATE INDEX idx_active_issues_repository
    ON quality_issues(repository_id, issue_kind, severity)
    WHERE resolved_at IS NULL;

CREATE TABLE security_hotspot_reviews (
    hotspot_review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issue_id BIGINT NOT NULL REFERENCES quality_issues(issue_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES developers(developer_id),
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    disposition TEXT NOT NULL CHECK (
        disposition IN ('SAFE', 'FIX_REQUIRED', 'ACKNOWLEDGED_RISK')
    ),
    rationale TEXT NOT NULL CHECK (btrim(rationale) <> '')
);

CREATE TABLE pull_requests (
    pull_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    source_branch_id BIGINT NOT NULL REFERENCES repository_branches(branch_id),
    target_branch_id BIGINT NOT NULL REFERENCES repository_branches(branch_id),
    author_id BIGINT NOT NULL REFERENCES developers(developer_id),
    title TEXT NOT NULL,
    state pull_request_state NOT NULL DEFAULT 'OPEN',
    head_commit TEXT NOT NULL,
    analyzed_commit TEXT,
    analysis_id BIGINT REFERENCES analysis_runs(analysis_id),
    is_draft BOOLEAN NOT NULL DEFAULT FALSE,
    has_conflicts BOOLEAN NOT NULL DEFAULT FALSE,
    conversations_resolved BOOLEAN NOT NULL DEFAULT FALSE,
    linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    merged_at TIMESTAMPTZ,
    CHECK (btrim(title) <> ''),
    CHECK (btrim(head_commit) <> ''),
    CHECK (source_branch_id <> target_branch_id),
    CHECK (state <> 'MERGED' OR merged_at IS NOT NULL),
    CHECK (NOT is_draft OR state IN ('DRAFT', 'CLOSED'))
);

CREATE INDEX idx_open_pull_requests
    ON pull_requests(repository_id, target_branch_id, created_at DESC)
    WHERE state IN ('DRAFT', 'OPEN');

CREATE TABLE pull_request_commits (
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    commit_sha TEXT NOT NULL,
    parent_commit_sha TEXT,
    sequence_number INTEGER NOT NULL,
    added_lines INTEGER NOT NULL DEFAULT 0,
    deleted_lines INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (pull_request_id, commit_sha),
    UNIQUE (pull_request_id, sequence_number),
    CHECK (sequence_number > 0),
    CHECK (added_lines >= 0 AND deleted_lines >= 0)
);

CREATE TABLE pull_request_reviews (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    reviewer_id BIGINT NOT NULL REFERENCES developers(developer_id),
    reviewed_commit TEXT NOT NULL,
    state review_state NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_code_owner_review BOOLEAN NOT NULL DEFAULT FALSE,
    review_body TEXT,
    CHECK (btrim(reviewed_commit) <> '')
);

CREATE INDEX idx_reviews_for_pull_request
    ON pull_request_reviews(pull_request_id, submitted_at DESC);

CREATE TABLE review_comments (
    comment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    review_id BIGINT NOT NULL REFERENCES pull_request_reviews(review_id)
        ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    body TEXT NOT NULL,
    is_inline BOOLEAN NOT NULL DEFAULT TRUE,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (btrim(file_path) <> ''),
    CHECK (line_number IS NULL OR line_number > 0),
    CHECK (btrim(body) <> '')
);

CREATE INDEX idx_unresolved_review_comments
    ON review_comments(review_id)
    WHERE resolved_at IS NULL;

CREATE TABLE pull_request_status_checks (
    status_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(pull_request_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    details TEXT,
    UNIQUE (pull_request_id, check_name, commit_sha),
    CHECK (btrim(check_name) <> '')
);

CREATE TABLE branch_protection_policies (
    policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id)
        ON DELETE CASCADE,
    branch_pattern TEXT NOT NULL,
    required_approvals INTEGER NOT NULL DEFAULT 1,
    require_code_owner BOOLEAN NOT NULL DEFAULT FALSE,
    require_linear_history BOOLEAN NOT NULL DEFAULT FALSE,
    disallow_direct_push BOOLEAN NOT NULL DEFAULT TRUE,
    disallow_force_push BOOLEAN NOT NULL DEFAULT TRUE,
    disallow_deletion BOOLEAN NOT NULL DEFAULT TRUE,
    require_resolved_conversations BOOLEAN NOT NULL DEFAULT TRUE,
    allow_administrator_bypass BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (repository_id, branch_pattern),
    CHECK (required_approvals >= 0),
    CHECK (btrim(branch_pattern) <> '')
);

CREATE TABLE required_status_checks (
    policy_id BIGINT NOT NULL REFERENCES branch_protection_policies(policy_id)
        ON DELETE CASCADE,
    check_name TEXT NOT NULL,
    PRIMARY KEY (policy_id, check_name),
    CHECK (btrim(check_name) <> '')
);

CREATE TABLE quality_gates (
    gate_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gate_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    CHECK (btrim(gate_name) <> '')
);

CREATE TABLE quality_gate_conditions (
    condition_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gate_id BIGINT NOT NULL REFERENCES quality_gates(gate_id)
        ON DELETE CASCADE,
    metric_key TEXT NOT NULL,
    comparison_operator TEXT NOT NULL CHECK (
        comparison_operator IN ('>', '>=', '<', '<=', '=', '!=')
    ),
    threshold NUMERIC(12, 3) NOT NULL,
    metric_scope TEXT NOT NULL CHECK (
        metric_scope IN ('NEW_CODE', 'OVERALL')
    ),
    description TEXT NOT NULL,
    UNIQUE (gate_id, metric_key, metric_scope),
    CHECK (btrim(metric_key) <> '')
);

CREATE TABLE quality_gate_evaluations (
    evaluation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    analysis_id BIGINT NOT NULL REFERENCES analysis_runs(analysis_id),
    gate_id BIGINT NOT NULL REFERENCES quality_gates(gate_id),
    status gate_state NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    failure_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (analysis_id, gate_id),
    CHECK (failure_count >= 0),
    CHECK (
        (status = 'OK' AND failure_count = 0)
        OR status <> 'OK'
    )
);

CREATE TABLE quality_gate_condition_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    evaluation_id BIGINT NOT NULL
        REFERENCES quality_gate_evaluations(evaluation_id)
        ON DELETE CASCADE,
    condition_id BIGINT NOT NULL
        REFERENCES quality_gate_conditions(condition_id),
    actual_value NUMERIC(12, 3) NOT NULL,
    passed BOOLEAN NOT NULL,
    UNIQUE (evaluation_id, condition_id)
);

-- A completed analysis cannot claim coverage beyond its source denominator.
-- The table checks above also prevent impossible new-code metric counts.

INSERT INTO repositories (repository_key, display_name)
VALUES ('payments-service', 'Payments Service');

INSERT INTO developers (username, display_name)
VALUES
    ('atul-dev', 'Application Developer'),
    ('reviewer-lee', 'Senior Reviewer'),
    ('security-owner', 'Security Code Owner'),
    ('ci-service', 'Continuous Integration Service');

INSERT INTO repository_members (
    repository_id, developer_id, can_review, is_code_owner, can_bypass_protection
)
SELECT r.repository_id, d.developer_id,
       d.username <> 'ci-service',
       d.username = 'security-owner',
       FALSE
FROM repositories r
CROSS JOIN developers d
WHERE r.repository_key = 'payments-service';

INSERT INTO repository_branches (
    repository_id, branch_name, head_commit, is_protected
)
SELECT repository_id, 'main', 'base-90b31', TRUE
FROM repositories
WHERE repository_key = 'payments-service';

INSERT INTO repository_branches (
    repository_id, branch_name, head_commit, is_protected
)
SELECT repository_id, 'feature/parameterized-query', 'commit-c7f91ad', FALSE
FROM repositories
WHERE repository_key = 'payments-service';

INSERT INTO quality_profiles (profile_name, language, version_label)
VALUES ('Python Production Profile', 'Python', '2026.1');

INSERT INTO quality_gates (gate_name, description)
VALUES (
    'Production Gate',
    'Reject unsafe changes, low new-code coverage, and excessive duplication.'
);

INSERT INTO quality_gate_conditions (
    gate_id, metric_key, comparison_operator, threshold,
    metric_scope, description
)
SELECT gate_id, condition.metric_key, condition.operator,
       condition.threshold, condition.scope, condition.description
FROM quality_gates
CROSS JOIN (
    VALUES
        ('new_coverage_percent', '>=', 80.000, 'NEW_CODE',
         'New-code coverage must reach 80 percent.'),
        ('new_duplicated_lines_percent', '<=', 3.000, 'NEW_CODE',
         'New-code duplication must not exceed 3 percent.'),
        ('new_bugs', '=', 0.000, 'NEW_CODE',
         'No new bugs are permitted.'),
        ('new_vulnerabilities', '=', 0.000, 'NEW_CODE',
         'No new vulnerabilities are permitted.'),
        ('new_blocker_issues', '=', 0.000, 'NEW_CODE',
         'No new blocker issues are permitted.')
) AS condition(metric_key, operator, threshold, scope, description)
WHERE gate_name = 'Production Gate';

INSERT INTO branch_protection_policies (
    repository_id, branch_pattern, required_approvals,
    require_code_owner, require_linear_history,
    disallow_direct_push, disallow_force_push,
    disallow_deletion, require_resolved_conversations,
    allow_administrator_bypass
)
SELECT repository_id, 'main', 2, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE, FALSE
FROM repositories
WHERE repository_key = 'payments-service';

INSERT INTO required_status_checks (policy_id, check_name)
SELECT policy_id, check_name
FROM branch_protection_policies
CROSS JOIN (
    VALUES ('build-linux'), ('unit-tests'), ('dependency-audit')
) AS checks(check_name)
WHERE branch_pattern = 'main';

INSERT INTO analysis_runs (
    repository_id, branch_id, profile_id, commit_sha, base_commit_sha,
    state, total_lines, covered_lines, duplicated_lines,
    new_lines, new_covered_lines, new_duplicated_lines
)
SELECT r.repository_id, b.branch_id, p.profile_id,
       'commit-c7f91ad', 'base-90b31', 'SUCCESS',
       1800, 1450, 45, 80, 68, 1
FROM repositories r
JOIN repository_branches b
  ON b.repository_id = r.repository_id
 AND b.branch_name = 'feature/parameterized-query'
JOIN quality_profiles p
  ON p.profile_name = 'Python Production Profile'
WHERE r.repository_key = 'payments-service';

INSERT INTO quality_issues (
    repository_id, issue_key, component_path, rule_key,
    issue_kind, severity, message, remediation_minutes,
    first_analysis_id, line_number, introduced_in_change
)
SELECT r.repository_id, issue.issue_key, issue.component_path, issue.rule_key,
       issue.issue_kind::issue_type, issue.severity::issue_severity,
       issue.message, issue.remediation_minutes,
       a.analysis_id, issue.line_number, issue.is_new
FROM repositories r
JOIN analysis_runs a ON a.repository_id = r.repository_id
CROSS JOIN (
    VALUES
        ('PAY-101', 'src/payment_service.py', 'python:S3776',
         'CODE_SMELL', 'MAJOR',
         'Reduce complexity in payment authorization.',
         40, 91, TRUE),
        ('PAY-102', 'src/payment_repository.py', 'python:S3649',
         'VULNERABILITY', 'CRITICAL',
         'Use parameterized database queries.',
         90, 143, TRUE),
        ('PAY-103', 'src/legacy_adapter.py', 'python:S1481',
         'CODE_SMELL', 'MINOR',
         'Remove the existing unused variable.',
         15, 28, FALSE),
        ('PAY-104', 'src/crypto_adapter.py', 'python:S4787',
         'SECURITY_HOTSPOT', 'MAJOR',
         'Review cryptographic construction and key handling.',
         30, 66, FALSE)
) AS issue(
    issue_key, component_path, rule_key, issue_kind, severity,
    message, remediation_minutes, line_number, is_new
)
WHERE r.repository_key = 'payments-service'
  AND a.commit_sha = 'commit-c7f91ad';

INSERT INTO security_hotspot_reviews (
    issue_id, reviewer_id, disposition, rationale
)
SELECT i.issue_id, d.developer_id, 'ACKNOWLEDGED_RISK',
       'The cryptographic construction requires a documented security decision.'
FROM quality_issues i
JOIN repositories r ON r.repository_id = i.repository_id
JOIN developers d ON d.username = 'security-owner'
WHERE r.repository_key = 'payments-service'
  AND i.issue_key = 'PAY-104';

INSERT INTO pull_requests (
    repository_id, source_branch_id, target_branch_id, author_id,
    title, state, head_commit, analyzed_commit, analysis_id,
    is_draft, has_conflicts, conversations_resolved, linear_history
)
SELECT r.repository_id, source.branch_id, target.branch_id,
       author.developer_id,
       'Use safe parameterized payment queries',
       'OPEN', 'commit-c7f91ad', 'commit-c7f91ad', a.analysis_id,
       FALSE, FALSE, TRUE, TRUE
FROM repositories r
JOIN repository_branches source
  ON source.repository_id = r.repository_id
 AND source.branch_name = 'feature/parameterized-query'
JOIN repository_branches target
  ON target.repository_id = r.repository_id
 AND target.branch_name = 'main'
JOIN developers author ON author.username = 'atul-dev'
JOIN analysis_runs a
  ON a.repository_id = r.repository_id
 AND a.commit_sha = 'commit-c7f91ad'
WHERE r.repository_key = 'payments-service';

INSERT INTO pull_request_commits (
    pull_request_id, commit_sha, parent_commit_sha,
    sequence_number, added_lines, deleted_lines
)
SELECT pull_request_id, 'commit-c7f91ad', 'base-90b31', 1, 80, 21
FROM pull_requests
WHERE title = 'Use safe parameterized payment queries';

INSERT INTO pull_request_reviews (
    pull_request_id, reviewer_id, reviewed_commit, state,
    is_code_owner_review, review_body
)
SELECT pr.pull_request_id, d.developer_id, 'commit-c7f91ad',
       'APPROVED', d.username = 'security-owner',
       'Reviewed query safety and the relevant authorization boundaries.'
FROM pull_requests pr
CROSS JOIN developers d
WHERE pr.title = 'Use safe parameterized payment queries'
  AND d.username IN ('reviewer-lee', 'security-owner');

INSERT INTO pull_request_status_checks (
    pull_request_id, check_name, commit_sha, passed, details
)
SELECT pr.pull_request_id, checks.check_name,
       'commit-c7f91ad', checks.passed, checks.details
FROM pull_requests pr
CROSS JOIN (
    VALUES
        ('build-linux', TRUE, 'Compilation and packaging succeeded.'),
        ('unit-tests', TRUE, 'Unit test suite completed successfully.'),
        ('dependency-audit', TRUE, 'Dependency policy checks passed.')
) AS checks(check_name, passed, details)
WHERE pr.title = 'Use safe parameterized payment queries';

INSERT INTO review_comments (
    review_id, file_path, line_number, body, is_inline
)
SELECT review_id, 'src/payment_repository.py', 143,
       'Confirm that every user-controlled parameter is bound separately.',
       TRUE
FROM pull_request_reviews
WHERE review_body LIKE 'Reviewed query safety%';

-- Quality metrics are computed from persisted findings and source counters.
-- New-code findings and overall debt deliberately use separate filters.
CREATE VIEW issue_metrics AS
SELECT
    r.repository_key,
    a.analysis_id,
    a.commit_sha,
    ROUND(
        100.0 * a.covered_lines / NULLIF(a.total_lines, 0), 2
    ) AS coverage_percent,
    ROUND(
        100.0 * a.new_covered_lines / NULLIF(a.new_lines, 0), 2
    ) AS new_coverage_percent,
    ROUND(
        100.0 * a.duplicated_lines / NULLIF(a.total_lines, 0), 2
    ) AS duplicated_lines_percent,
    ROUND(
        100.0 * a.new_duplicated_lines / NULLIF(a.new_lines, 0), 2
    ) AS new_duplicated_lines_percent,
    COUNT(i.issue_id) FILTER (
        WHERE i.resolved_at IS NULL
          AND i.introduced_in_change
          AND i.issue_kind = 'BUG'
    ) AS new_bugs,
    COUNT(i.issue_id) FILTER (
        WHERE i.resolved_at IS NULL
          AND i.introduced_in_change
          AND i.issue_kind = 'VULNERABILITY'
    ) AS new_vulnerabilities,
    COUNT(i.issue_id) FILTER (
        WHERE i.resolved_at IS NULL
          AND i.introduced_in_change
          AND i.severity = 'BLOCKER'
    ) AS new_blocker_issues,
    COUNT(i.issue_id) FILTER (
        WHERE i.resolved_at IS NULL
          AND i.introduced_in_change
          AND i.severity = 'CRITICAL'
    ) AS new_critical_issues,
    COALESCE(SUM(i.remediation_minutes) FILTER (
        WHERE i.resolved_at IS NULL
          AND i.introduced_in_change
    ), 0) AS new_technical_debt_minutes,
    COALESCE(SUM(i.remediation_minutes) FILTER (
        WHERE i.resolved_at IS NULL
    ), 0) AS technical_debt_minutes,
    COUNT(i.issue_id) FILTER (
        WHERE i.resolved_at IS NULL
    ) AS active_issue_count
FROM analysis_runs a
JOIN repositories r ON r.repository_id = a.repository_id
LEFT JOIN quality_issues i
  ON i.repository_id = r.repository_id
 AND i.first_analysis_id = a.analysis_id
WHERE a.state = 'SUCCESS'
GROUP BY
    r.repository_key, a.analysis_id, a.commit_sha,
    a.covered_lines, a.total_lines, a.new_covered_lines,
    a.new_lines, a.duplicated_lines, a.new_duplicated_lines;

-- A review decision must belong to a repository member authorized to review.
-- This trigger is illustrative application-domain enforcement; actual hosting
-- platforms must also enforce permissions in their own authorization layer.
CREATE FUNCTION validate_pull_request_review()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    pr_repository BIGINT;
    member_can_review BOOLEAN;
    reviewer_active BOOLEAN;
BEGIN
    SELECT repository_id
    INTO pr_repository
    FROM pull_requests
    WHERE pull_request_id = NEW.pull_request_id;

    IF pr_repository IS NULL THEN
        RAISE EXCEPTION 'Pull request does not exist';
    END IF;

    SELECT m.can_review, d.active
    INTO member_can_review, reviewer_active
    FROM repository_members m
    JOIN developers d ON d.developer_id = m.developer_id
    WHERE m.repository_id = pr_repository
      AND m.developer_id = NEW.reviewer_id;

    IF NOT FOUND OR NOT member_can_review OR NOT reviewer_active THEN
        RAISE EXCEPTION 'Reviewer is inactive or not authorized for this repository';
    END IF;

    IF NEW.is_code_owner_review AND NOT EXISTS (
        SELECT 1
        FROM repository_members m
        WHERE m.repository_id = pr_repository
          AND m.developer_id = NEW.reviewer_id
          AND m.is_code_owner
    ) THEN
        RAISE EXCEPTION 'Reviewer is not a registered code owner';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_pull_request_review
BEFORE INSERT OR UPDATE ON pull_request_reviews
FOR EACH ROW EXECUTE FUNCTION validate_pull_request_review();

-- Evaluate the gate from its configured conditions rather than hard-coding
-- a single final status in a client. This function supports numeric metrics.
CREATE FUNCTION evaluate_numeric_quality_gate(
    p_analysis_id BIGINT,
    p_gate_id BIGINT
)
RETURNS TABLE (
    metric_key TEXT,
    actual_value NUMERIC,
    comparison_operator TEXT,
    threshold NUMERIC,
    passed BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    metric_row RECORD;
    actual NUMERIC;
BEGIN
    FOR metric_row IN
        SELECT c.metric_key, c.comparison_operator, c.threshold, c.metric_scope
        FROM quality_gate_conditions c
        WHERE c.gate_id = p_gate_id
    LOOP
        SELECT CASE metric_row.metric_key
            WHEN 'coverage_percent' THEN m.coverage_percent
            WHEN 'new_coverage_percent' THEN m.new_coverage_percent
            WHEN 'duplicated_lines_percent' THEN m.duplicated_lines_percent
            WHEN 'new_duplicated_lines_percent' THEN m.new_duplicated_lines_percent
            WHEN 'new_bugs' THEN m.new_bugs::NUMERIC
            WHEN 'new_vulnerabilities' THEN m.new_vulnerabilities::NUMERIC
            WHEN 'new_blocker_issues' THEN m.new_blocker_issues::NUMERIC
            WHEN 'new_critical_issues' THEN m.new_critical_issues::NUMERIC
            WHEN 'new_technical_debt_minutes' THEN m.new_technical_debt_minutes::NUMERIC
            WHEN 'technical_debt_minutes' THEN m.technical_debt_minutes::NUMERIC
            ELSE NULL
        END
        INTO actual
        FROM issue_metrics m
        WHERE m.analysis_id = p_analysis_id;

        IF actual IS NULL THEN
            RAISE EXCEPTION 'Metric % is unavailable for analysis %',
                metric_row.metric_key, p_analysis_id;
        END IF;

        metric_key := metric_row.metric_key;
        actual_value := actual;
        comparison_operator := metric_row.comparison_operator;
        threshold := metric_row.threshold;

        passed := CASE comparison_operator
            WHEN '>' THEN actual > threshold
            WHEN '>=' THEN actual >= threshold
            WHEN '<' THEN actual < threshold
            WHEN '<=' THEN actual <= threshold
            WHEN '=' THEN actual = threshold
            WHEN '!=' THEN actual <> threshold
        END;

        RETURN NEXT;
    END LOOP;
END;
$$;

-- Report metrics for the analyzed commit.
SELECT *
FROM issue_metrics
ORDER BY repository_key, analysis_id;

-- Expose active issues and their contribution to technical debt.
SELECT
    issue_key,
    issue_kind,
    severity,
    component_path,
    line_number,
    remediation_minutes,
    introduced_in_change
FROM quality_issues
WHERE resolved_at IS NULL
ORDER BY
    CASE severity
        WHEN 'BLOCKER' THEN 1
        WHEN 'CRITICAL' THEN 2
        WHEN 'MAJOR' THEN 3
        WHEN 'MINOR' THEN 4
        ELSE 5
    END,
    issue_key;

-- Compute a gate evaluation using the persisted policy.
WITH current_analysis AS (
    SELECT analysis_id
    FROM analysis_runs
    WHERE commit_sha = 'commit-c7f91ad'
      AND state = 'SUCCESS'
),
current_gate AS (
    SELECT gate_id
    FROM quality_gates
    WHERE gate_name = 'Production Gate'
      AND enabled
)
SELECT evaluation.*
FROM current_analysis a
CROSS JOIN current_gate g
CROSS JOIN LATERAL evaluate_numeric_quality_gate(a.analysis_id, g.gate_id)
    AS evaluation;

-- Determine approval counts against the current head commit.
-- Stale reviews, dismissed decisions, and ineligible reviewers do not count.
SELECT
    pr.pull_request_id,
    pr.title,
    pr.head_commit,
    COUNT(DISTINCT rev.reviewer_id) FILTER (
        WHERE rev.state = 'APPROVED'
          AND rev.reviewed_commit = pr.head_commit
          AND m.can_review
          AND d.active
    ) AS valid_approval_count,
    BOOL_OR(
        rev.state = 'APPROVED'
        AND rev.reviewed_commit = pr.head_commit
        AND m.is_code_owner
        AND d.active
        AND m.can_review
    ) AS current_code_owner_approval
FROM pull_requests pr
JOIN repositories r ON r.repository_id = pr.repository_id
LEFT JOIN pull_request_reviews rev
  ON rev.pull_request_id = pr.pull_request_id
LEFT JOIN developers d ON d.developer_id = rev.reviewer_id
LEFT JOIN repository_members m
  ON m.repository_id = pr.repository_id
 AND m.developer_id = rev.reviewer_id
WHERE r.repository_key = 'payments-service'
GROUP BY pr.pull_request_id, pr.title, pr.head_commit;

-- Explain why a pull request cannot be merged under its branch policy.
-- The result deliberately distinguishes quality-gate failure from governance failure.
WITH request_context AS (
    SELECT
        pr.pull_request_id,
        pr.title,
        pr.state,
        pr.is_draft,
        pr.has_conflicts,
        pr.conversations_resolved,
        pr.linear_history,
        pr.head_commit,
        pr.analyzed_commit,
        pr.target_branch_id,
        a.state AS analysis_state,
        ge.status AS gate_status,
        bp.policy_id,
        bp.required_approvals,
        bp.require_code_owner,
        bp.require_linear_history,
        bp.require_resolved_conversations,
        bp.allow_administrator_bypass
    FROM pull_requests pr
    JOIN repositories r ON r.repository_id = pr.repository_id
    JOIN repository_branches target
      ON target.branch_id = pr.target_branch_id
    LEFT JOIN branch_protection_policies bp
      ON bp.repository_id = r.repository_id
     AND bp.branch_pattern = target.branch_name
    LEFT JOIN analysis_runs a ON a.analysis_id = pr.analysis_id
    LEFT JOIN quality_gate_evaluations ge
      ON ge.analysis_id = a.analysis_id
     AND ge.gate_id = bp.policy_id
    WHERE r.repository_key = 'payments-service'
)
SELECT
    pull_request_id,
    title,
    CASE
        WHEN state <> 'OPEN' THEN 'BLOCK: request is not open'
        WHEN is_draft THEN 'BLOCK: request is still a draft'
        WHEN has_conflicts THEN 'BLOCK: merge conflicts remain'
        WHEN head_commit IS DISTINCT FROM analyzed_commit
            THEN 'BLOCK: analysis is stale or absent'
        WHEN analysis_state IS DISTINCT FROM 'SUCCESS'::analysis_state
            THEN 'BLOCK: analysis has not succeeded'
        WHEN conversations_resolved = FALSE
             AND require_resolved_conversations
            THEN 'BLOCK: unresolved review conversations'
        WHEN linear_history = FALSE AND require_linear_history
            THEN 'BLOCK: linear history is required'
        WHEN policy_id IS NULL THEN 'BLOCK: no matching branch policy'
        ELSE 'REQUIRES CHECKS: validate gate, approvals, and required CI checks'
    END AS merge_eligibility_reason
FROM request_context;

-- Demonstrate transaction rollback when an impossible metric is attempted.
-- The nested block catches the expected constraint error and keeps the script
-- usable for the remaining read-only examples.
DO $$
BEGIN
    BEGIN
        INSERT INTO analysis_runs (
            repository_id, branch_id, profile_id, commit_sha, state,
            total_lines, covered_lines, duplicated_lines,
            new_lines, new_covered_lines, new_duplicated_lines
        )
        SELECT r.repository_id, b.branch_id, p.profile_id,
               'invalid-coverage-demo', 'SUCCESS',
               10, 11, 0, 2, 1, 0
        FROM repositories r
        JOIN repository_branches b ON b.repository_id = r.repository_id
        JOIN quality_profiles p ON p.profile_name = 'Python Production Profile'
        WHERE r.repository_key = 'payments-service'
          AND b.branch_name = 'main';

        RAISE EXCEPTION 'Expected invalid coverage to be rejected';
    EXCEPTION
        WHEN check_violation THEN
            RAISE NOTICE 'Correctly rejected impossible coverage counts.';
        WHEN raise_exception THEN
            IF SQLERRM = 'Expected invalid coverage to be rejected' THEN
                RAISE;
            ELSE
                RAISE NOTICE 'Correctly rejected invalid demonstration: %', SQLERRM;
            END IF;
    END;
END;
$$;

COMMIT;
