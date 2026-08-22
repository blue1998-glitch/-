import requests
import re
import yfinance as yf
import pandas as pd
import json
import time

def get_all_taiwan_symbols():
    """自動從證交所與櫃買中心抓取全台股 4 位數普通股清單"""
    symbols = []
    
    # 1. 上市股票 (TWSE)
    try:
        res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", timeout=15)
        res.encoding = "big5"
        tw_matches = re.findall(r'(\d{4})\u3000', res.text)
        for s in set(tw_matches):
            symbols.append((s, f"{s}.TW"))
    except Exception as e:
        print(f"TWSE 抓取失敗: {e}")

    # 2. 上櫃股票 (TPEx)
    try:
        res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", timeout=15)
        res.encoding = "big5"
        two_matches = re.findall(r'(\d{4})\u3000', res.text)
        for s in set(two_matches):
            symbols.append((s, f"{s}.TWO"))
    except Exception as e:
        print(f"TPEx 抓取失敗: {e}")

    return symbols

def main():
    all_symbols = get_all_taiwan_symbols()
    print(f"共取得 {len(all_symbols)} 檔台股標的，開始分批打包抓取...")

    ticker_map = {t: s for s, t in all_symbols}
    all_tickers = list(ticker_map.keys())

    # 每 80 檔打包成一批，避免 Yahoo 阻擋請求
    chunk_size = 80
    market_data = []

    for i in range(0, len(all_tickers), chunk_size):
        chunk = all_tickers[i:i + chunk_size]
        try:
            data = yf.download(
                tickers=" ".join(chunk),
                period="6mo",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True
            )
            
            for ticker in chunk:
                try:
                    if len(chunk) == 1:
                        df = data
                    else:
                        if ticker in data.columns.levels[0]:
                            df = data[ticker]
                        else:
                            continue
                            
                    if df is None or df.empty:
                        continue
                        
                    closes = df['Close'].dropna()
                    if len(closes) < 10:
                        continue
                        
                    p_now = float(closes.iloc[-1])
                    p_5d = float(closes.iloc[-6]) if len(closes) >= 6 else float(closes.iloc[0])
                    p_1m = float(closes.iloc[-21]) if len(closes) >= 21 else float(closes.iloc[0])
                    p_1q = float(closes.iloc[-61]) if len(closes) >= 61 else float(closes.iloc[0])

                    r_5d = ((p_now - p_5d) / p_5d) * 100
                    r_1m = ((p_now - p_1m) / p_1m) * 100
                    r_1q = ((p_now - p_1q) / p_1q) * 100

                    score = round((r_5d * 0.2) + (r_1m * 0.5) + (r_1q * 0.3), 2)
                    sym = ticker_map[ticker]
                    market_data.append({"symbol": str(sym), "score": score})
                except:
                    continue
        except Exception as e:
            print(f"批次抓取錯誤: {e}")
        
        time.sleep(0.5)

    print(f"成功計算 {len(market_data)} 檔有效標的，開始計算全市場 PR 百分位...")

    # 排序並計算 PR 值 (1 ~ 99)
    market_data.sort(key=lambda x: x['score'], reverse=True)
    total_count = len(market_data)

    if total_count > 0:
        for idx, item in enumerate(market_data):
            pr = max(1, min(99, int(((total_count - idx) / total_count) * 100)))
            item['rs_rating'] = pr

    with open("market_rankings.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    print(f"全市場 RS 排名完成！共收錄 {total_count} 檔股票。")

if __name__ == "__main__":
    main()
    
