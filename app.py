import requests
from bs4 import BeautifulSoup
import re
import json
import os
import time
from datetime import datetime

# ========== إعدادات تيليجرام ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID")

if not BOT_TOKEN or not CHANNEL_ID:
    print("❌ خطأ: يرجى إعداد BOT_TOKEN و CHANNEL_ID في متغيرات البيئة")
    exit(1)
# ====================================

URL = "https://sp-today.com/currency/us-dollar"
DATA_FILE = "last_prices.json"
LAST_SEND_FILE = "last_send_time.json"

def load_previous_prices():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            return data.get('buy_price'), data.get('sell_price')
    return None, None

def save_current_prices(buy_price, sell_price):
    with open(DATA_FILE, 'w') as f:
        json.dump({
            'buy_price': buy_price,
            'sell_price': sell_price,
            'last_update': datetime.now().isoformat()
        }, f)

def load_last_send_time():
    if os.path.exists(LAST_SEND_FILE):
        with open(LAST_SEND_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_send_time')
    return None

def save_last_send_time():
    with open(LAST_SEND_FILE, 'w') as f:
        json.dump({'last_send_time': datetime.now().timestamp()}, f)

def get_usd_prices():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()
        
        buy_match = re.search(r'شراء\s*([\d,]+)\s*ل\.س', page_text)
        sell_match = re.search(r'بيع\s*([\d,]+)\s*ل\.س', page_text)
        
        if buy_match and sell_match:
            buy_price = int(buy_match.group(1).replace(',', ''))
            sell_price = int(sell_match.group(1).replace(',', ''))
            return buy_price, sell_price
        return None, None
    except Exception as e:
        print(f"خطأ في الجلب: {e}")
        return None, None

def calculate_change(current, previous):
    if previous is None or previous == 0:
        return None, None
    difference = current - previous
    percentage = (difference / previous) * 100
    return difference, percentage

def get_market_status(buy_diff, sell_diff):
    if buy_diff is None or sell_diff is None:
        return "📊 تحديث أول"
    if buy_diff > 0 and sell_diff > 0:
        return "📈 السوق في صعود"
    elif buy_diff < 0 and sell_diff < 0:
        return "📉 السوق في هبوط"
    elif buy_diff == 0 and sell_diff == 0:
        return "➖ السوق مستقر"
    else:
        return "🔄 تقلبات في السوق"

def send_to_telegram(buy_price, sell_price, buy_diff, buy_perc, sell_diff, sell_perc):
    if not BOT_TOKEN or BOT_TOKEN.startswith("توكن"):
        return False
    
    market_status = get_market_status(buy_diff, sell_diff)
    
    message = f"🏦 شراء: {buy_price:,} ل.س"
    if buy_diff is not None:
        if buy_diff > 0:
            message += f" 📈 +{buy_diff:,} ({buy_perc:+.2f}%)"
        elif buy_diff < 0:
            message += f" 📉 {buy_diff:,} ({buy_perc:+.2f}%)"
        else:
            message += f" ➖"
    message += f"\n"
    message += f"🏪 بيع:  {sell_price:,} ل.س"
    if sell_diff is not None:
        if sell_diff > 0:
            message += f" 📈 +{sell_diff:,} ({sell_perc:+.2f}%)"
        elif sell_diff < 0:
            message += f" 📉 {sell_diff:,} ({sell_perc:+.2f}%)"
        else:
            message += f" ➖"
    message += f"\n\n{market_status}"
    
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
        print(f"خطأ في الإرسال: {e}")
        return False

def should_send(price_changed, last_send_time):
    current_time = datetime.now().timestamp()
    if price_changed:
        return True
    if last_send_time is None or (current_time - last_send_time) >= 3600:
        return True
    return False

def main():
    print("🚀 تشغيل بوت سعر الدولار على Render")
    print("="*50)
    
    last_send_time = load_last_send_time()
    
    while True:
        print(f"\n🔄 فحص الأسعار - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        current_buy, current_sell = get_usd_prices()
        
        if not current_buy or not current_sell:
            print("❌ فشل في جلب الأسعار - سأحاول مرة أخرى بعد 5 دقائق")
            time.sleep(300)
            continue
        
        previous_buy, previous_sell = load_previous_prices()
        
        buy_diff, buy_perc = calculate_change(current_buy, previous_buy)
        sell_diff, sell_perc = calculate_change(current_sell, previous_sell)
        
        print(f"📊 شراء: {current_buy:,} ل.س")
        print(f"📊 بيع:  {current_sell:,} ل.س")
        
        price_changed = False
        if previous_buy and previous_sell:
            if current_buy != previous_buy or current_sell != previous_sell:
                price_changed = True
        
        send_now = should_send(price_changed, last_send_time)
        
        if send_now:
            print("📤 جاري الإرسال إلى تليجرام...")
            if send_to_telegram(current_buy, current_sell, buy_diff, buy_perc, sell_diff, sell_perc):
                save_current_prices(current_buy, current_sell)
                save_last_send_time()
                last_send_time = datetime.now().timestamp()
        
        save_current_prices(current_buy, current_sell)
        
        print(f"\n⏳ انتظار 5 دقائق...")
        time.sleep(300)

if __name__ == "__main__":
    main()
