from fastapi import APIRouter, Depends
import os
from .models import SignalResponse
from .coinglass_client import CoinGlassClient
from .signal_calculator import SignalCalculator

router = APIRouter(prefix="/signals", tags=["Signals"])

# 使用 Dependency Injection，這樣測試時可以很方便地換掉 client
async def get_cg_client():
    api_key = os.getenv("COINGLASS_API_KEY")
    return CoinGlassClient(api_key)

@router.get("/{symbol}", response_model=SignalResponse) 
async def get_signal(symbol: str, client: CoinGlassClient = Depends(get_cg_client)):
    result = await SignalCalculator(cg_client=client).futures_D_spot_ratio(coin=symbol.upper(), interval="4h", limit=100)
    return result