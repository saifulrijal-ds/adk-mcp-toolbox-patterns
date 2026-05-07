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

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--table_names", default="")
    parser.add_argument("--output_format", default="detailed")
    parsed = parser.parse_args()
    params = {}
    if parsed.table_names:
        params["table_names"] = parsed.table_names
    if parsed.output_format != "detailed":
        params["output_format"] = parsed.output_format
    call_tool("tool_list_tables", params)


if __name__ == "__main__":
    main()
