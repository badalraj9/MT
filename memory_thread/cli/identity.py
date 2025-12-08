import typer
from typing import Optional
from memory_thread.services.identity_service import IdentityService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)
app = typer.Typer()

@app.command()
def scan(
    entity_type: str = typer.Option(..., "--entity-type", help="Type of entity to scan (e.g., person, place)"),
    threshold: float = typer.Option(0.95, "--threshold", help="Similarity threshold for merge proposals"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposals without executing")
):
    """
    Scan for duplicate entities and propose merges.
    """
    service = IdentityService()
    typer.echo(f"Scanning for duplicate {entity_type} entities (threshold: {threshold})...")

    proposals = service.scan_duplicates(entity_type=entity_type, threshold=threshold)

    if not proposals:
        typer.echo("No duplicates found.")
        return

    typer.echo(f"Found {len(proposals)} merge proposals:")
    for p in proposals:
        typer.echo(f"\n[PROPOSAL] Confidence: {p.confidence:.4f} | Reason: {p.reason}")
        typer.echo(f"  Source: {p.source_entity.name} ({p.source_entity.id})")
        typer.echo(f"  Target: {p.target_entity.name} ({p.target_entity.id})")

        if not dry_run:
            if p.confidence > 0.95:
                typer.echo("  >> Auto-merging (High Confidence)")
                service.execute_merge(p)
            else:
                confirm = typer.confirm(f"  >> Merge '{p.source_entity.name}' into '{p.target_entity.name}'?")
                if confirm:
                    service.execute_merge(p)
                else:
                    typer.echo("  >> Skipped.")

@app.command()
def create(
    name: str = typer.Option(..., "--name"),
    type: str = typer.Option(..., "--type"),
    attributes: str = typer.Option("{}", "--attributes", help="JSON string of attributes")
):
    """
    Manually create a new entity.
    """
    import json
    service = IdentityService()
    try:
        attrs = json.loads(attributes)
        entity = service.create_entity(name=name, entity_type=type, attributes=attrs)
        typer.echo(f"Created entity: {entity.name} ({entity.id})")
    except Exception as e:
        typer.echo(f"Error: {e}")

@app.command()
def list(
    type: Optional[str] = typer.Option(None, "--type")
):
    """
    List entities.
    """
    service = IdentityService()
    entities = service.list_entities(entity_type=type)
    for e in entities:
        status = "MERGED" if e.merged_into else "ACTIVE"
        typer.echo(f"{e.id} | {e.name} | {e.entity_type} | {status}")
