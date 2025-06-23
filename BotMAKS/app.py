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

# --- Настройки по умолчанию ---
DEFAULT_USER_DATA = {
    "bot_on": False,
    "server_ip": "localhost",
    "port": "25565",
    "max_messages": 25,
    "chat_history": []
}


# --- Работа с файлами ---
def get_user_file(username):
    return os.path.join(USER_FOLDER, f'{username}.json')


def load_user_data(username):
    path = get_user_file(username)
    if not os.path.exists(path):
        save_user_data(username, DEFAULT_USER_DATA.copy())
    with open(path, 'r') as f:
        data = json.load(f)

    # Ограничим размер истории при загрузке
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

        # Создаём файл пользователя при первом входе
        if not os.path.exists(get_user_file(username)):
            save_user_data(username, DEFAULT_USER_DATA.copy())

        return redirect(url_for('index'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/main')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session['username']
    user_data = load_user_data(username)
    return render_template('index.html', settings=user_data, username=username)


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


@app.route('/toggle_bot', methods=['POST'])
def toggle_bot():
    global bot_process

    if 'username' not in session:
        return jsonify(success=False)

    username = session['username']
    state = request.json.get('state', False)

    user_data = load_user_data(username)
    old_state = user_data['bot_on']

    user_data['bot_on'] = state
    save_user_data(username, user_data)

    # Путь к твоему скрипту бота
    bot_script_path = os.path.join("C:/Users\Pavel\Desktop/testbot", "start.py")

    if state and not old_state:
        # Включаем бота
        try:
            # Запускаем бота как отдельный процесс
            bot_process = subprocess.Popen(["python", bot_script_path])
            print(f"Бот запущен с PID: {bot_process.pid}")
        except Exception as e:
            print("Ошибка запуска бота:", e)
            return jsonify(success=False)

    elif not state and old_state:
        # Выключаем бота
        if bot_process:
            print(f"Останавливаем бота с PID: {bot_process.pid}")
            bot_process.terminate()
            bot_process.wait()  # Ждём завершения
            bot_process = None

    return jsonify(success=True)


@app.route('/update_server', methods=['POST'])
def update_server():
    if 'username' not in session:
        return jsonify(success=False)

    ip = request.form.get('ip')
    port = request.form.get('port')

    username = session['username']
    user_data = load_user_data(username)
    user_data['server_ip'] = ip
    user_data['port'] = port
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


# --- Автооткрытие ---
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000")


if __name__ == '__main__':
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        threading.Timer(1.5, open_browser).start()
    app.run(debug=True)
