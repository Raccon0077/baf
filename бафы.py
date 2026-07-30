import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
import random
import time
import threading
import requests
import json
import os
import sys
import gc
import logging
import atexit

# ================= КОНФИГУРАЦИЯ =================
DATA_FILE = "apostles_data.json"
LOCK_FILE = "bot.lock"
MEAD_ID = 212887447  # Екатерина Наумова (получает отчёты)

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

# ================= КОНФИГУРАЦИЯ БОТА =================
TOKEN_MEDEA = "vk1.a.pWAMTUhJkodcMkUFpCa-UMg_6DKXwr6ISV863itpGw410z1RVSyawnce0r8wMMho0eD5rtIVnrITM22tQbnuqGtnJBZfH5FLopBeT33UG0AUbJI_cEJVbcJEAvOs34dt3PfAA0yiL0sjgabDA88ll9GRCB2nyxiywcI5286nSS-Db2Rn5AAzgp3nkzXfWzkLc4Xf-_vPgUu7pMVJc490Vw"
GROUP_ID_MEDEA = 239699656
API_URL = "https://welldungeon.online/api/v1/"
MAX_CACHE_SIZE = 20
CACHE_TTL = 10
MAX_RETRIES = 3
RETRY_DELAY = 5

# ================= ХРАНИЛИЩЕ =================
apostles_data = {}
apostles_cache = {}
apostle_cooldowns = {}
buff_queue = {}

# ================= ЗАГРУЗКА И СОХРАНЕНИЕ =================
def load_apostles():
    global apostles_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                apostles_data = json.load(f)
                # 🔥 УДАЛЯЕМ ЕКАТЕРИНУ ИЗ АПОСТОЛОВ
                if "212887447" in apostles_data:
                    del apostles_data["212887447"]
                    save_apostles()
                    logger.info("🗑️ Екатерина Наумова удалена из списка апостолов")
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
        logger.info(f"💾 Сохранение {len(apostles_data)} апостолов...")
        
        existing_data = {}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    logger.info(f"   📂 В файле уже {len(existing_data)} апостолов")
            except Exception as e:
                logger.error(f"   ❌ Ошибка чтения файла: {e}")
                existing_data = {}
        
        # 🔥 УДАЛЯЕМ ЕКАТЕРИНУ ПРИ СОХРАНЕНИИ
        if "212887447" in existing_data:
            del existing_data["212887447"]
        
        for user_id, data in apostles_data.items():
            if user_id in existing_data:
                existing_data[user_id].update(data)
                logger.info(f"   📝 Обновлён {user_id}")
            else:
                existing_data[user_id] = data
                logger.info(f"   ➕ Добавлен {user_id}")
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Сохранено {len(existing_data)} апостолов")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")
        import traceback
        traceback.print_exc()
        return False

def clean_inactive_apostles():
    load_apostles()
    inactive = [uid for uid, data in apostles_data.items() if not data.get('active', False)]
    if inactive:
        for uid in inactive:
            del apostles_data[uid]
        save_apostles()
        logger.info(f"🗑️ Удалено {len(inactive)} неактивных апостолов")
    else:
        logger.info("✅ Нет неактивных апостолов для удаления")

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

def get_apostle_races(user_id, limit=2):
    race_text = get_apostle_race(user_id)
    if not race_text:
        return []
    if '-' in race_text:
        parts = race_text.split('-')
        return [part.strip().lower() for part in parts[:limit] if part.strip().lower() in RACE_BLESSINGS]
    else:
        race_text = race_text.strip().lower()
        return [race_text] if race_text in RACE_BLESSINGS else []

def get_name_from_vk(vk_id):
    try:
        vk_session = vk_api.VkApi(token=TOKEN_MEDEA)
        vk = vk_session.get_api()
        users = vk.users.get(user_ids=[vk_id])
        if users:
            name = f"{users[0].get('first_name', '')} {users[0].get('last_name', '')}"
            return name.strip() or f"Апостол_{vk_id}"
        return f"Апостол_{vk_id}"
    except Exception as e:
        logger.error(f"Ошибка получения имени из ВК: {e}")
        return f"Апостол_{vk_id}"

def get_with_retry(url, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
            data = response.json()
            if data.get('error', {}).get('code') == 'TOO_MANY_REQUESTS':
                logger.warning(f"⚠️ Лимит запросов, попытка {attempt+1}/{max_retries}, ждём {delay} сек")
                time.sleep(delay)
                continue
            return data
        except Exception as e:
            logger.error(f"Ошибка запроса (попытка {attempt+1}): {e}")
            time.sleep(delay)
    return None

def get_cached_apostle_info(user_id, force=False):
    str_user_id = str(user_id)
    if str_user_id not in apostles_cache:
        apostles_cache[str_user_id] = {'data': None, 'last_update': 0}

    cache = apostles_cache[str_user_id]
    current_time = time.time()

    if not force and cache['data'] is not None and (current_time - cache['last_update']) < CACHE_TTL:
        return cache['data']

    if len(apostles_cache) > MAX_CACHE_SIZE:
        oldest = min(apostles_cache.keys(), key=lambda x: apostles_cache[x]['last_update'])
        del apostles_cache[oldest]
        logger.info(f"🧹 Удалён старый кэш для {oldest}")

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
                vk_id = info.get('vk_id')
                real_name = get_name_from_vk(vk_id) if vk_id else f"Апостол_{user_id}"
                apostle['name'] = real_name
                apostle['voices'] = info.get('voices', 0)
                apostle['level'] = info.get('level', 0)
                apostle['race'] = info.get('race', '')
                save_apostles()
                logger.info(f"🔄 Обновлён {real_name}: голоса {apostle['voices']}")
            return info
        else:
            if data and data.get('error', {}).get('code') == 'TOO_MANY_REQUESTS':
                logger.warning("⚠️ Превышен лимит запросов, данные не обновлены")
            return cache['data']
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
        return cache['data']

def get_all_apostles_display():
    result = []
    for str_user_id, data in apostles_data.items():
        if data.get('active', False):
            user_id_int = int(str_user_id)
            get_cached_apostle_info(user_id_int, force=True)

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

            result.append(f"🦝 {race_short} {name} {voices}")
    return result

def get_available_blessings(user_id):
    available = list(BASE_BLESSINGS.keys())

    apostle = get_apostle_info(user_id)
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

# ================= ОТПРАВКА В ЛИЧКУ (ТОЛЬКО ЕКАТЕРИНЕ) =================
def send_to_mead(message):
    try:
        vk_session = vk_api.VkApi(token=TOKEN_MEDEA)
        vk = vk_session.get_api()
        vk.messages.send(
            user_id=MEAD_ID,
            message=message,
            random_id=random.randint(1, 1000000)
        )
        logger.info(f"📩 Отправлено Екатерине")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки Екатерине: {e}")
        return False

# ================= ФУНКЦИЯ НАЛОЖЕНИЯ =================
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

def get_sorted_apostles_for_user(target_user_id):
    active_apostles = []
    current_time = time.time()

    for str_user_id, data in apostles_data.items():
        if data.get('active', False):
            apostle_id = int(str_user_id)
            get_cached_apostle_info(apostle_id, force=True)
            voices = data.get('voices', 0) if data else 0

            is_on_cooldown = False
            if str_user_id in apostle_cooldowns:
                if current_time - apostle_cooldowns[str_user_id] < 60:
                    is_on_cooldown = True

            active_apostles.append({
                'user_id': apostle_id,
                'voices': voices,
                'is_on_cooldown': is_on_cooldown,
                'cooldown_end': apostle_cooldowns.get(str_user_id, 0)
            })

    active_apostles.sort(key=lambda x: (x['is_on_cooldown'], -x['voices']))
    return active_apostles

# ================= ОСНОВНАЯ ЛОГИКА ОЧЕРЕДИ =================
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
                
                if current_time - queue_data['last_time'] < 60:
                    continue
                
                blessing_name = queue_data['blessings'][queue_data['current_index']]
                bless_type = ALL_BLESSINGS.get(blessing_name)
                
                if not bless_type:
                    queue_data['current_index'] += 1
                    continue
                
                sorted_apostles = get_sorted_apostles_for_user(user_id)
                
                if not sorted_apostles:
                    send_to_mead(f"⚠️ Нет активных апостолов для наложения {blessing_name}")
                    queue_data['current_index'] += 1
                    queue_data['last_time'] = current_time
                    continue
                
                apostle = sorted_apostles[0]
                apostle_id = apostle['user_id']
                str_apostle_id = str(apostle_id)
                
                if str_apostle_id in apostle_cooldowns:
                    if current_time - apostle_cooldowns[str_apostle_id] < 60:
                        for ap in sorted_apostles:
                            ap_id = ap['user_id']
                            str_ap_id = str(ap_id)
                            if str_ap_id not in apostle_cooldowns or current_time - apostle_cooldowns[str_ap_id] >= 60:
                                apostle = ap
                                apostle_id = ap_id
                                str_apostle_id = str_ap_id
                                break
                        else:
                            queue_data['last_time'] = current_time
                            send_to_mead(f"⏳ Все апостолы на КД, ждём...")
                            continue
                
                success, result = apply_blessing(user_id, bless_type, apostle_id)
                
                if success:
                    apostle_cooldowns[str_apostle_id] = time.time()
                    queue_data['current_index'] += 1
                    queue_data['last_time'] = current_time
                    remaining = len(queue_data['blessings']) - queue_data['current_index']
                    send_to_mead(f"✅ {blessing_name} наложен апостолом {apostle_id}! Осталось: {remaining}")
                elif result and "уже действует" in str(result):
                    queue_data['current_index'] += 1
                    queue_data['last_time'] = current_time
                    send_to_mead(f"⏭️ {blessing_name} пропущен (уже действует)")
                else:
                    found = False
                    for ap in sorted_apostles:
                        if ap['user_id'] == apostle_id:
                            continue
                        ap_id = ap['user_id']
                        str_ap_id = str(ap_id)
                        
                        if str_ap_id in apostle_cooldowns:
                            if current_time - apostle_cooldowns[str_ap_id] < 60:
                                continue
                        
                        success2, result2 = apply_blessing(user_id, bless_type, ap_id)
                        if success2:
                            apostle_cooldowns[str_ap_id] = time.time()
                            queue_data['current_index'] += 1
                            queue_data['last_time'] = current_time
                            remaining = len(queue_data['blessings']) - queue_data['current_index']
                            send_to_mead(f"✅ {blessing_name} наложен апостолом {ap_id}! Осталось: {remaining}")
                            found = True
                            break
                    
                    if not found:
                        queue_data['current_index'] += 1
                        queue_data['last_time'] = current_time
                        send_to_mead(f"⏭️ {blessing_name} пропущен (не удалось наложить)")
            
            time.sleep(2)
        except Exception as e:
            logger.error(f"Ошибка обработки очереди: {e}")
            time.sleep(10)

def parse_blessings(text, available):
    text = text.lower().strip()
    for prefix in ['баф ', 'баф']:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    if not text:
        return []

    found = []
    remaining = text

    for name in available:
        if name in remaining:
            found.append(name)
            remaining = remaining.replace(name, '').strip()

    for shortcut, name in sorted(SHORTCUTS.items(), key=lambda x: -len(x[0])):
        if shortcut in remaining:
            if name in available and name not in found:
                found.append(name)
                remaining = remaining.replace(shortcut, '').strip()

    if not found:
        for char in text:
            if char in SHORTCUTS:
                shortcut_name = SHORTCUTS[char]
                if shortcut_name in available and shortcut_name not in found:
                    found.append(shortcut_name)

    return list(dict.fromkeys(found))

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
        logger.error(f"[МЕДЕЯ] ❌ {e}")
        return False

# ================= АВТО-ОЧИСТКА =================
def memory_cleaner():
    while True:
        try:
            if len(apostles_cache) > MAX_CACHE_SIZE:
                sorted_keys = sorted(apostles_cache.keys(),
                                   key=lambda x: apostles_cache[x]['last_update'])
                for key in sorted_keys[:-10]:
                    del apostles_cache[key]
                logger.info(f"🧹 Очищен кэш: стало {len(apostles_cache)}")

            clean_inactive_apostles()

            gc_count = gc.get_count()
            if gc_count[0] > 700:
                collected = gc.collect()
                if collected > 0:
                    logger.info(f"🧹 Собрано мусора: {collected} объектов")

            time.sleep(30)
        except Exception as e:
            logger.error(f"Ошибка очистки: {e}")
            time.sleep(60)

# ================= АВТО-СООБЩЕНИЕ (2-4 ЧАСА) =================
def send_alive_message():
    try:
        hours = random.randint(2, 4)
        minutes = hours * 60
        
        message = (
            "🦝 **Бот жив!**\n\n"
            f"✅ Следующее сообщение через {hours} часа(ов)\n"
            "🔥 Бафы можно брать!\n\n"
            "📋 Команды:\n"
            "• `баф [буквы]` — наложить благословения\n"
            "• `голоса` — список всех активных апостолов\n"
            "• `+апостол [токен]` — активировать апостола\n"
            "• `-апостол` — отключить апостола"
        )
        send_to_mead(message)
        return minutes * 60  # в секундах
    except Exception as e:
        logger.error(f"Ошибка отправки alive-сообщения: {e}")
        return 7200  # 2 часа по умолчанию

def alive_message_loop():
    while True:
        try:
            wait_time = send_alive_message()
            time.sleep(wait_time)
        except Exception as e:
            logger.error(f"Ошибка в цикле alive-сообщений: {e}")
            time.sleep(7200)

# ================= ОСНОВНОЙ БОТ =================
def main():
    check_lock()
    try:
        logger.info("=" * 50)
        logger.info("🤖 БОТ ВОПЛОЩЕНИЯ СВЕТА")
        logger.info("=" * 50)

        load_apostles()
        
        logger.info("🔄 Принудительное обновление данных всех апостолов...")
        for user_id in list(apostles_data.keys()):
            if apostles_data[user_id].get('active', False):
                try:
                    get_cached_apostle_info(int(user_id), force=True)
                    logger.info(f"   ✅ Обновлён апостол {user_id}")
                except Exception as e:
                    logger.error(f"   ❌ Ошибка обновления {user_id}: {e}")

        logger.info(f"📌 Всего апостолов в базе: {len(apostles_data)}")
        active_count = sum(1 for a in apostles_data.values() if a.get('active', False))
        logger.info(f"📌 Активных: {active_count}")
        logger.info("=" * 50)

        vk_session = vk_api.VkApi(token=TOKEN_MEDEA)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID_MEDEA)

        memory_thread = threading.Thread(target=memory_cleaner, daemon=True)
        memory_thread.start()
        logger.info("🧹 Запущена умная очистка памяти")

        queue_thread = threading.Thread(target=process_buff_queue, daemon=True)
        queue_thread.start()
        logger.info("📋 Запущен поток автоматической обработки очереди баффов")

        alive_thread = threading.Thread(target=alive_message_loop, daemon=True)
        alive_thread.start()
        logger.info("✅ Запущен поток авт-сообщений Екатерине (каждые 2-4 часа)")

        logger.info("✅ Бот запущен!")
        logger.info("📌 Команды:")
        logger.info("   • +апостол [токен] — активировать апостола")
        logger.info("   • -апостол — отключить апостола")
        logger.info("   • голоса — список всех активных апостолов")
        logger.info("   • баф [буквы] — наложить благословения")
        logger.info("📩 Отчёты о баффах приходят только Екатерине Наумовой")
        logger.info("💾 Данные сохраняются в файл apostles_data.json")
        logger.info("=" * 50)

        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                try:
                    user_id = event.message.from_id
                    message_text = event.message.text
                    message_id = event.message.id
                    peer_id = event.message.peer_id
                    msg = message_text.lower().strip()

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
                                    'race': ''
                                }
                                save_apostles()
                                if str_user_id in apostles_cache:
                                    del apostles_cache[str_user_id]

                                try:
                                    check_response = get_with_retry(f"{API_URL}TokenInfo?token={token}")
                                    if check_response and check_response.get('result') == 1:
                                        get_cached_apostle_info(user_id, force=True)
                                        send_to_mead(f"🦝 **Апостол успешно активирован для @id{user_id}!")
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
                                                   "❌ Неверный формат токена! Токен должен начинаться с `wd1_live_`",
                                                   reply_to=message_id)
                        else:
                            send_reply_to_chat(vk, peer_id,
                                               "❌ Укажи токен после команды!\nПример: `+апостол wd1_live_...`",
                                               reply_to=message_id)

                    elif msg == '-апостол':
                        str_user_id = str(user_id)
                        if str_user_id in apostles_data:
                            apostles_data[str_user_id]['active'] = False
                            save_apostles()
                            if str_user_id in apostles_cache:
                                del apostles_cache[str_user_id]
                            send_to_mead(f"⛔ **Апостол @id{user_id} отключен!**")
                        else:
                            send_reply_to_chat(vk, peer_id, "❌ У тебя нет активного апостола!", reply_to=message_id)

                    elif msg in ['голоса', 'голос']:
                        apostles_list = get_all_apostles_display()
                        if apostles_list:
                            response = "🔊 **Голоса:**\n\n" + "\n".join(apostles_list)
                        else:
                            response = "❌ Нет активных апостолов!"
                        send_reply_to_chat(vk, peer_id, response, reply_to=message_id)

                    elif msg.startswith('баф'):
                        available = get_available_blessings(user_id)
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
                        send_reply_to_chat(
                            vk, peer_id,
                            f"📋 **Благословения добавлены в очередь!**\n"
                            f"📌 {', '.join(blessings)}\n"
                            f"⏳ Всего в очереди: {queue_count}",
                            reply_to=message_id
                        )

                    elif msg in ['бот', 'помощь', 'help', '/help']:
                        help_text = (
                            "⚔️ **Команды Воплощения Света**\n\n"
                            "📩 `+апостол [токен]` — активировать апостола\n"
                            "   🔑 Токен должен начинаться с `wd1_live_`\n"
                            "⛔ `-апостол` — отключить апостола\n"
                            "🔊 `голоса` — список всех активных апостолов\n\n"
                            "🔥 **Баффы (автоматическая очередь, КД 60 сек):**\n"
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
                            "• `баф уаз` — удача, атака, защита\n"
                            "• `баф ауэ` — атака, удача, эльф\n"
                            "• `баф уазэ` — удача, атака, защита, эльф\n\n"
                            "⏳ КД между баффами: 60 секунд\n"
                            "🔄 Баффы накладываются автоматически по очереди"
                        )
                        send_reply_to_chat(vk, peer_id, help_text, reply_to=message_id)

                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        save_apostles()
        remove_lock()

# Регистрируем автосохранение
atexit.register(save_apostles)

if __name__ == "__main__":
    main()
