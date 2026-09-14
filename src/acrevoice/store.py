"""Append-only SQLite audit store.

The product claim is that every changed field keeps its question, answer, timestamp
and confirmation status.  That claim is only credible if the trail survives the
process, so events are appended to SQLite and never updated or deleted.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id          TEXT PRIMARY KEY,
    holding_id       TEXT NOT NULL,
    holding_name     TEXT NOT NULL DEFAULT '',
    application_year TEXT NOT NULL,
    language         TEXT NOT NULL DEFAULT 'de',
    status           TEXT NOT NULL,
    scheme_code      TEXT NOT NULL DEFAULT '',
    case_kind        TEXT NOT NULL DEFAULT 'correction',
    support_topic    TEXT NOT NULL DEFAULT '',
    source_cards     TEXT NOT NULL DEFAULT '[]',
    goal_step        TEXT NOT NULL DEFAULT '',
    expert_route     TEXT NOT NULL DEFAULT '{}',
    original_record  TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id    TEXT NOT NULL REFERENCES cases(case_id),
    kind       TEXT NOT NULL,
    field      TEXT,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_case ON events(case_id, event_id);

-- An append-only log stays append-only only if the database enforces it.
CREATE TRIGGER IF NOT EXISTS events_no_update
BEFORE UPDATE ON events
BEGIN
    SELECT RAISE(ABORT, 'audit events are append-only');
END;

CREATE TRIGGER IF NOT EXISTS events_no_delete
BEFORE DELETE ON events
BEGIN
    SELECT RAISE(ABORT, 'audit events are append-only');
END;
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Event:
    event_id: int
    case_id: str
    kind: str
    field: str | None
    payload: dict
    created_at: str


class AuditStore:
    """Durable case state plus an append-only event log."""

    def __init__(self, path: str | Path = "acrevoice.db"):
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        # Correct the prototype's mislabeled flower-strip scheme. The source
        # record and historical audit payloads remain untouched.
        self._conn.execute("UPDATE cases SET scheme_code = 'OER1B' WHERE scheme_code = 'OER3'")
        self._conn.commit()
        self._migrate_case_columns()

    def _migrate_case_columns(self) -> None:
        """Add columns introduced after a database was first created.

        ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so a
        pre-existing local ``acrevoice.db`` needs these added by hand.
        """
        existing = {row["name"] for row in self._conn.execute("PRAGMA table_info(cases)")}
        for column, default in (("holding_name", "''"), ("scheme_code", "''"),
                                ("case_kind", "'correction'"), ("support_topic", "''"),
                                ("source_cards", "'[]'"), ("goal_step", "''"),
                                ("expert_route", "'{}'")):
            if column not in existing:
                self._conn.execute(f"ALTER TABLE cases ADD COLUMN {column} TEXT NOT NULL DEFAULT {default}")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # -- cases ---------------------------------------------------------------

    def create_case(
        self,
        *,
        case_id: str,
        holding_id: str,
        application_year: str,
        record: dict[str, str],
        status: str,
        scheme_code: str,
        holding_name: str = "",
        language: str = "de",
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO cases (case_id, holding_id, holding_name, application_year, language,"
                " status, scheme_code, original_record, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (case_id, holding_id, holding_name, application_year, language, status, scheme_code,
                 json.dumps(record, ensure_ascii=False), now_iso()),
            )
            self._conn.commit()
        self.append(case_id, "case_imported", payload={"record": record, "status": status})

    def create_support_case(self, *, case_id: str, holding_name: str, language: str,
                            topic: str, source_cards: list[dict], record: dict[str, str]) -> None:
        """Create a navigator case without pretending the catalogue decided eligibility."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO cases (case_id, holding_id, holding_name, application_year, language, status, scheme_code, original_record, case_kind, support_topic, source_cards, goal_step, expert_route, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (case_id, record.get("holding_id", ""), holding_name, record.get("application_year", "2026"),
                 language, "needs_information", "OER2", json.dumps(record, ensure_ascii=False), "support",
                 topic, json.dumps(source_cards, ensure_ascii=False), "source_guidance_ready", "{}", now_iso()),
            )
            self._conn.commit()
        self.append(case_id, "support_request_received", payload={"topic": topic, "land": "Bayern"})
        self.append(case_id, "sources_selected", payload={"source_ids": [card["source_id"] for card in source_cards]})
        self.append(case_id, "goal_step_changed", payload={"step": "source_guidance_ready"})

    def set_goal_step(self, case_id: str, step: str) -> None:
        allowed = {
            "source_guidance_ready": {"awaiting_callback", "expert_routing"},
            "awaiting_callback": {"evidence_captured", "expert_routing"},
            "evidence_captured": {"human_review", "expert_routing"},
            "human_review": {"exported", "expert_routing"},
            "expert_routing": set(), "exported": set(),
        }
        case = self.get_case(case_id)
        if case is None or case["case_kind"] != "support":
            raise ValueError("not_a_support_goal")
        previous = case["goal_step"]
        if step not in allowed.get(previous, set()):
            raise ValueError(f"invalid_goal_transition:{previous}->{step}")
        with self._lock:
            self._conn.execute("UPDATE cases SET goal_step = ? WHERE case_id = ?", (step, case_id))
            self._conn.commit()
        self.append(case_id, "goal_step_changed", payload={"from": previous, "step": step})

    def route_to_expert(self, case_id: str, *, reason: str, question: str, assignee: str = "Farm advisory desk") -> None:
        case = self.get_case(case_id)
        if case is None or case["case_kind"] != "support":
            raise ValueError("not_a_support_goal")
        if case["goal_step"] != "expert_routing":
            self.set_goal_step(case_id, "expert_routing")
        route = {"reason": reason, "question": question, "assignee": assignee, "routed_at": now_iso()}
        with self._lock:
            self._conn.execute("UPDATE cases SET expert_route = ? WHERE case_id = ?", (json.dumps(route, ensure_ascii=False), case_id))
            self._conn.commit()
        self.append(case_id, "expert_routed", payload=route)

    def set_status(self, case_id: str, status: str) -> None:
        """Case status is a projection of the log; the log itself stays immutable.

        Entering ``call_in_progress`` reserves the case's one call slot, so
        that transition is a conditional update guarded by the lock, not a
        blind write: two threads racing to start a call on the same case must
        not both succeed (see ``begin_call``, which guards the same state for
        callers that reserve a slot before doing any work).
        """
        with self._lock:
            if status == "call_in_progress":
                changed = self._conn.execute(
                    "UPDATE cases SET status = ? WHERE case_id = ? "
                    "AND status NOT IN ('call_in_progress', 'closed')",
                    (status, case_id),
                ).rowcount
                self._conn.commit()
                if not changed:
                    raise ValueError("call_not_available")
            else:
                self._conn.execute("UPDATE cases SET status = ? WHERE case_id = ?", (status, case_id))
                self._conn.commit()
        self.append(case_id, "status_changed", payload={"status": status})

    def get_case(self, case_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
            if row is None:
                return None
            case = dict(row)
        case["original_record"] = json.loads(case["original_record"])
        case["source_cards"] = json.loads(case["source_cards"])
        case["expert_route"] = json.loads(case["expert_route"])
        return case

    def list_cases(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM cases ORDER BY created_at DESC").fetchall()
        out = []
        for row in rows:
            case = dict(row)
            case["original_record"] = json.loads(case["original_record"])
            case["source_cards"] = json.loads(case["source_cards"])
            case["expert_route"] = json.loads(case["expert_route"])
            out.append(case)
        return out

    # -- events --------------------------------------------------------------

    def append(self, case_id: str, kind: str, *, field: str | None = None, payload: dict) -> Event:
        with self._lock:
            created_at = now_iso()
            cur = self._conn.execute(
                "INSERT INTO events (case_id, kind, field, payload, created_at) VALUES (?,?,?,?,?)",
                (case_id, kind, field, json.dumps(payload, ensure_ascii=False), created_at),
            )
            self._conn.commit()
            return Event(cur.lastrowid, case_id, kind, field, payload, created_at)

    def begin_call(self, case_id: str, *, payload: dict) -> Event:
        """Reserve an attempt before queuing work, including across store connections."""
        with self._lock:
            with self._conn:
                changed = self._conn.execute(
                    "UPDATE cases SET status = 'call_in_progress' WHERE case_id = ? "
                    "AND status NOT IN ('call_in_progress', 'closed')", (case_id,),
                ).rowcount
                if not changed:
                    raise ValueError("call_not_available")
                created_at = now_iso()
                self._conn.execute(
                    "INSERT INTO events (case_id, kind, payload, created_at) VALUES (?,?,?,?)",
                    (case_id, "status_changed", '{"status":"call_in_progress"}', created_at),
                )
                cur = self._conn.execute(
                    "INSERT INTO events (case_id, kind, payload, created_at) VALUES (?,?,?,?)",
                    (case_id, "call_started", json.dumps(payload, ensure_ascii=False), created_at),
                )
            return Event(cur.lastrowid, case_id, "call_started", None, payload, created_at)

    def events(self, case_id: str, *, kind: str | None = None) -> list[Event]:
        sql = "SELECT * FROM events WHERE case_id = ?"
        args: list[object] = [case_id]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        with self._lock:
            rows = self._conn.execute(sql + " ORDER BY event_id", args).fetchall()
        return [
            Event(r["event_id"], r["case_id"], r["kind"], r["field"],
                  json.loads(r["payload"]), r["created_at"])
            for r in rows
        ]

    def timeline(self, case_id: str) -> list[dict]:
        """Human-readable evidence trail for the adviser and the export."""
        return [
            {"at": e.created_at, "event": e.kind, "field": e.field,
             **e.payload, "evidence_id": e.event_id}
            for e in self.events(case_id)
        ]
