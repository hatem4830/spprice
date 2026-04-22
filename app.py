import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime
import logging
import threading
import time
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ========== إعدادات تيليجرام ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
# ====================================

URL = "https://sp-today.com/currency/us-dollar"
DATA_FILE = "last_usd_price.json"

def load_last_price():
    """تحميل آخر سعر محفوظ"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('buy_price'), data.get('sell_price')
    except:
        pass
    return None, None

def save_current_price(buy_price, sell_price):
    """حفظ السعر الحالي"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'buy_price': buy_price,
                'sell_price': sell_price,
                'last_update': datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    except:
        pass

def get_usd_prices():
    """جلب سعر الشراء والبيع من الصفحة"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
        'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
    }
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()
        
        buy_pattern = r'شراء\s*([\d,]+)\s*ل\.س'
        sell_pattern = r'بيع\s*([\d,]+)\s*ل\.س'
        
        buy_match = re.search(buy_pattern, page_text)
        sell_match = re.search(sell_pattern, page_text)
        
        if buy_match and sell_match:
            buy_price = int(buy_match.group(1).replace(',', ''))
            sell_price = int(sell_match.group(1).replace(',', ''))
            return buy_price, sell_price
        return None, None
        
    except Exception as e:
        logging.error(f"خطأ في الجلب: {e}")
        return None, None

def send_to_channel(buy_price, sell_price, price_changed=False):
    """إرسال السعر إلى القناة"""
    if not BOT_TOKEN or not CHANNEL_ID:
        logging.error("BOT_TOKEN أو CHANNEL_ID غير مضبوط")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    change_indicator = "🟢 **تغير السعر!** 🟢\n\n" if price_changed else ""
    
    message = f"""💵 **سعر الدولار الأمريكي** 💵

{change_indicator}━━━━━━━━━━━━━━━━━━━
🏦 **سعر الشراء:** `{buy_price:,}` ل.س
🏪 **سعر البيع:** `{sell_price:,}` ل.س
📊 **الفرق:** `{sell_price - buy_price:,}` ل.س
━━━━━━━━━━━━━━━━━━━

🕐 **آخر تحديث:** {timestamp}

{'_🔄 تحديث تلقائي (كل ساعة)_' if not price_changed else '_⚡ تحديث فوري بسبب تغير السعر_'}
"""
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.ok
    except Exception as e:
        logging.error(f"خطأ في الإرسال: {e}")
        return False

def check_and_send():
    """التحقق من السعر وإرساله إذا تغير (أو كل ساعة)"""
    logging.info("🔄 جلب سعر الدولار...")
    
    current_buy, current_sell = get_usd_prices()
    
    if not current_buy or not current_sell:
        logging.error("❌ فشل في جلب الأسعار")
        return
    
    logging.info(f"📊 السعر الحالي: شراء {current_buy:,} | بيع {current_sell:,}")
    
    # تحميل آخر سعر
    last_buy, last_sell = load_last_price()
    
    # التحقق من التغير
    price_changed = False
    if last_buy and last_sell:
        if current_buy != last_buy or current_sell != last_sell:
            price_changed = True
            logging.info(f"🔄 تغير السعر! سابق: {last_buy:,} → جديد: {current_buy:,}")
    
    # إرسال التحديث (إذا تغير السعر أو كانت هذه أول مرة)
    if price_changed or not last_buy:
        logging.info("📤 جاري الإرسال (تغير السعر)...")
        if send_to_channel(current_buy, current_sell, price_changed=True):
            save_current_price(current_buy, current_sell)
            logging.info("✅ تم الإرسال وحفظ السعر الجديد")
    else:
        logging.info("✅ السعر لم يتغير - لن يتم الإرسال (سيتم الإرسال كل ساعة فقط)")

def hourly_update():
    """إرسال تحديث كل ساعة (حتى لو لم يتغير السعر)"""
    logging.info("🕐 تحديث الساعة - جاري جلب الأسعار...")
    
    current_buy, current_sell = get_usd_prices()
    
    if current_buy and current_sell:
        last_buy, last_sell = load_last_price()
        
        # التحقق مما إذا كان السعر قد تغير منذ آخر إرسال ساعي
        price_changed = False
        if last_buy and last_sell:
            if current_buy != last_buy or current_sell != last_sell:
                price_changed = True
        
        if send_to_channel(current_buy, current_sell, price_changed):
            save_current_price(current_buy, current_sell)
            logging.info("✅ تم إرسال التحديث الساعي")
        else:
            logging.error("❌ فشل الإرسال الساعي")
    else:
        logging.error("❌ فشل في جلب الأسعار للتحديث الساعي")

def continuous_monitor():
    """مراقبة مستمرة: كل 5 دقائق للتحقق من تغير السعر"""
    logging.info("🔍 بدء المراقبة المستمرة (فحص كل 5 دقائق)")
    
    while True:
        # كل 5 دقائق، تحقق من السعر وأرسل إذا تغير
        check_and_send()
        time.sleep(300)  # 5 دقائق

def scheduler_worker():
    """جدولة الإرسال كل ساعة"""
    # انتظر 10 ثواني ثم ابدأ
    time.sleep(10)
    
    # بدء المراقبة المستمرة في خيط منفصل
    monitor_thread = threading.Thread(target=continuous_monitor, daemon=True)
    monitor_thread.start()
    
    # جدولة الإرسال كل ساعة
    while True:
        time.sleep(3600)  # انتظر ساعة
        hourly_update()  # أرسل تحديثاً ساعياً (حتى لو لم يتغير السعر)

@app.route('/')
def home():
    return jsonify({
        "status": "Bot is running",
        "time": datetime.now().isoformat(),
        "message": "يرسل التحديثات فور تغير السعر + كل ساعة"
    })

@app.route('/test')
def test():
    """اختبار فوري"""
    check_and_send()
    return jsonify({"message": "تم الاختبار! تحقق من القناة"})

@app.route('/force')
def force():
    """إرسال تحديث فوري (حتى لو لم يتغير السعر)"""
    current_buy, current_sell = get_usd_prices()
    if current_buy and current_sell:
        send_to_channel(current_buy, current_sell, price_changed=False)
        return jsonify({"message": "تم الإرسال القسري"})
    return jsonify({"error": "فشل جلب الأسعار"})

def start_bot():
    thread = threading.Thread(target=scheduler_worker, daemon=True)
    thread.start()
    logging.info("🚀 تم بدء البوت - سيرسل التحديثات فور تغير السعر + كل ساعة")

if __name__ == "__main__":
    start_bot()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
