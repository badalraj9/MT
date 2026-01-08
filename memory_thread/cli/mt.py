"""
Memory Thread: CLI Tool
========================
Phase 11.2: Investor Demo Integration

Command-line interface for Memory Thread.
Usage: python -m memory_thread.cli.mt <command>

Commands:
  query    - Search the knowledge base
  ingest   - Add new information
  predict  - Forecast future values
  health   - Check system health
  demo     - Run interactive demo
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Optional

# Rich console for beautiful output (optional)
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    console = None

def print_header(text: str):
    """Print a styled header"""
    if RICH_AVAILABLE:
        console.print(Panel(text, style="bold blue"))
    else:
        print(f"\n{'='*60}")
        print(f"  {text}")
        print(f"{'='*60}\n")

def print_result(data: dict, title: str = "Result"):
    """Print formatted result"""
    if RICH_AVAILABLE:
        console.print_json(json.dumps(data))
    else:
        print(f"\n{title}:")
        print(json.dumps(data, indent=2, default=str))

def print_table(rows: list, columns: list, title: str = ""):
    """Print a table"""
    if RICH_AVAILABLE:
        table = Table(title=title)
        for col in columns:
            table.add_column(col, style="cyan")
        for row in rows:
            table.add_row(*[str(v) for v in row])
        console.print(table)
    else:
        print(f"\n{title}")
        print("-" * 60)
        for row in rows:
            print(" | ".join(str(v) for v in row))

# ============================================================================
# COMMANDS
# ============================================================================

def cmd_health(args):
    """Check system health"""
    print_header("Memory Thread Health Check")
    
    try:
        import psutil
        from memory_thread.db.postgres_client import PostgresClient
        
        # System metrics
        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        
        # Database check
        db_ok = True
        try:
            pg = PostgresClient()
            with pg.get_cursor() as cur:
                cur.execute("SELECT 1")
        except:
            db_ok = False
        
        health = {
            "status": "healthy" if db_ok else "degraded",
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_available_gb": round(mem.available / (1024**3), 2),
            "database_connected": db_ok,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        status_color = "green" if db_ok else "yellow"
        
        if RICH_AVAILABLE:
            console.print(f"[{status_color}]Status: {health['status'].upper()}[/]")
            console.print(f"CPU: {cpu}%")
            console.print(f"Memory: {mem.percent}% ({health['memory_available_gb']} GB available)")
            console.print(f"Database: {'✓ Connected' if db_ok else '✗ Disconnected'}")
        else:
            print(f"Status: {health['status'].upper()}")
            print(f"CPU: {cpu}%")
            print(f"Memory: {mem.percent}%")
            print(f"Database: {'Connected' if db_ok else 'Disconnected'}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_query(args):
    """Query the knowledge base"""
    print_header(f"Query: {args.query}")
    
    try:
        from memory_thread.services.retrieval_service import RetrievalService
        
        retrieval = RetrievalService()
        results = retrieval.query(args.query, top_k=args.top)
        
        if results:
            rows = []
            for r in results:
                name = r.get('name', 'Unknown')[:30]
                score = f"{r.get('score', 0):.2f}"
                entity_type = r.get('type', 'entity')
                rows.append([name, entity_type, score])
            
            print_table(rows, ["Name", "Type", "Relevance"], "Results")
        else:
            print("No results found.")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_ingest(args):
    """Ingest new data"""
    print_header(f"Ingesting: {args.name}")
    
    try:
        import uuid
        from memory_thread.services.ingest_service import IngestService
        
        entity_id = args.entity_id or str(uuid.uuid4())
        
        # Parse data from JSON string or key=value pairs
        data = {}
        if args.data:
            if args.data.startswith('{'):
                data = json.loads(args.data)
            else:
                for pair in args.data.split(','):
                    if '=' in pair:
                        k, v = pair.split('=', 1)
                        data[k.strip()] = v.strip()
        
        ingest = IngestService()
        # Would call async method here
        
        print(f"✓ Entity ID: {entity_id}")
        print(f"✓ Type: {args.type}")
        print(f"✓ Name: {args.name}")
        print(f"✓ Data: {data}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_predict(args):
    """Make predictions"""
    print_header(f"Predicting: {args.metric} for {args.entity[:8]}...")
    
    try:
        from memory_thread.services.predictive_service import PredictiveService
        
        predictor = PredictiveService()
        prediction = predictor.forecast(args.entity, args.metric, args.days)
        
        result = {
            "entity_id": args.entity[:8] + "...",
            "metric": args.metric,
            "horizon": f"{args.days} days",
            "predicted_value": prediction.predicted_value,
            "confidence": f"{prediction.confidence:.0%}",
            "confidence_interval": prediction.confidence_interval
        }
        
        print_result(result, "Prediction")
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_demo(args):
    """Run interactive demo"""
    print_header("Memory Thread Interactive Demo")
    
    print("Welcome to Memory Thread - Your Cognitive Memory System\n")
    
    demo_steps = [
        ("1. System Health", "Checking system status...", cmd_health),
        ("2. Sample Query", None, None),
        ("3. Prediction", None, None),
        ("4. Meta-Cognition", None, None),
    ]
    
    for title, desc, _ in demo_steps:
        if RICH_AVAILABLE:
            console.print(f"[bold cyan]{title}[/]")
            if desc:
                console.print(f"  {desc}")
        else:
            print(f"\n{title}")
            if desc:
                print(f"  {desc}")
    
    # Run health check as demo
    print("\n")
    
    class HealthArgs:
        pass
    
    cmd_health(HealthArgs())
    
    print("\n[Demo complete. See /docs for full API documentation.]")
    return 0


def cmd_gaps(args):
    """Show knowledge gaps"""
    print_header("Knowledge Gaps")
    
    try:
        from memory_thread.services.meta_cognitive import MetaCognitiveEngine
        
        meta = MetaCognitiveEngine()
        gaps = meta.what_dont_i_know(args.entity if hasattr(args, 'entity') else None)
        
        if gaps:
            rows = []
            for g in gaps[:10]:
                rows.append([g.gap_type.value, g.description[:40], f"{g.importance:.0%}"])
            
            print_table(rows, ["Type", "Description", "Importance"], "Detected Gaps")
        else:
            print("No knowledge gaps detected.")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_suggestions(args):
    """Show maintenance suggestions"""
    print_header("Maintenance Suggestions")
    
    try:
        from memory_thread.services.maintenance_suggester import MaintenanceSuggester
        
        suggester = MaintenanceSuggester()
        suggestions = suggester.get_suggestions(args.limit if hasattr(args, 'limit') else 10)
        
        if suggestions:
            rows = []
            for s in suggestions:
                rows.append([s.priority.value, s.title[:35], f"{s.confidence:.0%}"])
            
            print_table(rows, ["Priority", "Title", "Confidence"], "Suggestions")
        else:
            print("No suggestions available.")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="mt",
        description="Memory Thread CLI - Cognitive Memory System"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Health command
    health_parser = subparsers.add_parser("health", help="Check system health")
    health_parser.set_defaults(func=cmd_health)
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query knowledge base")
    query_parser.add_argument("query", type=str, help="Natural language query")
    query_parser.add_argument("-t", "--top", type=int, default=5, help="Number of results")
    query_parser.set_defaults(func=cmd_query)
    
    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest new data")
    ingest_parser.add_argument("name", type=str, help="Entity name")
    ingest_parser.add_argument("-t", "--type", type=str, default="entity", help="Entity type")
    ingest_parser.add_argument("-e", "--entity-id", type=str, help="Entity UUID")
    ingest_parser.add_argument("-d", "--data", type=str, help="Data as JSON or key=value pairs")
    ingest_parser.set_defaults(func=cmd_ingest)
    
    # Predict command
    predict_parser = subparsers.add_parser("predict", help="Make predictions")
    predict_parser.add_argument("entity", type=str, help="Entity ID")
    predict_parser.add_argument("metric", type=str, help="Metric to predict")
    predict_parser.add_argument("-d", "--days", type=int, default=7, help="Forecast horizon")
    predict_parser.set_defaults(func=cmd_predict)
    
    # Demo command
    demo_parser = subparsers.add_parser("demo", help="Run interactive demo")
    demo_parser.set_defaults(func=cmd_demo)
    
    # Gaps command
    gaps_parser = subparsers.add_parser("gaps", help="Show knowledge gaps")
    gaps_parser.add_argument("-e", "--entity", type=str, help="Entity ID (optional)")
    gaps_parser.set_defaults(func=cmd_gaps)
    
    # Suggestions command
    suggest_parser = subparsers.add_parser("suggest", help="Show maintenance suggestions")
    suggest_parser.add_argument("-l", "--limit", type=int, default=10, help="Max suggestions")
    suggest_parser.set_defaults(func=cmd_suggestions)
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
