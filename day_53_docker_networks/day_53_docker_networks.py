#!/usr/bin/env python3
"""
Docker Network Simulator
Models Docker bridge, host, and container-style networking behavior
without requiring Docker or third-party Python packages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from ipaddress import IPv4Address, IPv4Network
from typing import Dict, List, Optional, Set, Tuple


class NetworkMode(str, Enum):
    BRIDGE = "bridge"
    HOST = "host"
    CONTAINER = "container"


class Protocol(str, Enum):
    TCP = "tcp"
    UDP = "udp"


@dataclass(frozen=True)
class Endpoint:
    container: str
    ip: str
    port: int
    protocol: Protocol = Protocol.TCP

    def __post_init__(self) -> None:
        IPv4Address(self.ip)
        if not 1 <= self.port <= 65535:
            raise ValueError("Port must be between 1 and 65535.")


@dataclass
class Network:
    name: str
    subnet: IPv4Network
    gateway: str
    driver: str = "bridge"
    endpoints: Dict[str, str] = field(default_factory=dict)

    def connect(self, container_name: str, ip: Optional[str] = None) -> str:
        if container_name in self.endpoints:
            return self.endpoints[container_name]

        address = IPv4Address(ip) if ip else self._allocate_ip()
        if address not in self.subnet or str(address) == self.gateway:
            raise ValueError(f"{address} is not usable on network {self.name}.")
        if str(address) in self.endpoints.values():
            raise ValueError(f"IP address {address} is already allocated.")

        self.endpoints[container_name] = str(address)
        return str(address)

    def _allocate_ip(self) -> IPv4Address:
        used = {IPv4Address(value) for value in self.endpoints.values()}
        for address in self.subnet.hosts():
            if str(address) != self.gateway and address not in used:
                return address
        raise RuntimeError(f"Network {self.name} has no available addresses.")


@dataclass
class Container:
    name: str
    network_mode: NetworkMode = NetworkMode.BRIDGE
    networks: Dict[str, str] = field(default_factory=dict)
    exposed_ports: Set[Tuple[Protocol, int]] = field(default_factory=set)
    published_ports: Dict[int, int] = field(default_factory=dict)
    shared_network_namespace: Optional[str] = None

    def expose(self, port: int, protocol: Protocol = Protocol.TCP) -> None:
        if not 1 <= port <= 65535:
            raise ValueError("Invalid container port.")
        self.exposed_ports.add((protocol, port))


class DockerNetworkSimulator:
    """
    A simplified model of Docker networking.

    Bridge:
        Containers receive private IP addresses and communicate through
        a virtual bridge. Published ports represent host-to-container NAT.

    Host:
        The container shares the host network namespace. There is no
        container-specific bridge IP.

    Container:
        The container shares another container's network namespace and
        therefore uses the same network identity.
    """

    def __init__(self) -> None:
        self.networks: Dict[str, Network] = {}
        self.containers: Dict[str, Container] = {}
        self.host_ports: Dict[int, Tuple[str, int]] = {}

    def create_bridge(
        self,
        name: str,
        subnet: str,
        gateway: Optional[str] = None,
    ) -> Network:
        if name in self.networks:
            raise ValueError(f"Network {name!r} already exists.")

        network = IPv4Network(subnet, strict=False)
        if network.prefixlen >= 31:
            raise ValueError("Network must provide usable host addresses.")

        selected_gateway = gateway or str(next(network.hosts()))
        IPv4Address(selected_gateway)

        if IPv4Address(selected_gateway) not in network:
            raise ValueError("Gateway must belong to the network.")

        result = Network(
            name=name,
            subnet=network,
            gateway=selected_gateway,
        )
        self.networks[name] = result
        return result

    def run_container(
        self,
        name: str,
        network_mode: NetworkMode = NetworkMode.BRIDGE,
        network: Optional[str] = None,
        ip: Optional[str] = None,
        shared_with: Optional[str] = None,
    ) -> Container:
        if name in self.containers:
            raise ValueError(f"Container {name!r} already exists.")

        if network_mode == NetworkMode.BRIDGE:
            if not network:
                network = "bridge"
            if network not in self.networks:
                raise ValueError(f"Unknown bridge network {network!r}.")

        if network_mode == NetworkMode.CONTAINER:
            if not shared_with or shared_with not in self.containers:
                raise ValueError("Container mode requires an existing container.")
            source = self.containers[shared_with]
            container = Container(
                name=name,
                network_mode=NetworkMode.CONTAINER,
                networks=source.networks.copy(),
                shared_network_namespace=shared_with,
            )
            self.containers[name] = container
            return container

        container = Container(name=name, network_mode=network_mode)

        if network_mode == NetworkMode.BRIDGE:
            assert network is not None
            assigned_ip = self.networks[network].connect(name, ip)
            container.networks[network] = assigned_ip

        self.containers[name] = container
        return container

    def connect(self, container_name: str, network_name: str, ip: Optional[str] = None) -> str:
        container = self._container(container_name)
        network = self._network(network_name)

        if container.network_mode != NetworkMode.BRIDGE:
            raise ValueError("Only bridge-mode containers can be dynamically connected.")

        assigned = network.connect(container.name, ip)
        container.networks[network.name] = assigned
        return assigned

    def publish_port(self, container_name: str, host_port: int, container_port: int) -> None:
        container = self._container(container_name)

        if container.network_mode == NetworkMode.HOST:
            raise ValueError("Host-mode containers do not use Docker-style port publishing.")

        if host_port in self.host_ports:
            raise ValueError(f"Host port {host_port} is already published.")

        if not 1 <= host_port <= 65535 or not 1 <= container_port <= 65535:
            raise ValueError("Ports must be between 1 and 65535.")

        if (Protocol.TCP, container_port) not in container.exposed_ports:
            raise ValueError(
                f"Container {container_name} does not expose TCP/{container_port}."
            )

        container.published_ports[host_port] = container_port
        self.host_ports[host_port] = (container_name, container_port)

    def resolve(self, source: str, target: str) -> Optional[str]:
        """
        Resolve a target from a container perspective.

        Bridge networks use Docker-style service/container-name discovery
        only when both containers share a network.
        """
        src = self._container(source)
        dst = self._container(target)

        if src.network_mode == NetworkMode.CONTAINER:
            return self.resolve(src.shared_network_namespace or source, target)

        if dst.network_mode == NetworkMode.HOST:
            return "host"

        common = set(src.networks) & set(dst.networks)
        if common:
            network_name = sorted(common)[0]
            return dst.networks[network_name]

        return None

    def can_connect(
        self,
        source: str,
        target: str,
        target_port: int,
        protocol: Protocol = Protocol.TCP,
    ) -> Tuple[bool, str]:
        src = self._container(source)
        dst = self._container(target)

        if src.name == dst.name:
            return False, "A container cannot use this simulation as an external peer."

        if not 1 <= target_port <= 65535:
            return False, "Invalid target port."

        if dst.network_mode == NetworkMode.HOST:
            if (protocol, target_port) in dst.exposed_ports:
                return True, "Traffic reaches the host network namespace."

        if src.network_mode == NetworkMode.HOST:
            if dst.network_mode == NetworkMode.BRIDGE:
                if (protocol, target_port) in dst.exposed_ports:
                    return True, "Host-mode traffic can route to the bridge container."
            return False, "Target is not reachable through the modeled host path."

        common_networks = set(src.networks) & set(dst.networks)
        if not common_networks:
            return False, "Containers do not share a network."

        if (protocol, target_port) not in dst.exposed_ports:
            return False, "Target port is not listening/exposed."

        return True, f"Reachable through bridge network {sorted(common_networks)[0]}."

    def connect_to_host_published_port(
        self,
        source: str,
        host_port: int,
    ) -> Tuple[bool, str]:
        self._container(source)

        if host_port not in self.host_ports:
            return False, f"Host port {host_port} is not published."

        target, container_port = self.host_ports[host_port]
        return True, (
            f"Host NAT maps TCP/{host_port} to "
            f"{target}:TCP/{container_port}."
        )

    def inspect_container(self, name: str) -> dict:
        container = self._container(name)
        return {
            "name": container.name,
            "network_mode": container.network_mode.value,
            "networks": dict(container.networks),
            "exposed_ports": [
                f"{protocol.value}/{port}"
                for protocol, port in sorted(
                    container.exposed_ports,
                    key=lambda item: (item[0].value, item[1]),
                )
            ],
            "published_ports": dict(container.published_ports),
            "shared_network_namespace": container.shared_network_namespace,
        }

    def inspect_network(self, name: str) -> dict:
        network = self._network(name)
        return {
            "name": network.name,
            "driver": network.driver,
            "subnet": str(network.subnet),
            "gateway": network.gateway,
            "endpoints": dict(network.endpoints),
        }

    def _container(self, name: str) -> Container:
        if name not in self.containers:
            raise KeyError(f"Unknown container {name!r}.")
        return self.containers[name]

    def _network(self, name: str) -> Network:
        if name not in self.networks:
            raise KeyError(f"Unknown network {name!r}.")
        return self.networks[name]


def main() -> None:
    simulator = DockerNetworkSimulator()

    simulator.create_bridge("bridge", "172.20.0.0/24", "172.20.0.1")
    simulator.create_bridge("frontend_net", "172.21.0.0/24", "172.21.0.1")
    simulator.create_bridge("backend_net", "172.22.0.0/24", "172.22.0.1")

    web = simulator.run_container(
        "web",
        NetworkMode.BRIDGE,
        network="frontend_net",
        ip="172.21.0.10",
    )
    api = simulator.run_container(
        "api",
        NetworkMode.BRIDGE,
        network="backend_net",
        ip="172.22.0.10",
    )
    simulator.connect("api", "frontend_net", "172.21.0.20")

    db = simulator.run_container(
        "database",
        NetworkMode.BRIDGE,
        network="backend_net",
        ip="172.22.0.30",
    )
    proxy = simulator.run_container("host-proxy", NetworkMode.HOST)
    worker = simulator.run_container(
        "worker",
        NetworkMode.CONTAINER,
        shared_with="api",
    )

    web.expose(8080)
    api.expose(8080)
    db.expose(5432)
    proxy.expose(9000)

    simulator.publish_port("web", 8080, 8080)

    print("=== Network Inspection ===")
    for name in ("frontend_net", "backend_net"):
        print(simulator.inspect_network(name))

    print("\n=== Container Inspection ===")
    for name in ("web", "api", "database", "worker", "host-proxy"):
        print(simulator.inspect_container(name))

    print("\n=== Connectivity ===")
    tests = [
        ("web", "api", 8080),
        ("api", "database", 5432),
        ("web", "database", 5432),
        ("worker", "database", 5432),
    ]

    for source, target, port in tests:
        allowed, reason = simulator.can_connect(source, target, port)
        print(f"{source} -> {target}:{port}: {allowed} ({reason})")

    print("\n=== Host Port Publishing ===")
    allowed, reason = simulator.connect_to_host_published_port("api", 8080)
    print(f"api -> host:8080: {allowed} ({reason})")

    print("\n=== DNS-Style Container Resolution ===")
    print("web -> api:", simulator.resolve("web", "api"))
    print("web -> database:", simulator.resolve("web", "database"))

    print("\n=== Host Network ===")
    allowed, reason = simulator.can_connect("web", "host-proxy", 9000)
    print(f"web -> host-proxy:9000: {allowed} ({reason})")

    print("\n=== Failure Validation ===")
    try:
        simulator.publish_port("database", 8080, 8080)
    except ValueError as exc:
        print("Rejected invalid publication:", exc)

    try:
        simulator.create_bridge("bad_net", "172.21.0.0/24")
    except ValueError as exc:
        print("Rejected duplicate network:", exc)


if __name__ == "__main__":
    main()
