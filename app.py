import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime, timedelta
import logging
import threading
import time
from flask import Flask, jsonify

# إعداد نظام التسجيل
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ========== إعدادات تيليجرام ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
# ====================================

URL = "https://sp-today.com/currency/us-dollar"
DATA_FILE = "last_usd_price.json"

def load_last_price():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('buy_price'), data.get('sell_price')
    except Exception as e:
        logging.error(f"خطأ في التحميل: {e}")
    return None, None

def save_current_price(buy_price, sell_price):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'buy_price': buy_price,
                'sell_price': sell_price,
                'last_update': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"خطأ في الحفظ: {e}")

def get_usd_prices():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        page_text = soup.get_text()
        
        # أنماط البحث
        buy_pattern = r'شراء\s*([\d,]+)\s*ل\.س'
        sell_pattern = r'بيع\s*([\d,]+)\s*ل\.س'
        
        buy_match = re.search(buy_pattern, page_text)
        sell_match = re.search(sell_pattern, page_text)
        
        if buy_match and sell_match:
            buy_price = int(buy_match.group(1).replace(',', ''))
            sell_price = int(sell_match.group(1).replace(',', ''))
            logging.info(f"✅ تم جلب الأسعار - شراء: {buy_price}, بيع: {sell_price}")
            return buy_price, sell_price
        else:
            logging.warning("⚠️ لم يتم العثور على الأسعار في الصفحة")
            return None, None
        
    except Exception as e:
        logging.error(f"❌ خطأ في الجلب: {e}")
        return None, None

def send_to_channel(buy_price, sell_price):
    if not BOT_TOKEN or not CHANNEL_ID:
        logging.error("❌ BOT_TOKEN أو CHANNEL_ID غير مضبوط")
        return False
    
    if BOT_TOKEN.startswith("توكن"):
        logging.error("❌ يرجى تعديل BOT_TOKEN في متغيرات البيئة")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    change_percent = ((sell_price - buy_price) / buy_price) * 100 if buy_price else 0
    
    message = f"""💵 **سعر الدولار الأمريكي** 💵

━━━━━━━━━━━━━━━━━━━
🏦 **سعر الشراء:** `{buy_price:,}` ل.س
🏪 **سعر البيع:** `{sell_price:,}` ل.س
📊 **الفرق:** `{sell_price - buy_price:,}` ل.س
📈 **نسبة الفرق:** `{change_percent:.2f}%`
━━━━━━━━━━━━━━━━━━━

🕐 **آخر تحديث:** {timestamp}

_📢 تحديث كل ساعة_
"""
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.ok:
            logging.info("✅ تم الإرسال إلى القناة بنجاح")
            return True
        else:
            logging.error(f"❌ خطأ من تيليجرام: {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ خطأ في الإرسال: {e}")
        return False

def send_price_update():
    """إرسال تحديث السعر"""
    logging.info("🔄 بدء جلب سعر الدولار...")
    
    current_buy, current_sell = get_usd_prices()
    
    if not current_buy or not current_sell:
        logging.error("❌ فشل في جلب الأسعار")
        return
    
    logging.info(f"📊 السعر الحالي: شراء {current_buy:,} | بيع {current_sell:,}")
    
    if send_to_channel(current_buy, current_sell):
        save_current_price(current_buy, current_sell)
        logging.info("✅ تم تحديث الأسعار وإرسالها بنجاح")
    else:
        logging.error("❌ فشل الإرسال")

def scheduler_worker():
    """تشغيل المهام في الخلفية"""
    logging.info("🚀 بدء جدولة المهام - سيتم الإرسال كل ساعة")
    
    while True:
        now = datetime.now()
        
        # احسب الوقت حتى بداية الساعة القادمة
        next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        wait_seconds = (next_hour - now).total_seconds()
        
        logging.info(f"⏰ انتظار {wait_seconds/60:.0f} دقيقة حتى الساعة {next_hour.strftime('%H:%M')}")
        time.sleep(wait_seconds)
        
        # أرسل التحديث
        logging.info(f"🕐 الساعة {datetime.now().strftime('%H:%M')} - جاري الإرسال...")
        send_price_update()

@app.route('/')
def home():
    return jsonify({
        "status": "Bot is running",
        "time": datetime.now().isoformat(),
        "next_send": (datetime.now().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat()
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "time": datetime.now().isoformat()})

@app.route('/test')
def test():
    """مسار لاختبار الإرسال يدوياً"""
    send_price_update()
    return jsonify({"message": "Test sent! Check your channel and logs."})

# بدء تشغيل البوت
def start_bot():
    # بدء جدولة الإرسال في خلفية منفصلة
    thread = threading.Thread(target=scheduler_worker, daemon=True)
    thread.start()
    logging.info("🚀 تم بدء البوت")

if __name__ == "__main__":
    start_bot()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
