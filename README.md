# Trading Demo Report — 技術手冊

> 本專案為加密貨幣期貨交易分析平台的 Demo 版本（離線模擬模式）。源自完整交易系統的閹割版，使用模擬數據運行，無需連接真實交易所。

## 技術堆疊

- **後端框架**: FastAPI (Python 3.11+)
- **通訊協議**: MCP (JSON-RPC over stdio)
- **數據處理**: Pandas, NumPy, pandas_ta, SciPy
- **交易所 SDK**: binance-futures-connector
- **外部數據**: CoinGlass API (市場情緒/資金費率)
- **伺服器**: Uvicorn ASGI

## 系統架構

```
┌──────────────┐       stdio/JSON-RPC       ┌──────────────────┐
│  AI Client   │ ─────────────────────────▶ │  MCP Server      │
│  (Hermes/    │ ◀───────────────────────── │  (薄包裝層)       │
│   Claude)    │                            │  · Tool 定義     │
└──────────────┘                            │  · 請求轉譯       │
                                            └────────┬─────────┘
                                                     │ HTTP
                                                     ▼
                                            ┌──────────────────┐
                                            │  FastAPI 後端    │
                                            │  · 訊號分析層    │
                                            │  · 交易執行層    │
                                            │  · 風險管理層    │
                                            └────────┬─────────┘
                                                     │
                                              ┌──────┴──────┐
                                              ▼             ▼
                                   ┌──────────────┐ ┌──────────────┐
                                   │ 真實 API      │ │ Mock Service │
                                   │ (Binance/    │ │ (mock_data/) │
                                   │  CoinGlass)  │ │ (DEMO_MODE)  │
                                   └──────────────┘ └──────────────┘
```

### 層級說明

| 層級 | 組件 | 職責 |
|------|------|------|
| AI 宿主 | Hermes Agent / Claude Desktop | LLM 推理引擎，意圖理解與工具選擇 |
| MCP 協議層 | signal_mcp_server.py, trading_mcp_server_stdio.py | 工具註冊、請求轉譯、回應格式化 |
| 業務邏輯層 | main.py, signal_layer/ | 訊號計算、訂單管理、風險控管 |
| 數據存取層 | Binance API / CoinGlass API / mock_service.py | 真實或模擬數據來源 |

### Demo Mode vs 真實模式

透過 `DEMO_MODE` 環境變數切換：

| 行為 | Demo Mode | 真實模式 |
|------|-----------|----------|
| 數據來源 | 本地 JSON 檔案 | Binance / CoinGlass API |
| 下單操作 | 返回模擬回應 | 實際發送至交易所 |
| 持倉查詢 | 模擬持倉數據 | 即時從交易所獲取 |
| 訊號分析 | 使用模擬 K 線計算 | 使用真實市場數據 |

## 專案結構

```
trading-demo-report/
├── main.py                          # FastAPI 主程式 (API 端點)
├── signal_mcp_server.py             # MCP Server — 訊號分析插件
├── trading_mcp_server_stdio.py      # MCP Server — 交易操作插件
├── app/
│   ├── core/
│   │   └── config.py               # 設定 (DEMO_MODE, API Keys)
│   └── mock_service.py             # 模擬資料服務
├── signal_layer/
│   ├── signal_calculator.py         # RMMA 綜合訊號算法
│   ├── coinglass_client.py          # CoinGlass API 客戶端
│   ├── binance_client.py            # Binance API 客戶端
│   ├── symbol_classifier.py         # 幣種分類 (TradFi/Crypto)
│   ├── signal_router.py             # FastAPI Router (訊號端點)
│   ├── models.py                    # Pydantic 模型
│   └── scorer.py                    # 評分系統
├── mock_data/                       # 模擬數據
│   ├── klines.json                  # K 線數據
│   ├── signal_analysis.json         # 訊號分析結果
│   ├── wallet_balance.json          # 錢包餘額
│   ├── positions.json               # 持倉數據
│   ├── orders.json                  # 訂單歷史
│   └── market_stats.json            # 市場統計
├── trading_data.json                # 本地 JSON 資料庫 (訂單/持倉/精度快取)
├── requirements.txt
└── .env                             # 環境變數
```

## 環境變數

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `DEMO_MODE` | 啟用模擬模式 | `false` |
| `BINANCE_API_KEY` | Binance API 金鑰 | — |
| `BINANCE_API_SECRET` | Binance API 密鑰 | — |
| `BINANCE_API_KEY_TESTNET` | Binance Testnet 金鑰 | — |
| `BINANCE_API_SECRET_TESTNET` | Binance Testnet 密鑰 | — |
| `COINGLASS_API_KEY` | CoinGlass API 金鑰 | — |
| `TESTNET` | 使用測試網 | `true` |
| `ON_DEV` | 開發模式 (使用 port 8001) | `true` |

## 安裝與啟動

### 相依套件

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 啟動後端

```bash
# Demo 模式 (port 8069)
DEMO_MODE=true uvicorn main:app --port 8069

# 開發模式 (port 8001)
ON_DEV=true uvicorn main:app
```

啟動後 Swagger UI 文件位於 `http://127.0.0.1:8069/docs`。

### 啟動 MCP Server

```bash
# 訊號分析插件
python signal_mcp_server.py

# 交易操作插件
python trading_mcp_server_stdio.py
```

### Hermes Agent 配置

在 `config.yaml` 中配置 MCP Server：

```yaml
mcp:
  servers:
    signal:
      command: python
      args: ["<路徑>/signal_mcp_server.py"]
    trading:
      command: python
      args: ["<路徑>/trading_mcp_server_stdio.py"]
```

## API 端點

### 交易操作

- `POST /order` — 市價下單 (支援 USDT 金額或數量)
- `POST /place-limit` — 限價單 / 止盈單 (支援倉位百分比)
- `POST /cancel-order` — 取消指定幣種所有掛單
- `POST /close-position` — 市價平倉
- `POST /set-stop-loss` — 設定條件止損單 (支援百分比或絕對價格)

### 持倉與訂單管理

- `POST /positions` — 查詢持倉 (含市價、盈虧、ezmode 簡易模式)
- `GET /orders` — 訂單歷史
- `GET /pending-orders` — 未完成掛單
- `POST /sync-positions` — 從 Binance 同步持倉到本地

### 風險管理

- `POST /recommended-size` — 根據餘額與槓桿計算推薦倉位
- `POST /calculate-sl-by-leverage` — 根據槓桿計算止損/止盈點位
- `POST /grab-stop-losses` — 查詢已設定止損的持倉
- `POST /get-symbol-info` — 交易對資訊 (含分類)

### 訊號分析

- `POST /mixed_RMMA_singal` — 多週期綜合訊號分析 (RSI + MFI + MACD + 回歸推算)
- `POST /singal_test` — 訊號測試端點
- `POST /coinglass_test` — CoinGlass 連線測試

### 帳戶與系統

- `GET /wallet-balance` — USDT 合約錢包餘額
- `GET /` — 系統狀態
- `GET /get_available_times` — 可用時間框架列表

## MCP 工具清單

### Signal MCP Server (`signal_mcp_server.py`)

| 工具 | 參數 | 說明 |
|------|------|------|
| `get_symbol_info` | symbol | 交易對詳細資訊 (價格、精度、分類) |
| `get_analyze_RMMA_singal` | symbol | 多週期綜合技術指標分析 |

### Trading MCP Server (`trading_mcp_server_stdio.py`)

| 工具 | 參數 | 說明 |
|------|------|------|
| `place_market_order` | symbol, side, usdt_amount/quantity, leverage | 市價下單 |
| `place_limit_order` | symbol, side, price, usdt_amount/quantity/percentage, reduceOnly | 限價單 |
| `set_stop_loss` | symbol, stop_price/percentage | 設定止損 |
| `get_positions` | symbol (optional), ezmode | 查詢持倉 |
| `close_position` | symbol | 市價平倉 |
| `cancel_order` | symbol | 取消掛單 |
| `get_wallet_balance` | — | 錢包餘額 |
| `get_recommended_size` | leverage | 推薦倉位大小 |
| `get_active_stop_losses` | symbol (optional), ezmode | 已設止損的持倉 |
| `get_pending_orders` | — | 目前掛單列表 |
| `calculate_sl_by_leverage` | leverage, entry_price | 止損/止盈點位計算 |
| `sync_positions` | — | 同步 Binance 持倉 |
| `get_symbol_info` | symbol | 交易對資訊 |

## 訊號分析算法 (RMMA)

RMMA (RSI + MFI + MACD + Regression) 綜合訊號算法：

**L1 (4H) — 趨勢方向**
- EMA200 判斷多空分界
- 價格相對於長期均線的位置

**L2 (1H) — 環境評估**
- Bollinger Bands 寬度 (波動率)
- 平均波動率對比

**L3 (30m/15m) — 觸發點位**
- RSI/MFI 背離檢測
- MACD Z-Score 極值
- Swing High/Low 識別
- 支撐/阻力區域計算

輸出包含三層共振評分 (score 0-100) 與方向判斷 (STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL)。

## 幣種分類系統

`signal_layer/symbol_classifier.py` 提供靜態幣種分類：

- **TRADFI**: 貴金屬 (XAU/XAG)、大宗商品、美股 (AAPL/TSLA/NVDA...)、韓股、ETF (QQQ/SPY)、Pre-IPO
- **CRYPTO**: BTC, ETH, SOL, DOGE 等加密貨幣

分類函數:
- `classify_symbol(symbol)` → "TRADFI" | "CRYPTO" | "UNKNOWN"
- `get_tradfi_category(symbol)` → "貴金屬" | "大宗商品" | "美股" | "韓股" | "ETF" | "Pre-IPO" | "CRYPTO"

## 本地數據快取

`trading_data.json` 儲存：
- 訂單歷史紀錄
- 持倉狀態
- 交易對精度快取 (price_precision, qty_precision, tick_size)

精度快取策略：先讀快取，只有在止損或限價單報錯時才 `force_refresh=True` 重新從 Binance 抓取。

## 模擬數據格式

`mock_data/` 下的 JSON 檔案結構：

- **klines.json**: `{symbol: {interval: [[open_time, open, high, low, close, volume, ...], ...]}}`
- **positions.json**: `{symbol: {side, entry_price, mark_price, unrealized_pnl, percent_in_leverage, ...}}`
- **wallet_balance.json**: `{balance, crossWalletBalance, ...}`
- **orders.json**: `{orders: [...], pending_orders: [...]}`
- **signal_analysis.json**: `{symbol: {summary, layers: {L1, L2, L3}, ...}}`

## 與完整版的差異

| 功能 | Demo 版 | 完整版 |
|------|---------|--------|
| 數據來源 | mock_data/ (靜態 JSON) | Binance + CoinGlass 即時 API |
| 資料庫 | trading_data.json (JSON) | SQLite (dosc/sqlite_database.py) |
| 資料來源抽象層 | 無 | signal_layer/data_source/ (base + binance) |
| 資料庫遷移 | 無 | dosc/migrate_json_to_sqlite.py |
| 模擬服務 | app/mock_service.py | 無 |

## 安全考量

- MCP Server 作為中間層，僅暴露明確定義的工具
- 所有輸入參數經過 JSON Schema 驗證
- Demo Mode 下所有交易操作為模擬，零風險
- API Key 透過環境變數管理，不硬編碼

---

**聲明:** 本 Demo 使用模擬數據運行，不構成任何投資建議。所有數據僅供技術測試與學習參考。
