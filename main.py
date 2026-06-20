import json
import os
import asyncio
from typing import Optional
from datetime import datetime, time
from decimal import Decimal, ROUND_DOWN
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Depends
from pydantic import BaseModel
    
# 信號計算層
from signal_layer.coinglass_client import CoinGlassClient
from signal_layer.signal_calculator import SignalCalculator
# 幣種分類 for 傳統金融
from signal_layer.symbol_classifier import classify_symbol, get_tradfi_category

# dummy資料包裝
from app.core.config import get_settings
from app import mock_service
from app.mock_service import (
    place_mock_order,
    cancel_mock_order,
    set_mock_stop_loss,
)

# Binance 官方 SDK
try:
    from binance.um_futures import UMFutures
    bn_client_class = UMFutures
except ImportError:
    from binance import Client
    bn_client_class = Client

from dotenv import load_dotenv
load_dotenv()

# config
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")
API_KEY_TESTNET = os.getenv("BINANCE_API_KEY_TESTNET")
API_SECRET_TESTNET = os.getenv("BINANCE_API_SECRET_TESTNET")
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY")
TESTNET = os.getenv("TESTNET", "true").lower() == "true"
ON_DEV = os.getenv("ON_DEV", "true").lower() == "true"

# 對於測試環境 用另一個port 就不會跟生產環境幹一起
port = 8069
if ON_DEV:
    port = 8001

 
if TESTNET:
    bn_client = UMFutures(
        key=API_KEY_TESTNET,
        secret=API_SECRET_TESTNET,
        base_url="https://demo-fapi.binance.com"   # 測試網
    )
    print("[INFO] 使用 Binance Futures Testnet")
else:
    bn_client = UMFutures(
        key=API_KEY,
        secret=API_SECRET
    )
    print("[INFO] 使用 Binance Futures 主網")
coin_client = CoinGlassClient(api_key=str(COINGLASS_API_KEY))
signal_back = SignalCalculator(cg_client=coin_client)
# json db
class JSONDatabase:
    def __init__(self, file_path: str = "trading_data.json"):
        self.file_path = file_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.file_path):
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump({"orders": [], "positions": {}}, f, indent=4, ensure_ascii=False)

    def _load(self) -> dict:
        with open(self.file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save(self, data: dict):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def save_order(self, order: dict):
        data = self._load()
        data["orders"].append(order)
        self._save(data)

    def update_position(self, symbol: str, position_data: Optional[dict]):
        data = self._load()
        if position_data:
            data["positions"][symbol] = position_data
        else:
            data["positions"].pop(symbol, None)
        self._save(data)

    def get_all_data(self) -> dict:
        return self._load()
    
    def get_cached_precision(self, symbol: str) -> Optional[tuple]:
    # """從本地 JSON 讀取已快取的精度"""
        data = self._load()
        precisions = data.get("precisions", {})
        if symbol in precisions:
            p = precisions[symbol]
            return p["price_precision"], p["qty_precision"], p["tick_size"]
        return None

    def save_precision(self, symbol: str, price_precision: int, qty_precision: int, tick_size: float):
        """把精度持久化存到 trading_data.json"""
        data = self._load()
        if "precisions" not in data:
            data["precisions"] = {}
        data["precisions"][symbol] = {
            "price_precision": price_precision,
            "qty_precision": qty_precision,
            "tick_size": tick_size,
            "updated_at": str(datetime.now())
        }
        self._save(data)

db = JSONDatabase()

# pydantic models

# 市價單買入請求模型
class OrderRequest(BaseModel):
    symbol: str #幣種，例如 "BTCUSDT"
    side: str # BUY 或 SELL
    usdt_amount: Optional[float] = None # 價值的 USDT 金額（優先於 quantity）
    quantity: Optional[float] = None    # 指定數量的該幣
    leverage: Optional[int] = 10
    stop_loss: Optional[float] = None   # 額外記錄用
    take_profit: Optional[float] = None # 額外記錄用

# 限價單請求模型
class LimitOrderRequest(BaseModel):
    symbol: str #幣種，例如 "BTCUSDT"
    side: str # BUY 或 SELL
    price: Optional[float] = None # 限價價格
    type : Optional[str] = 'LIMIT' # LIMIT
    usdt_amount: Optional[float] = None # 價值的 USDT 金額（優先於 quantity）
    quantity: Optional[float] = None # 指定數量的該幣
    percentage: Optional[float] = None # 使用倉位百分比來計算減倉數量，不能用於買入（例如 50 就是使用一半倉位）
    reduceOnly: bool = True
    stop_loss: Optional[float] = None   # 額外記錄用
    take_profit: Optional[float] = None # 額外記錄用

# 條件止損請求模型
class StopLossRequest(BaseModel):
    symbol: str
    stop_price: Optional[float] = None      # 直接填止損價格
    percentage: Optional[float] = None      # 或填百分比 例如 2 = 2% 止損

# 幣種請求模型
class symbolRequest(BaseModel):
    symbol: str #幣種
    
# 幣種請求模型
class symbolRequestWithTime(BaseModel):
    symbol: str #幣種
    time_sacle: Optional[str] = "30m"

class symbolRequestWithBool(BaseModel):
    symbol: Optional[str] = None
    ezmode: bool = True

class pointRequest(BaseModel):
    leverage: int
    entry_price: float

class SizeRequest(BaseModel):
    leverage: Optional[int] = 10

# fastapi
app = FastAPI(title="Binance Futures 後端", version="4.0")
# 允許前端跨域存取（開發用）
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ip whitelist
# ALLOWED_IPS = {"127.0.0.1", "::1", "192.168.0.150"}

# @app.middleware("http")
# async def ip_whitelist_middleware(request, call_next):
#     client_ip = request.client.host
#     if client_ip not in ALLOWED_IPS:
#         raise HTTPException(status_code=403, detail="Access denied: IP not allowed")
#     response = await call_next(request)
#     return response

# background monitor 
# 後端本地追蹤功能預留
# async def background_monitor():    
#     while True:
#         pass
#         await asyncio.sleep(3)  # 每 3 秒檢查一次

# 全域快取
# symbol precision cache
async def get_symbol_precision(symbol: str, force_refresh: bool = False):
    """
    支援本地持久化快取
    - 平常直接讀快取 不重複叫api
    - 只有在 stop loss or 限價單報錯時 才force_refresh=True 重抓一次
    """
    # 先試快取
    if not force_refresh:
        cached = db.get_cached_precision(symbol)
        if cached:
            return cached

    # 沒有快取或強制重抓 去 Binance 拿最新資料
    try:
        exchange_info = bn_client.exchange_info()
        for s in exchange_info['symbols']:
            if s['symbol'] == symbol:
                price_precision = s.get('pricePrecision', 2)
                qty_precision = s.get('quantityPrecision', 3)

                tick_size = 0.01
                for f in s.get('filters', []):
                    if f['filterType'] == 'PRICE_FILTER':
                        tick_size = float(f.get('tickSize', '0.01'))
                        break

                # 存起來
                db.save_precision(symbol, price_precision, qty_precision, tick_size)
                return price_precision, qty_precision, tick_size

        # 沒找到就給預設值並存起來
        default = (2, 3, 0.01)
        db.save_precision(symbol, *default)
        return default

    except Exception as e:
        print(f"exchangeInfo failed: {e}")
        return 2, 3, 0.01
    
def round_to_tick(price: float, tick_size: float) -> float:
    """
    使用 decimal 來計算 消除噁心的浮點數誤差
    """
    if tick_size <= 0:
        return price
    try:
        price_dec = Decimal(str(price))          # 用 str 轉換 避免 float 誤差
        tick_dec = Decimal(str(tick_size))
        result = (price_dec // tick_dec) * tick_dec   # 無條件捨去
        return float(result)
    except:
        return price

def get_lerverage_from_position(pos: dict) -> int:
    notional = abs(float(pos.get("notional", 0)))
    initial_margin = float(pos.get("initialMargin", 0.0001))
    leverage = max(1, round(notional / initial_margin)) if notional > 0 and initial_margin > 0 else 10
    return leverage

# startup
@app.on_event("startup")
async def startup():
    # asyncio.create_task(background_monitor())
    settings = get_settings()
    if settings.demo_mode:
        print("demo mode enabled")
    else:
        print("server started")
@app.post("/order")
async def create_order(req: OrderRequest):
    if get_settings().demo_mode:
        return place_mock_order({
            "symbol": req.symbol,
            "side": req.side,
            "type": "MARKET",
            "quantity": str(req.quantity or req.usdt_amount or "0.1"),
            "price": "0"
        })
    try:
        for attr in ["quantity", "usdt_amount"]:
            if getattr(req, attr) is None or getattr(req, attr) == 0:
                setattr(req, attr, None)

        bn_client.change_leverage(symbol=req.symbol, leverage=req.leverage)
        try:
            bn_client.change_margin_type(symbol=req.symbol, marginType="CROSSED")
        except Exception as e:
            if "No need to change margin type" not in str(e):
                print(f"Margin type warning: {e}")
        # precision
        exchange_info = bn_client.exchange_info()
        symbol_info = next((s for s in exchange_info['symbols'] if s['symbol'] == req.symbol), None)
        qty_precision = symbol_info.get('quantityPrecision', 6) if symbol_info else 6

        # quantity
        if req.quantity:
            quantity = round(req.quantity, qty_precision)
        elif req.usdt_amount:
            ticker = bn_client.mark_price(symbol=req.symbol)
            current_price = float(ticker['markPrice'])
            raw_qty = req.usdt_amount / current_price
            quantity = round(raw_qty, qty_precision)
        else:
            raise HTTPException(400, "請提供 quantity 或 usdt_amount")

        # 下單
        order = bn_client.new_order(
            symbol=req.symbol,
            side=req.side.upper(),
            type="MARKET",
            quantity=quantity,
            recvWindow=10000
        )
            
        entry_price = float(order.get("avgPrice") or order.get("price") or 0)

        position_data = {
            "symbol": req.symbol,
            "entry_price": entry_price,
            "amount": quantity,
            "side": req.side.upper(),
            "leverage": req.leverage,
            "timestamp": str(datetime.now()),
            "take_profit": req.take_profit,
            "stop_loss": req.stop_loss,
            "had_sl_set": False
        }
        db.update_position(req.symbol, position_data)
        db.save_order({**order, "timestamp": str(datetime.now())})            

        return {"message": "下單成功", "quantity": quantity}

    except Exception as e:
        raise HTTPException(400, detail=str(e))
    
@app.post("/positions")
async def get_positions(req: symbolRequestWithBool):
    """回傳完整倉位資訊 + 市價 + 未實現盈虧 + 掛單列表"""
    if get_settings().demo_mode:
        positions = mock_service.get_mock_positions(req.symbol if req.symbol and req.symbol != "string" else None)
        if req.ezmode == True:
            temp_result = []
            for r in (positions if isinstance(positions, list) else [positions]):
                temp_result.append({
                    "symbol": r.get("symbol", ""),
                    "side": r.get("side", ""),
                    "entry_price": r.get("entry_price", 0),
                    "mark_price": r.get("mark_price", 0),
                    "unrealized_pnl": r.get("unrealized_pnl", 0),
                    "percent_in_leverage": r.get("percent_in_leverage", 0)
                })
            return {"positions": temp_result, "total_positions": len(temp_result)}
        return {"positions": positions if isinstance(positions, list) else [positions], "total_positions": len(positions) if isinstance(positions, list) else 1}
    try:
        # 從 Binance 取得真實持倉
        real_positions = bn_client.get_position_risk()
        result = []

        for pos in real_positions:
            if float(pos.get("positionAmt", 0)) == 0:
                continue

            symbol = pos["symbol"]
            entry_price = float(pos.get("entryPrice", 0))
            position_amt = float(pos.get("positionAmt", 0))
            unrealized_pnl = float(pos.get("unRealizedProfit", 0))
            leverage = get_lerverage_from_position(pos)
            # 取得目前市價
            try:
                ticker = bn_client.mark_price(symbol=symbol)
                mark_price = float(ticker["markPrice"])
            except:
                mark_price = 0

            # 取得該幣種所有掛單（限價、止盈、止損）

            result.append({
                "symbol": symbol,
                "side": "BUY" if position_amt > 0 else "SELL",
                "amount": abs(position_amt),
                "entry_price": entry_price,
                "mark_price": mark_price,
                "leverage": leverage,
                "unrealized_pnl": unrealized_pnl,
                "percent": round((unrealized_pnl / (abs(position_amt) * entry_price) * 100), 2) if entry_price > 0 else 0,
                "percent_in_leverage": round((unrealized_pnl / (abs(position_amt) * entry_price) * 100 * leverage), 2) if entry_price > 0 else 0
            })
            # 把價格寫入本地倉位資料庫，讓前端可以直接讀取（不需要每次都從 Binance 撈）
            local_data = db.get_all_data()["positions"].get(symbol, {}) 
            local_data["mark_price"] = mark_price
            local_data["entry_price"] = entry_price
            local_data["unrealized_pnl"] = unrealized_pnl
            local_data["leverage"] = leverage
            local_data["amount"] = abs(position_amt)
            local_data["timestamp"] = str(datetime.now())
            db.update_position(symbol, local_data)

        # 如果為簡易模式 返回只有幣種、方向、數量、市價、盈虧和盈虧百分比
        if req.ezmode == True:
            temp_result = []
            for r in result:
                temp_result.append({
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "entry_price": r["entry_price"],
                    "mark_price": r["mark_price"],
                    "unrealized_pnl": r["unrealized_pnl"],
                    "percent_in_leverage": r["percent_in_leverage"]
                })
            if req.symbol and req.symbol != "string":
                temp_result = [sl for sl in temp_result if sl["symbol"] == req.symbol]
            return {"positions": temp_result, "total_positions": len(temp_result)}
        
        # 如果有指定幣種 只返回該幣種
        if req.symbol and req.symbol != "string":
            result = [sl for sl in result if sl["symbol"] == req.symbol]
        return {"positions": result, "total_positions": len(result)}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/close-position")
async def close_position(req: symbolRequest):
    if get_settings().demo_mode:
        return place_mock_order({
            "symbol": req.symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": "1.0",
            "price": "0"
        })
    data = db.get_all_data()
    if req.symbol not in data["positions"]:
        raise HTTPException(404, "持倉不存在")

    pos = data["positions"][req.symbol]
    close_side = "SELL" if pos["side"] == "BUY" else "BUY"

    order = bn_client.new_order(
        symbol=req.symbol,
        side=close_side,
        type="MARKET",
        quantity=pos["amount"],
        reduceOnly=True
    )

    # 移除本地持倉
    db.update_position(req.symbol, None)
    db.save_order({**order, "reason": "手動平倉", "timestamp": str(datetime.now())})

    return {"message": f"{req.symbol} 已手動平倉"}


@app.get("/orders")
async def get_orders():
    if get_settings().demo_mode:
        return {"orders": mock_service.get_mock_orders()}
    return {"orders": db.get_all_data()["orders"]}


@app.post("/sync-positions")
async def sync_positions():
    """從 Binance 讀取真實持倉，並同步到本地 JSON"""
    if get_settings().demo_mode:
        positions = mock_service.get_mock_positions()
        return {
            "message": f"已同步 {len(positions) if isinstance(positions, list) else 1} 個模擬倉位",
            "symbols": [p.get("symbol") for p in (positions if isinstance(positions, list) else [positions])]
        }
    try:
        real_positions = bn_client.get_position_risk()   # ← 改成這個！
        synced_count = 0
        synced_symbols = []

        for pos in real_positions:
            position_amt = float(pos.get("positionAmt", 0))
            if position_amt == 0:
                continue

            symbol = pos["symbol"]
            entry_price = float(pos.get("entryPrice", 0))
            unrealized_pnl = float(pos.get("unRealizedProfit", 0))
            leverage = int(pos.get("leverage", 0)) or 10

            local_data = db.get_all_data()["positions"].get(symbol, {})
            stop_loss = local_data.get("stop_loss")
            take_profit = local_data.get("take_profit")

            new_position = {
                "symbol": symbol,
                "entry_price": entry_price,
                "amount": abs(position_amt),
                "side": "BUY" if position_amt > 0 else "SELL",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "leverage": leverage,
                "unrealized_pnl": unrealized_pnl,
                "timestamp": str(datetime.now())
            }

            db.update_position(symbol, new_position)
            synced_count += 1
            synced_symbols.append(symbol)

        return {
            "message": f"已同步 {synced_count} 個真實倉位",
            "symbols": synced_symbols
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@app.post("/place-limit")
async def place_limit_order(req: LimitOrderRequest):
    if get_settings().demo_mode:
        return place_mock_order({
            "symbol": req.symbol,
            "side": req.side,
            "type": req.type or "LIMIT",
            "quantity": str(req.quantity or req.usdt_amount or "0.1"),
            "price": str(req.price or "0")
        })
    try:
        # 對於未設置 可能會是0或None 的參數，統一處理成 None，讓後續邏輯更簡潔
        for attr in ["price", "percentage", "usdt_amount", "quantity"]:
            if getattr(req, attr) is None or getattr(req, attr) == 0:
                setattr(req, attr, None)
        
        if req.reduceOnly == False and req.percentage is not None:
            raise HTTPException(400, "reduceOnly 非減倉模式下不支援 percentage 參數 需要下單數量或價值")
        if req.usdt_amount is not None and req.quantity is not None:
            req.quantity = None
        price = req.price
        # cached precision
        price_precision, qty_precision, tick_size = await get_symbol_precision(req.symbol)

        price = round_to_tick(price, tick_size)

        # 決定數量 
        if req.percentage is not None:
            pos = next((p for p in bn_client.get_position_risk() if p["symbol"] == req.symbol), None)
            if not pos:
                raise HTTPException(400, "找不到該幣種倉位")
            current_amt = abs(float(pos["positionAmt"]))
            raw_qty = current_amt * (req.percentage / 100)
            quantity = round(raw_qty, qty_precision)
        elif req.usdt_amount is not None:
            ticker = bn_client.mark_price(symbol=req.symbol)
            current_price = float(ticker['markPrice'])
            raw_qty = req.usdt_amount / current_price
            quantity = round(raw_qty, qty_precision)
        elif req.quantity is not None:
            quantity = round(req.quantity, qty_precision)
        else:
            raise HTTPException(400, "請提供 quantity 或 percentage")

        # 準備下單參數
        order_params = {
            "symbol": req.symbol,
            "side": req.side.upper(),
            "type": req.type.upper(),
            "quantity": quantity,
            "reduceOnly": req.reduceOnly,
            "recvWindow": 10000,
            "timeInForce": "GTC",
            "price": price
        }
        
        order = bn_client.new_order(**order_params)

        # 更新資料庫
        local_data = db.get_all_data()["positions"].get(req.symbol, {})
        if local_data.get("had_sl_set") is None:
            local_data["had_sl_set"] = False
            db.update_position(req.symbol, local_data)

        return {
            "message": f"{req.type} 單已掛出",
            "quantity_used": quantity,
            "order": order
        }

    except Exception as e:
        # refresh precision on error
        try:
            await get_symbol_precision(req.symbol, force_refresh=True)
        except:
            pass
        raise HTTPException(400, detail=str(e))
                
@app.post("/cancel-order")
async def cancel_order(req: symbolRequest):
    """取消掛單"""
    if get_settings().demo_mode:
        return cancel_mock_order(hash(req.symbol) % 10000)
    try:
        # 取消該幣種所有掛單
        result = bn_client.cancel_open_orders(symbol=req.symbol)
        return {"message": f"已取消 {req.symbol} 所有掛單"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/set-stop-loss")
async def set_stop_loss(req: StopLossRequest):
    if get_settings().demo_mode:
        return set_mock_stop_loss({
            "symbol": req.symbol,
            "side": "SELL",
            "stopPrice": str(req.stop_price or (req.percentage or 0)),
            "quantity": "1.0"
        })
    try:
        symbol = req.symbol
        percentage = abs(int(req.percentage or 0))

        # 取得 Binance 真實持倉（只用來計算止損價格與數量）
        positions = bn_client.get_position_risk(symbol=symbol)
        pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not pos:
            raise HTTPException(404, "找不到該幣種持倉")

        entry_price = float(pos["entryPrice"])
        position_amt = float(pos["positionAmt"])
        side = "BUY" if position_amt > 0 else "SELL"
        amount = abs(position_amt)

        # 計算槓桿
        # notional = abs(float(pos.get("notional", 0)))
        # initial_margin = float(pos.get("initialMargin", 0.0001))
        # leverage = max(1, round(notional / initial_margin)) if notional > 0 and initial_margin > 0 else 10
        leverage = get_lerverage_from_position(pos)
        # 取得精度
        price_precision, qty_precision, tick_size = await get_symbol_precision(symbol)

        # 把所有數字轉成 Decimal 精準計算
        entry_dec = Decimal(str(entry_price))
        pct_dec = Decimal(str(percentage))
        lev_dec = Decimal(str(leverage))
        tick_dec = Decimal(str(tick_size))

        if req.stop_price:
            stop_loss_dec = Decimal(str(req.stop_price))
        elif req.percentage:
            if side == "SELL":
                stop_loss_dec = entry_dec * (Decimal('1') + (pct_dec / lev_dec / Decimal('100')))
            else:
                stop_loss_dec = entry_dec / (Decimal('1') + (pct_dec / lev_dec / Decimal('100')))
        else:
            raise HTTPException(400, "請提供 stop_price 或 percentage")

        # 用 Decimal + tick_size 精準捨去
        stop_loss_dec = (stop_loss_dec // tick_dec) * tick_dec

        # 計算 triggerPrice
        if side == "SELL":
            target_dec = stop_loss_dec + (Decimal('10') * tick_dec)
        else:
            target_dec = stop_loss_dec - (Decimal('10') * tick_dec)
        target_dec = (target_dec // tick_dec) * tick_dec

        # 轉回 float（只在最後轉一次）
        stop_loss = float(stop_loss_dec)
        stop_loss_target = float(target_dec)

# 關鍵：合併寫入，不要覆蓋整個 pos
        local_data = db.get_all_data()["positions"].get(symbol, {})
        
        local_data.update({
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "amount": amount,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "had_sl_set": True,           # 明確標記已設定止損
            "timestamp": str(datetime.now())
        })
        # end merge

        # 準備 Algo 止損單
        order_side = "BUY" if side == "SELL" else "SELL"
        order_params = {
            "algoType": "CONDITIONAL",
            "symbol": symbol,
            "side": order_side,
            "type": "STOP_MARKET",
            "closePosition": True,
            "triggerPrice": stop_loss_target,
            "timeInForce": "GTC",
            "workingType": "CONTRACT_PRICE",
            "recvWindow": 10000
        }

        bn_client.sign_request("POST", "/fapi/v1/algoOrder", order_params)
        db.update_position(symbol, local_data)

        return {"message": f"已設定止損 {stop_loss}"}

    except Exception as e:
        try:
            await get_symbol_precision(symbol, force_refresh=True)
        except:
            pass
        raise HTTPException(400, detail=str(e) + f" | error使用Decimal設定止損參數: {order_params}")    
    
@app.post("/grab-stop-losses")
async def get_active_stop_losses(req: symbolRequestWithBool):
    if get_settings().demo_mode:
        return {"stop_loss_orders": [], "_demo_note": "DEMO MODE - 模擬止損單列表"}
    try:
        symbol = req.symbol
        params = {
            "symbol": symbol,
            "recvWindow": 10000
        }
        # 可選：只看 CONDITIONAL 類型
        params["algoType"] = "CONDITIONAL"

        orders = bn_client.sign_request("GET", "/fapi/v1/openAlgoOrders", params)
        # 過濾出該幣種的止損單（可以根據需要進一步過濾）
        stop_loss_orders = []
        for o in orders:
            if o.get("symbol") == symbol and o.get("orderType") == "STOP":
                stop_loss_orders.append({
                    "algoId": o.get("algoId"),
                    "symbol": o.get("symbol"),
                    "side": o.get("side"),
                    "price": o.get("price"),
                    "triggerPrice": o.get("triggerPrice"),
                    "quantity": o.get("quantity"),
                    "reduceOnly": o.get("reduceOnly")
                })
        return {
            "stop_loss_orders": stop_loss_orders
        }

    except Exception as e:
        raise HTTPException(400, detail=f"查詢條件單失敗: {str(e)}")

    

@app.get("/pending-orders")    
async def get_pending_orders():
    """
    返回目前所有正在掛著的限價單 (Limit Orders) 。
    這可以幫助主人確認 TP 單有沒有成功掛出去。
    """
    if get_settings().demo_mode:
        return {"pending_orders": mock_service.get_mock_pending_orders()}
    try:
        all_orders = db.get_all_data().get("orders", [])
        pending_orders = [o for o in all_orders if o.get("status") != "CLOSED"]
        return {"pending_orders": pending_orders}
    except Exception as e: 
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/recommended-size")
async def get_recommended_size(req: SizeRequest):
    """
    根據目前錢包餘額和傳入的槓桿設定，計算推薦的 USDT 倉位價值。
    這個功能可以幫助主人決定下單金額，讓風險控制更簡單。
    目前的邏輯是：
    1. 風險保證金 = 可用餘額 × 5%
    2. 推薦倉位價值 = 風險保證金 × 槓桿倍數
    這樣可以確保每筆交易的保證金風險控制在 5% 以內，同時利用傳入的槓桿放大倉位。
    """
    if get_settings().demo_mode:
        wallet = mock_service.get_mock_wallet_balance()
        balance = wallet.get("walletBalance", 10000) if isinstance(wallet, dict) else 10000
        percentages_list = [0.5, 1, 2, 3, 5, 7, 10]
        recommended_list = []
        for pct in percentages_list:
            risk_margin = balance * (pct / 100)
            recommended_size = risk_margin * req.leverage
            size_wallet_ratio = round(recommended_size / balance, 2)
            recommended_list.append({
                "百分比": f"{pct}%",
                "保證金": round(risk_margin, 2),
                "名義倉位價值USDT": round(recommended_size, 2),
                "倉位對錢包比例": f"{size_wallet_ratio}x",
            })
        return {
            "recommended_position_value_usdt": recommended_list,
            "槓桿": req.leverage,
            "錢包": balance,
            "錢包目前價值": balance,
            "未實現盈虧": 0,
            "剩餘可開保證金": balance,
            "message": f"這是根據 {req.leverage} 槓桿的倉位名義價值推薦。",
            "_demo_note": "DEMO MODE - 模擬資料"
        }
    try:
        # 從 Binance 撈錢包餘額（USDT-M 合約帳戶）
        account_info = bn_client.account()
        
        usdt_balance = None
        for asset in account_info.get("assets", []):
            if asset.get("asset") == "USDT":
                wallet_balance = float(asset.get("walletBalance", 0))
                unrealized_pnl = float(asset.get("unrealizedProfit", 0))
                
                usdt_balance = {
                    "walletBalance": wallet_balance,
                    "equity": round(wallet_balance + unrealized_pnl, 4),
                    "unrealizedPNL": unrealized_pnl,
                    "marginBalance": float(asset.get("marginBalance", 0)),
                    "availableBalance": float(asset.get("availableBalance", 0))
                }
                break
        
        if not usdt_balance:
            return {"message": "錢包裡找不到 USDT 餘額"}

        # recommended size logic (with leverage)
        percentages_list = [0.5, 1, 2, 3, 5, 7, 10];
        recommended_list = []
        awllet_balance = float(usdt_balance["walletBalance"])
        for pct in percentages_list:
            risk_margin = awllet_balance * (pct / 100)
            recommended_size = risk_margin * req.leverage
            size_wllet_raito = round(recommended_size / awllet_balance, 2)
            # 匹配最接近1的為100 數值越高越小(0.8倍減少) 數值越小越小(0.9倍減少)
            
            recommended_list.append({
                "百分比": f"{pct}%",
                "保證金": round(risk_margin, 2),
                "名義倉位價值USDT": round(recommended_size, 2),
                "倉位對錢包比例": f"{size_wllet_raito}x",
            })

        return {
            "recommended_position_value_usdt": recommended_list,
            "槓桿": req.leverage,
            "錢包": usdt_balance["walletBalance"],
            "錢包目前價值": usdt_balance["equity"],
            "未實現盈虧": usdt_balance["unrealizedPNL"],
            "剩餘可開保證金": usdt_balance["availableBalance"],
            "message": f"這是根據 {req.leverage} 槓桿的倉位名義價值推薦。"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))    

@app.get("/wallet-balance")
async def get_wallet_balance():
    """
    返回 USDT 永續合約錢包餘額
    """
    if get_settings().demo_mode:
        return mock_service.get_mock_wallet_balance()
    try:
        account_info = bn_client.account()
        
        usdt_balance = None
        for asset in account_info.get("assets", []):
            if asset.get("asset") == "USDT":
                wallet_balance = float(asset.get("walletBalance", 0))
                unrealized_pnl = float(asset.get("unrealizedProfit", 0))
                
                usdt_balance = {
                    "walletBalance": wallet_balance,
                    "equity": round(wallet_balance + unrealized_pnl, 4),
                    "unrealizedPNL": unrealized_pnl,
                    "marginBalance": float(asset.get("marginBalance", 0)),
                    "availableBalance": float(asset.get("availableBalance", 0))
                }
                break
        
        if not usdt_balance:
            return {"message": "錢包裡找不到 USDT 餘額"}

        return {
            "asset": "USDT",
            "details": usdt_balance,
            "timestamp": str(datetime.now())
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/calculate-sl-by-leverage")
async def calculate_sl_by_leverage(req: pointRequest):
    """
    根據槓桿設定計算推薦點位距離。這個功能可以幫助主人決定止損和止盈的合理距離。
    目前的邏輯是：輸入槓桿倍數，返回建議的止損和止盈點位距離（以點位表示），例如：
    止損距離約在90~160%之間 代表如果是10倍槓桿，建議止損距離可以設在入場價的9%~16%以內；如果是20倍槓桿，建議止損距離可以設在入場價的4.5%~8%以內，以此類推。
    返回絕對價格列表 讓agent可以參考這些點位
    """
    if get_settings().demo_mode:
        return mock_service.get_mock_recommended_size(
            balance=10000,
            risk_percent=2,
            entry_price=req.entry_price,
            stop_loss=req.entry_price * 0.9
        )
    try:
        leverage = req.leverage
        entry = req.entry_price

        if leverage <= 0:
            raise ValueError("槓桿倍數必須大於 0 。")
        if entry <= 0:
            raise ValueError("入場價格必須大於 0 。")

        # 基礎係數（90~160）
        base_low = 90
        base_high = 160

        # 計算實際百分比距離
        sl_pct_low = round(base_low / leverage, 2)
        sl_pct_high = round(base_high / leverage, 2)

        # LONG position absolute price
        sl_price_wide = round(entry * (1 - sl_pct_high / 100), 8)
        sl_price_mid  = round(entry * (1 - (sl_pct_low + sl_pct_high) / 200), 8)
        sl_price_tight = round(entry * (1 - sl_pct_low / 100), 8)

        # 止盈建議（風險報酬比 1:2）
        tp_pct = round((sl_pct_low + sl_pct_high) / 2 * 2, 2)
        tp_price = round(entry * (1 + tp_pct / 100), 8)

        # SHORT position absolute price
        sl_price_short_wide = round(entry * (1 + sl_pct_high / 100), 8)
        sl_price_short_tight = round(entry * (1 + sl_pct_low / 100), 8)
        tp_price_short = round(entry * (1 - tp_pct / 100), 8)

        return {
            "leverage": leverage,
            "entry_price": entry,
            "sl_percent_range": [sl_pct_low, sl_pct_high],
            "long": {
                "stop_loss_prices": [sl_price_wide, sl_price_mid, sl_price_tight],
                "take_profit_price": tp_price,
                "risk_reward_ratio": "1:2"
            },
            "short": {
                "stop_loss_prices": [sl_price_short_tight, sl_price_short_wide],
                "take_profit_price": tp_price_short,
                "risk_reward_ratio": "1:2"
            },
            "note": f"。建議止損距離 {sl_pct_low}% ~ {sl_pct_high}%（依槓桿自動調整）\n"
                    f"多單止損請選 {sl_price_wide} ~ {sl_price_tight} 之間\n"
                    f"空單止損請選 {sl_price_short_tight} ~ {sl_price_short_wide} 之間\n"
                    f"止盈建議設在風險報酬比 1:2 的位置。"
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@app.post("/get-symbol-info")
async def get_symbol_info(req: symbolRequest):
    """獲取交易對的詳細資訊，包括價格與種類"""
    if get_settings().demo_mode:
        return mock_service.get_mock_symbol_info(req.symbol)
    try:
        symbol = req.symbol

        if not symbol:
            raise ValueError("交易對名稱必須提供。")

        # 從 Binance 撈取標的價格
        mark_price = 0
        try:
            ticker = bn_client.mark_price(symbol=symbol)
            mark_price = float(ticker['markPrice'])
        except:
            pass

        category = classify_symbol(symbol)
        category_detail = get_tradfi_category(symbol)

        return {
            "symbol": symbol,
            "mark_price": mark_price,
            "category": category,
            "category_detail": category_detail,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# signals
@app.post("/mixed_RMMA_singal")
async def signal_test(req: symbolRequest):
    """
    RSI MFI MACD與回歸推算的綜合信號算法 可以知道目前趨勢方向
    """
    if get_settings().demo_mode:
        return mock_service.get_mock_signal_analysis(req.symbol, "30m")
    try:
        symbol = req.symbol
        signals = await signal_back.singals_RMMA_entry(symbol=symbol)
        return signals

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法處理數據: {str(e)}")

@app.get("/get_available_times")
async def get_available_times():
    """
    取得可用的時間間隔 雖然是寫死的
    """
    return {
        "available_times": [
            "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "1w"
        ]
    }

@app.get("/")
async def root():
    settings = get_settings()
    if settings.demo_mode:
        mode = "DEMO MODE"
    elif TESTNET:
        mode = "Testnet"
    else:
        mode = "Production"
    return {"message": f" Binance Futures backend online. Mode: {mode} (v2.1 with limit stop-loss)"}

# test endpoints below
@app.post("/coinglass_test")
async def coinglass_test(req: symbolRequest):
    """
    這是一個測試用的 API 端點，用來驗證是否能成功從 包裝的CoinGlass客戶端 獲取數據。
    如果成功，會返回 CoinGlass 上 BTCUSDT 永續合約的未平倉量和多空比。
    如果失敗，會返回錯誤訊息。
    這個功能可以幫助主人確認 CoinGlass API 的連接狀態，並且獲取一些市場情緒指標。
    """
    if get_settings().demo_mode:
        return {
            "symbol": req.symbol,
            "oi_delta": mock_service.get_mock_market_stats(req.symbol),
            "message": "成功從模擬資料獲取數據。",
            "_demo_note": "DEMO MODE - 模擬 CoinGlass 數據"
        }
    try:
        symbol = req.symbol
        # 現在這裡的 cg 就是上面 get_cg_client 回傳的實例了。
        # 注意：這裡要確保您的 CoinGlassClient 有 get_oi_delta 這個方法
        data = await coin_client.get_many_indicators(symbol=symbol) 
        
        return {
            "symbol": symbol,
            "oi_delta": data,
            "message": "成功從 CoinGlass 獲取數據。" 
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法從 CoinGlass 獲取數據: {str(e)}")

@app.post("/singal_test")
async def signal_test(req: symbolRequest):
    """
    這是一個測試用的 API 端點，用來驗證是否能成功從 包裝的SignalGenerator客戶端 獲取交易信號。
    如果成功，會返回 BTCUSDT 永續合約的最新交易信號。
    如果失敗，會返回錯誤訊息。
    這個功能可以幫助主人確認 SignalGenerator 的運作狀態，並且獲取一些交易決策參考。
    """
    if get_settings().demo_mode:
        signal = mock_service.get_mock_signal_analysis(req.symbol, "30m")
        return {"symbol": req.symbol, "signal": signal}
    try:

        symbol = req.symbol
        signal = await signal_back.get_MACD(symbol=symbol) 
        
        return {"symbol":symbol, "signal": signal}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法從 SignalGenerator 獲取交易信號: {str(e)}")

# startup
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=port)
