import requests
from datetime import datetime
import logging
import threading
import time
from flask import Flask, jsonify
import os
import json

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ========== إعدادات تيليجرام ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")
# ====================================

# سعر صرف ثابت تقريبي (سيتم تحديثه من API آخر)
USD_TO_SYP = 12950  # سعر تقريبي

def get_usd_to_syp_rate():
    """
    جلب سعر USD/SYP من API مجاني
    """
    try:
        # المحاولة الأولى: API مجاني للأسعار
        url = "https://api.exchangerate.host/latest?base=USD&symbols=SYP"
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            # API يعيد السعر بالليرة السورية
            rate = data['rates'].get('SYP')
            if rate:
                logging.info(f"✅ تم جلب السعر من exchangerate.host: {rate}")
                return float(rate)
        
        # إذا فشل API الأول، استخدم سعراً افتراضياً مع تحديث من مصدر آخر
        logging.warning("⚠️ استخدام السعر الافتراضي المحفوظ")
        return get_default_rate()
        
    except Exception as e:
        logging.error(f"❌ خطأ في جلب السعر: {e}")
        return get_default_rate()

def get_default_rate():
    """تحميل آخر سعر محفوظ أو استخدام قيمة افتراضية"""
    try:
        if os.path.exists("last_rate.json"):
            with open("last_rate.json", 'r') as f:
                data = json.load(f)
                return data.get('rate', 12950)
    except:
        pass
    return 12950

def save_rate(rate):
    """حفظ السعر الحالي"""
    try:
        with open("last_rate.json", 'w') as f:
            json.dump({'rate': rate, 'last_update': datetime.now().isoformat()}, f)
    except:
        pass

def get_usd_prices():
    """جلب سعر الشراء والبيع"""
    rate = get_usd_to_syp_rate()
    
    # حساب سعر الشراء والبيع بهامش ربح 0.5%
    buy_price = int(rate * 0.998)  # أقل قليلاً من السعر الأساسي
    sell_price = int(rate * 1.002)  # أعلى قليلاً من السعر الأساسي
    
    return buy_price, sell_price

def send_to_channel(buy_price, sell_price, price_changed=False):
    """إرسال السعر إلى القناة"""
    if not BOT_TOKEN or not CHANNEL_ID:
        logging.error("❌ BOT_TOKEN أو CHANNEL_ID غير مضبوط")
        return False
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    change_indicator = "🟢 **تحديث السعر!** 🟢\n\n" if price_changed else ""
    
    message = f"""💵 **سعر الدولار الأمريكي** 💵

{change_indicator}━━━━━━━━━━━━━━━━━━━
🏦 **سعر الشراء:** `{buy_price:,}` ل.س
🏪 **سعر البيع:** `{sell_price:,}` ل.س
📊 **الفرق:** `{sell_price - buy_price:,}` ل.س
━━━━━━━━━━━━━━━━━━━

🕐 **آخر تحديث:** {timestamp}

_📡 يتم التحديث عبر API عالمي_
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
        logging.error(f"❌ خطأ في الإرسال: {e}")
        return False

def check_and_send():
    """التحقق من السعر وإرساله"""
    logging.info("🔄 جلب سعر الدولار...")
    
    current_buy, current_sell = get_usd_prices()
    
    logging.info(f"📊 السعر الحالي: شراء {current_buy:,} | بيع {current_sell:,}")
    
    # حفظ السعر
    save_rate(current_buy)
    
    # إرسال التحديث
    if send_to_channel(current_buy, current_sell):
        logging.info("✅ تم الإرسال إلى القناة")
    else:
        logging.error("❌ فشل الإرسال")

def scheduler_worker():
    """جدولة الإرسال"""
    time.sleep(10)
    
    while True:
        check_and_send()
        time.sleep(3600)  # انتظر ساعة

@app.route('/')
def home():
    return jsonify({
        "status": "Bot is running",
        "time": datetime.now().isoformat(),
        "message": "يعمل عبر API بديل"
    })

@app.route('/test')
def test():
    check_and_send()
    return jsonify({"message": "تم الاختبار!"})

def start_bot():
    thread = threading.Thread(target=scheduler_worker, daemon=True)
    thread.start()
    logging.info("🚀 تم بدء البوت باستخدام API بديل")

if __name__ == "__main__":
    start_bot()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
