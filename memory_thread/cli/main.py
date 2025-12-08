import typer
from memory_thread.cli import identity, assimilate
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(
    name="nebula",
    help="Memory Thread Management CLI"
)

app.add_typer(identity.app, name="identity", help="Identity management and deduplication")
app.add_typer(assimilate.app, name="assimilate", help="Event consolidation engine")

if __name__ == "__main__":
    app()
