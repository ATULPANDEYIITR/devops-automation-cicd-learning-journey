"use strict";

/*
 * Docker fundamentals using an event-driven deployment model.
 * Run with Node.js 18 or later. No npm dependencies are required.
 *
 * This model emphasizes asynchronous registry access, immutable image
 * metadata, container events, network publishing, and deployment policy.
 */

const { EventEmitter } = require("node:events");
const { createHash } = require("node:crypto");

class DockerError extends Error {
  constructor(message, code) {
    super(message);
    this.name = "DockerError";
    this.code = code;
  }
}

function digest(content) {
  return `sha256:${createHash("sha256").update(content).digest("hex")}`;
}

function createImage({
  repository,
  tag,
  layers,
  entrypoint,
  environment = {},
}) {
  if (!repository || !tag || !Array.isArray(layers) || layers.length === 0) {
    throw new DockerError("Image metadata is incomplete", "INVALID_IMAGE");
  }
  if (!Array.isArray(entrypoint) || entrypoint.length === 0) {
    throw new DockerError("Image entrypoint is required", "INVALID_ENTRYPOINT");
  }

  const immutableLayers = layers.map((layer) => {
    if (!layer.instruction || !Number.isFinite(layer.sizeMB) ||
        layer.sizeMB < 0) {
      throw new DockerError("Invalid image layer", "INVALID_LAYER");
    }
    return Object.freeze({
      digest: layer.digest || digest(layer.instruction),
      instruction: layer.instruction,
      sizeMB: layer.sizeMB,
    });
  });

  return Object.freeze({
    repository,
    tag,
    reference: `${repository}:${tag}`,
    layers: Object.freeze(immutableLayers),
    entrypoint: Object.freeze([...entrypoint]),
    environment: Object.freeze({ ...environment }),
  });
}

class LocalImageStore {
  constructor() {
    this.images = new Map();
    this.layers = new Map();
  }

  add(image) {
    this.images.set(image.reference, image);
    for (const layer of image.layers) {
      // Identical layer digests share local storage.
      if (!this.layers.has(layer.digest)) {
        this.layers.set(layer.digest, layer);
      }
    }
  }

  require(reference) {
    const image = this.images.get(reference);
    if (!image) {
      throw new DockerError(`Local image not found: ${reference}`, "NOT_FOUND");
    }
    return image;
  }

  storageMB() {
    return [...this.layers.values()].reduce(
      (total, layer) => total + layer.sizeMB,
      0,
    );
  }
}

class ImageRegistry {
  constructor(hostname) {
    if (!hostname || hostname.includes("/")) {
      throw new DockerError("Invalid registry hostname", "INVALID_REGISTRY");
    }
    this.hostname = hostname;
    this.images = new Map();
    this.authenticated = false;
  }

  async login(token) {
    // A real registry uses HTTPS and a credential helper or secret manager.
    if (typeof token !== "string" || token.trim() === "") {
      throw new DockerError("Registry token is required", "UNAUTHORIZED");
    }
    await Promise.resolve();
    this.authenticated = true;
  }

  async push(image, repository, tag) {
    if (!this.authenticated) {
      throw new DockerError("Registry login required", "UNAUTHORIZED");
    }
    if (!repository || !tag) {
      throw new DockerError("Repository and tag are required", "INVALID_TAG");
    }

    const reference = `${this.hostname}/${repository}:${tag}`;
    await Promise.resolve();

    // The simulated registry records a manifest referencing immutable layers.
    this.images.set(reference, image);
    return reference;
  }

  async pull(reference, store) {
    await Promise.resolve();
    const image = this.images.get(reference);
    if (!image) {
      throw new DockerError(
        `Registry image not found: ${reference}`,
        "NOT_FOUND",
      );
    }
    store.add(image);
    return image;
  }
}

class DockerHost extends EventEmitter {
  constructor({ memoryMB = 4096 } = {}) {
    super();
    if (!Number.isInteger(memoryMB) || memoryMB <= 0) {
      throw new DockerError("Host memory must be a positive integer", "LIMIT");
    }
    this.memoryMB = memoryMB;
    this.images = new LocalImageStore();
    this.containers = new Map();
    this.hostPorts = new Map();
    this.nextID = 1;
  }

  createContainer({
    name,
    imageReference,
    command,
    environment = {},
    ports = {},
    memoryMB = 256,
  }) {
    const image = this.images.require(imageReference);
    if (!name || [...this.containers.values()].some(
      (container) => container.name === name && container.state !== "removed",
    )) {
      throw new DockerError("Container name is invalid or duplicated", "NAME");
    }
    if (!Number.isInteger(memoryMB) || memoryMB <= 0 ||
        memoryMB > this.memoryMB) {
      throw new DockerError("Invalid container memory limit", "MEMORY_LIMIT");
    }

    const portBindings = new Map();
    for (const [containerPortText, hostPortValue] of Object.entries(ports)) {
      const containerPort = Number(containerPortText);
      const hostPort = Number(hostPortValue);

      if (![containerPort, hostPort].every(
        (port) => Number.isInteger(port) && port >= 1 && port <= 65535,
      )) {
        throw new DockerError("Invalid TCP port binding", "INVALID_PORT");
      }
      if (this.hostPorts.has(hostPort)) {
        throw new DockerError(`Host port ${hostPort} is occupied`, "PORT_BUSY");
      }
      portBindings.set(containerPort, hostPort);
    }

    const container = {
      id: String(this.nextID++).padStart(12, "0"),
      name,
      imageReference,
      command: command ? [...command] : [...image.entrypoint],
      environment: { ...image.environment, ...environment },
      ports: portBindings,
      memoryMB,
      state: "created",
      exitCode: null,
    };

    this.containers.set(container.id, container);
    for (const hostPort of portBindings.values()) {
      this.hostPorts.set(hostPort, container.id);
    }
    this.emit("container.created", this.snapshot(container));
    return container.id;
  }

  snapshot(container) {
    return {
      id: container.id,
      name: container.name,
      imageReference: container.imageReference,
      state: container.state,
      ports: Object.fromEntries(container.ports),
      memoryMB: container.memoryMB,
    };
  }

  requireContainer(id) {
    const container = this.containers.get(id);
    if (!container) {
      throw new DockerError(`Unknown container ${id}`, "NOT_FOUND");
    }
    return container;
  }

  start(id) {
    const container = this.requireContainer(id);
    if (!["created", "stopped"].includes(container.state)) {
      throw new DockerError(
        `Cannot start a ${container.state} container`,
        "INVALID_STATE",
      );
    }
    container.state = "running";
    container.exitCode = null;
    this.emit("container.started", this.snapshot(container));
  }

  stop(id, exitCode = 0) {
    const container = this.requireContainer(id);
    if (container.state !== "running") {
      throw new DockerError("Container is not running", "INVALID_STATE");
    }
    container.state = "stopped";
    container.exitCode = exitCode;
    this.emit("container.stopped", {
      ...this.snapshot(container),
      exitCode,
    });
  }

  remove(id) {
    const container = this.requireContainer(id);
    if (container.state === "running" || container.state === "removed") {
      throw new DockerError(
        "Stop the container before removing it",
        "INVALID_STATE",
      );
    }

    for (const hostPort of container.ports.values()) {
      this.hostPorts.delete(hostPort);
    }
    container.state = "removed";
    this.emit("container.removed", this.snapshot(container));
  }

  runningMemoryLimits() {
    return [...this.containers.values()]
      .filter((container) => container.state === "running")
      .reduce((sum, container) => sum + container.memoryMB, 0);
  }
}

function evaluateDeploymentPolicy({ image, host, containerID }) {
  const container = host.requireContainer(containerID);
  const failures = [];

  if (!image.reference.includes(":")) {
    failures.push("Image reference must contain a tag");
  }
  if (image.tag === "latest") {
    failures.push("Production deployments must use an explicit version");
  }
  if (container.state !== "running") {
    failures.push("Container must be running after deployment");
  }
  if (container.memoryMB < 128) {
    failures.push("Memory limit is below the deployment minimum");
  }

  return {
    eligible: failures.length === 0,
    failures,
  };
}

async function main() {
  const host = new DockerHost({ memoryMB: 2048 });

  // Event listeners observe state changes without controlling the lifecycle.
  host.on("container.created", (event) => {
    console.log(`[event] created ${event.name} (${event.id})`);
  });
  host.on("container.started", (event) => {
    console.log(`[event] started ${event.name}`);
  });
  host.on("container.stopped", (event) => {
    console.log(`[event] stopped ${event.name}, exit=${event.exitCode}`);
  });
  host.on("container.removed", (event) => {
    console.log(`[event] removed ${event.name}`);
  });

  const apiImage = createImage({
    repository: "warehouse-api",
    tag: "2.4.1",
    layers: [
      { instruction: "Node.js runtime", sizeMB: 65 },
      { instruction: "Production dependencies", sizeMB: 30 },
      { instruction: "Application bundle", sizeMB: 9 },
    ],
    entrypoint: ["node", "server.js"],
    environment: { NODE_ENV: "production" },
  });

  host.images.add(apiImage);

  const registry = new ImageRegistry("registry.example.com");
  try {
    await registry.push(apiImage, "operations/warehouse-api", "2.4.1");
  } catch (error) {
    console.log("Expected registry failure:", error.code);
  }

  await registry.login("demo-token");
  const remoteReference = await registry.push(
    apiImage,
    "operations/warehouse-api",
    "2.4.1",
  );
  console.log("Published image:", remoteReference);

  const deploymentStore = new LocalImageStore();
  const pulledImage = await registry.pull(remoteReference, deploymentStore);
  console.log("Deployment host pulled:", pulledImage.reference);

  const containerID = host.createContainer({
    name: "warehouse-api",
    imageReference: apiImage.reference,
    ports: { 3000: 13000 },
    environment: { LOG_LEVEL: "info" },
    memoryMB: 512,
  });

  host.start(containerID);

  console.log("Policy result:", evaluateDeploymentPolicy({
    image: apiImage,
    host,
    containerID,
  }));
  console.log("Running configured memory:", host.runningMemoryLimits(), "MB");
  console.log("Unique image-layer storage:", host.images.storageMB(), "MB");

  try {
    host.createContainer({
      name: "metrics",
      imageReference: apiImage.reference,
      ports: { 3000: 13000 },
    });
  } catch (error) {
    console.log("Expected port allocation failure:", error.code);
  }

  try {
    host.remove(containerID);
  } catch (error) {
    console.log("Expected lifecycle failure:", error.code);
  }

  host.stop(containerID);
  host.remove(containerID);

  console.log("Container lifecycle completed.");
}

main().catch((error) => {
  // A top-level rejection handler prevents silent failures in asynchronous
  // registry operations and keeps error diagnostics actionable.
  console.error("Deployment demonstration failed:", error.message);
  process.exitCode = 1;
});
