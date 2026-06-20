#!/usr/bin/env python3
"""
Signal MCP Server (stdio + JSON-RPC)
提供市場分析工具
"""

import sys
import json
import requests
from typing import Any, Dict

BACKEND_URL = "http://127.0.0.1:8069"

# tools
TOOLS = [
    {
        "name": "get_symbol_info",
        "description": "獲取交易對的詳細資訊，包括價格與種類",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對，例如 BTCUSDT"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_analyze_RMMA_singal",
        "description": "RSI MFI MACD與回歸推算的綜合信號算法 可以知道目前趨勢方向與入場風險 需要結合點位判斷工具使用",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對，例如 BTCUSDT"},
            },
            "required": ["symbol"]
        }
    }

]

# tool execution
def call_backend(endpoint: str, payload: dict = None) -> dict:
    url = f"{BACKEND_URL}{endpoint}"
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": f"後端呼叫失敗: {str(e)}", "backend_url": url}

def execute_tool(name: str, arguments: dict) -> dict:
    if name == "get_symbol_info":
        return call_backend("/get-symbol-info", payload=arguments)
    elif name == "get_analyze_RMMA_singal": 
        return call_backend("/mixed_RMMA_singal", payload=arguments)
    else:
        return {"error": f"未知工具: {name}"}

# mcp 協議啟動
def send_message(msg: dict):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def handle_initialize() -> dict:
    return {
        "protocolVersion": "2025-11-25",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "signal-mcp",
            "version": "2.1.0"
        }
    }

def handle_tools_list() -> dict:
    return {"tools": TOOLS}

def handle_tools_call(params: dict) -> dict:
    name = params.get("name")
    arguments = params.get("arguments", {})
    
    result = execute_tool(name, arguments)
    
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(result, ensure_ascii=False, indent=2)
            }
        ]
    }

def main():
    print(f"signal MCP started, backend: {BACKEND_URL}", file=sys.stderr)
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            if method == "initialize":
                result = handle_initialize()
            elif method == "tools/list":
                result = handle_tools_list()
            elif method == "tools/call":
                result = handle_tools_call(params)
            elif method == "ping":
                result = {"status": "ok"}
            else:
                result = {"error": f"unknown method: {method}"}

            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result
            }
            send_message(response)

        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": request.get("id") if 'request' in locals() else None,
                "error": {"code": -32603, "message": str(e)}
            }
            send_message(error_response)

if __name__ == "__main__":
    main()