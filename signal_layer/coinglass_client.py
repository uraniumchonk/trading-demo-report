import httpx
from typing import Dict, Any, Optional, List
import logging
import pandas as pd
from aiolimiter import AsyncLimiter
import asyncio
logger = logging.getLogger(__name__)

# 用於查詢可用的時間範圍
class coinGlassUserLevel:
    def __init__(self, symbol: str, level: int):
        self.level = level
        self.symbol = symbol
        
    def get_time_range_available(self) -> str:
        supported_time_ranges = ["30m", "6h", "8h", "12h", "1d", "1w"]
        return supported_time_ranges  # 預設為第一個可用的時間範圍
    
class CoinGlassClient:
    def __init__(self, api_key: str):
        self.base_url = "https://open-api-v4.coinglass.com"
        self.headers = {
            "CG-API-KEY": api_key,
            "accept": "application/json"
        }
        self.timeout = 45
        self.limiter = AsyncLimiter(13, 10)
        self._semaphore = asyncio.Semaphore(2)
        
    def _parse_interval_to_ms(self, interval: str) -> int:
        """將 interval 字串轉成毫秒"""
        unit = interval[-1]
        num = int(interval[:-1]) if interval[:-1].isdigit() else 1
        
        if unit == 'm':
            return num * 60 * 1000
        elif unit == 'h':
            return num * 60 * 60 * 1000
        elif unit == 'd':
            return num * 24 * 60 * 60 * 1000
        elif unit == 'w':
            return num * 7 * 24 * 60 * 60 * 1000
        else:
            return 60 * 60 * 1000  # 預設 1 小時
        
    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """統一請求方法 + Rate Limit + Semaphore"""
        url = f"{self.base_url}{endpoint}"
        
        async with self._semaphore:                  # 限制同時並發
            async with self.limiter:                 # Rate Limit（最核心）
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        resp = await client.get(url, headers=self.headers, params=params)
                        
                        if resp.status_code == 429:
                            logger.warning(f"🚨 CoinGlass Rate Limit 觸發！正在等待重試... {endpoint}")
                            await asyncio.sleep(5)   # 被限流時多等一下
                            # 可再加 exponential backoff
                            return {"error": "rate_limited"}
                        
                        if resp.status_code == 401:
                            return {"error": "upgrade_plan", "msg": "請升級方案"}
                        
                        resp.raise_for_status()
                        data = resp.json()
                        
                        if data.get("code") != "0":
                            return {"error": data.get("msg"), "raw": data}
                        return data
                        
                except Exception as e:
                    logger.error(f"Request failed {endpoint}: {e}")
                    return {"error": str(e)}    
    # ====================== 基礎資料處裡 ======================
    # 該幣的可用交易所列表
    async def get_exchanges(self, symbol: str) -> List[str]:
        """取得該幣的可用交易所列表"""
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")
        data = await self._get("/api/futures/pairs-markets", {"symbol": symbol})
        if "error" in data:
            return []
        exchanges = set()
        for item in data.get("data", []):
            exchange_name = item.get("exchange_name")
            if exchange_name:
                exchanges.add(exchange_name.lower())
        return list(exchanges)

    # ====================== 核心資料大全 ======================
    
    async def get_prices(self, symbol: str, interval: str = "1h", limit: int = 100) -> Dict[str, Any]:
        """取得原始價格"""
        data = await self._get("/api/futures/price/history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange": "binance"
        })
        return data
    
    async def get_price_history_time_window(
        self,
        symbol: str,
        interval: str = "30m",
        limit: int = 15,
        start_time: int = 0,          # 尖峰時間 (毫秒)
        window_size: int = 3,         # 查詢幾個窗口，建議用奇數（例如 15 = 前7 + 後7 + 當前）
        exchanges: list = ["binance"]
        ) -> List[Dict]:
        """
        接受一個開始時間（通常是尖峰時間），以 interval 計算窗口，
        回傳前後區間的 K 線資料，尖峰時間落在中間位置。
        """
        if window_size < 1:
            raise ValueError("window_size must be at least 1")

        interval_ms = self._parse_interval_to_ms(interval)

        # 計算真正的開始時間（讓尖峰落在回傳資料的中間）
        # window_size = 15 → 取前 7 個窗口 + 後 7 個窗口
        periods_before = (window_size - 1) // 2 * limit
        real_start_time = start_time - periods_before * interval_ms

        # 第一次抓取
        response = await self._get("/api/futures/price/history", {
            "symbol": symbol,
            "exchange": "binance",
            "interval": interval,
            "limit": limit,
            "start_time": real_start_time
        })
        # 轉成統一格式
        # data': [{'time': 1776103200000, 'open': '0.58514', 'high': '0.5894', 'low': '0.57127', 'close': '0.58034', 'volume_usd': '940927.9049'}]
        historical_data = []
        for data in response["data"]:
            historical_data.append({
                "time_date": pd.to_datetime(data["time"], unit="ms").strftime("%Y-%m-%d %H:%M"),
                "time": data["time"],
                "open": data["open"],
                "low": data["low"],
                "high": data["high"],
                "close": data["close"],
                "volume_usd": data["volume_usd"]
            })

        return historical_data

    async def get_oi_history(self, symbol: str, interval: str = "30m", limit: int = 20) -> Dict:
        """取得 Open Interest 歷史（用來計算 Delta）"""
        return await self._get("/api/futures/open-interest/history", {
            "symbol": symbol,            "interval": interval,
            "limit": limit,

            "exchange": "binance"
        })
    
    async def get_oi_history_crossAll(self, symbol: str, interval: str = "30m", limit: int = 20) -> Dict:
        """取得 Open Interest 歷史（用來計算 Delta）"""
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")
        return await self._get("/api/futures/open-interest/aggregated-stablecoin-history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange": "binance"
        })

    async def get_oi_delta(self, symbol: str, interval: str = "30m") -> Optional[float]:
        """計算最新 OI Delta（最新 - 前一個）"""
        try:
            data = await self.get_oi_history(symbol, interval=interval, limit=10)

            # 先檢查有沒有錯誤或沒資料
            if isinstance(data, dict) and "error" in data:
                logger.error(f"CoinGlass Error for {symbol}: {data['error']}")
                return 0.0

            if not data.get("data") or len(data["data"]) < 2:
                logger.error(f"Not enough history data for {symbol}")
                return 0.0

            history = data["data"]

            # 【關鍵修正】使用 float() 強制轉換，並處理可能的 None 值
            # 我們先用 get 拿到值，如果拿到 None，就給 0.0
            raw_latest = history[-1].get("close") or history[-1].get("oi") or 0
            raw_previous = history[-2].get("close") or history[-2].get("oi") or 0

            # 強制轉成 float，這樣就算 API 給的是 "123.45" 字串，也能正確運算。
            latest = float(raw_latest)
            previous = float(raw_previous)

            # 現在進行減法就不會噴錯了。
 
            delta = latest - previous
            return round(delta, 2)

        except Exception as e:
            # 這裡要小心，您的舊代碼裡 logger 用了 e 但沒定義 e，我幫您補上了
            logger.error(f"Error occurred while fetching OI history for {symbol}: {e}")
            return 0.0

    async def get_futures_aggregated_volume(self, symbol: str, exchange_list: list = ["binance"], interval: str = "30m", limit: int = 10) -> Dict:
        """全市場合約成交量（Aggregated Taker Buy/Sell Volume）"""
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")

        return await self._get("/api/futures/aggregated-taker-buy-sell-volume/history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange_list": exchange_list  # 這裡我們指定只看 Binance 的資料，避免跨交易所的問題。
        })

    async def get_spot_aggregated_volume(self, symbol: str, exchange_list: list = ["binance"], interval: str = "30m", limit: int = 10) -> Dict:
        """全市場現貨成交量"""
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")
        return await self._get("/api/spot/aggregated-taker-buy-sell-volume/history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange_list": exchange_list  # 這裡我們指定只看 Binance 的資料，避免跨交易所的問題。
        })
    
    async def get_funding_rate(self, symbol: str, interval: str = "30m", limit: int = 4) -> Optional[float]:
        """取得最新資金費率"""
        data = await self._get("/api/futures/funding-rate/history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange": "binance"
        })
        if "error" in data or not data.get("data"):
            return None
        
        return data
    
    async def get_funding_IO_rate(self, symbol: str, interval: str = "30m", limit: int = 4) -> Optional[float]:
        """取得最新IO加權資金費率"""
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")

        data = await self._get("/api/futures/funding-rate/oi-weight-history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        })
        if "error" in data or not data.get("data"):
            return None
        
        return data

    async def get_top_long_short_ratio(self, symbol: str, interval: str = "30m", limit: int = 10) -> Dict:
        """
        修正：如果報錯 pair 不存在，通常是因為缺少 exchange 參數或 symbol 格式不對。
        我們嘗試加入常見的參數組合。
        """
        # 有些 API 需要指定 exchange，這裡我們先嘗試標準的 symbol 傳入
        data = await self._get("/api/futures/top-long-short-account-ratio/history", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange": "binance"  # 嘗試加入 exchange 參數，看看能不能解決問題。
        })
        if "error" in data or not data.get("data"):
            return None

        return data

    async def get_liquidation(self, symbol: str, exchanges: list = ["binance"], interval: str = "1d", limit: int = 10) -> Dict:
        """
        修正：補上強制要求的 'exchange_list' 參數。
        例如: exchange_list="binance,okx"
        """
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")

        data = await self._get("/api/futures/liquidation/aggregated-history", {
            "symbol": symbol,
            "exchange_list": exchanges,  # <--- 補上這行。
            "interval": interval,
            "limit": limit
        })
        return data

    async def get_taker_volume(self, symbol: str, exchanges: list = ["binance"], interval: str = "1d", limit: int = 10) -> Dict:
        """
        修正：同樣補上 'exchange_list'。
        """
        # 對於跨交易所 跨交易對的指標，CoinGlass 通常要求 symbol 不帶交易對後綴，並且需要指定 exchange_list 參數。
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")

        data = await self._get("/api/futures/aggregated-taker-buy-sell-volume/history", {
            "symbol": symbol,
            "exchange_list": exchanges,
            "interval": interval,
            "limit": limit
        })
        return data
    
    async def get_supported_coins(self) -> List[str]:
        data = await self._get("/api/futures/supported-coins")
        if "error" in data:
            return []
        return [item["symbol"] for item in data.get("data", [])]

    async def get_pairs_markets(self, symbol: str) -> List[Dict]:
        symbol = symbol.upper()
        symbol = symbol.replace("USDT", "")
        data = await self._get("/api/futures/pairs-markets",
            {"symbol": symbol}
        )
        # data太長了 先過濾出Binance的資料"exchange_name": "Binance",
        data = {
            "data": [item for item in data.get("data", []) if item.get("exchange_name", "").lower() == "binance"]
        }
        # data東西有點多 btc只需要btcusdt的資料就好 其他的幣種也是一樣的邏輯 "instrument_id": "BTCUSDT",  "instrument_id": "BTCUSDC",
        data = {
            "data": [item for item in data.get("data", []) if item.get("instrument_id", "").upper() == symbol + "USDT"]
        }

        if "error" in data:
            return []
        return data.get("data", [])

    # api/calendar/economic-data
    async def get_economic_data(self) -> Dict:
        '''獲取經濟數據日曆，這個接口可以幫助我們了解即將發布的經濟數據事件，對於宏觀分析非常有用。'''
        data = await self._get("/api/calendar/economic-data")
        if "error" in data:
            return {}
        return data.get("data", {})
    # api/article/list
    async def get_articles(self, symbol: str, limit: int = 5) -> List[Dict]:
        '''新聞，這個接口可以幫助我們了解市場情緒和最新動態。'''
        data = await self._get("/api/article/list")
        if "error" in data:
            return {}
        return data.get("data", {})
    
    
        '''獲取價格歷史數據，用於技術指標計算。'''
    # ====================== 指標大禮包 ======================
    # https://open-api-v4.coinglass.com/api/futures/indicators/boll
    # https://open-api-v4.coinglass.com/api/futures/indicators/ma
    # https://open-api-v4.coinglass.com/api/futures/indicators/ema
    # https://open-api-v4.coinglass.com/api/futures/indicators/boll
    # https://open-api-v4.coinglass.com/api/futures/indicators/macd
    # https://open-api-v4.coinglass.com/api/futures/indicators/avg-true-range
    # https://open-api-v4.coinglass.com/api/futures/indicators/td
    #這些東西長的一膜一樣 就不一一寫了 只要把 endpoint 換掉就好。 寫一個返回全部的 還有一個特定選取的
    async def get_technical_indicators(self, symbol: str, interval: str = "30m", limit: int = 10) -> Dict[str, Any]:
        '''獲取技術指標大禮包，這個接口可以幫助我們快速獲取多種技術指標的數據，方便我們進行綜合分析。'''
        endpoints = [
            "/api/futures/indicators/boll",
            "/api/futures/indicators/ma",
            "/api/futures/indicators/ema",
            "/api/futures/indicators/macd",
            "/api/futures/indicators/td",
            "/api/futures/indicators/avg-true-range",
            "/api/futures/indicators/rsi"
        ]
        results = {}
        for endpoint in endpoints:
            data = await self._get(endpoint, {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
                "exchange": "binance"
            })
            if "error" in data:
                results[endpoint] = {"error": data["error"]}
            else:
                results[endpoint] = data.get("data", {})
        return results
    
    async def get_indicator(self, symbol: str, indicator: str, interval: str = "30m", limit: int = 10) -> Dict[str, Any]:
        '''獲取特定技術指標，這個接口可以幫助我們快速獲取指定技術指標的數據，方便我們進行針對性分析。'''
        endpoint_map = {
            "boll": "/api/futures/indicators/boll",
            "ma": "/api/futures/indicators/ma",
            "ema": "/api/futures/indicators/ema",
            "macd": "/api/futures/indicators/macd",
            "td": "/api/futures/indicators/td",
            "atr": "/api/futures/indicators/avg-true-range",
            "rsi": "/api/futures/indicators/rsi"
        }
        endpoint = endpoint_map.get(indicator.lower())
        if not endpoint:
            return {"error": f"不支持的指標 {indicator}。{'支持的指標': list(endpoint_map.keys())}"}
        
        data = await self._get(endpoint, {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
            "exchange": "binance"
        })
        if "error" in data:
            return {"error": data["error"]}
        return data.get("data", {})

    # ====================== 範例：一次抓多個指標 ======================
    async def get_many_indicators(self, symbol: str, exchange: str = "binance") -> Dict[str, Any]:
        """
        一次取得指標，並處理好可能的 null 值或錯誤。
        """
        # 我們使用 asyncio.gather 來並行請求，速度會快非常多。
        import asyncio
        interval = "30m"
        exchanges = await self.get_exchanges(symbol)
        tasks = {
            "oi_delta": self.get_oi_delta(symbol = symbol, interval=interval),
            "funding_rate": self.get_funding_rate(symbol = symbol, interval=interval),
            "oi_weighted_funding_rate": self.get_funding_IO_rate(symbol = symbol, interval=interval),
            "top_ls_ratio": self.get_top_long_short_ratio(symbol = symbol),
            "liquidation": self.get_liquidation(symbol = symbol, exchanges=[exchange]),
            "taker_volume": self.get_taker_volume(symbol = symbol, exchanges=[exchange]),
            "get_pairs_markets-rate": self.get_pairs_markets(symbol),
            "get_spot_aggregated_volume": self.get_spot_aggregated_volume(symbol = symbol, interval=interval, exchange_list=exchanges, limit=10),
            "get_futures_aggregated_volume": self.get_futures_aggregated_volume(symbol = symbol, interval=interval, exchange_list=exchanges, limit=10),
            "get_technical_indicators": self.get_technical_indicators(symbol = symbol, interval=interval, limit=10),
            "get_technical_indicator_macd": self.get_indicator(symbol = symbol, indicator="macd", interval=interval, limit=100),
            "get_technical_indicator_rtv": self.get_indicator(symbol = symbol, indicator="atr", interval=interval, limit=100)
        }

        results = {}

        for key, task in tasks.items():
            try:
                res = await task

    # 情況 A: 如果回傳的是 Exception (因為 gather 的 return_exceptions=True)
                if isinstance(res, Exception):
                    results[key] = None
                    continue

                # 情況 B: 如果回傳的是包含 error 的字典 (API 級別的錯誤)
                if isinstance(res, dict) and "error" in res:
                    results[key] = None # 不要把錯誤字串塞進數值欄位，直接設為 None
                    continue

    # 情況 C: 如果 API 回傳的是 {"data": 0.001} 這種格式，我們要提取它
    # 這點很重要！很多 API 不會直接回傳數字
                if isinstance(res, dict) and "data" in res:
                    results[key] = res["data"]
                elif isinstance(res, dict) and len(res) == 1 and list(res.values())[0] is not None: 
    # 如果字典只有一個 key，通常那個 value 就是我們要的數值
    # 例如 {"value": 0.05} -> 0.05
                    results[key] = list(res.values())[0]
                else:
                    results[key] = res

            except Exception:
                results[key] = None
        
        return results      
