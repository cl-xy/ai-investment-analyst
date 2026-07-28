"""
Investment Analyst CLI

Commands:
  analyze --ticker NVDA [--ticker AAPL]   Analyze specific tickers
  analyze --portfolio                       Analyze your full portfolio
  chat                                      Interactive conversational mode
  portfolio list                            Show current holdings
  portfolio add NVDA --shares 10 --cost 120.00
  portfolio remove NVDA
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env before any LangChain imports resolve API keys
load_dotenv()

import typer
from langchain_core.messages import HumanMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

# Ensure project root is on sys.path when run as `python -m src.cli.main`
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent.checkpointer import get_checkpointer
from src.agent.graph import build_graph
from src.agent.mcp_client import create_mcp_client

console = Console()
app = typer.Typer(help="Investment Analyst Agent", add_completion=False)
portfolio_app = typer.Typer(help="Manage your portfolio")
app.add_typer(portfolio_app, name="portfolio")

_DEFAULT_THREAD = "default-session"


async def _run_graph(
    user_message: str,
    thread_id: str = _DEFAULT_THREAD,
    intent: str | None = None,
    tickers: list[str] | None = None,
) -> dict:
    client = create_mcp_client()
    tools_list = await client.get_tools()
    mcp_tools = {t.name: t for t in tools_list}
    graph = build_graph(mcp_tools)
    async with get_checkpointer() as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}
        initial_state: dict = {"messages": [HumanMessage(content=user_message)]}
        if intent:
            initial_state["intent"] = intent
        if tickers:
            initial_state["tickers_to_analyze"] = tickers
        result = await compiled.ainvoke(initial_state, config=config)
    return result


@app.command()
def analyze(
    ticker: list[str] = typer.Option([], "--ticker", "-t", help="Ticker symbol(s) to analyze"),
    portfolio: bool = typer.Option(False, "--portfolio", "-p", help="Analyze your full portfolio"),
    thread_id: str = typer.Option(
        _DEFAULT_THREAD, "--session", help="Session thread ID for conversation history"
    ),
):
    """Analyze stocks or your full portfolio."""
    if portfolio:
        message = "Please run a full portfolio analysis."
    elif ticker:
        tickers_str = ", ".join(t.upper() for t in ticker)
        message = f"Analyze these stocks: {tickers_str}"
    else:
        console.print("[red]Provide --ticker SYMBOL or --portfolio[/red]")
        raise typer.Exit(1)

    console.print(Panel(f"[bold blue]Analyzing:[/bold blue] {message}", expand=False))

    with console.status("[cyan]Fetching data and running analysis...[/cyan]"):
        result = asyncio.run(_run_graph(message, thread_id))

    report = result.get("report_markdown", "")
    if report:
        console.print(Markdown(report))
    else:
        # Show the last AI message if no report was generated
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                console.print(Markdown(msg.content))
                break


@app.command()
def chat(
    thread_id: str = typer.Option(
        _DEFAULT_THREAD, "--session", help="Session thread ID for conversation history"
    ),
):
    """Interactive chat with the investment analyst."""
    console.print(
        Panel(
            "[bold green]Investment Analyst Chat[/bold green]\nType 'exit' or Ctrl+C to quit.",
            expand=False,
        )
    )

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        if user_input.strip().lower() in ("exit", "quit", "q"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if not user_input.strip():
            continue

        with console.status("[cyan]Thinking...[/cyan]"):
            result = asyncio.run(_run_graph(user_input, thread_id))

        messages = result.get("messages", [])
        for msg in reversed(messages):
            if hasattr(msg, "type") and msg.type == "ai":
                console.print("\n[bold green]Analyst:[/bold green]")
                console.print(Markdown(msg.content))
                break

        report = result.get("report_markdown", "")
        if report:
            console.print(Markdown(report))


@portfolio_app.command("list")
def portfolio_list(
    thread_id: str = typer.Option(_DEFAULT_THREAD, "--session"),
):
    """List your current portfolio holdings."""
    with console.status("[cyan]Loading portfolio...[/cyan]"):
        result = asyncio.run(_run_graph("Show me my portfolio", thread_id, intent="list_portfolio"))

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai":
            console.print(Markdown(msg.content))
            break


@portfolio_app.command("add")
def portfolio_add(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. NVDA"),
    shares: float = typer.Option(..., "--shares", "-s", help="Number of shares"),
    cost: float = typer.Option(..., "--cost", "-c", help="Average cost per share"),
    sector: str = typer.Option("Unknown", "--sector", help="Sector, e.g. Technology"),
    thread_id: str = typer.Option(_DEFAULT_THREAD, "--session"),
):
    """Add or update a position in your portfolio."""
    message = f"Add {shares} shares of {ticker.upper()} at ${cost:.2f} per share to my portfolio (sector: {sector})"
    with console.status(f"[cyan]Adding {ticker.upper()} to portfolio...[/cyan]"):
        result = asyncio.run(
            _run_graph(message, thread_id, intent="add_position", tickers=[ticker.upper()])
        )

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai":
            console.print(f"[green]{msg.content}[/green]")
            break


@portfolio_app.command("remove")
def portfolio_remove(
    ticker: str = typer.Argument(..., help="Ticker symbol to remove"),
    thread_id: str = typer.Option(_DEFAULT_THREAD, "--session"),
):
    """Remove a position from your portfolio."""
    message = f"Remove {ticker.upper()} from my portfolio"
    with console.status(f"[cyan]Removing {ticker.upper()}...[/cyan]"):
        result = asyncio.run(
            _run_graph(message, thread_id, intent="remove_position", tickers=[ticker.upper()])
        )

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai":
            console.print(f"[yellow]{msg.content}[/yellow]")
            break


if __name__ == "__main__":
    app()
