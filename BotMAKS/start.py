import subprocess
import json
import time
import threading
import os
# === Настройки ===
TREE_BLOCK = 'oak wood'
WOOD_PLANKS = 'oak_planks'
STICK = 'stick'
CRAFTING_TABLE = 'crafting_table'
WOODEN_PICKAXE = 'wooden_pickaxe'

SCAN_RADIUS = 80
REQUIRED_LOGS = 3

# === Запуск Node.js бота с указанием кодировки ===
node_process = subprocess.Popen(
    ['node', 'bot.js'],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding='utf-8',
    errors='replace'
)

USER_FOLDER = 'user_data'
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


# === Очистка буфера вывода ===
def clear_output_buffer():
    while True:
        line = node_process.stdout.readline()
        if not line or "Бот заспавнился" in line:
            break


# === Ожидание спавна бота ===
def wait_for_spawn():
    clear_output_buffer()
    print("[Python] Бот запущен и готов к работе")
    return True


# === Отправка команд ===
def send_command(cmd):
    print(f"[Python] Отправляем команду: {cmd}")
    node_process.stdin.write(cmd + '\n')
    node_process.stdin.flush()


# === Чтение событий и данных ===
def read_output():
    while True:
        line = node_process.stdout.readline()
        if not line:
            break
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
            elif event_type =="message":
                return ("message",parts[2])

        elif line == "DATA_READY":
            data_line = node_process.stdout.readline().strip()
            try:
                data = json.loads(data_line)
                print("[Python] Получены данные о мире и позиции")
                return {"type": "data", "content": data}
            except Exception as e:
                print("[Ошибка парсинга данных]", e)

    return None


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


# === Поиск ближайших бревен ===
def find_closest_logs(cache, position, count=3):
    candidates = []

    for key in cache:
        name = cache[key]
        if TREE_BLOCK in name.lower():
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

# === Основной цикл ===
def main():
    current_pos = {"x": 0, "y": 0, "z": 0}

    if not wait_for_spawn():
        print("[Ошибка] Бот не смог заспавниться")
        return

    try:
        user,message=wait_for_event("message",20)
        add_message_to_chat(user, message)
        if "дерево" in message:
            time.sleep(2)
            send_command("say Хорошо, нужно только найти немного дерева")
            add_message_to_chat(user, "MAKC: Хорошо, нужно только найти немного дерева")
            wait_for_event("said")
            # === 1. Осматриваемся для поиска ресурсов ===
            print("[Python] Осматриваемся...")
            send_command("look_around")
            look_finished()

            data = None
            while True:
                result = read_output()
                if isinstance(result, dict) and result.get("type") == "data":
                    data = result["content"]
                    current_pos = data["position"]
                    print(f"[Python] Текущая позиция: {current_pos}")
                    break
                time.sleep(0.1)

            # === 2. Найдем и добудем 3 ближайших бревна ===
            """trees = find_closest_logs(data["cache"], current_pos, REQUIRED_LOGS)
            print(trees)
            if not trees or len(trees) < REQUIRED_LOGS:
                print(f"[Python] Не найдено достаточного количества бревен (нужно {REQUIRED_LOGS})")
                return"""
            trees=[{"x":257,"y":71,"z":-188},{"x":257,"y":72,"z":-188},{"x":257,"y":73,"z":-188}]
            print(f"[Python] Найдены бревна: {trees}")
            send_command("say Увидел дерево недалеко")
            add_message_to_chat(user, "MAKC: Увидел дерево недалеко")
            wait_for_event("said")
            time.sleep(0.3)
            send_command(f"goto {trees[1]['x']} {trees[1]['y']} {trees[1]['z']}")
            wait_for_event("goal_reached")
            time.sleep(0.2)
            # Поворачиваемся к блоку
            send_command(f"look_at {trees[0]['x']} {trees[0]['y']} {trees[0]['z']}")
            wait_look_at()

            # Копаем
            send_command(f"dig {trees[0]['x']} {trees[0]['y']} {trees[0]['z']}")
            wait_for_event("digging_completed")

            """
                # Подходим к дереву
                send_command(f"goto {tree['x']} {tree['y']} {tree['z']}")
                wait_for_event("goal_reached")

                # Поворачиваемся к блоку
                send_command(f"look_at {tree['x']} {tree['y']} {tree['z']}")
                wait_look_at()

                # Копаем
                send_command(f"dig {tree['x']} {tree['y']} {tree['z']}")
                wait_for_event("digging_completed")
                time.sleep(0.2)"""
            # === 3. Ждём обновления инвентаря после добычи ===
            inventory = get_inventory()
            print("[Python] Инвентарь после добычи:", inventory)

            if inventory.get('log', 0) < 3:
                print("[Ошибка] Недостаточно бревен в инвентаре")
                return

            time.sleep(2)
            # === 4. Крафтим доски из бревен ===
            send_command("say Делаю доски")
            add_message_to_chat(user, "MAKC: Делаю доски")
            wait_for_event("said")
            print("[Python] Крафтим доски из бревен")
            send_command(f"craft planks 3")
            wait_for_event("crafted_successfully")  # craft может использовать событие digging_completed или другое
            time.sleep(1)
            # === 5. Крафтим палки из досок ===
            send_command("say Делаю палки")
            add_message_to_chat(user, "MAKC: Делаю палки")
            wait_for_event("said")
            print("[Python] Крафтим палки из досок")
            send_command(f"craft stick 1")
            wait_for_event("crafted_successfully")
            
            time.sleep(1)

            # === 6. Крафтим верстак ===
            send_command("say Делаю верстак")
            add_message_to_chat(user, "MAKC: Делаю верстак")
            wait_for_event("said")
            print("[Python] Крафтим верстак")
            send_command(f"craft crafting_table 1")
            wait_for_event("crafted_successfully")
            time.sleep(2)

            # === 7. Ставим верстак рядом ===
            print("[Python] Ставим верстак рядом")
            send_command("place crafting_table")
            wait_for_event("placed")
            time.sleep(1)
            send_command("say Делаю кирку на верстаке")
            add_message_to_chat(user, "MAKC: Делаю кирку на верстаке")
            wait_for_event("said")
            print("[Python] Крафтим деревянную кирку на верстаке")
            send_command("craft wooden_pickaxe 1")
            wait_for_event("crafted_successfully")
            time.sleep(1)
            send_command(f"say Иду к тебе, {user}!")
            add_message_to_chat(user, f"MAKC: Иду к тебе, {user}!")
            wait_for_event("said")
            send_command(f"follow {user}")
            wait_for_event("looked_at_player")
            time.sleep(1)
            send_command(f"say Держи что ты хотел, {user}")
            add_message_to_chat(user, f"MAKC: Держи что ты хотел, {user}")
            wait_for_event("said")
            send_command("toss wooden_pickaxe")
            time.sleep(10)
            print("[Python] Работа успешно завершена!")

    except KeyboardInterrupt:
        print("\n[Python] Остановка работы.")
        node_process.terminate()


if __name__ == "__main__":
    main()