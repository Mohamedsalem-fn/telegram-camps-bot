import json
import os
import time
import requests
import re
import threading
from datetime import datetime, timedelta

# #HESHVM - Modified manually by HESHVM with full power and precision ✍️

TOKEN = os.getenv("STUDY_BOT_TOKEN", "8662823218:AAFvqvbhGAMppfR_IrIaojk3EocViL3nfnM")
URL = f"https://api.telegram.org/bot{TOKEN}"

# ─── Developers ───────────────────────────────────────────────
DEVELOPERS = {
    8554620638: "@M_X_K1",
    8554620638: "@M_X_K1",
}

# ─── Bot State ────────────────────────────────────────────────
active_sessions = {}
session_locks = threading.Lock()

bot_enabled = True           # تفعيل/تعليق البوت
forced_channels = []         # قائمة القنوات الإجبارية
known_users = {}             # {user_id: {"name": ..., "username": ..., "joined": ...}}
user_locks = threading.Lock()
state_lock = threading.Lock()

# ─── Helpers ──────────────────────────────────────────────────

def is_developer(user_id: int) -> bool:
    return user_id in DEVELOPERS


def req(method, json_data=None, params=None):
    try:
        if json_data is not None:
            r = requests.post(f"{URL}/{method}", json=json_data, timeout=20)
        elif params is not None:
            r = requests.post(f"{URL}/{method}", data=params, timeout=20)
        else:
            r = requests.post(f"{URL}/{method}", timeout=20)
        return r.json() if r.text else {"ok": False}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_message(chat_id, text, parse_mode=None, disable_web_page_preview=True, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": disable_web_page_preview,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return req("sendMessage", json_data=payload)


def edit_message(chat_id, message_id, text, parse_mode=None, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return req("editMessageText", json_data=payload)


def answer_callback(callback_id, text="", show_alert=False):
    req("answerCallbackQuery", json_data={
        "callback_query_id": callback_id,
        "text": text,
        "show_alert": show_alert,
    })


def get_chat_member_status(channel, user_id):
    result = req("getChatMember", json_data={"chat_id": channel, "user_id": user_id})
    if result.get("ok"):
        return result["result"]["status"]
    return "left"


def is_user_subscribed(user_id: int) -> bool:
    """تحقق أن المستخدم مشترك في كل القنوات الإجبارية"""
    with state_lock:
        channels = list(forced_channels)
    for ch in channels:
        status = get_chat_member_status(ch, user_id)
        if status in ("left", "kicked"):
            return False
    return True


def get_bot_admin_status(channel) -> bool:
    """هل البوت أدمن في القناة/الجروب؟"""
    result = req("getMe", json_data={})
    if not result.get("ok"):
        return False
    bot_id = result["result"]["id"]
    status = get_chat_member_status(channel, bot_id)
    return status in ("administrator", "creator")


def register_user(user):
    uid = user["id"]
    with user_locks:
        if uid not in known_users:
            known_users[uid] = {
                "name": user.get("first_name", ""),
                "username": user.get("username", ""),
                "joined": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }


def notify_developers(text, parse_mode=None):
    for dev_id in DEVELOPERS:
        send_message(dev_id, text, parse_mode=parse_mode)

# ─── Subscription Check Keyboard ──────────────────────────────

def subscription_keyboard():
    with state_lock:
        channels = list(forced_channels)
    buttons = []
    for ch in channels:
        label = ch if ch.startswith("@") else ch
        buttons.append([{"text": f"📢 اشترك في {label}", "url": f"https://t.me/{ch.lstrip('@')}"}])
    buttons.append([{"text": "✅ تحققت من اشتراكي", "callback_data": "check_subscription"}])
    return json.dumps({"inline_keyboard": buttons})


def subscription_message(chat_id, user_name=""):
    with state_lock:
        channels = list(forced_channels)
    channels_list = "\n".join([f"   • {ch}" for ch in channels])
    text = (
        f"👋 مرحباً {user_name}!\n\n"
        f"⚠️ *يجب عليك الاشتراك في القنوات التالية أولاً لاستخدام البوت:*\n\n"
        f"{channels_list}\n\n"
        f"بعد الاشتراك اضغط زرار التحقق ✅"
    )
    send_message(chat_id, text, parse_mode="Markdown", reply_markup=subscription_keyboard())

# ─── Texts ────────────────────────────────────────────────────

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

# ─── Duration Parsing ─────────────────────────────────────────

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
    total = hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_datetime(dt):
    return dt.strftime("%I:%M %p").lstrip("0")

# ─── Timer Thread ─────────────────────────────────────────────

def update_timer(chat_id, session_key, duration_str):
    while session_key in active_sessions and active_sessions[session_key]["status"] == "active":
        try:
            session = active_sessions[session_key]
            now = datetime.now()
            end_time = datetime.fromisoformat(session["end_time"])

            if now >= end_time:
                with session_locks:
                    if session_key in active_sessions:
                        participants = session.get("participants", {})
                        participants_list = []
                        for participant in participants.values():
                            participants_list.append(f"{len(participants_list) + 1} {participant}")

                        participants_text = "\n".join(participants_list) if participants_list else "لا يوجد مشاركين"

                        end_message = (
                            f"*تم انهاء المعسكر بنجاح* ✅\n\n"
                            f"*المشاركين في هذا المعسكر* 👥\n\n"
                            f"{participants_text}\n\n"
                            f"*كان زمن هذا المعسكر* ( `{duration_str}` ) *⏱️*\n"
                            f"*ان شاء الله تكونو انجزتو كويس في المعسكر و خلصتو جزء من الي عليكم* 🖤"
                        )

                        send_message(chat_id, end_message, parse_mode="Markdown")
                        del active_sessions[session_key]
                break

            remaining = int((end_time - now).total_seconds())
            start_time = datetime.fromisoformat(session["start_time"])
            participants_count = len(session.get("participants", {}))

            msg_text = (
                f"*✨ دعـاء المذاكـرة (قبل البدء):*\n"
                f"» {session['dua']}\n\n"
                f"*⏳ الوقت المتبقي:* `{format_time(remaining)}`\n"
                f"*⏱️ المدة المحددة:* `{duration_str}`\n"
                f"*🕒 وقت البدء:* `{format_datetime(start_time)}`\n"
                f"*🎯 وقت الانتهاء:* `{format_datetime(end_time)}`\n"
                f"*👥 عدد المشاركين حالياً:* `{participants_count}`\n"
                f"————————————————————\n"
                f"• لإيقاف المؤقت: `/stop` | لاستئنافه: `/ready`"
            )

            keyboard = {
                "inline_keyboard": [
                    [{"text": "انضمام 👥", "callback_data": f"join_{session_key}"}]
                ]
            }

            if "message_id" not in session:
                result = send_message(chat_id, msg_text, parse_mode="Markdown", reply_markup=json.dumps(keyboard))
                if result.get("ok"):
                    session["message_id"] = result["result"]["message_id"]
            else:
                edit_message(chat_id, session["message_id"], msg_text, parse_mode="Markdown", reply_markup=json.dumps(keyboard))

            time.sleep(0.7)
        except Exception as e:
            print(f"Timer update error: {e}")
            break

# ─── Admin Panel ──────────────────────────────────────────────

def panel_keyboard():
    global bot_enabled
    toggle_label = "🔴 تعطيل البوت" if bot_enabled else "🟢 تفعيل البوت"
    return json.dumps({
        "inline_keyboard": [
            [{"text": toggle_label, "callback_data": "panel_toggle"}],
            [{"text": "👥 المستخدمين", "callback_data": "panel_users"}],
            [{"text": "📢 القنوات الإجبارية", "callback_data": "panel_channels"}],
            [{"text": "📊 إحصائيات", "callback_data": "panel_stats"}],
            [{"text": "📋 الجلسات النشطة", "callback_data": "panel_sessions"}],
            [{"text": "📣 رسالة جماعية", "callback_data": "panel_broadcast"}],
            [{"text": "🗑 مسح جميع الجلسات", "callback_data": "panel_clear_sessions"}],
            [{"text": "🔧 المطورين", "callback_data": "panel_devs"}],
        ]
    })


def panel_text():
    global bot_enabled
    status = "✅ مفعّل" if bot_enabled else "❌ معطّل"
    with state_lock:
        ch_count = len(forced_channels)
    with user_locks:
        u_count = len(known_users)
    with session_locks:
        s_count = len(active_sessions)
    return (
        f"*🎛 لوحة تحكم المطور*\n"
        f"————————————————————\n"
        f"*حالة البوت:* {status}\n"
        f"*👥 إجمالي المستخدمين:* `{u_count}`\n"
        f"*📢 القنوات الإجبارية:* `{ch_count}`\n"
        f"*⏱ الجلسات النشطة:* `{s_count}`\n"
        f"————————————————————\n"
        f"اختر إجراءً من القائمة أدناه:"
    )


def handle_panel_callback(callback_query, data):
    global bot_enabled
    chat_id = callback_query["message"]["chat"]["id"]
    message_id = callback_query["message"]["message_id"]
    cid = callback_query["id"]
    user_id = callback_query["from"]["id"]

    if not is_developer(user_id):
        answer_callback(cid, "⛔️ ليس لديك صلاحية!", show_alert=True)
        return

    if data == "panel_toggle":
        with state_lock:
            bot_enabled = not bot_enabled
        status = "✅ تم تفعيل البوت" if bot_enabled else "❌ تم تعطيل البوت"
        answer_callback(cid, status, show_alert=True)
        edit_message(chat_id, message_id, panel_text(), parse_mode="Markdown", reply_markup=panel_keyboard())

    elif data == "panel_users":
        with user_locks:
            users = dict(known_users)
        if not users:
            answer_callback(cid, "لا يوجد مستخدمين بعد", show_alert=True)
            return
        lines = [f"*👥 قائمة المستخدمين ({len(users)}):*\n"]
        for i, (uid, info) in enumerate(users.items(), 1):
            uname = f"@{info['username']}" if info['username'] else info['name']
            lines.append(f"{i}. {uname} — `{uid}` — {info['joined']}")
        text = "\n".join(lines)
        # إرسال كرسالة منفصلة لأنها قد تكون طويلة
        send_message(chat_id, text[:4096], parse_mode="Markdown")
        answer_callback(cid)

    elif data == "panel_channels":
        with state_lock:
            channels = list(forced_channels)
        if not channels:
            ch_text = "لا توجد قنوات إجبارية مضافة."
        else:
            ch_text = "\n".join([f"• {ch}" for ch in channels])
        text = (
            f"*📢 القنوات الإجبارية الحالية:*\n\n{ch_text}\n\n"
            f"لإضافة قناة: `/addchannel @username`\n"
            f"لحذف قناة: `/removechannel @username`"
        )
        keyboard = json.dumps({"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "panel_back"}]]})
        edit_message(chat_id, message_id, text, parse_mode="Markdown", reply_markup=keyboard)
        answer_callback(cid)

    elif data == "panel_stats":
        with user_locks:
            u_count = len(known_users)
        with session_locks:
            s_count = len(active_sessions)
        with state_lock:
            ch_count = len(forced_channels)
            enabled = bot_enabled
        text = (
            f"*📊 إحصائيات البوت*\n"
            f"————————————————————\n"
            f"*👥 المستخدمين:* `{u_count}`\n"
            f"*⏱ جلسات نشطة:* `{s_count}`\n"
            f"*📢 قنوات إجبارية:* `{ch_count}`\n"
            f"*حالة البوت:* {'✅ مفعّل' if enabled else '❌ معطّل'}\n"
            f"*🕒 التاريخ:* `{datetime.now().strftime('%Y-%m-%d %H:%M')}`"
        )
        keyboard = json.dumps({"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "panel_back"}]]})
        edit_message(chat_id, message_id, text, parse_mode="Markdown", reply_markup=keyboard)
        answer_callback(cid)

    elif data == "panel_sessions":
        with session_locks:
            sessions = dict(active_sessions)
        if not sessions:
            answer_callback(cid, "لا توجد جلسات نشطة حالياً", show_alert=True)
            return
        lines = [f"*📋 الجلسات النشطة ({len(sessions)}):*\n"]
        for key, s in sessions.items():
            end = datetime.fromisoformat(s["end_time"])
            remaining = max(0, int((end - datetime.now()).total_seconds()))
            participants = len(s.get("participants", {}))
            lines.append(
                f"• `{key}` | {s.get('duration_str','?')} | متبقي: {format_time(remaining)} | مشاركين: {participants}"
            )
        send_message(chat_id, "\n".join(lines)[:4096], parse_mode="Markdown")
        answer_callback(cid)

    elif data == "panel_broadcast":
        answer_callback(cid)
        send_message(chat_id,
            "*📣 أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:*\n"
            "_(أرسل الرسالة كرد على هذه الرسالة أو أرسل /broadcast ثم الرسالة)_",
            parse_mode="Markdown")

    elif data == "panel_clear_sessions":
        with session_locks:
            count = len(active_sessions)
            active_sessions.clear()
        answer_callback(cid, f"✅ تم مسح {count} جلسة", show_alert=True)
        edit_message(chat_id, message_id, panel_text(), parse_mode="Markdown", reply_markup=panel_keyboard())

    elif data == "panel_devs":
        devs = "\n".join([f"• {uname} — `{uid}`" for uid, uname in DEVELOPERS.items()])
        text = f"*🔧 المطورون:*\n\n{devs}"
        keyboard = json.dumps({"inline_keyboard": [[{"text": "🔙 رجوع", "callback_data": "panel_back"}]]})
        edit_message(chat_id, message_id, text, parse_mode="Markdown", reply_markup=keyboard)
        answer_callback(cid)

    elif data == "panel_back":
        edit_message(chat_id, message_id, panel_text(), parse_mode="Markdown", reply_markup=panel_keyboard())
        answer_callback(cid)

# ─── Handlers ─────────────────────────────────────────────────

def handle_my_chat_member(chat_member_update):
    chat_id = chat_member_update["chat"]["id"]
    old_status = chat_member_update["old_chat_member"]["status"]
    new_status = chat_member_update["new_chat_member"]["status"]

    if old_status in ["member", "restricted"] and new_status == "administrator":
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
        send_message(chat_id, group_welcome, parse_mode="Markdown")


# حالة انتظار البرودكاست
broadcast_waiting = set()


def handle_message(message):
    global bot_enabled
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    chat_type = message["chat"]["type"]
    user = message["from"]

    # تسجيل المستخدم دائماً
    register_user(user)

    # ─── أوامر المطور (تعمل حتى لو البوت معطّل) ────────────────

    if text == "/panel":
        if not is_developer(user_id):
            send_message(chat_id, "⛔️ هذا الأمر للمطورين فقط.")
            return
        send_message(chat_id, panel_text(), parse_mode="Markdown", reply_markup=panel_keyboard())
        return

    if text.startswith("/addchannel"):
        if not is_developer(user_id):
            send_message(chat_id, "⛔️ هذا الأمر للمطورين فقط.")
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ استخدام: `/addchannel @channel_username`", parse_mode="Markdown")
            return
        channel = parts[1]
        if not channel.startswith("@"):
            send_message(chat_id, "❌ يجب أن يبدأ اليوزر بـ @")
            return
        # تحقق أن البوت أدمن في القناة
        if not get_bot_admin_status(channel):
            send_message(chat_id, f"❌ البوت ليس مشرفاً في {channel}!\nأضف البوت كمشرف أولاً ثم أعد المحاولة.")
            return
        with state_lock:
            if channel not in forced_channels:
                forced_channels.append(channel)
                send_message(chat_id, f"✅ تم إضافة القناة الإجبارية: {channel}")
            else:
                send_message(chat_id, f"⚠️ القناة {channel} مضافة بالفعل!")
        return

    if text.startswith("/removechannel"):
        if not is_developer(user_id):
            send_message(chat_id, "⛔️ هذا الأمر للمطورين فقط.")
            return
        parts = text.split()
        if len(parts) < 2:
            send_message(chat_id, "❌ استخدام: `/removechannel @channel_username`", parse_mode="Markdown")
            return
        channel = parts[1]
        with state_lock:
            if channel in forced_channels:
                forced_channels.remove(channel)
                send_message(chat_id, f"✅ تم حذف القناة الإجبارية: {channel}")
            else:
                send_message(chat_id, f"⚠️ القناة {channel} غير موجودة في القائمة!")
        return

    if text.startswith("/broadcast"):
        if not is_developer(user_id):
            send_message(chat_id, "⛔️ هذا الأمر للمطورين فقط.")
            return
        parts = text.split(None, 1)
        if len(parts) < 2:
            broadcast_waiting.add(user_id)
            send_message(chat_id, "📣 أرسل الآن الرسالة التي تريد إرسالها لجميع المستخدمين:")
            return
        broadcast_text = parts[1]
        _do_broadcast(chat_id, broadcast_text)
        return

    # معالجة رسائل البرودكاست المنتظَرة
    if user_id in broadcast_waiting:
        broadcast_waiting.discard(user_id)
        _do_broadcast(chat_id, text)
        return

    # ─── فحص تفعيل البوت ────────────────────────────────────────
    if not bot_enabled:
        send_message(chat_id, "⏸ البوت معطّل مؤقتاً من قِبل المطورين.")
        return

    # ─── فحص الاشتراك الإجباري ──────────────────────────────────
    with state_lock:
        channels = list(forced_channels)
    if channels and not is_user_subscribed(user_id):
        user_name = user.get("first_name", "")
        subscription_message(chat_id, user_name)
        return

    # ─── الأوامر العادية ─────────────────────────────────────────

    if text == "/start":
        send_message(chat_id, WELCOME_TEXT, parse_mode="HTML")
        return

    if text.startswith("/start "):
        parts = text.split()
        if len(parts) > 1:
            duration_str = parts[1]
            duration = parse_duration(duration_str)
            if not duration:
                send_message(chat_id, "❌ صيغة الوقت غير صحيحة! استخدم مثلاً: /start 1h30m")
                return

            session_key = f"{chat_id}:0"
            if session_key in active_sessions:
                send_message(chat_id, "⏳ هناك جلسة نشطة حالياً. قم بإيقافها أولاً بـ /stop")
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
                    "chat_type": chat_type,
                }

            timer_thread = threading.Thread(
                target=update_timer,
                args=(chat_id, session_key, duration_str),
                daemon=True,
            )
            timer_thread.start()
        return

    if text.startswith("/s_"):
        shortcut = text[3:]
        duration = parse_duration(shortcut)
        if duration:
            session_key = f"{chat_id}:{user_id}"
            if session_key not in active_sessions:
                start_time = datetime.now()
                end_time = start_time + timedelta(seconds=duration)

                with session_locks:
                    active_sessions[session_key] = {
                        "status": "active",
                        "start_time": start_time.isoformat(),
                        "end_time": end_time.isoformat(),
                        "dua": DUA_LIST[0],
                        "duration_str": shortcut,
                    }

                timer_thread = threading.Thread(
                    target=update_timer,
                    args=(chat_id, session_key, shortcut),
                    daemon=True,
                )
                timer_thread.start()
        return

    if text == "/stop":
        session_key = f"{chat_id}:{0 if chat_type != 'private' else user_id}"
        with session_locks:
            if session_key in active_sessions:
                session = active_sessions[session_key]
                if session["status"] == "active":
                    session["status"] = "paused"
                    remaining = int((datetime.fromisoformat(session["end_time"]) - datetime.now()).total_seconds())
                    session["paused_remaining"] = max(0, remaining)
                    send_message(chat_id, "⏸ *تم إيقاف المؤقت مؤقتاً*", parse_mode="Markdown")
                else:
                    send_message(chat_id, "❌ المؤقت متوقف بالفعل.")
            else:
                send_message(chat_id, "❌ لا توجد جلسة نشطة حالياً.")
        return

    if text == "/ready":
        session_key = f"{chat_id}:{0 if chat_type != 'private' else user_id}"
        with session_locks:
            if session_key in active_sessions and active_sessions[session_key]["status"] == "paused":
                session = active_sessions[session_key]
                session["status"] = "active"
                remaining = session["paused_remaining"]
                start_time = datetime.now()
                end_time = start_time + timedelta(seconds=remaining)
                session["start_time"] = start_time.isoformat()
                session["end_time"] = end_time.isoformat()
                send_message(chat_id, "▶ *تم استئناف المؤقت*", parse_mode="Markdown")

                timer_thread = threading.Thread(
                    target=update_timer,
                    args=(chat_id, session_key, session.get("duration_str", "unknown")),
                    daemon=True,
                )
                timer_thread.start()
            else:
                send_message(chat_id, "❌ لا توجد جلسة متوقفة.")
        return


def _do_broadcast(sender_chat_id, broadcast_text):
    """إرسال رسالة جماعية لجميع المستخدمين"""
    with user_locks:
        users = list(known_users.keys())
    success = 0
    fail = 0
    for uid in users:
        result = send_message(uid, f"📣 *رسالة من الإدارة:*\n\n{broadcast_text}", parse_mode="Markdown")
        if result.get("ok"):
            success += 1
        else:
            fail += 1
        time.sleep(0.05)
    send_message(sender_chat_id, f"✅ تم الإرسال!\n✔️ نجح: {success}\n❌ فشل: {fail}")


def handle_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    user_id = callback_query["from"]["id"]
    data = callback_query["data"]
    message_id = callback_query["message"]["message_id"]
    first_name = callback_query["from"].get("first_name", "")
    username = callback_query["from"].get("username")
    cid = callback_query["id"]
    user = callback_query["from"]

    # تسجيل المستخدم
    register_user(user)

    # ─── لوحة التحكم ────────────────────────────────────────────
    if data.startswith("panel_"):
        handle_panel_callback(callback_query, data)
        return

    # ─── تحقق الاشتراك ──────────────────────────────────────────
    if data == "check_subscription":
        with state_lock:
            channels = list(forced_channels)
        if not channels or is_user_subscribed(user_id):
            answer_callback(cid, "✅ شكراً! تم التحقق من اشتراكك.", show_alert=True)
            send_message(chat_id, WELCOME_TEXT, parse_mode="HTML")
            # إشعار المطورين
            uname = f"@{username}" if username else first_name
            notify_developers(
                f"👤 *مستخدم جديد انضم بعد الاشتراك الإجباري!*\n"
                f"الاسم: {uname}\n"
                f"ID: `{user_id}`",
                parse_mode="Markdown"
            )
        else:
            answer_callback(cid, "❌ لم تشترك في جميع القنوات بعد!", show_alert=True)
        return

    # ─── الانضمام للجلسة ─────────────────────────────────────────
    if data.startswith("join_"):
        # فحص الاشتراك
        with state_lock:
            channels = list(forced_channels)
        if channels and not is_user_subscribed(user_id):
            answer_callback(cid, "⚠️ يجب الاشتراك في القنوات أولاً!", show_alert=True)
            return

        session_key = data[5:]
        should_edit = False
        alert_text = None
        snapshot = None

        with session_locks:
            if session_key not in active_sessions:
                alert_text = "❌ لا توجد جلسة نشطة حالياً."
            else:
                session = active_sessions[session_key]
                participants = session.setdefault("participants", {})

                participant_display = f"المستخدم ( @{username} )" if username else f"المستخدم ( {first_name} )"

                if str(user_id) in participants:
                    alert_text = "⚠️ انت منضم سابقاً بالفعل!"
                else:
                    participants[str(user_id)] = participant_display
                    alert_text = "✅ تم انضمامك للمعسكر!"
                    should_edit = True

                snapshot = {
                    "dua": session.get("dua", ""),
                    "duration_str": session.get("duration_str", "unknown"),
                    "start_time": session.get("start_time"),
                    "end_time": session.get("end_time"),
                    "participants_count": len(participants),
                }

        if alert_text:
            answer_callback(cid, alert_text, show_alert=False)

        if not should_edit or not snapshot or not snapshot.get("start_time") or not snapshot.get("end_time"):
            return

        try:
            remaining = int((datetime.fromisoformat(snapshot["end_time"]) - datetime.now()).total_seconds())
            start_time = datetime.fromisoformat(snapshot["start_time"])
            end_time = datetime.fromisoformat(snapshot["end_time"])

            msg_text = (
                f"*✨ دعـاء المذاكـرة (قبل البدء):*\n"
                f"» {snapshot['dua']}\n\n"
                f"*⏳ الوقت المتبقي:* `{format_time(max(0, remaining))}`\n"
                f"*⏱️ المدة المحددة:* `{snapshot['duration_str']}`\n"
                f"*🕒 وقت البدء:* `{format_datetime(start_time)}`\n"
                f"*🎯 وقت الانتهاء:* `{format_datetime(end_time)}`\n"
                f"*👥 عدد المشاركين حالياً:* `{snapshot['participants_count']}`\n"
                f"————————————————————\n"
                f"• لإيقاف المؤقت: `/stop` | لاستئنافه: `/ready`"
            )

            keyboard = {
                "inline_keyboard": [
                    [{"text": "انضمام 👥", "callback_data": f"join_{session_key}"}]
                ]
            }

            edit_message(chat_id, message_id, msg_text, parse_mode="Markdown", reply_markup=json.dumps(keyboard))
        except Exception:
            return

# ─── Main Loop ────────────────────────────────────────────────

def main():
    offset = 0

    if not TOKEN or TOKEN == "توكن_البوت":
        print("ERROR: ضع توكن البوت في متغير البيئة STUDY_BOT_TOKEN")
        return

    print("✅ Study bot running... | #HESHVM")

    while True:
        try:
            resp = requests.get(
                f"{URL}/getUpdates",
                params={
                    "timeout": 30,
                    "offset": offset,
                    "allowed_updates": ["message", "chat_member", "my_chat_member", "callback_query"],
                },
                timeout=40,
            )

            if not resp.ok:
                time.sleep(1)
                continue

            data = resp.json()
            if not data.get("ok"):
                time.sleep(1)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                try:
                    if "message" in update:
                        handle_message(update["message"])
                    elif "my_chat_member" in update:
                        handle_my_chat_member(update["my_chat_member"])
                    elif "callback_query" in update:
                        handle_callback(update["callback_query"])
                except Exception as e:
                    print(f"Update handling error: {e}")

        except KeyboardInterrupt:
            print("Stopped")
            raise
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()

# #HESHVM ✍️ — Edited manually with full precision and power 🔥
