# lfb_sqlite_jobs.py
# Status: In Development
# Role: CRUD operations for the jobs table.
#       Tracks active job lifecycle per chat.
#
# Key Functions:
#   create_job(job_id, block_id, chat_id): Inserts new job row with status=running.
#   get_job(job_id): Returns job row or None.
#   get_job_by_block(block_id): Returns job row for a given block or None.
#   update_job_status(job_id, status, error): Updates status and optionally error.
#   set_killme(job_id): Sets killme=1 for a given job.
#   delete_job(job_id): Removes job row on completion or failure.
#   get_active_job_by_chat(chat_id): Returns most recent running job for chat.
#
# Dependencies:
#   lfb_sqlite: get_conn()
#   lfb_log: log()
#
# Dev Notes:
#   Job row is created in pipe() at submission time and deleted in outlet() on completion.
#   set_killme() is called by /kill command — checked by orchestrator after each poll.
#   Orphaned running jobs are marked failed at startup in init_db().
#
# Schema: LFB03112026A

from datetime import datetime, timezone
from lfb_sqlite import get_conn
from lfb_log import log


def _now():
    return datetime.now(timezone.utc).isoformat()


def create_job(job_id, block_id, chat_id):
    log("lfb_sqlite_jobs", f"create_job({job_id[:8]}..., block={block_id[:8]}..., chat={chat_id})")
    conn = get_conn()
    with conn:
        conn.execute(
            """INSERT INTO jobs (job_id, block_id, chat_id, status, killme, created_at)
               VALUES (?, ?, ?, 'running', 0, ?)""",
            (job_id, block_id, chat_id, _now())
        )
    conn.close()


def get_job(job_id):
    log("lfb_sqlite_jobs", f"get_job({job_id[:8]}...)")
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_job_by_block(block_id):
    log("lfb_sqlite_jobs", f"get_job_by_block({block_id[:8]}...)")
    conn = get_conn()
    row = conn.execute("SELECT * FROM jobs WHERE block_id = ?", (block_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_job_status(job_id, status, error=None):
    log("lfb_sqlite_jobs", f"update_job_status({job_id[:8]}..., status={status})")
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE jobs SET status = ?, error = ? WHERE job_id = ?",
            (status, error, job_id)
        )
    conn.close()


def set_killme(job_id):
    log("lfb_sqlite_jobs", f"set_killme({job_id[:8]}...)")
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE jobs SET killme = 1 WHERE job_id = ?",
            (job_id,)
        )
    conn.close()


def delete_job(job_id):
    log("lfb_sqlite_jobs", f"delete_job({job_id[:8]}...)")
    conn = get_conn()
    with conn:
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
    conn.close()


def get_active_job_by_chat(chat_id):
    log("lfb_sqlite_jobs", f"get_active_job_by_chat({chat_id})")
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM jobs WHERE chat_id = ? AND status = 'running' ORDER BY created_at DESC LIMIT 1",
        (chat_id,)
    ).fetchone()
    conn.close()
    result = dict(row) if row else None
    log("lfb_sqlite_jobs", f"get_active_job_by_chat → {result['job_id'][:8] if result else None}")
    return result
