DROP SCHEMA IF EXISTS dockerfile_learning CASCADE;
CREATE SCHEMA dockerfile_learning;
SET search_path TO dockerfile_learning;

CREATE TABLE base_images (
    base_image_id BIGSERIAL PRIMARY KEY,
    repository TEXT NOT NULL,
    tag TEXT,
    digest TEXT,
    architecture TEXT NOT NULL DEFAULT 'amd64',
    trusted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT base_image_repository_chk
        CHECK (length(trim(repository)) > 0),
    CONSTRAINT base_image_reference_chk
        CHECK (tag IS NOT NULL OR digest IS NOT NULL)
);

CREATE UNIQUE INDEX base_images_reference_uq
    ON base_images (
        repository,
        COALESCE(tag, ''),
        COALESCE(digest, ''),
        architecture
    );

CREATE TABLE repositories (
    repository_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    owner_team TEXT NOT NULL,
    production BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE dockerfiles (
    dockerfile_id BIGSERIAL PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(repository_id),
    path TEXT NOT NULL,
    branch_name TEXT NOT NULL DEFAULT 'main',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (repository_id, path, branch_name, version)
);

CREATE TABLE instructions (
    instruction_id BIGSERIAL PRIMARY KEY,
    dockerfile_id BIGINT NOT NULL REFERENCES dockerfiles(dockerfile_id)
        ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    keyword TEXT NOT NULL,
    arguments TEXT NOT NULL,
    base_image_id BIGINT REFERENCES base_images(base_image_id),
    CONSTRAINT instruction_line_chk CHECK (line_number > 0),
    CONSTRAINT instruction_keyword_chk CHECK (
        keyword IN (
            'FROM',
            'RUN',
            'COPY',
            'CMD',
            'ENTRYPOINT',
            'ENV',
            'WORKDIR',
            'EXPOSE',
            'USER'
        )
    ),
    UNIQUE (dockerfile_id, line_number)
);

CREATE TABLE builds (
    build_id BIGSERIAL PRIMARY KEY,
    dockerfile_id BIGINT NOT NULL REFERENCES dockerfiles(dockerfile_id),
    status TEXT NOT NULL DEFAULT 'QUEUED',
    image_tag TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    failure_reason TEXT,
    CONSTRAINT build_status_chk CHECK (
        status IN ('QUEUED', 'RUNNING', 'PASSED', 'FAILED', 'BLOCKED')
    ),
    CONSTRAINT build_time_chk CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    )
);

CREATE TABLE build_policies (
    policy_id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    severity TEXT NOT NULL,
    CONSTRAINT policy_severity_chk CHECK (
        severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')
    )
);

CREATE TABLE build_policy_results (
    build_id BIGINT NOT NULL REFERENCES builds(build_id)
        ON DELETE CASCADE,
    policy_id BIGINT NOT NULL REFERENCES build_policies(policy_id),
    passed BOOLEAN NOT NULL,
    details TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (build_id, policy_id)
);

CREATE INDEX instructions_keyword_idx
    ON instructions(keyword);

CREATE INDEX builds_status_idx
    ON builds(status);

CREATE INDEX policy_results_build_pass_idx
    ON build_policy_results(build_id, passed);

CREATE OR REPLACE FUNCTION validate_dockerfile_instruction()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    first_keyword TEXT;
    normalized TEXT;
BEGIN
    IF trim(NEW.arguments) = '' THEN
        RAISE EXCEPTION
            'Instruction % on line % has empty arguments',
            NEW.keyword,
            NEW.line_number;
    END IF;

    IF NEW.keyword = 'COPY'
       AND NEW.arguments LIKE '%../%' THEN
        RAISE EXCEPTION
            'COPY instruction cannot escape the build context';
    END IF;

    IF NEW.keyword IN ('ENV', 'RUN') THEN
        normalized := lower(NEW.arguments);

        IF normalized ~ '(password|secret|private_key|api[_-]?key)[[:space:]]*='
        THEN
            RAISE EXCEPTION
                'Credential-like data must not be stored in %',
                NEW.keyword;
        END IF;
    END IF;

    IF NEW.keyword = 'FROM' THEN
        IF position(':' IN split_part(NEW.arguments, ' ', 1)) = 0
           AND position('@sha256:' IN NEW.arguments) = 0 THEN
            RAISE EXCEPTION
                'FROM should use an explicit tag or digest in this policy';
        END IF;
    END IF;

    IF NEW.line_number = 1 THEN
        first_keyword := NEW.keyword;

        IF first_keyword <> 'FROM' THEN
            RAISE EXCEPTION
                'FROM must be the first instruction';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER dockerfile_instruction_validation
BEFORE INSERT OR UPDATE ON instructions
FOR EACH ROW
EXECUTE FUNCTION validate_dockerfile_instruction();

CREATE OR REPLACE FUNCTION evaluate_build(build_identifier BIGINT)
RETURNS TABLE (
    policy_name TEXT,
    passed BOOLEAN,
    details TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    dockerfile_identifier BIGINT;
    has_from BOOLEAN;
    has_startup BOOLEAN;
    has_user BOOLEAN;
    has_secret BOOLEAN;
BEGIN
    SELECT b.dockerfile_id
    INTO dockerfile_identifier
    FROM builds b
    WHERE b.build_id = build_identifier;

    IF dockerfile_identifier IS NULL THEN
        RAISE EXCEPTION 'Unknown build id %', build_identifier;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM instructions
        WHERE dockerfile_id = dockerfile_identifier
          AND keyword = 'FROM'
    )
    INTO has_from;

    SELECT EXISTS (
        SELECT 1
        FROM instructions
        WHERE dockerfile_id = dockerfile_identifier
          AND keyword IN ('CMD', 'ENTRYPOINT')
    )
    INTO has_startup;

    SELECT EXISTS (
        SELECT 1
        FROM instructions
        WHERE dockerfile_id = dockerfile_identifier
          AND keyword = 'USER'
    )
    INTO has_user;

    SELECT EXISTS (
        SELECT 1
        FROM instructions
        WHERE dockerfile_id = dockerfile_identifier
          AND keyword IN ('ENV', 'RUN')
          AND lower(arguments) ~
              '(password|secret|private_key|api[_-]?key)[[:space:]]*='
    )
    INTO has_secret;

    RETURN QUERY
    SELECT
        'base-image'::TEXT,
        has_from,
        CASE
            WHEN has_from
            THEN 'FROM instruction exists'
            ELSE 'Dockerfile has no FROM instruction'
        END;

    RETURN QUERY
    SELECT
        'startup-definition'::TEXT,
        has_startup,
        CASE
            WHEN has_startup
            THEN 'CMD or ENTRYPOINT exists'
            ELSE 'Container startup behavior is undefined'
        END;

    RETURN QUERY
    SELECT
        'credential-storage'::TEXT,
        NOT has_secret,
        CASE
            WHEN NOT has_secret
            THEN 'No credential-like ENV or RUN assignment detected'
            ELSE 'Credential-like data detected'
        END;

    RETURN QUERY
    SELECT
        'non-root-user'::TEXT,
        has_user,
        CASE
            WHEN has_user
            THEN 'USER instruction exists'
            ELSE 'No USER instruction was declared'
        END;
END;
$$;

CREATE OR REPLACE VIEW dockerfile_instruction_report AS
SELECT
    d.name AS repository,
    f.path,
    f.branch_name,
    f.version,
    i.line_number,
    i.keyword,
    i.arguments
FROM repositories d
JOIN dockerfiles f
    ON f.repository_id = d.repository_id
JOIN instructions i
    ON i.dockerfile_id = f.dockerfile_id
ORDER BY d.name, f.path, i.line_number;

CREATE OR REPLACE VIEW build_governance_report AS
SELECT
    b.build_id,
    r.name AS repository,
    b.status AS build_status,
    p.name AS policy,
    p.severity,
    rsl.passed,
    rsl.details
FROM builds b
JOIN dockerfiles d
    ON d.dockerfile_id = b.dockerfile_id
JOIN repositories r
    ON r.repository_id = d.repository_id
JOIN build_policy_results rsl
    ON rsl.build_id = b.build_id
JOIN build_policies p
    ON p.policy_id = rsl.policy_id;

INSERT INTO base_images
    (repository, tag, digest, architecture, trusted)
VALUES
    ('python', '3.13-slim', NULL, 'amd64', TRUE),
    ('node', '22-bookworm-slim', NULL, 'amd64', TRUE),
    ('nginx', 'stable-alpine', NULL, 'amd64', TRUE);

INSERT INTO repositories
    (name, owner_team, production)
VALUES
    ('order-service', 'platform', TRUE),
    ('static-web', 'frontend', TRUE);

INSERT INTO dockerfiles
    (repository_id, path, branch_name, version)
VALUES
    (
        (SELECT repository_id FROM repositories WHERE name = 'order-service'),
        'Dockerfile',
        'main',
        1
    ),
    (
        (SELECT repository_id FROM repositories WHERE name = 'static-web'),
        'Dockerfile',
        'main',
        1
    );

INSERT INTO instructions
    (dockerfile_id, line_number, keyword, arguments, base_image_id)
VALUES
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    1,
    'FROM',
    'python:3.13-slim',
    (SELECT base_image_id
     FROM base_images
     WHERE repository = 'python'
       AND tag = '3.13-slim')
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    3,
    'ENV',
    'PYTHONUNBUFFERED=1 APP_ENV=production',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    5,
    'WORKDIR',
    '/app',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    7,
    'COPY',
    'requirements.txt .',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    8,
    'RUN',
    'pip install --no-cache-dir -r requirements.txt',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    10,
    'COPY',
    'app.py .',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    12,
    'ENTRYPOINT',
    '["python", "app.py"]',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'order-service'
       )),
    13,
    'CMD',
    '["--port", "8000"]',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'static-web'
       )),
    1,
    'FROM',
    'nginx:stable-alpine',
    (SELECT base_image_id
     FROM base_images
     WHERE repository = 'nginx'
       AND tag = 'stable-alpine')
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'static-web'
       )),
    3,
    'ENV',
    'NGINX_PORT=8080',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'static-web'
       )),
    5,
    'COPY',
    'index.html /usr/share/nginx/html/index.html',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'static-web'
       )),
    7,
    'ENTRYPOINT',
    '["nginx"]',
    NULL
),
(
    (SELECT dockerfile_id
     FROM dockerfiles
     WHERE path = 'Dockerfile'
       AND repository_id = (
           SELECT repository_id
           FROM repositories
           WHERE name = 'static-web'
       )),
    8,
    'CMD',
    '["-g", "daemon off;"]',
    NULL
);

INSERT INTO builds
    (dockerfile_id, status, image_tag, started_at, finished_at)
SELECT
    dockerfile_id,
    'PASSED',
    name || ':1.0',
    now() - interval '4 minutes',
    now()
FROM dockerfiles d
JOIN repositories r USING (repository_id);

INSERT INTO build_policies
    (name, description, severity)
VALUES
    ('Base image declared',
     'Dockerfile contains a FROM instruction.',
     'HIGH'),
    ('Startup configured',
     'Dockerfile contains CMD or ENTRYPOINT.',
     'MEDIUM'),
    ('Credentials excluded',
     'Dockerfile does not persist obvious credentials.',
     'CRITICAL'),
    ('Non-root execution',
     'Dockerfile declares USER for production execution.',
     'HIGH');

INSERT INTO build_policy_results
    (build_id, policy_id, passed, details)
SELECT
    b.build_id,
    p.policy_id,
    CASE p.name
        WHEN 'Base image declared' THEN TRUE
        WHEN 'Startup configured' THEN TRUE
        WHEN 'Credentials excluded' THEN TRUE
        WHEN 'Non-root execution' THEN FALSE
    END,
    CASE p.name
        WHEN 'Base image declared'
            THEN 'FROM is present.'
        WHEN 'Startup configured'
            THEN 'ENTRYPOINT and CMD define startup behavior.'
        WHEN 'Credentials excluded'
            THEN 'No credentials were persisted.'
        WHEN 'Non-root execution'
            THEN 'USER was not declared in the sample Dockerfiles.'
    END
FROM builds b
CROSS JOIN build_policies p;

BEGIN;

UPDATE builds
SET status = 'RUNNING',
    started_at = COALESCE(started_at, now())
WHERE build_id = (
    SELECT min(build_id)
    FROM builds
);

-- A production workflow can transition to PASSED only after all
-- mandatory policy results have passed.
UPDATE builds b
SET status = CASE
    WHEN NOT EXISTS (
        SELECT 1
        FROM build_policy_results r
        JOIN build_policies p
          ON p.policy_id = r.policy_id
        WHERE r.build_id = b.build_id
          AND p.severity IN ('HIGH', 'CRITICAL')
          AND NOT r.passed
    )
    THEN 'PASSED'
    ELSE 'BLOCKED'
END,
finished_at = now()
WHERE b.build_id = (
    SELECT min(build_id)
    FROM builds
);

COMMIT;

SELECT *
FROM dockerfile_instruction_report;

SELECT *
FROM build_governance_report
ORDER BY build_id, policy;

SELECT *
FROM evaluate_build(
    (SELECT min(build_id) FROM builds)
);

WITH instruction_counts AS (
    SELECT
        dockerfile_id,
        keyword,
        count(*) AS occurrences
    FROM instructions
    GROUP BY dockerfile_id, keyword
)
SELECT
    r.name AS repository,
    d.path,
    c.keyword,
    c.occurrences
FROM instruction_counts c
JOIN dockerfiles d
    ON d.dockerfile_id = c.dockerfile_id
JOIN repositories r
    ON r.repository_id = d.repository_id
ORDER BY r.name, d.path, c.keyword;

SELECT
    r.name AS repository,
    count(*) FILTER (WHERE i.keyword = 'RUN') AS run_count,
    count(*) FILTER (WHERE i.keyword = 'COPY') AS copy_count,
    count(*) FILTER (WHERE i.keyword = 'ENV') AS env_count,
    count(*) FILTER (WHERE i.keyword = 'CMD') AS cmd_count,
    count(*) FILTER (WHERE i.keyword = 'ENTRYPOINT') AS entrypoint_count,
    count(*) FILTER (WHERE i.keyword = 'USER') AS user_count
FROM repositories r
JOIN dockerfiles d
    ON d.repository_id = r.repository_id
JOIN instructions i
    ON i.dockerfile_id = d.dockerfile_id
GROUP BY r.name
ORDER BY r.name;
