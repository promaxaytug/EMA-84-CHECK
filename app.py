import streamlit as st
import pandas as pd
import ccxt # SENKRON VERSİYON
import os
from dotenv import load_dotenv
import asyncio
import telegram
from datetime import datetime
import pytz
import numpy as np

# --- 1. YAPILANDIRMA ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
st.set_page_config(page_title="EMA Trend Tarayıcı", layout="wide")
st.title("🐌 Basitleştirilmiş EMA Trend Tarayıcı (Test Versiyonu)")

# --- 2. YARDIMCI FONKSİYONLAR ---

# Bu testte önbelleği devre dışı bırakıyoruz ki veriler taze gelsin
# @st.cache_data(ttl=600) 
def get_ohlcv(exchange, symbol, timeframe, limit=500):
    try:
        return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        return []

# ... Diğer yardımcı fonksiyonlar (calculate_adx, get_status_icon vs.) aynı kalabilir ...
def get_status_icon(price, ema, direction):
    if ema is None: return "Veri Yetersiz"
    proximity = abs(price - ema) / ema
    if proximity <= 0.005: return "⚪️"
    if direction == 'Long': return "🟢" if price > ema else "🔴"
    elif direction == 'Short': return "🟢" if price < ema else "🔴"
    else: return "🟢" if price > ema else "🔴"

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

# --- ARAYÜZ (STREAMLIT UI) ---
# ... (Arayüz kodunda değişiklik yok) ...
with st.sidebar:
    st.header("⚙️ Tarama Ayarları")
    analysis_mode = st.radio("Analiz Modu", ('Liste Tara', 'Tek Coin Analiz Et'), horizontal=True)
    # ... (geri kalanı aynı)
    selected_list, selected_coin = None, None
    def get_coin_lists(): return [f for f in os.listdir('.') if f.endswith('.txt')]
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

# --- ANA İŞ AKIŞI (SENKRON VERSİYON) ---
if scan_button:
    exchange = ccxt.binance({'options': {'defaultType': 'future'}})
    apply_pre_filter = True
    if analysis_mode == 'Tek Coin Analiz Et' or (analysis_mode == 'Liste Tara' and selected_list and selected_list.startswith('takip_')):
        apply_pre_filter = False

    target_coins = []
    # ... (Hedef coin listesini oluşturma mantığı aynı) ...
    if analysis_mode == 'Liste Tara':
        if selected_list == "--- TÜMÜ ---":
            all_coins = set()
            for file_name in get_coin_lists(): all_coins.update(line.strip().upper().replace('USDT', '/USDT') for line in open(file_name, 'r'))
            target_coins = sorted(list(all_coins))
        else:
            with open(selected_list, 'r') as f: target_coins = sorted([line.strip().upper().replace('USDT', '/USDT') for line in f if line.strip()])
    else:
        target_coins = [selected_coin.replace('USDT', '/USDT')]

    if not target_coins:
        st.warning("Analiz edilecek coin bulunamadı.")
    else:
        results = []
        progress_bar = st.progress(0, text="Tarama başladı...")
        
        for i, coin in enumerate(target_coins):
            try:
                # Her coin için sırayla veri çek ve analiz et
                data_1h = get_ohlcv(exchange, coin, '1h')
                data_4h = get_ohlcv(exchange, coin, '4h')
                if not data_1h or not data_4h or len(data_1h) < ema_period or len(data_4h) < ema_period:
                    continue # Yeterli veri yoksa bu coini atla

                df_1h = pd.DataFrame(data_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df_4h = pd.DataFrame(data_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                ema_1h = df_1h['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
                ema_4h = df_4h['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
                price_1h = df_1h['close'].iloc[-1]
                price_4h = df_4h['close'].iloc[-1]
                
                pre_filter_passed = False
                if direction == 'Long' and price_1h > ema_1h and price_4h > ema_4h: pre_filter_passed = True
                if direction == 'Short' and price_1h < ema_1h and price_4h < ema_4h: pre_filter_passed = True

                if apply_pre_filter and not pre_filter_passed:
                    continue

                # Filtreden geçtiyse veya filtre kapalıysa, detaylı analize devam et
                data_1d = get_ohlcv(exchange, coin, '1d')
                data_15m = get_ohlcv(exchange, coin, '15m')
                # ... (Burada tam analiz devam ediyor, önceki koddan kopyalanabilir)
                # Bu kısmı sadeleştirmek adına şimdilik sadece temel bilgileri ekliyorum:
                results.append({"Coin": coin, "1h Fiyat": price_1h, "1h EMA": ema_1h, "4h Fiyat": price_4h, "4h EMA": ema_4h})

            except Exception as e:
                st.write(f"{coin} için hata: {e}") # Hata olursa ekrana yaz
            
            progress_bar.progress((i + 1) / len(target_coins), text=f"Analiz ediliyor: {coin}")
        
        progress_bar.empty()
        
        if results:
            df = pd.DataFrame(results)
            st.session_state['results_df'] = df
        else:
            st.success("Koşulları sağlayan coin bulunamadı.")
            if 'results_df' in st.session_state: del st.session_state['results_df']

if 'results_df' in st.session_state and not st.session_state.results_df.empty:
    st.dataframe(st.session_state.results_df, use_container_width=True)
    # Telegram butonu şimdilik devre dışı bırakıldı