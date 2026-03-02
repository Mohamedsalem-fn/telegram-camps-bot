import json
import os
import time
import requests
import re
import threading
from datetime import datetime, timedelta


TOKEN = "8662823218:AAFvqvbhGAMppfR_IrIaojk3EocViL3nfnM"
URL = f"https://api.telegram.org/bot{TOKEN}"

active_sessions = {}
session_locks = threading.Lock()


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
                        
                        if participants_list:
                            participants_text = "\n".join(participants_list)
                        else:
                            participants_text = "لا يوجد مشاركين"
                        
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


def handle_message(message):
    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "")
    chat_type = message["chat"]["type"]
    
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
            
            session_key = f"{chat_id}:0"  # للمجموعات نستخدم 0 بدل user_id
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
                    "chat_type": chat_type
                }
            
            timer_thread = threading.Thread(
                target=update_timer,
                args=(chat_id, session_key, duration_str),
                daemon=True
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
                        "duration_str": shortcut
                    }
                
                timer_thread = threading.Thread(
                    target=update_timer,
                    args=(chat_id, session_key, shortcut),
                    daemon=True
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
                    daemon=True
                )
                timer_thread.start()
            else:
                send_message(chat_id, "❌ لا توجد جلسة متوقفة.")
        return


def handle_callback(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    user_id = callback_query["from"]["id"]
    data = callback_query["data"]
    message_id = callback_query["message"]["message_id"]
    first_name = callback_query["from"].get("first_name", "")
    username = callback_query["from"].get("username")
    
    if data.startswith("join_"):
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

                if username:
                    participant_display = f"المستخدم ( @{username} )"
                else:
                    participant_display = f"المستخدم ( {first_name} )"

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
            req(
                "answerCallbackQuery",
                json_data={
                    "callback_query_id": callback_query["id"],
                    "text": alert_text,
                    "show_alert": False,
                },
            )

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


def main():
    offset = 0

    if not TOKEN or TOKEN == "توكن_البوت":
        print("ERROR: ضع توكن البوت في متغير البيئة STUDY_BOT_TOKEN أو عدّل قيمة TOKEN داخل الملف")
        return

    print("Study bot running...")

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
                if "message" in update:
                    handle_message(update["message"])
                elif "my_chat_member" in update:
                    handle_my_chat_member(update["my_chat_member"])
                elif "callback_query" in update:
                    handle_callback(update["callback_query"])

        except KeyboardInterrupt:
            print("Stopped")
            raise
        except Exception:
            time.sleep(1)


if __name__ == "__main__":
    main()
