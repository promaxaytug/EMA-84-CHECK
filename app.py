import streamlit as st
import pandas as pd
import ccxt.pro as ccxt
import os
from dotenv import load_dotenv
import asyncio
import telegram
from datetime import datetime
import pytz
import numpy as np

# --- 1. YAPILANDIRMA VE BAŞLANGIÇ AYARLARI ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
st.set_page_config(page_title="EMA Trend Tarayıcı", layout="wide")
st.title("🚀 Hızlandırılmış EMA Trend Tarayıcı (Binance Futures)")

# --- 2. YARDIMCI FONKSİYONLAR ---

# GÜNCELLEME: İkon hesaplama fonksiyonu artık global ve 'Neutral' modu var
def get_status_icon(price, ema, direction):
    """Fiyatın EMA'ya göre durumunu belirler. 'Neutral' yönü mutlak durumu gösterir."""
    if ema is None: return "Veri Yetersiz"
    proximity = abs(price - ema) / ema
    if proximity <= 0.005: return "⚪️"
    
    if direction == 'Long':
        return "🟢" if price > ema else "🔴"
    elif direction == 'Short':
        return "🟢" if price < ema else "🔴"
    else: # Neutral (Mutlak Durum)
        return "🟢" if price > ema else "🔴"

def calculate_adx(high, low, close, period=14):
    plus_dm = high.diff()
    minus_dm = low.diff().mul(-1)
    tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean().replace(0, 1)
    plus_di = (plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0).ewm(span=period, adjust=False).mean() / atr) * 100
    minus_di = (minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0).ewm(span=period, adjust=False).mean() / atr) * 100
    dx_denominator = (plus_di + minus_di).replace(0, 1)
    dx = (abs(plus_di - minus_di) / dx_denominator) * 100
    return dx.ewm(span=period, adjust=False).mean().iloc[-1]

async def get_data_for_coin(exchange, symbol, ema_period, direction, apply_pre_filter):
    try:
        timeframes = ['15m', '1h', '4h', '1d']
        limit = ema_period * 3
        tasks = [exchange.fetch_ohlcv(symbol, tf, limit=limit) for tf in timeframes]
        ohlcv_data = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(ohlcv_data):
            if isinstance(result, Exception) or not result or len(result) < ema_period:
                return {"Coin": symbol, "Trend Score": 0, "Hata": "Veri Yetersiz"}
        
        data_15m, data_1h, data_4h, data_1d = ohlcv_data

        df_1h = pd.DataFrame(data_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(data_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_1d = pd.DataFrame(data_1d, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        ema_1h = df_1h['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
        ema_4h = df_4h['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
        ema_1d = df_1d['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
        price_1h = df_1h['close'].iloc[-1]
        price_4h = df_4h['close'].iloc[-1]
        price_1d = df_1d['close'].iloc[-1]

        if apply_pre_filter:
            pre_filter_passed = False
            if direction == 'Long':
                if price_1h > ema_1h and price_4h > ema_4h: pre_filter_passed = True
            else: # Short
                if price_1h < ema_1h and price_4h < ema_4h: pre_filter_passed = True
            if not pre_filter_passed:
                return None

        # GÜNCELLEME: İkonların yönü, filtrenin durumuna göre belirleniyor
        icon_direction = direction if apply_pre_filter else "Neutral"

        adx_1d = calculate_adx(df_1d['high'], df_1d['low'], df_1d['close'])
        adx_1h = calculate_adx(df_1h['high'], df_1h['low'], df_1h['close'])
        
        tr_1d = pd.concat([df_1d['high'] - df_1d['low'], abs(df_1d['high'] - df_1d['close'].shift(1)), abs(df_1d['low'] - df_1d['close'].shift(1))], axis=1).max(axis=1)
        atr_1d = tr_1d.ewm(span=14, adjust=False).mean().iloc[-1]
        atr_percent = (atr_1d / price_1d) * 100 if price_1d > 0 else 0
        distance_from_ema = ((price_1d - ema_1d) / ema_1d) * 100 if ema_1d > 0 else 0
        
        total_score = 0
        if direction == 'Long':
            if price_1d > ema_1d: total_score += 40
            if price_4h > ema_4h: total_score += 30
            if price_1h > ema_1h: total_score += 20
            if ema_1h > ema_4h: total_score += 10
        else:
            if price_1d < ema_1d: total_score += 40
            if price_4h < ema_4h: total_score += 30
            if price_1h < ema_1h: total_score += 20
            if ema_1h < ema_4h: total_score += 10
        
        df_15m = pd.DataFrame(data_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        ema_15m_21 = df_15m['close'].ewm(span=21, adjust=False).mean().iloc[-1]
        price_15m = df_15m['close'].iloc[-1]
        
        return {
            "Coin": symbol,
            "15m (21 EMA)": get_status_icon(price_15m, ema_15m_21, icon_direction),
            f"1h ({ema_period} EMA)": get_status_icon(price_1h, ema_1h, icon_direction),
            f"4h ({ema_period} EMA)": get_status_icon(price_4h, ema_4h, icon_direction),
            f"1d ({ema_period} EMA)": get_status_icon(price_1d, ema_1d, icon_direction),
            "Trend Score": total_score,
            "1H ADX (14)": f"{adx_1h:.2f}",
            "1D ADX (14)": f"{adx_1d:.2f}",
            "Günlük ATR %": f"{atr_percent:.2f}%",
            "Fiyatın 1D EMA'dan Uzaklığı %": f"{distance_from_ema:.2f}%"
        }
    except Exception as e:
        return {"Coin": symbol, "Trend Score": 0, "Hata": str(e)[:50]}

async def main_scanner(target_coins, ema_period, direction, apply_pre_filter):
    exchange_async = ccxt.binance({'options': {'defaultType': 'future'}})
    tasks = [get_data_for_coin(exchange_async, coin, ema_period, direction, apply_pre_filter) for coin in target_coins]
    results = []
    progress_bar = st.progress(0, text="Tarama başladı...")
    for i, task in enumerate(asyncio.as_completed(tasks)):
        result = await task
        results.append(result)
        progress_percentage = (i + 1) / len(tasks)
        progress_bar.progress(progress_percentage, text=f"{i+1}/{len(tasks)} coin analiz edildi...")
    await exchange_async.close()
    progress_bar.empty()
    final_results = [r for r in results if r is not None and "Hata" not in r]
    return final_results

# ... Diğer yardımcı fonksiyonlar ve UI Arayüzü (değişmedi) ...
def get_coin_lists(): return [f for f in os.listdir('.') if f.endswith('.txt')]
async def send_telegram_report(html_content):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID: st.error("Telegram bilgileri .env dosyasında eksik!"); return
    try:
        bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        with open("scan_results.html", "w", encoding="utf-8") as f: f.write(html_content)
        with open("scan_results.html", "rb") as f:
            await bot.send_document(chat_id=TELEGRAM_CHAT_ID, document=f, filename="Tarama_Sonuclari.html", caption="EMA Trend Tarama Raporu")
        st.success("Rapor Telegram'a başarıyla gönderildi!")
    except Exception as e: st.error(f"Telegram'a gönderirken hata oluştu: {e}")
    finally:
        if os.path.exists("scan_results.html"): os.remove("scan_results.html")

with st.sidebar:
    st.header("⚙️ Tarama Ayarları")
    analysis_mode = st.radio("Analiz Modu", ('Liste Tara', 'Tek Coin Analiz Et'), horizontal=True)
    selected_list, selected_coin = None, None
    if analysis_mode == 'Liste Tara':
        available_lists, list_options = get_coin_lists(), ["--- TÜMÜ ---"] + get_coin_lists()
        selected_list = st.selectbox("Liste Seç", options=list_options)
    else:
        try:
            with open('coin_list.txt', 'r') as f: coins = sorted([line.strip().upper() for line in f if line.strip()])
            selected_coin = st.selectbox("Coin Seç", options=coins)
        except FileNotFoundError: st.error("`coin_list.txt` dosyası bulunamadı!"); st.stop()
    direction = st.selectbox("İşlem Yönü", ('Long', 'Short'))
    ema_period = st.number_input("EMA Değeri", min_value=1, value=84)
    scan_button = st.button("🚀 Tara", use_container_width=True)

if scan_button:
    apply_pre_filter = True
    if analysis_mode == 'Tek Coin Analiz Et':
        apply_pre_filter = False
    elif analysis_mode == 'Liste Tara' and selected_list and selected_list.startswith('takip_'):
        apply_pre_filter = False
    target_coins = []
    if analysis_mode == 'Liste Tara':
        if selected_list == "--- TÜMÜ ---":
            all_coins = set()
            for file_name in get_coin_lists(): all_coins.update(line.strip().upper().replace('USDT', '/USDT') for line in open(file_name, 'r'))
            target_coins = sorted(list(all_coins))
        else:
            with open(selected_list, 'r') as f: target_coins = sorted([line.strip().upper().replace('USDT', '/USDT') for line in f if line.strip()])
    else:
        target_coins = [selected_coin.replace('USDT', '/USDT')]
    if not target_coins: st.warning("Analiz edilecek coin bulunamadı.")
    else:
        results = asyncio.run(main_scanner(target_coins, ema_period, direction, apply_pre_filter))
        if results:
            df = pd.DataFrame(results).sort_values(by="Trend Score", ascending=False).reset_index(drop=True)
            st.session_state['results_df'] = df
        else:
            message = "Filtreli tarama sonucunda koşulları sağlayan coin bulunamadı." if apply_pre_filter else "Seçilen coin(ler) için analiz tamamlandı."
            st.success(message)
            if 'results_df' in st.session_state: del st.session_state['results_df']

if 'results_df' in st.session_state and not st.session_state.results_df.empty:
    st.markdown("---"); st.subheader("🔍 Sonuçları Filtrele")
    col1, col2 = st.columns(2)
    with col1: filter_adx_1d = st.checkbox("Sadece 1D ADX > 25 Olanları Göster")
    with col2: filter_adx_1h = st.checkbox("Sadece 1H ADX > 25 Olanları Göster")
    filtered_df = st.session_state['results_df'].copy()
    if '1D ADX (14)' in filtered_df.columns: filtered_df['1D ADX (14)'] = pd.to_numeric(filtered_df['1D ADX (14)'], errors='coerce')
    if '1H ADX (14)' in filtered_df.columns: filtered_df['1H ADX (14)'] = pd.to_numeric(filtered_df['1H ADX (14)'], errors='coerce')
    if filter_adx_1d and '1D ADX (14)' in filtered_df.columns: filtered_df = filtered_df[filtered_df['1D ADX (14)'] > 25]
    if filter_adx_1h and '1H ADX (14)' in filtered_df.columns: filtered_df = filtered_df[filtered_df['1H ADX (14)'] > 25]
    st.dataframe(filtered_df, use_container_width=True)
    if st.button("Filtrelenmiş Sonuçları Telegram'a Gönder"):
        turkey_tz, now = pytz.timezone("Europe/Istanbul"), datetime.now(pytz.timezone("Europe/Istanbul"))
        timestamp_str = now.strftime("%d/%m/%Y --- %H:%M (GMT+3)")
        html_header = f"""<html><head><style>body {{ font-family: sans-serif; }} table {{ border-collapse: collapse; width: 100%; }} th, td {{ border: 1px solid #dddddd; text-align: center; padding: 8px; }} th {{ background-color: #f2f2f2; }} h3, p {{ text-align: center; }}</style></head><body><h3>EMA Trend Tarama Raporu</h3><p><b>Tarama Zamanı:</b> {timestamp_str}</p>"""
        html_footer, results_html = "</body></html>", filtered_df.to_html(index=False, justify='center', border=1)
        full_html = html_header + results_html + html_footer
        asyncio.run(send_telegram_report(full_html))