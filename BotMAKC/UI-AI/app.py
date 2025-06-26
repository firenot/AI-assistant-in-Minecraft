from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
import json
import subprocess
import threading
import sys
import webbrowser

app = Flask(__name__)
app.secret_key = 'super-secret-key'

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
file = os.path.join(PROJECT_ROOT, "user_data")

USER_FOLDER = file
os.makedirs(USER_FOLDER, exist_ok=True)

# --- Глобальные переменные ---
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
    "chat_history": []
}
DEFAULT_TEMP_DATA={
    "lastmessage": ""
}


# --- Вспомогательные функции ---
def get_user_file(username):
    return os.path.join(USER_FOLDER, f'{username}.json')

def load_user_data(username):
    path = get_user_file(username)
    if not os.path.exists(path):
        save_user_data(username, DEFAULT_USER_DATA.copy())
    with open(path, 'r') as f:
        data = json.load(f)
    # Ограничиваем историю сообщений
    max_msgs = data.get("max_messages", 25)
    data["chat_history"] = data["chat_history"][-max_msgs:]
    return data

def save_user_data(username, data):
    max_msgs = data.get("max_messages", 25)
    data["chat_history"] = data["chat_history"][-max_msgs:]
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
        with open(os.path.join(USER_FOLDER, f'active_user.json'), 'w') as f:
            json.dump({"active":username}, f, indent=4)
        if not os.path.exists(get_user_file(username)):
            save_user_data(username, DEFAULT_USER_DATA.copy())
        if not os.path.exists(os.path.join(USER_FOLDER, f'{username}TEMP.json')):
            with open(os.path.join(USER_FOLDER, f'{username}TEMP.json'), 'w') as f:
                json.dump(DEFAULT_TEMP_DATA.copy(), f, indent=4)
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
        return jsonify(success=False), 401

    username = session['username']
    state = request.json.get('state', False)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ai_script_path = os.path.join(project_root, "AI", "run_ai.py")

    if state:
        if ai_process is None:
            try:
                # Передаем username как аргумент командной строки
                ai_process = subprocess.Popen([sys.executable, ai_script_path, "--username", username])
                print(f"ИИ запущен для пользователя '{username}' с PID: {ai_process.pid}")
            except Exception as e:
                print("Ошибка запуска ИИ:", e)
                return jsonify(success=False), 500
    else:
        if ai_process:
            print(f"Останавливаем ИИ с PID: {ai_process.pid}")
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
    formatted_message = f"{username}: {message}"
    user_data["chat_history"].append(formatted_message)
    save_user_data(username, user_data)
    return jsonify(success=True)

@app.route('/get_chat_history')
def get_chat_history():
    if 'username' not in session:
        return jsonify(history=[])
    username = session['username']
    user_data = load_user_data(username)
    return jsonify(history=user_data.get("chat_history", []))

@app.route('/get_username')
def get_username():
    if 'username' not in session:
        return jsonify(username=None)
    return jsonify(username=session['username'])

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
    bot_script_path = os.path.join(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'BOT', 'bot_logic.py'))
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
    ip = request.form.get('ip')
    port = request.form.get('port')
    level_seed = request.form.get('level_seed', '')
    level_type = request.form.get('level_type', 'DEFAULT').upper()
    username = session['username']
    user_data = load_user_data(username)
    user_data.update({
        'server_ip': ip,
        'port': port,
        'level_seed': level_seed,
        'level_type': level_type
    })
    save_user_data(username, user_data)
    return jsonify(success=True)

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
        server_process = subprocess.Popen(['python', 'main.py'], cwd=folder)
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# --- Автооткрытие браузера при старте ---
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")

if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.5, open_browser).start()
    app.run(debug=True)