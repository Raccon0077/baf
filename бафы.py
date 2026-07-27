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

# ================= НАСТРОЙКА =================
DATA_DIR = os.environ.get('DATA_DIR', '/app/data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, "apostles_data.json")
LOCK_FILE = os.path.join(DATA_DIR, "bot.lock")

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


# ================= РАБОТА С ФАЙЛОМ =================
def load_apostles():
    """Загружает данные апостолов из файла"""
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
        apostles_data = {}
        save_apostles()
        logger.info("📂 Создан новый файл данных")
        return True


def save_apostles():
    """Сохраняет данные апостолов в файл (обновляет, не удаляя)"""
    try:
        # Загружаем существующие данные
        existing_data = {}
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            except:
                existing_data = {}
        
        # Обновляем данные, не удаляя существующие
        for user_id, data in apostles_data.items():
            if user_id in existing_data:
                # Обновляем существующего апостола
                existing_data[user_id].update(data)
            else:
                # Добавляем нового апостола
                existing_data[user_id] = data
        
        # Сохраняем
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 Сохранено {len(existing_data)} апостолов")
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения данных: {e}")
        return False


def update_apostle_data(user_id, new_data):
    """Обновляет данные апостола, не удаляя существующие"""
    str_user_id = str(user_id)
    
    # Загружаем текущие данные
    load_apostles()
    
    if str_user_id not in apostles_data:
        apostles_data[str_user_id] = {}
    
    # Обновляем только переданные поля
    for key, value in new_data.items():
        apostles_data[str_user_id][key] = value
    
    save_apostles()
    logger.info(f"🔄 Обновлены данные для {user_id}")


def clean_inactive_apostles():
    """Удаляет только тех апостолов, у которых active = False"""
    load_apostles()
    inactive = [uid for uid, data in apostles_data.items() if not data.get('active', False)]
    
    if inactive:
        for uid in inactive:
            del apostles_data[uid]
        save_apostles()
        logger.info(f"🗑️ Удалено {len(inactive)} неактивных апостолов")
    else:
        logger.info("✅ Нет неактивных апостолов для удаления")


# ================= УМНАЯ ОЧИСТКА ПАМЯТИ =================
def memory_cleaner():
    """Умная очистка памяти — только при перегрузке"""
    while True:
        try:
            # 1. Проверяем размер кэша
            cache_size = len(apostles_cache)
            if cache_size > 20:
                sorted_keys = sorted(apostles_cache.keys(),
                                   key=lambda x: apostles_cache[x]['last_update'])
                for key in sorted_keys[:-10]:
                    del apostles_cache[key]
                logger.info(f"🧹 Очищен кэш: было {cache_size}, стало {len(apostles_cache)}")

            # 2. Очищаем неактивных апостолов (только если их много)
            clean_inactive_apostles()

            # 3. Проверяем сборку мусора
            gc_count = gc.get_count()
            if gc_count[0] > 700:
                collected = gc.collect()
                if collected > 0:
                    logger.info(f"🧹 Собрано мусора: {collected} объектов")

            time.sleep(30)

        except Exception as e:
            logger.error(f"❌ Ошибка очистки памяти: {e}")
            time.sleep(60)


# ================= АВТО-СООБЩЕНИЕ =================
def send_alive_message(vk):
    try:
        minutes = random.randint(10, 30)
        message = (
            "🦝 **Бот жив!**\n\n"
            f"✅ Следующее сообщение через {minutes} минут\n"
            "🔥 Бафы можно брать!\n\n"
            "📋 Команды:\n"
            "• `баф [буквы]` — наложить благословения\n"
            "• `голоса` — список всех активных апостолов\n"
            "• `+апостол [токен]` — активировать апостола\n"
            "• `-апостол` — отключить апостола"
        )

        vk.messages.send(
            user_id=MEAD_ID,
            message=message,
            random_id=random.randint(1, 1000000)
        )
        logger.info(f"📩 Отправлено сообщение Екатерине (следующее через {minutes} мин)")
        return minutes * 60
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")
        return 600


# ================= КОНФИГУРАЦИЯ =================
TOKEN_MEDEA = "vk1.a.pWAMTUhJkodcMkUFpCa-UMg_6DKXwr6ISV863itpGw410z1RVSyawnce0r8wMMho0eD5rtIVnrITM22tQbnuqGtnJBZfH5FLopBeT33UG0AUbJI_cEJVbcJEAvOs34dt3PfAA0yiL0sjgabDA88ll9GRCB2nyxiywcI5286nSS-Db2Rn5AAzgp3nkzXfWzkLc4Xf-_vPgUu7pMVJc490Vw"
GROUP_ID_MEDEA = 239699656

MEAD_ID = 212887447

API_URL = "https://welldungeon.online/api/v1/"

# ================= ХРАНИЛИЩЕ =================
apostles_data = {}
apostles_cache = {}
apostle_cooldowns = {}
buff_queue = {}

CACHE_TTL = 10


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


# ================= ОСТАЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) =================
# ... (все функции get_apostle_info, get_apostle_token, etc остаются теми же)

# ================= ОСНОВНОЙ БОТ =================
def main():
    check_lock()
    try:
        logger.info("=" * 50)
        logger.info("🤖 БОТ ВОПЛОЩЕНИЯ СВЕТА")
        logger.info("=" * 50)

        # Загружаем данные
        load_apostles()
        
        logger.info("🔄 Обновление данных всех апостолов...")
        for user_id in list(apostles_data.keys()):
            if apostles_data[user_id].get('active', False):
                try:
                    get_cached_apostle_info(int(user_id), force=True)
                except Exception as e:
                    logger.error(f"   ❌ Ошибка обновления {user_id}: {e}")

        logger.info(f"📌 Всего апостолов в базе: {len(apostles_data)}")
        active_count = sum(1 for a in apostles_data.values() if a.get('active', False))
        logger.info(f"📌 Активных: {active_count}")
        logger.info("=" * 50)

        vk_session = vk_api.VkApi(token=TOKEN_MEDEA)
        vk = vk_session.get_api()
        longpoll = VkBotLongPoll(vk_session, GROUP_ID_MEDEA)

        # Запускаем очистку памяти
        memory_thread = threading.Thread(target=memory_cleaner, daemon=True)
        memory_thread.start()
        logger.info("🧹 Запущена умная очистка памяти")

        # Запускаем авт-сообщения
        def alive_message_loop():
            while True:
                try:
                    wait_time = send_alive_message(vk)
                    time.sleep(wait_time)
                except Exception as e:
                    logger.error(f"❌ Ошибка в цикле alive-сообщений: {e}")
                    time.sleep(600)

        alive_thread = threading.Thread(target=alive_message_loop, daemon=True)
        alive_thread.start()
        logger.info("✅ Запущен поток авт-сообщений Екатерине (каждые 10-30 минут)")

        logger.info("✅ Бот запущен!")
        logger.info("📌 Команды:")
        logger.info("   • +апостол [токен] — активировать апостола")
        logger.info("   • -апостол — отключить апостола")
        logger.info("   • голоса — список всех активных апостолов")
        logger.info("   • баф [буквы] — наложить благословения")
        logger.info("=" * 50)

        # Обработка команд
        for event in longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW:
                try:
                    user_id = event.message.from_id
                    message_text = event.message.text
                    message_id = event.message.id
                    peer_id = event.message.peer_id
                    msg = message_text.lower().strip()

                    # ... (весь обработчик команд остаётся без изменений)

                except Exception as e:
                    logger.error(f"❌ Ошибка: {e}")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        remove_lock()


if __name__ == "__main__":
    main()
