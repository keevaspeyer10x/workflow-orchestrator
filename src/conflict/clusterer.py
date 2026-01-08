"""
Conflict Clusterer

Groups related conflicts for efficient wave-based resolution.

When multiple agents work in parallel, their changes may form natural
clusters based on shared files, shared domains, or dependencies.
Resolving conflicts cluster-by-cluster is more efficient than handling
all conflicts at once.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ConflictCluster:
    """A group of related conflicts to resolve together."""
    id: str
    cluster_type: str  # "file", "domain", "dependency"
    agent_ids: list[str] = field(default_factory=list)
    shared_files: list[str] = field(default_factory=list)
    shared_domains: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)  # Cluster IDs
    complexity: str = "medium"  # "simple", "medium", "complex"

    @property
    def size(self) -> int:
        """Number of agents in this cluster."""
        return len(self.agent_ids)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "cluster_type": self.cluster_type,
            "agent_ids": self.agent_ids,
            "shared_files": self.shared_files,
            "shared_domains": self.shared_domains,
            "depends_on": self.depends_on,
            "complexity": self.complexity,
        }


class ConflictClusterer:
    """
    Groups agents into conflict clusters for wave-based resolution.

    Strategy:
    1. Build file overlap graph
    2. Build domain overlap graph (infer from paths, manifests)
    3. Find connected components = clusters
    4. Order clusters by dependencies
    """

    def cluster(
        self,
        agents: list[dict],
        by: str = "file",
    ) -> list[ConflictCluster]:
        """
        Cluster agents based on their changes.

        Args:
            agents: List of agent info dicts with keys:
                - id: Agent identifier
                - files: List of files touched
                - domains: Optional list of domains (auto-detected if missing)
            by: Clustering strategy - "file", "domain", or "both"

        Returns:
            List of ConflictCluster objects
        """
        if not agents:
            return []

        if len(agents) == 1:
            # Single agent = single cluster
            return [ConflictCluster(
                id="cluster-0",
                cluster_type=by,
                agent_ids=[agents[0]["id"]],
                shared_files=agents[0].get("files", []),
            )]

        # Build adjacency based on clustering strategy
        if by == "file":
            adjacency = self._build_file_adjacency(agents)
        elif by == "domain":
            adjacency = self._build_domain_adjacency(agents)
        else:  # both
            file_adj = self._build_file_adjacency(agents)
            domain_adj = self._build_domain_adjacency(agents)
            # Merge adjacencies
            adjacency = defaultdict(set)
            for agent_id, neighbors in file_adj.items():
                adjacency[agent_id].update(neighbors)
            for agent_id, neighbors in domain_adj.items():
                adjacency[agent_id].update(neighbors)

        # Find connected components
        clusters = self._find_connected_components(agents, adjacency)

        # Enrich clusters with shared files/domains
        for cluster in clusters:
            self._enrich_cluster(cluster, agents)

        return clusters

    def order_by_dependency(
        self,
        clusters: list[dict | ConflictCluster],
    ) -> list[dict | ConflictCluster]:
        """
        Order clusters so dependencies come first.

        Uses topological sort to ensure clusters are processed
        in an order where dependencies are resolved first.

        Args:
            clusters: List of clusters with "id" and "depends_on" keys

        Returns:
            Ordered list of clusters
        """
        if not clusters:
            return []

        # Convert to dicts if needed
        cluster_dicts = []
        for c in clusters:
            if isinstance(c, ConflictCluster):
                cluster_dicts.append(c.to_dict())
            else:
                cluster_dicts.append(c)

        # Build dependency graph
        id_to_cluster = {c["id"]: c for c in cluster_dicts}
        in_degree = {c["id"]: 0 for c in cluster_dicts}

        for cluster in cluster_dicts:
            for dep_id in cluster.get("depends_on", []):
                if dep_id in in_degree:
                    in_degree[cluster["id"]] += 1

        # Kahn's algorithm for topological sort
        queue = [cid for cid, degree in in_degree.items() if degree == 0]
        ordered = []

        while queue:
            current_id = queue.pop(0)
            ordered.append(id_to_cluster[current_id])

            # Reduce in-degree for dependent clusters
            for cluster in cluster_dicts:
                if current_id in cluster.get("depends_on", []):
                    in_degree[cluster["id"]] -= 1
                    if in_degree[cluster["id"]] == 0:
                        queue.append(cluster["id"])

        # Handle cycles (shouldn't happen, but be safe)
        remaining = [c for c in cluster_dicts if c not in ordered]
        ordered.extend(remaining)

        return ordered

    def _build_file_adjacency(
        self,
        agents: list[dict],
    ) -> dict[str, set[str]]:
        """Build adjacency graph based on shared files."""
        adjacency = defaultdict(set)

        # Map files to agents
        file_to_agents = defaultdict(set)
        for agent in agents:
            agent_id = agent["id"]
            for file_path in agent.get("files", []):
                file_to_agents[file_path].add(agent_id)

        # Agents sharing files are adjacent
        for file_path, agent_ids in file_to_agents.items():
            agent_list = list(agent_ids)
            for i, a1 in enumerate(agent_list):
                for a2 in agent_list[i + 1:]:
                    adjacency[a1].add(a2)
                    adjacency[a2].add(a1)

        return adjacency

    def _build_domain_adjacency(
        self,
        agents: list[dict],
    ) -> dict[str, set[str]]:
        """Build adjacency graph based on shared domains."""
        adjacency = defaultdict(set)

        # Map domains to agents
        domain_to_agents = defaultdict(set)
        for agent in agents:
            agent_id = agent["id"]
            domains = agent.get("domains", self._infer_domains(agent.get("files", [])))
            for domain in domains:
                domain_to_agents[domain].add(agent_id)

        # Agents sharing domains are adjacent
        for domain, agent_ids in domain_to_agents.items():
            agent_list = list(agent_ids)
            for i, a1 in enumerate(agent_list):
                for a2 in agent_list[i + 1:]:
                    adjacency[a1].add(a2)
                    adjacency[a2].add(a1)

        return adjacency

    def _infer_domains(self, files: list[str]) -> list[str]:
        """Infer domains from file paths."""
        domains = set()

        domain_patterns = {
            "auth": ["auth", "login", "session", "permission"],
            "api": ["api/", "routes", "endpoints", "handlers"],
            "database": ["models", "migrations", "schema", "db"],
            "ui": ["components", "views", "pages", "templates"],
            "config": ["config", "settings"],
        }

        for file_path in files:
            path_lower = file_path.lower()
            for domain, patterns in domain_patterns.items():
                if any(p in path_lower for p in patterns):
                    domains.add(domain)

        return list(domains)

    def _find_connected_components(
        self,
        agents: list[dict],
        adjacency: dict[str, set[str]],
    ) -> list[ConflictCluster]:
        """Find connected components in the agent graph."""
        visited = set()
        clusters = []
        cluster_idx = 0

        agent_ids = [a["id"] for a in agents]

        for agent_id in agent_ids:
            if agent_id in visited:
                continue

            # BFS to find all connected agents
            component = []
            queue = [agent_id]

            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue

                visited.add(current)
                component.append(current)

                for neighbor in adjacency.get(current, []):
                    if neighbor not in visited:
                        queue.append(neighbor)

            # Create cluster from component
            clusters.append(ConflictCluster(
                id=f"cluster-{cluster_idx}",
                cluster_type="file",
                agent_ids=component,
            ))
            cluster_idx += 1

        return clusters

    def _enrich_cluster(
        self,
        cluster: ConflictCluster,
        agents: list[dict],
    ) -> None:
        """Add shared files and domains to cluster."""
        # Get all agents in this cluster
        cluster_agents = [a for a in agents if a["id"] in cluster.agent_ids]

        if len(cluster_agents) < 2:
            return

        # Find shared files
        file_sets = [set(a.get("files", [])) for a in cluster_agents]
        shared_files = file_sets[0]
        for fs in file_sets[1:]:
            shared_files = shared_files & fs
        cluster.shared_files = list(shared_files)

        # Find shared domains
        domain_sets = [
            set(a.get("domains", self._infer_domains(a.get("files", []))))
            for a in cluster_agents
        ]
        shared_domains = domain_sets[0]
        for ds in domain_sets[1:]:
            shared_domains = shared_domains & ds
        cluster.shared_domains = list(shared_domains)

        # Assess complexity
        total_files = sum(len(a.get("files", [])) for a in cluster_agents)
        if total_files > 20 or len(cluster.agent_ids) > 3:
            cluster.complexity = "complex"
        elif total_files > 10 or len(cluster.agent_ids) > 2:
            cluster.complexity = "medium"
        else:
            cluster.complexity = "simple"
