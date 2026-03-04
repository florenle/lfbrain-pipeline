# lfb_sqlite_blocks.py
# Status: In Development
# Role: CRUD operations for the blocks table.
#       Each block represents one user turn: user input + assistant result.
#
# Key Functions:
#   add_block(chat_id, block_id, owui_message_id, user_content): Inserts new block, auto-assigns next seq.
#   get_block(block_id): Returns block row or None.
#   get_blocks_by_chat(chat_id): Returns all blocks for a chat ordered by seq.
#   update_block_assistant(block_id, assistant_content): Stores final LLM result.
#   upsert_block(chat_id, seq, owui_message_id, user_content, assistant_content): Insert or replace by (chat_id, seq).
#   delete_blocks_from_seq(chat_id, seq): Deletes all blocks with seq >= value.
#
# Dependencies:
#   lfb_sqlite: get_conn()
#   lfb_log: log()
#
# Dev Notes:
#   seq is auto-assigned as max(seq)+1 per chat at insert time
#   block_id is a UUID generated in pipe() at job submission time
#   owui_message_id is the OpenWebUI user message ID — used as sync key in inlet()
#   system_content is ephemeral — streamed as <think>...</think>, never stored
#
# Schema: LFB03042026A

from datetime import datetime, timezone
from lfb_sqlite import get_conn
from lfb_log import log


def _now():
    return datetime.now(timezone.utc).isoformat()


def add_block(chat_id, block_id, owui_message_id=None, user_content=None, assistant_content=None):
    log("lfb_sqlite_blocks", f"add_block({chat_id}, {block_id[:8]}...)")
    conn = get_conn()
    with conn:
        row = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM blocks WHERE chat_id = ?",
            (chat_id,)
        ).fetchone()
        next_seq = row["next_seq"]
        conn.execute(
            """INSERT INTO blocks (block_id, chat_id, seq, owui_message_id, user_content, assistant_content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (block_id, chat_id, next_seq, owui_message_id, user_content, assistant_content, _now())
        )
    conn.close()
    log("lfb_sqlite_blocks", f"add_block → seq={next_seq}")
    return next_seq


def get_block(block_id):
    log("lfb_sqlite_blocks", f"get_block({block_id[:8]}...)")
    conn = get_conn()
    row = conn.execute("SELECT * FROM blocks WHERE block_id = ?", (block_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_blocks_by_chat(chat_id):
    log("lfb_sqlite_blocks", f"get_blocks_by_chat({chat_id})")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM blocks WHERE chat_id = ? ORDER BY seq", (chat_id,)
    ).fetchall()
    conn.close()
    log("lfb_sqlite_blocks", f"get_blocks_by_chat → {len(rows)} blocks")
    return [dict(r) for r in rows]


def update_block_assistant(block_id, assistant_content):
    log("lfb_sqlite_blocks", f"update_block_assistant({block_id[:8]}...) len={len(assistant_content)}")
    conn = get_conn()
    with conn:
        conn.execute(
            "UPDATE blocks SET assistant_content = ? WHERE block_id = ?",
            (assistant_content, block_id)
        )
    conn.close()


def upsert_block(chat_id, seq, owui_message_id, user_content, assistant_content):
    log("lfb_sqlite_blocks", f"upsert_block({chat_id}, seq={seq})")
    import uuid
    conn = get_conn()
    with conn:
        conn.execute(
            """INSERT INTO blocks (block_id, chat_id, seq, owui_message_id, user_content, assistant_content, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (chat_id, seq) DO UPDATE SET
                   owui_message_id   = excluded.owui_message_id,
                   user_content      = excluded.user_content,
                   assistant_content = excluded.assistant_content""",
            (str(uuid.uuid4()), chat_id, seq, owui_message_id, user_content, assistant_content, _now())
        )
    conn.close()


def delete_blocks_from_seq(chat_id, seq):
    log("lfb_sqlite_blocks", f"delete_blocks_from_seq({chat_id}, seq>={seq})")
    conn = get_conn()
    with conn:
        conn.execute(
            "DELETE FROM blocks WHERE chat_id = ? AND seq >= ?",
            (chat_id, seq)
        )
    conn.close()
