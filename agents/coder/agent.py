"""
Coder Agent — The Builder.

Connects to Azure AI Foundry (gpt-4o) via OpenAI-compatible API,
uses GitHub MCP Server tools to read code, write fixes, and create PRs.
Handles the full rejection/resubmit loop with the Senior Coder.

Usage:
    python -m agents.coder.agent "Fix the authentication bug in login API"
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone

from azure.ai.projects import AIProjectClient
from azure.core.credentials import AzureKeyCredential
from opentelemetry import trace
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

from agents.coder.tools import GitHubMCPClient, get_tool_definitions, ToolResult
from agents.coder.prompts import CODER_SYSTEM_PROMPT, REJECTION_HANDLER_PROMPT
from agents.memory import AgentMemory

load_dotenv()
logger = logging.getLogger("coder.agent")
tracer = trace.get_tracer("nexussynapse.coder")
console = Console()

# ── Event bus for frontend updates ───────────────────────────────────

_event_listeners: list = []


def on_agent_event(callback):
    """Register a listener for agent events (used by frontend)."""
    _event_listeners.append(callback)


def _emit(event_type: str, data: dict):
    """Emit an event to all registered listeners."""
    event = {"type": event_type, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    for listener in _event_listeners:
        try:
            listener(event)
        except Exception:
            pass


class CoderAgent:
    """
    Autonomous Coder Agent powered by Azure AI Foundry + GitHub MCP.

    Flow:
    1. Receive task from Manager (or CLI)
    2. Read existing code via GitHub MCP
    3. Write fix using gpt-4o reasoning
    4. Submit PR via GitHub MCP
    5. Handle rejection feedback → fix → resubmit (up to MAX_RETRIES)
    """

    MAX_RETRIES = 3
    MAX_TOOL_ROUNDS = 15

    def __init__(self):
        # Azure AI Foundry — get OpenAI-compatible client
        conn_str = os.environ["PROJECT_CONNECTION_STRING"]
        api_key = os.environ["AZURE_API_KEY"]
        self.model = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o")

        self.project_client = AIProjectClient.from_connection_string(
            conn_str=conn_str,
            credential=AzureKeyCredential(api_key),
        )
        self.openai_client = self.project_client.get_openai_client(api_key=api_key)

        # GitHub MCP client
        self.mcp = GitHubMCPClient()

        # Persistent memory — survives across sessions since gpt-4o has none
        self.memory = AgentMemory("coder")

        # State
        self.conversation: list[dict] = []
        self.files_changed: list[str] = []
        self.pr_url: str | None = None
        self.attempt = 0

    # ── Tool dispatch ────────────────────────────────────────────────

    async def _execute_tool(self, name: str, arguments: dict) -> str:
        """Route an LLM tool call to the corresponding MCP method."""
        dispatch = {
            "github_read_file": lambda: self.mcp.read_file(
                arguments["path"], arguments.get("branch", "dev")
            ),
            "github_create_or_update_file": lambda: self.mcp.create_or_update_file(
                arguments["path"],
                arguments["content"],
                arguments["message"],
                arguments.get("branch", "feature/coder-agent"),
            ),
            "github_create_pull_request": lambda: self.mcp.create_pull_request(
                arguments["title"],
                arguments["body"],
                arguments.get("head", "feature/coder-agent"),
                arguments.get("base", "dev"),
            ),
            "github_list_files": lambda: self.mcp.list_files(
                arguments.get("path", ""), arguments.get("branch", "dev")
            ),
            "github_search_code": lambda: self.mcp.search_code(
                arguments["query"]
            ),
        }

        handler = dispatch.get(name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {name}"})

        result: ToolResult = await handler()

        # Track side effects
        if name == "github_create_or_update_file" and result.success:
            path = arguments["path"]
            if path not in self.files_changed:
                self.files_changed.append(path)
            _emit("file_changed", {"path": path, "content": arguments["content"]})

        if name == "github_create_pull_request" and result.success:
            if isinstance(result.data, dict):
                self.pr_url = result.data.get("html_url", str(result.data))
            else:
                self.pr_url = str(result.data)
            _emit("pr_created", {"url": self.pr_url})

        if result.success:
            return json.dumps(result.data) if isinstance(result.data, (dict, list)) else str(result.data)
        return json.dumps({"error": result.error})

    # ── Agentic loop ─────────────────────────────────────────────────

    async def run(self, task: str) -> dict:
        """
        Execute the full coder workflow for a given task.
        Returns a summary dict with status, files_changed, pr_url, and attempts.
        """
        with tracer.start_as_current_span("coder_agent.run") as span:
            span.set_attribute("task", task)

            console.print(Panel(
                f"[bold cyan]CODER AGENT ACTIVATED[/bold cyan]\n\n{task}",
                border_style="cyan",
                title="NexusSynapse",
            ))
            _emit("agent_started", {"task": task})

            await self.mcp.connect()

            try:
                result = await self._agentic_loop(task)
            finally:
                await self.mcp.disconnect()

            return result

    async def _agentic_loop(self, task: str) -> dict:
        """Core agentic loop: send messages → handle tool calls → iterate."""
        # Build tools list for OpenAI chat completions
        tool_defs = get_tool_definitions()

        # Inject persistent memory into system prompt
        memory_context = self.memory.build_context_prompt(max_memories=8)
        system_prompt = CODER_SYSTEM_PROMPT
        if memory_context:
            system_prompt += f"\n\n{memory_context}"

        # Conversation history
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"## Task from Manager Agent\n\n{task}"},
        ]

        console.print(f"[dim]Using model: {self.model}[/dim]")

        # Agentic loop — the agent thinks, calls tools, observes results, repeats
        for round_num in range(self.MAX_TOOL_ROUNDS):
            console.print(f"\n[bold yellow]── Round {round_num + 1} ──[/bold yellow]")
            _emit("round_started", {"round": round_num + 1})

            # Call gpt-4o via OpenAI-compatible API
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model=self.model,
                messages=messages,
                tools=tool_defs,
                tool_choice="auto",
            )

            choice = response.choices[0]

            # If the model wants to call tools
            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                # Add assistant message with tool calls to history
                messages.append(choice.message.model_dump())

                for tc in choice.message.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments)

                    console.print(f"  [green]→ {name}[/green]({_summarize_args(args)})")
                    _emit("tool_call", {"tool": name, "args": args})

                    output = await self._execute_tool(name, args)

                    # Show syntax-highlighted preview for file reads
                    if name == "github_read_file" and not output.startswith('{"error'):
                        _show_code_preview(args.get("path", ""), output)

                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": output,
                    })
                continue

            # Model finished (no more tool calls)
            if choice.message.content:
                text = choice.message.content
                console.print(Panel(
                    Markdown(text[:2000]),
                    title="[bold green]Coder Agent[/bold green]",
                    border_style="green",
                ))
                _emit("agent_message", {"content": text})
            break

        # Store task outcome in persistent memory
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.memory.store(
            category="task",
            key=f"task-{timestamp}",
            content=f"Task: {task[:200]} | Files: {', '.join(self.files_changed)} | PR: {self.pr_url or 'none'}",
            metadata={"files": self.files_changed, "pr_url": self.pr_url},
        )
        if self.files_changed:
            for path in self.files_changed:
                self.memory.store(
                    category="repo_structure",
                    key=f"file-{path}",
                    content=f"Modified file: {path}",
                    relevance_score=0.5,
                )

        summary = {
            "status": "complete" if self.pr_url else "in_progress",
            "files_changed": self.files_changed,
            "pr_url": self.pr_url,
            "attempt": self.attempt + 1,
        }
        console.print(Panel(
            _format_summary(summary),
            title="[bold cyan]RESULT[/bold cyan]",
            border_style="cyan",
        ))
        _emit("agent_complete", summary)
        return summary

    # ── Rejection handler ────────────────────────────────────────────

    async def handle_rejection(self, feedback: str, score: int) -> dict:
        """
        Called when the Senior Coder rejects the code.
        Fixes the specific issues raised and resubmits.
        """
        self.attempt += 1
        if self.attempt >= self.MAX_RETRIES:
            console.print("[bold red]Max retries reached. Escalating to Manager.[/bold red]")
            _emit("max_retries", {"attempts": self.attempt})
            return {"status": "escalated", "attempts": self.attempt}

        console.print(Panel(
            f"[bold red]REJECTION #{self.attempt}[/bold red]\n"
            f"Score: {score}/100\n\n{feedback}",
            title="Senior Coder Feedback",
            border_style="red",
        ))
        _emit("rejection", {"feedback": feedback, "score": score, "attempt": self.attempt})

        # Store rejection in memory so we learn from it
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.memory.store(
            category="rejection",
            key=f"rejection-{timestamp}",
            content=f"Score: {score}/100 | Feedback: {feedback[:300]}",
            metadata={"score": score, "attempt": self.attempt},
            relevance_score=1.5,  # Rejections are high-value memories
        )

        rejection_task = REJECTION_HANDLER_PROMPT.format(feedback=feedback, score=score)
        return await self.run(rejection_task)


# ── Helpers ──────────────────────────────────────────────────────────

def _summarize_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        val = str(v)
        if len(val) > 60:
            val = val[:57] + "..."
        parts.append(f"{k}={val!r}")
    return ", ".join(parts)


def _show_code_preview(path: str, content: str):
    ext = path.rsplit(".", 1)[-1] if "." in path else "text"
    lang_map = {"py": "python", "js": "javascript", "ts": "typescript", "yml": "yaml", "yaml": "yaml"}
    lang = lang_map.get(ext, ext)
    try:
        syntax = Syntax(content[:3000], lang, theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"[dim]{path}[/dim]", border_style="dim"))
    except Exception:
        console.print(f"[dim]{content[:500]}[/dim]")


def _format_summary(summary: dict) -> str:
    lines = [f"Status: {summary['status']}"]
    if summary["files_changed"]:
        lines.append(f"Files changed: {', '.join(summary['files_changed'])}")
    if summary["pr_url"]:
        lines.append(f"PR: {summary['pr_url']}")
    lines.append(f"Attempt: {summary['attempt']}")
    return "\n".join(lines)


# ── CLI entry point ──────────────────────────────────────────────────

async def main():
    if len(sys.argv) < 2:
        console.print("[red]Usage: python -m agents.coder.agent 'Fix the bug in ...'[/red]")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    agent = CoderAgent()
    result = await agent.run(task)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    asyncio.run(main())
