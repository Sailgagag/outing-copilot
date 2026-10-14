"""Simulated Alexa+ conversation against the real Outing Copilot MCP server.

It starts the server as a separate process on Streamable HTTP, connects with the
official MCP Python client, and plays a scripted household conversation. The
"intent router" below is a deliberately simple stand-in for the Alexa+ LLM:
it only maps each utterance to a tool call; all answers come from the server.

    python demo/alexa_sim.py            # live public APIs
    python demo/alexa_sim.py --offline  # recorded fixtures (no network)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from mcp import Client

PINNED_PROTOCOL = "2025-11-25"
ROOT = Path(__file__).resolve().parents[1]

SCRIPT = [
    ("Alexa, remember home as Seattle.", "remember_place", {"nickname": "home", "place": "Seattle"}),
    ("Alexa, when's the best time to walk the dog at home today?", "find_best_time",
     {"place": "home", "activity": "dog_walk", "day": "today"}),
    ("My son has asthma, so be careful about air quality.", "set_preferences", {"sensitive_to_air": True}),
    ("Could we do a two-hour picnic this weekend?", "find_best_time",
     {"place": "home", "activity": "picnic", "day": "weekend", "duration_hours": 2}),
    ("Which day this week is best for a run?", "week_outlook", {"place": "home", "activity": "run"}),
    ("We're visiting Portland tomorrow. When should we go for a walk?", "find_best_time",
     {"place": "Portland", "activity": "walk", "day": "tomorrow"}),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(port: int, timeout: float = 15) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("server did not start")


async def converse(url: str) -> None:
    # Pin the 2025-11-25 spec: mode="legacy" is the SDK's documented switch for the
    # initialize handshake (Alexa+ targets MCP 2025-11-25, not the 2026 discover flow).
    async with Client(url, mode="legacy") as client:
        if client.protocol_version != PINNED_PROTOCOL:
            raise RuntimeError(f"expected MCP {PINNED_PROTOCOL}, negotiated {client.protocol_version}")
        info = client.server_info
        print(f"[connected to {info.name if info else '?'} via Streamable HTTP, protocol {client.protocol_version}]")
        tools = [t.name for t in (await client.list_tools()).tools]
        print(f"[tools: {', '.join(tools)}]\n")
        for utterance, tool, args in SCRIPT:
            print(f"USER : {utterance}")
            print(f"       -> tools/call {tool} {args}")
            r = await client.call_tool(tool, args)
            data = r.structured_content or {}
            print(f"ALEXA: {data.get('speech', r.content)}")
            if card := data.get("card"):
                print(f"       [card] {card['title']} — {card['text']}")
            print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="serve upstream APIs from tests/fixtures")
    a = ap.parse_args()
    port = free_port()
    env = dict(os.environ, OUTING_STATE_FILE=str(Path(tempfile.mkdtemp()) / "state.json"))
    if a.offline:
        env["OUTING_FIXTURE_DIR"] = str(ROOT / "tests" / "fixtures")
        env["OUTING_NOW"] = "2026-10-14T16:00:00+00:00"  # 9 AM in Seattle, matches the recording
    proc = subprocess.Popen(
        [sys.executable, "-m", "outing_copilot.server", "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        wait_for(port)
        asyncio.run(converse(f"http://127.0.0.1:{port}/mcp"))
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    main()
