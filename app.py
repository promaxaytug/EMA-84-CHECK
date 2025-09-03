import streamlit as st
import ccxt
import os
from dotenv import load_dotenv

# --- YAPILANDIRMA ---
load_dotenv()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY") or st.secrets.get("BINANCE_API_KEY")
BINANCE_SECRET_KEY = os.getenv("BINANCE_SECRET_KEY") or st.secrets.get("BINANCE_SECRET_KEY")

st.set_page_config(page_title="Bağlantı Testi", layout="centered")
st.title("Binance Futures Bağlantı Testi")
st.info("Bu araç, Streamlit Cloud sunucusunun Binance API'sine ulaşıp veri çekip çekemediğini test eder.")

if not BINANCE_API_KEY or not BINANCE_SECRET_KEY:
    st.error("API Anahtarları Streamlit Secrets içinde bulunamadı!")
else:
    st.success("API Anahtarları Streamlit Secrets'tan başarıyla okundu.")

    exchange = ccxt.binance({
        'apiKey': BINANCE_API_KEY,
        'secret': BINANCE_SECRET_KEY,
        'options': {
            'defaultType': 'future',
        },
        'enableRateLimit': True,
    })

    st.markdown("---")
    st.subheader("Test Adımı: BTC/USDT için 1 Saatlik Veri Çekme")

    try:
        with st.spinner("Binance Futures'a bağlanılıyor ve veri isteniyor..."):
            # Önce marketleri yüklemeyi dene, bu bağlantıyı test eder
            exchange.load_markets()
            st.write("✅ Market verileri başarıyla yüklendi (Bağlantı OK).")

            # Şimdi mum verilerini çekmeyi dene
            ohlcv = exchange.fetch_ohlcv('BTC/USDT', '1h', limit=2)
            st.write("✅ `fetch_ohlcv` komutu başarıyla çalıştı.")
            
        st.markdown("---")
        st.subheader("Sonuç:")
        
        if ohlcv:
            st.success("TEST BAŞARILI! Veri başarıyla çekildi.")
            st.write("Çekilen Ham Veri:")
            st.json(ohlcv)
        else:
            st.error("TEST BAŞARISIZ! Bağlantı kuruldu ancak Binance hiçbir veri (boş liste) göndermedi. Bu genellikle bir IP kısıtlaması veya API anahtar izni sorunudur.")

    except ccxt.AuthenticationError:
        st.error("TEST BAŞARISIZ! Kimlik Doğrulama Hatası (AuthenticationError). Lütfen API Anahtarı ve Secret Key'inizin doğru olduğundan ve izinlerinin tam olduğundan emin olun.")
    except ccxt.NetworkError:
        st.error("TEST BAŞARISIZ! Ağ Hatası (NetworkError). Streamlit sunucusu Binance'e ulaşamıyor. Bu geçici bir sorun veya bir IP engellemesi olabilir.")
    except Exception as e:
        st.error(f"TEST BAŞARISIZ! Beklenmedik bir hata oluştu: {e}")