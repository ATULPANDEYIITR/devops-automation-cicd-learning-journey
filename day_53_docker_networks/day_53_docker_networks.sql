DROP SCHEMA IF EXISTS docker_network_lab CASCADE;
CREATE SCHEMA docker_network_lab;
SET search_path = docker_network_lab, public;

-- A Docker network represents a logical connectivity domain.
CREATE TABLE docker_network (
    network_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    driver text NOT NULL DEFAULT 'bridge',
    subnet cidr NOT NULL,
    gateway inet NOT NULL,
    CHECK (driver IN ('bridge', 'host')),
    CHECK (family(gateway) = 4),
    CHECK (gateway <<= subnet)
);

-- Container network modes are intentionally distinct:
-- bridge gets its own endpoint, host shares the host namespace,
-- and container shares another container's network namespace.
CREATE TABLE container (
    container_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE,
    network_mode text NOT NULL,
    shared_container_id bigint REFERENCES container(container_id),
    status text NOT NULL DEFAULT 'running',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (network_mode IN ('bridge', 'host', 'container')),
    CHECK (status IN ('created', 'running', 'stopped')),
    CHECK (
        (network_mode = 'container' AND shared_container_id IS NOT NULL)
        OR
        (network_mode <> 'container' AND shared_container_id IS NULL)
    )
);

CREATE TABLE container_network (
    container_network_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id bigint NOT NULL REFERENCES container(container_id) ON DELETE CASCADE,
    network_id bigint NOT NULL REFERENCES docker_network(network_id) ON DELETE CASCADE,
    ip_address inet NOT NULL,
    UNIQUE (container_id, network_id),
    UNIQUE (network_id, ip_address),
    CHECK (family(ip_address) = 4)
);

CREATE TABLE container_port (
    container_port_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id bigint NOT NULL REFERENCES container(container_id) ON DELETE CASCADE,
    protocol text NOT NULL,
    port integer NOT NULL,
    listening boolean NOT NULL DEFAULT true,
    UNIQUE (container_id, protocol, port),
    CHECK (protocol IN ('tcp', 'udp')),
    CHECK (port BETWEEN 1 AND 65535)
);

CREATE TABLE published_port (
    published_port_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    container_id bigint NOT NULL REFERENCES container(container_id) ON DELETE CASCADE,
    protocol text NOT NULL DEFAULT 'tcp',
    host_port integer NOT NULL,
    container_port integer NOT NULL,
    UNIQUE (protocol, host_port),
    CHECK (protocol IN ('tcp', 'udp')),
    CHECK (host_port BETWEEN 1 AND 65535),
    CHECK (container_port BETWEEN 1 AND 65535)
);

CREATE INDEX idx_container_network_network
    ON container_network(network_id);

CREATE INDEX idx_container_port_lookup
    ON container_port(container_id, protocol, port)
    WHERE listening;

CREATE INDEX idx_published_port_host
    ON published_port(protocol, host_port);

-- Validate that a container endpoint belongs to its network.
CREATE OR REPLACE FUNCTION validate_container_network_ip()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    network_subnet cidr;
BEGIN
    SELECT subnet
    INTO network_subnet
    FROM docker_network
    WHERE network_id = NEW.network_id;

    IF network_subnet IS NULL THEN
        RAISE EXCEPTION 'Network % does not exist', NEW.network_id;
    END IF;

    IF NOT (NEW.ip_address <<= network_subnet) THEN
        RAISE EXCEPTION
            'IP % does not belong to subnet %',
            NEW.ip_address,
            network_subnet;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM docker_network
        WHERE network_id = NEW.network_id
          AND gateway = NEW.ip_address
    ) THEN
        RAISE EXCEPTION
            'IP % cannot be the network gateway',
            NEW.ip_address;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_container_network_ip
BEFORE INSERT OR UPDATE ON container_network
FOR EACH ROW
EXECUTE FUNCTION validate_container_network_ip();

-- A published port must map to a listening container port.
CREATE OR REPLACE FUNCTION validate_published_port()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM container_port cp
        WHERE cp.container_id = NEW.container_id
          AND cp.protocol = NEW.protocol
          AND cp.port = NEW.container_port
          AND cp.listening
    ) THEN
        RAISE EXCEPTION
            'Container % does not listen on %/%',
            NEW.container_id,
            NEW.protocol,
            NEW.container_port;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_published_port
BEFORE INSERT OR UPDATE ON published_port
FOR EACH ROW
EXECUTE FUNCTION validate_published_port();

-- Bridge containers require at least one network endpoint.
-- Host containers intentionally have no container-specific endpoint.
CREATE OR REPLACE FUNCTION validate_container_mode()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.network_mode = 'container'
       AND NEW.shared_container_id = NEW.container_id THEN
        RAISE EXCEPTION 'A container cannot share its own network namespace';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_validate_container_mode
BEFORE INSERT OR UPDATE ON container
FOR EACH ROW
EXECUTE FUNCTION validate_container_mode();

CREATE OR REPLACE FUNCTION connectivity(
    source_container text,
    target_container text,
    target_protocol text,
    target_port integer
)
RETURNS TABLE (
    allowed boolean,
    reason text
)
LANGUAGE plpgsql
AS $$
DECLARE
    source_mode text;
    target_mode text;
    common_network text;
    target_listening boolean;
BEGIN
    SELECT network_mode
    INTO source_mode
    FROM container
    WHERE name = source_container;

    SELECT network_mode
    INTO target_mode
    FROM container
    WHERE name = target_container;

    IF source_mode IS NULL OR target_mode IS NULL THEN
        RETURN QUERY
        SELECT false, 'Unknown source or target container';
        RETURN;
    END IF;

    IF source_container = target_container THEN
        RETURN QUERY
        SELECT false, 'Self-connectivity is outside this workflow';
        RETURN;
    END IF;

    IF target_mode = 'host' THEN
        SELECT EXISTS (
            SELECT 1
            FROM container c
            JOIN container_port cp
              ON cp.container_id = c.container_id
            WHERE c.name = target_container
              AND cp.protocol = target_protocol
              AND cp.port = target_port
              AND cp.listening
        )
        INTO target_listening;

        RETURN QUERY
        SELECT
            target_listening,
            CASE
                WHEN target_listening
                    THEN 'Destination uses the host network namespace'
                ELSE 'Target port is not listening'
            END;
        RETURN;
    END IF;

    SELECT n.name
    INTO common_network
    FROM container_network source_cn
    JOIN container_network target_cn
      ON target_cn.network_id = source_cn.network_id
    JOIN docker_network n
      ON n.network_id = source_cn.network_id
    JOIN container source_c
      ON source_c.container_id = source_cn.container_id
    JOIN container target_c
      ON target_c.container_id = target_cn.container_id
    WHERE source_c.name = source_container
      AND target_c.name = target_container
    ORDER BY n.name
    LIMIT 1;

    IF common_network IS NULL THEN
        RETURN QUERY
        SELECT false, 'Containers share no Docker network';
        RETURN;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM container c
        JOIN container_port cp
          ON cp.container_id = c.container_id
        WHERE c.name = target_container
          AND cp.protocol = target_protocol
          AND cp.port = target_port
          AND cp.listening
    )
    INTO target_listening;

    IF NOT target_listening THEN
        RETURN QUERY
        SELECT
            false,
            'Network path exists but target port is not listening';
        RETURN;
    END IF;

    RETURN QUERY
    SELECT
        true,
        format('Reachable through bridge network %s', common_network);
END;
$$;

CREATE OR REPLACE VIEW v_container_network_topology AS
SELECT
    c.name AS container_name,
    c.network_mode,
    n.name AS network_name,
    cn.ip_address,
    n.subnet,
    n.gateway
FROM container c
LEFT JOIN container_network cn
    ON cn.container_id = c.container_id
LEFT JOIN docker_network n
    ON n.network_id = cn.network_id
ORDER BY c.name, n.name;

CREATE OR REPLACE VIEW v_published_ports AS
SELECT
    c.name AS container_name,
    pp.protocol,
    pp.host_port,
    pp.container_port
FROM published_port pp
JOIN container c
  ON c.container_id = pp.container_id
ORDER BY pp.host_port;

INSERT INTO docker_network(name, driver, subnet, gateway)
VALUES
    ('frontend', 'bridge', '172.50.0.0/24', '172.50.0.1'),
    ('backend', 'bridge', '172.51.0.0/24', '172.51.0.1'),
    ('isolated', 'bridge', '172.52.0.0/24', '172.52.0.1');

INSERT INTO container(name, network_mode)
VALUES
    ('web', 'bridge'),
    ('api', 'bridge'),
    ('database', 'bridge'),
    ('monitor', 'host');

INSERT INTO container(name, network_mode, shared_container_id)
SELECT
    'api-worker',
    'container',
    container_id
FROM container
WHERE name = 'api';

INSERT INTO container_network(container_id, network_id, ip_address)
SELECT
    c.container_id,
    n.network_id,
    x.ip_address
FROM (
    VALUES
        ('web', 'frontend', '172.50.0.10'::inet),
        ('api', 'frontend', '172.50.0.20'::inet),
        ('api', 'backend', '172.51.0.10'::inet),
        ('database', 'backend', '172.51.0.30'::inet)
) AS x(container_name, network_name, ip_address)
JOIN container c
  ON c.name = x.container_name
JOIN docker_network n
  ON n.name = x.network_name;

INSERT INTO container_port(container_id, protocol, port, listening)
SELECT c.container_id, 'tcp', x.port, true
FROM (
    VALUES
        ('web', 8080),
        ('api', 8080),
        ('database', 5432),
        ('monitor', 9090)
) AS x(container_name, port)
JOIN container c
  ON c.name = x.container_name;

INSERT INTO published_port(
    container_id,
    protocol,
    host_port,
    container_port
)
SELECT
    c.container_id,
    'tcp',
    8080,
    8080
FROM container c
WHERE c.name = 'web';

-- Topology inspection.
SELECT *
FROM v_container_network_topology;

-- Published-port inspection.
SELECT *
FROM v_published_ports;

-- Containers on a shared network.
SELECT
    n.name AS network_name,
    c.name AS container_name,
    cn.ip_address
FROM docker_network n
JOIN container_network cn
  ON cn.network_id = n.network_id
JOIN container c
  ON c.container_id = cn.container_id
ORDER BY n.name, c.name;

-- Connectivity evaluations.
SELECT 'web -> api:8080' AS test, *
FROM connectivity('web', 'api', 'tcp', 8080);

SELECT 'api -> database:5432' AS test, *
FROM connectivity('api', 'database', 'tcp', 5432);

SELECT 'web -> database:5432' AS test, *
FROM connectivity('web', 'database', 'tcp', 5432);

SELECT 'web -> monitor:9090' AS test, *
FROM connectivity('web', 'monitor', 'tcp', 9090);

-- Find services exposed on each Docker network.
SELECT
    n.name AS network_name,
    c.name AS container_name,
    cp.protocol,
    cp.port
FROM docker_network n
JOIN container_network cn
  ON cn.network_id = n.network_id
JOIN container c
  ON c.container_id = cn.container_id
JOIN container_port cp
  ON cp.container_id = c.container_id
WHERE cp.listening
ORDER BY n.name, c.name, cp.port;

-- Transactional port-publication example.
BEGIN;

INSERT INTO container_port(container_id, protocol, port, listening)
SELECT container_id, 'tcp', 8443, true
FROM container
WHERE name = 'api';

INSERT INTO published_port(
    container_id,
    protocol,
    host_port,
    container_port
)
SELECT
    container_id,
    'tcp',
    8443,
    8443
FROM container
WHERE name = 'api';

COMMIT;

-- The newly published endpoint is now visible.
SELECT *
FROM v_published_ports
WHERE host_port = 8443;

-- Demonstrate database-level failure handling.
DO $$
BEGIN
    BEGIN
        INSERT INTO published_port(
            container_id,
            protocol,
            host_port,
            container_port
        )
        SELECT
            container_id,
            'tcp',
            8443,
            8080
        FROM container
        WHERE name = 'database';
    EXCEPTION
        WHEN OTHERS THEN
            RAISE NOTICE 'Expected publication failure: %', SQLERRM;
    END;
END;
$$;

-- A failed attempt does not create an invalid publication.
SELECT *
FROM v_published_ports
WHERE host_port = 8443;
