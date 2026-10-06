"use strict";

/*
 * Build artifact lifecycle model for Node.js.
 *
 * The implementation focuses on artifact creation, immutable storage,
 * metadata, checksums, downloading, verification, retention, and safe
 * extraction. It intentionally uses Node's standard library only.
 */

const fs = require("node:fs");
const fsp = require("node:fs/promises");
const crypto = require("node:crypto");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

function sha256File(filePath) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(filePath);

    stream.on("data", chunk => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

async function ensureDirectory(directory) {
  await fsp.mkdir(directory, { recursive: true });
}

async function writeJson(filePath, value) {
  await fsp.writeFile(filePath, JSON.stringify(value, null, 2), "utf8");
}

async function collectFiles(root) {
  const results = [];

  async function walk(current) {
    const entries = await fsp.readdir(current, { withFileTypes: true });

    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
      const absolute = path.join(current, entry.name);

      if (entry.isDirectory()) {
        await walk(absolute);
      } else if (entry.isFile()) {
        const stat = await fsp.stat(absolute);
        results.push({
          absolute,
          relativePath: path.relative(root, absolute).split(path.sep).join("/"),
          sizeBytes: stat.size,
          sha256: await sha256File(absolute)
        });
      }
    }
  }

  await walk(root);
  return results;
}

async function createBuildOutput(directory) {
  await ensureDirectory(path.join(directory, "dist"));
  await ensureDirectory(path.join(directory, "config"));

  await fsp.writeFile(
    path.join(directory, "dist", "release.txt"),
    "service=payments-api\nversion=2026.10.06\nprofile=production\n",
    "utf8"
  );

  await writeJson(path.join(directory, "config", "runtime.json"), {
    environment: "production",
    artifactFormat: "tar.gz",
    immutable: true
  });
}

function createTarGzip(sourceDirectory, archivePath) {
  /*
   * Node's standard library does not expose a tar writer. The tar command is
   * used only for packaging, while Node performs metadata, hashing, storage,
   * validation, and lifecycle management.
   */
  const result = spawnSync(
    "tar",
    ["-czf", archivePath, "-C", sourceDirectory, "."],
    { encoding: "utf8" }
  );

  if (result.error) {
    throw new Error(
      `Unable to execute tar. A tar implementation is required: ${result.error.message}`
    );
  }

  if (result.status !== 0) {
    throw new Error(`tar failed: ${result.stderr || "unknown error"}`);
  }
}

async function buildArtifact({
  sourceDirectory,
  stagingDirectory,
  repository,
  commitSha,
  buildNumber,
  retentionDays
}) {
  const files = await collectFiles(sourceDirectory);

  if (files.length === 0) {
    throw new Error("An empty build output cannot be published.");
  }

  const artifactId =
    `${repository.replaceAll("/", "-")}-${buildNumber}-` +
    crypto.randomUUID().slice(0, 12);

  const archivePath = path.join(stagingDirectory, `${artifactId}.tar.gz`);
  const manifestPath = path.join(stagingDirectory, `${artifactId}.manifest.json`);

  createTarGzip(sourceDirectory, archivePath);

  const archiveSha256 = await sha256File(archivePath);

  const manifest = {
    schemaVersion: 1,
    artifactId,
    repository,
    commitSha,
    buildNumber,
    createdAt: new Date().toISOString(),
    retentionDays,
    totalSizeBytes: files.reduce((sum, file) => sum + file.sizeBytes, 0),
    archiveSha256,
    files: files.map(file => ({
      relativePath: file.relativePath,
      sizeBytes: file.sizeBytes,
      sha256: file.sha256
    }))
  };

  await writeJson(manifestPath, manifest);

  return { artifactId, archivePath, manifestPath, manifest };
}

class ArtifactStore {
  constructor(rootDirectory) {
    this.rootDirectory = rootDirectory;
  }

  async initialize() {
    await ensureDirectory(this.rootDirectory);
  }

  archivePath(artifactId) {
    return path.join(this.rootDirectory, `${artifactId}.tar.gz`);
  }

  manifestPath(artifactId) {
    return path.join(this.rootDirectory, `${artifactId}.manifest.json`);
  }

  async upload(artifact) {
    const actualHash = await sha256File(artifact.archivePath);

    if (actualHash !== artifact.manifest.archiveSha256) {
      throw new Error("Refusing upload because the archive checksum is invalid.");
    }

    /*
     * The store uses a content key that is tied to the artifact identifier.
     * A production object store would normally make the object immutable or
     * restrict overwrites through bucket-level policy.
     */
    await fsp.copyFile(
      artifact.archivePath,
      this.archivePath(artifact.artifactId),
      fs.constants.COPYFILE_EXCL
    ).catch(error => {
      if (error.code === "EEXIST") {
        throw new Error("Artifact already exists and cannot be overwritten.");
      }
      throw error;
    });

    await writeJson(this.manifestPath(artifact.artifactId), artifact.manifest);
  }

  async download(artifactId, destinationDirectory, expectedSha256) {
    const source = this.archivePath(artifactId);

    await fsp.access(source);
    await ensureDirectory(destinationDirectory);

    const destination = path.join(
      destinationDirectory,
      `${artifactId}.tar.gz`
    );

    await fsp.copyFile(source, destination);

    const actualHash = await sha256File(destination);

    if (expectedSha256 && actualHash !== expectedSha256) {
      await fsp.rm(destination, { force: true });
      throw new Error(
        `Downloaded artifact failed checksum validation. Expected ${expectedSha256}, got ${actualHash}.`
      );
    }

    return destination;
  }

  async readManifest(artifactId) {
    const content = await fsp.readFile(this.manifestPath(artifactId), "utf8");
    const manifest = JSON.parse(content);

    if (manifest.schemaVersion !== 1) {
      throw new Error("Unsupported artifact manifest version.");
    }

    return manifest;
  }

  async list() {
    const entries = await fsp.readdir(this.rootDirectory);
    const artifacts = [];

    for (const entry of entries.filter(name => name.endsWith(".manifest.json"))) {
      const artifactId = entry.slice(0, -".manifest.json".length);
      const manifest = await this.readManifest(artifactId);
      artifacts.push(manifest);
    }

    return artifacts.sort((a, b) =>
      a.createdAt.localeCompare(b.createdAt)
    );
  }

  async purgeExpired(now = new Date()) {
    const manifests = await this.list();
    const deleted = [];

    for (const manifest of manifests) {
      const created = new Date(manifest.createdAt);
      const expires = new Date(
        created.getTime() + manifest.retentionDays * 86400000
      );

      if (now >= expires) {
        await fsp.rm(this.archivePath(manifest.artifactId), { force: true });
        await fsp.rm(this.manifestPath(manifest.artifactId), { force: true });
        deleted.push(manifest.artifactId);
      }
    }

    return deleted;
  }
}

async function demonstrateEventDrivenLifecycle() {
  /*
   * EventEmitter is useful when upload completion triggers downstream work.
   * A real CI system could connect these events to deployment, notification,
   * indexing, or provenance services.
   */
  const { EventEmitter } = require("node:events");
  const events = new EventEmitter();

  events.on("artifact:uploaded", artifact => {
    console.log(`EVENT uploaded: ${artifact.artifactId}`);
  });

  events.on("artifact:verified", artifact => {
    console.log(`EVENT verified: ${artifact.artifactId}`);
  });

  return events;
}

async function main() {
  const root = await fsp.mkdtemp(path.join(os.tmpdir(), "artifact-node-"));
  const buildDirectory = path.join(root, "build");
  const stagingDirectory = path.join(root, "staging");
  const repositoryDirectory = path.join(root, "repository");
  const downloadDirectory = path.join(root, "downloads");

  await Promise.all([
    ensureDirectory(buildDirectory),
    ensureDirectory(stagingDirectory),
    ensureDirectory(repositoryDirectory),
    ensureDirectory(downloadDirectory)
  ]);

  await createBuildOutput(buildDirectory);

  const artifact = await buildArtifact({
    sourceDirectory: buildDirectory,
    stagingDirectory,
    repository: "platform/release-service",
    commitSha: "7f3d8a2b91c4",
    buildNumber: 184,
    retentionDays: 30
  });

  console.log("Artifact created:", artifact.artifactId);
  console.log("Archive SHA-256:", artifact.manifest.archiveSha256);

  const store = new ArtifactStore(repositoryDirectory);
  await store.initialize();

  const events = await demonstrateEventDrivenLifecycle();

  await store.upload(artifact);
  events.emit("artifact:uploaded", artifact);

  const downloadedPath = await store.download(
    artifact.artifactId,
    downloadDirectory,
    artifact.manifest.archiveSha256
  );

  console.log("Downloaded:", path.basename(downloadedPath));

  /*
   * Verification is deliberately separate from download. A successful transfer
   * does not by itself prove that the downloaded bytes are the intended build.
   */
  const verifiedHash = await sha256File(downloadedPath);

  if (verifiedHash !== artifact.manifest.archiveSha256) {
    throw new Error("Post-download integrity verification failed.");
  }

  events.emit("artifact:verified", artifact);

  const manifest = await store.readManifest(artifact.artifactId);
  console.log("Manifest commit:", manifest.commitSha);
  console.log("Manifest file count:", manifest.files.length);

  const stored = await store.list();
  console.log("Stored artifact count:", stored.length);

  const deleted = await store.purgeExpired(
    new Date(Date.now() + 31 * 86400000)
  );
  console.log("Retention cleanup:", deleted);

  await fsp.rm(root, { recursive: true, force: true });
}

main().catch(error => {
  console.error(`Artifact lifecycle failed: ${error.message}`);
  process.exitCode = 1;
});
