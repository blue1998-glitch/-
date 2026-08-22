import yfinance as yf
import pandas as pd
import json
import time
import requests
import sys

def get_tw_market_tickers():
    """分別向官方 API 抓取上市與上櫃清單，並精確標註 .TW 與 .TWO"""
    target_list = []  # 存 (symbol, ticker)
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. 抓取上市股票 (TWSE) -> 對應 .TW
    try:
        url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        res = requests.get(url_twse, headers=headers, timeout=12)
        if res.status_code == 200:
            for row in res.json():
                c = str(row.get('公司代號', '')).strip()
                if len(c) == 4 and c.isdigit():
                    target_list.append((c, f"{c}.TW"))
    except Exception as e:
        print(f"TWSE API 連線異常: {e}")

    # 2. 抓取上櫃股票 (TPEx) -> 對應 .TWO
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
        res = requests.get(url_tpex, headers=headers, timeout=12)
        if res.status_code == 200:
            for row in res.json():
                c = str(row.get('SecuritiesCompanyCode', row.get('公司代號', ''))).strip()
                if len(c) == 4 and c.isdigit():
                    target_list.append((c, f"{c}.TWO"))
    except Exception as e:
        print(f"TPEx API 連線異常: {e}")

    # 去重
    unique_map = {}
    for s, t in target_list:
        if s not in unique_map:
            unique_map[s] = t

    return [(k, v) for k, v in unique_map.items()]

def main():
    ticker_pairs = get_tw_market_tickers()
    print(f"成功取得台股全市場 {len(ticker_pairs)} 檔有效標的（含上市與上櫃），開始批次下載...")

    if len(ticker_pairs) < 500:
        print("❌ 取得代號數量不足，取消覆蓋檔案。")
        sys.exit(1)

    all_tickers = [t for s, t in ticker_pairs]
    ticker_to_sym = {t: s for s, t in ticker_pairs}

    # 每批 60 檔，發送精準代號，避免 Yahoo 丟失資料
    chunk_size = 60
    market_data = []

    for i in range(0, len(all_tickers), chunk_size):
        chunk = all_tickers[i:i + chunk_size]
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
                        sym = ticker_to_sym[ticker]
                        market_data.append({"symbol": sym, "score": score})
                    except Exception:
                        continue
        except Exception:
            pass

        time.sleep(0.4)

    # 排序並計算全市場 PR 百分位 (1 ~ 99)
    market_data.sort(key=lambda x: x['score'], reverse=True)
    total_count = len(market_data)
    print(f"成功收錄 {total_count} 檔有效股票，開始計算全市場 PR 百分位...")

    if total_count < 1000:
        print(f"❌ 警告：成功計算筆數 ({total_count}) 低於 1000，取消覆蓋檔案。")
        sys.exit(1)

    for idx, item in enumerate(market_data):
        pr = max(1, min(99, int(((total_count - idx) / total_count) * 100)))
        item['rs_rating'] = pr

    with open("market_rankings.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 全市場排名大功告成！共計收錄 {total_count} 檔股票。")

if __name__ == "__main__":
    main()
