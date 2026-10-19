'use strict';

/*
 * Docker image lifecycle event model.
 *
 * This implementation uses JavaScript's event-driven model to represent image
 * construction, cache lookup, tagging, promotion, and retirement. It is
 * intentionally not a line-by-line translation of the Python implementation.
 *
 * Run with:
 *   node docker-image-lifecycle.js
 */

const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');

function digest(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function shortDigest(value) {
  return value.slice(0, 12);
}

function requireNonEmpty(value, fieldName) {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new TypeError(`${fieldName} must be a non-empty string`);
  }
  return value;
}

class ImageLayer {
  constructor({ parent, instruction, input, size }) {
    requireNonEmpty(instruction, 'instruction');
    if (!Number.isInteger(size) || size < 0) {
      throw new RangeError('layer size must be a non-negative integer');
    }

    this.parent = parent ?? null;
    this.instruction = instruction;
    this.input = input ?? '';
    this.size = size;
    this.createdAt = new Date().toISOString();

    this.digest = `sha256:${digest(
      JSON.stringify({
        parent: this.parent,
        instruction: this.instruction,
        input: this.input
      })
    )}`;
  }
}

class DockerImageStore extends EventEmitter {
  constructor() {
    super();
    this.layers = new Map();
    this.images = new Map();
    this.tags = new Map();
    this.cache = new Map();
    this.registry = new Map();
  }

  cacheKey(parent, instruction, input) {
    return digest(JSON.stringify({ parent, instruction, input }));
  }

  getOrCreateLayer(spec) {
    const key = this.cacheKey(
      spec.parent,
      spec.instruction,
      spec.input
    );

    const cachedDigest = this.cache.get(key);

    if (cachedDigest && this.layers.has(cachedDigest)) {
      this.emit('cache-hit', {
        key,
        digest: cachedDigest,
        instruction: spec.instruction
      });
      return {
        layer: this.layers.get(cachedDigest),
        cacheHit: true
      };
    }

    const layer = new ImageLayer(spec);
    this.layers.set(layer.digest, layer);
    this.cache.set(key, layer.digest);

    this.emit('layer-created', {
      digest: layer.digest,
      instruction: layer.instruction,
      size: layer.size
    });

    return {
      layer,
      cacheHit: false
    };
  }

  async build({
    repository,
    tag = 'latest',
    steps,
    buildContext
  }) {
    requireNonEmpty(repository, 'repository');
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new RangeError('a build requires at least one instruction');
    }

    let parent = null;
    const layerDigests = [];
    let cacheHits = 0;
    let cacheMisses = 0;

    for (const step of steps) {
      await new Promise(resolve => setImmediate(resolve));

      const input = buildContext?.[step.input] ?? '';

      const result = this.getOrCreateLayer({
        parent,
        instruction: step.instruction,
        input,
        size: step.size
      });

      if (result.cacheHit) {
        cacheHits += 1;
      } else {
        cacheMisses += 1;
      }

      layerDigests.push(result.layer.digest);
      parent = result.layer.digest;
    }

    const imageId = `sha256:${digest(
      JSON.stringify(layerDigests)
    )}`;

    const image = {
      id: imageId,
      repository,
      layers: Object.freeze([...layerDigests]),
      createdAt: new Date().toISOString()
    };

    this.images.set(imageId, image);
    this.tags.set(`${repository}:${tag}`, imageId);

    this.emit('image-built', {
      image,
      cacheHits,
      cacheMisses
    });

    return {
      image,
      cacheHits,
      cacheMisses
    };
  }

  resolve(reference) {
    if (this.images.has(reference)) {
      return this.images.get(reference);
    }

    const imageId = this.tags.get(reference);

    if (!imageId || !this.images.has(imageId)) {
      throw new Error(`Unknown image reference: ${reference}`);
    }

    return this.images.get(imageId);
  }

  tag(source, repository, tag) {
    const image = this.resolve(source);
    const reference = `${repository}:${tag}`;

    this.tags.set(reference, image.id);

    this.emit('tag-moved', {
      reference,
      imageId: image.id
    });
  }

  async push(source, registryRepository) {
    const image = this.resolve(source);

    // A real registry receives manifests and blobs over a network. This model
    // records the immutable image identity that a repository reference points
    // to, rather than pretending a local Map is a network registry.
    await new Promise(resolve => setImmediate(resolve));

    this.registry.set(registryRepository, image.id);

    this.emit('pushed', {
      repository: registryRepository,
      imageId: image.id
    });
  }

  removeTag(reference) {
    if (!this.tags.delete(reference)) {
      throw new Error(`Tag does not exist: ${reference}`);
    }

    this.emit('tag-removed', { reference });
  }

  imageSize(source) {
    const image = this.resolve(source);

    return image.layers.reduce((total, layerDigest) => {
      const layer = this.layers.get(layerDigest);
      return total + layer.size;
    }, 0);
  }

  inspect(source) {
    const image = this.resolve(source);

    return {
      id: image.id,
      repository: image.repository,
      createdAt: image.createdAt,
      layers: image.layers.map(layerDigest => {
        const layer = this.layers.get(layerDigest);
        return {
          digest: layer.digest,
          instruction: layer.instruction,
          size: layer.size
        };
      })
    };
  }
}

function megabytes(value) {
  return value * 1024 * 1024;
}

function attachAuditLogging(store) {
  store.on('cache-hit', event => {
    console.log(
      `CACHE HIT  ${shortDigest(event.digest)}  ${event.instruction}`
    );
  });

  store.on('layer-created', event => {
    console.log(
      `LAYER NEW  ${shortDigest(event.digest)}  ${event.instruction}`
    );
  });

  store.on('tag-moved', event => {
    console.log(
      `TAG MOVE   ${event.reference} -> ${shortDigest(event.imageId)}`
    );
  });

  store.on('pushed', event => {
    console.log(
      `PUSH       ${event.repository} -> ${shortDigest(event.imageId)}`
    );
  });
}

async function run() {
  const store = new DockerImageStore();
  attachAuditLogging(store);

  const steps = [
    {
      instruction: 'FROM node:24-alpine',
      input: 'base',
      size: megabytes(8)
    },
    {
      instruction: 'COPY package*.json /workspace/',
      input: 'package-lock',
      size: 12 * 1024
    },
    {
      instruction: 'RUN npm ci --omit=dev',
      input: 'package-lock',
      size: megabytes(32)
    },
    {
      instruction: 'COPY src/ /workspace/src/',
      input: 'source',
      size: 180 * 1024
    }
  ];

  const stableContext = {
    base: 'node-24-alpine-digest',
    'package-lock': 'lockfile-v1',
    source: 'source-v1'
  };

  console.log('=== First build ===');

  const first = await store.build({
    repository: 'payments-api',
    tag: '1.0.0',
    steps,
    buildContext: stableContext
  });

  console.log(
    `cache hits=${first.cacheHits}, misses=${first.cacheMisses}`
  );

  console.log('\n=== Source-only rebuild ===');

  const changedSource = {
    ...stableContext,
    source: 'source-v2'
  };

  const second = await store.build({
    repository: 'payments-api',
    tag: '1.0.1',
    steps,
    buildContext: changedSource
  });

  console.log(
    `cache hits=${second.cacheHits}, misses=${second.cacheMisses}`
  );

  store.tag(
    'payments-api:1.0.1',
    'payments-api',
    'candidate'
  );

  await store.push(
    'payments-api:candidate',
    'registry.internal/payments-api'
  );

  console.log('\n=== Image inspection ===');

  const inspected = store.inspect('payments-api:candidate');

  for (const layer of inspected.layers) {
    console.log(
      `${shortDigest(layer.digest)} | ${layer.size} bytes | ${layer.instruction}`
    );
  }

  console.log(
    `logical layer size: ${store.imageSize('payments-api:candidate')} bytes`
  );

  console.log('\n=== Cache invalidation boundary ===');

  const dependencyChange = {
    ...changedSource,
    'package-lock': 'lockfile-v2'
  };

  const third = await store.build({
    repository: 'payments-api',
    tag: '2.0.0',
    steps,
    buildContext: dependencyChange
  });

  console.log(
    `dependency change: cache hits=${third.cacheHits}, ` +
    `misses=${third.cacheMisses}`
  );

  console.log(
    '\nThe package-lock change invalidates dependency installation and ' +
    'the source COPY step that follows it.'
  );

  console.log('\n=== Tag lifecycle ===');

  store.tag(
    'payments-api:2.0.0',
    'payments-api',
    'candidate'
  );

  console.log(
    `candidate now points to ${shortDigest(
      store.resolve('payments-api:candidate').id
    )}`
  );

  store.tag(
    'payments-api:candidate',
    'payments-api',
    'production'
  );

  console.log(
    `production points to ${shortDigest(
      store.resolve('payments-api:production').id
    )}`
  );

  store.removeTag('payments-api:candidate');

  console.log(
    'candidate tag removed; the immutable image can still exist through ' +
    'the production tag.'
  );
}

run().catch(error => {
  console.error(`Image workflow failed: ${error.message}`);
  process.exitCode = 1;
});
