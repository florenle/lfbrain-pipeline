# lfb_commands.py
# Status: In Development
# Role: Handles slash commands entered by the user in chat.
#
# Key Functions:
#   handle_command(command, chat_id, api_key): Dispatches slash commands, yields response lines.
#   _cmd_info(chat_id): Returns chat_id, title, summary, docs.
#   _cmd_load_as_one(parts, chat_id, api_key): Streams full source chat history as single assistant block.
#   _cmd_load_as_history(parts, chat_id, api_key): Appends source blocks individually into current chat.
#
# Dependencies:
#   lfb_sqlite: get_chat()
#   lfb_sqlite_docs: get_docs_by_chat()
#   lfb_sqlite_blocks: get_blocks_by_chat(), add_block()
#   lfb_owui_api: rewrite_chat_history()
#   lfb_log: log()
#
# Dev Notes:
#   Called from pipe() in lfbrain.py - pipe() owns block creation for the command turn itself.
#   These functions only yield output - pipe() writes user_content + assistant_content to DB.
#   api_key: OpenWebUI pipelines API key (Valve), used by rewrite_chat_history().
#   rewrite_chat_history() called only by /loadAsHistory and /rmb - not /loadAsOne or /info.
#   /loadAsOne and /info: OpenWebUI records response natively, no rewrite needed.
#
# /loadAsOne [-v] [chat_id]: streams full source chat history as single assistant block.
# /loadAsHistory [-v] [chat_id]: appends source blocks individually, rewrites OpenWebUI history.

import uuid
from lfb_sqlite import get_chat
from lfb_sqlite_docs import get_docs_by_chat
from lfb_sqlite_blocks import get_blocks_by_chat, add_block
from lfb_owui_api import rewrite_chat_history
from lfb_log import log


def handle_command(command: str, chat_id: str, api_key: str = ""):
    log("lfb_commands", f"handle_command({command}, chat_id={chat_id})")
    parts = command.strip().split()
    cmd = parts[0].lower()

    if cmd == "/info":
        yield from _cmd_info(chat_id)
        return

    if cmd == "/loadasone":
        yield from _cmd_load_as_one(parts, chat_id, api_key)
        return

    if cmd == "/loadashistory":
        yield from _cmd_load_as_history(parts, chat_id, api_key)
        return

    log("lfb_commands", f"unknown command: {cmd}")
    yield f"Unknown command: {command}\n"
    yield "Available commands: /info, /loadAsOne, /loadAsHistory\n"


def _cmd_info(chat_id: str):
    log("lfb_commands", f"_cmd_info({chat_id})")
    chat = get_chat(chat_id)
    if not chat:
        yield f"No chat found for ID: {chat_id}\n"
        return
    title = chat.get("title") or "Untitled"
    summary = chat.get("summary") or title
    docs = get_docs_by_chat(chat_id)
    docs_str = ", ".join(d["filename"] for d in docs) if docs else "none"
    yield f"**Chat ID:** {chat_id}\n"
    yield f"**Title:** {title}\n"
    yield f"**Summary:** {summary}\n"
    yield f"**Docs:** {docs_str}\n"


def _parse_load_args(parts: list, current_chat_id: str):
    verbose = False
    target_chat_id = current_chat_id
    args = parts[1:]
    if args and args[0] == "-v":
        verbose = True
        args = args[1:]
    if args:
        target_chat_id = args[0]
    return verbose, target_chat_id


def _cmd_load_as_one(parts: list, chat_id: str, api_key: str):
    verbose, target_chat_id = _parse_load_args(parts, chat_id)
    log("lfb_commands", f"_cmd_load_as_one(target={target_chat_id}, verbose={verbose})")

    chat = get_chat(target_chat_id)
    if not chat:
        yield f"No chat found for ID: {target_chat_id}\n"
        return

    title = chat.get("title") or "Untitled"
    summary = chat.get("summary") or title
    docs = get_docs_by_chat(target_chat_id)
    docs_str = ", ".join(d["filename"] for d in docs) if docs else "none"

    yield "***-0-***\n"
    yield f"*Chat ID: {target_chat_id}\n"
    yield f"*Title: {title}\n"
    yield f"*Summary: {summary}\n"
    yield f"*Docs: {docs_str}\n"

    blocks = get_blocks_by_chat(target_chat_id)
    for i, block in enumerate(blocks, start=1):
        yield f"***-{i}-***\n"
        user_content = block.get("user_content") or ""
        system_content = block.get("system_content") or ""
        assistant_content = block.get("assistant_content") or ""
        if user_content:
            yield f"**user:** {user_content}\n"
        if verbose and system_content:
            yield f"**system:** {system_content}\n"
        if assistant_content:
            yield f"**assistant:** {assistant_content}\n"


def _cmd_load_as_history(parts: list, chat_id: str, api_key: str):
    verbose, target_chat_id = _parse_load_args(parts, chat_id)
    log("lfb_commands", f"_cmd_load_as_history(target={target_chat_id}, verbose={verbose})")

    chat = get_chat(target_chat_id)
    if not chat:
        yield f"No chat found for ID: {target_chat_id}\n"
        return

    title = chat.get("title") or "Untitled"
    summary = chat.get("summary") or title
    docs = get_docs_by_chat(target_chat_id)
    docs_str = ", ".join(d["filename"] for d in docs) if docs else "none"

    # This command's own assistant response = /info of source chat
    yield f"*Chat ID: {target_chat_id}\n"
    yield f"*Title: {title}\n"
    yield f"*Summary: {summary}\n"
    yield f"*Docs: {docs_str}\n"

    # Copy source blocks into current chat pipeline SQLite with new UUIDs
    source_blocks = get_blocks_by_chat(target_chat_id)
    for block in source_blocks:
        new_block_id = str(uuid.uuid4())
        add_block(
            chat_id,
            new_block_id,
            block.get("user_content") or "",
            system_content=block.get("system_content"),
            assistant_content=block.get("assistant_content"),
        )
        log("lfb_commands", f"_cmd_load_as_history - copied block -> {new_block_id[:8]}...")

    # Rewrite OpenWebUI history with all current chat blocks
    # combine_system=True merges system+assistant to match native OpenWebUI format
    all_blocks = get_blocks_by_chat(chat_id)
    ok = rewrite_chat_history(chat_id, all_blocks, api_key, combine_system=True)
    if not ok:
        yield "\nWarning: OpenWebUI history sync failed. Pipeline SQLite updated but UI may be out of sync.\n"

