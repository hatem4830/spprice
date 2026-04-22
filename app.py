import cloudscraper
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

# إنشاء scraper عالمي
scraper = cloudscraper.create_scraper(
    browser={
        'browser': 'chrome',
        'platform': 'windows',
        'desktop': True
    }
)

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
    """جلب الأسعار باستخدام cloudscraper"""
    try:
        # استخدام scraper بدلاً من requests
        response = scraper.get(URL, timeout=20)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()
        
        # البحث المباشر عن الأسعار
        buy_pattern = r'شراء\s*([\d,]+)\s*ل\.س'
        sell_pattern = r'بيع\s*([\d,]+)\s*ل\.س'
        
        buy_match = re.search(buy_pattern, page_text)
        sell_match = re.search(sell_pattern, page_text)
        
        if buy_match and sell_match:
            buy_price = int(buy_match.group(1).replace(',', ''))
            sell_price = int(sell_match.group(1).replace(',', ''))
            logging.info(f"✅ تم جلب الأسعار - شراء: {buy_price}, بيع: {sell_price}")
            return buy_price, sell_price
        
        # محاولة البحث بطريقة بديلة (من الجدول)
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 3 and 'USD' in cells[0].text:
                    buy_price = int(cells[1].text.replace(',', '').replace('ل.س', '').strip())
                    sell_price = int(cells[2].text.replace(',', '').replace('ل.س', '').strip())
                    logging.info(f"✅ تم جلب الأسعار من الجدول - شراء: {buy_price}, بيع: {sell_price}")
                    return buy_price, sell_price
        
        logging.error("❌ لم يتم العثور على الأسعار")
        return None, None
        
    except Exception as e:
        logging.error(f"❌ خطأ في الجلب: {e}")
        return None, None

def send_to_channel(buy_price, sell_price, price_changed=False):
    if not BOT_TOKEN or not CHANNEL_ID:
        logging.error("❌ BOT_TOKEN أو CHANNEL_ID غير مضبوط")
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
        if response.ok:
            logging.info("✅ تم الإرسال إلى القناة")
            return True
        else:
            logging.error(f"❌ خطأ من تيليجرام: {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ خطأ في الإرسال: {e}")
        return False

def check_and_send():
    """التحقق من السعر وإرساله إذا تغير"""
    logging.info("🔄 جلب سعر الدولار...")
    
    current_buy, current_sell = get_usd_prices()
    
    if not current_buy or not current_sell:
        logging.error("❌ فشل في جلب الأسعار")
        return
    
    logging.info(f"📊 السعر الحالي: شراء {current_buy:,} | بيع {current_sell:,}")
    
    last_buy, last_sell = load_last_price()
    
    price_changed = False
    if last_buy and last_sell:
        if current_buy != last_buy or current_sell != last_sell:
            price_changed = True
            logging.info(f"🔄 تغير السعر! سابق: {last_buy:,} → جديد: {current_buy:,}")
    
    if price_changed or not last_buy:
        if send_to_channel(current_buy, current_sell, price_changed):
            save_current_price(current_buy, current_sell)
            logging.info("✅ تم الإرسال وحفظ السعر الجديد")
    else:
        logging.info("✅ السعر لم يتغير")

def hourly_update():
    """إرسال تحديث كل ساعة"""
    logging.info("🕐 تحديث الساعة - جاري جلب الأسعار...")
    
    current_buy, current_sell = get_usd_prices()
    
    if current_buy and current_sell:
        last_buy, last_sell = load_last_price()
        price_changed = (last_buy and last_sell and (current_buy != last_buy or current_sell != last_sell))
        
        if send_to_channel(current_buy, current_sell, price_changed):
            save_current_price(current_buy, current_sell)
            logging.info("✅ تم إرسال التحديث الساعي")
    else:
        logging.error("❌ فشل في جلب الأسعار")

def continuous_monitor():
    """مراقبة كل 5 دقائق"""
    logging.info("🔍 بدء المراقبة المستمرة (فحص كل 5 دقائق)")
    while True:
        check_and_send()
        time.sleep(300)  # 5 دقائق

def scheduler_worker():
    """جدولة الإرسال كل ساعة"""
    time.sleep(10)
    
    # بدء المراقبة المستمرة
    monitor_thread = threading.Thread(target=continuous_monitor, daemon=True)
    monitor_thread.start()
    
    # جدولة الإرسال كل ساعة
    while True:
        time.sleep(3600)
        hourly_update()

@app.route('/')
def home():
    return jsonify({
        "status": "Bot is running",
        "time": datetime.now().isoformat(),
        "message": "يرسل التحديثات فور تغير السعر + كل ساعة"
    })

@app.route('/test')
def test():
    check_and_send()
    return jsonify({"message": "تم الاختبار! تحقق من القناة"})

def start_bot():
    thread = threading.Thread(target=scheduler_worker, daemon=True)
    thread.start()
    logging.info("🚀 تم بدء البوت - سيتم تجاوز حماية الموقع باستخدام cloudscraper")

if __name__ == "__main__":
    start_bot()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
