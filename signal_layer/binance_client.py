import httpx
import pandas as pd
from typing import List

class BinanceClient:
    def __init__(self):
        self.base_url = "https://fapi.binance.com"

    async def get_klines(self, symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
        url = f"{self.base_url}/fapi/v1/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
        df = df[["open_time", "open", "high", "low", "close", "volume"]].astype(float)
        return df