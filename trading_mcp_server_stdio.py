#!/usr/bin/env python3
"""
Trading MCP Server (stdio + JSON-RPC)
提供幣安期貨交易工具
"""

import sys
import json
import requests
from typing import Any, Optional

BACKEND_URL = "http://127.0.0.1:8069"

# tools

TOOLS = [
    {
        "name": "place_market_order",
        "description": "市價下單（支援 USDT 金額或直接輸入數量，可帶止損與止盈）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對，例如 BTCUSDT"},
                "side": {"type": "string", "enum": ["BUY", "SELL"], "description": "方向"},
                "usdt_amount": {"type": "number", "description": "使用 USDT 名義持倉價值下單"},
                "quantity": {"type": "number", "description": "直接輸入該幣數量"},
                "leverage": {"type": "integer", "description": "槓桿倍數 預設為 10", "default": 10},
            },
            "required": ["symbol", "side"]
        }
    },
    {
        "name": "place_limit_order",
        "description": "掛限價單用於開倉、平倉或止盈。支援價格、數量或倉位百分比，若要進場需要reduceOnly = False。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對"},
                "side": {"type": "string", "enum": ["BUY", "SELL"], "description": "方向"},
                "price": {"type": "number", "description": "限價價格，槓桿前的價格"},
                "usdt_amount": {"type": "number", "description": "使用 USDT 名義持倉價值下單 若同時提供 quantity 以 usdt_amount 為準"},
                "quantity": {"type": "number", "description": "固定數量"},
                "percentage": {"type": "number", "description": "使用倉位百分比來計算減倉數量（例如 50 就是使用一半倉位）不能用於進場買入"},
                "percentagePnl": {"type": "number", "description": "使用盈虧百分比計算止盈點位 (例如 20 代表盈利 20% 時觸發)"},
                "type": {"type": "string", "enum": ["LIMIT", "STOP_LIMIT"], "default": "LIMIT"},
                "reduceOnly": {"type": "boolean", "description": "是否只減倉", "default": True}
            },
            "required": ["symbol", "side", "price", "reduceOnly"]
        }
    },
    {
        "name": "set_stop_loss",
        "description": "設置止損（支援直接輸入價格或收益率） 不可用於止盈",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對"},
                "stop_price": {"type": "number", "description": "填寫目標止損價格"},
                "percentage": {"type": "number", "description": "填寫虧損率百分比"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_positions",
        "description": "查詢所有當前倉位資訊（含市價、盈虧、掛單列表）",
        "inputSchema": {
            "type": "object", 
            "properties": {
                "symbol": {"type": "string", "description": "可選的交易對過濾參數 未傳入或填入 'string' 代表不過濾"},
                "ezmode": {"type": "boolean", "description": "是否啟用簡易模式省下token 預設開啟", "default": True}
            }
        }
    },
    {
        "name": "close_position",
        "description": "立刻以市價平掉指定交易對的倉位",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "cancel_order",
        "description": "取消該幣種所有掛單。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "交易對"},
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_wallet_balance",
        "description": "查詢 USDT 合約錢包餘額資訊",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_recommended_size",
        "description": "根據目前餘額與傳入的槓桿，計算推薦的 USDT 名義持倉價值",
        "inputSchema": {
            "type": "object",
            "properties": {
                "leverage": {"type": "integer", "description": "預計使用的槓桿倍數", "default": 10}
            },
            "required": ["leverage"]
        }
    },
    {
        "name": "get_active_stop_losses",
        "description": "返回所有已經成功設定了止損 (stop_loss) 的現有倉位列表",
        "inputSchema": {
            "type": "object",
            "properties": {
                 "symbol": {"type": "string", "description": "可選的交易對過濾參數 未傳入或填入 'string' 代表不過濾"},
                 "ezmode": {"type": "boolean", "description": "是否啟用簡易模式省下token", "default": True}
            }
        }
    },
    {
        "name": "get_pending_orders",
        "description": "返回目前所有正在掛著的限價單 (Limit Orders)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "calculate_sl_by_leverage",
        "description": "根據槓桿倍數計算建議的止損與止盈點位距離（返回絕對價格列表）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "leverage": {"type": "integer", "description": "槓桿倍數"},
                "entry_price": {"type": "number", "description": "入場價格"}
            },
            "required": ["leverage", "entry_price"]
        }
    },
    {
        "name": "sync_positions",
        "description": "從 Binance 讀取真實持倉並同步到本地資料庫",
        "inputSchema": {"type": "object", "properties": {}}
    },
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
    }
]

# tool execution

def call_backend(endpoint: str, method: str = "POST", payload: Optional[dict] = None) -> dict:
    url = f"{BACKEND_URL}{endpoint}"
    resp = None
    try:
        if method == "GET":
            resp = requests.get(url, timeout=15)
        else:
            resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        # 嘗試從 response body 中取得詳細錯誤訊息
        if resp is not None:
            try:
                error_detail = resp.json().get("detail", str(e))
            except Exception:
                error_detail = str(e)
        else:
            error_detail = str(e)
        return {"error": error_detail}
    except Exception as e:
        return {"error": str(e)}

def execute_tool(name: str, arguments: dict) -> dict:
    if name == "place_market_order":
        return call_backend("/order", payload=arguments)
    elif name == "place_limit_order":
        return call_backend("/place-limit", payload=arguments)
    elif name == "get_positions":
        return call_backend("/positions", payload=arguments)
    elif name == "sync_positions":
        return call_backend("/sync-positions")
    elif name == "cancel_order":
        return call_backend("/cancel-order", payload=arguments)
    elif name == "close_position":
        return call_backend("/close-position", payload=arguments)
    elif name == "get_wallet_balance":
        return call_backend("/wallet-balance", method="GET")
    elif name == "get_active_stop_losses":
        return call_backend("/grab-stop-losses", payload=arguments)
    elif name == "get_pending_orders":
        return call_backend("/pending-orders", method="GET")
    elif name == "get_recommended_size":
        return call_backend("/recommended-size", payload=arguments)
    elif name == "calculate_sl_by_leverage":
        return call_backend("/calculate-sl-by-leverage", payload=arguments)
    elif name == "set_stop_loss":
        return call_backend("/set-stop-loss", payload=arguments)
    elif name == "get_symbol_info":
        return call_backend("/get-symbol-info", payload=arguments)
    else:
        return {"error": f"未知工具: {name}"}

# mcp 協議啟動
def send_message(msg: dict):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def handle_initialize(params: dict) -> dict:
    return {
        "protocolVersion": "2025-11-25",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "trading-mcp",
            "version": "2.0.0"
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
    print("trading MCP server started", file=sys.stderr)
    
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
                result = handle_initialize(params)
            elif method == "tools/list":
                result = handle_tools_list()
            elif method == "tools/call":
                result = handle_tools_call(params)
            elif method == "ping":
                result = {}
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
