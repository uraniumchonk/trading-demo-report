from datetime import datetime
from typing import Dict
import pandas as pd
import pandas_ta as ta
import numpy as np
from scipy import stats
from typing import Any, List, Dict, Optional
from scipy.signal import argrelextrema
import asyncio
from .coinglass_client import CoinGlassClient
from dataclasses import dataclass


class SignalCalculator:
    def __init__(self, cg_client: "CoinGlassClient"):
        self.cg_client = cg_client
        self.analyzer = MultiTFAnalyzer(self.cg_client)

    async def futures_D_spot_ratio(
            self, symbol: str, interval: str = "4h", 
            limit: int = 168,
            spike_method: str = "zscore",
            zscore_threshold: float = 3.5) -> Dict:
        """
        計算 Aggregated Futures/Spot Volume Ratio + 完整統計
        修正版：使用正確的欄位名稱 aggregated_buy_volume_usd + aggregated_sell_volume_usd
        """
        cg_client = self.cg_client

        # 1. 抓資料
        exchanges = await cg_client.get_exchanges(symbol)
        fut = await cg_client.get_futures_aggregated_volume(symbol=symbol, exchange_list=exchanges, interval=interval, limit=limit)
        spot = await cg_client.get_spot_aggregated_volume(symbol=symbol, exchange_list=exchanges, interval=interval, limit=limit)

        if "error" in fut or "error" in spot:
            return {"symbol": symbol, "error": "資料抓取失敗"}
        if len(fut["data"]) == 0 or len(spot["data"]) == 0:
            return {"symbol": symbol, "error": "無有效數據 可能沒上現貨或合約"}
        # 2. 轉成 DataFrame
        fut_df = pd.DataFrame(fut["data"])
        spot_df = pd.DataFrame(spot["data"])

        # === 關鍵修正：使用正確欄位 ===
        fut_df["futures_vol"] = fut_df["aggregated_buy_volume_usd"] + fut_df["aggregated_sell_volume_usd"]
        spot_df["spot_vol"] = spot_df["aggregated_buy_volume_usd"] + spot_df["aggregated_sell_volume_usd"]

        # 合併（以 time 為 key）
        df = pd.merge(
            fut_df[["time", "futures_vol"]], 
            spot_df[["time", "spot_vol"]], 
            on="time", 
            how="inner"
        )

        # 計算 Ratio（避免除以 0）
        df["ratio"] = df["futures_vol"] / df["spot_vol"].replace(0, np.nan)
        df = df.dropna(subset=["ratio"])

        ratio_series = df["ratio"]

        if len(ratio_series) == 0:
            return {"symbol": symbol, "error": "無有效數據"}

        # 3. 基礎統計
        stats_result = {
            "symbol": symbol,
            "periods": len(ratio_series),
            "mean": round(ratio_series.mean(), 2),
            "median": round(ratio_series.median(), 2),
            "std": round(ratio_series.std(), 2),
            "min": round(ratio_series.min(), 2),
            "max": round(ratio_series.max(), 2),
            "p95": round(ratio_series.quantile(0.95), 2),
            "p99": round(ratio_series.quantile(0.99), 2),
        }

        # 4. 尖峰極端值檢測
        if spike_method == "zscore":
            z_scores = np.abs(stats.zscore(ratio_series))
            spikes = ratio_series[z_scores > zscore_threshold]
            stats_result["spike_count"] = len(spikes)
            stats_result["spike_ratio"] = round(len(spikes) / len(ratio_series) * 100, 2)
            stats_result["spike_values"] = [round(v, 2) for v in spikes.tail(5).tolist()]

        elif spike_method == "iqr":
            Q1 = ratio_series.quantile(0.25)
            Q3 = ratio_series.quantile(0.75)
            IQR = Q3 - Q1
            spikes = ratio_series[(ratio_series < (Q1 - 1.5 * IQR)) | (ratio_series > (Q3 + 1.5 * IQR))]
            stats_result["spike_count"] = len(spikes)
            stats_result["spike_ratio"] = round(len(spikes) / len(ratio_series) * 100, 2)

        elif spike_method == "winsorize":
            winsorized = stats.mstats.winsorize(ratio_series, limits=[0.01, 0.01])
            stats_result["winsorized_mean"] = round(np.mean(winsorized), 2)

        elif spike_method == "log":
            log_ratio = np.log1p(ratio_series)
            stats_result["log_mean"] = round(log_ratio.mean(), 2)
            stats_result["log_std"] = round(log_ratio.std(), 2)

        # 5. 最近趨勢
        stats_result["latest_ratio"] = round(ratio_series.iloc[-1], 2)
        if len(ratio_series) >= 24:
            stats_result["ratio_change_24h"] = round(
                (ratio_series.iloc[-1] - ratio_series.iloc[-24]) / ratio_series.iloc[-24] * 100, 1
            )
        else:
            stats_result["ratio_change_24h"] = None

        # 6. 回傳最近 50 筆（方便畫圖或後續使用）
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        recent_df = df[["time", "ratio", "futures_vol", "spot_vol"]].tail(50)

        return {
            "stats": stats_result,
            "recent_data": recent_df.to_dict("records")
        }
    
    async def get_MFI(self, symbol: str, interval: str = "30m", limit: int = 100):
        """計算 MFI 指標 — 使用 CoinGlass 取得 K 線後自行計算"""
        cg_client = self.cg_client
        period = 14
        limit = limit + period
        data = await cg_client.get_prices(symbol=symbol, interval=interval, limit=limit)
        data = data["data"]
        df = pd.DataFrame(data)

        # 轉成數值
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume_usd'], errors='coerce')

        # === MFI 核心計算 ===
        df['tp'] = (df['high'] + df['low'] + df['close']) / 3          # 典型價格
        df['rmf'] = df['tp'] * df['volume']                             # 原始金錢流量

        # 正負金錢流量
        df['positive_flow'] = df['rmf'].where(df['tp'] > df['tp'].shift(1), 0.0)
        df['negative_flow'] = df['rmf'].where(df['tp'] < df['tp'].shift(1), 0.0)

        # 14 期滾動加總
        positive_sum = df['positive_flow'].rolling(window=period, min_periods=period).sum()
        negative_sum = df['negative_flow'].rolling(window=period, min_periods=period).sum()

        # MFR 與 MFI
        mfr = positive_sum / negative_sum
        df['mfi'] = 100 - (100 / (1 + mfr))

        # 回傳結果（只留重要欄位）
        result = df[['time', 'close', 'mfi']].copy()
        result['mfi'] = result['mfi'].round(2)   # 保留兩位小數
        result = result.replace({np.nan: None}) 
        # 將資料轉為 list[{'time': ..., 'close': ..., 'mfi': ...},]
        result = result.to_dict(orient='records')
        # 移除mfi為none的資料項目
        result = [item for item in result if item['mfi'] is not None]
        return result

    async def get_RSI(self, symbol: str, interval: str = "30m", limit: int = 100) -> Dict[str, Any]:
        """計算 RSI 指標 — 透過 CoinGlass API 取得 RSI 數據"""
        try:
            cg_client = self.cg_client
            # 30m RSI
            rsi = await cg_client.get_indicator(symbol=symbol, interval=interval, limit=limit, indicator="rsi")
            return rsi
        except Exception as e:
            return {"error": str(e)}
        
    async def get_MACD(self, symbol: str, interval: str = "30m", limit: int = 300) -> Dict[str, Any]:
        """計算 MACD 指標 — 透過 CoinGlass API 取得 MACD 數據"""
        try:
            cg_client = self.cg_client
            macd = await cg_client.get_indicator(symbol=symbol, interval=interval, limit=limit, indicator="macd")
            macd = [item for item in macd if "histogram" in item]
            return macd
        except Exception as e:
            return {"error": str(e)}
    
    async def singals_RMMA_entry(self, symbol: str, interval: str = "30"):
        mfi_list = await self.get_MFI(symbol=symbol, interval=interval)
        rsi_list = await self.get_RSI(symbol=symbol, interval=interval)
        macd_list = await self.get_MACD(symbol=symbol, interval=interval)
                
        interList = [mfi_list, rsi_list, macd_list]
        if len(interList[0]) == 0 or len(interList[1]) == 0 or len(interList[2]) == 0:
            return {"error": "資料不足"}
        result = await self.analyzer.analyze(symbol, interData=interList)
        return result
    
        # async def R_M_M_A_entry(self, symbol: str, swing_window: int = 6, interval: str = "30m") -> Dict[str, Any]:
    #     """
    #     進階版：多波段高低點 + 支撐阻力區間 + 多指標確認
    #     """
    #     try:
    #         # === 1. 抓取基礎指標資料 ===
    #         mfi_list = await self.get_MFI(symbol=symbol, interval=interval)
    #         rsi_list, macd_list = await self.get_R_M_A(symbol=symbol, interval=interval)

    #         if len(mfi_list) < 8:
    #             return {"phase": "資料不足", "trend": "unknown"}

    #         # === 2. 使用新 API 抓取歷史價格（重點！）===
    #         # 取最新一根的 time 當作中心點
    #         latest_time = mfi_list[-1]["time"]
            
    #         historical_price = await self.cg_client.get_price_history_time_window(
    #             symbol=symbol,
    #             interval=interval,
    #             limit=60,                    # 抓 40 根 30m（約 20 小時）
    #             start_time=latest_time,
    #             window_size=41               # 前後各抓一些
    #         )
    #         latest_price = await self.cg_client.get_prices(symbol=symbol, interval="30m", limit=1)
    #         latest_price = (float(latest_price["data"][0]["close"]) + float(latest_price["data"][0]["open"])) / 2
    #         latest_price = round(latest_price, 8)
            
    #         # === 3. 合併所有資料 ===
    #         df = pd.DataFrame(mfi_list)
    #         df_rsi = pd.DataFrame(rsi_list)
    #         df_macd = pd.DataFrame(macd_list)
    #         df_hist = pd.DataFrame(historical_price)   # ← 新增歷史價格

    #         # 強制 time 為 int64
    #         for d in [df, df_rsi, df_macd, df_hist]:
    #             d['time'] = d['time'].astype('int64')

    #         # 合併
    #         df = df.merge(df_rsi, on='time', how='left')
    #         df = df.merge(df_macd, on='time', how='left')
    #         df = df.merge(df_hist[['time', 'high', 'low']], on='time', how='left')  # 加入 high/low
    #         df = df.sort_values('time').reset_index(drop=True)
    #         df = df.ffill().bfill()

    #         # === 4. 偵測多個波段高低點 ===
    #         closes = df['close'].values
    #         max_idx = argrelextrema(closes, np.greater, order=swing_window)[0]
    #         min_idx = argrelextrema(closes, np.less, order=swing_window)[0]

    #         # 取最近 3 個高點與低點
    #         swing_highs = [round(df.loc[i, 'close'], 6) for i in max_idx[-3:]] if len(max_idx) >= 3 else []
    #         swing_lows = [round(df.loc[i, 'close'], 6) for i in min_idx[-3:]] if len(min_idx) >= 3 else []

    #         latest_swing_high = swing_highs[-1] if swing_highs else None
    #         latest_swing_low = swing_lows[-1] if swing_lows else None

    #         # === 5. 計算支撐阻力區間 ===
    #         support_zone     = sorted([float(x) for x in swing_lows])[:2] if len(swing_lows) >= 2 else []
    #         resistance_zone  = sorted([float(x) for x in swing_highs], reverse=True)[:2] if len(swing_highs) >= 2 else []
            
    #         # === 6. 最新指標 ===
    #         latest = df.iloc[-1]
    #         latest_close = latest['close']
    #         latest_mfi = latest['mfi']
    #         latest_rsi = latest.get('rsi_value')
    #         latest_rsi = round(latest_rsi, 2)
    #         latest_macd_hist = latest.get('histogram', 0)
    #         latest_10_mfi = df['mfi'].tail(10).tolist()  # 最近10筆MFI
    #         latest_10_mfi.reverse()
    #         latest_10_rsi = df['rsi_value'].tail(10).tolist()  # 最近10筆RSI
    #         latest_10_rsi.reverse()
    #         # rsi 做round,2
    #         latest_10_rsi = [round(x, 2) for x in latest_10_rsi] 
            
    #         # === 7. 進階階段判斷 ===
    #         phase = "橫盤整理中"
    #         divergence = "無明顯背離"

    #         near_resistance = latest_swing_high and latest_close >= latest_swing_high * 0.985
    #         near_support = latest_swing_low and latest_close <= latest_swing_low * 1.015
            
    #         if near_resistance and latest_mfi > 70 and latest_macd_hist < 0:
    #             phase = f"觸頂下降中（頂點: {latest_swing_high}）"
    #             divergence = "看跌背離"
    #         elif near_support and latest_mfi < 35 and latest_macd_hist > 0:
    #             phase = f"底部反彈中（前低: {latest_swing_low}）"
    #             divergence = "看漲背離"
    #         elif latest_mfi > 65 and latest_macd_hist > 0:
    #             phase = f"上升中（支撐: {support_zone}）"
    #         elif latest_mfi < 35 and latest_macd_hist < 0:
    #             phase = f"下降中（阻力: {resistance_zone}）"
    #         else:
    #             phase = "橫盤震盪中"
            
    #         rsi_mfi_diff = round(latest_mfi - latest_rsi, 2)
    #         if latest_mfi > 50 and latest_rsi > 50:
    #             rsi_mfi_anays = "rsi mfi同向上"
    #         elif latest_mfi > 50 and latest_rsi < 50:
    #             rsi_mfi_anays = f'rsi: {latest_rsi} mfi {latest_mfi} 差值{rsi_mfi_diff}'
    #             if latest_mfi - latest_rsi > 20:
    #                 rsi_mfi_anays = f'rsi: {latest_rsi} mfi {latest_mfi} 背離嚴重 差值{rsi_mfi_diff}'
    #         elif latest_mfi < 50 and latest_rsi > 50:
    #             rsi_mfi_anays = f'rsi: {latest_rsi} mfi {latest_mfi} 差值{rsi_mfi_diff}'
    #             if latest_mfi - latest_rsi < -20:
    #                 rsi_mfi_anays = f'rsi: {latest_rsi} mfi {latest_mfi} 背離嚴重 差值{rsi_mfi_diff}'
    #         elif latest_mfi < 50 and latest_rsi < 50:
    #             rsi_mfi_anays = "rsi mfi同在下"
    #         else:
    #             rsi_mfi_anays = "其他"
                
    #         return {
    #             "time_window": interval,
    #             "phase": phase,
    #             "trend": "指標向上" if latest_macd_hist > 0 else "指標向下" if latest_macd_hist < 0 else "指標橫盤",
    #             "mfi_macd_divergence": divergence,
    #             "rsi_mfi_divergence": rsi_mfi_anays,
    #             "swing_highs": swing_highs,           # 多個頂點
    #             "swing_lows": swing_lows,             # 多個低點
    #             "support_zone": support_zone,         # 短期支撐區
    #             "resistance_zone": resistance_zone,   # 短期阻力區
    #             "latest_swing_high": latest_swing_high,
    #             "latest_swing_low": latest_swing_low,
    #             "latest_price": latest_price,
    #             "latest_close": round(latest_close, 2),
    #             "latest_mfi": round(latest_mfi, 2),
    #             "latest_rsi": round(latest_rsi, 2) if latest_rsi else None,
    #             "latest_macd_histogram": round(latest_macd_hist, 2),
    #             "latest_10_mfi": latest_10_mfi,
    #             "latest_10_rsi": latest_10_rsi,
    #         }

    #     except Exception as e:
    #         return {"error": f"分析失敗: {str(e)}"}
            

class MarketState:
    def __init__(self, direction="neutral", score=0, message=""):
        self.direction = direction
        self.score = score
        self.message = message

class MultiTFAnalyzer:
    def __init__(self, cg_client):
        self.cg_client = cg_client
        self.symbol = ""
        self.interval = ""

    # === 核心入口 ===

    async def analyze(self, symbol: str, interval: str = "30m", interData: list = []) -> Dict[str, Any]:
        """
        主入口：執行多週期共振分析
        """
        self.symbol = symbol
        self.interval = interval

        try:
            # === 正確的 asyncio.gather 寫法 ===
            l1_task = self._get_l1_trend(symbol)
            l2_task = self._get_l2_context(symbol, "1h")
            l3_task = self._get_l3_trigger(symbol, interval, interData=interData)

            results = await asyncio.gather(l1_task, l2_task, l3_task)

            l1_data, l2_data, l3_data = results

            # 2. 計算共振得分與最終結論
            decision = self._calculate_confluence(l1_data, l2_data, l3_data)

            # 3. 封裝結構化輸出
            return {
                "symbol": symbol,
                "timestamp": pd.Timestamp.now().isoformat(),
                "summary": {
                    "decision": decision.direction,
                    "score": decision.score,
                    "message": decision.message,
                    "action": "BUY" if decision.score >= 3 else "SELL" if decision.score <= -3 else "HOLD"
                },
                "layers": {
                    "L1_Trend_4H": l1_data,
                    "L2_Context_1H": l2_data,
                    "L3_Trigger_30m": l3_data
                }
            }

        except Exception as e:
            return {"error": f"分析引擎崩潰: {str(e)}", "traceback": True}
    # === L1: 大週期趨勢層 (4H) ===

    async def _get_l1_trend(self, symbol: str) -> Dict[str, Any]:
        """
        判斷大週期方向：使用 EMA200
        """
        hist = await self.cg_client.get_price_history_time_window(
            symbol=symbol, interval="4h", limit=300
        )
        df = pd.DataFrame(hist)
        df['close'] = df['close'].astype(float)

        # EMA200
        ema200 = df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
        current_price = df['close'].iloc[-1]

        direction = "neutral"
        if current_price > ema200:
            direction = "bullish"
        elif current_price < ema200:
            direction = "bearish"

        return {
            "direction": direction,
            "price": round(current_price, 4),
            "ema200": round(ema200, 4)
        }

    # === L2: 中週期環境層 (1H) ===

    async def _get_l2_context(self, symbol: str, interval: str) -> Dict[str, Any]:
        """
        判斷市場環境：使用布林帶寬度 (BB Width) 判斷是否擠壓
        """
        hist = await self.cg_client.get_price_history_time_window(
            symbol=symbol, interval=interval, limit=100
        )
        df = pd.DataFrame(hist)
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)

        # 計算布林帶
        ma = df['close'].rolling(window=20).mean() 
        std = df['close'].rolling(window=20).std()
        upper_bb = ma + (std * 2)
        lower_bb = ma - (std * 2)

        # BB Width
        bb_width = (upper_bb - lower_bb) / ma
        current_width = bb_width.iloc[-1]
        avg_width = bb_width.rolling(window=50).mean().iloc[-1]

        # 判斷環境
        env = "trending"
        if current_width < avg_width * 0.8:  # 寬度比平均值低 20%
            env = "squeezing"
        elif current_width > avg_width * 1.5:
            env = "volatile"

        return {
            "environment": env,
            "bb_width": round(current_width, 6),
            "avg_width": round(avg_width, 6)
        }

    # === L3: 小週期觸發層 (30m) ===

    async def _get_l3_trigger(self, symbol: str, interval: str, swing_window: int = 6, interData:list = []) -> Dict[str, Any]:
        """
        原本的 MFI + RSI + MACD + Swing Points 邏輯
        """
        try:
            # === 1. 抓取基礎指標資料 ===
            cg_client = self.cg_client
            mfi_list = interData[0]
            rsi_list = interData[1]
            macd_list = interData[2]
            if len(mfi_list) < 8:
                return {"phase": "資料不足", "trend": "unknown"}

            # === 2. 使用 CoinGlass 抓取歷史價格 ===
            # 取最新一根的 time 當作中心點
            latest_time = mfi_list[-1]["time"]
            
            historical_price = await cg_client.get_price_history_time_window(
                symbol=symbol,
                interval=interval,
                limit=60,                    # 抓 40 根 30m（約 20 小時）
                start_time=latest_time,
                window_size=41               # 前後各抓一些
            )
            latest_price = await cg_client.get_prices(symbol=symbol, interval="30m", limit=1)
            latest_price = (float(latest_price["data"][0]["close"]) + float(latest_price["data"][0]["open"])) / 2
            latest_price = round(latest_price, 8)
            
            # === 3. 合併所有資料 ===
            df = pd.DataFrame(mfi_list)
            df_rsi = pd.DataFrame(rsi_list)
            df_macd = pd.DataFrame(macd_list)
            df_hist = pd.DataFrame(historical_price)   # 新增歷史價格

            # 強制 time 為 int64
            for d in [df, df_rsi, df_macd, df_hist]:
                d['time'] = d['time'].astype('int64')

            # 合併
            df = df.merge(df_rsi, on='time', how='left')
            df = df.merge(df_macd, on='time', how='left')
            df = df.merge(df_hist[['time', 'high', 'low']], on='time', how='left')  # 加入 high/low
            df = df.sort_values('time').reset_index(drop=True)
            df = df.ffill().bfill()
            # MACD normalization layer
            # 放在 df = df.ffill().bfill() 之後、偵測波段高低點之前
            if 'histogram' in df.columns and len(df) >= 30:
                window = min(50, len(df) - 1)
                rolling_mean = df['histogram'].rolling(window=window).mean()
                rolling_std = df['histogram'].rolling(window=window).std().replace(0, np.nan)
                
                # Z-Score：代表「相對於這支幣自己過去50根，現在的 MACD 有多極端」
                df['hist_zscore'] = (df['histogram'] - rolling_mean) / rolling_std
                
                latest_macd_hist = df['histogram'].iloc[-1]
                latest_macd_z = round(float(df['hist_zscore'].iloc[-1]), 2) if pd.notna(df['hist_zscore'].iloc[-1]) else 0.0
            else:
                latest_macd_hist = 0.0
                latest_macd_z = 0.0
            # end MACD normalization
            # === 4. 偵測多個波段高低點 ===
            closes = df['close'].values
            max_idx = argrelextrema(closes, np.greater, order=swing_window)[0]
            min_idx = argrelextrema(closes, np.less, order=swing_window)[0]

            # 取最近 3 個高點與低點
            swing_highs = [round(df.loc[i, 'close'], 6) for i in max_idx[-3:]] if len(max_idx) >= 3 else []
            swing_lows = [round(df.loc[i, 'close'], 6) for i in min_idx[-3:]] if len(min_idx) >= 3 else []

            latest_swing_high = swing_highs[-1] if swing_highs else None
            latest_swing_low = swing_lows[-1] if swing_lows else None

            # === 5. 計算支撐阻力區間 ===
            support_zone     = sorted([float(x) for x in swing_lows])[:2] if len(swing_lows) >= 2 else []
            resistance_zone  = sorted([float(x) for x in swing_highs], reverse=True)[:2] if len(swing_highs) >= 2 else []
            
            # === 6. 最新指標 ===
            latest = df.iloc[-1]
            latest_close = latest['close']
            latest_mfi = latest['mfi']
            latest_rsi = latest.get('rsi_value')
            latest_rsi = round(latest_rsi, 2)
            latest_macd_z = latest.get('hist_zscore', 0.0) if 'hist_zscore' in latest else 0.0
            latest_macd_hist = latest.get('histogram', 0.0)            
            latest_10_mfi = df['mfi'].tail(10).tolist()  # 最近10筆MFI
            latest_10_mfi.reverse()
            latest_10_rsi = df['rsi_value'].tail(10).tolist()  # 最近10筆RSI
            latest_10_rsi.reverse()
            # rsi 做round,2
            latest_10_rsi = [round(x, 2) for x in latest_10_rsi] 
            
            # === 7. 進階階段判斷 ===
            # === 1. 初始化 ===
            phase = "橫盤整理中"
            trend = "中性"
            divergence = "無明顯背離"

            # === 2. 偵測 MFI 背離 (優化版) ===
            # 確保至少有兩個高點/低點可以比對
            if len(max_idx) >= 2 and len(min_idx) >= 2:
                # 嘗試偵測看跌背離：價格創新高/接近高點，但 MFI 沒創新高
                prev_high_idx = max_idx[-2] 
            if latest_close >= latest_swing_high * 0.99 and latest_mfi < df['mfi'].iloc[prev_high_idx]:
                divergence = "看跌背離（MFI）"

            # 嘗試偵測看漲背離：價格接近低點，但 MFI 沒創新低
                prev_low_idx = min_idx[-2]
                if latest_close <= latest_swing_low * 1.01 and latest_mfi > df['mfi'].iloc[prev_low_idx]:
                    divergence = "看漲背離（MFI）"

            # === 3. 判斷當前位置 (增加緩衝區) ===
            # 使用 1.5% 的緩衝，避免訊號在邊緣閃爍
            near_resistance = latest_swing_high and latest_close >= latest_swing_high * 0.985
            near_support    = latest_swing_low and latest_close <= latest_swing_low * 1.015

            # === 4. 決定 Phase 與 Trend (層級化判斷) ===
            # 第一層：極端轉折點 (結合 MFI 與 MACD)
            if near_resistance and latest_mfi > 70 and latest_macd_hist < 0:
                phase = f"觸頂看跌（頂點: {latest_swing_high}）"
                trend = "強烈看空"
            elif near_support and latest_mfi < 30 and latest_macd_hist > 0:
                phase = f"觸底看漲（底點: {latest_swing_low}）"
                trend = "強烈看多"

            # 第二層：趨勢確認
            elif latest_mfi > 65 and latest_macd_hist > 0:
                phase = f"多頭趨勢（支撐: {support_zone}）"
                trend = "看多"
            elif latest_mfi < 35 and latest_macd_hist < 0:
                phase = f"空頭趨勢（阻力: {resistance_zone}）"
                trend = "看空"

            # 第三層：偏向判斷 (震盪中的傾向)
            elif latest_macd_hist > 0 and latest_mfi > 50:
                phase = "震盪偏多"
                trend = "偏多"
            elif latest_macd_hist < 0 and latest_mfi < 50:
                phase = "震盪偏空"
                trend = "偏空"
            else:
                phase = "橫盤整理中"
                trend = "中性"

            # === 5. RSI/MFI 差值分析 ===
            rsi_mfi_diff = round(latest_mfi - latest_rsi, 2) 
            # 增加一個絕對值判斷，避免正負號混淆
            if abs(rsi_mfi_diff) > 22:
                rsi_mfi_anays = f'嚴重背離（差值 {rsi_mfi_diff}）'
            elif latest_mfi > 50 and latest_rsi > 50:
                rsi_mfi_anays = "rsi mfi 同在上"
            elif latest_mfi < 50 and latest_rsi < 50:
                rsi_mfi_anays = "rsi mfi 同在下"
            else:
                rsi_mfi_anays = f'rsi:{latest_rsi:.2f} mfi:{latest_mfi:.2f} 差{rsi_mfi_diff}'
                
            return {
                "time_window": interval,
                "phase": phase,
                "trend": trend,
                "mfi_macd_divergence": divergence,
                "rsi_mfi_divergence": rsi_mfi_anays,
                "latest_swing_high": latest_swing_high,
                "latest_swing_low": latest_swing_low,
                "latest_price": latest_price,
                "latest_macd_zscore": latest_macd_z,            
                "swing_highs": swing_highs,           # 多個頂點
                "swing_lows": swing_lows,             # 多個低點
                "support_zone": support_zone,         # 短期支撐區
                "resistance_zone": resistance_zone,   # 短期阻力區
                "latest_10_mfi": latest_10_mfi,
                "latest_10_rsi": latest_10_rsi,
            }
            
        except Exception as e:
            return {"error": f"分析失敗: {str(e)}"}

    # === 核心引擎：共振判斷 ===

    def _calculate_confluence(self, l1: dict, l2: dict, l3: dict) -> MarketState:
        """
        升級版共振引擎：結合 L1 趨勢、L2 環境與 L3 的新趨勢/背離邏輯
        """
        score = 0
        direction = "neutral"
        message = "訊號不明確，等待更強烈的共振"

        # 提取各層級數據
        l1_dir = l1['direction']          # bullish, bearish, neutral
        l2_env = l2['environment']        # trending, squeezing, volatile

        l3_trend = l3.get('trend', '中性')   # 看多, 看空, 偏多, 偏空, 中性
        l3_div = l3.get('mfi_macd_divergence', '無明顯背離')
        l3_phase = l3.get('phase', '')

        # --- STEP 1: 方向共振 (Directional Alignment) ---
        # 我們要看 L1 (大週期) 和 L3 (小週期) 是否在往同一個方向走
        is_bullish_confluence = False
        is_bearish_confluence = False

        # 判斷 L3 是否屬於「多頭系」
        if l3_trend in ["看多", "偏多", "強烈看多"] or "看漲" in l3_div:
            if l1_dir == "bullish":
                is_bullish_confluence = True
                score += 1  # 基礎分：大方向對了
            elif l1_dir == "bearish":
                score -= 2 # 警告分：大方向看空，小週期卻在反彈 (可能是在回調)

        # 判斷 L3 是否屬於「空頭系」
        if l3_trend in ["看空", "偏空", "強烈看空"] or "看跌" in l3_div:
            if l1_dir == "bearish":
                is_bearish_confluence = True
                score += 1  # 基礎分：大方向對了
            elif l1_dir == "bullish":
                score -= 2 # 警告分：大方向看多，小週期卻在回調

        # --- STEP 2: 訊號強度加分 (Signal Strength) ---

        # 看漲加分 
        if "強烈看多" in l3_phase or "看漲背離" in l3_div:
            score += 2
            if is_bullish_confluence:
                score += 1 # 真正的共振加分！

        # 看跌加分
        if "強烈看空" in l3_phase or "看跌背離" in l3_div:
            score += 2
            if is_bearish_confluence:
                score += 1 # 真正的共振加分！

        # --- STEP 3: 環境濾網 (Environment Filter) ---
        # 如果 L2 處於高波動 (volatile) 或 擠壓中 (squeezing)，我們要降低信心度
        if l2_env == "volatile":
            score -= 1 # 波動太大，容易被洗
            message_suffix = " (市場高波動，小心洗盤)"
        elif l2_env == "squeezing":
            score -= 1 # 正在擠壓，可能還沒爆發
            message_suffix = " (市場正在擠壓，等待突破)"
        else:
            message_suffix = ""

        # --- STEP 4: 最終決策判定 (Final Decision) ---

        # 判斷最終方向與訊息
        if score >= 3:
            direction = "STRONG_BUY"
            message = "極強共振：多頭趨勢 + 底部背離" + message_suffix
        elif score >= 1:
            direction = "BUY"
            message = "趨勢同步：多頭方向一致" + message_suffix
        elif score <= -3:
            direction = "STRONG_SELL"
            message = "極強共振：空頭趨勢 + 頂部背離" + message_suffix
        elif score <= -1:
            direction = "SELL"
            message = "趨勢同步：空頭方向一致" + message_suffix
        elif score < 0:
            direction = "WAIT"
            message = "方向衝突：大週期與小週期背離，建議觀望" + message_suffix
        else:
            direction = "WAIT"
            message = "訊號不明確，等待背離或趨勢確立" + message_suffix

        return MarketState(direction=direction, score=score, message=message)
