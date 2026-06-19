"""파이프라인 운영 로깅 — pipeline_runs 단계 기록.

03-시스템-아키텍처.md §12 (db_ops). Python 3.9 호환.
"""
from typing import Optional
import db_core


def log_start(db_path: Optional[str], run_date: str, stage: str) -> int:
    """단계 시작 기록(running). 반환: pipeline_runs.id."""
    with db_core.get_connection(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO pipeline_runs (run_date, stage, status, started_at) "
            "VALUES (?, ?, 'running', datetime('now'))", (run_date, stage))
        return cur.lastrowid


def log_finish(db_path: Optional[str], stage_id: int, status: str,
               message: str = '') -> None:
    """단계 종료 기록(completed/failed/skipped)."""
    with db_core.get_connection(db_path) as conn:
        conn.execute(
            "UPDATE pipeline_runs SET status=?, message=?, finished_at=datetime('now') "
            "WHERE id=?", (status, message[:500], stage_id))
