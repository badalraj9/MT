import uuid
from typing import List, Dict, Optional, Set
from collections import deque

from memory_thread.services.graph_service import GraphService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class QueryEngine:
    """
    Multi-Hop Graph Query Engine.
    Implements BFS/DFS for pathfinding.
    """
    def __init__(self):
        self.graph = GraphService()

    def find_path(self, start_id: uuid.UUID, end_id: uuid.UUID, max_hops: int = 3, bidirectional: bool = True) -> Optional[List[Dict]]:
        """
        Finds the shortest path between start and end entities.
        Supports Bidirectional Search for efficiency.
        """
        if start_id == end_id:
            return []

        if bidirectional:
            return self._find_path_bidirectional(start_id, end_id, max_hops)
        else:
            return self._find_path_bfs(start_id, end_id, max_hops)

    def _find_path_bfs(self, start_id: uuid.UUID, end_id: uuid.UUID, max_hops: int) -> Optional[List[Dict]]:
        queue = deque([(str(start_id), [])])
        visited = {str(start_id)}

        while queue:
            curr_id, path = queue.popleft()

            if len(path) >= max_hops:
                continue

            relations = self.graph.get_relations(uuid.UUID(curr_id), direction="out")

            for rel in relations:
                target = str(rel['target_entity_id'])
                new_path = path + [rel]

                if target == str(end_id):
                    return new_path

                if target not in visited:
                    visited.add(target)
                    queue.append((target, new_path))
        return None

    def _find_path_bidirectional(self, start_id: uuid.UUID, end_id: uuid.UUID, max_hops: int) -> Optional[List[Dict]]:
        # Forward search
        q_fwd = deque([str(start_id)])
        visited_fwd = {str(start_id): []} # id -> path_to_reach

        # Backward search
        q_bwd = deque([str(end_id)])
        visited_bwd = {str(end_id): []} # id -> path_from_reach

        # Track depth to respect max_hops (approx)
        depth = 0

        while q_fwd and q_bwd and depth < max_hops:
            # Expand Forward
            if q_fwd:
                curr_fwd = q_fwd.popleft()
                rels_fwd = self.graph.get_relations(uuid.UUID(curr_fwd), direction="out")

                for rel in rels_fwd:
                    neighbor = str(rel['target_entity_id'])
                    if neighbor in visited_bwd:
                        # Path found!
                        # Path is: path_to_curr_fwd + [rel] + reverse(path_from_neighbor)
                        # Note: path_from_neighbor in visited_bwd stores edges coming back from end
                        # We need to reconstruct carefully.
                        # To simplify, let's just use visited maps to store paths.
                        path_a = visited_fwd[curr_fwd]
                        path_b = visited_bwd[neighbor] # These are edges from End backwards

                        # Correct direction for path_b: it contains edges like (prev <- end).
                        # Actually, visited_bwd stores edges traversed from end to start.
                        # So if end -> X, then visited_bwd[X] = [Edge(end->X)].
                        # Wait, get_relations 'in' direction gives incoming edges to End?
                        # No, for backward search, we traverse 'in' edges of current node to find parents.
                        # If we start at End and go backwards, we look for X where X -> End.

                        return path_a + [rel] + self._reverse_path(path_b)

                    if neighbor not in visited_fwd:
                        visited_fwd[neighbor] = visited_fwd[curr_fwd] + [rel]
                        q_fwd.append(neighbor)

            # Expand Backward
            if q_bwd:
                curr_bwd = q_bwd.popleft()
                # Find nodes X that point to curr_bwd (X -> curr_bwd)
                rels_bwd = self.graph.get_relations(uuid.UUID(curr_bwd), direction="in")

                for rel in rels_bwd:
                    neighbor = str(rel['source_entity_id'])
                    if neighbor in visited_fwd:
                        # Path found!
                        path_a = visited_fwd[neighbor]
                        path_b = visited_bwd[curr_bwd]
                        # rel is neighbor -> curr_bwd
                        return path_a + [rel] + self._reverse_path(path_b)

                    if neighbor not in visited_bwd:
                        visited_bwd[neighbor] = visited_bwd[curr_bwd] + [rel]
                        q_bwd.append(neighbor)

            depth += 1 # Rough depth tracking

        return None

    def _reverse_path(self, path: List[Dict]) -> List[Dict]:
        # path is [Edge(Y->Z), Edge(Z->End)]
        # We need to return them in order?
        # Actually in backward search:
        # Start at End. Find X where X->End. Path at X is [X->End].
        # Next find W where W->X. Path at W is [X->End, W->X] (order of discovery).
        # So we just need to reverse the list to get W->X, X->End.
        return path[::-1]

    def find_common_neighbors(self, entity_a: uuid.UUID, entity_b: uuid.UUID) -> List[Dict]:
        """
        Finds entities connected to both A and B.
        """
        # Get neighbors of A
        rels_a_out = self.graph.get_relations(entity_a, direction="out")
        targets_a = {str(r['target_entity_id']) for r in rels_a_out}

        # Get neighbors of B
        rels_b_out = self.graph.get_relations(entity_b, direction="out")
        targets_b = {str(r['target_entity_id']) for r in rels_b_out}

        common = targets_a.intersection(targets_b)
        return list(common)
