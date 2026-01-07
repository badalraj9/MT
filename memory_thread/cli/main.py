import typer
from memory_thread.cli import identity, assimilate, prune, decay, maintenance, graph
from memory_thread.cli import debug, timewarp_stub, replay_stub, maintenance_stub
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(
    name="nebula",
    help="Memory Thread Management CLI"
)

app.add_typer(identity.app, name="identity", help="Identity management and deduplication")
app.add_typer(assimilate.app, name="assimilate", help="Event consolidation engine")
app.add_typer(prune.app, name="prune", help="State pruning engine")
app.add_typer(decay.app, name="decay", help="Truth vector decay engine")

for cmd in maintenance_stub.app.registered_commands:
    maintenance.app.command(name=cmd.name)(cmd.callback)

app.add_typer(maintenance.app, name="maintenance", help="Orchestration of maintenance jobs")

# Debug commands at top level as requested by script usage `memory-thread load-fixtures`
# But script calls `memory-thread load-fixtures`. Typer supports this if added to `app`.
app.add_typer(debug.app, name="debug", help="Debug tools")
# Also alias them to top level
app.command("load-fixtures")(debug.load_fixtures)
app.command("ingest-provenance")(debug.ingest_provenance)

app.add_typer(timewarp_stub.app, name="timewarp", help="Phase 6 Timewarp Stub")
app.add_typer(replay_stub.app, name="replay", help="Phase 6 Replay Stub")
app.add_typer(graph.app, name="graph", help="Phase 7 Knowledge Graph")

if __name__ == "__main__":
    app()
