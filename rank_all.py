import requests
import re
import yfinance as yf
import pandas as pd
import json
import time

def get_all_taiwan_symbols():
    """精準抓取台股上市與上櫃 4 位數普通股清單"""
    symbols = []
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    # 1. 上市 (TWSE)
    try:
        res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", headers=headers, timeout=15)
        res.encoding = "big5"
        matches = re.findall(r'([1-9]\d{3})\u3000', res.text)
        for s in set(matches):
            symbols.append((s, f"{s}.TW"))
    except Exception as e:
        print(f"TWSE 抓取異常: {e}")

    # 2. 上櫃 (TPEx)
    try:
        res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", headers=headers, timeout=15)
        res.encoding = "big5"
        matches = re.findall(r'([1-9]\d{3})\u3000', res.text)
        for s in set(matches):
            symbols.append((s, f"{s}.TWO"))
    except Exception as e:
        print(f"TPEx 抓取異常: {e}")

    # 排除重複代號
    seen = set()
    clean_symbols = []
    for s, t in symbols:
        if s not in seen:
            seen.add(s)
            clean_symbols.append((s, t))
    return clean_symbols

def main():
    all_symbols = get_all_taiwan_symbols()
    print(f"共取得 {len(all_symbols)} 檔普通股標的，開始穩健分批抓取...")

    ticker_map = {t: s for s, t in all_symbols}
    all_tickers = list(ticker_map.keys())

    # 每批 50 檔，總共約 35 批，耗時約 80 秒，避開 Yahoo 頻率限制
    chunk_size = 50
    market_data = []

    for i in range(0, len(all_tickers), chunk_size):
        chunk = all_tickers[i:i + chunk_size]
        
        df = None
        for attempt in range(2):
            try:
                df = yf.download(
                    tickers=chunk,
                    period="6mo",
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    threads=True,
                    timeout=20
                )
                if df is not None and not df.empty and 'Close' in df:
                    break
            except Exception:
                time.sleep(2)
        
        if df is not None and not df.empty and 'Close' in df:
            closes_df = df['Close']
            for ticker in chunk:
                try:
                    if isinstance(closes_df, pd.DataFrame):
                        if ticker in closes_df.columns:
                            series = closes_df[ticker].dropna()
                        else:
                            continue
                    elif isinstance(closes_df, pd.Series):
                        series = closes_df.dropna()
                    else:
                        continue

                    if len(series) < 10:
                        continue

                    p_now = float(series.iloc[-1])
                    p_5d = float(series.iloc[-6]) if len(series) >= 6 else float(series.iloc[0])
                    p_1m = float(series.iloc[-21]) if len(series) >= 21 else float(series.iloc[0])
                    p_1q = float(series.iloc[-61]) if len(series) >= 61 else float(series.iloc[0])

                    r_5d = ((p_now - p_5d) / p_5d) * 100
                    r_1m = ((p_now - p_1m) / p_1m) * 100
                    r_1q = ((p_now - p_1q) / p_1q) * 100

                    score = round((r_5d * 0.2) + (r_1m * 0.5) + (r_1q * 0.3), 2)
                    sym = ticker_map[ticker]
                    market_data.append({"symbol": str(sym), "score": score})
                except Exception:
                    continue
        
        time.sleep(1.0)

    # 排序並計算全市場 PR 百分位 (1 ~ 99)
    market_data.sort(key=lambda x: x['score'], reverse=True)
    total_count = len(market_data)
    print(f"成功收錄 {total_count} 檔有效股票，開始計算全市場 PR 值...")

    if total_count > 0:
        for idx, item in enumerate(market_data):
            pr = max(1, min(99, int(((total_count - idx) / total_count) * 100)))
            item['rs_rating'] = pr

    with open("market_rankings.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 全市場排名大功告成！共計收錄 {total_count} 檔股票。")

if __name__ == "__main__":
    main()
