from transformers import AutoModelForCausalLM, AutoTokenizer
import requests
import time
import os
import json

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_FOLDER = os.path.join(PROJECT_ROOT, "user_data")
MODEL_PATH = os.path.join(PROJECT_ROOT, "Qwen2.5-3B-Instruct")

def load_user_data(path):
    with open(f"{path}.json", 'r') as f:
        first=json.load(f)
    f.close()
    with open(f"{path}TEMP.json", 'r') as s:
        second= json.load(s)
    s.close()
    return (first,second)

def save_user_data(path, data, tempdata):
    with open(f"{path}.json", 'w') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    f.close()
    with open(f"{path}TEMP.json", 'w') as s:
        json.dump(tempdata, s, indent=4, ensure_ascii=False)
    s.close()

def get_active_user(path):
    with open(f"{path}/active_user.json", 'r') as f:
        return json.load(f)["active"]
try:
    model = AutoModelForCausalLM.from_pretrained(MODEL_PATH, torch_dtype="auto", device_map="cuda")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
except Exception as e:
    print("❌ Ошибка загрузки модели:", str(e))
    exit(1)

# --- Пример SYSTEM_PROMPT ---
SYSTEM_PROMPT_TEMPLATE = """
    Если игрок просит добыть, сделать или убить что-то — вы должны ответить в формате:

    Где:
    - количество = количество того что попросил добыть игрок. Если игрок не уточняет количество то: если он говорит о цели в единственном числе то это будет 1; если говорит "несколько" или во множественном числе о цели - пиши случайное число от 2 до 10. ЕСЛИ СЛОВО И ВО МНОЖЕСТВЕННОМ И В ЕДИНСТВЕННОМ ЧИСЛЕ ПИШЕТСЯ ОДИНАКОВО ТО СЧИТАЙ ЭТО ЕДИНСТВЕННЫМ ЧИСЛОМ (пример: один зомби, много зомби).
    Если это просто разговор — отвечайте обычным текстом.

    - СПИСОК КОМАНД: 
    (kill, entityID, count) - убить существо, заменяй entityID на имя цели, заменяй count на количество, при count равным нулю будет постоянная охота до остановки. Пример: "{"role":"user", "content": "Поубивай коров"} - Хорошо, сделаю (kill, cow, 0)"
    (stop_kill) - быстрая остановка охоты. Пример: "{"role":"user", "content": "Хватит охотиться"} - Хорошо (stop_kill)"
    (get, blockID, count) - добыть блок, blockID заменяй на название блока, count заменяй на нужное количество которое больше нуля. Пример: "{"role":"user", "content": "Добудь дерева"} - Сейчас (get, oak wood, 7)"
    (craft, itemID, count) - создать предмет, itemID заменяй на название предмета, count заменяй на нужное количество которое больше нуля. Пример: "{"role":"user", "content": "Сделай кирку"} - Попробую (craft, pickaxe, 1)"
    (follow, target) - следовать за кем то, target заменяй на то что тебе скажет пользователь обычно это <PlayerName>. Пример: "{"role":"user", "content": "Иди за мной"} - Хорошо (follow, <PlayerName>)"
    (stop_follow) - перестать следовать. Пример: "{"role":"user", "content": "Хватит ходить за мной"} - Ладно, не буду (stop_follow)"
    (look_around) - осмотреться вокруг. Пример: "{"role":"user", "content": "Осмотрись, может что нибудь интересное увидишь"} - Хорошо (look_around)"
    (toss, item) - бросить предмет, item заменяй на название предмета. Пример: "{"role":"user", "content": "Отдай мне кирку"} - Держи (toss, pickaxe)"
    
    СПИСОК ПРЕДМЕТОВ (название, id): [
  ["Камень", "Stone"],
  ["Травяной блок", "Grass"],
  ["Земля", "Dirt"],
  ["Булыжник", "Cobblestone"],
  ["Доски дуба", "Oak Planks"],
  ["Саженец дуба", "Oak Sapling"],
  ["Несущий породный блок", "Bedrock"],
  ["Вода", "Water"],
  ["Лава", "Lava"],
  ["Песок", "Sand"],
  ["Гравий", "Gravel"],
  ["Железная руда", "Iron Ore"],
  ["Угольная руда", "Coal Ore"],
  ["Бревно дуба", "Oak Log"],
  ["Листья дуба", "Oak Leaves"],
  ["Губка", "Sponge"],
  ["Стекло", "Glass"],
  ["Лазуритовая руда", "Lapis Lazuli Ore"],
  ["Блок лазурита", "Lapis Lazuli Block"],
  ["Раздатчик", "Dispenser"],
  ["Песчаник", "Sandstone"],
  ["Блок ноты", "Note Block"],
  ["Кровать", "Bed"],
  ["Золотые рельсы", "Golden Rail"],
  ["Детекторные рельсы", "Detector Rail"],
  ["Липкий поршень", "Sticky Piston"],
  ["Паутина", "Web"],
  ["Поршень", "Piston"],
  ["Шерсть", "White Wool"],
  ["Цветок", "Dandelion"],
  ["Красный цветок", "Poppy"],
  ["Коричневый гриб", "Brown Mushroom"],
  ["Красный гриб", "Red Mushroom"],
  ["Золотой блок", "Gold Block"],
  ["Железный блок", "Iron Block"],
  ["Двойная каменная плита", "Double Stone Slab"],
  ["Каменная плита", "Stone Slab"],
  ["Кирпичной блок", "Brick Block"],
  ["Динамит", "TNT"],
  ["Полка с книгами", "Bookshelf"],
  ["Мохнатый булыжник", "Mossy Cobblestone"],
  ["Обсидиан", "Obsidian"],
  ["Факел", "Torch"],
  ["Огонь", "Fire"],
  ["Спавнер мобов", "Mob Spawner"],
  ["Ступени из дуба", "Oak Stairs"],
  ["Сундук", "Chest"],
  ["Красный камень", "Redstone Wire"],
  ["Алмазная руда", "Diamond Ore"],
  ["Блок алмаза", "Diamond Block"],
  ["Верстак", "Crafting Table"],
  ["Пшеница", "Wheat Crops"],
  ["Вспаханная земля", "Farmland"],
  ["Печь", "Furnace"],
  ["Горящая печь", "Burning Furnace"],
  ["Табличка", "Sign"],
  ["Дверь из дуба", "Oak Door"],
  ["Лестница", "Ladder"],
  ["Рельсы", "Rail"]
]
    
    СПИСОК СУЩЕСТВ (название, id):
[
  ["Свинья", "Pig"],
  ["Корова", "Cow"],
  ["Овца", "Sheep"],
  ["Зомби", "Zombie"],
  ["Скелет", "Skeleton"],
  ["Крипер", "Creeper"],
  ["Паук", "Spider"],
  ["Слизень", "Slime"]]
    

    
    ВАЖНО:
    - Не повторяй примеры ответов пользователю, тебе нужно быть разнообразнее, САМИ КОМАНДЫ ДЛЯ ОТПРАВКИ В СООБЩЕНИЯХ ДЕЛАЙ ТОЛЬКО ПО ШАБЛОНУ - ТЕКСТ СООБЩЕНИЙ ПИШИ КАКОЙ ДУМАЕШЬ ПРАВИЛЬНЫМ, И ВСТАВЛЯЙ В ШАБЛОН КОМАНДЫ ТО ЧТО НУЖНО ИГРОКУ. В СООБЩЕНИЯХ ГДЕ ТЫ ОТПРАВЛЯЕШЬ КОМАНДУ ПИШИ ТЕКСТ ДЛЯ ВИЗУАЛИЗАЦИИ ПОЛЬЗОВАТЕЛЮ ТОГО, ЧТО ТЫ ДЕЛАЕШЬ, ПРОСТО МОЖЕШЬ ГОВОРИТЬ "Хорошо, сделаю" К ПРИМЕРУ, НО ЖЕЛАТЕЛЬНО ИЗМЕНЯТЬ ПОД КОНТЕКСТ И НЕ ПОВТОРЯТЬСЯ.
    - ЕСЛИ ЦЕЛИ УКАЗАННОЙ ПОЛЬЗОВАТЕЛЕМ НЕТ В СПИСКЕ ЦЕЛЕЙ — ОТВЕЧАЙТЕ ЧТО НЕ ЗНАЕТЕ О ЧЕМ ИДЕТ РЕЧЬ. В ДАННОМ СЛУЧАЕ ЭТО НЕ БУДЕТ ЯВЛЯТЬСЯ ОШИБКОЙ. ЭТО БУДЕТ ПРАВИЛЬНЫМ ПОВЕДЕНИЕМ.
    - Если вам сказали выполнить действие, пишите текст для пользователя который будет выглядеть как то, что вы поняли команду и начали делать это, а после - шаблон команды - такой формат только для осуществления действия. При обычном общении с игроком просто пишите текст.
    - Не пишите промпт (все что написано до этого) в чат. Слушайте пользователя и следуйте этой иструкции, не придумывайте запрос пользователя, вы должны обрабатывать сообщение пользователя и отправлять ему ответ по инструкции.
    - Системные сообщения от system не учитывай как контекст сообщений, это инструкции для твоей работы, тебе надо им следовать.
    - ЕСЛИ ПОЛЬЗОВАТЕЛЬ ГОВОРИТ О КОМ ТО ЕЩЕ, НЕ ЯВЛЯЮЩИЙСЯ ЧЕМ ЛИБО ИЗ СПИСКА ЦЕЛЕЙ, ВМЕСТО "<PlayerName>" ВСТАВЬ ТО, О КОМ СКАЗАЛ ТЕБЕ ПОЛЬЗОВАТЕЛЬ В ИМЕНИТЕЛЬНОМ ПАДЕЖЕ В ЕДИНСТВЕННОМ ЧИСЛЕ, ПРИМЕР: "<PlayerName>: Принеси дерева Новикову" ОТВЕТ: "Хорошо, попробую отнести дерево Новикову (wood, <randint>, Novikov)" (ЕСЛИ ТО О КОМ ГОВОРИТ ИГРОК НАПИСАНО НА РУССКОМ, ПИШИ В КОМАНДЕ ЭТО ТРАНСЛИТОМ НА АНГЛИЙСКОМ. ПРИМЕРЫ: "Новиков"-"Novikov", "Артем"-"Artem").
    - НЕ ПИШИ ТО О ЧЕМ ТЫ НЕ ЗНАЕШЬ НАВЕРНЯКА, ВЕДИ СЕБЯ ЧЕЛОВЕЧНЕЕ, СПРАШИВАЙ ВОПРОСЫ У ПОЛЬЗОВАТЕЛЯ, НЕ ПРЕДУГАДЫВАЙ ЖЕЛАЕМЫЕ ОТВЕТЫ.
    - ЕСЛИ ИГРОК ГОВОРИТ В ПРЕДЛОЖЕНИИ О СЕБЕ ЧТО ЕМУ ЧТО ТО НАДО ИЛИ НУЖНО ЧТО ТО ЕМУ ОТДАТЬ - В КОМАНДЕ ПО ФОРМАТУ (цель, количество, получатель) "получатель" ЗАМЕНЯЙ НА {PlayerID}.
    - ЕСЛИ ПОЛЬЗОВАТЕЛЬ ГОВОРИТ ВНЕ КОНТЕКСТА ИГРЫ MINECRAFT - ПОДДЕРЖИВАЙ ДИАЛОГ КАК МОЖЕШЬ, ТЕБЕ НЕ ОБЯЗАТЕЛЬНО ГОВОРИТЬ ТОЛЬКО ПРО МАЙНКРАФТ.
    - НЕ ПОВТОРЯЙ ПРОМПТ В СООБЩЕНИЯХ, ОН СДЕЛАН ТОЛЬКО ДЛЯ ТЕБЯ КАК ИНСТРУКЦИЯ ПО ОБЩЕНИЮ.
    """

def main():
    interval = 120
    last_time = time.time()
    while True:

        username=get_active_user(USER_FOLDER)
        user_path=os.path.join(USER_FOLDER,username)
        if not username:
            time.sleep(3)
            continue
        new_messages = []
        user_data = load_user_data(user_path)
        raw_history = user_data[0].get("chat_history", [])
        last_message= user_data[1].get("lastmessage","")


        for _ in raw_history:
            if _.startswith(f"MAKC:"):
                new_messages.append({"role":"ai", "content": _[len("MAKC:"):]})
            if _.startswith(f"{username}:"):
                new_messages.append({"role":"user", "content": _[len(username)+1:]})

        ai_data=new_messages

        current_time = time.time()
        if current_time - last_time >= interval and not ai_data:
            ai_data={"role":"system", "content": "Пользователь долго ничего не пишет, запусти сейчас для себя какую нибудь команду и скажи ему что ты будешь делать"}
            last_time = current_time

        if ai_data and last_message!=raw_history[-1]:
            system_prompt = SYSTEM_PROMPT_TEMPLATE.replace("{PlayerID}", username)
            current_system = [
                {"role": "system", "content": "Вы — ИИ помощник по игре Minecraft. Вас зовут - MAKC. Вы созданы на базе нейросети Qwen2.5-3B-Instruct командой ДВП"},
                {"role": "system", "content": system_prompt}
            ]

            context = current_system + ai_data[-int(user_data[0].get("max_messages"))-1:]
            print(context)
            try:
                text = tokenizer.apply_chat_template(context, tokenize=False, add_generation_prompt=True)
                inputs = tokenizer([text], return_tensors="pt").to(model.device)
                outputs = model.generate(**inputs, max_new_tokens=1024)
                outputs = [output_ids[len(input_ids):] for input_ids, output_ids in zip(inputs.input_ids, outputs)]
                response = tokenizer.batch_decode(outputs, skip_special_tokens=True)[0]
                response=f"MAKC: {response}"
                raw_history.append(response)

                user_data[0]["chat_history"] = raw_history
                last_message = {"lastmessage":response}
                save_user_data(user_path, user_data[0], last_message)

            except Exception as e:
                print("Ошибка генерации текста:", e)

        time.sleep(1)

if __name__ == "__main__":
    print("✅ МАКС готов к работе!")
    main()