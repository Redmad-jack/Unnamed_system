from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from have_some_ai.models import (
    Answer,
    Assignment,
    DrawnQuestion,
    ObservationEvent,
    Participant,
    ParticipantStatus,
    QueueStatus,
    VoiceAnswerInterpretation,
)


class MealRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_participant(
        self,
        *,
        notes: str | None = None,
        safety_flags: dict[str, Any] | None = None,
    ) -> Participant:
        participant_id = str(uuid.uuid4())
        public_code = self._next_public_code()
        flags = safety_flags or {}
        self._conn.execute(
            """
            INSERT INTO meal_participants (id, public_code, status, notes, safety_flags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                participant_id,
                public_code,
                ParticipantStatus.WAITING.value,
                notes,
                _json(flags),
            ),
        )
        self._conn.commit()
        return self.get_participant(participant_id)

    def get_participant(self, participant_id: str) -> Participant:
        row = self._conn.execute(
            "SELECT * FROM meal_participants WHERE id = ?",
            (participant_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Participant not found: {participant_id}")
        return _participant_from_row(row)

    def list_participants(self, limit: int = 50) -> list[Participant]:
        rows = self._conn.execute(
            "SELECT * FROM meal_participants ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_participant_from_row(row) for row in rows]

    def update_participant_status(self, participant_id: str, status: ParticipantStatus) -> None:
        self._conn.execute(
            """
            UPDATE meal_participants
            SET status = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (status.value, participant_id),
        )
        self._conn.commit()

    def update_safety_flags(self, participant_id: str, safety_flags: dict[str, Any]) -> None:
        self._conn.execute(
            """
            UPDATE meal_participants
            SET safety_flags = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (_json(safety_flags), participant_id),
        )
        self._conn.commit()

    def store_draws(self, participant_id: str, draws: list[DrawnQuestion]) -> None:
        for draw in draws:
            question = draw.question
            options = [
                {
                    "id": opt.id,
                    "text": opt.text,
                    "text_zh": opt.text_zh,
                    "scores": opt.scores,
                }
                for opt in question.options
            ]
            self._conn.execute(
                """
                INSERT OR IGNORE INTO meal_question_draws (
                    participant_id, module_id, question_id, question_text,
                    question_text_zh, options_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    participant_id,
                    draw.module_id,
                    question.id,
                    question.text,
                    question.text_zh,
                    _json(options),
                ),
            )
        self._conn.commit()

    def get_draws(self, participant_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM meal_question_draws
            WHERE participant_id = ?
            ORDER BY id ASC
            """,
            (participant_id,),
        ).fetchall()
        return [_row_to_dict(row) | {"options": _loads(row["options_json"])} for row in rows]

    def store_voice_interpretation(
        self,
        interpretation: VoiceAnswerInterpretation,
    ) -> VoiceAnswerInterpretation:
        try:
            cursor = self._conn.execute(
                """
                INSERT INTO meal_voice_answer_interpretations (
                    participant_id, question_id, attempt_id, transcript, detected_language,
                    stt_confidence, stt_metadata_json, inferred_option_id,
                    llm_confidence, reason_zh, reason_en, raw_llm_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interpretation.participant_id,
                    interpretation.question_id,
                    interpretation.attempt_id,
                    interpretation.transcript,
                    interpretation.detected_language,
                    interpretation.stt_confidence,
                    _json(interpretation.stt_metadata),
                    interpretation.inferred_option_id,
                    interpretation.llm_confidence,
                    interpretation.reason_zh,
                    interpretation.reason_en,
                    _json(interpretation.raw_llm_json),
                    interpretation.status,
                ),
            )
        except sqlite3.IntegrityError:
            if interpretation.attempt_id:
                existing = self.get_voice_interpretation_by_attempt(
                    interpretation.participant_id,
                    interpretation.question_id,
                    interpretation.attempt_id,
                )
                if existing is not None:
                    return existing
            raise
        self._conn.commit()
        return self.get_voice_interpretation(int(cursor.lastrowid))

    def get_voice_interpretation(self, interpretation_id: int) -> VoiceAnswerInterpretation:
        row = self._conn.execute(
            "SELECT * FROM meal_voice_answer_interpretations WHERE id = ?",
            (interpretation_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Voice interpretation not found: {interpretation_id}")
        return _voice_interpretation_from_row(row)

    def get_voice_interpretations(self, participant_id: str) -> list[VoiceAnswerInterpretation]:
        rows = self._conn.execute(
            """
            SELECT * FROM meal_voice_answer_interpretations
            WHERE participant_id = ?
            ORDER BY id ASC
            """,
            (participant_id,),
        ).fetchall()
        return [_voice_interpretation_from_row(row) for row in rows]

    def get_voice_interpretation_by_attempt(
        self,
        participant_id: str,
        question_id: str,
        attempt_id: str,
    ) -> VoiceAnswerInterpretation | None:
        row = self._conn.execute(
            """
            SELECT * FROM meal_voice_answer_interpretations
            WHERE participant_id = ? AND question_id = ? AND attempt_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (participant_id, question_id, attempt_id),
        ).fetchone()
        return _voice_interpretation_from_row(row) if row is not None else None

    def store_answers(self, participant_id: str, answers: list[Answer]) -> None:
        for answer in answers:
            self._conn.execute(
                """
                INSERT INTO meal_answers (participant_id, question_id, option_id)
                VALUES (?, ?, ?)
                ON CONFLICT(participant_id, question_id) DO UPDATE SET
                    option_id = excluded.option_id,
                    answered_at = datetime('now')
                """,
                (participant_id, answer.question_id, answer.option_id),
            )
        self._conn.commit()

    def get_answers(self, participant_id: str) -> list[Answer]:
        rows = self._conn.execute(
            """
            SELECT * FROM meal_answers
            WHERE participant_id = ?
            ORDER BY id ASC
            """,
            (participant_id,),
        ).fetchall()
        return [
            Answer(
                participant_id=row["participant_id"],
                question_id=row["question_id"],
                option_id=row["option_id"],
                answered_at=row["answered_at"],
            )
            for row in rows
        ]

    def store_observation_events(
        self,
        participant_id: str,
        events: list[ObservationEvent],
    ) -> None:
        for event in events:
            self._conn.execute(
                """
                INSERT INTO meal_observation_events (
                    participant_id, event_type, confidence, duration_ms, metadata
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    participant_id,
                    event.event_type,
                    event.confidence,
                    event.duration_ms,
                    _json(event.metadata),
                ),
            )
        self._conn.commit()

    def get_observation_events(self, participant_id: str) -> list[ObservationEvent]:
        rows = self._conn.execute(
            """
            SELECT * FROM meal_observation_events
            WHERE participant_id = ?
            ORDER BY id ASC
            """,
            (participant_id,),
        ).fetchall()
        return [
            ObservationEvent(
                participant_id=row["participant_id"],
                event_type=row["event_type"],
                confidence=float(row["confidence"]),
                duration_ms=row["duration_ms"],
                metadata=_loads(row["metadata"]),
            )
            for row in rows
        ]

    def store_assignment(self, assignment: Assignment) -> Assignment:
        self._conn.execute(
            """
            INSERT INTO meal_assignments (
                participant_id, food_code, food_label, final_food_code, final_food_label,
                ai_trace_score, relational_score, rationale_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(participant_id) DO UPDATE SET
                food_code = excluded.food_code,
                food_label = excluded.food_label,
                final_food_code = excluded.final_food_code,
                final_food_label = excluded.final_food_label,
                ai_trace_score = excluded.ai_trace_score,
                relational_score = excluded.relational_score,
                rationale_json = excluded.rationale_json,
                assigned_at = datetime('now')
            """,
            (
                assignment.participant_id,
                assignment.food_code,
                assignment.food_label,
                assignment.food_code,
                assignment.food_label,
                assignment.ai_trace_score,
                assignment.relational_score,
                _json(assignment.rationale),
            ),
        )
        self._conn.commit()

        stored = self.get_assignment(assignment.participant_id)
        self._enqueue_assignment(stored)
        return stored

    def get_assignment(self, participant_id: str) -> Assignment:
        row = self._conn.execute(
            "SELECT * FROM meal_assignments WHERE participant_id = ?",
            (participant_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Assignment not found for participant: {participant_id}")
        return Assignment(
            assignment_id=row["id"],
            participant_id=row["participant_id"],
            food_code=row["final_food_code"],
            food_label=row["final_food_label"],
            ai_trace_score=float(row["ai_trace_score"]),
            relational_score=float(row["relational_score"]),
            rationale=_loads(row["rationale_json"]),
            assigned_at=row["assigned_at"],
        )

    def list_staff_queue(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                q.*,
                p.public_code,
                p.safety_flags,
                a.final_food_code,
                a.final_food_label,
                a.ai_trace_score,
                a.relational_score,
                a.assigned_at
            FROM meal_staff_queue q
            JOIN meal_participants p ON p.id = q.participant_id
            JOIN meal_assignments a ON a.id = q.assignment_id
            ORDER BY
                CASE q.status
                    WHEN 'pending' THEN 0
                    WHEN 'preparing' THEN 1
                    WHEN 'served' THEN 2
                    ELSE 3
                END,
                q.created_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        items = []
        for row in rows:
            item = _row_to_dict(row)
            item["safety_flags"] = _loads(row["safety_flags"])
            items.append(item)
        return items

    def update_queue_item(
        self,
        queue_item_id: int,
        status: QueueStatus,
        staff_notes: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE meal_staff_queue
            SET status = ?, staff_notes = COALESCE(?, staff_notes), updated_at = datetime('now')
            WHERE id = ?
            """,
            (status.value, staff_notes, queue_item_id),
        )
        if status == QueueStatus.SERVED:
            self._conn.execute(
                """
                UPDATE meal_participants
                SET status = ?, updated_at = datetime('now')
                WHERE id = (
                    SELECT participant_id FROM meal_staff_queue WHERE id = ?
                )
                """,
                (ParticipantStatus.SERVED.value, queue_item_id),
            )
        self._conn.commit()

    def export_all(self) -> dict[str, Any]:
        tables = [
            "meal_participants",
            "meal_question_draws",
            "meal_answers",
            "meal_observation_events",
            "meal_voice_answer_interpretations",
            "meal_assignments",
            "meal_staff_queue",
        ]
        return {
            table: [
                _row_to_dict(row)
                for row in self._conn.execute(f"SELECT * FROM {table} ORDER BY 1 ASC").fetchall()
            ]
            for table in tables
        }

    def _next_public_code(self) -> str:
        row = self._conn.execute(
            """
            SELECT COALESCE(MAX(CAST(SUBSTR(public_code, 2) AS INTEGER)), 0) + 1 AS n
            FROM meal_participants
            WHERE public_code LIKE 'A%'
            """
        ).fetchone()
        return f"A{int(row['n']):03d}"

    def _enqueue_assignment(self, assignment: Assignment) -> None:
        self._conn.execute(
            """
            INSERT INTO meal_staff_queue (assignment_id, participant_id, status)
            VALUES (?, ?, ?)
            ON CONFLICT(assignment_id) DO NOTHING
            """,
            (
                assignment.assignment_id,
                assignment.participant_id,
                QueueStatus.PENDING.value,
            ),
        )
        self._conn.commit()


def _participant_from_row(row: sqlite3.Row) -> Participant:
    return Participant(
        id=row["id"],
        public_code=row["public_code"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        notes=row["notes"],
        safety_flags=_loads(row["safety_flags"]),
    )


def _voice_interpretation_from_row(row: sqlite3.Row) -> VoiceAnswerInterpretation:
    return VoiceAnswerInterpretation(
        interpretation_id=row["id"],
        participant_id=row["participant_id"],
        question_id=row["question_id"],
        attempt_id=row["attempt_id"] if "attempt_id" in row.keys() else None,
        transcript=row["transcript"],
        detected_language=row["detected_language"],
        stt_confidence=(
            float(row["stt_confidence"]) if row["stt_confidence"] is not None else None
        ),
        stt_metadata=_loads(row["stt_metadata_json"]),
        inferred_option_id=row["inferred_option_id"],
        llm_confidence=(
            float(row["llm_confidence"]) if row["llm_confidence"] is not None else None
        ),
        reason_zh=row["reason_zh"],
        reason_en=row["reason_en"],
        raw_llm_json=_loads(row["raw_llm_json"]),
        status=row["status"],
        created_at=row["created_at"],
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | None) -> Any:
    if not value:
        return {}
    return json.loads(value)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)
