import json
import os
import time
import requests
import re
import threading
from datetime import datetime, timedelta

# ================= إعدادات البوت (قم بتعديلها) =================
TOKEN = os.getenv("STUDY_BOT_TOKEN", "8285457029:AAGzgyfW8ASNBoXuKp5f1RFzTTWEkPIiANI")
DEV_ID = 8554620638  # ⚠️ ضع الآيدي الخاص بك هنا لتتحكم بالبوت
FORCE_CHANNEL = ""  # ⚠️ ضع معرف قناتك للاشتراك الإجباري (أو اتركه فارغاً "")

URL = f"https://api.telegram.org/bot{TOKEN}"
avetaar_session = requests.Session()  # بصمة مخفية وتسريع للاتصال

# ================= قواعد البيانات =================
AVETAAR_DB_FILE = "bot_data.json"

def load_avetaar_db():
    if os.path.exists(AVETAAR_DB_FILE):
        with open(AVETAAR_DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": [], "groups": [], "banned":[]}

def save_avetaar_db(data):
    with open(AVETAAR_DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

db = load_avetaar_db()

# الجلسات النشطة
avetaar_active_camps = {}
avetaar_lock = threading.Lock()

# ================= دوال الاتصال الأساسية =================
def req(method, json_data=None, params=None):
    try:
        if json_data:
            r = avetaar_session.post(f"{URL}/{method}", json=json_data, timeout=20)
        elif params:
            r = avetaar_session.post(f"{URL}/{method}", data=params, timeout=20)
        else:
            r = avetaar_session.post(f"{URL}/{method}", timeout=20)
        return r.json() if r.text else {"ok": False}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def send_message(chat_id, text, parse_mode="HTML", reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True, "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    return req("sendMessage", json_data=payload)

def edit_message(chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": parse_mode}
    if reply_markup: payload["reply_markup"] = reply_markup
    return req("editMessageText", json_data=payload)

def get_chat_member(chat_id, user_id):
    res = req("getChatMember", params={"chat_id": chat_id, "user_id": user_id})
    if res.get("ok"): return res["result"]["status"]
    return None

def is_admin_or_creator(chat_id, user_id):
    if user_id == DEV_ID: return True
    status = get_chat_member(chat_id, user_id)
    return status in ["administrator", "creator"]

def check_force_join(user_id):
    if not FORCE_CHANNEL or user_id == DEV_ID: return True
    status = get_chat_member(FORCE_CHANNEL, user_id)
    return status in["member", "administrator", "creator"]

# ================= النصوص والتصميم =================
WELCOME_TEXT = (
    "<b>أهلاً بك في بوت المعسكرات 🏕 (Study Bot)</b>\n\n"
    "بوت متخصص لعمل معسكرات مذاكرة جماعية أو فردية، لترتيب وقتك وإنجاز مهامك.\n\n"
    "<b>كيف أبدأ معسكر؟ ⛔️</b>\n"
    "👈🏻 أرسل الأمر <code>/start</code> متبوعاً بالوقت:\n"
    "   • <code>/start 2h30m</code> ➡️ معسكر لساعتين ونصف\n"
    "   • <code>/start 45m</code>   ➡️ معسكر لـ 45 دقيقة\n"
    "   • <code>/s_10m</code>       ➡️ اختصار سريع لـ 10 دقائق\n\n"
    "<b>الاختصارات:</b> <code>h</code> (ساعات) • <code>m</code> (دقائق) • <code>s</code> (ثواني)\n\n"
    "<i>متنساش تصلي على النبي وتستغفر ربنا قبل متبدأ معسكرك 🤍.</i>"
)

DUA = "اللهم إنّي أسألك فهم النبيين، وحفظ المرسلين، وإلهام الملائكة المقربين، اللهم اجعل ألسنتنا عامرة بذكرك وقلوبنا بطاعتك."

def parse_duration(duration_str):
    duration_str = duration_str.replace(" ", "").lower().replace("س", "h").replace("د", "m").replace("ث", "s")
    match = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$").fullmatch(duration_str)
    if not match: return None
    h, m, s =[int(g) if g else 0 for g in match.groups()]
    total = h*3600 + m*60 + s
    return total if total > 0 else None

def format_time(seconds):
    return f"{seconds//3600:02d}:{(seconds%3600)//60:02d}:{seconds%60:02d}"

def format_datetime(dt):
    return dt.strftime("%I:%M %p").lstrip("0")

# ================= محرك المعسكرات (Avetaar Engine) =================
def build_camp_keyboard(session_key):
    return {
        "inline_keyboard":[[{"text": "انضمام 👥", "callback_data": f"join_{session_key}"}],[{"text": "⏸ إيقاف مؤقت", "callback_data": f"pause_{session_key}"}, 
             {"text": "▶️ استئناف", "callback_data": f"resume_{session_key}"}],[{"text": "🛑 إنهاء المعسكر", "callback_data": f"stop_{session_key}"}]
        ]
    }

def end_camp_avetaar(chat_id, session_key, session_data):
    duration_str = session_data["duration_str"]
    participants = session_data.get("participants", {})
    participants_list =[f"{i+1}- {p}" for i, p in enumerate(participants.values())]
    part_text = "\n".join(participants_list) if participants_list else "لا يوجد مشاركين 💔"
    
    end_message = (
        f"✅ - <b>تم انهاء المعسكر بنجاح</b> .\n"
        f"👥 <b>المشاركين في هذا المعسكر</b> :\n\n"
        f"{part_text}\n\n"
        f"⏱ <b>كان زمن هذا المعسكر ( {duration_str} )</b> \n"
        f"🤍 <b>ان شاء الله تكونو انجزتو كويس في المعسكر و خلصتو جزء من الي عليكم .</b>"
    )
    send_message(chat_id, end_message)

def update_timer_avetaar(chat_id, session_key):
    UPDATE_INTERVAL = 10 
    while session_key in avetaar_active_camps and avetaar_active_camps[session_key]["status"] == "active":
        try:
            session = avetaar_active_camps[session_key]
            now = datetime.now()
            end_time = datetime.fromisoformat(session["end_time"])
            
            if now >= end_time:
                with avetaar_lock:
                    if session_key in avetaar_active_camps:
                        end_camp_avetaar(chat_id, session_key, session)
                        del avetaar_active_camps[session_key]
                break
            
            remaining = int((end_time - now).total_seconds())
            start_time = datetime.fromisoformat(session["start_time"])
            p_count = len(session.get("participants", {}))
            
            msg_text = (
                f"✨ <b>دعـاء المذاكـرة (قبل البدء):</b>\n"
                f"» {session['dua']}\n\n"
                f"⏳ <b>الوقت المتبقي:</b> <code>{format_time(remaining)}</code>\n"
                f"⏱️ <b>المدة المحددة:</b> <code>{session['duration_str']}</code>\n"
                f"🕒 <b>وقت البدء:</b> <code>{format_datetime(start_time)}</code>\n"
                f"🎯 <b>وقت الانتهاء:</b> <code>{format_datetime(end_time)}</code>\n"
                f"👥 <b>عدد المشاركين حالياً:</b> <code>{p_count}</code>\n"
            )
            
            keyboard = build_camp_keyboard(session_key)
            
            if "message_id" not in session:
                res = send_message(chat_id, msg_text, reply_markup=json.dumps(keyboard))
                if res.get("ok"): session["message_id"] = res["result"]["message_id"]
            else:
                edit_message(chat_id, session["message_id"], msg_text, reply_markup=json.dumps(keyboard))
            
            time.sleep(UPDATE_INTERVAL)
        except Exception as e:
            time.sleep(5)

# ================= معالجة الرسائل =================
def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    chat_type = message["chat"]["type"]
    first_name = message["from"].get("first_name", "")
    username = message["from"].get("username", "")

    if user_id in db["banned"]: return

    # تسجيل الأعضاء والجروبات
    if chat_type == "private":
        if user_id not in db["users"]:
            db["users"].append(user_id)
            save_avetaar_db(db)
            u_link = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>{first_name}</a>"
            send_message(DEV_ID, f"🔔 <b>دخول جديد!</b>\n👤 العضو: {u_link}\n🆔 الآيدي: <code>{user_id}</code>")
    else:
        if chat_id not in db["groups"]:
            db["groups"].append(chat_id)
            save_avetaar_db(db)

    # الاشتراك الإجباري الأنيق المعتمد على الأزرار
    if not check_force_join(user_id):
        sub_kb = {"inline_keyboard": [[{"text": "📢 اضغط هنا للاشتراك", "url": f"https://t.me/{FORCE_CHANNEL.replace('@', '')}"}],[{"text": "✅ تحقق من الاشتراك", "callback_data": "check_sub"}]
        ]}
        send_message(chat_id, f"🚫 <b>عذراً عزيزي، يجب عليك الاشتراك في قناة البوت أولاً لتتمكن من استخدامه.</b>\n\nاشترك ثم اضغط تحقق:", reply_markup=json.dumps(sub_kb))
        return

    # أوامر المطور
    if user_id == DEV_ID and chat_type == "private":
        if text == "/admin" or text == "لوحة المطور":
            admin_kb = {"inline_keyboard": [[{"text": "📊 الإحصائيات", "callback_data": "admin_stats"}],[{"text": "📢 أوامر الإذاعة والحظر", "callback_data": "admin_help"}]
            ]}
            send_message(chat_id, "👨🏻‍💻 <b>أهلاً بك يا (Avetaar) في لوحة التحكم:</b>", reply_markup=json.dumps(admin_kb))
            return
        if text.startswith("/broadcast "):
            msg = text.replace("/broadcast ", "")
            send_message(chat_id, "⏳ <b>جاري الإذاعة...</b>")
            count = sum(1 for uid in db["users"] + db["groups"] if send_message(uid, f"📢 <b>رسالة إدارية:</b>\n\n{msg}").get("ok"))
            send_message(chat_id, f"✅ <b>تمت الإذاعة لـ {count} دردشة.</b>")
            return
        if text.startswith("/ban "):
            bid = int(text.split()[1])
            if bid not in db["banned"]: db["banned"].append(bid); save_avetaar_db(db)
            send_message(chat_id, f"✅ <b>تم حظر {bid}</b>")
            return
        if text.startswith("/unban "):
            bid = int(text.split()[1])
            if bid in db["banned"]: db["banned"].remove(bid); save_avetaar_db(db)
            send_message(chat_id, f"✅ <b>تم إلغاء حظر {bid}</b>")
            return

    # الأوامر الرئيسية
    if text == "/start":
        if chat_type == "private":
            main_kb = {"inline_keyboard": [[{"text": "🏕 كيفية إنشاء معسكر؟", "callback_data": "help_camp"}],[{"text": "👨‍💻 مطور البوت", "url": "tg://user?id=" + str(DEV_ID)}]
            ]}
            send_message(chat_id, WELCOME_TEXT, reply_markup=json.dumps(main_kb))
        else:
            send_message(chat_id, WELCOME_TEXT)
        return
        
    if text.startswith("/start ") or text.startswith("/s_"):
        duration_str = text.split()[1] if text.startswith("/start ") and len(text.split()) > 1 else text[3:]
        duration = parse_duration(duration_str)
        
        if not duration:
            send_message(chat_id, "❌ <b>صيغة الوقت غير صحيحة!</b>\nاستخدم مثلاً: <code>/start 1h30m</code> أو <code>/s_10m</code>")
            return
        
        session_key = str(chat_id)
        if session_key in avetaar_active_camps:
            send_message(chat_id, "⏳ <b>هناك معسكر نشط حالياً! استخدم الأزرار للتحكم به.</b>")
            return
            
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=duration)
        
        with avetaar_lock:
            avetaar_active_camps[session_key] = {
                "status": "active",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "dua": DUA,
                "duration_str": duration_str,
                "participants": {},
                "starter_id": user_id 
            }
        
        threading.Thread(target=update_timer_avetaar, args=(chat_id, session_key), daemon=True).start()
        return

# ================= معالجة الأزرار (Callbacks) =================
def handle_callback_avetaar(call):
    chat_id = call["message"]["chat"]["id"]
    msg_id = call["message"]["message_id"]
    user_id = call["from"]["id"]
    data = call["data"]
    username = call["from"].get("username")
    first_name = call["from"].get("first_name", "بدون اسم")

    def answer(text, alert=False):
        req("answerCallbackQuery", json_data={"callback_query_id": call["id"], "text": text, "show_alert": alert})

    # زر التحقق من الاشتراك
    if data == "check_sub":
        if check_force_join(user_id):
            answer("✅ شكراً لك! تم تفعيل البوت، أرسل /start الآن.", True)
            req("deleteMessage", json_data={"chat_id": chat_id, "message_id": msg_id})
        else:
            answer("❌ لم تقم بالاشتراك بعد!", True)
        return

    # أزرار المساعدة والمطور
    if data == "help_camp":
        answer("أرسل /start متبوعاً بالوقت، مثلاً /start 1h لبدء معسكر لمدة ساعة.", True)
        return
    if data == "admin_stats":
        if user_id == DEV_ID:
            answer(f"المستخدمين: {len(db['users'])}\nالجروبات: {len(db['groups'])}\nالمحظورين: {len(db['banned'])}", True)
        return
    if data == "admin_help":
        if user_id == DEV_ID:
            answer("للإذاعة: /broadcast + رسالتك\nللحظر: /ban + الايدي\nلفك الحظر: /unban + الايدي", True)
        return

    # الاشتراك الإجباري قبل الانضمام للمعسكر
    if not check_force_join(user_id):
        answer("🚫 يجب عليك الاشتراك في قناة البوت أولاً!", True)
        return

    # أزرار المعسكر (انضمام، إيقاف، استئناف، إنهاء)
    if "_" in data:
        action, session_key = data.split("_", 1)
        
        with avetaar_lock:
            if session_key not in avetaar_active_camps:
                answer("❌ هذا المعسكر انتهى أو غير موجود.")
                return
                
            session = avetaar_active_camps[session_key]
            starter = session.get("starter_id")
            
            # زر الانضمام (متاح للجميع)
            if action == "join":
                part_name = f"المستخدم ( @{username} )" if username else f"المستخدم ( {first_name} )"
                if str(user_id) in session["participants"]:
                    answer("⚠️ أنت منضم سابقاً بالفعل!")
                else:
                    session["participants"][str(user_id)] = part_name
                    answer("✅ تم انضمامك للمعسكر بنجاح!")
                return

            # أزرار التحكم (متاحة لصاحب المعسكر والمشرفين والمطور فقط)
            if user_id != starter and not is_admin_or_creator(chat_id, user_id):
                answer("🚫 عذراً، فقط من أنشأ المعسكر أو المشرفين يمكنهم التحكم به!", True)
                return

            if action == "pause":
                if session["status"] == "active":
                    session["status"] = "paused"
                    rem = int((datetime.fromisoformat(session["end_time"]) - datetime.now()).total_seconds())
                    session["paused_remaining"] = max(0, rem)
                    edit_message(chat_id, msg_id, "⏸ <b>تم إيقاف المعسكر مؤقتاً...</b>\n<i>اضغط استئناف لإكمال المعسكر.</i>", reply_markup=json.dumps(build_camp_keyboard(session_key)))
                    answer("✅ تم الإيقاف المؤقت.")
                else:
                    answer("⚠️ المعسكر متوقف بالفعل.")
                    
            elif action == "resume":
                if session["status"] == "paused":
                    session["status"] = "active"
                    rem = session["paused_remaining"]
                    st = datetime.now()
                    session["start_time"] = st.isoformat()
                    session["end_time"] = (st + timedelta(seconds=rem)).isoformat()
                    answer("▶️ تم الاستئناف بنجاح!")
                    threading.Thread(target=update_timer_avetaar, args=(chat_id, session_key), daemon=True).start()
                else:
                    answer("⚠️ المعسكر يعمل بالفعل.")
                    
            elif action == "stop":
                end_camp_avetaar(chat_id, session_key, session)
                del avetaar_active_camps[session_key]
                req("deleteMessage", json_data={"chat_id": chat_id, "message_id": msg_id})
                answer("🛑 تم إنهاء المعسكر.")

# ================= معالجة الجروبات =================
def handle_group_join(update):
    chat_id = update["chat"]["id"]
    new_status = update["new_chat_member"]["status"]
    
    if new_status in ["member", "administrator"]:
        if chat_id not in db["groups"]:
            db["groups"].append(chat_id)
            save_avetaar_db(db)
            send_message(DEV_ID, f"📢 <b>تمت إضافة البوت لمجموعة جديدة!</b>\n🆔 الآيدي: <code>{chat_id}</code>")
        
        msg = (
            "<b>شكراً لإضافتي في المجموعة 🫂🖤</b>\n"
            "يرجى رفعي كـ <b>مشرف</b> مع إعطائي الصلاحيات التالية:\n"
            "📌 حذف وتعديل وتثبيت الرسائل.\n\n"
            "لبدء معسكر اكتب: <code>/start 1h</code>"
        )
        send_message(chat_id, msg)

# ================= التشغيل الأساسي =================
def run_avetaar_bot():
    offset = 0
    if not TOKEN or TOKEN == "توكن_البوت_هنا":
        print("ERROR: الرجاء وضع التوكن الخاص بك في الكود!")
        return

    print("✅ Study Bot (Avetaar Edition) is Running Successfully...")
    send_message(DEV_ID, "✅ <b>تم تشغيل بوت المعسكرات بنجاح (𓂀 الأڤـيـتـار 𓂀)!</b>")

    while True:
        try:
            resp = avetaar_session.get(f"{URL}/getUpdates", params={"timeout": 30, "offset": offset, "allowed_updates":["message", "chat_member", "my_chat_member", "callback_query"]}, timeout=40)
            if not resp.ok:
                time.sleep(1)
                continue

            for update in resp.json().get("result", []):
                offset = update["update_id"] + 1
                if "message" in update and "text" in update["message"]:
                    handle_message(update["message"])
                elif "my_chat_member" in update:
                    handle_group_join(update["my_chat_member"])
                elif "callback_query" in update:
                    handle_callback_avetaar(update["callback_query"])
        except Exception as e:
            time.sleep(2)

if __name__ == "__main__":
    run_avetaar_bot()
