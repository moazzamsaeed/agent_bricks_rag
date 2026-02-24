"""
Financial Reports Assistant — Interactive CLI
==============================================
Query the Financial Reports Knowledge Assistant from the command line.
Supports a single one-shot question (via --question) or an interactive
REPL loop when run with no arguments.

Usage:
    # Interactive loop
    python query_ka.py

    # Single question
    python query_ka.py --question "What was the Q1 2025 EPS?"

    # Pipe a question in
    echo "What is the CapEx approval threshold?" | python query_ka.py --stdin

Environment:
    DATABRICKS_HOST   Workspace URL (or ~/.databrickscfg)
    DATABRICKS_TOKEN  Personal access token (or ~/.databrickscfg)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST          = "https://adb-6417907769725610.10.azuredatabricks.net"
ENDPOINT_NAME = "ka-e53ea1a5-endpoint"

WRAP_WIDTH = 88  # Console output wrap width

# ---------------------------------------------------------------------------
# SDK import
# ---------------------------------------------------------------------------

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
except ImportError:
    print("ERROR: databricks-sdk is not installed. Run: pip install databricks-sdk>=0.20.0")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Optional rich output (falls back to plain text gracefully)
# ---------------------------------------------------------------------------

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.text import Text

    _console = Console()

    def _print_header() -> None:
        _console.print(Rule("[bold blue]Financial Reports Assistant[/bold blue]"))
        _console.print(
            "[dim]Type your question and press Enter. Type [bold]exit[/bold] or [bold]quit[/bold] to stop.[/dim]\n"
        )

    def _print_answer(answer: str, citations: list[str]) -> None:
        _console.print(Panel(Markdown(answer), title="[green]Answer[/green]", border_style="green"))
        if citations:
            _console.print("\n[bold blue]Sources retrieved:[/bold blue]")
            for i, c in enumerate(citations, 1):
                _console.print(f"  [{i}] {c}")
        _console.print()

    def _print_error(msg: str) -> None:
        _console.print(f"[bold red]ERROR:[/bold red] {msg}")

    def _prompt(text: str = "You") -> str:
        return _console.input(f"[bold cyan]{text}>[/bold cyan] ")

    RICH_AVAILABLE = True

except ImportError:
    RICH_AVAILABLE = False

    def _print_header() -> None:  # type: ignore[misc]
        print("=" * WRAP_WIDTH)
        print("Financial Reports Assistant")
        print("Type your question and press Enter. Type 'exit' or 'quit' to stop.")
        print("=" * WRAP_WIDTH)
        print()

    def _print_answer(answer: str, citations: list[str]) -> None:  # type: ignore[misc]
        print("\n--- Answer " + "-" * (WRAP_WIDTH - 10))
        for line in textwrap.wrap(answer, WRAP_WIDTH):
            print(line)
        if citations:
            print("\nSources retrieved:")
            for i, c in enumerate(citations, 1):
                print(f"  [{i}] {c}")
        print("-" * WRAP_WIDTH)
        print()

    def _print_error(msg: str) -> None:  # type: ignore[misc]
        print(f"ERROR: {msg}", file=sys.stderr)

    def _prompt(text: str = "You") -> str:  # type: ignore[misc]
        return input(f"{text}> ").strip()


# ---------------------------------------------------------------------------
# Core query logic
# ---------------------------------------------------------------------------


def query_knowledge_assistant(
    client: WorkspaceClient,
    question: str,
    endpoint_name: str = ENDPOINT_NAME,
) -> tuple[str, list[str]]:
    """
    Send a question to the Knowledge Assistant endpoint.

    Returns:
        (answer_text, list_of_source_citations)
    """
    resp = client.api_client.do(
        "POST",
        f"/serving-endpoints/{endpoint_name}/invocations",
        body={"input": [{"role": "user", "content": question}]},
    )

    # Parse OpenAI Responses API format returned by Agent Bricks KA
    answer_parts: list[str] = []
    citations: list[str] = []
    for msg in resp.get("output", []):
        for part in msg.get("content", []):
            if part.get("type") == "output_text":
                answer_parts.append(part.get("text", ""))
                for ann in part.get("annotations", []):
                    title = ann.get("title", "")
                    if title and title not in citations:
                        citations.append(title)

    return "".join(answer_parts), citations


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive CLI for the Financial Reports Knowledge Assistant.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query_ka.py
  python query_ka.py --question "What was Q1 2025 EPS?"
  python query_ka.py --endpoint my-custom-endpoint --question "..."
  echo "What is the CapEx threshold?" | python query_ka.py --stdin
        """,
    )
    parser.add_argument(
        "--question", "-q",
        default=None,
        help="Ask a single question and exit",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read question from stdin (pipe mode)",
    )
    parser.add_argument(
        "--endpoint",
        default=ENDPOINT_NAME,
        help=f"Serving endpoint name (default: {ENDPOINT_NAME})",
    )
    parser.add_argument(
        "--host",
        default=HOST,
        help=f"Databricks workspace URL (default: {HOST})",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print raw JSON response instead of formatted output",
    )
    return parser.parse_args()


def run_single_question(
    client: WorkspaceClient,
    question: str,
    endpoint_name: str,
    raw: bool = False,
) -> int:
    """Run a single question. Returns exit code (0 = success, 1 = error)."""
    try:
        answer, citations = query_knowledge_assistant(client, question, endpoint_name)
    except Exception as exc:
        _print_error(str(exc))
        return 1

    if raw:
        print(json.dumps({"answer": answer, "citations": citations}, indent=2))
    else:
        _print_answer(answer, citations)
    return 0


def run_interactive_loop(
    client: WorkspaceClient,
    endpoint_name: str,
    raw: bool = False,
) -> None:
    """Run an interactive Q&A REPL until the user exits."""
    _print_header()

    while True:
        try:
            question = _prompt()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        question = question.strip()
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q", "bye"}:
            print("Goodbye.")
            break

        try:
            answer, citations = query_knowledge_assistant(client, question, endpoint_name)
        except Exception as exc:
            _print_error(str(exc))
            continue

        if raw:
            print(json.dumps({"answer": answer, "citations": citations}, indent=2))
        else:
            _print_answer(answer, citations)


def main() -> None:
    args = parse_args()

    # Connect to Databricks
    try:
        client = WorkspaceClient(host=args.host)
    except Exception as exc:
        _print_error(f"Failed to connect to {args.host}: {exc}")
        sys.exit(1)

    # Pipe / stdin mode
    if args.stdin:
        question = sys.stdin.read().strip()
        if not question:
            _print_error("No question received from stdin.")
            sys.exit(1)
        sys.exit(run_single_question(client, question, args.endpoint, args.raw))

    # Single-question mode
    if args.question:
        sys.exit(run_single_question(client, args.question, args.endpoint, args.raw))

    # Interactive loop mode
    run_interactive_loop(client, args.endpoint, args.raw)


if __name__ == "__main__":
    main()
