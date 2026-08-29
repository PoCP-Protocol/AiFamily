"""In-memory `AiRunLedgerPort` for unit tests — records everything, never
fails, no DB dependency. See `domain/ai_run.py` for the record shape.
"""
from __future__ import annotations

from ..application.ports import AiRunLedgerPort
from ..domain.ai_run import AiRunRecord


class FakeAiRunLedger(AiRunLedgerPort):
    def __init__(self):
        self.records: list[AiRunRecord] = []

    async def record(self, run: AiRunRecord) -> None:
        self.records.append(run)
