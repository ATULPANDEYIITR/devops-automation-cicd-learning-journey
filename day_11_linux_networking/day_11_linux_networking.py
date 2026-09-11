"""
Linux Networking Study Script
=============================

Topic:
    Linux Networking | IP, ports, interfaces, hostname, DNS basics

Purpose:
    A self-contained educational script covering Linux networking fundamentals
    through advanced practical concepts. The demonstrations use Python's
    standard library where possible and can be run on Linux, with several
    sections also working on Windows and macOS.

Important:
    Some demonstrations inspect the local machine's networking configuration.
    They do not modify network settings.
"""

from __future__ import annotations

import errno
import ipaddress
import os
import platform
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional


# ============================================================================
# 1. BASIC OUTPUT HELPERS
# ============================================================================

def section(title: str) -> None:
    """Print a clear section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    """Print a smaller heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain(message: str) -> None:
    """Print educational text."""
    print(message)


def safe_call(function, *args, **kwargs):
    """Run a demonstration without allowing one failure to stop the script."""
    try:
        return function(*args, **kwargs)
    except Exception as error:
        print(f"[Demonstration error] {type(error).__name__}: {error}")
        return None


# ============================================================================
# 2. NETWORKING FUNDAMENTALS
# ============================================================================

def demonstrate_networking_fundamentals() -> None:
    section("1. Networking fundamentals")

    explain(
        """
A computer network allows devices to exchange data.

Important terms:

    Host
        A device participating in a network.

    IP address
        A logical network address assigned to an interface.

    Interface
        A network connection through which a host sends or receives traffic.
        Examples include Ethernet, Wi-Fi, loopback, and virtual interfaces.

    Port
        A number used by transport-layer protocols such as TCP and UDP to
        identify an application endpoint.

    Protocol
        A defined set of communication rules.

    TCP
        Connection-oriented transport protocol that provides reliable,
        ordered byte-stream delivery.

    UDP
        Connectionless transport protocol that provides datagrams without
        TCP's delivery guarantees.

    Hostname
        A human-readable name assigned to a host.

    DNS
        Domain Name System. It maps names such as example.com to records
        such as IPv4 and IPv6 addresses.

A useful mental model is:

    interface -> IP address -> transport port -> application

For example:

    eth0 -> 192.168.1.20 -> TCP port 22 -> SSH server

The interface is the network attachment, the IP identifies the host on that
network, and the port identifies the service endpoint.
"""
    )


# ============================================================================
# 3. IP ADDRESS FUNDAMENTALS
# ============================================================================

def demonstrate_ip_addresses() -> None:
    section("2. IP addresses")

    subsection("IPv4")

    ipv4_examples = [
        "127.0.0.1",
        "192.168.1.10",
        "10.0.0.5",
        "172.16.20.30",
        "8.8.8.8",
    ]

    for address_text in ipv4_examples:
        address = ipaddress.ip_address(address_text)
        print(
            f"{address_text:15} "
            f"version={address.version} "
            f"private={address.is_private} "
            f"loopback={address.is_loopback} "
            f"global={address.is_global}"
        )

    subsection("IPv6")

    ipv6_examples = [
        "::1",
        "fe80::1",
        "2001:db8::1",
    ]

    for address_text in ipv6_examples:
        address = ipaddress.ip_address(address_text)
        print(
            f"{address_text:20} "
            f"version={address.version} "
            f"private={address.is_private} "
            f"loopback={address.is_loopback} "
            f"link_local={address.is_link_local}"
        )

    subsection("IPv4 and IPv6 comparison")

    comparison = {
        "IPv4": "32-bit address space, traditionally written as four decimal octets",
        "IPv6": "128-bit address space, written using hexadecimal groups",
        "IPv4 example": "192.168.1.20",
        "IPv6 example": "2001:db8::20",
        "IPv4 loopback": "127.0.0.1",
        "IPv6 loopback": "::1",
    }

    for key, value in comparison.items():
        print(f"{key:18}: {value}")


# ============================================================================
# 4. SUBNETS AND CIDR
# ============================================================================

def demonstrate_subnets() -> None:
    section("3. Subnets and CIDR")

    explain(
        """
CIDR notation combines an IP network address with a prefix length.

Example:

    192.168.1.0/24

The /24 means that 24 bits identify the network portion.

For IPv4:

    /8   = 255.0.0.0
    /16  = 255.255.0.0
    /24  = 255.255.255.0
    /32  = one IPv4 address

The number of addresses in an IPv4 network is:

    2 ** (32 - prefix_length)

For a normal /24 network:

    2 ** 8 = 256 total addresses

Traditional subnetting often reserves the network and broadcast addresses,
leaving 254 conventional host addresses. Modern networking can use different
rules depending on the address type and environment.
"""
    )

    networks = [
        "192.168.1.0/24",
        "10.0.0.0/8",
        "172.16.0.0/16",
        "2001:db8::/64",
    ]

    for network_text in networks:
        network = ipaddress.ip_network(network_text, strict=False)

        print(f"\nNetwork: {network}")
        print(f"  version:       IPv{network.version}")
        print(f"  prefix length: {network.prefixlen}")
        print(f"  netmask:       {network.netmask}")
        print(f"  network:       {network.network_address}")
        print(f"  broadcast:     {network.broadcast_address}")

        if network.version == 4:
            print(f"  total addresses: {network.num_addresses}")

        sample_addresses = list(network.hosts())[:3]
        if sample_addresses:
            print(f"  sample hosts: {sample_addresses}")


# ============================================================================
# 5. IP ADDRESS CLASSIFICATION
# ============================================================================

def demonstrate_ip_classification() -> None:
    section("4. Important IP address classifications")

    addresses = [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.10.20",
        "224.0.0.1",
        "255.255.255.255",
        "8.8.8.8",
        "192.0.2.10",
        "::1",
        "fe80::1",
        "2001:db8::1",
    ]

    for address_text in addresses:
        address = ipaddress.ip_address(address_text)

        print(f"\n{address_text}")
        print(f"  private:       {address.is_private}")
        print(f"  global:        {address.is_global}")
        print(f"  loopback:      {address.is_loopback}")
        print(f"  link-local:    {address.is_link_local}")
        print(f"  multicast:     {address.is_multicast}")
        print(f"  reserved:      {address.is_reserved}")

    explain(
        """
Common special IPv4 ranges:

    127.0.0.0/8
        Loopback.

    10.0.0.0/8
        Private addressing.

    172.16.0.0/12
        Private addressing.

    192.168.0.0/16
        Private addressing.

    169.254.0.0/16
        IPv4 link-local addressing.

Private addresses are normally used inside local networks and are not
globally routable on the public Internet.

NAT is commonly used to allow private-addressed hosts to communicate with
external networks through a public address.
"""
    )


# ============================================================================
# 6. IP ADDRESS OPERATIONS
# ============================================================================

def demonstrate_ipaddress_operations() -> None:
    section("5. Practical IP address operations")

    network = ipaddress.ip_network("192.168.50.0/24")

    test_addresses = [
        "192.168.50.1",
        "192.168.50.100",
        "192.168.51.1",
    ]

    print(f"Network: {network}")

    for address_text in test_addresses:
        address = ipaddress.ip_address(address_text)
        print(f"{address} belongs to network: {address in network}")

    subsection("Subnetting")

    parent_network = ipaddress.ip_network("192.168.100.0/24")
    subnets = list(parent_network.subnets(new_prefix=26))

    print(f"Parent network: {parent_network}")
    print("Subnets:")

    for subnet in subnets:
        print(f"  {subnet}")

    subsection("Supernetting")

    small_network = ipaddress.ip_network("192.168.100.0/24")
    print(f"Small network: {small_network}")
    print(f"Supernet:      {small_network.supernet(new_prefix=22)}")

    subsection("Address arithmetic")

    address = ipaddress.ip_address("192.168.1.10")

    print(f"Original: {address}")
    print(f"+ 1:      {address + 1}")
    print(f"- 1:      {address - 1}")

    subsection("Invalid address handling")

    invalid_values = [
        "192.168.1.999",
        "hello",
        "300.1.1.1",
    ]

    for value in invalid_values:
        try:
            ipaddress.ip_address(value)
        except ValueError as error:
            print(f"{value!r} -> invalid IP: {error}")


# ============================================================================
# 7. NETWORK INTERFACES
# ============================================================================

def get_linux_interfaces() -> list[str]:
    """Read interface names from Linux sysfs without requiring external tools."""
    interfaces_path = "/sys/class/net"

    if not os.path.isdir(interfaces_path):
        return []

    try:
        return sorted(os.listdir(interfaces_path))
    except OSError:
        return []


def demonstrate_interfaces() -> None:
    section("6. Network interfaces")

    explain(
        """
A network interface is the operating system's representation of a network
connection.

Common Linux interfaces include:

    lo
        Loopback interface.

    eth0
        A common Ethernet naming example.

    wlan0
        A traditional Wi-Fi naming example.

Modern Linux distributions may use predictable names such as:

    enp3s0
    ens33
    wlp2s0

Virtual machines, containers, VPNs, bridges, and other technologies can
create additional interfaces.
"""
    )

    interfaces = get_linux_interfaces()

    if interfaces:
        print("Interfaces discovered through /sys/class/net:")
        for interface in interfaces:
            print(f"  {interface}")
    else:
        print("Linux interface directory is not available on this system.")

    subsection("Interface state")

    if platform.system() == "Linux":
        for interface in interfaces:
            state_path = f"/sys/class/net/{interface}/operstate"

            try:
                with open(state_path, "r", encoding="utf-8") as file:
                    state = file.read().strip()
                print(f"{interface:15} state={state}")
            except OSError:
                print(f"{interface:15} state=unavailable")


# ============================================================================
# 8. SOCKET INTERFACE INFORMATION
# ============================================================================

def demonstrate_local_addresses() -> None:
    section("7. Local address information")

    hostname = socket.gethostname()

    print(f"Hostname: {hostname}")

    try:
        fully_qualified_name = socket.getfqdn()
        print(f"FQDN:     {fully_qualified_name}")
    except socket.error as error:
        print(f"FQDN lookup failed: {error}")

    try:
        addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )

        unique_addresses = sorted(
            {
                result[4][0]
                for result in addresses
                if result[4]
            }
        )

        print("Addresses associated with hostname:")
        for address in unique_addresses:
            print(f"  {address}")

    except socket.gaierror as error:
        print(f"Address lookup failed: {error}")


# ============================================================================
# 9. HOSTNAME
# ============================================================================

def demonstrate_hostname() -> None:
    section("8. Hostnames")

    hostname = socket.gethostname()

    print(f"Current hostname: {hostname}")
    print(f"Fully qualified hostname: {socket.getfqdn()}")

    explain(
        """
Linux hostname commands commonly include:

    hostname
        Display the current hostname.

    hostnamectl
        Display or manage system hostname information on systems using
        systemd.

A hostname is not the same thing as an IP address.

Example:

    server01.example.com
        |
        DNS
        |
    192.0.2.25

The DNS mapping can change without changing the conceptual name of the
service.

A hostname can also resolve to multiple addresses, and a single IP address
can have multiple names associated with it.
"""
    )


# ============================================================================
# 10. DNS BASICS
# ============================================================================

def demonstrate_dns_basics() -> None:
    section("9. DNS basics")

    explain(
        """
DNS is a distributed naming system.

Common DNS record types:

    A
        Maps a hostname to an IPv4 address.

    AAAA
        Maps a hostname to an IPv6 address.

    CNAME
        Creates an alias to another domain name.

    MX
        Identifies mail servers for a domain.

    NS
        Identifies authoritative name servers.

    TXT
        Stores text data, commonly used for verification and email-security
        mechanisms.

DNS resolution is conceptually:

    Application
        |
    Resolver
        |
    DNS server
        |
    DNS hierarchy
        |
    Authoritative server
        |
    DNS response

Linux systems can obtain resolver configuration from mechanisms such as
/etc/resolv.conf and systemd-resolved, depending on distribution and setup.
"""
    )

    domains = [
        "localhost",
        "example.com",
    ]

    for domain in domains:
        subsection(f"Resolving {domain}")

        try:
            results = socket.getaddrinfo(
                domain,
                None,
                type=socket.SOCK_STREAM,
            )

            unique_results = sorted(
                {
                    (result[0], result[4][0])
                    for result in results
                    if result[4]
                }
            )

            for family, address in unique_results:
                family_name = (
                    "IPv4"
                    if family == socket.AF_INET
                    else "IPv6"
                    if family == socket.AF_INET6
                    else str(family)
                )
                print(f"  {family_name:5} {address}")

        except socket.gaierror as error:
            print(f"  DNS resolution failed: {error}")


# ============================================================================
# 11. FORWARD AND REVERSE DNS
# ============================================================================

def demonstrate_forward_reverse_dns() -> None:
    section("10. Forward and reverse DNS")

    hostname = "example.com"

    try:
        forward_results = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )

        addresses = sorted(
            {
                result[4][0]
                for result in forward_results
                if result[4]
            }
        )

        print(f"Forward lookup: {hostname}")

        for address in addresses:
            print(f"  {address}")

            try:
                reverse_name = socket.gethostbyaddr(address)
                print(f"  Reverse lookup: {reverse_name[0]}")
            except socket.herror as error:
                print(f"  Reverse lookup unavailable: {error}")

    except socket.gaierror as error:
        print(f"Forward lookup failed: {error}")

    explain(
        """
Forward DNS:

    name -> address

Reverse DNS:

    address -> name

Reverse DNS is commonly associated with PTR records.

Forward and reverse DNS do not have to be symmetrical. An IP address can
resolve to a name that does not point back to the same address.
"""
    )


# ============================================================================
# 12. DNS CACHE CONCEPTS
# ============================================================================

def demonstrate_dns_cache_concepts() -> None:
    section("11. DNS caching and TTL")

    explain(
        """
DNS responses commonly have a TTL, meaning Time To Live.

A resolver can cache a DNS response for the duration permitted by the
record's TTL.

Example conceptual flow:

    Client asks for example.com
             |
             v
    Local cache
       /       \
    hit        miss
     |           |
   answer    DNS query

Caching improves performance and reduces repeated DNS traffic.

A DNS cache can also introduce a practical complication: when a DNS record
changes, different clients may continue using older cached information until
the relevant TTL expires.

DNS caching may occur at several layers:

    application
    operating system
    local resolver
    recursive DNS server
    network infrastructure
"""
    )


# ============================================================================
# 13. /etc/HOSTS CONCEPT
# ============================================================================

def demonstrate_hosts_file() -> None:
    section("12. The hosts file")

    hosts_path = "/etc/hosts"

    if os.path.exists(hosts_path):
        print(f"Reading {hosts_path}:")

        try:
            with open(hosts_path, "r", encoding="utf-8", errors="replace") as file:
                lines = file.readlines()

            for line in lines[:20]:
                print("  " + line.rstrip())

            if len(lines) > 20:
                print("  ...")

        except PermissionError:
            print("Permission denied while reading the hosts file.")
        except OSError as error:
            print(f"Could not read hosts file: {error}")
    else:
        print(f"{hosts_path} does not exist on this system.")

    explain(
        """
The hosts file provides local static hostname mappings.

Typical syntax:

    IP_ADDRESS hostname alias

For example:

    127.0.0.1 localhost

The hosts file is checked by the system's name-resolution mechanism according
to the configured name-service policy.

It can be useful for local development, testing, and controlled overrides.

Do not modify system networking files casually on production systems.
"""
    )


# ============================================================================
# 14. PORTS
# ============================================================================

COMMON_PORTS = {
    20: "FTP data",
    21: "FTP control",
    22: "SSH",
    23: "Telnet",
    25: "SMTP",
    53: "DNS",
    67: "DHCP server",
    68: "DHCP client",
    80: "HTTP",
    110: "POP3",
    123: "NTP",
    143: "IMAP",
    161: "SNMP",
    389: "LDAP",
    443: "HTTPS",
    445: "SMB",
    587: "SMTP submission",
    993: "IMAPS",
    995: "POP3S",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    8080: "Common alternative HTTP port",
}


def demonstrate_ports() -> None:
    section("13. Ports")

    explain(
        """
A port is a 16-bit transport-layer number.

Valid TCP and UDP port numbers range from:

    0 through 65535

Common conceptual categories:

    0-1023
        Traditionally known as well-known ports.

    1024-49151
        Registered ports.

    49152-65535
        Commonly used as dynamic/private ports, though exact ephemeral-port
        allocation depends on the operating system.

A TCP endpoint is commonly represented as:

    IP address + TCP port

For example:

    192.168.1.20:22

An IPv6 endpoint is conventionally written with brackets:

    [2001:db8::20]:443
"""
    )

    for port, service in COMMON_PORTS.items():
        print(f"{port:5} -> {service}")


# ============================================================================
# 15. TCP AND UDP SOCKETS
# ============================================================================

def demonstrate_socket_concepts() -> None:
    section("14. TCP and UDP sockets")

    explain(
        """
A socket is an operating-system communication endpoint.

TCP server concept:

    socket()
      |
    bind()
      |
    listen()
      |
    accept()
      |
    recv()/send()

TCP client concept:

    socket()
      |
    connect()
      |
    send()/recv()

UDP is different:

    socket()
      |
    sendto()/recvfrom()

UDP does not use TCP's connection establishment and reliable byte-stream
semantics.
"""
    )

    tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        print("Created TCP socket.")
        print(f"Address family: {tcp_socket.family}")
        print(f"Socket type:    {tcp_socket.type}")
        print(f"Protocol:       {tcp_socket.proto}")
    finally:
        tcp_socket.close()

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        print("\nCreated UDP socket.")
        print(f"Address family: {udp_socket.family}")
        print(f"Socket type:    {udp_socket.type}")
        print(f"Protocol:       {udp_socket.proto}")
    finally:
        udp_socket.close()


# ============================================================================
# 16. SAFE LOCAL TCP SERVER
# ============================================================================

def demonstrate_local_tcp_server() -> None:
    section("15. Local TCP server and client")

    explain(
        """
This demonstration creates a temporary TCP server on the loopback interface.

Binding to 127.0.0.1 means the service is reachable only from the local host,
not from other machines on the network.

The operating system chooses an available ephemeral port because port 0 is
used during bind().
"""
    )

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        server_address = server.getsockname()
        print(f"Server listening on {server_address}")

        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            client.settimeout(2)
            client.connect(server_address)

            connection, client_address = server.accept()

            try:
                print(f"Accepted client from {client_address}")

                message = b"Hello from TCP client"
                client.sendall(message)

                received = connection.recv(1024)

                print(f"Server received: {received!r}")

                connection.sendall(b"TCP response received")

                response = client.recv(1024)
                print(f"Client received: {response!r}")

            finally:
                connection.close()

        finally:
            client.close()

    except OSError as error:
        print(f"TCP demonstration failed: {error}")

    finally:
        server.close()


# ============================================================================
# 17. LOCAL UDP SERVER
# ============================================================================

def demonstrate_local_udp_server() -> None:
    section("16. Local UDP server and client")

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        server.bind(("127.0.0.1", 0))
        server_address = server.getsockname()
        print(f"UDP server listening on {server_address}")

        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            client.settimeout(2)

            message = b"Hello from UDP client"
            client.sendto(message, server_address)

            received, client_address = server.recvfrom(1024)

            print(f"Server received {received!r} from {client_address}")

            server.sendto(b"UDP response", client_address)

            response, _ = client.recvfrom(1024)

            print(f"Client received: {response!r}")

        finally:
            client.close()

    except OSError as error:
        print(f"UDP demonstration failed: {error}")

    finally:
        server.close()


# ============================================================================
# 18. SOCKET ADDRESS INFORMATION
# ============================================================================

def demonstrate_socket_address_information() -> None:
    section("17. Socket address information")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.bind(("127.0.0.1", 0))

        local_endpoint = sock.getsockname()

        print(f"Local endpoint: {local_endpoint}")

    finally:
        sock.close()

    explain(
        """
getsockname() returns the local endpoint of a socket.

For a connected TCP socket, getpeername() returns the remote endpoint.

This distinction is important:

    local endpoint
        Where the local application is bound.

    peer endpoint
        The remote endpoint involved in the connection.
"""
    )


# ============================================================================
# 19. SERVICE PORT TEST
# ============================================================================

def test_tcp_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Test whether a TCP connection can be established to a host and port."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def demonstrate_port_connectivity() -> None:
    section("18. TCP port connectivity test")

    explain(
        """
A TCP connection test answers a narrow question:

    Can this machine establish a TCP connection to this host and port?

It does not prove that:

    the application is healthy,
    authentication will work,
    the protocol is correct,
    a firewall is completely absent,
    or UDP traffic is permitted.

This demonstration uses example.com and common web ports.
"""
    )

    host = "example.com"

    for port in (80, 443):
        result = test_tcp_port(host, port)
        status = "reachable" if result else "not reachable"
        print(f"{host}:{port} -> {status}")


# ============================================================================
# 20. DNS AND PORT ARE DIFFERENT
# ============================================================================

def demonstrate_dns_vs_ports() -> None:
    section("19. DNS versus ports")

    explain(
        """
DNS and ports solve different problems.

DNS answers:

    "Which network address is associated with this name?"

A port answers:

    "Which transport-layer service endpoint should receive this traffic?"

For example:

    example.com
        |
        DNS
        v
    93.184.216.34
        |
        TCP port 443
        v
    HTTPS service

Resolving a hostname does not mean that every port on the resulting host is
open.
"""
    )

    try:
        address = socket.gethostbyname("example.com")
        print(f"example.com resolved to: {address}")
    except socket.gaierror as error:
        print(f"Resolution failed: {error}")


# ============================================================================
# 21. LINUX COMMANDS
# ============================================================================

def run_command(command: list[str], timeout: float = 5.0) -> None:
    """Run a read-only system command for educational inspection."""
    print(f"\n$ {' '.join(command)}")

    executable = shutil.which(command[0])

    if executable is None:
        print(f"Command not found: {command[0]}")
        return

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        if result.stdout:
            print(result.stdout[:6000])

        if result.stderr:
            print(result.stderr[:3000])

        print(f"Exit code: {result.returncode}")

    except subprocess.TimeoutExpired:
        print("Command timed out.")
    except OSError as error:
        print(f"Command failed: {error}")


def demonstrate_linux_commands() -> None:
    section("20. Linux networking commands")

    explain(
        """
Important Linux networking commands include:

    ip addr
        Show IP addresses and interfaces.

    ip link
        Show and inspect interfaces.

    ip route
        Show the routing table.

    ip neigh
        Show the neighbor table.

    ss
        Inspect sockets and listening ports.

    hostname
        Display hostname.

    getent hosts NAME
        Query the system's configured name-service mechanism.

    resolvectl
        Inspect DNS resolver state on systems using systemd-resolved.

    ping
        Test IP reachability using ICMP or the platform's equivalent.

    traceroute / tracepath
        Investigate a path toward a destination.

    dig
        Perform detailed DNS queries when installed.

    nslookup
        DNS lookup utility.

The commands below are read-only inspection commands.
"""
    )

    if platform.system() == "Linux":
        commands = [
            ["ip", "addr"],
            ["ip", "route"],
            ["ip", "neigh"],
            ["ss", "-tuln"],
            ["hostname"],
        ]

        for command in commands:
            run_command(command)
    else:
        print(
            "The current operating system is not Linux, so Linux-specific "
            "commands are not executed."
        )


# ============================================================================
# 22. SOCKET STATES
# ============================================================================

def demonstrate_socket_states() -> None:
    section("21. TCP socket states")

    explain(
        """
Important TCP states include:

    LISTEN
        A server is waiting for incoming connection requests.

    SYN-SENT
        A client has sent a SYN and is waiting for a response.

    SYN-RECEIVED
        A server has received a SYN and is processing connection setup.

    ESTABLISHED
        The TCP connection is active.

    FIN-WAIT-1
    FIN-WAIT-2
    CLOSE-WAIT
    LAST-ACK
    TIME-WAIT
        Various stages of connection termination.

The ss command is commonly used on Linux to inspect these states.

Example conceptual command:

    ss -tan

The exact state transitions are part of TCP's connection-management
mechanism.
"""
    )


# ============================================================================
# 23. ROUTING BASICS
# ============================================================================

def demonstrate_routing_basics() -> None:
    section("22. Routing basics")

    explain(
        """
An IP address identifies an endpoint, while routing determines where packets
should be sent next.

A simplified routing decision looks like:

    destination IP
          |
          v
    routing table
          |
          v
    matching route
          |
          v
    interface + next hop

A typical Linux host may have:

    connected network route
    default route
    loopback route

The default route is used when a more specific matching route is unavailable.

The default route is often represented as:

    0.0.0.0/0

for IPv4, or:

    ::/0

for IPv6.
"""
    )

    if platform.system() == "Linux":
        run_command(["ip", "route"])


# ============================================================================
# 24. DEFAULT GATEWAY
# ============================================================================

def demonstrate_default_gateway() -> None:
    section("23. Default gateway")

    explain(
        """
A default gateway is a router used to reach destinations that are not
covered by more specific local routes.

Example:

    Computer
       |
       | 192.168.1.20
       |
    Router
       |
       | Internet
       |
    Remote network

The host's routing table might conceptually contain:

    192.168.1.0/24 -> local interface
    0.0.0.0/0      -> 192.168.1.1

The second route is the default route.
"""
    )

    if platform.system() == "Linux":
        run_command(["ip", "route", "show", "default"])


# ============================================================================
# 25. ARP AND NEIGHBOR DISCOVERY
# ============================================================================

def demonstrate_neighbor_discovery() -> None:
    section("24. ARP and neighbor discovery")

    explain(
        """
IPv4 uses ARP to associate local IPv4 addresses with link-layer addresses
such as Ethernet MAC addresses.

Conceptually:

    192.168.1.1
         |
        ARP
         v
    aa:bb:cc:dd:ee:ff

IPv6 uses Neighbor Discovery Protocol rather than ARP.

Linux exposes neighbor information through:

    ip neigh

The neighbor table is different from the routing table.

Routing answers:

    "Where should the packet go?"

Neighbor resolution helps answer:

    "Which local link-layer destination should receive the frame?"
"""
    )

    if platform.system() == "Linux":
        run_command(["ip", "neigh"])


# ============================================================================
# 26. ICMP CONCEPT
# ============================================================================

def demonstrate_icmp_concept() -> None:
    section("25. ICMP and ping")

    explain(
        """
ICMP is a network-layer control and diagnostic protocol.

Ping commonly uses ICMP Echo Request and Echo Reply.

A successful ping can indicate that:

    the destination is reachable,
    ICMP traffic is permitted,
    and a response was received.

A failed ping does not necessarily mean the host is down.

Possible reasons include:

    firewall filtering,
    ICMP being disabled,
    routing failure,
    DNS failure if a hostname was used,
    packet loss,
    temporary network failure.

Therefore:

    DNS failure
    TCP failure
    ICMP failure

are distinct problems and should be tested independently.
"""
    )


# ============================================================================
# 27. NAME RESOLUTION DIAGNOSTICS
# ============================================================================

def diagnose_hostname(hostname: str) -> None:
    """Perform basic non-invasive hostname diagnostics."""
    print(f"\nDiagnosing: {hostname}")

    try:
        addresses = socket.getaddrinfo(
            hostname,
            None,
            type=socket.SOCK_STREAM,
        )

        unique_addresses = sorted(
            {
                result[4][0]
                for result in addresses
                if result[4]
            }
        )

        print("Resolved addresses:")
        for address in unique_addresses:
            print(f"  {address}")

    except socket.gaierror as error:
        print(f"DNS/name resolution error: {error}")
        return

    for port in (80, 443):
        reachable = test_tcp_port(hostname, port)
        print(
            f"TCP {port}: "
            f"{'connection possible' if reachable else 'connection failed'}"
        )


# ============================================================================
# 28. NETWORKING DIAGNOSTIC WORKFLOW
# ============================================================================

def demonstrate_diagnostic_workflow() -> None:
    section("26. Networking troubleshooting workflow")

    explain(
        """
A disciplined troubleshooting sequence prevents unrelated problems from
being mixed together.

A useful workflow is:

    1. Check the physical or virtual interface.
    2. Check interface state.
    3. Check IP address.
    4. Check subnet configuration.
    5. Check routing table.
    6. Check default gateway.
    7. Test local connectivity.
    8. Test gateway connectivity.
    9. Test remote IP connectivity.
   10. Test DNS resolution.
   11. Test TCP connectivity to the required port.
   12. Test the application protocol itself.

Examples:

    ip addr
    ip link
    ip route
    ip neigh
    ping
    getent hosts
    ss
    curl

The key principle is to isolate layers.

If:

    DNS fails

there is little value in immediately debugging the web application's HTTP
logic.

If:

    DNS works
    TCP connection fails

the investigation should focus on routing, firewalling, listening services,
port selection, or transport connectivity.
"""
    )

    diagnose_hostname("example.com")


# ============================================================================
# 29. ERROR TYPES
# ============================================================================

def demonstrate_network_errors() -> None:
    section("27. Common networking errors")

    errors = {
        socket.gaierror: "Name/address resolution failure",
        ConnectionRefusedError: "Host reachable but connection was refused",
        TimeoutError: "Operation exceeded its timeout",
        ConnectionResetError: "Peer reset the connection",
        OSError: "General operating-system networking error",
    }

    for error_type, explanation_text in errors.items():
        print(f"{error_type.__name__:25} -> {explanation_text}")

    explain(
        """
Connection refused and timeout are especially important distinctions.

Connection refused usually means a response was received indicating that the
destination endpoint rejected the connection. A common cause is that no
service is listening on the requested TCP port.

A timeout means no usable response arrived within the configured timeout.
Possible causes include filtering, routing problems, packet loss, or an
unreachable destination.

These are symptoms, not guaranteed diagnoses.
"""
    )


# ============================================================================
# 30. TIMEOUTS
# ============================================================================

def demonstrate_timeouts() -> None:
    section("28. Network timeouts")

    explain(
        """
Network applications should normally use explicit timeouts.

Without appropriate timeouts, an application may remain blocked for an
unacceptably long period.

Typical categories include:

    connect timeout
        Maximum time allowed to establish a connection.

    read timeout
        Maximum time allowed while waiting for data.

    write timeout
        Maximum time allowed while sending data.

Timeout values are application-specific.

A timeout that is too short can cause false failures under normal network
latency. A timeout that is too long can make failures slow and expensive.
"""
    )

    test_host = "example.com"

    start = time.monotonic()

    try:
        with socket.create_connection((test_host, 443), timeout=2.0):
            elapsed = time.monotonic() - start
            print(f"Connection succeeded in approximately {elapsed:.3f} seconds.")
    except OSError as error:
        elapsed = time.monotonic() - start
        print(f"Connection failed after approximately {elapsed:.3f} seconds.")
        print(f"Error: {error}")


# ============================================================================
# 31. NETWORK BYTE ORDER
# ============================================================================

def demonstrate_network_byte_order() -> None:
    section("29. Network byte order")

    explain(
        """
Networking protocols frequently use network byte order, which is
big-endian.

Python provides conversion functions:

    htons()
        Host-to-network short.

    ntohs()
        Network-to-host short.

    htonl()
        Host-to-network long.

    ntohl()
        Network-to-host long.

These functions matter when dealing with low-level binary protocols.
"""
    )

    value = 8080

    network_value = socket.htons(value)
    restored_value = socket.ntohs(network_value)

    print(f"Host value:    {value}")
    print(f"Network value: {network_value}")
    print(f"Restored:      {restored_value}")


# ============================================================================
# 32. BINARY IP REPRESENTATION
# ============================================================================

def demonstrate_binary_ip() -> None:
    section("30. Binary representation of IPv4")

    address_text = "192.168.1.10"
    address = ipaddress.ip_address(address_text)

    packed = address.packed

    print(f"Address: {address_text}")
    print(f"Packed bytes: {packed}")
    print(f"Hexadecimal: {packed.hex()}")

    binary = ".".join(
        format(byte, "08b")
        for byte in packed
    )

    print(f"Binary: {binary}")


# ============================================================================
# 33. NETMASK CALCULATION
# ============================================================================

def demonstrate_netmask_calculation() -> None:
    section("31. CIDR and netmask calculation")

    prefixes = [8, 16, 20, 24, 26, 30, 32]

    for prefix in prefixes:
        network = ipaddress.ip_network(f"192.168.0.0/{prefix}")
        print(
            f"/{prefix:2} -> "
            f"netmask={network.netmask} "
            f"addresses={network.num_addresses}"
        )

    explain(
        """
The prefix length indicates how many leading bits belong to the network
portion.

For IPv4:

    host bits = 32 - prefix length

Therefore:

    total addresses = 2 ** host bits

A /32 contains one address.

A /31 contains two addresses and is commonly useful for point-to-point links
under modern IPv4 rules.

A /0 covers the entire IPv4 address space.
"""
    )


# ============================================================================
# 34. IPv6 BASICS
# ============================================================================

def demonstrate_ipv6() -> None:
    section("32. IPv6 basics")

    addresses = [
        "2001:db8:abcd:0012:0000:0000:0000:0001",
        "2001:db8:abcd:12::1",
        "::1",
        "fe80::abcd",
    ]

    for address_text in addresses:
        address = ipaddress.ip_address(address_text)

        print(f"Input:       {address_text}")
        print(f"Compressed:  {address.compressed}")
        print(f"Exploded:    {address.exploded}")
        print(f"Version:     IPv{address.version}")
        print()

    explain(
        """
IPv6 addresses are 128 bits.

IPv6 commonly uses /64 subnets for ordinary host networks, although IPv6
networking supports many prefix lengths.

IPv6 does not use broadcast in the IPv4 sense. Multicast and Neighbor
Discovery provide mechanisms used for functions that commonly involved
broadcast in IPv4 environments.
"""
    )


# ============================================================================
# 35. UNIX DOMAIN SOCKETS
# ============================================================================

def demonstrate_unix_domain_sockets() -> None:
    section("33. Unix domain sockets")

    explain(
        """
Not every socket communicates over IP.

Unix domain sockets provide local inter-process communication on Unix-like
systems.

They are commonly used when:

    client and server are on the same machine,
    networking is unnecessary,
    filesystem-based socket addressing is convenient.

Common address families include:

    AF_INET
        IPv4.

    AF_INET6
        IPv6.

    AF_UNIX
        Unix domain sockets.

Unix domain sockets can avoid IP networking overhead for local IPC and can
also integrate with filesystem permissions depending on the socket type and
platform.
"""
    )

    if hasattr(socket, "AF_UNIX"):
        path = "/tmp/linux_networking_study_socket"

        try:
            if os.path.exists(path):
                os.remove(path)

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

            try:
                server.bind(path)
                server.listen(1)

                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

                try:
                    client.settimeout(2)
                    client.connect(path)

                    connection, _ = server.accept()

                    try:
                        client.sendall(b"local IPC message")
                        received = connection.recv(1024)
                        print(f"Unix socket server received: {received!r}")
                    finally:
                        connection.close()

                finally:
                    client.close()

            finally:
                server.close()

        except OSError as error:
            print(f"Unix socket demonstration failed: {error}")

        finally:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
    else:
        print("AF_UNIX is not available on this platform.")


# ============================================================================
# 36. SERVICE BINDING
# ============================================================================

def demonstrate_binding_addresses() -> None:
    section("34. Binding to specific addresses")

    explain(
        """
A server can bind to different local addresses.

127.0.0.1
    Accepts local loopback connections.

0.0.0.0
    IPv4 wildcard address. Usually means listen on all available IPv4
    interfaces for the socket.

A specific interface address
    Limits the service to that local address.

Example:

    server.bind(("127.0.0.1", 8080))

is very different from:

    server.bind(("0.0.0.0", 8080))

The second can expose the service to other reachable machines depending on
routing and firewall rules.

Binding broadly is therefore a security consideration.
"""
    )


# ============================================================================
# 37. PORT SECURITY
# ============================================================================

def demonstrate_port_security() -> None:
    section("35. Port security")

    explain(
        """
An open listening port is an exposed service endpoint.

Security principles:

    - Do not expose services that do not need network access.
    - Prefer binding development services to 127.0.0.1.
    - Use firewalls to restrict unnecessary access.
    - Authenticate services properly.
    - Encrypt sensitive communication.
    - Avoid insecure legacy protocols such as Telnet when secure alternatives
      are available.
    - Keep services patched.
    - Do not assume a non-standard port makes a service secure.
    - Log and monitor important services.

Port number selection is not an authentication mechanism.

Changing SSH from port 22 to another port may reduce some automated noise,
but it does not replace proper authentication, firewalling, and hardening.
"""
    )


# ============================================================================
# 38. DNS SECURITY
# ============================================================================

def demonstrate_dns_security() -> None:
    section("36. DNS security considerations")

    explain(
        """
DNS is part of the application's trust chain.

Potential risks include:

    DNS spoofing
        A client receives incorrect DNS information.

    DNS cache poisoning
        Incorrect records are inserted into a resolver's cache.

    DNS hijacking
        DNS configuration or delegation is altered maliciously.

    Plain DNS transport
        Traditional DNS commonly uses UDP or TCP port 53 without application-
        level encryption.

Security mechanisms and deployment models can include:

    DNSSEC
        Provides cryptographic authenticity for signed DNS data.

    DoH
        DNS over HTTPS.

    DoT
        DNS over TLS.

Encrypted DNS transport protects the DNS communication channel from certain
observers, while DNSSEC addresses authenticity of signed DNS data. They solve
different problems.
"""
    )


# ============================================================================
# 39. HOSTNAME VALIDATION
# ============================================================================

HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)"
    r"(?:[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"\.)*"
    r"[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def validate_hostname(hostname: str) -> bool:
    """Perform basic hostname syntax validation."""
    return bool(HOSTNAME_PATTERN.fullmatch(hostname))


def demonstrate_hostname_validation() -> None:
    section("37. Hostname validation")

    values = [
        "example.com",
        "server01",
        "api.example.com",
        "-invalid.example.com",
        "invalid-.example.com",
        "example..com",
    ]

    for hostname in values:
        print(f"{hostname:30} valid={validate_hostname(hostname)}")


# ============================================================================
# 40. PORT VALIDATION
# ============================================================================

def validate_port(port: int) -> bool:
    """Return True when port is a valid TCP/UDP port number."""
    return isinstance(port, int) and 0 <= port <= 65535


def demonstrate_port_validation() -> None:
    section("38. Port validation")

    values = [
        0,
        22,
        80,
        443,
        65535,
        -1,
        65536,
        8080.5,
    ]

    for port in values:
        print(f"{port!r:10} valid={validate_port(port)}")


# ============================================================================
# 41. NETWORK CONFIGURATION DATA MODEL
# ============================================================================

@dataclass
class NetworkEndpoint:
    """Represent a host and transport port."""

    host: str
    port: int
    protocol: str = "tcp"

    def __post_init__(self) -> None:
        protocol = self.protocol.lower()

        if protocol not in {"tcp", "udp"}:
            raise ValueError("Protocol must be TCP or UDP.")

        if not validate_port(self.port):
            raise ValueError("Port must be between 0 and 65535.")

        self.protocol = protocol

    def __str__(self) -> str:
        return f"{self.protocol.upper()} {self.host}:{self.port}"


def demonstrate_endpoint_model() -> None:
    section("39. Modeling network endpoints")

    endpoints = [
        NetworkEndpoint("127.0.0.1", 8080),
        NetworkEndpoint("192.168.1.20", 22),
        NetworkEndpoint("example.com", 443, "tcp"),
        NetworkEndpoint("192.168.1.30", 5353, "udp"),
    ]

    for endpoint in endpoints:
        print(endpoint)

    try:
        NetworkEndpoint("127.0.0.1", 70000)
    except ValueError as error:
        print(f"Validation example: {error}")


# ============================================================================
# 42. NETWORK RANGE MEMBERSHIP
# ============================================================================

def find_matching_network(
    address: str,
    networks: Iterable[str],
) -> list[str]:
    """Return networks containing the supplied IP address."""
    ip = ipaddress.ip_address(address)
    matches = []

    for network_text in networks:
        network = ipaddress.ip_network(network_text, strict=False)

        if ip.version == network.version and ip in network:
            matches.append(str(network))

    return matches


def demonstrate_network_matching() -> None:
    section("40. Finding the network containing an address")

    networks = [
        "10.0.0.0/8",
        "192.168.0.0/16",
        "192.168.10.0/24",
        "172.16.0.0/12",
    ]

    address = "192.168.10.42"

    matches = find_matching_network(address, networks)

    print(f"Address: {address}")
    print("Matching networks:")

    for match in matches:
        print(f"  {match}")


# ============================================================================
# 43. DNS RESULT STRUCTURE
# ============================================================================

def demonstrate_getaddrinfo() -> None:
    section("41. Detailed getaddrinfo() results")

    try:
        results = socket.getaddrinfo(
            "example.com",
            443,
            type=socket.SOCK_STREAM,
        )

        for result in results[:10]:
            family, socket_type, protocol, canonical_name, sockaddr = result

            print(
                f"family={family}, "
                f"type={socket_type}, "
                f"protocol={protocol}, "
                f"canonical={canonical_name!r}, "
                f"address={sockaddr}"
            )

    except socket.gaierror as error:
        print(f"getaddrinfo failed: {error}")


# ============================================================================
# 44. SERVICE NAME RESOLUTION
# ============================================================================

def demonstrate_service_names() -> None:
    section("42. Service names and ports")

    services = [
        ("http", "tcp"),
        ("https", "tcp"),
        ("ssh", "tcp"),
        ("domain", "udp"),
    ]

    for service, protocol in services:
        try:
            port = socket.getservbyname(service, protocol)
            print(f"{service}/{protocol} -> port {port}")
        except OSError as error:
            print(f"{service}/{protocol} -> unavailable: {error}")

    try:
        print(f"Port 80/tcp -> service {socket.getservbyport(80, 'tcp')}")
    except OSError as error:
        print(f"Reverse service lookup failed: {error}")


# ============================================================================
# 45. DNS LOOKUP TIMING
# ============================================================================

def demonstrate_dns_timing() -> None:
    section("43. Measuring DNS lookup duration")

    hostname = "example.com"

    start = time.perf_counter()

    try:
        socket.getaddrinfo(hostname, None)
        elapsed = time.perf_counter() - start

        print(f"Lookup for {hostname}: {elapsed * 1000:.2f} ms")

    except socket.gaierror as error:
        elapsed = time.perf_counter() - start
        print(f"Lookup failed after {elapsed * 1000:.2f} ms: {error}")

    explain(
        """
Timing a DNS lookup measures the behavior of the local name-resolution
path, not necessarily a direct query to an authoritative DNS server.

The result can be affected by:

    cache state,
    local resolver,
    network latency,
    recursive DNS server,
    DNS configuration,
    and temporary network conditions.
"""
    )


# ============================================================================
# 46. CONNECTION LATENCY
# ============================================================================

def demonstrate_connection_timing() -> None:
    section("44. Measuring TCP connection time")

    host = "example.com"
    port = 443

    start = time.perf_counter()

    try:
        with socket.create_connection((host, port), timeout=3):
            elapsed = time.perf_counter() - start

        print(
            f"TCP connection to {host}:{port} "
            f"completed in {elapsed * 1000:.2f} ms"
        )

    except OSError as error:
        elapsed = time.perf_counter() - start

        print(
            f"TCP connection failed after "
            f"{elapsed * 1000:.2f} ms: {error}"
        )

    explain(
        """
TCP connection timing does not equal complete application response time.

For HTTPS, for example, a complete request can involve:

    DNS lookup
    TCP handshake
    TLS handshake
    HTTP request
    HTTP response

Each stage contributes to total latency.
"""
    )


# ============================================================================
# 47. PERFORMANCE CONSIDERATIONS
# ============================================================================

def demonstrate_performance_considerations() -> None:
    section("45. Networking performance considerations")

    explain(
        """
Important performance factors include:

    Latency
        Time required for data or a request to travel through the network.

    Bandwidth
        Maximum data-transfer capacity.

    Throughput
        Actual useful data transferred per unit time.

    Packet loss
        Packets that do not successfully reach the intended destination.

    Jitter
        Variation in packet delay.

    Connection overhead
        Cost associated with establishing transport and security sessions.

A useful distinction is:

    bandwidth != latency

A high-bandwidth connection can still have high latency.

Applications can improve network performance through appropriate techniques
such as connection reuse, batching, compression where beneficial, caching,
and avoiding unnecessary round trips.
"""
    )


# ============================================================================
# 48. TCP VS UDP
# ============================================================================

def demonstrate_tcp_udp_comparison() -> None:
    section("46. TCP versus UDP")

    comparison = [
        ("Connection", "Connection-oriented", "Connectionless"),
        ("Ordering", "Provides ordered byte stream", "No built-in ordering guarantee"),
        ("Reliability", "Reliable delivery mechanism", "No delivery guarantee"),
        ("Flow control", "Yes", "Not provided by UDP itself"),
        ("Congestion control", "Built into common TCP implementations", "Not provided by UDP itself"),
        ("Data model", "Byte stream", "Datagrams"),
        ("Typical uses", "Web, SSH, databases", "DNS, streaming, real-time applications"),
    ]

    print(f"{'Property':25} {'TCP':35} {'UDP':35}")
    print("-" * 95)

    for property_name, tcp_value, udp_value in comparison:
        print(
            f"{property_name:25} "
            f"{tcp_value:35} "
            f"{udp_value:35}"
        )


# ============================================================================
# 49. SECURITY BOUNDARIES
# ============================================================================

def demonstrate_security_boundaries() -> None:
    section("47. Networking security boundaries")

    explain(
        """
A network service should be evaluated across several boundaries.

Host exposure:
    Which interfaces are listening?

Network exposure:
    Which networks can reach the service?

Transport exposure:
    Which ports are open?

Application exposure:
    What protocol and commands are accepted?

Identity and authorization:
    Who is allowed to use the service?

Encryption:
    Can an observer read or alter traffic?

A service bound to 127.0.0.1 is normally much less exposed than the same
service bound to 0.0.0.0.

A firewall can provide another layer of control.

Application authentication and authorization remain necessary even when a
firewall exists.
"""
    )


# ============================================================================
# 50. INPUT VALIDATION
# ============================================================================

def parse_ip_or_hostname(value: str) -> tuple[str, str]:
    """
    Classify input as an IP address or hostname.

    This does not resolve the hostname and therefore does not perform network
    activity.
    """
    value = value.strip()

    try:
        ipaddress.ip_address(value)
        return "ip", value
    except ValueError:
        pass

    if validate_hostname(value):
        return "hostname", value

    return "invalid", value


def demonstrate_input_validation() -> None:
    section("48. Safe network input validation")

    values = [
        "127.0.0.1",
        "192.168.1.10",
        "example.com",
        "invalid hostname!",
        "2001:db8::1",
    ]

    for value in values:
        kind, normalized = parse_ip_or_hostname(value)
        print(f"{value!r:25} -> {kind:10} {normalized}")


# ============================================================================
# 51. SSRF SECURITY CONCEPT
# ============================================================================

def demonstrate_ssrf_concept() -> None:
    section("49. Server-side request forgery and network validation")

    explain(
        """
Applications that accept user-supplied URLs or hostnames need special care.

A naive application may accept:

    http://user-supplied-host/

and allow the server to connect to arbitrary destinations.

This can create SSRF risks, where a server is abused to access resources that
the user should not be able to reach directly.

Dangerous targets can include:

    localhost
    loopback addresses
    private networks
    link-local addresses
    cloud metadata endpoints
    internal administration services

Checking only whether input is syntactically a valid hostname is not enough.

Security-sensitive applications need an explicit network access policy and
must consider DNS rebinding, redirects, IPv4/IPv6 behavior, proxy settings,
and address resolution changes.

The parsing function in this script intentionally does not claim to be an
SSRF defense.
"""
    )


# ============================================================================
# 52. PRODUCTION DESIGN
# ============================================================================

def demonstrate_production_design() -> None:
    section("50. Production networking design")

    explain(
        """
Production network applications should consider:

Configuration
    Keep hostnames, ports, timeouts, and network policies configurable.

Reliability
    Handle connection failures, timeouts, retries, and partial failures.

Observability
    Record useful connection and application-level metrics.

Security
    Minimize exposed interfaces and ports, authenticate clients, and encrypt
    sensitive traffic.

Resource management
    Close sockets and avoid unbounded connection growth.

Concurrency
    Choose appropriate threading, asynchronous I/O, processes, or event-loop
    architecture.

Backpressure
    Prevent fast producers from overwhelming slow consumers.

Timeouts
    Avoid indefinitely blocked operations.

Retries
    Retry only operations where retrying is safe and useful. Use bounded
    retries and backoff.

Idempotency
    Repeating an operation should not unintentionally create duplicate
    effects.

DNS behavior
    Do not assume DNS records remain fixed indefinitely.

IPv6
    Applications should avoid assuming every host has only an IPv4 address.

Deployment
    Understand container networking, reverse proxies, firewalls, service
    discovery, load balancers, and cloud networking where applicable.
"""
    )


# ============================================================================
# 53. RETRY POLICY
# ============================================================================

def demonstrate_retry_logic() -> None:
    section("51. Safe retry concepts")

    explain(
        """
Retries are useful for transient network failures but can also make an
incident worse if implemented carelessly.

A good retry policy normally has:

    bounded attempts
    bounded total time
    backoff
    jitter
    awareness of whether the operation is safe to repeat

For demonstration, the following code implements exponential backoff
calculation without performing repeated network operations.
"""
    )

    base_delay = 0.25
    maximum_delay = 4.0

    for attempt in range(1, 6):
        delay = min(maximum_delay, base_delay * (2 ** (attempt - 1)))
        print(f"Attempt {attempt}: suggested base delay {delay:.2f} seconds")


# ============================================================================
# 54. NETWORK CONFIGURATION SUMMARY
# ============================================================================

def build_local_network_summary() -> dict[str, object]:
    """Collect basic non-destructive local network information."""
    summary: dict[str, object] = {
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "fqdn": socket.getfqdn(),
        "interfaces": get_linux_interfaces(),
    }

    try:
        summary["hostname_addresses"] = sorted(
            {
                result[4][0]
                for result in socket.getaddrinfo(
                    socket.gethostname(),
                    None,
                )
                if result[4]
            }
        )
    except socket.gaierror:
        summary["hostname_addresses"] = []

    return summary


def demonstrate_local_network_summary() -> None:
    section("52. Local networking summary")

    summary = build_local_network_summary()

    for key, value in summary.items():
        print(f"{key:25}: {value}")


# ============================================================================
# 55. PRACTICAL MINI DIAGNOSTIC TOOL
# ============================================================================

def network_diagnostic_tool(
    target: str,
    ports: tuple[int, ...] = (80, 443),
) -> None:
    """
    Perform a basic DNS and TCP diagnostic.

    This intentionally avoids scanning arbitrary port ranges. Only the
    explicitly supplied ports are tested.
    """
    section(f"53. Mini diagnostic tool: {target}")

    kind, value = parse_ip_or_hostname(target)

    if kind == "invalid":
        print("Invalid IP address or hostname.")
        return

    print(f"Target type: {kind}")

    addresses: list[str] = []

    if kind == "ip":
        addresses = [value]
    else:
        try:
            results = socket.getaddrinfo(
                value,
                None,
                type=socket.SOCK_STREAM,
            )

            addresses = sorted(
                {
                    result[4][0]
                    for result in results
                    if result[4]
                }
            )

        except socket.gaierror as error:
            print(f"DNS resolution failed: {error}")
            return

    print("Resolved addresses:")

    for address in addresses:
        print(f"  {address}")

    for address in addresses:
        print(f"\nTesting address: {address}")

        for port in ports:
            reachable = test_tcp_port(address, port, timeout=1.5)

            print(
                f"  TCP {port:5}: "
                f"{'reachable' if reachable else 'not reachable'}"
            )


# ============================================================================
# 56. EDGE CASES
# ============================================================================

def demonstrate_edge_cases() -> None:
    section("54. Networking edge cases")

    explain(
        """
Important edge cases include:

    1. A hostname can resolve to multiple IPv4 or IPv6 addresses.

    2. DNS can succeed while the required TCP port is unreachable.

    3. A TCP port can be reachable while the application protocol is broken.

    4. A service can listen on localhost but not be reachable remotely.

    5. A service can listen on all interfaces and accidentally become exposed.

    6. An IP address can belong to multiple overlapping network definitions,
       although routing uses longest-prefix matching to select the most
       specific applicable route.

    7. IPv4 and IPv6 can produce different connectivity behavior.

    8. DNS results can change over time.

    9. Reverse DNS may not exist.

   10. A timeout is not proof that a service is down.

   11. Ping failure is not proof that TCP is unavailable.

   12. Port numbers identify transport endpoints, not applications with
       absolute certainty. A service can operate on a non-standard port.

   13. NAT can make the externally visible address differ from a host's
       internal private address.

   14. Containers can have separate network namespaces and virtual interfaces.

   15. VPNs can introduce additional interfaces and alter routing.
"""
    )

    overlapping_networks = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("10.20.0.0/16"),
        ipaddress.ip_network("10.20.30.0/24"),
    ]

    address = ipaddress.ip_address("10.20.30.40")

    print(f"Address: {address}")

    matches = [
        network
        for network in overlapping_networks
        if address in network
    ]

    print("Matching networks:")

    for network in matches:
        print(f"  {network}")

    print(
        "Most specific matching prefix: "
        f"{max(matches, key=lambda network: network.prefixlen)}"
    )


# ============================================================================
# 57. COMMON MISTAKES
# ============================================================================

def demonstrate_common_mistakes() -> None:
    section("55. Common Linux networking mistakes")

    mistakes = [
        (
            "Confusing hostname with IP address",
            "A hostname requires name resolution; an IP address does not."
        ),
        (
            "Assuming DNS means connectivity",
            "Name resolution and transport connectivity are separate tests."
        ),
        (
            "Assuming port 80 means HTTP",
            "Applications can use non-standard ports."
        ),
        (
            "Binding development servers to 0.0.0.0",
            "This can expose the service to other reachable hosts."
        ),
        (
            "Using no socket timeout",
            "A failed network operation may block longer than intended."
        ),
        (
            "Treating ping as a universal connectivity test",
            "ICMP filtering can make ping fail while TCP works."
        ),
        (
            "Assuming IPv4 only",
            "Modern systems can use IPv6 as well."
        ),
        (
            "Ignoring routing",
            "A valid IP address is not enough to guarantee packet delivery."
        ),
        (
            "Assuming localhost means the network",
            "127.0.0.1 and ::1 refer to the local host."
        ),
        (
            "Using retries without limits",
            "Unbounded retries can amplify failures and increase load."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake:   {mistake}")
        print(f"Correct:   {correction}")


# ============================================================================
# 58. TESTS
# ============================================================================

def test_ip_validation() -> None:
    assert ipaddress.ip_address("127.0.0.1").is_loopback
    assert ipaddress.ip_address("192.168.1.1").is_private


def test_network_membership() -> None:
    network = ipaddress.ip_network("192.168.1.0/24")
    assert ipaddress.ip_address("192.168.1.20") in network
    assert ipaddress.ip_address("192.168.2.20") not in network


def test_hostname_validation() -> None:
    assert validate_hostname("example.com")
    assert validate_hostname("server01")
    assert not validate_hostname("-invalid.com")
    assert not validate_hostname("invalid-.com")


def test_port_validation() -> None:
    assert validate_port(0)
    assert validate_port(80)
    assert validate_port(65535)
    assert not validate_port(-1)
    assert not validate_port(65536)
    assert not validate_port(80.5)


def test_endpoint_model() -> None:
    endpoint = NetworkEndpoint("localhost", 8080, "TCP")
    assert endpoint.protocol == "tcp"

    try:
        NetworkEndpoint("localhost", 99999)
        raise AssertionError("Invalid port was accepted.")
    except ValueError:
        pass


def run_tests() -> None:
    section("56. Built-in tests")

    tests = [
        test_ip_validation,
        test_network_membership,
        test_hostname_validation,
        test_port_validation,
        test_endpoint_model,
    ]

    passed = 0

    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
            passed += 1
        except AssertionError as error:
            print(f"FAIL: {test.__name__}: {error}")

    print(f"\nTests passed: {passed}/{len(tests)}")


# ============================================================================
# 59. FINAL REFERENCE TABLE
# ============================================================================

def demonstrate_reference_table() -> None:
    section("57. Linux networking quick reference")

    reference = [
        ("ip addr", "Inspect IP addresses and interfaces"),
        ("ip link", "Inspect network interfaces"),
        ("ip route", "Inspect routing table"),
        ("ip neigh", "Inspect neighbor table"),
        ("ss -tuln", "Inspect listening TCP/UDP sockets"),
        ("hostname", "Display hostname"),
        ("getent hosts NAME", "Resolve a hostname using system configuration"),
        ("resolvectl", "Inspect systemd DNS resolver information"),
        ("ping HOST", "Test ICMP-based reachability"),
        ("traceroute HOST", "Investigate network path"),
        ("dig NAME", "Perform detailed DNS query"),
        ("nslookup NAME", "Perform DNS lookup"),
    ]

    print(f"{'Command':30} Purpose")
    print("-" * 78)

    for command, purpose in reference:
        print(f"{command:30} {purpose}")


# ============================================================================
# 60. MAIN PROGRAM
# ============================================================================

def main() -> None:
    """
    Run the educational demonstrations.

    The script is deliberately organized from foundational concepts to
    practical diagnostics, security, and production considerations.
    """

    print(
        """
Linux Networking
IP, ports, interfaces, hostname, DNS basics

This script performs educational, mostly read-only networking demonstrations.
Some sections make network connections to public example services.
"""
    )

    demonstrations = [
        demonstrate_networking_fundamentals,
        demonstrate_ip_addresses,
        demonstrate_subnets,
        demonstrate_ip_classification,
        demonstrate_ipaddress_operations,
        demonstrate_interfaces,
        demonstrate_local_addresses,
        demonstrate_hostname,
        demonstrate_dns_basics,
        demonstrate_forward_reverse_dns,
        demonstrate_dns_cache_concepts,
        demonstrate_hosts_file,
        demonstrate_ports,
        demonstrate_socket_concepts,
        demonstrate_local_tcp_server,
        demonstrate_local_udp_server,
        demonstrate_socket_address_information,
        demonstrate_port_connectivity,
        demonstrate_dns_vs_ports,
        demonstrate_linux_commands,
        demonstrate_socket_states,
        demonstrate_routing_basics,
        demonstrate_default_gateway,
        demonstrate_neighbor_discovery,
        demonstrate_icmp_concept,
        demonstrate_diagnostic_workflow,
        demonstrate_network_errors,
        demonstrate_timeouts,
        demonstrate_network_byte_order,
        demonstrate_binary_ip,
        demonstrate_netmask_calculation,
        demonstrate_ipv6,
        demonstrate_unix_domain_sockets,
        demonstrate_binding_addresses,
        demonstrate_port_security,
        demonstrate_dns_security,
        demonstrate_hostname_validation,
        demonstrate_port_validation,
        demonstrate_endpoint_model,
        demonstrate_network_matching,
        demonstrate_getaddrinfo,
        demonstrate_service_names,
        demonstrate_dns_timing,
        demonstrate_connection_timing,
        demonstrate_performance_considerations,
        demonstrate_tcp_udp_comparison,
        demonstrate_security_boundaries,
        demonstrate_input_validation,
        demonstrate_ssrf_concept,
        demonstrate_production_design,
        demonstrate_retry_logic,
        demonstrate_local_network_summary,
        lambda: network_diagnostic_tool("example.com", (80, 443)),
        demonstrate_edge_cases,
        demonstrate_common_mistakes,
        run_tests,
        demonstrate_reference_table,
    ]

    for demonstration in demonstrations:
        safe_call(demonstration)

    section("Study file execution completed")

    print(
        """
The main concepts demonstrated include:

    IP addresses
    IPv4 and IPv6
    CIDR and subnetting
    private and special addresses
    interfaces
    hostnames
    DNS
    hosts file
    ports
    TCP
    UDP
    sockets
    routing
    default gateways
    ARP and IPv6 neighbor discovery
    ICMP
    Linux networking commands
    diagnostics
    timeouts
    security
    performance
    production considerations
    testing
"""
    )


if __name__ == "__main__":
    main()
