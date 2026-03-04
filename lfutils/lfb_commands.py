# lfb_commands.py
# Status: In Development
# Role: Handles slash commands entered by the user in chat.
#
# Key Functions:
#   handle_command(command, chat_id, api_key): Dispatches slash commands, yields response lines.
#   _cmd_info(parts, chat_id): Returns one-line chat info for current or specified chat.
#   _cmd_load(parts, chat_id): Streams full chat JSON in <think>, yields durable summary line.
#   _cmd_lsc(chat_id): Lists all chats, one line each.
#   _cmd_kill(parts): Sends kill signal to a job.
#
# Dependencies:
#   lfb_sqlite: get_chat(), list_chats()
#   lfb_sqlite_blocks: get_blocks_by_chat()
#   lfb_sqlite_jobs: set_killme()
#   lfb_log: log()
#
# Dev Notes:
#   Called from pipe() in lfbrain.py — pipe() owns block creation for the command turn itself.
#   These functions only yield output — pipe() writes user_content + assistant_content to DB.
#   /load JSON is yielded inside <think>...</think> — ephemeral, not stored.
#   /load visible response line is stored as assistant_content — survives branch reconciliation.
#   Slash command blocks are filtered from /load JSON output.
#
# Schema: LFB03042026A

import json
from lfb_sqlite import get_chat, list_chats
from lfb_sqlite_blocks import get_blocks_by_chat
from lfb_sqlite_jobs import set_killme
from lfb_log import log


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
    created = chat.get("created_at") or "?"
    modified = chat.get("last_updated") or "?"
    description = chat.get("description") or ""
    summary = chat.get("summary") or ""
    yield (
        f"Chat {target_id} — Title: {title} · Created: {created} · "
        f"Modified: {modified} · Description: {description} · Summary: {summary}"
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
    filtered_blocks = [
        {"seq": b["seq"], "user": b.get("user_content") or "", "assistant": b.get("assistant_content") or ""}
        for b in blocks
        if not (b.get("user_content") or "").startswith("/")
    ]

    payload = {
        "chat_id": target_id,
        "title": chat.get("title") or "Untitled",
        "description": chat.get("description") or "",
        "summary": chat.get("summary") or "",
        "created_at": chat.get("created_at") or "",
        "last_updated": chat.get("last_updated") or "",
        "blocks": filtered_blocks,
    }

    yield "<think>\n"
    yield json.dumps(payload, indent=2, ensure_ascii=False)
    yield "\n</think>\n"

    title = chat.get("title") or "Untitled"
    yield (
        f"Successfully loaded chat {target_id} — Title: {title} · "
        f"Blocks: {len(filtered_blocks)} · Description: {chat.get('description') or ''}"
    )


def _cmd_lsc(chat_id: str):
    log("lfb_commands", "_cmd_lsc()")
    chats = list_chats()
    if not chats:
        yield "No chats found.\n"
        return
    for c in chats:
        yield (
            f"{c['chat_id']} · Title: {c.get('title') or 'Untitled'} · "
            f"Modified: {c.get('last_updated') or '?'} · Description: {c.get('description') or ''}\n"
        )


def _cmd_kill(parts: list):
    if len(parts) < 2:
        yield "Usage: /kill <job_id>\n"
        return
    job_id = parts[1]
    log("lfb_commands", f"_cmd_kill(job_id={job_id})")
    set_killme(job_id)
    yield f"Kill signal sent to job {job_id}"
