"""
GitHub MCP Tool Client for the Coder Agent.

Connects to the GitHub MCP Server (npx @modelcontextprotocol/server-github)
and exposes tools for reading files, writing code, and creating PRs.

Uses the official `mcp` Python SDK as the MCP client.
"""

import os
import json
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("coder.tools")


@dataclass
class ToolResult:
    """Standardized result from any tool call."""
    success: bool
    data: Any = None
    error: str | None = None


@dataclass
class GitHubMCPClient:
    """
    MCP client that connects to the GitHub MCP Server.

    Provides high-level methods for the Coder Agent:
    - read_file: Read a file from the repo
    - create_or_update_file: Write code to the repo
    - create_pull_request: Submit a PR for review
    - list_files: List directory contents
    """

    repo_owner: str = field(default_factory=lambda: os.environ["GITHUB_REPO_OWNER"])
    repo_name: str = field(default_factory=lambda: os.environ["GITHUB_REPO_NAME"])
    github_token: str = field(default_factory=lambda: os.environ["GITHUB_TOKEN"])
    _session: ClientSession | None = field(default=None, init=False, repr=False)
    _client_ctx: Any = field(default=None, init=False, repr=False)
    _session_ctx: Any = field(default=None, init=False, repr=False)

    def _server_params(self) -> StdioServerParameters:
        return StdioServerParameters(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={
                **os.environ,
                "GITHUB_PERSONAL_ACCESS_TOKEN": self.github_token,
            },
        )

    async def connect(self) -> None:
        """Start the GitHub MCP server and establish a session."""
        logger.info("Connecting to GitHub MCP Server...")
        self._client_ctx = stdio_client(self._server_params())
        read_stream, write_stream = await self._client_ctx.__aenter__()
        self._session_ctx = ClientSession(read_stream, write_stream)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

        tools = await self._session.list_tools()
        tool_names = [t.name for t in tools.tools]
        logger.info(f"GitHub MCP connected. Available tools: {tool_names}")

    async def disconnect(self) -> None:
        """Shut down the MCP session and server."""
        if self._session_ctx:
            await self._session_ctx.__aexit__(None, None, None)
        if self._client_ctx:
            await self._client_ctx.__aexit__(None, None, None)
        logger.info("GitHub MCP disconnected.")

    async def _call_tool(self, tool_name: str, arguments: dict) -> ToolResult:
        """Call a tool on the MCP server and return a standardized result."""
        if not self._session:
            return ToolResult(success=False, error="Not connected to MCP server")
        try:
            result = await self._session.call_tool(tool_name, arguments)
            # MCP returns content as a list of content blocks
            if result.content:
                text_parts = [
                    block.text for block in result.content
                    if hasattr(block, "text")
                ]
                combined = "\n".join(text_parts)
                # Try to parse as JSON
                try:
                    return ToolResult(success=True, data=json.loads(combined))
                except json.JSONDecodeError:
                    return ToolResult(success=True, data=combined)
            return ToolResult(success=True, data=None)
        except Exception as e:
            logger.error(f"MCP tool call failed: {tool_name} → {e}")
            return ToolResult(success=False, error=str(e))

    # ── High-Level Tool Methods ──────────────────────────────────────

    async def read_file(self, path: str, branch: str = "dev") -> ToolResult:
        """Read a file from the repo."""
        logger.info(f"Reading: {self.repo_owner}/{self.repo_name}/{path} @ {branch}")
        return await self._call_tool("get_file_contents", {
            "owner": self.repo_owner,
            "repo": self.repo_name,
            "path": path,
            "branch": branch,
        })

    async def create_or_update_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str = "feature/coder-agent",
        sha: str | None = None,
    ) -> ToolResult:
        """Create or update a file in the repo."""
        logger.info(f"Writing: {path} on branch {branch}")
        args = {
            "owner": self.repo_owner,
            "repo": self.repo_name,
            "path": path,
            "content": content,
            "message": message,
            "branch": branch,
        }
        if sha:
            args["sha"] = sha
        return await self._call_tool("create_or_update_file", args)

    async def create_pull_request(
        self,
        title: str,
        body: str,
        head: str = "feature/coder-agent",
        base: str = "dev",
    ) -> ToolResult:
        """Create a pull request."""
        logger.info(f"Creating PR: {title} ({head} → {base})")
        return await self._call_tool("create_pull_request", {
            "owner": self.repo_owner,
            "repo": self.repo_name,
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        })

    async def list_files(self, path: str = "", branch: str = "dev") -> ToolResult:
        """List files in a directory."""
        logger.info(f"Listing: {path or '/'} @ {branch}")
        return await self._call_tool("get_file_contents", {
            "owner": self.repo_owner,
            "repo": self.repo_name,
            "path": path,
            "branch": branch,
        })

    async def create_branch(self, branch: str, from_branch: str = "dev") -> ToolResult:
        """Create a new branch from an existing one."""
        logger.info(f"Creating branch: {branch} from {from_branch}")
        return await self._call_tool("create_branch", {
            "owner": self.repo_owner,
            "repo": self.repo_name,
            "branch": branch,
            "from_branch": from_branch,
        })

    async def search_code(self, query: str) -> ToolResult:
        """Search for code in the repo."""
        logger.info(f"Searching code: {query}")
        return await self._call_tool("search_code", {
            "q": f"{query} repo:{self.repo_owner}/{self.repo_name}",
        })


def get_tool_definitions() -> list[dict]:
    """
    Return OpenAI-compatible function definitions for the Coder Agent's tools.
    These are passed to Azure AI Foundry so the LLM can call them.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "github_read_file",
                "description": "Read a file from the GitHub repository. Always call this before writing code to understand existing code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to repo root, e.g. 'src/api/checkout.py'",
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch to read from. Default: 'dev'",
                            "default": "dev",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "github_create_or_update_file",
                "description": "Create or update a file in the repository with new code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path relative to repo root",
                        },
                        "content": {
                            "type": "string",
                            "description": "The full file content to write",
                        },
                        "message": {
                            "type": "string",
                            "description": "Commit message describing the change",
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch to commit to. Default: 'feature/coder-agent'",
                            "default": "feature/coder-agent",
                        },
                    },
                    "required": ["path", "content", "message"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "github_create_pull_request",
                "description": "Create a pull request to submit your code for review by the Senior Coder.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "PR title — be concise and descriptive",
                        },
                        "body": {
                            "type": "string",
                            "description": "PR description — explain what you changed and why",
                        },
                        "head": {
                            "type": "string",
                            "description": "Source branch. Default: 'feature/coder-agent'",
                            "default": "feature/coder-agent",
                        },
                        "base": {
                            "type": "string",
                            "description": "Target branch. Default: 'dev'",
                            "default": "dev",
                        },
                    },
                    "required": ["title", "body"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "github_list_files",
                "description": "List files in a directory of the repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path relative to repo root. Empty string for root.",
                            "default": "",
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch to list from. Default: 'dev'",
                            "default": "dev",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "github_search_code",
                "description": "Search for code patterns in the repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query — function names, error messages, etc.",
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]
