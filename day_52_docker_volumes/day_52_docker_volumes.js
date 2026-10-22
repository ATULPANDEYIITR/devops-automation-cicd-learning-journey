#!/usr/bin/env node
"use strict";

/*
 * Docker storage policy and event model.
 *
 * The implementation deliberately uses Node.js capabilities rather than
 * translating the Python data model. It represents storage operations as
 * asynchronous events and evaluates whether a requested mount is safe.
 *
 * Storage types:
 *   named-volume  -> Docker-managed persistent data
 *   bind-mount    -> host-owned path
 *   ephemeral     -> container writable layer
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

class StoragePolicyError extends Error {}
class MountConflictError extends StoragePolicyError {}
class StorageNotFoundError extends StoragePolicyError {}

const StorageType = Object.freeze({
  NAMED_VOLUME: "named-volume",
  BIND_MOUNT: "bind-mount",
  EPHEMERAL: "ephemeral"
});

function assertName(value, field) {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$/.test(value)) {
    throw new StoragePolicyError(`Invalid ${field}: ${value}`);
  }
}

function assertContainerPath(value) {
  if (typeof value !== "string" || !value.startsWith("/")) {
    throw new StoragePolicyError(`Container path must be absolute: ${value}`);
  }

  const normalized = path.posix.normalize(value);
  if (normalized.split("/").includes("..")) {
    throw new StoragePolicyError("Parent traversal is not permitted");
  }

  return normalized;
}

class StorageRegistry extends EventEmitter {
  #volumes = new Map();
  #bindMounts = new Map();
  #containers = new Map();

  createNamedVolume(name) {
    assertName(name, "volume name");

    if (this.#volumes.has(name)) {
      throw new StoragePolicyError(`Volume already exists: ${name}`);
    }

    this.#volumes.set(name, {
      name,
      data: new Map(),
      attachments: new Set()
    });

    this.emit("volume.created", { name });
  }

  registerBindMount(hostPath, options = {}) {
    if (!hostPath || typeof hostPath !== "string") {
      throw new StoragePolicyError("Host path is required");
    }

    if (this.#bindMounts.has(hostPath)) {
      throw new StoragePolicyError(`Bind mount exists: ${hostPath}`);
    }

    this.#bindMounts.set(hostPath, {
      hostPath,
      readOnly: Boolean(options.readOnly),
      data: new Map(Object.entries(options.initialData || {}))
    });

    this.emit("bind.created", { hostPath });
  }

  createContainer(id) {
    assertName(id, "container ID");

    if (this.#containers.has(id)) {
      throw new StoragePolicyError(`Container exists: ${id}`);
    }

    this.#containers.set(id, {
      id,
      mounts: [],
      ephemeral: new Map(),
      state: "created"
    });

    this.emit("container.created", { id });
  }

  startContainer(id) {
    const container = this.#container(id);

    if (container.state === "removed") {
      throw new StoragePolicyError("Removed containers cannot start");
    }

    container.state = "running";
    this.emit("container.started", { id });
  }

  stopContainer(id) {
    const container = this.#container(id);
    container.state = "stopped";
    this.emit("container.stopped", { id });
  }

  mountNamedVolume(containerId, volumeName, destination, readOnly = false) {
    const container = this.#container(containerId);
    const volume = this.#volume(volumeName);

    this.#addMount(container, {
      source: volumeName,
      destination: assertContainerPath(destination),
      type: StorageType.NAMED_VOLUME,
      readOnly
    });

    volume.attachments.add(containerId);
    this.emit("volume.attached", { containerId, volumeName });
  }

  mountBind(containerId, hostPath, destination, readOnly = false) {
    const container = this.#container(containerId);

    if (!this.#bindMounts.has(hostPath)) {
      throw new StorageNotFoundError(
        `Bind source is not registered: ${hostPath}`
      );
    }

    this.#addMount(container, {
      source: hostPath,
      destination: assertContainerPath(destination),
      type: StorageType.BIND_MOUNT,
      readOnly
    });

    this.emit("bind.attached", { containerId, hostPath });
  }

  async write(containerId, containerPath, value) {
    const container = this.#container(containerId);
    const mount = this.#resolveMount(container, containerPath);

    if (!mount) {
      container.ephemeral.set(
        this.#relative(containerPath),
        String(value)
      );
      this.emit("storage.write", {
        containerId,
        type: StorageType.EPHEMERAL,
        path: containerPath
      });
      return;
    }

    if (mount.readOnly) {
      throw new StoragePolicyError(
        `Write blocked by read-only mount: ${mount.destination}`
      );
    }

    const data = this.#dataForMount(mount);
    data.set(this.#relative(containerPath, mount.destination), String(value));

    this.emit("storage.write", {
      containerId,
      type: mount.type,
      path: containerPath
    });
  }

  async read(containerId, containerPath) {
    const container = this.#container(containerId);
    const mount = this.#resolveMount(container, containerPath);

    if (!mount) {
      const key = this.#relative(containerPath);
      if (!container.ephemeral.has(key)) {
        throw new StorageNotFoundError(`File not found: ${containerPath}`);
      }
      return container.ephemeral.get(key);
    }

    const data = this.#dataForMount(mount);
    const key = this.#relative(containerPath, mount.destination);

    if (!data.has(key)) {
      throw new StorageNotFoundError(`File not found: ${containerPath}`);
    }

    return data.get(key);
  }

  async removeContainer(id) {
    const container = this.#container(id);

    for (const mount of container.mounts) {
      if (mount.type === StorageType.NAMED_VOLUME) {
        this.#volume(mount.source).attachments.delete(id);
      }
    }

    this.#containers.delete(id);
    this.emit("container.removed", { id });
  }

  volumeSnapshot(volumeName) {
    const volume = this.#volume(volumeName);

    return {
      volume: volumeName,
      createdAt: new Date().toISOString(),
      checksum: crypto
        .createHash("sha256")
        .update(JSON.stringify([...volume.data]))
        .digest("hex"),
      files: Object.fromEntries(volume.data)
    };
  }

  restoreVolume(volumeName, snapshot) {
    const volume = this.#volume(volumeName);

    if (!snapshot || typeof snapshot.files !== "object") {
      throw new StoragePolicyError("Invalid volume snapshot");
    }

    volume.data = new Map(Object.entries(snapshot.files));
    this.emit("volume.restored", { volumeName });
  }

  inspect() {
    return {
      volumes: Object.fromEntries(
        [...this.#volumes].map(([name, volume]) => [
          name,
          {
            files: Object.fromEntries(volume.data),
            attachments: [...volume.attachments]
          }
        ])
      ),
      bindMounts: Object.fromEntries(
        [...this.#bindMounts].map(([hostPath, mount]) => [
          hostPath,
          {
            readOnly: mount.readOnly,
            files: Object.fromEntries(mount.data)
          }
        ])
      ),
      containers: Object.fromEntries(
        [...this.#containers].map(([id, container]) => [
          id,
          {
            state: container.state,
            ephemeral: Object.fromEntries(container.ephemeral),
            mounts: container.mounts
          }
        ])
      )
    };
  }

  #addMount(container, mount) {
    if (container.mounts.some(
      existing => existing.destination === mount.destination
    )) {
      throw new MountConflictError(
        `Destination already mounted: ${mount.destination}`
      );
    }

    container.mounts.push(mount);
  }

  #resolveMount(container, containerPath) {
    const normalized = assertContainerPath(containerPath);

    return container.mounts
      .filter(mount =>
        normalized === mount.destination ||
        normalized.startsWith(`${mount.destination.replace(/\/$/, "")}/`)
      )
      .sort((a, b) => b.destination.length - a.destination.length)[0] || null;
  }

  #dataForMount(mount) {
    if (mount.type === StorageType.NAMED_VOLUME) {
      return this.#volume(mount.source).data;
    }

    if (mount.type === StorageType.BIND_MOUNT) {
      return this.#bindMounts.get(mount.source).data;
    }

    throw new StoragePolicyError("Invalid mounted storage type");
  }

  #relative(containerPath, base = "/") {
    const normalizedPath = assertContainerPath(containerPath);
    const normalizedBase = assertContainerPath(base);

    if (normalizedBase === "/") {
      return normalizedPath.slice(1);
    }

    return normalizedPath
      .slice(normalizedBase.length)
      .replace(/^\/+/, "") || ".";
  }

  #container(id) {
    const container = this.#containers.get(id);

    if (!container) {
      throw new StorageNotFoundError(`Container not found: ${id}`);
    }

    return container;
  }

  #volume(name) {
    const volume = this.#volumes.get(name);

    if (!volume) {
      throw new StorageNotFoundError(`Volume not found: ${name}`);
    }

    return volume;
  }
}

async function demonstrate() {
  const registry = new StorageRegistry();

  registry.on("storage.write", event => {
    console.log(
      `[event] write: ${event.type} ${event.containerId} ${event.path}`
    );
  });

  registry.on("volume.restored", event => {
    console.log(`[event] restored volume: ${event.volumeName}`);
  });

  registry.createNamedVolume("postgres-data");

  registry.registerBindMount(
    "/srv/application/config",
    {
      readOnly: false,
      initialData: {
        "app.conf": "environment=production"
      }
    }
  );

  registry.createContainer("database");
  registry.mountNamedVolume(
    "database",
    "postgres-data",
    "/var/lib/postgresql/data"
  );

  registry.startContainer("database");

  await registry.write(
    "database",
    "/var/lib/postgresql/data/metadata.json",
    JSON.stringify({ version: 1, records: 250 })
  );

  registry.createContainer("application");
  registry.mountBind(
    "application",
    "/srv/application/config",
    "/etc/application",
    true
  );

  console.log(
    "Persistent named-volume data:",
    await registry.read(
      "database",
      "/var/lib/postgresql/data/metadata.json"
    )
  );

  console.log(
    "Host-owned bind data:",
    await registry.read(
      "application",
      "/etc/application/app.conf"
    )
  );

  try {
    await registry.write(
      "application",
      "/etc/application/app.conf",
      "environment=test"
    );
  } catch (error) {
    console.log("Read-only policy rejected write:", error.message);
  }

  registry.createContainer("worker");
  await registry.write("worker", "/tmp/output.txt", "temporary");
  await registry.removeContainer("worker");

  registry.createContainer("worker-replacement");

  try {
    await registry.read("worker-replacement", "/tmp/output.txt");
  } catch (error) {
    console.log(
      "Ephemeral data is absent after container removal:",
      error.message
    );
  }

  const snapshot = registry.volumeSnapshot("postgres-data");
  console.log("Volume snapshot checksum:", snapshot.checksum);

  snapshot.files["metadata.json"] = JSON.stringify({
    version: 2,
    records: 275
  });

  registry.restoreVolume("postgres-data", snapshot);

  console.log(
    "Restored named-volume data:",
    await registry.read(
      "database",
      "/var/lib/postgresql/data/metadata.json"
    )
  );

  console.log(
    "\nHost operating-system temporary directory:",
    os.tmpdir()
  );

  console.log(
    "\nStorage model:",
    JSON.stringify(registry.inspect(), null, 2)
  );

  console.log(
    "\nOperational rule: named volumes are appropriate for container-managed "
    + "persistent data; bind mounts are appropriate when the host path itself "
    + "must remain the source of truth; container writable layers are "
    + "appropriate only for disposable state."
  );
}

demonstrate().catch(error => {
  console.error(`Fatal storage operation failure: ${error.message}`);
  process.exitCode = 1;
});
