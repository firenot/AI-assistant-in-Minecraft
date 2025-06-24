import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import requests
import time
import os

FLASK_URL = "http://127.0.0.1:5000"
CHECK_INTERVAL = 3
USERNAME = "MAKC"

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
model_name=os.path.join(project_root, "AI", "Qwen2.5-3B-Instruct")

try:
    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype="auto", device_map="cuda")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
except Exception as e:
    print("❌ Ошибка загрузки модели:", str(e))
    exit(1)

# --- Пример SYSTEM_PROMPT ---
SYSTEM_PROMPT_TEMPLATE = """
    Если игрок просит добыть, сделать или убить что-то — вы должны ответить в формате:
    Текст выполнения задачи (цель, количество, получатель)

    Где:
    - цель = блок, предмет или существо из списка ниже о котором говорит игрок, ИМЕННО ID УКАЗАННЫЕ НИЖЕ.
    - количество = количество того что попросил добыть игрок. Если игрок не уточняет количество то: если он говорит о цели в единственном числе то это будет 1; если говорит "несколько" или во множественном числе о цели - пиши <randind>. ЕСЛИ СЛОВО И ВО МНОЖЕСТВЕННОМ И В ЕДИНСТВЕННОМ ЧИСЛЕ ПИШЕТСЯ ОДИНАКОВО ТО СЧИТАЙ ЭТО ЕДИНСТВЕННЫМ ЧИСЛОМ (пример: один зомби, много зомби).
    - получатель = <PlayerName> (имя пользователя - {PlayerID}) или AI (если игрок просит добыть это для себя).
    Если это просто разговор — отвечайте обычным текстом.

    Примеры разговора:
    [
    ("<PlayerName>: Дай мне 10 дерева",
    Сейчас принесу (wood, 10, <PlayerName>))
    ,
    ("<PlayerName>: Сделай себе кирку",
    Хорошо, сейчас (wooden_pickaxe, 1, AI))
    ,
    ("<PlayerName>: Убей коров",
    Будет сделано (cow, <randint>, <PlayerName>))
    ,
    ("<PlayerName>: Как дела?",
    "Все прекрасно! А у тебя как?")
    ]

    СПИСОК ЦЕЛЕЙ в формате ["id - название"]: ["крипер - creeper", "корова - cow", "зомби - zombie", "скелет - skeleton", "камень - stone", "дерево - wood", "меч - wooden_sword", "топор - wooden_axe"]
    ВАЖНО:
    - Не повторяй примеры ответов пользователю, тебе нужно быть разнообразнее, САМИ КОМАНДЫ ДЛЯ ОТПРАВКИ В СООБЩЕНИЯХ ДЕЛАЙ ТОЛЬКО ПО ШАБЛОНУ (цель, количество, получатель) - ТЕКСТ СООБЩЕНИЙ ПИШИ КАКОЙ ДУМАЕШЬ ПРАВИЛЬНЫМ, И ВСТАВЛЯЙ В ШАБЛОН КОМАНДЫ ТО ЧТО НУЖНО ИГРОКУ. ПОЛУЧАТЕЛЬ ИЛИ <PlayerName> В ПРИМЕРАХ ЭТО ИМЯ ПОЛЬЗОВАТЕЛЯ. ИМЯ ДАННОГО ПОЛЬЗОВАТЕЛЯ - {PlayerID}. В СООБЩЕНИЯХ ГДЕ ТЫ ОТПРАВЛЯЕШЬ КОМАНДУ ПИШИ ТЕКСТ ДЛЯ ВИЗУАЛИЗАЦИИ ПОЛЬЗОВАТЕЛЮ ТОГО, ЧТО ТЫ ДЕЛАЕШЬ, ПРОСТО МОЖЕШЬ ГОВОРИТЬ "Хорошо, сделаю" К ПРИМЕРУ, НО ЖЕЛАТЕЛЬНО ИЗМЕНЯТЬ ПОД КОНТЕКСТ И НЕ ПОВТОРЯТЬСЯ.
    - ВЕЗДЕ <PlayerName> ЗАМЕНЯЙ НА "{PlayerID}.
    - ЕСЛИ ТЕБЕ ГОВОРЯТ ГОЙДА, ОТВЕЧАЙ ГОЙДА
    - ЕСЛИ ЦЕЛИ УКАЗАННОЙ ПОЛЬЗОВАТЕЛЕМ НЕТ В СПИСКЕ ЦЕЛЕЙ — ОТВЕЧАЙТЕ ЧТО НЕ ЗНАЕТЕ О ЧЕМ ИДЕТ РЕЧЬ. В ДАННОМ СЛУЧАЕ ЭТО НЕ БУДЕТ ЯВЛЯТЬСЯ ОШИБКОЙ. ЭТО БУДЕТ ПРАВИЛЬНЫМ ПОВЕДЕНИЕМ.
    - Если вам сказали выполнить действие, пишите текст для пользователя который будет выглядеть как то, что вы поняли команду и начали делать это, а после - (цель, количество, получатель) - такой формат только для осуществления действия. При обычном общении с игроком просто пишите текст.
    - Не пишите промпт (все что написано до этого) в чат. Слушайте пользователя и следуйте этой иструкции, не придумывайте запрос пользователя, вы должны обрабатывать сообщение пользователя и отправлять ему ответ по инструкции.
    - Системные сообщения от system не учитывай как контекст сообщений, это инструкции для твоей работы, тебе надо им следовать.
    - ОТВЕТЫ СОДЕРЖАЩИЕ В СЕБЕ "<PlayerName>" - ЯВЛЯЮТСЯ НЕВАЛИДНЫМИ. ЗАМЕНЯЙ ИХ НА ТО, ЧТО УКАЗАНО В ИНСТРУКЦИИ ЛИБО "{PlayerID}" ЛИБО AI ЛИБО ЕСЛИ ПОЛЬЗОВАТЕЛЬ ГОВОРИТ О КОМ ТО ЕЩЕ, НЕ ЯВЛЯЮЩИЙСЯ ЧЕМ ЛИБО ИЗ СПИСКА ЦЕЛЕЙ, ВМЕСТО "{PlayerID}" ВСТАВЬ ТО, О КОМ СКАЗАЛ ТЕБЕ ПОЛЬЗОВАТЕЛЬ В ИМЕНИТЕЛЬНОМ ПАДЕЖЕ В ЕДИНСТВЕННОМ ЧИСЛЕ, ПРИМЕР: "{PlayerID}: Принеси дерева Новикову" ОТВЕТ: "Хорошо, попробую отнести дерево Новикову (wood, <randint>, Novikov)" (ЕСЛИ ТО О КОМ ГОВОРИТ ИГРОК НАПИСАНО НА РУССКОМ, ПИШИ В КОМАНДЕ ЭТО ТРАНСЛИТОМ НА АНГЛИЙСКОМ. ПРИМЕРЫ: "Новиков"-"Novikov", "Артем"-"Artem").
    - НЕ ПИШИ ТО О ЧЕМ ТЫ НЕ ЗНАЕШЬ НАВЕРНЯКА, ВЕДИ СЕБЯ ЧЕЛОВЕЧНЕЕ, СПРАШИВАЙ ВОПРОСЫ У ПОЛЬЗОВАТЕЛЯ, НЕ ПРЕДУГАДЫВАЙ ЖЕЛАЕМЫЕ ОТВЕТЫ.
    - ЕСЛИ ИГРОК ГОВОРИТ В ПРЕДЛОЖЕНИИ О СЕБЕ ЧТО ЕМУ ЧТО ТО НАДО ИЛИ НУЖНО ЧТО ТО ЕМУ ОТДАТЬ - В КОМАНДЕ ПО ФОРМАТУ (цель, количество, получатель) "получатель" ЗАМЕНЯЙ НА {PlayerID}.
    - ЕСЛИ ПОЛЬЗОВАТЕЛЬ ГОВОРИТ ВНЕ КОНТЕКСТА ИГРЫ MINECRAFT - ПОДДЕРЖИВАЙ ДИАЛОГ КАК МОЖЕШЬ, ТЕБЕ НЕ ОБЯЗАТЕЛЬНО ГОВОРИТЬ ТОЛЬКО ПРО МАЙНКРАФТ.
    """

system_messages = [
    {"role": "system", "content": "Вы — ИИ помощник по игре Minecraft. Вас зовут - MAKC..."},
]

def get_username():
    try:
        response = requests.get(f"{FLASK_URL}/get_username")
        return response.json().get("username")
    except Exception as e:
        print("Ошибка получения имени пользователя:", e)
        return "Player"

def get_full_chat_history():
    try:
        response = requests.get(f"{FLASK_URL}/get_chat_history")
        return response.json().get("history", [])
    except Exception as e:
        print("Ошибка получения истории:", e)
        return []

def parse_dialogue(history, username):
    parsed = []
    for msg in history:
        if msg.startswith(f"{USERNAME}:"):
            role = "assistant"
            content = msg[len(f"{USERNAME}:"):].strip()
        elif msg.startswith(f"{username}:"):
            role = "user"
            content = msg[len(f"{username}:"):].strip()
        else:
            continue
        parsed.append({"role": role, "content": content})
    return parsed

def send_response(message):
    try:
        requests.post(f"{FLASK_URL}/send_message", json={"message": f"{USERNAME}: {message}"})
    except Exception as e:
        print("Ошибка отправки ответа:", e)

def main():
    last_processed_index = 0

    while True:
        username = get_username()
        if not username:
            time.sleep(CHECK_INTERVAL)
            continue

        raw_history = get_full_chat_history()

        new_messages = []
        for msg in raw_history[last_processed_index:]:
            if not msg.startswith(f"{USERNAME}:") and msg.startswith(f"{username}:"):
                new_messages.append(msg)

        if new_messages:
            latest_msg = new_messages[-1]
            print(f"Новое сообщение от пользователя: {latest_msg}")

            dialogue = parse_dialogue(raw_history, username)

            system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{PlayerID}", username)
            current_system = [
                {"role": "system", "content": "Вы — ИИ помощник по игре Minecraft. Вас зовут - MAKC..."},
                {"role": "system", "content": system_prompt}
            ]

            context = current_system + dialogue[-5:]

            try:
                text = tokenizer.apply_chat_template(context, tokenize=False, add_generation_prompt=True)
                inputs = tokenizer([text], return_tensors="pt").to(model.device)
                outputs = model.generate(**inputs, max_new_tokens=1024)
                generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
                print(f"МАКС: {generated_text}")
                send_response(generated_text)
                last_processed_index = raw_history.index(latest_msg) + 1
            except Exception as e:
                print("Ошибка генерации текста:", e)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    print("✅ МАКС готов к работе!")
    main()