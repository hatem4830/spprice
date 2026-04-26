import requests
from bs4 import BeautifulSoup
import re
import json
import os
from datetime import datetime
import time

# ========== إعدادات تيليجرام ==========
BOT_TOKEN = "8592121887:AAGnD0KW9izbAofHXp0DaTXEEpyEmgOyDok"
CHANNEL_ID = "@sppricenow"
# ====================================

URL = "https://sp-today.com/currency/us-dollar"
DATA_FILE = "last_prices.json"
LAST_SEND_FILE = "last_send_time.json"

# ========== إعدادات أوقات العمل ==========
WORKING_DAYS = [5, 6, 0, 1, 2, 3, 4]  # السبت=5, الأحد=6, الإثنين=0, الثلاثاء=1, الأربعاء=2, الخميس=3, الجمعة=4 معطلة
# ملاحظة: datetime Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
START_HOUR = 10  # 10 صباحاً
END_HOUR = 19    # 7 مساءً (19:00)
# =========================================

def is_working_time():
    """التحقق ما إذا كان الوقت الحالي ضمن ساعات العمل"""
    now = datetime.now()
    current_day = now.weekday()  # الإثنين=0 ... الأحد=6
    current_hour = now.hour
    
    # التحقق من أن اليوم ليس الجمعة (4)
    if current_day == 4:  # الجمعة
        return False
    
    # التحقق من أن اليوم ضمن أيام العمل
    if current_day not in WORKING_DAYS:
        return False
    
    # التحقق من أن الساعة ضمن 10 صباحاً - 7 مساءً
    if START_HOUR <= current_hour < END_HOUR:
        return True
    
    return False

def get_next_working_time():
    """حساب وقت البدء التالي (لحالة الانتظار خارج أوقات العمل)"""
    now = datetime.now()
    current_day = now.weekday()
    current_hour = now.hour
    
    # إذا كان اليوم جمعة (4)
    if current_day == 4:
        # ننتظر حتى السبت 10 صباحاً
        days_to_add = 2  # الجمعة -> السبت
        next_start = datetime(now.year, now.month, now.day, START_HOUR, 0, 0)
        next_start = next_start.replace(day=now.day + days_to_add)
        return next_start
    
    # إذا كان الوقت قبل 10 صباحاً
    if current_hour < START_HOUR:
        next_start = datetime(now.year, now.month, now.day, START_HOUR, 0, 0)
        return next_start
    
    # إذا كان الوقت بعد 7 مساءً
    if current_hour >= END_HOUR:
        # ننتقل إلى اليوم التالي الساعة 10 صباحاً
        next_start = datetime(now.year, now.month, now.day + 1, START_HOUR, 0, 0)
        # التحقق إذا كان اليوم التالي جمعة، ننتقل إلى السبت
        if next_start.weekday() == 4:  # جمعة
            next_start = next_start.replace(day=next_start.day + 1)
        return next_start
    
    # إذا كان اليوم غير مسموح
    next_start = datetime(now.year, now.month, now.day + 1, START_HOUR, 0, 0)
    return next_start

def load_previous_prices():
    """تحميل الأسعار السابقة"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            return data.get('buy_price'), data.get('sell_price')
    return None, None

def save_current_prices(buy_price, sell_price):
    """حفظ الأسعار الحالية"""
    with open(DATA_FILE, 'w') as f:
        json.dump({
            'buy_price': buy_price,
            'sell_price': sell_price,
            'last_update': datetime.now().isoformat()
        }, f)

def load_last_send_time():
    """تحميل وقت آخر إرسال"""
    if os.path.exists(LAST_SEND_FILE):
        with open(LAST_SEND_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_send_time')
    return None

def save_last_send_time():
    """حفظ وقت الإرسال الحالي"""
    with open(LAST_SEND_FILE, 'w') as f:
        json.dump({'last_send_time': datetime.now().timestamp()}, f)

def get_usd_prices():
    """جلب سعر الشراء والبيع"""
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
    """حساب نسبة التغير"""
    if previous is None or previous == 0:
        return None, None
    difference = current - previous
    percentage = (difference / previous) * 100
    return difference, percentage

def get_market_status(buy_diff, sell_diff):
    """تحديد حالة السوق"""
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
    """إرسال إلى تليجرام"""
    if BOT_TOKEN.startswith("توكن"):
        print("⚠️ يرجى إعداد توكن البوت أولاً")
        return False
    
    market_status = get_market_status(buy_diff, sell_perc)
    
    # بناء الرسالة
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
    
    # إرسال إلى تليجرام
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        if response.ok:
            print("✅ تم الإرسال إلى تليجرام")
            return True
        else:
            print(f"❌ خطأ: {response.text}")
            return False
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return False

def should_send(price_changed, last_send_time):
    """تحديد ما إذا كان يجب الإرسال"""
    current_time = datetime.now().timestamp()
    
    if price_changed:
        return True
    
    if last_send_time is None or (current_time - last_send_time) >= 3600:
        return True
    
    return False

def main_loop():
    """الحلقة الرئيسية - فحص كل 5 دقائق خلال أوقات العمل"""
    print("🚀 تشغيل بوت سعر الدولار")
    print("⏱️  فحص السعر: كل 5 دقائق")
    print("📤 نشر التحديث: عند تغير السعر أو كل ساعة")
    print("🕒 أوقات العمل: السبت - الخميس (10 صباحاً - 7 مساءً)")
    print("📅 يوم العطلة: الجمعة")
    print("="*60)
    
    last_send_time = load_last_send_time()
    
    while True:
        # التحقق من وقت العمل
        if not is_working_time():
            next_time = get_next_working_time()
            wait_seconds = (next_time - datetime.now()).total_seconds()
            wait_hours = wait_seconds // 3600
            wait_minutes = (wait_seconds % 3600) // 60
            
            print(f"\n⏸️  خارج أوقات العمل (العمل: السبت-الخميس 10ص-7م)")
            print(f"⏳ انتظار حتى {next_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"📅 الوقت المتبقي: {int(wait_hours)} ساعة و {int(wait_minutes)} دقيقة")
            
            time.sleep(wait_seconds)
            continue
        
        print(f"\n🔄 فحص الأسعار - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        current_buy, current_sell = get_usd_prices()
        
        if not current_buy or not current_sell:
            print("❌ فشل في جلب الأسعار - سأحاول مرة أخرى بعد 5 دقائق")
            time.sleep(300)
            continue
        
        previous_buy, previous_sell = load_previous_prices()
        
        buy_diff, buy_perc = calculate_change(current_buy, previous_buy)
        sell_diff, sell_perc = calculate_change(current_sell, previous_sell)
        
        # عرض في الشاشة
        print(f"📊 شراء: {current_buy:,} ل.س", end="")
        if previous_buy:
            if buy_diff > 0:
                print(f" (صعود +{buy_diff:,} | {buy_perc:+.2f}%)")
            elif buy_diff < 0:
                print(f" (هبوط {buy_diff:,} | {buy_perc:+.2f}%)")
            else:
                print(f" (ثابت)")
        else:
            print()
        
        print(f"📊 بيع:  {current_sell:,} ل.س", end="")
        if previous_sell:
            if sell_diff > 0:
                print(f" (صعود +{sell_diff:,} | {sell_perc:+.2f}%)")
            elif sell_diff < 0:
                print(f" (هبوط {sell_diff:,} | {sell_perc:+.2f}%)")
            else:
                print(f" (ثابت)")
        else:
            print()
        
        # التحقق من تغير السعر
        price_changed = False
        if previous_buy and previous_sell:
            if current_buy != previous_buy or current_sell != previous_sell:
                price_changed = True
        
        send_now = should_send(price_changed, last_send_time)
        
        if send_now:
            print(f"📤 جاري الإرسال إلى تليجرام...")
            if send_to_telegram(current_buy, current_sell, buy_diff, buy_perc, sell_diff, sell_perc):
                save_current_prices(current_buy, current_sell)
                save_last_send_time()
                last_send_time = datetime.now().timestamp()
        else:
            print(f"⏸️  لن يتم الإرسال - لا تغير في السعر ولم تمر ساعة")
        
        save_current_prices(current_buy, current_sell)
        
        # التحقق مرة أخرى قبل النوم (قد يصادف نهاية وقت العمل)
        if not is_working_time():
            continue
            
        print(f"\n⏳ انتظار 5 دقائق حتى الفحص التالي...")
        time.sleep(300)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n🛑 تم إيقاف البوت بواسطتك")
    except Exception as e:
        print(f"\n❌ خطأ غير متوقع: {e}")
