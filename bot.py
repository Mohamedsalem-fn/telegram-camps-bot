import json
import os
import time
import telebot
import re
import threading
from datetime import datetime, timedelta
from telebot import types

TOKEN = "8662823218:AAFvqvbhGAMppfR_IrIaojk3EocViL3nfnM"
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

# Storage and Locks
active_sessions = {}
session_locks = threading.Lock()

# Constants and Templates
WELCOME_TEXT = (
    "Welcome To Study bot\n\n"
    "👈🏻  استخدم الأمر مع الوقت المطلوب لتحديد مدة المذاكرة\n"
    "   • <code>/start 2h30m</code>  ➡️ لمدة ساعتان ونصف\n"
    "   • <code>/start 45m</code>    ➡️ لمدة 45 دقيقة\n"
    "   • <code>/s_10m</code>        ➡️ اختصار سريع لـ 10 دقائق\n\n"
    "<b>📌 ملاحظة : يمكنك تحديد المدة بكتابة <code>/start</code> متبوعة بالمدة والاختصار المناسب.</b>\n"
    "   مثال: <code>/start 5h</code> ➡️ لمدة 5 ساعات\n"
    "————————————————————\n"
    "<b>🔹 الاختصارات يغالي عشان تعرف تستخدم البوت 🔹</b>\n"
    "   <code>h</code> = ساعات • <code>m</code> = دقائق • <code>s</code> = ثواني\n"
    "————————————————————\n"
    "<b>متنساش تصلي على النبي و تستغفر ربنا قبل متبدأ معسكر ⛔️.</b>"
)

DUA_LIST = [
    "اللهم إنّي أسألك فهم النبيين، وحفظ المرسلين، وإلهام الملائكة المقربين،\n   اللهم اجعل ألسنتنا عامرة بذكرك وقلوبنا بطاعتك.",
    "اللهم إني أستودعك ما علمتني فاحفظه لي في ذهني وعقلي وقلبي،\n   اللهم ردده علي عند حاجتي إليه، ولا تنسيني إياه يا حي يا قيوم.",
    "رب اشرح لي صدري ويسر لي أمري واحلل عقدة من لساني يفقهوا قولي،\n   اللهم لا سهل إلا ما جعلته سهلاً وأنت تجعل الحزن إذا شئت سهلاً."
]

# Utility Functions
def parse_duration(duration_str):
    duration_str = duration_str.replace(" ", "").lower()
    duration_str = duration_str.replace("س", "h").replace("د", "m").replace("ث", "s")
    pattern = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")
    match = pattern.fullmatch(duration_str)
    if not match:
        return None
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    total = hours*3600 + minutes*60 + seconds
    return total if total > 0 else None

def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def format_datetime(dt):
    return dt.strftime("%I:%M %p").lstrip("0")

def get_timer_keyboard(session_key):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("انضمام 👥", callback_data=f"join_{session_key}"))
    return keyboard

def get_timer_text(session, remaining):
    start_time = datetime.fromisoformat(session["start_time"])
    end_time = datetime.fromisoformat(session["end_time"])
    participants_count = len(session.get("participants", {}))
    
    return (
        f"*✨ دعـاء المذاكـرة (قبل البدء):*\n"
        f"» {session['dua']}\n\n"
        f"*⏳ الوقت المتبقي:* `{format_time(remaining)}`\n"
        f"*⏱️ المدة المحددة:* `{session['duration_str']}`\n"
        f"*🕒 وقت البدء:* `{format_datetime(start_time)}`\n"
        f"*🎯 وقت الانتهاء:* `{format_datetime(end_time)}`\n"
        f"*👥 عدد المشاركين حالياً:* `{participants_count}`\n"
        f"————————————————————\n"
        f"• لإيقاف المؤقت: /stop | لاستئنافه: /ready"
    )

# Timer Thread
def update_timer(chat_id, session_key):
    while session_key in active_sessions and active_sessions[session_key]["status"] == "active":
        try:
            session = active_sessions[session_key]
            now = datetime.now()
            end_time = datetime.fromisoformat(session["end_time"])
            
            if now >= end_time:
                with session_locks:
                    if session_key in active_sessions:
                        participants = session.get("participants", {})
                        participants_list = [f"{i+1} {p}" for i, p in enumerate(participants.values())]
                        participants_text = "\n".join(participants_list) if participants_list else "لا يوجد مشاركين"
                        
                        end_message = (
                            f"*تم انهاء المعسكر بنجاح* ✅\n\n"
                            f"*المشاركين في هذا المعسكر* 👥\n\n"
                            f"{participants_text}\n\n"
                            f"*كان زمن هذا المعسكر* ( `{session['duration_str']}` ) *⏱️*\n"
                            f"*ان شاء الله تكونو انجزتو كويس في المعسكر و خلصتو جزء من الي عليكم* 🖤"
                        )
                        bot.send_message(chat_id, end_message, parse_mode="Markdown")
                        del active_sessions[session_key]
                break
            
            remaining = int((end_time - now).total_seconds())
            msg_text = get_timer_text(session, remaining)
            keyboard = get_timer_keyboard(session_key)
            
            if "message_id" not in session:
                msg = bot.send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=keyboard)
                session["message_id"] = msg.message_id
            else:
                try:
                    bot.edit_message_text(msg_text, chat_id, session["message_id"], parse_mode="Markdown", reply_markup=keyboard)
                except telebot.apihelper.ApiTelegramException as e:
                    if "message is not modified" not in e.description:
                        print(f"Edit error: {e}")
            
            time.sleep(1)
        except Exception as e:
            print(f"Timer update error: {e}")
            break

# Handlers
@bot.message_handler(commands=['start'])
def start_cmd(message):
    parts = message.text.split()
    if len(parts) == 1:
        bot.send_message(message.chat.id, WELCOME_TEXT, parse_mode="HTML")
        return

    duration_str = parts[1]
    duration = parse_duration(duration_str)
    if not duration:
        bot.send_message(message.chat.id, "❌ صيغة الوقت غير صحيحة! استخدم مثلاً: /start 1h30m")
        return
    
    chat_type = message.chat.type
    session_key = f"{message.chat.id}:0" if chat_type != 'private' else f"{message.chat.id}:{message.from_user.id}"
    
    if session_key in active_sessions:
        bot.send_message(message.chat.id, "⏳ هناك جلسة نشطة حالياً. قم بإيقافها أولاً بـ /stop")
        return
        
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=duration)
    
    with session_locks:
        active_sessions[session_key] = {
            "status": "active",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "dua": DUA_LIST[0],
            "duration_str": duration_str,
            "participants": {},
            "chat_type": chat_type
        }
    
    threading.Thread(target=update_timer, args=(message.chat.id, session_key), daemon=True).start()

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/s_"))
def shortcut_handler(message):
    shortcut = message.text[3:]
    duration = parse_duration(shortcut)
    if not duration:
        return
        
    session_key = f"{message.chat.id}:{message.from_user.id}"
    if session_key in active_sessions:
        return
        
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=duration)
    
    with session_locks:
        active_sessions[session_key] = {
            "status": "active",
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "dua": DUA_LIST[0],
            "duration_str": shortcut,
            "participants": {},
            "chat_type": message.chat.type
        }
    
    threading.Thread(target=update_timer, args=(message.chat.id, session_key), daemon=True).start()

@bot.message_handler(commands=['stop'])
def stop_cmd(message):
    chat_type = message.chat.type
    session_key = f"{message.chat.id}:0" if chat_type != 'private' else f"{message.chat.id}:{message.from_user.id}"
    
    with session_locks:
        if session_key in active_sessions:
            session = active_sessions[session_key]
            if session["status"] == "active":
                session["status"] = "paused"
                remaining = int((datetime.fromisoformat(session["end_time"]) - datetime.now()).total_seconds())
                session["paused_remaining"] = max(0, remaining)
                bot.send_message(message.chat.id, "⏸ *تم إيقاف المؤقت مؤقتاً*", parse_mode="Markdown")
            else:
                bot.send_message(message.chat.id, "❌ المؤقت متوقف بالفعل.")
        else:
            bot.send_message(message.chat.id, "❌ لا توجد جلسة نشطة حالياً.")

@bot.message_handler(commands=['ready'])
def ready_cmd(message):
    chat_type = message.chat.type
    session_key = f"{message.chat.id}:0" if chat_type != 'private' else f"{message.chat.id}:{message.from_user.id}"
    
    with session_locks:
        if session_key in active_sessions and active_sessions[session_key]["status"] == "paused":
            session = active_sessions[session_key]
            session["status"] = "active"
            remaining = session["paused_remaining"]
            start_time = datetime.now()
            end_time = start_time + timedelta(seconds=remaining)
            session["start_time"] = start_time.isoformat()
            session["end_time"] = end_time.isoformat()
            bot.send_message(message.chat.id, "▶ *تم استئناف المؤقت*", parse_mode="Markdown")
            
            threading.Thread(target=update_timer, args=(message.chat.id, session_key), daemon=True).start()
        else:
            bot.send_message(message.chat.id, "❌ لا توجد جلسة متوقفة.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("join_"))
def join_callback(call):
    session_key = call.data[5:]
    alert_text = None
    should_edit = False

    with session_locks:
        if session_key not in active_sessions:
            alert_text = "❌ لا توجد جلسة نشطة حالياً."
        else:
            session = active_sessions[session_key]
            user_id_str = str(call.from_user.id)
            participants = session.setdefault("participants", {})

            if user_id_str in participants:
                alert_text = "⚠️ انت منضم سابقاً بالفعل!"
            else:
                display_name = f"المستخدم ( @{call.from_user.username} )" if call.from_user.username else f"المستخدم ( {call.from_user.first_name} )"
                participants[user_id_str] = display_name
                alert_text = "✅ تم انضمامك للمعسكر!"
                should_edit = True

    bot.answer_callback_query(call.id, alert_text)

    if should_edit:
        try:
            remaining = int((datetime.fromisoformat(session["end_time"]) - datetime.now()).total_seconds())
            bot.edit_message_text(
                get_timer_text(session, max(0, remaining)),
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=get_timer_keyboard(session_key)
            )
        except Exception:
            pass

@bot.my_chat_member_handler()
def my_chat_member_handler(update):
    if update.old_chat_member.status in ["member", "restricted"] and update.new_chat_member.status == "administrator":
        group_welcome = (
            "*شكرا لأضافتي في المجموعة* 🫂🖤\n\n"
            "*بعض التعليمات المهمه عني لكي تستطيع استخدامي جيدا* 👇:\n"
            "يجب عليك رفع البوت مشرف في المجموعه و فتح الصلاحيات التالية:\n"
            "*• صلاحية حذف الرسائل*\n"
            "*• صلاحية تعديل الرسائل*\n"
            "*• صلاحية تثبيت الرسائل*\n\n"
            "*كيفية استخدامي* ⛔️:\n"
            "👈🏻  استخدم الأمر مع الوقت المطلوب لتحديد مدة المعسكر\n"
            "   - `/start 2h30m`  ➡️ لمدة ساعتان ونصف\n"
            "   - `/start 45m`        ➡️ لمدة 45 دقيقة"
        )
        bot.send_message(update.chat.id, group_welcome, parse_mode="Markdown")

if __name__ == "__main__":
    print("Study bot running with telebot...")
    bot.infinity_polling(allowed_updates=["message", "chat_member", "my_chat_member", "callback_query"])
