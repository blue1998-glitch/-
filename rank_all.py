import yfinance as yf
import pandas as pd
import numpy as np
import json
import time
import requests
import sys

def get_tw_market_tickers():
    """抓取全台股代號、中文簡稱與上市櫃類別"""
    target_list = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. 上市 (TWSE)
    try:
        url_twse = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        res = requests.get(url_twse, headers=headers, timeout=12)
        if res.status_code == 200:
            for row in res.json():
                c = str(row.get('公司代號', '')).strip()
                n = str(row.get('公司簡稱', row.get('公司名稱', c))).strip()
                if len(c) == 4 and c.isdigit():
                    target_list.append({"symbol": c, "name": n, "market": "上市", "ticker": f"{c}.TW"})
    except Exception as e:
        print(f"TWSE API 連線異常: {e}")

    # 2. 上櫃 (TPEx)
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O"
        res = requests.get(url_tpex, headers=headers, timeout=12)
        if res.status_code == 200:
            for row in res.json():
                c = str(row.get('SecuritiesCompanyCode', row.get('公司代號', ''))).strip()
                n = str(row.get('CompanyAbbreviation', row.get('SecuritiesCompanyName', row.get('公司簡稱', c)))).strip()
                if len(c) == 4 and c.isdigit():
                    target_list.append({"symbol": c, "name": n, "market": "上櫃", "ticker": f"{c}.TWO"})
    except Exception as e:
        print(f"TPEx API 連線異常: {e}")

    # 去重
    unique_map = {item["symbol"]: item for item in target_list}
    return list(unique_map.values())

def calculate_master_vcp_rs(close_series: pd.Series, high_series: pd.Series, low_series: pd.Series):
    """
    Minervini / O'Neil 風格：專注於【新高突破】與【VCP即將創新高】的 RS 動能引擎
    """
    if len(close_series) < 61:
        return 0.0, "📦 潛伏盤整", 0.0, 0.0, 0.0, float(close_series.iloc[-1])

    closes = close_series.values
    highs = high_series.values
    lows = low_series.values

    p_now = float(closes[-1])
    p_5d = float(closes[-6])
    p_20d = float(closes[-21])
    p_60d = float(closes[-61])
    
    # 1. 計算多週期實質報酬率
    r_5d = ((p_now - p_5d) / p_5d) * 100
    r_20d = ((p_now - p_20d) / p_20d) * 100
    r_60d = ((p_now - p_60d) / p_60d) * 100

    # 基礎動能得分
    base_momentum = (r_5d * 0.30) + (r_20d * 0.45) + (r_60d * 0.25)
    
    # 2. 【新高接近度係數 Proximity Factor】
    high_60d = float(np.max(highs[-60:]))
    off_high_pct = ((high_60d - p_now) / high_60d) * 100 if high_60d > 0 else 0.0  # 0% 代表創 60 日新高
    
    if off_high_pct <= 0.5:
        h_prox = 1.25  # 創 60 日新高，給予 1.25 倍突破獎勵
    elif off_high_pct <= 8.0:
        h_prox = 1.12 - (off_high_pct / 8.0) * 0.12  # 距高點 8% 內，微幅加成 (1.12 ~ 1.0)
    elif off_high_pct <= 18.0:
        h_prox = 1.0 - ((off_high_pct - 8.0) / 10.0) * 0.25  # 距高點 8~18%，輕微衰減 (1.0 ~ 0.75)
    else:
        # 跌幅超過 18%，上方套牢賣壓沉重，重罰
        h_prox = max(0.20, 0.75 - ((off_high_pct - 18.0) / 20.0) * 0.55)

    # 3. 【VCP 波動收斂度 Tightness Factor】
    high_10d = float(np.max(highs[-10:]))
    low_10d = float(np.min(lows[-10:]))
    range_10d = ((high_10d - low_10d) / low_10d) * 100 if low_10d > 0 else 20.0  # 近 10 日震幅

    if range_10d <= 7.0 and off_high_pct <= 10.0:
        v_tight = 1.18  # 經典 VCP：極窄震幅 + 緊貼高點 (即將噴出)
    elif range_10d <= 12.0 and off_high_pct <= 12.0:
        v_tight = 1.08  # 次級收斂整理
    elif range_10d > 22.0:
        v_tight = 0.85  # 波動過大，籌碼未沉澱
    else:
        v_tight = 1.00

    # 4. 【趨勢結構健康度與均線濾網】
    ma20 = float(np.mean(closes[-20:]))
    ma60 = float(np.mean(closes[-60:]))
    
    t_trend = 1.0
    if p_now < ma60:
        t_trend *= 0.35  # 季線之下，嚴懲
    if p_now < ma20:
        t_trend *= 0.75  # 月線之下，非即時發動結構
    if r_20d < 0 and r_5d > 0:
        t_trend *= 0.65  # 月線為負之短線反彈波，折扣

    # 5. 最終綜合順勢得分
    final_score = base_momentum * h_prox * v_tight * t_trend

    # 6. 自動打上「順勢型態特徵標籤」
    if off_high_pct <= 1.0 and r_5d >= 3.0:
        pattern_badge = "⭐ 歷史/區間新高"
    elif off_high_pct <= 8.0 and range_10d <= 9.0:
        pattern_badge = "🎯 VCP收縮蓄勢"
    elif off_high_pct <= 12.0 and p_now >= ma20:
        pattern_badge = "🚀 右側強勢整理"
    elif r_20d < 0 and r_5d > 0:
        pattern_badge = "⚠️ 左側弱勢反彈"
    else:
        pattern_badge = "📦 區間整理"

    return round(final_score, 2), pattern_badge, round(r_5d, 2), round(r_20d, 2), round(r_60d, 2), round(p_now, 2)

def main():
    stock_info_list = get_tw_market_tickers()
    print(f"成功取得台股全市場 {len(stock_info_list)} 檔標的資料，開始批次下載動能...")

    if len(stock_info_list) < 500:
        print("❌ 取得代號數量不足，取消覆蓋檔案。")
        sys.exit(1)

    all_tickers = [item["ticker"] for item in stock_info_list]
    ticker_to_info = {item["ticker"]: item for item in stock_info_list}

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

            if df is not None and not df.empty and 'Close' in df and 'High' in df and 'Low' in df:
                closes_df = df['Close']
                highs_df = df['High']
                lows_df = df['Low']

                for ticker in chunk:
                    try:
                        # 處理收盤價、最高價與最低價序列
                        if isinstance(closes_df, pd.DataFrame):
                            if ticker in closes_df.columns:
                                close_series = closes_df[ticker].dropna()
                                high_series = highs_df[ticker].dropna()
                                low_series = lows_df[ticker].dropna()
                            else:
                                continue
                        elif isinstance(closes_df, pd.Series):
                            close_series = closes_df.dropna()
                            high_series = highs_df.dropna()
                            low_series = lows_df.dropna()
                        else:
                            continue

                        if len(close_series) < 61:
                            continue

                        score, badge, r_5d, r_20d, r_60d, cur_p = calculate_master_vcp_rs(
                            close_series, high_series, low_series
                        )
                        info = ticker_to_info[ticker]
                        
                        market_data.append({
                            "symbol": info["symbol"],
                            "name": info["name"],
                            "market": info["market"],
                            "close_price": cur_p,
                            "r_5d": r_5d,
                            "r_20d": r_20d,
                            "r_60d": r_60d,
                            "score": score,
                            "pattern_badge": badge
                        })
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
