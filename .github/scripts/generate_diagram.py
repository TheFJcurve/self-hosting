import os
import yaml
from pathlib import Path
from collections import defaultdict
from diagrams import Diagram, Cluster, Edge
from diagrams.onprem.container import Docker
from diagrams.onprem.network import Nginx
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.vcs import Gitea
from diagrams.onprem.auth import Oauth2Proxy
from diagrams.onprem.queue import Kafka
from diagrams.generic.network import Firewall
from diagrams.onprem.network import Internet

ICON_MAP = {
    "nginx":        Nginx,
    "grafana":      Grafana,
    "prometheus":   Prometheus,
    "postgres":     PostgreSQL,
    "redis":        Redis,
    "valkey":       Redis,
    "forgejo":      Gitea,
    "authentik":    Oauth2Proxy,
    "loki":         Kafka,      # closest available icon
    "promtail":     Kafka,
}

# Networks that bridge multiple stacks (defined in npm compose)
BRIDGE_NETWORKS = {
    "npm_proxy",
    "grafana_default",
}

def pick_icon(name: str):
    for key, cls in ICON_MAP.items():
        if key in name.lower():
            return cls
    return Docker

def load_stacks(root: Path) -> dict:
    """Returns { stack_name: { services: {...}, networks: {...} } }"""
    stacks = {}
    for compose_file in sorted(root.rglob("docker-compose.yml")):
        if any(p.startswith(".") for p in compose_file.parts):
            continue
        with open(compose_file) as f:
            data = yaml.safe_load(f)
        if not data or "services" not in data:
            continue
        stack_name = compose_file.parent.name
        stacks[stack_name] = {
            "services": data.get("services", {}),
            "networks": data.get("networks", {}),
            "file":     compose_file,
        }
    return stacks

def get_service_networks(svc: dict) -> list[str]:
    nets = svc.get("networks", [])
    if isinstance(nets, dict):
        return list(nets.keys())
    if isinstance(nets, list):
        return nets
    return []

def get_exposed_ports(svc: dict) -> list[str]:
    ports = []
    for p in svc.get("ports", []):
        if isinstance(p, dict):
            ports.append(f"{p.get('published', '?')}:{p.get('target', '?')}")
        else:
            ports.append(str(p))
    return ports

def resolve_network_name(net_key: str, stack_networks: dict) -> str:
    """Get the actual Docker network name from the compose networks block."""
    net_def = stack_networks.get(net_key, {}) or {}
    return net_def.get("name", net_key)

def main():
    root = Path(".")
    stacks = load_stacks(root)
    os.makedirs("docs", exist_ok=True)

    # --- Build a global map: real_network_name -> [service_names] ---
    network_members: dict[str, list[str]] = defaultdict(list)
    # service_name -> list of real network names
    service_networks: dict[str, list[str]] = defaultdict(list)
    # service_name -> list of exposed port strings
    service_ports: dict[str, list[str]] = {}
    # service_name -> stack_name
    service_stack: dict[str, str] = {}

    all_services: dict[str, dict] = {}   # svc_name -> svc dict

    for stack_name, stack in stacks.items():
        stack_nets = stack["networks"]
        for svc_name, svc in stack["services"].items():
            service_stack[svc_name] = stack_name
            all_services[svc_name] = svc
            ports = get_exposed_ports(svc)
            if ports:
                service_ports[svc_name] = ports
            for net_key in get_service_networks(svc):
                real_name = resolve_network_name(net_key, stack_nets)
                network_members[real_name].append(svc_name)
                service_networks[svc_name].append(real_name)

    # --- Determine isolated pairs (no shared network) ---
    def shares_network(a: str, b: str) -> bool:
        return bool(set(service_networks[a]) & set(service_networks[b]))

    # --- Draw ---
    with Diagram(
        "Self-Hosted Architecture — Networks & Isolation",
        filename="docs/architecture",
        outformat="png",
        show=False,
        direction="TB",
        graph_attr={
            "bgcolor":   "transparent",
            "pad":       "1.0",
            "nodesep":   "0.6",
            "ranksep":   "1.2",
            "fontsize":  "14",
        },
        node_attr={"fontsize": "11"},
        edge_attr={"fontsize": "9"},
    ):
        nodes: dict[str, object] = {}

        # --- Draw stacks as clusters ---
        for stack_name, stack in stacks.items():
            with Cluster(
                f"stack: {stack_name}",
                graph_attr={"bgcolor": "lightgrey", "style": "dashed"},
            ):
                for svc_name, svc in stack["services"].items():
                    icon   = pick_icon(svc_name)
                    ports  = service_ports.get(svc_name, [])
                    label  = svc_name.replace("_", "\n")
                    if ports:
                        label += "\n[" + ", ".join(ports) + "]"
                    nodes[svc_name] = icon(label)

        # --- depends_on edges (solid, dark) ---
        for svc_name, svc in all_services.items():
            deps = svc.get("depends_on", [])
            if isinstance(deps, dict):
                deps = list(deps.keys())
            for dep in deps:
                if svc_name in nodes and dep in nodes:
                    nodes[dep] >> Edge(
                        color="black",
                        style="solid",
                        label="depends",
                    ) >> nodes[svc_name]

        # --- Network edges (group by real network name) ---
        # For each network, draw edges between all member pairs
        NET_COLORS = [
            "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
            "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
            "#bcbd22", "#17becf",
        ]
        net_list = sorted(network_members.keys())
        for i, net_name in enumerate(net_list):
            members = list(dict.fromkeys(network_members[net_name]))  # dedupe
            color   = NET_COLORS[i % len(NET_COLORS)]
            style   = "bold" if net_name in BRIDGE_NETWORKS else "solid"

            # Draw a connection from first member to all others to represent
            # shared network membership without O(n²) edges
            for j in range(len(members) - 1):
                a, b = members[j], members[j + 1]
                if a in nodes and b in nodes:
                    nodes[a] - Edge(
                        color=color,
                        style=style,
                        label=net_name,
                    ) - nodes[b]

        # --- Isolation markers (red dashed) between known isolated stacks ---
        # Find stack pairs that share zero networks
        stack_names = list(stacks.keys())
        for i in range(len(stack_names)):
            for j in range(i + 1, len(stack_names)):
                sa, sb = stack_names[i], stack_names[j]
                svcs_a = list(stacks[sa]["services"].keys())
                svcs_b = list(stacks[sb]["services"].keys())
                # Check if ANY service in sa shares a network with ANY in sb
                connected = any(
                    shares_network(a, b)
                    for a in svcs_a for b in svcs_b
                )
                if not connected and svcs_a and svcs_b:
                    # Draw one isolation edge between representative services
                    a, b = svcs_a[0], svcs_b[0]
                    if a in nodes and b in nodes:
                        nodes[a] >> Edge(
                            color="red",
                            style="dashed",
                            label=f"ISOLATED\n{sa}↔{sb}",
                        ) >> nodes[b]

        # --- Exposed ports: draw edge from a pseudo-internet node ---
        exposed = {s: p for s, p in service_ports.items() if s in nodes}
        if exposed:
            with Cluster("Host / Internet", graph_attr={"style": "dotted"}):
                inet = Internet("host ports")
            for svc_name, ports in exposed.items():
                inet >> Edge(
                    color="orange",
                    style="bold",
                    label="\n".join(ports),
                ) >> nodes[svc_name]

if __name__ == "__main__":
    main()