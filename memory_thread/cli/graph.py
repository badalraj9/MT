import typer
from typing import Optional
from uuid import UUID
from memory_thread.services.graph_service import GraphService
from memory_thread.services.reasoning.query_engine import QueryEngine
from memory_thread.services.reasoning.inference_engine import InferenceEngine

app = typer.Typer(help="Graph operations and reasoning.")

@app.command()
def show(entity_id: str, direction: str = "out"):
    """
    Show relations for an entity.
    """
    try:
        eid = UUID(entity_id)
        graph = GraphService()
        rels = graph.get_relations(eid, direction=direction)
        if not rels:
            typer.echo("No relations found.")
            return

        typer.echo(f"Relations for {entity_id} ({direction}):")
        for r in rels:
            typer.echo(f" - {r['relation_type']} -> {r['target_entity_id']} (conf: {r['confidence']})")
    except ValueError:
        typer.echo("Invalid UUID.")

@app.command()
def path(start_id: str, end_id: str, max_hops: int = 5):
    """
    Find path between two entities.
    """
    try:
        sid = UUID(start_id)
        eid = UUID(end_id)
        engine = QueryEngine()

        path_list = engine.find_path(sid, eid, max_hops=max_hops)

        if not path_list:
            typer.echo("No path found.")
            return

        typer.echo(f"Path found ({len(path_list)} steps):")
        curr = start_id
        for step in path_list:
            typer.echo(f"{curr} --[{step['relation_type']}]--> {step['target_entity_id']}")
            curr = step['target_entity_id']

    except ValueError:
        typer.echo("Invalid UUID.")

@app.command()
def infer(entity_id: str):
    """
    Run inference rules on an entity.
    """
    try:
        eid = UUID(entity_id)
        engine = InferenceEngine()

        typer.echo("Running inference...")
        engine.infer_transitive_relations(eid)
        engine.infer_symmetry(eid)
        engine.infer_inverse(eid)
        conflicts = engine.infer_contradictions(eid)

        if conflicts:
            typer.echo(f"Found {len(conflicts)} conflicts:")
            for c in conflicts:
                typer.echo(f" - {c['message']}")
        else:
            typer.echo("No conflicts found.")

        typer.echo("Inference complete.")

    except ValueError:
        typer.echo("Invalid UUID.")

if __name__ == "__main__":
    app()
