"""
Symbol Classification Utility (Demo Static Version)

Demo 版本使用靜態數據，不需要連接 Binance API。
分類邏輯與完整版一致，但 symbol_map 為硬編碼。

TradFi 包含：
- 貴金屬 (XAU, XAG, XPT, XPD)
- 大宗商品 (COPPER, NATGAS, CL, BZ)
- 美股單股 (AAPL, TSLA, NVDA, AMD...)
- 韓國股票 (SAMSUNG, HYUNDAI, SKHYNIX)
- ETF (EWJ, QQQ, SPY, IWM...)
- Pre-IPO (OPENAI, ANTHROPIC)
"""

from typing import Dict, Optional, Any, List

# 靜態 symbol_map — Demo 模式不需要網路請求
# 涵蓋常見的 TradFi 交易對
_STATIC_SYMBOL_MAP: Dict[str, Dict[str, Any]] = {
    # 貴金屬
    "XAUUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XAU", "quoteAsset": "USDT"},
    "XAGUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XAG", "quoteAsset": "USDT"},
    "XPTUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XPT", "quoteAsset": "USDT"},
    "XPDUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XPD", "quoteAsset": "USDT"},

    # 大宗商品
    "COPPERUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "COPPER", "quoteAsset": "USDT"},
    "NATGASUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "NATGAS", "quoteAsset": "USDT"},
    "CLUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "CL", "quoteAsset": "USDT"},
    "BZUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "BZ", "quoteAsset": "USDT"},

    # 美股
    "AAPLUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "AAPL", "quoteAsset": "USDT"},
    "TSLAUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "TSLA", "quoteAsset": "USDT"},
    "NVDAUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "NVDA", "quoteAsset": "USDT"},
    "AMDUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "AMD", "quoteAsset": "USDT"},
    "AMZNUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "AMZN", "quoteAsset": "USDT"},
    "GOOGLUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "GOOGL", "quoteAsset": "USDT"},
    "MSFTUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "MSFT", "quoteAsset": "USDT"},
    "METAUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "META", "quoteAsset": "USDT"},
    "NFLXUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "NFLX", "quoteAsset": "USDT"},
    "NIOUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "NIO", "quoteAsset": "USDT"},
    "BABAUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "BABA", "quoteAsset": "USDT"},
    "COINUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "COIN", "quoteAsset": "USDT"},
    "BAKUSETUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "BAKUSET", "quoteAsset": "USDT"},

    # 韓股
    "SAMSUNGUSDT": {"underlyingType": "KR_EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "SAMSUNG", "quoteAsset": "USDT"},
    "HYUNDAIUSDT": {"underlyingType": "KR_EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "HYUNDAI", "quoteAsset": "USDT"},
    "SKHYNIXUSDT": {"underlyingType": "KR_EQUITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "SKHYNIX", "quoteAsset": "USDT"},

    # ETF
    "EWJUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi", "ETF"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "EWJ", "quoteAsset": "USDT"},
    "QQQUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi", "ETF"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "QQQ", "quoteAsset": "USDT"},
    "SPYUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi", "ETF"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "SPY", "quoteAsset": "USDT"},
    "IWMUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi", "ETF"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "IWM", "quoteAsset": "USDT"},

    # Pre-IPO
    "OPENAIUSDT": {"underlyingType": "PREMARKET", "underlyingSubType": ["TradFi", "Pre-IPO"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "OPENAI", "quoteAsset": "USDT"},
    "ANTHROPICUSDT": {"underlyingType": "PREMARKET", "underlyingSubType": ["TradFi", "Pre-IPO"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ANTHROPIC", "quoteAsset": "USDT"},

    # 加密貨幣（對照組）— 扩充完整列表
    "BTCUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "BTC", "quoteAsset": "USDT"},
    "ETHUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ETH", "quoteAsset": "USDT"},
    "BNBUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "BNB", "quoteAsset": "USDT"},
    "SOLUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "SOL", "quoteAsset": "USDT"},
    "XRPUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XRP", "quoteAsset": "USDT"},
    "DOGEUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "DOGE", "quoteAsset": "USDT"},
    "ADAUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ADA", "quoteAsset": "USDT"},
    "AVAXUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "AVAX", "quoteAsset": "USDT"},
    "DOTUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "DOT", "quoteAsset": "USDT"},
    "LINKUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "LINK", "quoteAsset": "USDT"},
    "LTCUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "LTC", "quoteAsset": "USDT"},
    "BCHUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "BCH", "quoteAsset": "USDT"},
    "UNIUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "UNI", "quoteAsset": "USDT"},
    "ATOMUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ATOM", "quoteAsset": "USDT"},
    "APTUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "APT", "quoteAsset": "USDT"},
    "ARBUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ARB", "quoteAsset": "USDT"},
    "SUIUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "SUI", "quoteAsset": "USDT"},
    "NEARUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "NEAR", "quoteAsset": "USDT"},
    "INJUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "INJ", "quoteAsset": "USDT"},
    "ETCUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ETC", "quoteAsset": "USDT"},
    "XLMUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XLM", "quoteAsset": "USDT"},
    "ALGOUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ALGO", "quoteAsset": "USDT"},
    "VETUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "VET", "quoteAsset": "USDT"},
    "ICPUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "ICP", "quoteAsset": "USDT"},
    "FILUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "FIL", "quoteAsset": "USDT"},
    "APEUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "APE", "quoteAsset": "USDT"},
    "GMTUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "GMT", "quoteAsset": "USDT"},
    "OPUSDT": {"underlyingType": "COIN", "underlyingSubType": [], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "OP", "quoteAsset": "USDT"},
    "XAUTUSDT": {"underlyingType": "COMMODITY", "underlyingSubType": ["TradFi"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "XAU", "quoteAsset": "USDT"},
    "DIAUSDT": {"underlyingType": "EQUITY", "underlyingSubType": ["TradFi", "ETF"], "contractType": "PERPETUAL", "status": "TRADING", "baseAsset": "DIA", "quoteAsset": "USDT"},
}

# 全域 symbol_map（Demo 模式直接使用靜態數據）
symbol_map = _STATIC_SYMBOL_MAP


def build_symbol_map(exchange_data: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Demo 版本：直接回傳靜態映射，不接受 exchange_data。
    保留此函數簽名以兼容完整版的 import。
    """
    return _STATIC_SYMBOL_MAP


def classify_symbol(symbol: str, symbol_map: Optional[Dict[str, Dict]] = None) -> str:
    """
    根據分類判斷市場類別。

    Returns:
        "TRADFI" | "CRYPTO" | "UNKNOWN"
    """
    if symbol_map is None:
        symbol_map = _STATIC_SYMBOL_MAP

    if not symbol or not symbol_map:
        return "UNKNOWN"

    info = symbol_map.get(symbol)
    if not info:
        return "UNKNOWN"

    sub_types = info.get("underlyingSubType", [])
    if "TradFi" in sub_types:
        return "TRADFI"

    return "CRYPTO"


def get_tradfi_category(symbol: str, symbol_map: Optional[Dict[str, Dict]] = None) -> str:
    """
    獲取更細緻的 TradFi 分類。
    如果不是 TradFi 回傳 "CRYPTO"。

    Returns:
        "貴金屬" | "大宗商品" | "美股" | "韓股" | "ETF" | "Pre-IPO" | "CRYPTO"
    """
    if symbol_map is None:
        symbol_map = _STATIC_SYMBOL_MAP

    if not symbol or not symbol_map:
        return "UNKNOWN"

    info = symbol_map.get(symbol)
    if not info:
        return "UNKNOWN"

    sub_types = info.get("underlyingSubType", [])
    underlying_type = info.get("underlyingType", "")

    if "TradFi" not in sub_types:
        return "CRYPTO"

    # ETF
    if "ETF" in sub_types:
        return "ETF"

    # Pre-IPO
    if "Pre-IPO" in sub_types:
        return "Pre-IPO"

    # 根據 underlyingType 分類
    if underlying_type == "COMMODITY":
        base = symbol.replace("USDT", "")
        if base in ("XAU", "XAG", "XPT", "XPD"):
            return "貴金屬"
        return "大宗商品"

    if underlying_type == "KR_EQUITY":
        return "韓股"

    if underlying_type in ("EQUITY", "PREMARKET"):
        return "美股"

    return "TRADFI"


def is_tradfi(symbol: str, symbol_map: Optional[Dict[str, Dict]] = None) -> bool:
    """快速檢查是否為 TradFi 資產"""
    return classify_symbol(symbol, symbol_map) == "TRADFI"


def get_all_tradfi_symbols(symbol_map: Optional[Dict[str, Dict]] = None) -> List[str]:
    """獲取所有 TradFi symbol 列表"""
    if symbol_map is None:
        symbol_map = _STATIC_SYMBOL_MAP
    return [
        sym for sym, info in symbol_map.items()
        if "TradFi" in info.get("underlyingSubType", [])
    ]
