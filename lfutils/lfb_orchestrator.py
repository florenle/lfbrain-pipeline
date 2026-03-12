# lfb_orchestrator.py
# Status: In Development
# Role: Handles HTTP streaming between the pipeline and lfbrain-orchestrator.
#
# Key Functions:
#   stream_job_http(): Async generator. Connects to POST /stream, yields normalized
#                      (kind, chunk) events: think, token, usage, done, error.
#
# Dependencies:
#   httpx
#   lfb_log: log()
#
# Dev Notes:
#   stream_job_http() is async — lfb_pipeStream bridges it into a sync iterator via
#   a dedicated event loop on a daemon thread.
#   SSE format: "data: {json}\n\n". Types: think, token, usage, done, error.
#
# Schema: LFB03112026A

import json
import httpx
from typing import AsyncGenerator
from lfb_log import log


async def stream_job_http(
    orchestrator_url: str,
    query: str,
    context: str,
    model_hint: str,
) -> AsyncGenerator[tuple[str, str], None]:
    log("lfb_orchestrator", f"stream_job_http start — model_hint={model_hint} query={query[:40]}...")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{orchestrator_url}/stream",
                json={
                    "query": query,
                    "context": context,
                    "model_hint": model_hint,
                },
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    try:
                        data = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    kind = data.get("type")
                    chunk = data.get("chunk", "")
                    if kind == "done":
                        log("lfb_orchestrator", "stream_job_http complete")
                        return
                    elif kind == "error":
                        log("lfb_orchestrator", f"stream_job_http error — {chunk}")
                        yield ("failed", chunk)
                        return
                    elif kind == "usage":
                        yield ("usage", data.get("usage", {}))
                    elif kind in ("think", "token"):
                        yield (kind, chunk)
    except Exception as e:
        log("lfb_orchestrator", f"stream_job_http connection error — {str(e)}")
        yield ("failed", f"Stream connection error: {str(e)}")
