import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import time
import threading
import requests
import json
import os
import sys
import logging
import atexit

# ================= КОНФИГУРАЦИЯ =================
TOKEN = "vk1.a.pWAMTUhJkodcMkUFpCa-UMg_6DKXwr6ISV863itpGw410z1RVSyawnce0r8wMMho0eD5rtIVnrITM22tQbnuqGtnJBZfH5FLopBeT33UG0AUbJI_cEJVbcJEAvOs34dt3PfAA0yiL0sjgabDA88ll9GRCB2nyxiywcI5286nSS-Db2Rn5AAzgp3nkzXfWzkLc4Xf-_vPgUu7pMVJc490Vw"
GROUP_ID = 239699656
MEAD_ID = 212887447

DATA_FILE = "apostles_data.json"
LOCK_FILE = "bot.lock"

API_URL = "https://welldungeon.online/api/v1/"

# ================= ЛОГИРОВАНИЕ =================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ================= БЛОКИРОВКА =================
def check_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE, 'r') as f:
                pid = f.read().strip()
                if os.name == 'nt':
                    import subprocess
                    result = subprocess.run(['tasklist', '/FI', f'PID eq {pid}'], capture_output=True, text=True)
                    if str(pid) in result.stdout:
                        logger.error(f"❌ Бот уже запущен (PID: {pid})!")
                        sys.exit(0)
                else:
                    try:
                        os.kill(int(pid), 0)
                        logger.error(f"❌ Бот уже запущен (PID: {pid})!")
                        sys.exit(0)
                    except OSError:
                        pass
        except:
            pass

    with open(LOCK_FILE, 'w') as f:
        f.write(str(os.getpid()))
    logger.info(f"🔒 Блокировка установлена (PID: {os.getpid()})")

def remove_lock():
    if os.path.exists(LOCK_FILE):
        try:
            os.remove(LOCK_FILE)
            logger.info("🔓 Блокировка снята")
        except:
            pass

# ================= ХРАНИЛИЩЕ =================
apostles_data = {}
apostles_cache = {}
apostle_cooldowns = {}
buff_queue = {}

# ================= 🎲 СЛУЧАЙНЫЕ СМАЙЛИКИ ДЛЯ АПОСТОЛОВ =================
APOSTLE_EMOJIS = [
    "🦊", "🐺", "🐉", "🦄", "🐲", "🦅", "🦇", "🐋", "🦈", "🐊",
    "🦍", "🐘", "🦏", "🐃", "🐆", "🐅", "🦁", "🐯", "🦒", "🦌",
    "🐕", "🐩", "🐈", "🐇", "🦝", "🦡", "🦫", "🦦", "🐿️", "🦔",
    "🦉", "🦜", "🐧", "🐦", "🦚", "🦩", "🕊️", "🦢", "🦃", "🐓",
    "🐞", "🦋", "🐝", "🐜", "🦟", "🦗", "🐌", "🐛", "🐚", "🪸"
]

def get_apostle_emoji(user_id):
    """Возвращает закреплённый смайлик для апостола или генерирует новый"""
    str_user_id = str(user_id)
    apostle = get_apostle_info(user_id)
    
    if apostle and 'emoji' in apostle and apostle['emoji']:
        return apostle['emoji']
    
    # Генерируем новый смайлик
    if apostle:
        # Проверяем, какие смайлики уже заняты
        used_emojis = set()
        for data in apostles_data.values():
            if 'emoji' in data and data['emoji']:
                used_emojis.add(data['emoji'])
        
        available_emojis = [e for e in APOSTLE_EMOJIS if e not in used_emojis]
        
        if available_emojis:
            emoji = random.choice(available_emojis)
        else:
            emoji = random.choice(APOSTLE_EMOJIS)  # Если все заняты
        
        apostle['emoji'] = emoji
        save_apostles()
        return emoji
    
    return "🦝"  # Дефолтный

# ================= ЗАГРУЗКА И СОХРАНЕНИЕ =================
def load_apostles():
    global apostles_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                apostles_data = json.load(f)
                logger.info(f"📂 Загружено {len(apostles_data)} апостолов")
                return True
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            apostles_data = {}
            return False
    else:
        logger.warning(f"⚠️ Файл {DATA_FILE} не найден, создаю новый")
        apostles_data = {}
        save_apostles()
        return True

def save_apostles():
    try:
        existing_data = {}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                existing_data = {}
        
        for user_id, data in apostles_data.items():
            if user_id in existing_data:
                existing_data[user_id].update(data)
            else:
                existing_data[user_id] = data
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Сохранено {len(existing_data)} апостолов")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")
        return False

# ================= БЛАГОСЛОВЕНИЯ =================
BASE_BLESSINGS = {
    "атаки": "BlessOfAttack",
    "защиты": "BlessOfDefense",
    "удачи": "BlessOfLuck"
}

RACE_BLESSINGS = {
    "человек": "BlessOfHuman",
    "эльф": "BlessOfElf",
    "орк": "BlessOfOrk",
    "гоблин": "BlessOfGoblin",
    "гном": "BlessOfGnome",
    "демон": "BlessOfDemon",
    "нежить": "BlessOfUndead"
}

RACE_TO_BLESSING = {
    "человек": "человека",
    "эльф": "эльфа",
    "орк": "орка",
    "гоблин": "гоблина",
    "гном": "гнома",
    "демон": "демона",
    "нежить": "нежити"
}

SHORTCUTS = {
    "а": "атаки",
    "з": "защиты",
    "у": "удачи",
    "ч": "человека",
    "э": "эльфа",
    "о": "орка",
    "г": "гоблина",
    "в": "гнома",
    "д": "демона",
    "н": "нежити"
}

ALL_BLESSINGS = {**BASE_BLESSINGS}
for race, bless in RACE_BLESSINGS.items():
    ALL_BLESSINGS[RACE_TO_BLESSING[race]] = bless

# ================= РАБОТА С АПОСТОЛАМИ =================
def get_apostle_info(user_id):
    return apostles_data.get(str(user_id))

def get_apostle_token(user_id):
    apostle = get_apostle_info(user_id)
    return apostle.get('token') if apostle else None

def is_apostle_active(user_id):
    apostle = get_apostle_info(user_id)
    return apostle.get('active', False) if apostle else False

def get_apostle_race(user_id):
    apostle = get_apostle_info(user_id)
    return apostle.get('race', '') if apostle else ''

def get_with_retry(url, max_retries=3, delay=5):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            data = response.json()
            if data.get('error', {}).get('code') == 'TOO_MANY_REQUESTS':
                logger.warning(f"⚠️ Лимит запросов, ждём {delay} сек")
                time.sleep(delay)
                continue
            return data
        except Exception as e:
            logger.error(f"Ошибка запроса: {e}")
            time.sleep(delay)
    return None

def get_cached_apostle_info(user_id, force=False):
    str_user_id = str(user_id)
    if str_user_id not in apostles_cache:
        apostles_cache[str_user_id] = {'data': None, 'last_update': 0}

    cache = apostles_cache[str_user_id]
    current_time = time.time()

    if not force and cache['data'] is not None and (current_time - cache['last_update']) < 60:
        return cache['data']

    token = get_apostle_token(user_id)
    if not token or not is_apostle_active(user_id):
        return None

    try:
        data = get_with_retry(f"{API_URL}GetCharacterInfo?token={token}")
        if data and data.get('result') == 1:
            info = data.get('info', {})
            cache['data'] = info
            cache['last_update'] = current_time

            apostle = get_apostle_info(user_id)
            if apostle:
                apostle['voices'] = info.get('voices', 0)
                apostle['level'] = info.get('level', 0)
                apostle['race'] = info.get('race', '')
                save_apostles()
            return info
        else:
            return cache['data']
    except Exception as e:
        return cache['data']

# ================= ДВЕ ФУНКЦИИ ДОСТУПНОСТИ =================
def get_available_blessings_for_target(user_id):
    """Для цели — все расы доступны"""
    available = list(BASE_BLESSINGS.keys())
    available.append("человека")
    available.append("эльфа")
    available.append("орка")
    available.append("гоблина")
    available.append("гнома")
    available.append("демона")
    available.append("нежити")
    return list(dict.fromkeys(available))

def get_available_blessings_for_apostle(apostle_id):
    """Для апостола — ТОЛЬКО его расы"""
    available = list(BASE_BLESSINGS.keys())
    
    apostle = get_apostle_info(apostle_id)
    if apostle:
        race_text = apostle.get('race', '')
        if race_text:
            if '-' in race_text:
                parts = race_text.split('-')
                for part in parts[:2]:
                    part = part.strip().lower()
                    if part in RACE_BLESSINGS:
                        blessing_name = RACE_TO_BLESSING.get(part)
                        if blessing_name:
                            available.append(blessing_name)
            else:
                race_text = race_text.strip().lower()
                if race_text in RACE_BLESSINGS:
                    blessing_name = RACE_TO_BLESSING.get(race_text)
                    if blessing_name:
                        available.append(blessing_name)
    
    return list(dict.fromkeys(available))

def send_to_mead(message):
    try:
        vk_session = vk_api.VkApi(token=TOKEN)
        vk = vk_session.get_api()
        vk.messages.send(
            user_id=MEAD_ID,
            message=message,
            random_id=random.randint(1, 1000000)
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False

def apply_blessing(user_id, blessing_type, apostle_user_id):
    token = get_apostle_token(apostle_user_id)
    if not token or not is_apostle_active(apostle_user_id):
        return False, f"❌ Апостол {apostle_user_id} не активен!"

    try:
        response = requests.post(
            API_URL + "ApplySocialEffectToPlayer",
            data={
                "token": token,
                "player_id": user_id,
                "type": blessing_type
            },
            timeout=10
        )
        data = response.json()

        apostle_info = get_apostle_info(apostle_user_id)
        apostle_name = apostle_info.get('name', f"Апостол_{apostle_user_id}") if apostle_info else f"Апостол_{apostle_user_id}"
        
        target_info = get_apostle_info(user_id)
        target_name = target_info.get('name', f"Пользователь_{user_id}") if target_info else f"Пользователь_{user_id}"

        if data.get('result') == 1:
            send_to_mead(f"✅ **{apostle_name}** наложил **{blessing_type}** на **{target_name}** (ID: {user_id})")
            return True, f"✅ {blessing_type} (от {apostle_user_id})"
        else:
            error = data.get('error', {})
            error_message = error.get('message', 'Ошибка')
            if "уже действует" in error_message or "already active" in error_message:
                return False, "уже действует"
            send_to_mead(f"❌ **{apostle_name}** НЕ смог наложить **{blessing_type}** на **{target_name}** (ID: {user_id})\nОшибка: {error_message}")
            return False, f"❌ {error_message}"
    except Exception as e:
        return False, f"❌ Ошибка: {e}"

def get_all_apostles_for_user(target_user_id):
    """Возвращает ВСЕХ активных апостолов"""
    active_apostles = []
    
    for str_user_id, data in apostles_data.items():
        if data.get('active', False):
            apostle_id = int(str_user_id)
            get_cached_apostle_info(apostle_id)
            voices = data.get('voices', 0) if data else 0
            
            active_apostles.append({
                'user_id': apostle_id,
                'voices': voices
            })
    
    return active_apostles

def get_prioritized_apostles_for_buff(target_user_id, blessing_name):
    """
    Возвращает список апостолов, отсортированных по приоритету:
    1. Сначала те, у кого голосов >= 10 (могут накладывать любые баффы)
    2. Потом те, у кого голосов < 10 (могут накладывать ТОЛЬКО расовые)
    """
    all_apostles = get_all_apostles_for_user(target_user_id)
    prioritized = []
    
    is_race_blessing = blessing_name in RACE_TO_BLESSING.values()
    
    for apostle in all_apostles:
        apostle_id = apostle['user_id']
        apostle_info = get_apostle_info(apostle_id)
        voices = apostle_info.get('voices', 0) if apostle_info else 0
        
        # Проверяем, может ли апостол наложить этот бафф
        apostle_available = get_available_blessings_for_apostle(apostle_id)
        if blessing_name not in apostle_available:
            continue
        
        # Проверка приоритета
        if voices >= 10:
            # Может накладывать любые баффы
            prioritized.append({
                'user_id': apostle_id,
                'voices': voices,
                'priority': 1,  # Высокий приоритет
                'can_use_any': True
            })
        elif is_race_blessing and voices > 0:
            # Может накладывать ТОЛЬКО расовые баффы (голосов < 10)
            prioritized.append({
                'user_id': apostle_id,
                'voices': voices,
                'priority': 2,  # Низкий приоритет
                'can_use_any': False
            })
        # Если голосов < 10 и это НЕ расовый бафф — пропускаем
    
    # Сортируем: сначала priority 1 (>=10 голосов), потом priority 2 (<10 голосов)
    # Внутри каждой группы — по убыванию голосов
    prioritized.sort(key=lambda x: (x['priority'], -x['voices']))
    
    return prioritized

# ================= ОБРАБОТКА ОЧЕРЕДИ =================
def process_buff_queue():
    while True:
        try:
            current_time = time.time()
            
            for str_user_id in list(buff_queue.keys()):
                user_id = int(str_user_id)
                queue_data = buff_queue[str_user_id]
                
                if queue_data['current_index'] >= len(queue_data['blessings']):
                    del buff_queue[str_user_id]
                    continue
                
                blessing_name = queue_data['blessings'][queue_data['current_index']]
                bless_type = ALL_BLESSINGS.get(blessing_name)
                
                if not bless_type:
                    queue_data['current_index'] += 1
                    continue
                
                # Получаем апостолов с приоритетом
                prioritized_apostles = get_prioritized_apostles_for_buff(user_id, blessing_name)
                
                if not prioritized_apostles:
                    queue_data['current_index'] += 1
                    queue_data['last_time'] = current_time
                    
                    # Проверяем, есть ли вообще апостолы с голосами
                    all_apostles = get_all_apostles_for_user(user_id)
                    has_voices = any(a.get('voices', 0) > 0 for a in all_apostles)
                    
                    if not has_voices:
                        send_to_mead(f"⏭️ {blessing_name} пропущен (нет апостолов с голосами)")
                    else:
                        send_to_mead(f"⏭️ {blessing_name} пропущен (нет подходящих апостолов)")
                    continue
                
                # Проверяем, есть ли свободный апостол
                free_apostle = None
                for apostle in prioritized_apostles:
                    apostle_id = apostle['user_id']
                    str_apostle_id = str(apostle_id)
                    
                    if str_apostle_id not in apostle_cooldowns or current_time - apostle_cooldowns[str_apostle_id] >= 60:
                        free_apostle = apostle
                        break
                
                if free_apostle:
                    # Есть свободный — накладываем
                    apostle_id = free_apostle['user_id']
                    str_apostle_id = str(apostle_id)
                    voices = free_apostle['voices']
                    
                    success, result = apply_blessing(user_id, bless_type, apostle_id)
                    
                    if success:
                        apostle_cooldowns[str_apostle_id] = time.time()
                        queue_data['current_index'] += 1
                        queue_data['last_time'] = current_time
                        
                        remaining = len(queue_data['blessings']) - queue_data['current_index']
                        send_to_mead(f"✅ {blessing_name} наложен апостолом {apostle_id} (голосов: {voices})! Осталось: {remaining}")
                    elif result and "уже действует" in str(result):
                        queue_data['current_index'] += 1
                        queue_data['last_time'] = current_time
                        send_to_mead(f"⏭️ {blessing_name} пропущен (уже действует)")
                    else:
                        queue_data['current_index'] += 1
                        queue_data['last_time'] = current_time
                        send_to_mead(f"⏭️ {blessing_name} пропущен (ошибка)")
                else:
                    # Нет свободных — ждём
                    min_wait = 60
                    for apostle in prioritized_apostles:
                        apostle_id = apostle['user_id']
                        str_apostle_id = str(apostle_id)
                        if str_apostle_id in apostle_cooldowns:
                            wait_time = 60 - (current_time - apostle_cooldowns[str_apostle_id])
                            if wait_time > 0:
                                min_wait = min(min_wait, wait_time)
                    
                    wait_time = min(min_wait, 60)
                    time.sleep(wait_time + 1)
                    send_to_mead(f"⏳ Ждём освобождения апостола для {blessing_name} ({int(wait_time)} сек)")
            
            time.sleep(2)
        except Exception as e:
            logger.error(f"Ошибка обработки очереди: {e}")
            time.sleep(10)

# ================= ФУНКЦИЯ ПАРСИНГА (сохраняет порядок) =================
def parse_blessings(text, available):
    text = text.lower().strip()
    for prefix in ['баф ', 'баф']:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    if not text:
        return []

    found = []
    
    # Проходим посимвольно — сохраняется порядок
    i = 0
    while i < len(text):
        matched = False
        
        # Сначала проверяем полные названия
        for name in available:
            if text[i:].startswith(name):
                if name not in found:
                    found.append(name)
                    i += len(name)
                    matched = True
                    break
        
        if not matched:
            # Проверяем сокращения
            for shortcut, name in SHORTCUTS.items():
                if text[i:].startswith(shortcut):
                    if name in available and name not in found:
                        found.append(name)
                        i += len(shortcut)
                        matched = True
                        break
        
        if not matched:
            i += 1
    
    # Fallback
    if not found:
        for char in text:
            if char in SHORTCUTS:
                shortcut_name = SHORTCUTS[char]
                if shortcut_name in available and shortcut_name not in found:
                    found.append(shortcut_name)
    
    return found

def send_reply_to_chat(vk, peer_id, message, reply_to=None):
    try:
        vk.messages.send(
            peer_id=peer_id,
            message=message,
            reply_to=reply_to,
            random_id=random.randint(1, 1000000)
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        return False

# ================= ОСНОВНОЙ БОТ =================
def main():
    check_lock()
    try:
        logger.info("=" * 50)
        logger.info("🤖 БОТ ВОПЛОЩЕНИЯ СВЕТА")
        logger.info("=" * 50)

        load_apostles()
        
        logger.info("🔄 Обновление данных апостолов...")
        for user_id in list(apostles_data.keys()):
            if apostles_data[user_id].get('active', False):
                try:
                    get_cached_apostle_info(int(user_id), force=True)
                except Exception as e:
                    logger.error(f"Ошибка обновления {user_id}: {e}")

        logger.info(f"📌 Всего апостолов: {len(apostles_data)}")
        active_count = sum(1 for a in apostles_data.values() if a.get('active', False))
        logger.info(f"📌 Активных: {active_count}")
        logger.info("=" * 50)

        vk_session = vk_api.VkApi(token=TOKEN)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID)

        queue_thread = threading.Thread(target=process_buff_queue, daemon=True)
        queue_thread.start()
        logger.info("📋 Запущен поток обработки очереди")

        send_to_mead("🦝 **Бот запущен!**\n\n"
                    "✅ В ЛС реагирует только на +апостол\n"
                    "✅ В чатах работает полноценно\n"
                    "✅ Апостолы с 0 голосов пропускаются\n"
                    "✅ Баффы накладываются в порядке ввода\n"
                    "✅ У каждого апостола свой уникальный смайлик")

        logger.info("✅ Бот запущен!")
        logger.info("📌 В ЛС — только команда +апостол")
        logger.info("📌 В чатах — все команды")
        logger.info("📌 Апостолы с 0 голосов НЕ накладывают баффы")
        logger.info("📌 Апостолы с <10 голосов — только расовые баффы")
        logger.info("📌 Апостолы с 10+ голосов — любые баффы")
        logger.info("📌 КД между баффами: 60 секунд")
        logger.info("=" * 50)

        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                try:
                    user_id = event.message.from_id
                    message_text = event.message.text
                    message_id = event.message.id
                    peer_id = event.message.peer_id
                    
                    msg = message_text.lower().strip()
                    
                    # 🔥 ОПРЕДЕЛЯЕМ: личка это или чат
                    is_private = (peer_id == user_id)
                    
                    if is_private:
                        logger.info(f"💬 Личное сообщение от {user_id}: '{msg}'")
                        
                        # 🔥 В ЛИЧКЕ РЕАГИРУЕМ ТОЛЬКО НА +АПОСТОЛ
                        if msg.startswith('+апостол'):
                            # Обрабатываем активацию апостола
                            parts = msg.split()
                            if len(parts) >= 2:
                                token = parts[1]
                                if token.startswith('wd1_live_'):
                                    str_user_id = str(user_id)
                                    
                                    apostles_data[str_user_id] = {
                                        'token': token,
                                        'active': True,
                                        'name': 'Апостол',
                                        'voices': 0,
                                        'level': 0,
                                        'race': '',
                                        'emoji': ''
                                    }
                                    save_apostles()
                                    if str_user_id in apostles_cache:
                                        del apostles_cache[str_user_id]

                                    try:
                                        check_response = get_with_retry(f"{API_URL}TokenInfo?token={token}")
                                        if check_response and check_response.get('result') == 1:
                                            get_cached_apostle_info(user_id, force=True)
                                            emoji = get_apostle_emoji(user_id)
                                            send_to_mead(f"🦝 **Апостол активирован для @id{user_id}!** Смайлик: {emoji}")
                                            send_reply_to_chat(vk, peer_id, f"✅ Апостол активирован! Твой смайлик: {emoji}", reply_to=message_id)
                                        else:
                                            apostles_data[str_user_id]['active'] = False
                                            save_apostles()
                                            send_reply_to_chat(vk, peer_id, "❌ Неверный токен!", reply_to=message_id)
                                    except Exception as e:
                                        apostles_data[str_user_id]['active'] = False
                                        save_apostles()
                                        send_reply_to_chat(vk, peer_id, f"❌ Ошибка: {e}", reply_to=message_id)
                                else:
                                    send_reply_to_chat(vk, peer_id,
                                                       "❌ Неверный формат токена! Должен начинаться с `wd1_live_`",
                                                       reply_to=message_id)
                            else:
                                send_reply_to_chat(vk, peer_id,
                                                   "❌ Укажи токен!\nПример: `+апостол wd1_live_...`",
                                                   reply_to=message_id)
                        else:
                            # 🔥 ВСЕ ОСТАЛЬНЫЕ СООБЩЕНИЯ В ЛИЧКЕ ИГНОРИРУЕМ
                            logger.info(f"💬 Личное сообщение от {user_id} проигнорировано (не +апостол)")
                            continue
                    else:
                        # 🔥 В ЧАТАХ РАБОТАЕМ ПОЛНОСТЬЮ
                        logger.info(f"💬 Получено: '{msg}' от {user_id} в чате {peer_id}")

                        available = get_available_blessings_for_target(user_id)

                        if msg.startswith('+апостол'):
                            parts = msg.split()
                            if len(parts) >= 2:
                                token = parts[1]
                                if token.startswith('wd1_live_'):
                                    str_user_id = str(user_id)
                                    
                                    apostles_data[str_user_id] = {
                                        'token': token,
                                        'active': True,
                                        'name': 'Апостол',
                                        'voices': 0,
                                        'level': 0,
                                        'race': '',
                                        'emoji': ''
                                    }
                                    save_apostles()
                                    if str_user_id in apostles_cache:
                                        del apostles_cache[str_user_id]

                                    try:
                                        check_response = get_with_retry(f"{API_URL}TokenInfo?token={token}")
                                        if check_response and check_response.get('result') == 1:
                                            get_cached_apostle_info(user_id, force=True)
                                            emoji = get_apostle_emoji(user_id)
                                            send_to_mead(f"🦝 **Апостол активирован для @id{user_id}!** Смайлик: {emoji}")
                                            send_reply_to_chat(vk, peer_id, f"✅ Апостол активирован! Твой смайлик: {emoji}", reply_to=message_id)
                                        else:
                                            apostles_data[str_user_id]['active'] = False
                                            save_apostles()
                                            send_reply_to_chat(vk, peer_id, "❌ Неверный токен!", reply_to=message_id)
                                    except Exception as e:
                                        apostles_data[str_user_id]['active'] = False
                                        save_apostles()
                                        send_reply_to_chat(vk, peer_id, f"❌ Ошибка: {e}", reply_to=message_id)
                                else:
                                    send_reply_to_chat(vk, peer_id,
                                                       "❌ Неверный формат токена! Должен начинаться с `wd1_live_`",
                                                       reply_to=message_id)
                            else:
                                send_reply_to_chat(vk, peer_id,
                                                   "❌ Укажи токен!\nПример: `+апостол wd1_live_...`",
                                                   reply_to=message_id)

                        elif msg == '-апостол':
                            str_user_id = str(user_id)
                            if str_user_id in apostles_data:
                                apostles_data[str_user_id]['active'] = False
                                save_apostles()
                                if str_user_id in apostles_cache:
                                    del apostles_cache[str_user_id]
                                send_to_mead(f"⛔ **Апостол @id{user_id} отключен!**")
                                send_reply_to_chat(vk, peer_id, "✅ Апостол отключён!", reply_to=message_id)
                            else:
                                send_reply_to_chat(vk, peer_id, "❌ У тебя нет активного апостола!", reply_to=message_id)

                        elif msg in ['голоса', 'голос']:
                            apostles_list = []
                            for str_user_id, data in apostles_data.items():
                                if data.get('active', False):
                                    user_id_int = int(str_user_id)
                                    info = get_cached_apostle_info(user_id_int, force=True)
                                    name = data.get('name', f"Апостол_{user_id_int}")
                                    voices = data.get('voices', 0)
                                    race_text = data.get('race', '')
                                    race_short = ""
                                    
                                    race_map = {
                                        "человек": "ч",
                                        "эльф": "э",
                                        "орк": "о",
                                        "гоблин": "г",
                                        "гном": "в",
                                        "демон": "д",
                                        "нежить": "н"
                                    }
                                    
                                    if race_text:
                                        parts = race_text.split('-')
                                        short_parts = []
                                        for part in parts[:2]:
                                            part = part.strip().lower()
                                            if part in race_map:
                                                short_parts.append(race_map[part])
                                        race_short = "/".join(short_parts) if short_parts else race_text
                                    
                                    emoji = get_apostle_emoji(user_id_int)
                                    apostles_list.append(f"{emoji} {race_short}/{name} {voices}")
                            
                            if apostles_list:
                                response = "🔊 **Голоса:**\n\n" + "\n".join(apostles_list)
                            else:
                                response = "❌ Нет активных апостолов!"
                            send_reply_to_chat(vk, peer_id, response, reply_to=message_id)

                        elif msg.startswith('баф'):
                            blessings = parse_blessings(msg, available)
                            
                            if not blessings:
                                send_reply_to_chat(
                                    vk, peer_id,
                                    f"❌ Не найдены благословения!\nДоступны: {', '.join(available)}",
                                    reply_to=message_id
                                )
                                continue

                            str_user_id = str(user_id)
                            if str_user_id not in buff_queue:
                                buff_queue[str_user_id] = {
                                    'blessings': blessings,
                                    'current_index': 0,
                                    'last_time': 0
                                }
                            else:
                                buff_queue[str_user_id]['blessings'].extend(blessings)

                            queue_count = len(buff_queue[str_user_id]['blessings']) - buff_queue[str_user_id]['current_index']
                            
                            low_voice_blessings = []
                            high_voice_blessings = []
                            
                            for blessing in blessings:
                                has_low = False
                                has_high = False
                                for apostle_id, data in apostles_data.items():
                                    if data.get('active', False):
                                        voices = data.get('voices', 0)
                                        apostle_available = get_available_blessings_for_apostle(int(apostle_id))
                                        if blessing in apostle_available:
                                            if voices >= 10:
                                                has_high = True
                                            elif voices > 0:
                                                has_low = True
                                
                                if has_low and not has_high:
                                    low_voice_blessings.append(blessing)
                                elif has_high:
                                    high_voice_blessings.append(blessing)
                            
                            warning = ""
                            if low_voice_blessings:
                                warning = f"\n⚠️ {', '.join(low_voice_blessings)} — только через апостолов с <10 голосов"
                            
                            send_reply_to_chat(
                                vk, peer_id,
                                f"📋 **Благословения добавлены в очередь!**\n"
                                f"📌 {', '.join(blessings)}\n"
                                f"⏳ Всего в очереди: {queue_count}{warning}",
                                reply_to=message_id
                            )

                        elif msg in ['бот', 'помощь', 'help', '/help']:
                            help_text = (
                                "⚔️ **Команды:**\n\n"
                                "📩 `+апостол [токен]` — активировать апостола\n"
                                "⛔ `-апостол` — отключить апостола\n"
                                "🔊 `голоса` — список апостолов\n\n"
                                "🔥 **Приоритет баффов:**\n"
                                "• 10+ голосов — могут накладывать ЛЮБЫЕ баффы\n"
                                "• 1-9 голосов — могут накладывать ТОЛЬКО РАСОВЫЕ баффы\n"
                                "• 0 голосов — НЕ работают\n\n"
                                "📋 **Команды баффов:**\n"
                                "• `баф а` — атака\n"
                                "• `баф з` — защита\n"
                                "• `баф у` — удача\n"
                                "• `баф ч` — человек\n"
                                "• `баф э` — эльф\n"
                                "• `баф о` — орк\n"
                                "• `баф г` — гоблин\n"
                                "• `баф в` — гном\n"
                                "• `баф д` — демон\n"
                                "• `баф н` — нежить\n\n"
                                "📋 **Примеры:**\n"
                                "• `баф уаз` — удача, атака, защита (в этом порядке)\n"
                                "• `баф уазэ` — удача, атака, защита, эльф (в этом порядке)\n\n"
                                "💡 Апостолы с <10 голосов используют только расовые баффы!\n"
                                "🎯 У каждого апостола свой уникальный смайлик!"
                            )
                            send_reply_to_chat(vk, peer_id, help_text, reply_to=message_id)

                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        save_apostles()
        remove_lock()

atexit.register(save_apostles)

if __name__ == "__main__":
    main()
