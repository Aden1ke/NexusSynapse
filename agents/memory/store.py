"""
Shared Agent Memory Store.

Persistent memory layer for all NexusSynapse agents.
Stores lessons learned, code patterns, past reviews, and task context
so agents build knowledge across sessions — since gpt-4o has no built-in memory.

Storage: SQLite (zero-config, single file, survives restarts).
"""

import json
import sqlite3
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agents.memory")

DB_PATH = os.environ.get(
    "AGENT_MEMORY_DB",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "agent_memory.db"),
)


@dataclass
class MemoryEntry:
    """A single memory record."""
    id: int | None
    agent_role: str          # "coder", "senior_coder", "manager", "deployer"
    category: str            # "pattern", "review", "rejection", "task", "repo_structure"
    key: str                 # short identifier, e.g. "auth-bug-fix-pattern"
    content: str             # the actual memory content
    metadata: dict = field(default_factory=dict)
    relevance_score: float = 1.0
    created_at: str = ""
    updated_at: str = ""


class AgentMemory:
    """
    Shared persistent memory for all NexusSynapse agents.

    Each agent reads/writes memories tagged with its role.
    Agents can also query OTHER agents' memories for cross-role learning.

    Usage:
        memory = AgentMemory("coder")
        memory.store("pattern", "auth-fix", "Always check token expiry before validation")
        results = memory.recall("auth", limit=5)
        context = memory.build_context_prompt()  # inject into system prompt
    """

    def __init__(self, agent_role: str):
        self.agent_role = agent_role
        self._ensure_db()

    def _ensure_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_role TEXT NOT NULL,
                category TEXT NOT NULL,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                relevance_score REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(agent_role, category, key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_role ON memories(agent_role)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category)
        """)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Write ────────────────────────────────────────────────────────

    def store(
        self,
        category: str,
        key: str,
        content: str,
        metadata: dict | None = None,
        relevance_score: float = 1.0,
    ) -> MemoryEntry:
        """Store or update a memory. Upserts on (agent_role, category, key)."""
        now = self._now()
        meta_json = json.dumps(metadata or {})
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            """
            INSERT INTO memories (agent_role, category, key, content, metadata, relevance_score, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_role, category, key) DO UPDATE SET
                content = excluded.content,
                metadata = excluded.metadata,
                relevance_score = excluded.relevance_score,
                updated_at = excluded.updated_at
            """,
            (self.agent_role, category, key, content, meta_json, relevance_score, now, now),
        )
        conn.commit()
        row_id = conn.execute(
            "SELECT id FROM memories WHERE agent_role=? AND category=? AND key=?",
            (self.agent_role, category, key),
        ).fetchone()[0]
        conn.close()

        logger.info(f"Memory stored: [{self.agent_role}] {category}/{key}")
        return MemoryEntry(
            id=row_id, agent_role=self.agent_role, category=category,
            key=key, content=content, metadata=metadata or {},
            relevance_score=relevance_score, created_at=now, updated_at=now,
        )

    # ── Read ─────────────────────────────────────────────────────────

    def recall(
        self,
        query: str = "",
        category: str | None = None,
        include_other_roles: bool = False,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """
        Search memories by keyword match on key/content.
        By default only returns this agent's memories.
        Set include_other_roles=True to search across all agents.
        """
        conn = sqlite3.connect(DB_PATH)
        conditions = []
        params: list[Any] = []

        if not include_other_roles:
            conditions.append("agent_role = ?")
            params.append(self.agent_role)

        if category:
            conditions.append("category = ?")
            params.append(category)

        if query:
            conditions.append("(key LIKE ? OR content LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT id, agent_role, category, key, content, metadata, relevance_score, created_at, updated_at "
            f"FROM memories {where} ORDER BY relevance_score DESC, updated_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        conn.close()

        return [
            MemoryEntry(
                id=r[0], agent_role=r[1], category=r[2], key=r[3],
                content=r[4], metadata=json.loads(r[5]),
                relevance_score=r[6], created_at=r[7], updated_at=r[8],
            )
            for r in rows
        ]

    def recall_by_role(self, role: str, limit: int = 5) -> list[MemoryEntry]:
        """Recall memories from a specific other agent's role."""
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute(
            "SELECT id, agent_role, category, key, content, metadata, relevance_score, created_at, updated_at "
            "FROM memories WHERE agent_role = ? ORDER BY relevance_score DESC, updated_at DESC LIMIT ?",
            (role, limit),
        ).fetchall()
        conn.close()
        return [
            MemoryEntry(
                id=r[0], agent_role=r[1], category=r[2], key=r[3],
                content=r[4], metadata=json.loads(r[5]),
                relevance_score=r[6], created_at=r[7], updated_at=r[8],
            )
            for r in rows
        ]

    # ── Delete ───────────────────────────────────────────────────────

    def forget(self, category: str, key: str) -> bool:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.execute(
            "DELETE FROM memories WHERE agent_role=? AND category=? AND key=?",
            (self.agent_role, category, key),
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    # ── Context builder ──────────────────────────────────────────────

    def build_context_prompt(self, max_memories: int = 8) -> str:
        """
        Build a context block to inject into the agent's system prompt.
        Pulls the most relevant memories so gpt-4o has persistent knowledge.
        """
        memories = self.recall(limit=max_memories)
        if not memories:
            return ""

        lines = ["## Your Persistent Memory (from previous sessions)\n"]
        for m in memories:
            lines.append(f"- **[{m.category}] {m.key}**: {m.content}")

        # Also check if other roles have useful memories
        other_roles = {"coder", "senior_coder", "manager", "deployer"} - {self.agent_role}
        cross_role = []
        for role in other_roles:
            role_memories = self.recall_by_role(role, limit=3)
            for m in role_memories:
                cross_role.append(f"- **[{m.agent_role}/{m.category}] {m.key}**: {m.content}")

        if cross_role:
            lines.append("\n### Shared Team Knowledge")
            lines.extend(cross_role[:6])

        return "\n".join(lines)
