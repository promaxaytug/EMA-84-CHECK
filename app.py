import streamlit as st
import pandas as pd
import ccxt
import os
from dotenv import load_dotenv
import asyncio
import telegram
from datetime import datetime
import pytz

# --- 1. YAPILANDIRMA ---
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
st.set_page_config(page_title="EMA Trend Tarayıcı", layout="wide")
st.title("🐞 EMA Trend Tarayıcı (Teşhis Modu)")

# GÜNCELLEME: Exchange nesnesi artık global olarak tanımlanıyor.
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

# --- 2. YARDIMCI FONKSİYONLAR ---

# GÜNCELLEME: Fonksiyon artık 'exchange' parametresi almıyor, global olanı kullanıyor.
@st.cache_data(ttl=300) 
def get_ohlcv(symbol, timeframe, limit=500):
    """Fonksiyon artık global exchange nesnesini kullanıyor."""
    try:
        return exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    except Exception as e:
        return []

# --- ARAYÜZ (STREAMLIT UI) ---
with st.sidebar:
    st.header("⚙️ Tarama Ayarları")
    analysis_mode = st.radio("Analiz Modu", ('Liste Tara', 'Tek Coin Analiz Et'), horizontal=True)
    
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
    st.markdown("---")
    debug_mode = st.checkbox("🐞 Hata Ayıklama Modunu Aktif Et", value=True)

# --- ANA İŞ AKIŞI ---
if scan_button:
    if debug_mode:
        st.subheader("🐞 Hata Ayıklama Raporu: BTC/USDT")
        st.info("Bu rapor, bulut sunucusunun filtreleme için kullandığı kesin değerleri göstermektedir.")

        with st.spinner("BTC/USDT için 1S ve 4S verileri çekiliyor..."):
            # GÜNCELLEME: Fonksiyona artık 'exchange' parametresi gönderilmiyor.
            data_1h = get_ohlcv('BTC/USDT', '1h')
            data_4h = get_ohlcv('BTC/USDT', '4h')
        
        st.markdown("---")
        st.write(f"**Veri Çekme Sonuçları:**")
        st.write(f"1S için alınan mum sayısı: `{len(data_1h)}`")
        st.write(f"4S için alınan mum sayısı: `{len(data_4h)}`")

        if not data_1h or not data_4h or len(data_1h) < ema_period or len(data_4h) < ema_period:
            st.error("Veri Yetersiz! Sunucu, BTC/USDT için bile yeterli sayıda mum verisi alamıyor.")
        else:
            st.success("Veri çekme başarılı, yeterli sayıda mum mevcut.")
            st.markdown("---")
            st.write("**Hesaplama Sonuçları:**")
            
            df_1h = pd.DataFrame(data_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h = pd.DataFrame(data_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            ema_1h = df_1h['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
            ema_4h = df_4h['close'].ewm(span=ema_period, adjust=False).mean().iloc[-1]
            price_1h = df_1h['close'].iloc[-1]
            price_4h = df_4h['close'].iloc[-1]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label=f"1S Anlık Fiyat", value=f"{price_1h:,.2f}")
                st.metric(label=f"1S {ema_period} EMA", value=f"{ema_1h:,.2f}")
            with col2:
                st.metric(label="4S Anlık Fiyat", value=f"{price_4h:,.2f}")
                st.metric(label=f"4S {ema_period} EMA", value=f"{ema_4h:,.2f}")

            st.markdown("---")
            st.write("**Filtreleme Kontrolü:**")
            st.write(f"Seçilen Yön: **{direction}**")

            check_1h = price_1h > ema_1h if direction == 'Long' else price_1h < ema_1h
            check_4h = price_4h > ema_4h if direction == 'Long' else price_4h < ema_4h
            
            st.write(f"1S Koşulu Sağlandı mı? (`Fiyat {' >' if direction == 'Long' else ' <'} EMA`): **{check_1h}**")
            st.write(f"4S Koşulu Sağlandı mı? (`Fiyat {' >' if direction == 'Long' else ' <'} EMA`): **{check_4h}**")

            final_verdict = "✅ GEÇTİ" if (check_1h and check_4h) else "❌ GEÇEMEDİ"
            st.subheader(f"Genel Sonuç: {final_verdict}")
    else:
        st.warning("Normal tarama modu bu test versiyonunda devre dışıdır. Lütfen Hata Ayıklama Modu ile devam edin.")