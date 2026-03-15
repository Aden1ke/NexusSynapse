"""
Builder Agent — The Coder.

Runs as an A2A server on CODER_AGENT_URL (default localhost:5002).
Receives tasks from the Manager via POST /code, reads existing code
using GitHub MCP, writes fixes with gpt-4o, creates PRs, then
returns the result to the Manager for Senior Coder review.

Usage:
    python -m agents.coder.agent                          # Start A2A server
    python -m agents.coder.agent "Fix the login bug"      # One-shot CLI mode
"""

import os
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent.parent.parent / ".env")
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone

import requests
from openai import AzureOpenAI
from opentelemetry import trace
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

from agents.coder.tools import GitHubMCPClient, get_tool_definitions, ToolResult
from agents.memory import AgentMemory


logger = logging.getLogger("builder.agent")
tracer = trace.get_tracer("nexussynapse.builder")
console = Console(force_terminal=True)

# A2A config
A2A_TOKEN        = os.environ.get("A2A_SHARED_TOKEN", "")
SENIOR_CODER_URL = os.environ.get("SENIOR_CODER_URL", "http://localhost:5001")

# ── Event bus ───────────────────────────────────────────────────────

_event_listeners: list = []

def on_agent_event(callback):
    _event_listeners.append(callback)

def _emit(event_type: str, data: dict):
    event = {"type": event_type, "timestamp": datetime.now(timezone.utc).isoformat(), **data}
    for listener in _event_listeners:
        try:
            listener(event)
        except Exception:
            pass


# ── System prompt ────────────────────────────────────────────────────

CODER_SYSTEM_PROMPT = """You are the Builder Agent — an expert Python developer in the NexusSynapse multi-agent system.

Your job is to receive a coding task from the Manager Agent, read the relevant files from the GitHub repository, write the solution, push it to a feature branch, and create a Pull Request.

WORKFLOW — follow these steps in order:
1. Use github_list_files to explore the repository structure
2. Use github_read_file to read relevant existing files
3. Write the complete solution code
4. Use github_create_or_update_file to push your code to the repository (branch: feature/coder-agent)
5. Use github_create_pull_request to create a PR from feature/coder-agent to main

IMPORTANT RULES:
- You MUST always write and push actual code — never just analyze or explain
- You MUST call github_create_or_update_file to save your code
- You MUST call github_create_pull_request to create the PR
- Write complete, production-ready Python code with docstrings
- Handle edge cases and errors properly
- Follow PEP8 style
- Never leave placeholder comments like "# TODO" or "pass"

If the task is to fix a bug, write the complete fixed file.
If the task is to create a new feature, write all necessary files.
Always finish by creating a Pull Request.
"""


class BuilderAgent:
    """
    Autonomous Builder Agent powered by Azure AI Foundry + GitHub MCP.
    Receives tasks via POST /code, writes code, creates PRs.
    """

    MAX_TOOL_ROUNDS = 15

    def __init__(self):
        conn_str = os.environ["PROJECT_CONNECTION_STRING"]
        api_key  = os.environ["AZURE_API_KEY"]
        self.model = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o")

        endpoint = conn_str.split("/api/")[0] if "/api/" in conn_str else conn_str

        self.openai_client = AzureOpenAI(
            azure_endpoint = endpoint,
            api_key        = api_key,
            api_version    = "2025-01-01-preview",
        )

        self.mcp    = GitHubMCPClient()
        self.memory = AgentMemory("coder")

        # State (reset per task)
        self.files_changed: list[str] = []
        self.pr_url:   str | None = None
        self.last_code: str | None = None

    def _reset_state(self):
        self.files_changed = []
        self.pr_url        = None
        self.last_code     = None

    # ── Tool dispatch ────────────────────────────────────────────────

    async def _execute_tool(self, name: str, arguments: dict) -> str:
        dispatch = {
            "github_read_file": lambda: self.mcp.read_file(
                arguments["path"], arguments.get("branch")
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
                arguments.get("base", "main"),
            ),
            "github_list_files": lambda: self.mcp.list_files(
                arguments.get("path", ""), arguments.get("branch")
            ),
            "github_search_code": lambda: self.mcp.search_code(
                arguments["query"]
            ),
        }

        handler = dispatch.get(name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {name}"})

        result: ToolResult = await handler()

        if name == "github_create_or_update_file" and result.success:
            path = arguments["path"]
            if path not in self.files_changed:
                self.files_changed.append(path)
            self.last_code = arguments["content"]
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
        """Execute the full builder workflow. Returns Manager-compatible result dict."""
        with tracer.start_as_current_span("builder_agent.run") as span:
            span.set_attribute("task", task)

            console.print(Panel(
                f"[bold cyan]BUILDER AGENT ACTIVATED[/bold cyan]\n\n{task}",
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
        tool_defs = get_tool_definitions()

        memory_context = self.memory.build_context_prompt(max_memories=8)
        system_prompt  = CODER_SYSTEM_PROMPT
        if memory_context:
            system_prompt += f"\n\n{memory_context}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": (
                f"## Task from Manager Agent\n\n{task}\n\n"
                f"Remember: you MUST write actual code and push it using "
                f"github_create_or_update_file, then create a PR with "
                f"github_create_pull_request. Do not just analyze."
            )},
        ]

        console.print(f"[dim]Using model: {self.model}[/dim]")

        for round_num in range(self.MAX_TOOL_ROUNDS):
            console.print(f"\n[bold yellow]-- Round {round_num + 1} --[/bold yellow]")
            _emit("round_started", {"round": round_num + 1})

            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model    = self.model,
                messages = messages,
                tools    = tool_defs,
                tool_choice = "auto",
            )

            choice = response.choices[0]

            if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
                messages.append(choice.message.model_dump())

                for tc in choice.message.tool_calls:
                    name = tc.function.name
                    args = json.loads(tc.function.arguments)

                    console.print(f"  [green]-> {name}[/green]({_summarize_args(args)})")
                    _emit("tool_call", {"tool": name, "args": args})

                    output = await self._execute_tool(name, args)

                    if name == "github_read_file" and not output.startswith('{"error'):
                        _show_code_preview(args.get("path", ""), output)

                    messages.append({
                        "role":        "tool",
                        "tool_call_id": tc.id,
                        "content":     output,
                    })
                continue

            if choice.message.content:
                text = choice.message.content
                console.print(Panel(
                    Markdown(text[:2000]),
                    title="[bold green]Builder Agent[/bold green]",
                    border_style="green",
                ))
                _emit("agent_message", {"content": text})
            break

        # If no code was written, generate it directly without tools
        if not self.last_code:
            console.print("[yellow]No code pushed via tools — generating directly...[/yellow]")
            self.last_code = await self._generate_code_directly(task)

        # Save to memory
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.memory.store(
            category = "task",
            key      = f"task-{timestamp}",
            content  = f"Task: {task[:200]} | Files: {', '.join(self.files_changed)} | PR: {self.pr_url or 'none'}",
            metadata = {"files": self.files_changed, "pr_url": self.pr_url},
        )

        return {
            "status":        "submitted",
            "code":          self.last_code or "",
            "pr_url":        self.pr_url or "",
            "files_changed": self.files_changed,
        }

    async def _generate_code_directly(self, task: str) -> str:
        """
        Fallback: generate code directly via LLM when MCP tool calls
        don't produce any file writes.
        """
        try:
            response = await asyncio.to_thread(
                self.openai_client.chat.completions.create,
                model    = self.model,
                messages = [
                    {"role": "system", "content": (
                        "You are an expert Python developer. Write complete, "
                        "production-ready Python code. Return ONLY the code — "
                        "no explanation, no markdown fences."
                    )},
                    {"role": "user", "content": (
                        f"Write Python code to complete this task:\n\n{task}\n\n"
                        "Requirements:\n"
                        "- Complete implementation, no placeholders or 'pass'\n"
                        "- Include docstrings\n"
                        "- Handle edge cases\n"
                        "- Follow PEP8"
                    )},
                ],
                max_tokens = 1500,
            )
            code = response.choices[0].message.content.strip()
            # Strip markdown fences if present
            if code.startswith("```"):
                lines = code.split("\n")
                code  = "\n".join(lines[1:])
            if code.endswith("```"):
                code = "\n".join(code.split("\n")[:-1])
            console.print("[green]Direct code generation successful[/green]")
            return code
        except Exception as e:
            console.print(f"[red]Direct generation failed: {e}[/red]")
            return f"# Auto-generated for: {task}\n# Manual implementation required\ndef solution():\n    raise NotImplementedError('{task}')\n"


# ── A2A Server ──────────────────────────────────────────────────────

def create_a2a_server(agent: BuilderAgent):
    from flask import Flask, request as flask_request, jsonify

    app = Flask(__name__)

    def verify_a2a_token():
        auth = flask_request.headers.get("Authorization", "")
        return auth == f"Bearer {A2A_TOKEN}"

    @app.route("/.well-known/agent.json", methods=["GET"])
    def agent_card():
        return jsonify({
            "name":        "Builder Agent",
            "version":     "1.0.0",
            "description": "The Coder — reads existing code, writes fixes, creates PRs via GitHub MCP.",
            "endpoint":    "/code",
            "port":        5002,
            "capabilities": ["code_generation", "pr_creation", "persistent_memory"],
        })

    @app.route("/code", methods=["POST"])
    def handle_code_task():
        """
        Receive a coding task from the Manager Agent via A2A.
        Expected JSON: {"task": "Fix the login bug..."}
        Returns: {"status": "submitted", "code": "...", "pr_url": "..."}

        NOTE: Manager handles the Senior Coder review loop.
        Coder just writes code and returns — no internal review loop.
        """
        if not verify_a2a_token():
            return jsonify({"error": "Unauthorized"}), 403

        data = flask_request.get_json()
        if not data or "task" not in data:
            return jsonify({"error": "'task' field is required"}), 400

        task = data["task"]
        agent._reset_state()

        loop = asyncio.new_event_loop()
        try:
            coder_result = loop.run_until_complete(agent.run(task))
        finally:
            loop.close()

        # Return directly to Manager — Manager handles Senior Coder review
        return jsonify(coder_result)

    @app.route("/health", methods=["GET"])
    def health():
        memory_count = len(agent.memory.recall(limit=100))
        return jsonify({
            "status":         "healthy",
            "agent":          "Builder Agent",
            "memory_entries": memory_count,
        })

    return app


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
    ext      = path.rsplit(".", 1)[-1] if "." in path else "text"
    lang_map = {"py": "python", "js": "javascript", "ts": "typescript",
                "yml": "yaml", "yaml": "yaml", "html": "html", "css": "css"}
    lang = lang_map.get(ext, ext)
    try:
        syntax = Syntax(content[:3000], lang, theme="monokai", line_numbers=True)
        console.print(Panel(syntax, title=f"[dim]{path}[/dim]", border_style="dim"))
    except Exception:
        console.print(f"[dim]{content[:500]}[/dim]")


# ── Entry point ──────────────────────────────────────────────────────

async def main():
    if len(sys.argv) >= 2 and not sys.argv[1].startswith("--"):
        task  = " ".join(sys.argv[1:])
        agent = BuilderAgent()
        result = await agent.run(task)
        print(json.dumps(result, indent=2))
    else:
        port  = 5002
        agent = BuilderAgent()
        app   = create_a2a_server(agent)

        console.print(Panel(
            f"[bold cyan]BUILDER AGENT A2A SERVER[/bold cyan]\n\n"
            f"Listening on port {port}\n"
            f"Agent card: http://localhost:{port}/.well-known/agent.json\n"
            f"Code endpoint: POST http://localhost:{port}/code\n"
            f"Memory entries: {len(agent.memory.recall(limit=100))}",
            border_style="cyan",
            title="NexusSynapse",
        ))

        app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
    asyncio.run(main())