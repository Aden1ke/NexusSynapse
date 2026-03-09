"""
Agent-to-Agent (A2A) Protocol for NexusSynapse.

Implements Google's A2A protocol spec for inter-agent communication.
Each agent runs an A2A server and uses the A2A client to talk to peers.

Key concepts:
- Agent Card: JSON describing agent capabilities (hosted at /.well-known/agent.json)
- Tasks: Units of work sent between agents with lifecycle (submitted → working → completed/failed)
- Artifacts: Results produced by tasks (code, reviews, deployments)

Protocol flow:
  Manager → POST /a2a (task) → Coder Agent
  Coder   → POST /a2a (task) → Senior Coder (for review)
  Senior  → POST /a2a (task) → Coder (rejection feedback)
"""

import os
import json
import uuid
import logging
import hmac
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any
from enum import Enum

import asyncio
from aiohttp import web, ClientSession

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("agents.a2a")

A2A_TOKEN = os.environ.get("A2A_SHARED_TOKEN", "")


class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass
class A2AMessage:
    """A message within an A2A task."""
    role: str              # "user" or "agent"
    parts: list[dict]      # [{"type": "text", "text": "..."}, ...]
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def text(role: str, content: str, **meta) -> "A2AMessage":
        return A2AMessage(role=role, parts=[{"type": "text", "text": content}], metadata=meta)


@dataclass
class A2AArtifact:
    """An output artifact produced by a task."""
    name: str
    parts: list[dict]
    metadata: dict = field(default_factory=dict)


@dataclass
class A2ATask:
    """A task in the A2A protocol lifecycle."""
    id: str
    status: TaskState
    messages: list[A2AMessage] = field(default_factory=list)
    artifacts: list[A2AArtifact] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": {"state": self.status.value},
            "messages": [asdict(m) for m in self.messages],
            "artifacts": [asdict(a) for a in self.artifacts],
            "metadata": self.metadata,
        }


# ── A2A Client ──────────────────────────────────────────────────────

class A2AClient:
    """
    Client for sending tasks to other agents via A2A protocol.

    Usage:
        client = A2AClient()
        result = await client.send_task(
            agent_url="http://localhost:5001",
            method="tasks/send",
            message="Review this code: ...",
            metadata={"from": "coder", "pr_url": "..."},
        )
    """

    def __init__(self):
        self._session: ClientSession | None = None

    async def _ensure_session(self):
        if not self._session:
            self._session = ClientSession()

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def _sign_payload(self, payload: bytes) -> str:
        """HMAC-SHA256 signature for authentication between agents."""
        return hmac.new(A2A_TOKEN.encode(), payload, hashlib.sha256).hexdigest()

    async def get_agent_card(self, agent_url: str) -> dict:
        """Fetch an agent's capability card."""
        await self._ensure_session()
        async with self._session.get(f"{agent_url}/.well-known/agent.json") as resp:
            return await resp.json()

    async def send_task(
        self,
        agent_url: str,
        message: str,
        task_id: str | None = None,
        metadata: dict | None = None,
    ) -> A2ATask:
        """
        Send a task to another agent (tasks/send — synchronous completion).
        Waits for the agent to finish and returns the completed task.
        """
        await self._ensure_session()
        task_id = task_id or str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "tasks/send",
            "params": {
                "id": task_id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                    "metadata": metadata or {},
                },
            },
        }

        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {A2A_TOKEN}",
            "X-A2A-Signature": self._sign_payload(body),
        }

        logger.info(f"A2A → {agent_url} | task={task_id}")
        async with self._session.post(f"{agent_url}/a2a", headers=headers, data=body) as resp:
            data = await resp.json()

        if "error" in data:
            logger.error(f"A2A error: {data['error']}")
            return A2ATask(
                id=task_id, status=TaskState.FAILED,
                messages=[A2AMessage.text("agent", f"Error: {data['error']}")],
            )

        result = data.get("result", {})
        return A2ATask(
            id=result.get("id", task_id),
            status=TaskState(result.get("status", {}).get("state", "completed")),
            messages=[
                A2AMessage(role=m["role"], parts=m["parts"], metadata=m.get("metadata", {}))
                for m in result.get("messages", [])
            ],
            artifacts=[
                A2AArtifact(name=a.get("name", ""), parts=a.get("parts", []), metadata=a.get("metadata", {}))
                for a in result.get("artifacts", [])
            ],
            metadata=result.get("metadata", {}),
        )

    async def send_task_streaming(
        self,
        agent_url: str,
        message: str,
        task_id: str | None = None,
        metadata: dict | None = None,
    ):
        """
        Send a task with streaming response (tasks/sendSubscribe).
        Yields status update events as they arrive.
        """
        await self._ensure_session()
        task_id = task_id or str(uuid.uuid4())

        payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "tasks/sendSubscribe",
            "params": {
                "id": task_id,
                "message": {
                    "role": "user",
                    "parts": [{"type": "text", "text": message}],
                    "metadata": metadata or {},
                },
            },
        }

        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {A2A_TOKEN}",
            "X-A2A-Signature": self._sign_payload(body),
            "Accept": "text/event-stream",
        }

        async with self._session.post(f"{agent_url}/a2a", headers=headers, data=body) as resp:
            async for line in resp.content:
                line = line.decode().strip()
                if line.startswith("data:"):
                    event_data = json.loads(line[5:].strip())
                    yield event_data

    async def get_task(self, agent_url: str, task_id: str) -> A2ATask:
        """Check the status of a previously submitted task."""
        await self._ensure_session()
        payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "tasks/get",
            "params": {"id": task_id},
        }
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {A2A_TOKEN}",
            "X-A2A-Signature": self._sign_payload(body),
        }
        async with self._session.post(f"{agent_url}/a2a", headers=headers, data=body) as resp:
            data = await resp.json()

        result = data.get("result", {})
        return A2ATask(
            id=result.get("id", task_id),
            status=TaskState(result.get("status", {}).get("state", "failed")),
            messages=[
                A2AMessage(role=m["role"], parts=m["parts"], metadata=m.get("metadata", {}))
                for m in result.get("messages", [])
            ],
        )

    async def cancel_task(self, agent_url: str, task_id: str) -> bool:
        """Cancel a running task on another agent."""
        await self._ensure_session()
        payload = {
            "jsonrpc": "2.0",
            "id": task_id,
            "method": "tasks/cancel",
            "params": {"id": task_id},
        }
        body = json.dumps(payload).encode()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {A2A_TOKEN}",
            "X-A2A-Signature": self._sign_payload(body),
        }
        async with self._session.post(f"{agent_url}/a2a", headers=headers, data=body) as resp:
            data = await resp.json()
        return "error" not in data


# ── A2A Server ──────────────────────────────────────────────────────

class A2AServer:
    """
    A2A protocol server that any agent can embed.

    Usage:
        server = A2AServer(
            agent_name="Senior Coder",
            agent_description="Reviews code for quality and security",
            port=5001,
            handler=my_task_handler,
        )
        await server.start()

    The handler receives an A2ATask and returns an A2ATask with results.
    """

    def __init__(
        self,
        agent_name: str,
        agent_description: str,
        port: int,
        handler,  # async callable(A2ATask) -> A2ATask
        skills: list[dict] | None = None,
    ):
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.port = port
        self.handler = handler
        self.skills = skills or []
        self.tasks: dict[str, A2ATask] = {}
        self.app = web.Application()
        self._setup_routes()

    def _setup_routes(self):
        self.app.router.add_get("/.well-known/agent.json", self._agent_card)
        self.app.router.add_post("/a2a", self._handle_a2a)

    def _verify_auth(self, request: web.Request, body: bytes) -> bool:
        """Verify the A2A shared token and HMAC signature."""
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {A2A_TOKEN}":
            return False
        sig = request.headers.get("X-A2A-Signature", "")
        expected = hmac.new(A2A_TOKEN.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)

    async def _agent_card(self, request: web.Request) -> web.Response:
        """Serve the Agent Card at /.well-known/agent.json per A2A spec."""
        card = {
            "name": self.agent_name,
            "description": self.agent_description,
            "url": f"http://localhost:{self.port}",
            "version": "1.0.0",
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
                "stateTransitionHistory": True,
            },
            "authentication": {
                "schemes": ["bearer"],
            },
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "skills": self.skills,
        }
        return web.json_response(card)

    async def _handle_a2a(self, request: web.Request) -> web.Response:
        """Handle incoming A2A JSON-RPC requests."""
        body = await request.read()

        if not self._verify_auth(request, body):
            return web.json_response(
                {"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized"}},
                status=401,
            )

        data = json.loads(body)
        method = data.get("method", "")
        params = data.get("params", {})
        req_id = data.get("id", "")

        if method == "tasks/send":
            return await self._handle_send(req_id, params)
        elif method == "tasks/get":
            return await self._handle_get(req_id, params)
        elif method == "tasks/cancel":
            return await self._handle_cancel(req_id, params)
        elif method == "tasks/sendSubscribe":
            return await self._handle_send_subscribe(req_id, params, request)
        else:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            })

    async def _handle_send(self, req_id: str, params: dict) -> web.Response:
        """Handle tasks/send — synchronous task execution."""
        task_id = params.get("id", str(uuid.uuid4()))
        msg_data = params.get("message", {})

        message = A2AMessage(
            role=msg_data.get("role", "user"),
            parts=msg_data.get("parts", []),
            metadata=msg_data.get("metadata", {}),
        )

        task = A2ATask(id=task_id, status=TaskState.SUBMITTED, messages=[message])
        self.tasks[task_id] = task

        # Execute the handler
        task.status = TaskState.WORKING
        try:
            result_task = await self.handler(task)
            self.tasks[task_id] = result_task
        except Exception as e:
            logger.error(f"A2A handler failed: {e}")
            result_task = A2ATask(
                id=task_id, status=TaskState.FAILED,
                messages=[message, A2AMessage.text("agent", f"Handler error: {e}")],
            )
            self.tasks[task_id] = result_task

        return web.json_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result_task.to_dict(),
        })

    async def _handle_get(self, req_id: str, params: dict) -> web.Response:
        """Handle tasks/get — check task status."""
        task_id = params.get("id", "")
        task = self.tasks.get(task_id)
        if not task:
            return web.json_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32001, "message": f"Task not found: {task_id}"},
            })
        return web.json_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": task.to_dict(),
        })

    async def _handle_cancel(self, req_id: str, params: dict) -> web.Response:
        """Handle tasks/cancel."""
        task_id = params.get("id", "")
        task = self.tasks.get(task_id)
        if task:
            task.status = TaskState.CANCELED
        return web.json_response({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"id": task_id, "status": {"state": "canceled"}},
        })

    async def _handle_send_subscribe(self, req_id: str, params: dict, request: web.Request) -> web.StreamResponse:
        """Handle tasks/sendSubscribe — streaming SSE response."""
        task_id = params.get("id", str(uuid.uuid4()))
        msg_data = params.get("message", {})
        message = A2AMessage(
            role=msg_data.get("role", "user"),
            parts=msg_data.get("parts", []),
            metadata=msg_data.get("metadata", {}),
        )
        task = A2ATask(id=task_id, status=TaskState.SUBMITTED, messages=[message])
        self.tasks[task_id] = task

        response = web.StreamResponse()
        response.content_type = "text/event-stream"
        await response.prepare(request)

        # Send working status
        task.status = TaskState.WORKING
        await response.write(
            f"data: {json.dumps({'type': 'status', 'task': task.to_dict()})}\n\n".encode()
        )

        try:
            result_task = await self.handler(task)
            self.tasks[task_id] = result_task
            await response.write(
                f"data: {json.dumps({'type': 'result', 'task': result_task.to_dict()})}\n\n".encode()
            )
        except Exception as e:
            error_task = A2ATask(
                id=task_id, status=TaskState.FAILED,
                messages=[message, A2AMessage.text("agent", str(e))],
            )
            self.tasks[task_id] = error_task
            await response.write(
                f"data: {json.dumps({'type': 'error', 'task': error_task.to_dict()})}\n\n".encode()
            )

        await response.write_eof()
        return response

    async def start(self):
        """Start the A2A server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"A2A Server '{self.agent_name}' listening on port {self.port}")
        return runner
