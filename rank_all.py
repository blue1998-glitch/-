import requests
import re
import yfinance as yf
import pandas as pd
import json
import concurrent.futures

def get_all_taiwan_symbols():
    """自動從證交所與櫃買中心抓取全台股 4 位數普通股清單"""
    symbols = []
    
    # 1. 抓取上市股票 (TWSE)
    try:
        res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", timeout=15)
        res.encoding = "big5"
        tw_matches = re.findall(r'(\d{4})\u3000', res.text)
        for s in set(tw_matches):
            symbols.append((s, f"{s}.TW"))
    except Exception as e:
        print(f"TWSE 抓取失敗: {e}")

    # 2. 抓取上櫃股票 (TPEx)
    try:
        res = requests.get("https://isin.twse.com.tw/isin/C_public.jsp?strMode=4", timeout=15)
        res.encoding = "big5"
        two_matches = re.findall(r'(\d{4})\u3000', res.text)
        for s in set(two_matches):
            symbols.append((s, f"{s}.TWO"))
    except Exception as e:
        print(f"TPEx 抓取失敗: {e}")

    return symbols

def process_single_stock(stock_tuple):
    """計算單檔股票極致動能加權分數"""
    sym, ticker = stock_tuple
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="6mo")
        if hist.empty or len(hist) < 10:
            return None
        
        closes = hist['Close']
        p_now = closes.iloc[-1]
        p_5d = closes.iloc[-6] if len(closes) >= 6 else closes.iloc[0]
        p_1m = closes.iloc[-21] if len(closes) >= 21 else closes.iloc[0]
        p_1q = closes.iloc[-61] if len(closes) >= 61 else closes.iloc[0]

        r_5d = ((p_now - p_5d) / p_5d) * 100
        r_1m = ((p_now - p_1m) / p_1m) * 100
        r_1q = ((p_now - p_1q) / p_1q) * 100

        # 極致動能權重：5日 20%、1個月 50%、1季 30%
        score = round((r_5d * 0.2) + (r_1m * 0.5) + (r_1q * 0.3), 2)
        return {"symbol": sym, "score": score}
    except:
        return None

def main():
    all_symbols = get_all_taiwan_symbols()
    print(f"共取得 {len(all_symbols)} 檔台股標的，開始平行運算動能...")

    market_data = []
    # 使用 12 條線程平行加速計算
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(process_single_stock, all_symbols))

    market_data = [r for r in results if r is not None]
    
    # 依照綜合動能分數由大到小排序
    market_data.sort(key=lambda x: x['score'], reverse=True)
    total_count = len(market_data)
    print(f"成功計算 {total_count} 檔有效股票，開始計算全市場 PR 百分位...")

    # 計算全市場百分位 PR 值 (1 ~ 99)
    if total_count > 0:
        for i, item in enumerate(market_data):
            pr = max(1, min(99, int(((total_count - i) / total_count) * 100)))
            item['rs_rating'] = pr

    # 輸出至 market_rankings.json
    with open("market_rankings.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)
    print("全市場 RS 排名計算完成並已儲存！")

if __name__ == "__main__":
    main()
