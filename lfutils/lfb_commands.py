# lfb_commands.py
# Status: In Development
# Role: Handles slash commands entered by the user in chat.
#
# Key Functions:
#   handle_command(command, chat_id, api_key): Dispatches slash commands, yields response lines.
#   _cmd_info(parts, chat_id): Returns one-line chat info including docs for current or specified chat.
#   _cmd_load(parts, chat_id): Yields summary line then fenced JSON of full chat. Durable.
#   _cmd_lsc(chat_id): Lists all chats, one line each.
#   _cmd_kill(parts): Sends kill signal to a job.
#
# Dependencies:
#   lfb_sqlite: get_chat(), list_chats()
#   lfb_sqlite_blocks: get_blocks_by_chat()
#   lfb_sqlite_docs: get_docs_by_chat()
#   lfb_sqlite_jobs: set_killme()
#   lfb_log: log()
#
# Dev Notes:
#   Called from pipe() in lfbrain.py — pipe() owns block creation for the command turn itself.
#   These functions only yield output — pipe() writes user_content + assistant_content to DB.
#   /load JSON is a fenced code block in assistant response — durable, survives branch reconciliation.
#   Slash command blocks are filtered from /load JSON output.
#   assistant_content in DB contains raw <think>...</think> blocks — stripped in /load output.
#
# Schema: LFB03052026B

import json
import re
from lfb_sqlite import get_chat, list_chats
from lfb_sqlite_blocks import get_blocks_by_chat
from lfb_sqlite_docs import get_docs_by_chat
from lfb_sqlite_jobs import set_killme
from lfb_log import log


def _fmt_dt(iso_str: str | None) -> str:
    if not iso_str:
        return "?"
    try:
        from datetime import datetime, timezone, timedelta
        EST = timezone(timedelta(hours=-5))
        dt = datetime.fromisoformat(iso_str).astimezone(EST)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str


def _strip_think(content: str) -> str:
    return re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()


def handle_command(command: str, chat_id: str, api_key: str = ""):
    log("lfb_commands", f"handle_command({command}, chat_id={chat_id})")
    parts = command.strip().split()
    cmd = parts[0].lower()

    if cmd == "/info":
        yield from _cmd_info(parts, chat_id)
        return

    if cmd == "/load":
        yield from _cmd_load(parts, chat_id)
        return

    if cmd == "/lsc":
        yield from _cmd_lsc(chat_id)
        return

    if cmd == "/kill":
        yield from _cmd_kill(parts)
        return

    log("lfb_commands", f"unknown command: {cmd}")
    yield f"Unknown command: {command}\n"
    yield "Available commands: /info, /load, /lsc, /kill\n"


def _cmd_info(parts: list, chat_id: str):
    target_id = parts[1] if len(parts) > 1 else chat_id
    log("lfb_commands", f"_cmd_info(target={target_id})")
    chat = get_chat(target_id)
    if not chat:
        yield f"No chat found for ID: {target_id}\n"
        return
    title = chat.get("title") or "Untitled"
    created = _fmt_dt(chat.get("created_at"))
    modified = _fmt_dt(chat.get("last_updated"))
    description = chat.get("description") or ""
    summary = chat.get("summary") or ""
    docs = get_docs_by_chat(target_id)
    docs_str = ", ".join(d["filename"] for d in docs) if docs else "none"
    yield (
        f"Chat {target_id} — Title: {title} · Created: {created} · "
        f"Modified: {modified} · Description: {description} · Summary: {summary} · Docs: {docs_str}"
    )


def _cmd_load(parts: list, chat_id: str):
    if len(parts) < 2:
        yield "Usage: /load <chat_id>\n"
        return
    target_id = parts[1]
    log("lfb_commands", f"_cmd_load(target={target_id})")

    chat = get_chat(target_id)
    if not chat:
        yield f"No chat found for ID: {target_id}\n"
        return

    blocks = get_blocks_by_chat(target_id)
    filtered_blocks = []
    for b in blocks:
        user = b.get("user_content") or ""
        if not user.startswith("/") or user.startswith("/load"):
            filtered_blocks.append({
                "seq": b["seq"],
                "user": user,
                "assistant": _strip_think(b.get("assistant_content") or ""),
            })

    title = chat.get("title") or "Untitled"
    description = chat.get("description") or ""

    payload = {
        "chat_id": target_id,
        "title": title,
        "description": description,
        "summary": chat.get("summary") or "",
        "created_at": chat.get("created_at") or "",
        "last_updated": chat.get("last_updated") or "",
        "blocks": filtered_blocks,
    }

    yield (
        f"Successfully loaded chat {target_id} — Title: {title} · "
        f"Blocks: {len(filtered_blocks)} · Description: {description}\n\n"
    )
    yield f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```"


def _cmd_lsc(chat_id: str):
    log("lfb_commands", "_cmd_lsc()")
    chats = list_chats()
    if not chats:
        yield "No chats found.\n"
        return
    for c in chats:
        yield (
            f"{c['chat_id']} · Title: {c.get('title') or 'Untitled'} · "
            f"Modified: {_fmt_dt(c.get('last_updated'))} · Description: {c.get('description') or ''}\n"
        )


def _cmd_kill(parts: list):
    if len(parts) < 2:
        yield "Usage: /kill <job_id>\n"
        return
    job_id = parts[1]
    log("lfb_commands", f"_cmd_kill(job_id={job_id})")
    set_killme(job_id)
    yield f"Kill signal sent to job {job_id}"
