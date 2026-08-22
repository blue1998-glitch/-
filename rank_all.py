import yfinance as yf
import pandas as pd
import json
import time

# 這裡是一個簡化的全市場代號清單 (你可以持續增加)
# 為了節省時間，你可以先放 100 檔強勢股代號，未來再擴充
symbols = ["2330", "2454", "2317", "3441", "3008"] # 請自行擴充你的關注清單
market_data = []

for sym in symbols:
    try:
        ticker_tw = f"{sym}.TW"
        ticker_two = f"{sym}.TWO"
        # 嘗試抓 TW 或 TWO
        stock = yf.Ticker(ticker_tw)
        hist = stock.history(period="6mo")
        if len(hist) < 61:
            stock = yf.Ticker(ticker_two)
            hist = stock.history(period="6mo")
            
        if len(hist) >= 61:
            r_5d = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-6]) / hist['Close'].iloc[-6]) * 100
            r_1m = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-21]) / hist['Close'].iloc[-21]) * 100
            r_1q = ((hist['Close'].iloc[-1] - hist['Close'].iloc[-61]) / hist['Close'].iloc[-61]) * 100
            
            # 使用你的加權權重
            score = (r_5d * 0.2) + (r_1m * 0.5) + (r_1q * 0.3)
            market_data.append({"symbol": sym, "score": score})
        time.sleep(0.5) # 避免 Yahoo 擋請求
    except:
        continue

# 排序並計算排名
market_data.sort(key=lambda x: x['score'], reverse=True)
for i, item in enumerate(market_data):
    # 算百分位 PR 值
    pr = int((len(market_data) - i) / len(market_data) * 100)
    item['rs_rating'] = pr

with open("market_rankings.json", "w") as f:
    json.dump(market_data, f)
