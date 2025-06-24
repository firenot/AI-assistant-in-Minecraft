from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import webbrowser
import threading
import os
import json
import subprocess

app = Flask(__name__)
app.secret_key = 'super-secret-key'

USER_FOLDER = 'user_data'
os.makedirs(USER_FOLDER, exist_ok=True)

ai_process = None
bot_process = None
server_process = None

# --- Настройки по умолчанию ---
DEFAULT_USER_DATA = {
    "bot_on": False,
    "server_ip": "localhost",
    "port": "25565",
    "level_seed": "",
    "level_type": "DEFAULT",
    "server_folder": "",
    "task_flags": {str(i): False for i in range(1, 11)},
    "max_messages": 25,
    "chat_history": [],
}


# --- Работа с файлами ---
def get_user_file(username):
    return os.path.join(USER_FOLDER, f'{username}.json')

def load_user_data(username):
    path = get_user_file(username)
    if not os.path.exists(path):
        save_user_data(username, DEFAULT_USER_DATA.copy())
    with open(path, 'r') as f:
        return json.load(f)

def save_user_data(username, data):
    path = get_user_file(username)
    with open(path, 'w') as f:
        json.dump(data, f, indent=4)

# --- Роуты ---
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if not username:
            return render_template('login.html', error="Имя обязательно")
        session['username'] = username

        if not os.path.exists(get_user_file(username)):
            save_user_data(username, DEFAULT_USER_DATA.copy())
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'username' in session:
        username = session['username']
        user_data = load_user_data(username)

        # Сбросить все флаги задач
        user_data['task_flags'] = {str(i): False for i in range(1, 11)}
        save_user_data(username, user_data)

    session.clear()
    return redirect(url_for('login'))


@app.route('/main')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    user_data = load_user_data(username)
    return render_template('index.html', settings=user_data, username=username)

@app.route('/toggle_ai', methods=['POST'])
def toggle_ai():
    global ai_process
    if 'username' not in session:
        return jsonify(success=False)

    state = request.json.get('state', False)
    ai_script_path = os.path.join(os.getcwd(), "ai.py")

    if state:
        try:
            ai_process = subprocess.Popen(["python", ai_script_path])
            print(f"ИИ запущен (PID: {ai_process.pid})")
        except Exception as e:
            print("Ошибка запуска ИИ:", e)
            return jsonify(success=False)
    else:
        if ai_process:
            print(f"Останавливаем ИИ (PID: {ai_process.pid})")
            ai_process.terminate()
            ai_process.wait()
            ai_process = None

    return jsonify(success=True)

@app.route('/send_message', methods=['POST'])
def send_message():
    if 'username' not in session:
        return jsonify(success=False)

    username = session['username']
    message = request.json.get('message', '').strip()
    if not message:
        return jsonify(success=False)

    user_data = load_user_data(username)
    user_data["chat_history"].append(message)
    save_user_data(username, user_data)

    return jsonify(success=True)

@app.route('/get_chat_history')
def get_chat_history():
    if 'username' not in session:
        return jsonify(history=[])

    username = session['username']
    user_data = load_user_data(username)
    return jsonify(history=user_data.get("chat_history", []))

@app.route('/get_context_messages')
def get_context_messages():
    if 'username' not in session:
        return jsonify(context=[])

    username = session['username']
    user_data = load_user_data(username)
    max_msgs = user_data.get("max_messages", 25)
    return jsonify(context=user_data.get("chat_history", [])[-max_msgs:])

@app.route('/clear_chat', methods=['POST'])
def clear_chat():
    if 'username' not in session:
        return jsonify(success=False)

    username = session['username']
    user_data = load_user_data(username)
    user_data['chat_history'] = []
    save_user_data(username, user_data)

    return jsonify(success=True)

@app.route('/activate_task', methods=['POST'])
def activate_task():
    if 'username' not in session:
        return jsonify(success=False)

    task_id = str(request.json.get('task_id'))
    if task_id not in map(str, range(1, 11)):
        return jsonify(success=False, message="Некорректный ID задачи")

    username = session['username']
    user_data = load_user_data(username)

    # Сбросить все флаги, кроме выбранного
    user_data['task_flags'] = {str(i): (str(i) == task_id) for i in range(1, 11)}

    save_user_data(username, user_data)
    return jsonify(success=True)


@app.route('/toggle_bot', methods=['POST'])
def toggle_bot():
    global bot_process

    if 'username' not in session:
        return jsonify(success=False)

    username = session['username']
    state = request.json.get('state', False)

    user_data = load_user_data(username)
    old_state = user_data.get('bot_on', False)

    user_data['bot_on'] = state
    save_user_data(username, user_data)

    bot_script_path = os.path.join("C:/Users/Pavel/Desktop/testbot", "start.py")

    if state and not old_state:
        try:
            bot_process = subprocess.Popen(["python", bot_script_path])
            print(f"Бот запущен с PID: {bot_process.pid}")
        except Exception as e:
            print("Ошибка запуска бота:", e)
            return jsonify(success=False)

    elif not state and old_state:
        if bot_process:
            print(f"Останавливаем бота с PID: {bot_process.pid}")
            bot_process.terminate()
            bot_process.wait()
            bot_process = None

    return jsonify(success=True)

@app.route('/update_server', methods=['POST'])
def update_server():
    if 'username' not in session:
        return jsonify(success=False)

    username = session['username']
    user_data = load_user_data(username)

    ip = request.json.get('ip', '').strip()
    port = request.json.get('port', '25565').strip()
    level_seed = request.json.get('level_seed', '').strip()
    level_type = request.json.get('level_type', 'DEFAULT').strip().upper()

    user_data.update({
        'server_ip': ip,
        'port': port,
        'level_seed': level_seed,
        'level_type': level_type
    })
    save_user_data(username, user_data)

    server_folder = user_data.get('server_folder')
    if not server_folder or not os.path.isdir(server_folder):
        return jsonify(success=False, message="Неверная папка сервера")

    props_path = os.path.join(server_folder, 'server.properties')
    if not os.path.exists(props_path):
        return jsonify(success=False, message="Файл server.properties не найден")

    try:
        with open(props_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        def replace_or_add(key, value):
            found = False
            for i, line in enumerate(lines):
                if line.startswith(key + "="):
                    lines[i] = f"{key}={value}\n"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}\n")

        replace_or_add("server-port", port)
        replace_or_add("server-ip", "" if ip == "localhost" else ip)
        replace_or_add("level-seed", level_seed)
        replace_or_add("level-type", level_type)

        with open(props_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, message=str(e))



@app.route('/set_max_messages', methods=['POST'])
def set_max_messages():
    if 'username' not in session:
        return jsonify(success=False)

    value = int(request.json.get('value', 25))
    username = session['username']
    user_data = load_user_data(username)
    user_data['max_messages'] = value
    save_user_data(username, user_data)
    return jsonify(success=True)


@app.route('/set_server_folder', methods=['POST'])
def set_server_folder():
    data = request.get_json()
    folder = data.get('folder')
    if not os.path.isdir(folder):
        return jsonify({'status': 'error', 'message': 'Папка не существует'}), 400
    username = session['username']
    user_data = load_user_data(username)
    user_data['server_folder'] = folder
    save_user_data(username, user_data)
    return jsonify({'status': 'ok'})

@app.route('/start_server', methods=['POST'])
def start_server():
    global server_process
    username = session['username']
    user_data = load_user_data(username)
    folder = user_data.get('server_folder')
    if not folder or not os.path.isdir(folder):
        return jsonify({'status': 'error', 'message': 'Укажите корректную папку сервера'}), 400
    if server_process and server_process.poll() is None:
        return jsonify({'status': 'error', 'message': 'Сервер уже запущен'}), 400

    try:
        # Запускаем сервер в новой консоли
        server_process = subprocess.Popen(
            ['python', 'main.py'], cwd=folder,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- Автооткрытие ---
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.5, open_browser).start()
    app.run(debug=True)
