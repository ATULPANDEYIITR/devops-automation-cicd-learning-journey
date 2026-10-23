'use strict';

/**
 * Docker network behavior model.
 *
 * This implementation focuses on event-driven policy evaluation:
 * network creation, container attachment, service discovery, port
 * publishing, and connectivity checks are represented as events.
 *
 * Run with:
 *   node docker-networks.js
 */

const EventEmitter = require('node:events');

const NetworkMode = Object.freeze({
  BRIDGE: 'bridge',
  HOST: 'host',
  CONTAINER: 'container'
});

class NetworkError extends Error {}

class DockerNetworkController extends EventEmitter {
  #networks = new Map();
  #containers = new Map();
  #publishedPorts = new Map();

  constructor() {
    super();
    this.on('containerStarted', event =>
      console.log(`[event] container started: ${event.name}`)
    );
    this.on('networkConnected', event =>
      console.log(`[event] ${event.container} connected to ${event.network} as ${event.ip}`)
    );
  }

  createBridge(name, subnet, gateway) {
    if (this.#networks.has(name)) {
      throw new NetworkError(`Network ${name} already exists.`);
    }

    const [networkAddress, prefixText] = subnet.split('/');
    const prefix = Number(prefixText);

    if (!networkAddress || !Number.isInteger(prefix) || prefix < 16 || prefix > 30) {
      throw new NetworkError('Expected an IPv4 CIDR between /16 and /30.');
    }

    const network = {
      name,
      driver: 'bridge',
      subnet,
      gateway: gateway ?? networkAddress,
      endpoints: new Map()
    };

    this.#networks.set(name, network);
    return network;
  }

  startContainer({
    name,
    mode = NetworkMode.BRIDGE,
    network,
    ip,
    shareWith
  }) {
    if (this.#containers.has(name)) {
      throw new NetworkError(`Container ${name} already exists.`);
    }

    if (mode === NetworkMode.BRIDGE && !this.#networks.has(network)) {
      throw new NetworkError(`Unknown bridge network: ${network}`);
    }

    if (mode === NetworkMode.CONTAINER) {
      const source = this.#containers.get(shareWith);
      if (!source) {
        throw new NetworkError(`Shared network container ${shareWith} does not exist.`);
      }

      const container = {
        name,
        mode,
        networks: new Map(source.networks),
        ports: new Set(),
        publishedPorts: new Map(),
        sharedWith: shareWith
      };

      this.#containers.set(name, container);
      this.emit('containerStarted', container);
      return container;
    }

    const container = {
      name,
      mode,
      networks: new Map(),
      ports: new Set(),
      publishedPorts: new Map()
    };

    this.#containers.set(name, container);

    if (mode === NetworkMode.BRIDGE) {
      this.connectContainer(name, network, ip);
    }

    this.emit('containerStarted', container);
    return container;
  }

  connectContainer(containerName, networkName, requestedIp) {
    const container = this.#requireContainer(containerName);
    const network = this.#requireNetwork(networkName);

    if (container.mode !== NetworkMode.BRIDGE) {
      throw new NetworkError(
        'Dynamic network attachment is restricted to bridge-mode containers.'
      );
    }

    const ip = requestedIp || this.#allocateIp(network);

    if (network.endpoints.has(ip)) {
      throw new NetworkError(`IP ${ip} is already allocated.`);
    }

    network.endpoints.set(ip, containerName);
    container.networks.set(networkName, ip);

    this.emit('networkConnected', {
      container: containerName,
      network: networkName,
      ip
    });

    return ip;
  }

  expose(containerName, port, protocol = 'tcp') {
    const container = this.#requireContainer(containerName);
    this.#validatePort(port);
    container.ports.add(`${protocol.toLowerCase()}/${port}`);
  }

  publishPort(containerName, hostPort, containerPort, protocol = 'tcp') {
    const container = this.#requireContainer(containerName);

    if (container.mode === NetworkMode.HOST) {
      throw new NetworkError('Host mode does not require Docker port publishing.');
    }

    this.#validatePort(hostPort);
    this.#validatePort(containerPort);

    const key = `${protocol.toLowerCase()}/${containerPort}`;
    if (!container.ports.has(key)) {
      throw new NetworkError(
        `${containerName} does not expose ${key}.`
      );
    }

    if (this.#publishedPorts.has(hostPort)) {
      throw new NetworkError(`Host port ${hostPort} is already allocated.`);
    }

    container.publishedPorts.set(hostPort, containerPort);
    this.#publishedPorts.set(hostPort, {
      container: containerName,
      containerPort,
      protocol: protocol.toLowerCase()
    });
  }

  resolve(sourceName, targetName) {
    const source = this.#requireContainer(sourceName);
    const target = this.#requireContainer(targetName);

    if (target.mode === NetworkMode.HOST) {
      return 'host';
    }

    for (const [networkName] of source.networks) {
      if (target.networks.has(networkName)) {
        return target.networks.get(networkName);
      }
    }

    return null;
  }

  evaluateConnection(sourceName, targetName, port, protocol = 'tcp') {
    const source = this.#requireContainer(sourceName);
    const target = this.#requireContainer(targetName);

    this.#validatePort(port);

    if (sourceName === targetName) {
      return { allowed: false, reason: 'Self-connection is outside this model.' };
    }

    const protocolPort = `${protocol.toLowerCase()}/${port}`;

    if (target.mode === NetworkMode.HOST) {
      if (target.ports.has(protocolPort)) {
        return {
          allowed: true,
          reason: 'Traffic terminates in the host network namespace.'
        };
      }

      return {
        allowed: false,
        reason: 'The requested host port is not listening.'
      };
    }

    if (source.mode === NetworkMode.HOST) {
      if (target.mode === NetworkMode.BRIDGE && target.ports.has(protocolPort)) {
        return {
          allowed: true,
          reason: 'Host namespace can reach the bridge endpoint.'
        };
      }

      return {
        allowed: false,
        reason: 'No modeled route exists from the host namespace.'
      };
    }

    const shared = [...source.networks.keys()]
      .filter(networkName => target.networks.has(networkName));

    if (shared.length === 0) {
      return {
        allowed: false,
        reason: 'Containers do not share a Docker network.'
      };
    }

    if (!target.ports.has(protocolPort)) {
      return {
        allowed: false,
        reason: `${targetName} is not listening on ${protocolPort}.`
      };
    }

    return {
      allowed: true,
      reason: `Reachable through ${shared[0]}.`
    };
  }

  inspectNetwork(name) {
    const network = this.#requireNetwork(name);

    return {
      name: network.name,
      driver: network.driver,
      subnet: network.subnet,
      gateway: network.gateway,
      endpoints: Object.fromEntries(network.endpoints)
    };
  }

  inspectContainer(name) {
    const container = this.#requireContainer(name);

    return {
      name: container.name,
      mode: container.mode,
      networks: Object.fromEntries(container.networks),
      ports: [...container.ports],
      publishedPorts: Object.fromEntries(container.publishedPorts),
      sharedWith: container.sharedWith ?? null
    };
  }

  async evaluateAsync(source, target, port) {
    await new Promise(resolve => setImmediate(resolve));
    return this.evaluateConnection(source, target, port);
  }

  #allocateIp(network) {
    const base = network.subnet.split('/')[0].split('.').map(Number);
    const prefix = Number(network.subnet.split('/')[1]);
    const hostCount = 2 ** (32 - prefix);

    for (let offset = 2; offset < hostCount - 1; offset++) {
      const value = (base[0] << 24) |
        (base[1] << 16) |
        (base[2] << 8) |
        base[3];

      const candidate = (value + offset) >>> 0;
      const ip = [
        (candidate >>> 24) & 255,
        (candidate >>> 16) & 255,
        (candidate >>> 8) & 255,
        candidate & 255
      ].join('.');

      if (ip !== network.gateway && !network.endpoints.has(ip)) {
        return ip;
      }
    }

    throw new NetworkError(`No free addresses remain in ${network.name}.`);
  }

  #validatePort(port) {
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new NetworkError(`Invalid port: ${port}`);
    }
  }

  #requireContainer(name) {
    const container = this.#containers.get(name);
    if (!container) {
      throw new NetworkError(`Unknown container: ${name}`);
    }
    return container;
  }

  #requireNetwork(name) {
    const network = this.#networks.get(name);
    if (!network) {
      throw new NetworkError(`Unknown network: ${name}`);
    }
    return network;
  }
}

async function main() {
  const controller = new DockerNetworkController();

  controller.createBridge('frontend', '172.30.0.0/24', '172.30.0.1');
  controller.createBridge('backend', '172.31.0.0/24', '172.31.0.1');

  controller.startContainer({
    name: 'web',
    mode: NetworkMode.BRIDGE,
    network: 'frontend',
    ip: '172.30.0.10'
  });

  controller.startContainer({
    name: 'api',
    mode: NetworkMode.BRIDGE,
    network: 'backend',
    ip: '172.31.0.10'
  });

  controller.connectContainer('api', 'frontend', '172.30.0.20');

  controller.startContainer({
    name: 'db',
    mode: NetworkMode.BRIDGE,
    network: 'backend',
    ip: '172.31.0.30'
  });

  controller.startContainer({
    name: 'monitor',
    mode: NetworkMode.HOST
  });

  controller.startContainer({
    name: 'api-worker',
    mode: NetworkMode.CONTAINER,
    shareWith: 'api'
  });

  controller.expose('web', 8080);
  controller.expose('api', 8080);
  controller.expose('db', 5432);
  controller.expose('monitor', 9090);

  controller.publishPort('web', 8080, 8080);

  console.log('\n=== Networks ===');
  console.dir(controller.inspectNetwork('frontend'), { depth: null });
  console.dir(controller.inspectNetwork('backend'), { depth: null });

  console.log('\n=== Containers ===');
  for (const name of ['web', 'api', 'db', 'api-worker', 'monitor']) {
    console.dir(controller.inspectContainer(name), { depth: null });
  }

  console.log('\n=== DNS-Style Resolution ===');
  console.log('web -> api:', controller.resolve('web', 'api'));
  console.log('web -> db:', controller.resolve('web', 'db'));

  console.log('\n=== Connectivity ===');
  for (const [source, target, port] of [
    ['web', 'api', 8080],
    ['api', 'db', 5432],
    ['web', 'db', 5432],
    ['api-worker', 'db', 5432]
  ]) {
    console.log(
      `${source} -> ${target}:${port}`,
      controller.evaluateConnection(source, target, port)
    );
  }

  console.log('\n=== Asynchronous Policy Evaluation ===');
  console.log(await controller.evaluateAsync('web', 'api', 8080));

  console.log('\n=== Failure Handling ===');
  try {
    controller.publishPort('db', 8080, 8080);
  } catch (error) {
    console.log('Rejected:', error.message);
  }
}

main().catch(error => {
  console.error(`Fatal error: ${error.message}`);
  process.exitCode = 1;
});
