import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import datetime
import random
import sqlite3
import time

# ==================================================
# ========== ТВОИ ДАННЫЕ ===========================
# ==================================================

GROUP_ID = 195388835
POST_ID = 21351
ACCESS_TOKEN = "vk1.a.EQ4igo1JXTzr3yUVjVjAncwJuNiynaujlMz0A0tlGGPe3qN5JIRW17qFhcqBoIcxBOIYI-hSpLzCns6Ux0CD5qBPu962E09lp0JgkHq168qspp6elPFWTKuY4vjN8_cpUg3GCiPKyfgdMXFdxF61NYNs1PjihwOkswWpvetCDPOpfs2pJi6AIgsm5_T7VcZp0T8-RAa5tTn3tAkg5_i-fg"

WORDS = ['Урок', 'рубин',  'мониторинг', 'корзина', 'школа', 'отзыв', 'аспирант', 'бакалавриат', 'рюкзак', 'циркуль', 'кисточка', 'ремонт', 'ножницы', 'университет', 'факультет', 'дистанция', 'адрес', 'сайт', 'факт', 'ручка', 'клей', 'пластилин', 'альбом', 'папка', 'файл', 'точилка', 'бумага', 'стикер', 'ежедневник', 'доска', 'транспортир', 'статья', 'буфет', 'учебник', 'словарь', 'атлас', 'гуашь', 'фломастер', 'крокодил', 'подушка', 'ошибка', 'внешность', 'инвентарь', 'аукцион', 'список', 'город', 'квартира', 'товар', 'штраф', 'экзамен', 'лекция', 'сессия', 'реферат', 'доклад']

ATTEMPTS_SUBSCRIBED = 15
ATTEMPTS_UNSUBSCRIBED = 10
BONUS_ATTEMPTS_FOR_REPOST = 20

DB_NAME = "/app/data/game_stats.db"

# ==================================================
# ========== КЭШ ===================================
# ==================================================

subscription_cache = {}   # { user_id: (is_subscribed, timestamp) }
name_cache = {}           # { user_id: (first_name, last_name) }
CACHE_TTL = 600           # 10 минут

# ==================================================
# ========== БАЗА ДАННЫХ ===========================
# ==================================================

def init_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS players (
        user_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, total_words INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS guessed_words (
        word TEXT PRIMARY KEY, user_id INTEGER, guessed_date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS attempts (
        user_id INTEGER, date TEXT, count INTEGER DEFAULT 0, bonus_used INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, date))''')
    conn.commit()
    conn.close()


def get_player_stats(user_id):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT total_words FROM players WHERE user_id = ?', (user_id,))
    r = cur.fetchone(); conn.close()
    return r[0] if r else 0


def update_player_stats(user_id, first_name, last_name):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT user_id FROM players WHERE user_id = ?', (user_id,))
    if cur.fetchone():
        cur.execute('UPDATE players SET total_words = total_words + 1, first_name=?, last_name=? WHERE user_id=?',
                    (first_name, last_name, user_id))
    else:
        cur.execute('INSERT INTO players (user_id, first_name, last_name, total_words) VALUES (?,?,?,1)',
                    (user_id, first_name, last_name))
    conn.commit(); conn.close()


def save_guessed_word(word, user_id):
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO guessed_words (word, user_id, guessed_date) VALUES (?,?,?)',
                (word, user_id, get_today()))
    conn.commit(); conn.close()


def get_guessed_words():
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT word, user_id FROM guessed_words')
    r = cur.fetchall(); conn.close()
    return {w: str(u) for w, u in r}


def get_all_players_stats():
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT user_id, first_name, last_name, total_words FROM players ORDER BY total_words DESC')
    r = cur.fetchall(); conn.close(); return r


def get_attempts_info_db(user_id):
    today = get_today()
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    cur.execute('SELECT count, bonus_used FROM attempts WHERE user_id=? AND date=?', (user_id, today))
    r = cur.fetchone(); conn.close()
    return {"date": today, "count": r[0], "bonus_used": r[1]} if r else {"date": today, "count": 0, "bonus_used": 0}


def update_attempts_db(user_id, count, bonus_used=None):
    today = get_today()
    conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
    if bonus_used is not None:
        cur.execute('INSERT OR REPLACE INTO attempts (user_id, date, count, bonus_used) VALUES (?,?,?,?)',
                    (user_id, today, count, bonus_used))
    else:
        cur.execute('''INSERT OR REPLACE INTO attempts (user_id, date, count, bonus_used)
                       VALUES (?,?,?, COALESCE((SELECT bonus_used FROM attempts WHERE user_id=? AND date=?),0))''',
                    (user_id, today, count, user_id, today))
    conn.commit(); conn.close()


def is_bonus_used(user_id):
    return get_attempts_info_db(user_id)["bonus_used"] == 1


def use_bonus(user_id):
    info = get_attempts_info_db(user_id)
    update_attempts_db(user_id, info["count"] + BONUS_ATTEMPTS_FOR_REPOST, 1)


def get_max_attempts(user_id):
    return ATTEMPTS_SUBSCRIBED if is_subscribed(user_id) else ATTEMPTS_UNSUBSCRIBED


def get_total_attempts(user_id):
    base = get_max_attempts(user_id)
    return base + BONUS_ATTEMPTS_FOR_REPOST if get_attempts_info_db(user_id)["bonus_used"] == 1 else base


def get_remaining_attempts(user_id):
    return max(0, get_total_attempts(user_id) - get_attempts_info_db(user_id)["count"])


def can_try(user_id):
    return get_remaining_attempts(user_id) > 0


def use_attempt(user_id):
    info = get_attempts_info_db(user_id)
    update_attempts_db(user_id, info["count"] + 1)


# ==================================================
# ========== ВСПОМОГАТЕЛЬНЫЕ =======================
# ==================================================

def get_today():
    return datetime.date.today().isoformat()


def is_subscribed(user_id):
    """Проверка подписки с кэшем на 10 минут"""
    now = time.time()
    if user_id in subscription_cache:
        cached_value, cached_time = subscription_cache[user_id]
        if now - cached_time < CACHE_TTL:
            return cached_value
    try:
        response = vk.groups.isMember(group_id=GROUP_ID, user_id=user_id)
        subscription_cache[user_id] = (response, now)
        return response
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        return False


def get_user_name(user_id):
    """Получение имени с кэшем"""
    if user_id in name_cache:
        return name_cache[user_id]
    try:
        u = vk.users.get(user_ids=user_id)[0]
        name = (u['first_name'], u['last_name'])
        name_cache[user_id] = name
        return name
    except:
        return (f"id{user_id}", "")


def send_comment(post_id, user_id, message, reply_to=None):
    try:
        vk.wall.createComment(owner_id=-GROUP_ID, post_id=post_id, from_group=1,
                              message=message, reply_to_comment=reply_to)
    except Exception as e:
        print(f"Ошибка отправки комментария: {e}")


def send_message(user_id, message):
    try:
        vk.messages.send(user_id=user_id, message=message, random_id=random.randint(1, 2 ** 31))
    except Exception as e:
        print(f"Ошибка отправки ЛС: {e}")


def check_repost(user_id):
    try:
        response = vk.wall.getReposts(owner_id=-GROUP_ID, post_id=POST_ID)
        if 'items' in response:
            for item in response['items']:
                if item.get('from_id') == user_id:
                    return True
        return False
    except Exception as e:
        print(f"Ошибка проверки репоста: {e}")
        return False


# ==================================================
# ========== ВСПОМОГАТЕЛЬНЫЕ ОТПРАВКИ ==============
# ==================================================

def send_hint_to_user(user_id):
    """Отправляет список отгаданных слов в ЛС"""
    guessed = get_guessed_words()
    if guessed:
        hint = "🔍 Отгаданные слова:\n" + "\n".join(
            f"✅ {w} — {' '.join(get_user_name(int(u)))}" for w, u in guessed.items())
    else:
        hint = "🔍 Пока не отгадано ни одного слова."
    send_message(user_id, hint)


def send_leaderboard_to_user(user_id):
    """Отправляет таблицу лидеров в ЛС"""
    players = get_all_players_stats()
    if not players:
        send_message(user_id, "🏆 Пока никто не отгадал ни одного слова!")
        return
    lb = "🏆 ТАБЛИЦА ЛИДЕРОВ 🏆\n\n"
    for i, (uid, fn, ln, total) in enumerate(players[:10], 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        lb += f"{medal} {fn} {ln} — {total} слов\n"
    if len(players) > 10:
        lb += f"\n... и ещё {len(players) - 10} игроков"
    send_message(user_id, lb)


# ==================================================
# ========== ОБРАБОТКА ЛС ==========================
# ==================================================

def handle_private_message(user_id, text):
    text_lower = text.strip().lower()

    # Подсказка
    if text_lower == "подсказка":
        send_hint_to_user(user_id)
        return

    # Лидеры
    if text_lower in ("лидеры", "топ"):
        send_leaderboard_to_user(user_id)
        return

    # Моя статистика
    if text_lower in ("моя статистика", "статистика", "я"):
        total = get_player_stats(user_id)
        remaining = get_remaining_attempts(user_id)
        fn, ln = get_user_name(user_id)
        send_message(user_id,
                     f"📊 {fn} {ln}\n"
                     f"✅ Отгадано слов: {total}\n"
                     f"🎯 Осталось попыток: {remaining}")
        return

    # Помощь
    if text_lower in ("помощь", "help", "начать", "start", "привет"):
        send_message(user_id,
                     "🎮 Доступные команды:\n\n"
                     "🔍 подсказка — список отгаданных слов\n"
                     "🏆 лидеры — таблица лидеров\n"
                     "📊 статистика — твоя статистика\n"
                     "🎁 репост — проверить репост и получить бонус\n\n"
                     "А ещё ты можешь угадывать слова в комментариях под постом!")
        return

    # Проверка репоста
    if text_lower in ("репост", "бонус", "проверить репост"):
        if is_bonus_used(user_id):
            send_message(user_id,
                         f"ℹ️ Ты уже использовал бонус сегодня! Осталось попыток: {get_remaining_attempts(user_id)}")
            return
        if check_repost(user_id):
            use_bonus(user_id)
            send_message(user_id,
                         f"🎁 Спасибо за репост! Ты получил +{BONUS_ATTEMPTS_FOR_REPOST} попыток!\n"
                         f"Осталось: {get_remaining_attempts(user_id)}")
        else:
            send_message(user_id, "❌ Репост не найден. Сделай репост поста и напиши «репост» снова.")
        return

    # Неизвестная команда
    send_message(user_id, "🤔 Я не понял команду. Напиши «помощь», чтобы увидеть список команд.")


# ==================================================
# ========== ОСНОВНАЯ ЛОГИКА (КОММЕНТАРИИ) =========
# ==================================================

def handle_comment(user_id, text, comment_id=None):
    text = text.strip().lower()

    # ====== 1. Команда "лидеры" ======
    if text in ("лидеры", "топ"):
        send_leaderboard_to_user(user_id)
        send_comment(POST_ID, user_id, "📊 Таблица лидеров отправлена в ЛС!")
        return

    # ====== 2. Команда "репост" / "бонус" ======
    if text in ("репост", "бонус", "проверить репост"):
        if is_bonus_used(user_id):
            send_comment(POST_ID, user_id,
                         f"ℹ️ Ты уже использовал бонус сегодня! Осталось попыток: {get_remaining_attempts(user_id)}")
            return
        if check_repost(user_id):
            use_bonus(user_id)
            fn, ln = get_user_name(user_id)
            send_comment(POST_ID, user_id,
                         f"🎁 {fn} {ln}, спасибо за репост! +{BONUS_ATTEMPTS_FOR_REPOST} попыток! "
                         f"Осталось: {get_remaining_attempts(user_id)}")
            send_message(user_id, f"🎁 Ты получил +{BONUS_ATTEMPTS_FOR_REPOST} попыток за репост!")
        else:
            send_comment(POST_ID, user_id, "❌ Репост не найден. Сделай репост поста и напиши «репост» снова.")
        return

    # ====== 3. Проверяем, слово ли это ======
    found = next((w for w in WORDS if w.lower() == text), None)

    # Если не слово из списка — сразу отвечаем (без проверки попыток)
    if not found:
        # Но если это похоже на попытку угадать — списываем попытку
        if not can_try(user_id):
            if not is_bonus_used(user_id):
                send_comment(POST_ID, user_id,
                             f"❌ Попытки закончились! Сделай репост и напиши «репост» — получишь +{BONUS_ATTEMPTS_FOR_REPOST}.")
            else:
                send_comment(POST_ID, user_id, "❌ Попытки закончились на сегодня! Завтра новый шанс.")
            return
        use_attempt(user_id)
        send_comment(POST_ID, user_id, f"❌ Неправильно! Осталось попыток: {get_remaining_attempts(user_id)}")
        return

    # ====== 4. Проверка попыток ======
    if not can_try(user_id):
        if not is_bonus_used(user_id):
            send_comment(POST_ID, user_id,
                         f"❌ Попытки закончились! Сделай репост и напиши «репост» — получишь +{BONUS_ATTEMPTS_FOR_REPOST}.")
        else:
            send_comment(POST_ID, user_id, "❌ Попытки закончились на сегодня! Завтра новый шанс.")
        return

    # ====== 5. Проверяем отгадано ли слово ======
    guessed = get_guessed_words()

    if found in guessed:
        fn, ln = get_user_name(int(guessed[found]))
        send_comment(POST_ID, user_id, f"⚠️ Слово «{found}» уже отгадал(а) {fn} {ln}!")
        # Попытку НЕ списываем, если слово уже отгадано
        return

    # ====== 6. Новое слово — засчитываем ======
    fn, ln = get_user_name(user_id)
    save_guessed_word(found, user_id)
    update_player_stats(user_id, fn, ln)
    use_attempt(user_id)

    send_comment(POST_ID, user_id,
                 f"🎉 Правильно! {fn} {ln} отгадал(а) «{found}»! "
                 f"Осталось: {get_remaining_attempts(user_id)}, всего: {get_player_stats(user_id)}")


# ==================================================
# ========== ЗАПУСК ================================
# ==================================================

init_database()

vk_session = vk_api.VkApi(token=ACCESS_TOKEN, api_version='5.131')
vk = vk_session.get_api()
longpoll = VkBotLongPoll(vk_session, GROUP_ID)

print("🤖 Бот запущен и слушает комментарии и ЛС...")
print(f"📌 Группа: {GROUP_ID}, Пост: {POST_ID}")
print("=" * 50)

for event in longpoll.listen():
    try:
        # ====== 1. СОБЫТИЯ ИЗ КОММЕНТАРИЕВ ======
        if event.type == VkBotEventType.WALL_REPLY_NEW:
            obj = event.object
            post_id = obj.get('post_id')
            if post_id != POST_ID:
                continue

            user_id = obj.get('from_id')
            text = obj.get('text', '').strip()
            comment_id = obj.get('id')

            if not text or user_id is None:
                continue
            if user_id < 0:
                continue

            print(f"💬 Комментарий от {user_id}: {text}")

            # Подсказка из комментариев → в ЛС + подтверждение
            if text.lower() == "подсказка":
                send_hint_to_user(user_id)
                send_comment(POST_ID, user_id, "📩 Подсказка отправлена тебе в личные сообщения!")
                continue

            handle_comment(user_id, text, comment_id)

        # ====== 2. СОБЫТИЯ ИЗ ЛИЧНЫХ СООБЩЕНИЙ ======
        elif event.type == VkBotEventType.MESSAGE_NEW:
            msg = event.object.message
            user_id = msg.get('from_id')
            text = msg.get('text', '').strip()

            if not text or user_id is None:
                continue
            if user_id < 0:
                continue

            print(f"✉️ ЛС от {user_id}: {text}")
            handle_private_message(user_id, text)

    except Exception as e:
        print(f"⚠️ Ошибка: {e}")
        continue
