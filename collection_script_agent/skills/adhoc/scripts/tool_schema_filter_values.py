#!/usr/bin/env python3
import json
import os
import sys
import urllib.request

TOOLBOX_URL = os.environ.get("TOOLBOX_URL", "http://127.0.0.1:5002")


def call_tool(tool_name: str, params: dict) -> None:
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": params},
        "id": 1,
    }).encode()
    req = urllib.request.Request(
        f"{TOOLBOX_URL}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    if "error" in data:
        print(f"Error: {data['error']}", file=sys.stderr)
        return
    for item in data.get("result", {}).get("content", []):
        if item.get("type") == "text":
            print(item["text"])

if __name__ == "__main__":
    call_tool("tool_schema_filter_values", {})
