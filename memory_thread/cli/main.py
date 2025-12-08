import typer
from memory_thread.cli import identity
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

app = typer.Typer(
    name="nebula",
    help="Memory Thread Management CLI"
)

app.add_typer(identity.app, name="identity", help="Identity management and deduplication")

if __name__ == "__main__":
    app()
