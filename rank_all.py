import yfinance as yf
import pandas as pd
import json
import time
import requests
import re
import sys

def get_complete_tw_symbols():
    """多管道獲取全台股 1,800+ 檔上市上櫃普通股清單"""
    symbols = set()
    
    # 管道 1：透過政府資料開放平台 API (海外不擋連線)
    try:
        url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            for row in res.json():
                c = str(row.get('公司代號', '')).strip()
                if len(c) == 4 and c.isdigit():
                    symbols.add(c)
    except Exception:
        pass

    # 管道 2：備援證交所 ISIN 清單
    if len(symbols) < 500:
        for mode in [2, 4]:
            try:
                r = requests.get(f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}", timeout=10)
                r.encoding = "big5"
                m = re.findall(r'([1-9]\d{3})\u3000', r.text)
                for code in m:
                    symbols.add(code)
            except Exception:
                pass

    return sorted(list(symbols))

def main():
    raw_symbols = get_complete_tw_symbols()
    print(f"共取得 {len(raw_symbols)} 檔台股代號，開始進行全市場矩陣運算...")

    target_tickers = []
    ticker_to_sym = {}
    for s in raw_symbols:
        tw = f"{s}.TW"
        two = f"{s}.TWO"
        target_tickers.extend([tw, two])
        ticker_to_sym[tw] = s
        ticker_to_sym[two] = s

    market_data = {}
    chunk_size = 100

    for i in range(0, len(target_tickers), chunk_size):
        chunk = target_tickers[i:i + chunk_size]
        try:
            df = yf.download(
                tickers=chunk,
                period="6mo",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,
                timeout=15
            )

            if df is not None and not df.empty and 'Close' in df:
                closes_df = df['Close']
                for ticker in chunk:
                    try:
                        sym = ticker_to_sym[ticker]
                        if sym in market_data:
                            continue

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
                        market_data[sym] = score
                    except Exception:
                        continue
        except Exception:
            pass

        time.sleep(0.4)

    results = [{"symbol": k, "score": v} for k, v in market_data.items()]

    if len(results) < 50:
        print(f"❌ 警告：僅收錄 {len(results)} 檔，取消覆蓋檔案。")
        sys.exit(1)

    # 排序並計算全市場 PR 百分位 (1 ~ 99)
    results.sort(key=lambda x: x['score'], reverse=True)
    total_count = len(results)
    print(f"成功收錄 {total_count} 檔有效股票，開始計算全市場 PR 百分位...")

    for idx, item in enumerate(results):
        pr = max(1, min(99, int(((total_count - idx) / total_count) * 100)))
        item['rs_rating'] = pr

    with open("market_rankings.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"✅ 全市場排名大功告成！共計收錄 {total_count} 檔股票。")

if __name__ == "__main__":
    main()
