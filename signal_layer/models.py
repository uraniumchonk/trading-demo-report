from pydantic import BaseModel

class SignalResponse(BaseModel):
    symbol: str
    score: int
    direction: str
    oi_delta: float
    funding_rate: float
    futures_spot_ratio: float
    timestamp: str
