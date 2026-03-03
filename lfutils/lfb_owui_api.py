# lfb_owui_api.py
# Status: In Development
# Role: OpenWebUI API integration for chat history rewrite.
#       Converts pipeline SQLite blocks into OpenWebUI history format and POSTs to API.
#
# Key Functions:
#   build_history(blocks, combine_system): Converts pipeline blocks to OpenWebUI linked-list history dict.
#   rewrite_chat_history(chat_id, blocks, api_key, combine_system): POSTs reconstructed history to OpenWebUI.
#
# Dependencies:
#   requests, uuid
#
# Dev Notes:
#   OpenWebUI internal port is 8080 (mapped to 3000 on host).
#   Each pipeline block maps to one user+assistant message pair.
#   system_content is pipeline-only by default — never written to OpenWebUI history unless combine_system=True.
#   combine_system=True: merges system_content + assistant_content (used by loadAsHistory).
#   combine_system=False: assistant_content only (default, for rewrite/cleanup ops).
#   Messages are a linked list: null -> user1 -> assistant1 -> user2 -> assistant2 -> ...
#   currentId = last assistant message id.
#   api_key = pipelines API key passed as Valve from lfbrain.py.
#   build_history() is format-only — caller (_cmd_load_as_history or equivalent) prepares content.

import uuid
import requests
from lfb_log import log

OWUI_BASE_URL = "http://open-webui:8080/api/v1"

def build_history(blocks: list, combine_system: bool = False) -> dict:
    # combine_system=True: merges system_content + assistant_content (for loadAsHistory)
    # combine_system=False: assistant_content only (default, for rewrite/cleanup ops)
    log("lfb_owui_api", f"build_history({len(blocks)} blocks, combine_system={combine_system})")
    messages = {}
    prev_id = None
    last_assistant_id = None

    for block in blocks:
        user_id = str(uuid.uuid4())
        assistant_id = str(uuid.uuid4())

        system_content = block.get("system_content") or ""
        assistant_content = block.get("assistant_content") or ""
        if combine_system and system_content:
            final_assistant = f"{system_content}\n{assistant_content}".strip()
        else:
            final_assistant = assistant_content

        messages[user_id] = {
            "id": user_id,
            "parentId": prev_id,
            "childrenIds": [assistant_id],
            "role": "user",
            "content": block.get("user_content") or "",
            "timestamp": _iso_to_timestamp(block.get("created_at")),
            "done": True,
            "model": "lfbrain",
            "data": {},
            "meta": {},
        }
        messages[assistant_id] = {
            "id": assistant_id,
            "parentId": user_id,
            "childrenIds": [],
            "role": "assistant",
            "content": final_assistant,
            "timestamp": _iso_to_timestamp(block.get("created_at")),
            "done": True,
            "model": "lfbrain",
            "data": {},
            "meta": {},
        }

        if prev_id and prev_id in messages:
            messages[prev_id]["childrenIds"] = [user_id]

        prev_id = assistant_id
        last_assistant_id = assistant_id

    return {
        "messages": messages,
        "currentId": last_assistant_id,
    }

def rewrite_chat_history(chat_id: str, blocks: list, api_key: str, combine_system: bool = False) -> bool:
    log("lfb_owui_api", f"rewrite_chat_history(chat_id={chat_id}, blocks={len(blocks)}, combine_system={combine_system})")
    history = build_history(blocks, combine_system=combine_system)
    url = f"{OWUI_BASE_URL}/chats/{chat_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"chat": {"history": history}}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 200:
            log("lfb_owui_api", "rewrite_chat_history — success")
            return True
        else:
            log("lfb_owui_api", f"rewrite_chat_history — failed {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log("lfb_owui_api", f"rewrite_chat_history — exception: {e}")
        return False

def _iso_to_timestamp(iso_str: str) -> int:
    if not iso_str:
        return 0
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso_str)
        return int(dt.timestamp())
    except Exception:
        return 0
