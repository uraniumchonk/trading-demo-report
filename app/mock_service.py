"""
Mock Service - Demo Mode 假資料服務
所有 API 端點在 DEMO_MODE=true 時使用此服務返回模擬資料
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional

MOCK_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mock_data")


def _load_mock(filename: str) -> Any:
    """載入 mock JSON 資料"""
    filepath = os.path.join(MOCK_DATA_DIR, filename)
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# kline data

def get_mock_klines(symbol: str, interval: str = "30m", limit: int = 10) -> List[Dict]:
    """取得模擬 K 線資料"""
    data = _load_mock("klines.json")
    symbol_data = data.get(symbol, {})
    klines = symbol_data.get(interval, [])
    return klines[:limit]


# wallet balance

def get_mock_wallet_balance() -> Dict:
    """取得模擬錢包餘額"""
    return _load_mock("wallet_balance.json")


# positions

def get_mock_positions(symbol: Optional[str] = None) -> Any:
    """取得模擬持倉"""
    all_positions = _load_mock("positions.json")
    if symbol:
        return all_positions.get(symbol, None)
    return list(all_positions.values())


# orders

def get_mock_orders() -> List[Dict]:
    """取得模擬訂單歷史"""
    data = _load_mock("orders.json")
    return data.get("orders", [])


def get_mock_pending_orders() -> List[Dict]:
    """取得模擬未完成訂單"""
    data = _load_mock("orders.json")
    return data.get("pending_orders", [])


# place order (mock)

_mock_order_counter = 2000

def place_mock_order(order_data: Dict) -> Dict:
    """模擬下單，返回假訂單回應"""
    global _mock_order_counter
    _mock_order_counter += 1
    
    return {
        "orderId": _mock_order_counter,
        "symbol": order_data.get("symbol", "BTCUSDT"),
        "side": order_data.get("side", "BUY"),
        "type": order_data.get("type", "MARKET"),
        "quantity": order_data.get("quantity", "0.1"),
        "price": order_data.get("price", "0"),
        "status": "FILLED",
        "fills": [
            {
                "price": order_data.get("price", "69000.00"),
                "qty": order_data.get("quantity", "0.1"),
                "commission": "0.01",
                "commissionAsset": "USDT",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        ],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_demo_note": "DEMO MODE - 此訂單未實際執行"
    }


def cancel_mock_order(order_id: int) -> Dict:
    """模擬取消訂單"""
    return {
        "success": True,
        "orderId": order_id,
        "message": "訂單已取消 (Demo Mode)",
        "_demo_note": "DEMO MODE - 此操作未實際執行"
    }


# stop loss

def set_mock_stop_loss(order_data: Dict) -> Dict:
    """模擬設定停損"""
    global _mock_order_counter
    _mock_order_counter += 1
    
    return {
        "orderId": _mock_order_counter,
        "symbol": order_data.get("symbol"),
        "side": order_data.get("side"),
        "type": "STOP_MARKET",
        "stopPrice": order_data.get("stopPrice"),
        "quantity": order_data.get("quantity"),
        "status": "NEW",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "_demo_note": "DEMO MODE - 停損單未實際設定"
    }


# market stats

def get_mock_market_stats(symbol: str) -> Dict:
    """取得模擬市場統計"""
    data = _load_mock("market_stats.json")
    return data.get(symbol, {})


# signal analysis

def get_mock_signal_analysis(symbol: str, interval: str = "30m") -> Dict:
    """取得模擬信號分析結果（匹配真實 RMMA 回傳格式）"""
    data = _load_mock("signal_analysis.json")
    result = data.get(symbol, {
        "symbol": symbol,
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "decision": "NEUTRAL",
            "score": 0,
            "message": "⚖️ 中性：無此幣種的模擬資料",
            "action": "HOLD"
        },
        "layers": {
            "L1_Trend_4H": {"direction": "neutral", "price": 0, "ema200": 0},
            "L2_Context_1H": {"environment": "neutral", "bb_width": 0, "avg_width": 0},
            "L3_Trigger_30m": {
                "time_window": "30m",
                "phase": "無資料",
                "trend": "中性",
                "mfi_macd_divergence": "無資料",
                "rsi_mfi_divergence": "無資料",
                "latest_swing_high": 0,
                "latest_swing_low": 0,
                "latest_price": 0,
                "latest_macd_zscore": 0,
                "swing_highs": [],
                "swing_lows": [],
                "support_zone": [],
                "resistance_zone": [],
                "latest_10_mfi": [],
                "latest_10_rsi": []
            }
        },
        "_demo_note": "DEMO MODE - 模擬分析結果"
    })
    return result


# recommended size

def get_mock_recommended_size(balance: float = 10000, risk_percent: float = 2, 
                            entry_price: float = 69000, stop_loss: float = 65000) -> Dict:
    """模擬推薦倉位大小"""
    risk_amount = balance * (risk_percent / 100)
    price_distance = abs(entry_price - stop_loss)
    if price_distance == 0:
        return {"error": "停損價格不能等於進場價格"}
    
    position_size = risk_amount / price_distance
    return {
        "recommended_size": round(position_size, 6),
        "risk_amount": round(risk_amount, 2),
        "risk_percent": risk_percent,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "max_loss": round(risk_amount, 2),
        "_demo_note": "DEMO MODE - 僅供參考"
    }


# symbol info

def get_mock_symbol_info(symbol: str) -> Dict:
    """取得模擬交易對資訊（含分類）"""
    from signal_layer.symbol_classifier import classify_symbol, get_tradfi_category

    # 基於真實 Binance 價格的完整交易對列表
    mock_info = {
        # 虛擬貨幣
        "BTCUSDT": {"baseAsset": "BTC", "quoteAsset": "USDT", "pricePrecision": 1, "qtyPrecision": 5, "tickSize": 0.1, "mark_price": 63295.80},
        "ETHUSDT": {"baseAsset": "ETH", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 5, "tickSize": 0.01, "mark_price": 1706.68},
        "BNBUSDT": {"baseAsset": "BNB", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 580.90},
        "SOLUSDT": {"baseAsset": "SOL", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 69.41},
        "XRPUSDT": {"baseAsset": "XRP", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 1.1344},
        "DOGEUSDT": {"baseAsset": "DOGE", "quoteAsset": "USDT", "pricePrecision": 5, "qtyPrecision": 0, "tickSize": 0.00001, "mark_price": 0.08329},
        "ADAUSDT": {"baseAsset": "ADA", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 0.1617},
        "AVAXUSDT": {"baseAsset": "AVAX", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 5.903},
        "DOTUSDT": {"baseAsset": "DOT", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 0.956},
        "LINKUSDT": {"baseAsset": "LINK", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 7.923},
        "LTCUSDT": {"baseAsset": "LTC", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 43.85},
        "BCHUSDT": {"baseAsset": "BCH", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 197.90},
        "UNIUSDT": {"baseAsset": "UNI", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 3.065},
        "ATOMUSDT": {"baseAsset": "ATOM", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 1.802},
        "APTUSDT": {"baseAsset": "APT", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 0.631},
        "ARBUSDT": {"baseAsset": "ARB", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 0.0834},
        "SUIUSDT": {"baseAsset": "SUI", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 0.7132},
        "NEARUSDT": {"baseAsset": "NEAR", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 2.153},
        "INJUSDT": {"baseAsset": "INJ", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 5.111},
        "ETCUSDT": {"baseAsset": "ETC", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 7.639},
        "XLMUSDT": {"baseAsset": "XLM", "quoteAsset": "USDT", "pricePrecision": 5, "qtyPrecision": 0, "tickSize": 0.00001, "mark_price": 0.21734},
        "ALGOUSDT": {"baseAsset": "ALGO", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 0.0949},
        "VETUSDT": {"baseAsset": "VET", "quoteAsset": "USDT", "pricePrecision": 6, "qtyPrecision": 0, "tickSize": 0.000001, "mark_price": 0.004887},
        "ICPUSDT": {"baseAsset": "ICP", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 2.253},
        "FILUSDT": {"baseAsset": "FIL", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 0.788},
        "APEUSDT": {"baseAsset": "APE", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 0.1306},
        "GMTUSDT": {"baseAsset": "GMT", "quoteAsset": "USDT", "pricePrecision": 5, "qtyPrecision": 0, "tickSize": 0.00001, "mark_price": 0.00796},
        "OPUSDT": {"baseAsset": "OP", "quoteAsset": "USDT", "pricePrecision": 3, "qtyPrecision": 3, "tickSize": 0.001, "mark_price": 0.103},
        
        # 黃金
        "XAUTUSDT": {"baseAsset": "XAU", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 4146.99},
        
        # 美股
        "AAPLUSDT": {"baseAsset": "AAPL", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 296.56},
        "TSLAUSDT": {"baseAsset": "TSLA", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 399.72},
        "NVDAUSDT": {"baseAsset": "NVDA", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 209.29},
        "MSFTUSDT": {"baseAsset": "MSFT", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 381.82},
        "AMZNUSDT": {"baseAsset": "AMZN", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 243.14},
        "GOOGLUSDT": {"baseAsset": "GOOGL", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 366.12},
        "METAUSDT": {"baseAsset": "META", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 576.72},
        "NFLXUSDT": {"baseAsset": "NFLX", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 77.57},
        "AMDUSDT": {"baseAsset": "AMD", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 538.78},
        "QQQUSDT": {"baseAsset": "QQQ", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 741.29},
        "SPYUSDT": {"baseAsset": "SPY", "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 746.33},
        "DIAUSDT": {"baseAsset": "DIA", "quoteAsset": "USDT", "pricePrecision": 4, "qtyPrecision": 1, "tickSize": 0.0001, "mark_price": 0.1174},
    }

    base = mock_info.get(symbol, {"baseAsset": symbol.replace("USDT", ""), "quoteAsset": "USDT", "pricePrecision": 2, "qtyPrecision": 3, "tickSize": 0.01, "mark_price": 0})

    category = classify_symbol(symbol)
    category_detail = get_tradfi_category(symbol)

    return {
        **base,
        "symbol": symbol,
        "category": category,
        "category_detail": category_detail,
    }
