import re
import subprocess
import json
import time
import threading
import os

# === Настройки ===


SCAN_RADIUS = 80
REQUIRED_LOGS = 3
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# === Запуск Node.js бота с указанием кодировки ===
node_process = subprocess.Popen(
    ['node', os.path.join(project_root, "BOT", "bot_controller.js")],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding='utf-8',
    errors='replace'
)


USER_FOLDER = os.path.join(project_root, "UI-AI", "user_data")
DEFAULT_USER_DATA = {
    "bot_on": False,
    "server_ip": "localhost",
    "port": "25565",
    "max_messages": 25,
    "chat_history": []
}

def get_user_file(username):
    return os.path.join(USER_FOLDER, f'{username}.json')


def load_user_data(username):
    path = get_user_file(username)
    if not os.path.exists(path):
        save_user_data(username, DEFAULT_USER_DATA.copy())
    with open(path, 'r') as f:
        data = json.load(f)
    max_msgs = data.get("max_messages", 25)
    data["chat_history"] = data["chat_history"][-max_msgs:]
    return data


def save_user_data(username, data):
    max_msgs = data.get("max_messages", 25)
    data["chat_history"] = data["chat_history"][-max_msgs:]

    path = get_user_file(username)
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)


def add_message_to_chat(username, message):
    user_data = load_user_data(username)
    # Просто добавляем обычную строку — json сам всё закодирует
    user_data["chat_history"].append(message)
    save_user_data(username, user_data)

# === Чтение ошибок ===
def read_stderr():
    for line in node_process.stderr:
        print(f"[JS Error] {line.strip()}")


threading.Thread(target=read_stderr, daemon=True).start()



# === Ожидание спавна бота ===
def wait_for_spawn():
    while True:
        line = node_process.stdout.readline()
        line = line.strip()
        if "Бот заспавнился" in line:
            print("[Python] Бот успешно загрузился")
            return True


# === Отправка команд ===
def send_command(cmd):
    print(f"[Python] Отправляем команду: {cmd}")
    node_process.stdin.write(cmd + '\n')
    node_process.stdin.flush()


# === Чтение событий и данных ===
def read_output(timeout=10):
    """
    Читает вывод из stdout и возвращает:
    - "goal_reached"
    - "digging_completed"
    - "look_finished"
    - "look_at_complete"
    - ("message", username:message)
    - {"type": "data", "content": data}
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        line = node_process.stdout.readline()
        if not line:
            time.sleep(0.1)
            continue

        line = line.strip()

        if line.startswith("EVENT"):
            parts = line.split()
            event_type = parts[1]

            if event_type == "goal_reached":
                return "goal_reached"
            elif event_type == "digging_completed":
                return "digging_completed"
            elif event_type == "look_finished":
                return "look_finished"
            elif event_type == "look_at_complete":
                return "look_at_complete"
            elif event_type == "digging":
                return "digging"
            elif event_type == "message":
                try:
                    user = parts[2]
                    msg=" ".join(parts[3:])
                    return ("message", user, msg)
                except Exception as e:
                    print("[Ошибка парсинга сообщения]", e)
                    return ("message", "unknown", parts[2:])

        elif line == "CACHE_UPDATE":
            try:
                data_line = node_process.stdout.readline().strip()
                data = json.loads(data_line)
                print("[Python] Получены данные о мире и позиции")
                return {"type": "data", "content": data}
            except Exception as e:
                print("[Ошибка парсинга данных]", e)

        elif line.startswith("ERROR"):
            print(f"[JS Error] {line}")

    print("[read_output] Таймаут ожидания события")
    return None

def read_cache_update():
    print("[Python] Ожидаем обновление кеша...")
    while True:
        line = node_process.stdout.readline()
        if not line:
            continue
        line = line.strip()
        if line == "CACHE_UPDATE":
            data_line = node_process.stdout.readline().strip()
            try:
                data = json.loads(data_line)
                print(f"[Python] Получен кеш: {len(data['cache'])} блоков")
                return data
            except Exception as e:
                print("[Ошибка парсинга кеша]", e)



# === Ждём завершения осмотра ===
def look_finished():
    while True:
        result = read_output()
        if result == "look_finished":
            print("[Python] Осмотр окончен")
            break
        time.sleep(0.1)


# === Ждём завершения поворота на блок ===
def wait_look_at():
    while True:
        result = read_output()
        if result == "look_at_complete":
            print("[Python] Поворот завершён")
            break
        time.sleep(0.1)

def read_ai_output(path):
    with open(f"{path}/active_user.json", 'r') as s:
        user=json.load(s)["active"]
    with open(f"{path}/{user}.json", 'r', encoding='utf-8') as f:
        return json.load(f)

# === Поиск ближайших бревен ===
def find_closest_blocks(cache, target, position, count=3):
    candidates = []
    for key in cache:
        name = cache[key]
        if name.lower() in target:
            x, y, z = map(int, key.split(","))
            dx = x - position['x']
            dy = y - position['y']
            dz = z - position['z']
            dist = dx * dx + dy * dy + dz * dz
            candidates.append((dist, {"x": x, "y": y, "z": z}))
    # Сортируем по расстоянию и берем первые count
    candidates.sort(key=lambda x: x[0])
    return [item[1] for item in candidates[:count]]

# === Ожидание события определенного типа ===
def wait_for_event(event_type, timeout=10):
    """
    Ждёт появления нужного события в stdout.
    Возвращает True, если событие найдено. False — если истекло время ожидания.
    """
    print(f"[Python] Ожидаем событие: {event_type} (таймаут: {timeout} секунд)")
    start_time = time.time()

    while time.time() - start_time < timeout:
        line = node_process.stdout.readline()
        if not line:
            continue  # EOF или пустая строка

        line = line.strip()
        print(f"[DEBUG] Получена строка: {line}")

        if line.startswith("EVENT"):
            try:
                received_event = line.split()[1]
                print(f"[Python] Получено событие: {received_event}")
                if received_event == event_type:
                    if received_event=="message":
                        message=(line[14:].split(":"))[1]
                        user=(line[14:].split(":"))[0]
                        print(f"[Python] Сообщение '{message}' получено")
                        return (user, message)
                    else:
                        print(f"[Python] Событие '{event_type}' получено")
                        return True
            except IndexError:
                print("error")
                continue  # некорректная строка — пропускаем

        elif line == "DATA_READY":
            # Пропускаем строки с данными, если они мешают
            node_process.stdout.readline()  # пропускаем JSON-строку

    print(f"[Ошибка] Таймаут ожидания события '{event_type}'")
    return False


# === Выполнение команды и ожидание результата ===
def execute_and_wait(command, expected_event=None):
    send_command(command)
    if expected_event:
        wait_for_event(expected_event)

def get_inventory():
    while True:
        line = node_process.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line == "INVENTORY_UPDATE":
            inv_line = node_process.stdout.readline().strip()
            try:
                return json.loads(inv_line)
            except Exception as e:
                print("[Ошибка парсинга инвентаря]", e)
    return {}

print("[Python] Запускаем JS-бота...")
if not wait_for_spawn():
    print("[Ошибка] Бот не смог заспавниться")

print("[Python] Бот успешно заспавнился")


def get_target_block(target_item, count):
    try:
        world_data=None
        for _ in range(10):  # Пытаемся получить данные до 10 раз
            result = read_output(timeout=5)
            if isinstance(result, dict) and result.get("type") == "data":
                world_data = result["content"]
                break
        if not world_data:
            print("[Ошибка] Не удалось получить данные о мире")
            return
    
        current_pos = world_data["position"]
        block_cache = world_data["cache"]
    
        print(f"[Python] Текущая позиция: {current_pos}")
        print(f"[Python] Количество блоков в кеше: {len(block_cache)}")
    
        # === Поиск деревьев ===
        blocks = find_closest_blocks(block_cache, target_item, current_pos, count)
        if not blocks or len(blocks) < 1:
            print(f"[Python] Не найдено {target_item} рядом")
            print(block_cache)
            send_command("say Не могу найти нужный блок")
            return
    
        print(f"[Python] Найдены {target_item}: {blocks}")
        first_block = blocks[0]
        block_x, block_y, block_z = first_block['x'], first_block['y'], first_block['z']
    
        # === Подходим к дереву ===
        send_command(f"goto {block_x} {block_y} {block_z}")
        goal_result = read_output(timeout=20)
        if goal_result == "goal_reached":
            print(f"[Python] Цель достигнута — подошли к {target_item}")
    
        # === Поворачиваемся на дерево ===
        send_command(f"look_at {block_x} {block_y} {block_z}")
        look_at_result = read_output(timeout=10)
        if look_at_result == "look_at_complete":
            print(f"[Python] Повернулись на {target_item}")
    
        # === Копаем дерево ===
        send_command(f"dig {block_x} {block_y} {block_z}")
        digging_result = read_output(timeout=20)
        if digging_result == "digging_completed":
            print(f"[Python] Дерево {target_item}")
    
        # === Проверяем инвентарь ===
        inventory = get_inventory()
        print("[Python] Инвентарь после добычи:", inventory)
    
        print("[Python] Работа завершена!")
        return True
    except Exception as E:
        print("[DEBUG] ОШИБКА: ",E)
        return False
        
def lookaround():
    try:
        print("[Python] Осматриваемся...")
        send_command("look_around")
        if look_finished():
            print("[Python] Осмотр окончен")
            return True
    except Exception as E:
        return False


# === Основной цикл ===
def main():
    while True:
        text=read_ai_output(USER_FOLDER)["chat_history"]
        if text:
            text=text[-1]
            print(text)
            command=re.findall(r'\((.*?)\)', text)
            command=command[0].split(", ")
            if command!=[""]:
                target=command[0]
                if target=="kill":
                    send_command(f"kill {command[1]} {command[2]}")
                if target=="stop_kill":
                    send_command("stop_kill")
                if target=="get":
                    get_target_block(command[1],command[2])
                if target=="craft":
                    send_command(f"craft {command[1]} {command[2]}")

                if target=="follow":
                    send_command(f"follow {command[1]}")
                if target=="stop_follow":
                    send_command(f"stop_follow")
                if target=="look_around":
                    send_command("")
                if target=="toss":
                    send_command(f"toss {command[1]}")

if __name__ == '__main__':
    main()