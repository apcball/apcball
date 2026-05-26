#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP Client for Odoo 17 — stdio transport (no external dependencies)
Connects AI agents to Odoo via the MCP Server module.

Environment variables:
  ODOO_URL      — Odoo base URL (e.g. https://mogdev.work)
  ODOO_API_KEY  — API key from MCP Server settings
  ODOO_DB       — Odoo database name (e.g. MOG_DEV)
"""

import json
import os
import sys
import traceback
import urllib.request
import urllib.error

# ─── Config ───────────────────────────────────────────────
ODOO_URL = os.environ.get("ODOO_URL", "").rstrip("/")
ODOO_API_KEY = os.environ.get("ODOO_API_KEY", "")
ODOO_DB = os.environ.get("ODOO_DB", "MOG_DEV")

if not ODOO_URL or not ODOO_API_KEY:
    sys.stderr.write("ERROR: ODOO_URL and ODOO_API_KEY environment variables are required.\n")
    sys.exit(1)


# ─── HTTP helpers ─────────────────────────────────────────

def _url(path, params=None):
    url = f"{ODOO_URL}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    return url


def _headers():
    return {
        "X-API-Key": ODOO_API_KEY,
        "X-Odoo-DB": ODOO_DB,
        "Content-Type": "application/json",
        "User-Agent": "odoo-mcp-client/0.2",
    }


def odoo_call(endpoint, payload):
    """Call an Odoo MCP endpoint and return the result dict."""
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        _url(endpoint, {"db": ODOO_DB}),
        data=data,
        headers=_headers(),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = json.loads(e.read().decode("utf-8"))
    if not body.get("success"):
        raise RuntimeError(body.get("error", "Unknown error"))
    return body.get("data")


def fetch_tools():
    """Fetch available tools from the /mcp/tools endpoint."""
    req = urllib.request.Request(
        _url("/mcp/tools", {"db": ODOO_DB}),
        headers=_headers(),
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ─── MCP protocol (stdio) ─────────────────────────────────

def send_result(msg_id, result):
    msg = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def send_error(msg_id, code, message):
    msg = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def handle_message(msg):
    """Process a single JSON-RPC message."""
    msg_id = msg.get("id")
    method = msg.get("method", "")

    if method == "initialize":
        send_result(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "odoo-mcp", "version": "0.2.0"},
        })

    elif method == "notifications/initialized":
        pass  # no response

    elif method == "ping":
        send_result(msg_id, {})

    elif method == "tools/list":
        try:
            tools = fetch_tools()
            send_result(msg_id, {"tools": tools})
        except Exception as e:
            send_result(msg_id, {"tools": [], "error": str(e)})

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        try:
            data = odoo_call(f"/mcp/call/{tool_name}", arguments)
            text = json.dumps(data, ensure_ascii=False, default=str)
            send_result(msg_id, {
                "content": [{"type": "text", "text": text}],
            })
        except Exception as e:
            send_result(msg_id, {
                "content": [{"type": "text", "text": f"Error: {e}"}],
                "isError": True,
            })

    else:
        send_error(msg_id, -32601, f"Method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            handle_message(msg)
        except json.JSONDecodeError:
            send_error(None, -32700, "Parse error")
        except Exception:
            send_error(None, -32603, traceback.format_exc())


if __name__ == "__main__":
    main()
