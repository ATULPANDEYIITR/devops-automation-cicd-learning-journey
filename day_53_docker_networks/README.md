# Docker Networks: Bridge, Host, and Container Networking

## Scope

This project models three Docker networking modes as distinct mechanisms:

- **Bridge networking** gives containers their own network identity and connects them through a virtual bridge.
- **Host networking** removes the container-specific network namespace and places the workload in the host network namespace.
- **Container networking** shares the network namespace of another container.

The five implementations use different perspectives rather than translating one program into five languages. Python provides a repository-style simulation of network objects and connectivity. JavaScript models network events and asynchronous policy evaluation. C++ implements a strongly typed topology and connectivity engine. Java models network behavior through enterprise-oriented domain types and services. PostgreSQL represents the same domain as relational state with constraints, triggers, views, functions, and transactional operations.

The central relationship is:

**Network mode → network namespace → endpoint identity → routing/connectivity → port exposure or publication**

A bridge network supplies container endpoints. Host mode changes where the endpoint exists. Container mode reuses another container's network namespace.

---

## Network Modes

| Mode | Network namespace | Container IP | Typical connectivity model | Port publishing |
|---|---|---|---|---|
| `bridge` | Separate container namespace | Yes | Virtual bridge and shared Docker network | Supported |
| `host` | Host namespace | No container-specific IP | Direct host networking | Not required |
| `container` | Shares another container namespace | Same namespace identity | Uses the other container's networking | Controlled by shared namespace |

### Bridge networking

Bridge mode is the normal isolated container networking model represented in this project.

A bridge network has:

- a subnet
- a gateway
- container endpoints
- private IP addresses
- optional membership from multiple containers

A container can be attached to more than one bridge network. This is important for service architectures where one component connects an application-facing network to a database or internal-services network.

The Python, C++, Java, and SQL implementations model this explicitly. The JavaScript implementation uses a `Map` for network membership and endpoint state.

The sample topology contains a frontend network and backend network:

```text
                  frontend
             172.50.0.0/24
                    |
              +-----+-----+
              |           |
             web          api
          .50.0.10     .50.0.20
                            |
                            |
                         backend
                    172.51.0.0/24
                            |
                       database
                       .51.0.30
```

The API container is attached to both networks. This gives it two network interfaces and makes it the modeled boundary between the frontend and backend connectivity domains.

### Host networking

Host mode does not assign a separate bridge-network IP to the container.

The process instead uses the host's network namespace. The important consequence is not merely that the container can "see the host"; the network identity itself is shared.

The implementations therefore reject Docker-style host-port publication for host-mode containers. A process listening on a host-mode port is modeled as listening directly in the host namespace.

This mode can reduce networking overhead, but it reduces network isolation and can create port conflicts with host services.

### Container networking

Container mode is represented by a second container sharing the network namespace of an existing container.

The `api-worker` example shares the namespace of `api`. It therefore receives the same modeled network identity rather than a new independent bridge endpoint.

This differs fundamentally from connecting two containers to the same bridge network:

- Shared bridge: two independent network namespaces communicate through a network.
- Container mode: two containers use the same network namespace.

That distinction matters for port binding, interface visibility, and network identity.

---

## Pulling the Network Model Apart

The implementations keep several concepts separate because they solve different problems.

| Concept | Meaning |
|---|---|
| Network | Connectivity domain with subnet and gateway |
| Endpoint | Container attachment to a network |
| IP address | Network-layer identity of an endpoint |
| Listening port | Application endpoint inside a namespace |
| Published port | Host-to-container port mapping |
| Network mode | Determines namespace and isolation behavior |
| Shared namespace | Container-mode relationship |
| Connectivity decision | Result of applying topology and port rules |

A container being attached to a network does not automatically mean an application is reachable. The target must also have a listening service on the requested port.

This distinction appears in all implementations.

---

## Python Implementation

The Python file uses dataclasses and enums to create a compact network model.

`Network` owns:

- subnet information
- gateway information
- endpoint allocation

`Container` owns:

- network mode
- network attachments
- exposed ports
- published ports
- shared namespace information

`DockerNetworkSimulator` coordinates the objects.

The simulator allocates addresses from an IPv4 network, rejects duplicate addresses, prevents gateway reuse, validates ports, and evaluates whether two containers have a common network.

The connectivity calculation checks:

- whether both containers exist
- whether the requested port is valid
- whether host or container namespace rules apply
- whether bridge-mode containers share a network
- whether the target listens on the requested port

This avoids treating IP reachability and application availability as the same thing.

The Python implementation also models host port publishing separately from direct bridge connectivity. Publishing TCP port `8080` on `web` creates a host-to-container mapping. It does not change the container's private IP address.

The script uses only the Python standard library and can be executed directly with Python 3.

---

## JavaScript Implementation

The JavaScript implementation uses Node.js `EventEmitter` to represent changes in network state as events.

Important events include:

- container startup
- network attachment

The event-driven design is useful for network automation because infrastructure systems often react to state changes rather than continuously executing a linear sequence.

The `DockerNetworkController` uses private class fields for internal state:

- `#networks`
- `#containers`
- `#publishedPorts`

Maps are used for fast name-based lookup and endpoint ownership.

The implementation also provides asynchronous connectivity evaluation with `setImmediate`. This models a service boundary where policy evaluation could be performed asynchronously without introducing an external dependency.

The JavaScript version performs validation before modifying state. For example, port publication is rejected when:

- the container is using host networking
- the host port is already occupied
- the container does not expose the requested destination port

The program is designed for Node.js and uses only built-in modules.

---

## C++ Implementation

The C++ program emphasizes explicit domain types and deterministic data structures.

`IPv4` represents an IPv4 address as a 32-bit value. It provides parsing, formatting, comparison, and subnet membership support.

`IPv4Network` represents:

- network address
- prefix length
- address count
- membership validation

The governance engine stores networks and containers in ordered maps. This provides deterministic output while maintaining straightforward lookup semantics.

`Port` combines protocol and port number into a value object. The type participates in ordered sets, allowing duplicate listener definitions to be rejected naturally.

The C++ design treats connectivity as a decision rather than returning a raw boolean:

- `allowed`
- `reason`

This is important for diagnostics. A denied connection can be denied because the containers have no shared network, because the port is closed, or because host-mode rules apply.

The implementation also demonstrates namespace sharing through `startContainerNamespace`.

The program can be compiled with a C++17 compiler. It requires no external library.

---

## Java Implementation

The Java implementation uses explicit domain modeling appropriate for an enterprise networking service.

The principal domain types are:

- `NetworkMode`
- `Protocol`
- `Port`
- `NetworkAddress`
- `ConnectivityDecision`
- `Network`
- `Container`

The `RepositoryGovernance` class acts as the service layer for topology changes and connectivity evaluation.

Immutable Java records are used where a value should represent data rather than mutable lifecycle state. `Port`, `NetworkAddress`, and `ConnectivityDecision` are examples.

The `Container` entity owns state transitions such as:

- attaching to a network
- opening a listening port
- publishing a port

The service layer enforces higher-level rules such as:

- host-mode containers cannot use bridge-style port publishing
- only bridge containers can be dynamically attached to networks
- a published port must correspond to a listening container port
- duplicate host-port mappings are rejected
- a container namespace cannot be shared with itself

The model also represents multi-network containers. The API container is connected to both frontend and backend networks, while the database is connected only to backend.

A generic `ReviewPolicy` interface is included as a reusable policy abstraction for enterprise-style rule evaluation, while the concrete `MergePolicy` record demonstrates immutable policy configuration. The network service remains focused on networking rather than introducing unrelated application behavior.

---

## PostgreSQL Data Model

The SQL implementation treats Docker networking as persistent relational state.

The main relationships are:

```text
docker_network
      |
      | 1-to-many
      v
container_network
      ^
      |
      | many-to-1
container
      |
      +------> container_port
      |
      +------> published_port
```

`docker_network` stores the network-level configuration.

`container` stores network mode and namespace-sharing information.

`container_network` represents the many-to-many relationship between bridge networks and containers while also storing each endpoint IP.

`container_port` represents listening application ports.

`published_port` represents host-to-container port mappings.

This separation prevents a private container IP from being confused with a published host port.

---

## Database Constraints and Validation

The SQL model uses PostgreSQL constraints for rules that should always be true.

Network modes are restricted by `CHECK` constraints.

Container-mode records must reference a shared container.

Ports must remain between `1` and `65535`.

Protocol values are restricted to TCP and UDP.

Network endpoints use a unique constraint on `(network_id, ip_address)`, preventing two containers from claiming the same address on one network.

The endpoint trigger validates that the address belongs to the configured subnet and is not the gateway.

The publication trigger verifies that the destination container is actually listening on the requested protocol and port.

These checks move important correctness rules into the database rather than relying exclusively on application code.

---

## Connectivity Function

The PostgreSQL `connectivity` function evaluates a source container, target container, protocol, and target port.

It distinguishes several outcomes:

- unknown containers
- self-connectivity
- host-network destinations
- host-to-bridge access
- containers with no shared network
- shared network with a closed target port
- successful bridge connectivity

The function returns both a boolean decision and a diagnostic reason.

For example, a web container can reach the API because both share `frontend`. The web container cannot directly reach the database because the web container is not attached to `backend`.

The API can reach the database because API has a backend endpoint and database is also attached to backend.

---

## Port Publishing

A bridge container can expose an internal port and publish it on the host.

The conceptual mapping is:

```text
Host TCP/8080
      |
      v
published_port
      |
      v
Container TCP/8080
      |
      v
web service
```

The private bridge IP remains separate from the host port.

The database example intentionally demonstrates an invalid publication attempt. The trigger rejects the operation because the database does not listen on the requested destination port.

This illustrates an important distinction:

**Exposing or listening on a container port is not the same as publishing that port to the host.**

A service may be reachable by other containers on the same network without being published to the host.

---

## Network Isolation

Network membership provides an important isolation boundary.

In the sample topology:

```text
frontend network
    |
    +-- web
    |
    +-- api

backend network
    |
    +-- api
    |
    +-- database
```

The API is intentionally multi-homed.

The web service can reach the API through the frontend network.

The API can reach the database through the backend network.

The web service cannot reach the database through the modeled direct bridge path because it has no backend endpoint.

This is a common architectural pattern for separating public-facing services from internal data services.

Network isolation is not equivalent to a complete security policy. Real Docker deployments can also involve firewall rules, iptables/nftables behavior, DNS configuration, routing, service binding, TLS, application authentication, and host-level security controls.

---

## DNS and Service Discovery

The simulations use container names as logical identifiers and resolve a target only when the source and target have a shared modeled network.

The important rule is:

```text
shared network
      +
target endpoint
      =
possible network-level discovery
```

A name alone does not establish connectivity.

A container on `frontend` should not be able to resolve or directly access an isolated backend-only service merely because both containers exist in the same Docker host.

Real Docker environments provide DNS behavior that depends on the network configuration. The implementations intentionally model the core relationship rather than attempting to reproduce every detail of Docker's embedded DNS implementation.

---

## Bridge Networking Trade-offs

Bridge networking provides strong practical isolation while retaining straightforward container-to-container communication.

Advantages include:

- separate network namespace
- private IP addressing
- multiple independent networks
- service-level isolation
- explicit host port publication

Costs include:

- additional network configuration
- virtual networking overhead
- address management
- possible routing and firewall complexity
- more interfaces when containers are multi-homed

Bridge networks are usually appropriate when services need controlled communication without sharing the host network namespace.

---

## Host Networking Trade-offs

Host mode reduces network abstraction because the workload uses the host namespace.

This can be useful for applications that need direct access to host networking behavior or where avoiding an additional network namespace is desirable.

The cost is reduced isolation.

Port conflicts become a host-level concern because two workloads cannot independently bind the same host address and port combination.

The host-mode example therefore does not use a Docker-style `host_port:container_port` mapping.

---

## Container Namespace Sharing Trade-offs

Container mode is useful when tightly coupled containers need to observe and use the same network namespace.

The benefit is that network identity is shared.

The cost is that the containers are no longer independently isolated at the network namespace level.

This can simplify tightly coupled sidecar-style designs but creates stronger coupling between the participating containers.

The `api-worker` example demonstrates this distinction by copying the API network identity rather than creating a separate endpoint.

---

## Edge Cases Covered

The implementations explicitly handle several failure conditions:

- duplicate network names
- duplicate container names
- invalid IPv4 addresses
- invalid subnet prefixes
- gateway reuse
- IP address collisions
- exhausted network address space
- invalid ports
- duplicate host-port publication
- publishing an unlistened container port
- dynamic attachment of non-bridge containers
- nonexistent networks
- nonexistent containers
- namespace sharing with a nonexistent container
- self-connectivity
- connectivity without a shared bridge network
- closed target ports

The SQL version adds database-level protection so invalid state is rejected even if an application attempts to bypass normal workflow logic.

---

## Performance Considerations

Network topology lookup is primarily map-based in the Python, JavaScript, C++, and Java implementations.

Container and network names therefore provide efficient direct lookup.

The SQL implementation indexes:

- network membership by network
- listening ports by container, protocol, and port
- published ports by protocol and host port

The partial index on listening ports avoids indexing inactive service definitions when they are not relevant to connectivity evaluation.

For a large infrastructure inventory, additional indexing could be justified for workload-specific queries, but indexes should follow actual query patterns rather than being added indiscriminately.

IP allocation in the simulations scans candidate addresses. This is appropriate for a learning-scale model but would need a more sophisticated allocation strategy for very large or highly concurrent systems.

---

## Security Considerations

Network separation should not be treated as application authentication.

A container being unreachable through one bridge network does not replace:

- TLS
- application authentication
- authorization
- credential management
- host firewall controls
- least-privilege container configuration
- image and dependency security
- secrets management

Host networking deserves particular care because it reduces network namespace isolation.

Published ports should also be treated as externally reachable interfaces unless host firewall and application-level controls restrict them.

The SQL model prevents structurally invalid endpoint and publication state, but database integrity alone does not provide network security.

---

## Failure Diagnosis

A useful debugging sequence is to separate topology from application behavior.

```text
Is the container running?
        |
        v
Is the container attached to the expected network?
        |
        v
Does the target have an endpoint on that network?
        |
        v
Is the target service listening on the requested port?
        |
        v
Is a host publication actually required?
        |
        v
Are firewall, routing, DNS, or application policies blocking traffic?
```

This prevents common mistakes such as assuming that a published host port is necessary for container-to-container communication.

For bridge networking, containers on the same network can use their internal network identity without publishing the service to the host.

---

## Implementation Mapping

| Concern | Python | JavaScript | C++17 | Java 17 | PostgreSQL |
|---|---|---|---|---|---|
| Network model | Dataclass | Object/Map | Struct/class | Domain class | Table |
| Container model | Dataclass | Object | Struct | Domain class | Table |
| Network modes | Enum | Frozen object | Enum class | Enum | Check constraint |
| Endpoint allocation | IPv4/network iteration | Address calculation | 32-bit IPv4 | Explicit endpoint records | `cidr`/`inet` |
| Connectivity | Simulator method | Controller method | Governance engine | Service method | Stored function |
| Validation | Exceptions | Custom error | Exceptions | Exceptions | Constraints/triggers |
| Event behavior | Direct workflow | `EventEmitter` | Deterministic engine | Service operations | Triggers |
| Port publication | Dictionary mapping | Map | Map | Map | Relational mapping |
| Persistence | In-memory | In-memory | In-memory | In-memory | PostgreSQL |
| Transactions | Not applicable | Not applicable | Not applicable | Not applicable | `BEGIN`/`COMMIT` |

---

## Practical Distinctions

The project intentionally keeps the three modes separate.

**Bridge mode** answers:

> Which isolated network endpoint does this container have?

**Host mode** answers:

> Which services are available through the host network namespace?

**Container mode** answers:

> Which existing container's network namespace does this workload share?

These are namespace decisions, not merely three different ways of assigning an IP address.

Likewise, the following concepts remain distinct:

**Container port**

A port on which an application inside the container namespace listens.

**Published port**

A host-facing mapping to a container port.

**Bridge network**

A logical connectivity domain joining independent container namespaces.

**Host network**

The host's network namespace used directly by a workload.

**Container network mode**

A shared namespace relationship with another container.

Understanding these distinctions is essential when diagnosing connectivity, designing service boundaries, and deciding whether a service should be reachable only inside Docker networking or from the host and external clients.
````
