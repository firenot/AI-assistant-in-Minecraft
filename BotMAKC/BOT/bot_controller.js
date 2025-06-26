const mineflayer = require('mineflayer');
const pathfinder = require('mineflayer-pathfinder');
const CollectBlock = require('mineflayer-collectblock');
const { Movements, goals } = pathfinder;
const mcData = require('minecraft-data');
console.log("Поддерживаемые версии:", mcData.supportedVersions);
const Vec3 = require('vec3');
const Recipe=require("prismarine-recipe")("1.12.2").Recipe;
const fs = require('fs');
const path = require('path');


process.on('uncaughtException', (err) => {
    console.error('[JS FATAL ERROR]', err.message);
    process.stdout.write(`ERROR uncaughtException ${err.message}\n`);
});

process.on('unhandledRejection', (reason, promise) => {
    console.error('[JS UNHANDLED REJECTION]', reason.message || reason);
    process.stdout.write(`ERROR unhandledRejection ${reason.message || reason}\n`);
});

let blockCache = {}; // Кеш блоков в памяти
let entityCache = {};


const CACHE_FILE = "C:\\Projects\\BotMAKC\\BOT\\scanned_blocks.json";

const ENTITY_FILE = "C:\\Projects\\BotMAKC\\BOT\\entities.json";

loadEntityCacheFromFile();

const SCAN_RADIUS = 80;

function loadBlockCacheFromFile() {
    if (fs.existsSync(CACHE_FILE)) {
        try {
            const data = fs.readFileSync(CACHE_FILE, 'utf8');
            blockCache = JSON.parse(data) || {};
            console.log(`Кеш загружен: ${Object.keys(blockCache).length} блоков`);
        } catch (err) {
            console.error("Ошибка чтения кеша из файла:", err.message);
        }
    } else {
        console.log("Файл кеша не найден — создаём новый");
        fs.writeFileSync(CACHE_FILE, '{}', 'utf8');
    }
}
loadBlockCacheFromFile();
// Создаем бота
const bot = mineflayer.createBot({
    host: 'localhost',
    port: 25565,
    username: 'MAKCAI',
    version: '1.12.2'
});


// Регулярная проверка: продолжать ли атаку
setInterval(() => {
    if (currentAggressor && currentAggressor.alive) {
        const distance = bot.entity.position.distanceTo(currentAggressor.position);
        if (distance > 10) {
            bot.pvp.stop();
            bot.pathfinder.setGoal(null);
            currentAggressor = null;
        }
    }
}, 2000);

// Подготавливаем данные Minecraft
let registry = null;


bot.on('spawn', () => {
    console.log("Бот заспавнился");

    registry = mcData(bot.version);

    setInterval(sendInventoryUpdate, 2000);
    bot.loadPlugin(pathfinder.pathfinder);
    const movements = new Movements(bot, registry);
    bot.pathfinder.setMovements(movements);

    try {
        const { plugin: PVP } = require('mineflayer-pvp');
        bot.loadPlugin(PVP);
        console.log("mineflayer-pvp успешно загружен");
    } catch (err) {
        console.error("Ошибка загрузки mineflayer-pvp:", err.message);
    }

    startScanningCycle();
    bot.on('chat', (username, message) => {
    if (username === bot.username) return; // Игнорируем собственные сообщения
    console.log(`EVENT message ${username} ${message}`);
    });
});


bot._client.on("hurt_animation", (packet) => {
        const entity = bot.entities[packet.entityId];
        if (!entity || !entity.alive) return;

        // === Проверяем, кто нанёс урон ===
        let aggressor = null;
        if (packet.sourceDirectId && bot.entities[packet.sourceDirectId]) {
            aggressor = bot.entities[packet.sourceDirectId];
        } else if (packet.sourceCauseId && bot.entities[packet.sourceCauseId]) {
            aggressor = bot.entities[packet.sourceCauseId];
        }

        if (!aggressor || !aggressor.alive) return;

        // === Сценарий 1: Бот получил урон → защищаемся ===
        if (aggressor.id !== bot.entity.id && entity.id === bot.entity.id) {
            console.log(`Бот был атакован: ${aggressor.displayName}`);
            startAttack(aggressor);
        }
        // === Сценарий 2: Враг рядом получил урон → атакуем его ===
        else if (aggressor.kind === 'Hostile mobs' || aggressor.type === 'mob') {
            const distance = bot.entity.position.distanceTo(aggressor.position);
            if (distance <= 10) {
                console.log(`Враг рядом получил урон: ${aggressor.displayName}`);
                startAttack(aggressor);
            }
        }
    });


// Обработчики событий pathfinder
bot.on('goal_reached', () => {
    console.log("Цель достигнута!");
    process.stdout.write("EVENT goal_reached\n");
});

bot.on('digging_completed', (block) => {
    console.log(`Копание завершено: ${block.displayName}`);
    process.stdout.write(`EVENT digging_completed ${block.displayName}\n`);
});
bot.on('digging', (block) => {
    console.log(`Начал копать: ${block.displayName}`);
});


// Файл для сохранения данных о блоках
const outputFile = CACHE_FILE;


// === Основная функция сканирования ===
async function scanEnvironmentAsync() {
    const steps = 0.7;
    const maxDistance = 40;

    const yaw = bot.entity.yaw;
    const pitch = bot.entity.pitch;
    const direction = getDirectionVector(yaw, pitch);
    const position = bot.entity.position.offset(0, bot.entity.height, 0);

    const newScanned = {};

    // === Зона 1: центральное зрение (шаг 1°) ===
    await scanZone(position, direction, -10, 10, -10, 10, 1, steps, maxDistance, newScanned);

    // === Зона 2: средняя периферия (шаг 2.5°) ===
    await scanZone(position, direction, -60, 60, -60, -10, 2.5, steps, maxDistance, newScanned);
    await scanZone(position, direction, -60, 60, 10, 60, 2.5, steps, maxDistance, newScanned);
    await scanZone(position, direction, -60, -10, -10, 10, 2.5, steps, maxDistance, newScanned);
    await scanZone(position, direction, 10, 60, -10, 10, 2.5, steps, maxDistance, newScanned);

    // === Зона 3: крайнее периферическое зрение (шаг 5°) ===
    await scanZone(position, direction, -90, 90, -90, -60, 5, steps, maxDistance, newScanned);
    await scanZone(position, direction, -90, 90, 60, 90, 5, steps, maxDistance, newScanned);
    await scanZone(position, direction, -90, -60, -60, 60, 5, steps, maxDistance, newScanned);
    await scanZone(position, direction, 60, 90, -60, 60, 5, steps, maxDistance, newScanned);

    return newScanned;
}

async function scanZone(start, direction, hStart, hEnd, vStart, vEnd, stepAngle, stepRay, maxDistance, output) {
    for (let pitchOffsetDeg = vStart; pitchOffsetDeg <= vEnd; pitchOffsetDeg += stepAngle) {
        for (let yawOffsetDeg = hStart; yawOffsetDeg <= hEnd; yawOffsetDeg += stepAngle) {
            const rotatedDir = rotateDirection(direction, yawOffsetDeg, pitchOffsetDeg);
            castRay(start, rotatedDir, stepRay, maxDistance, output);
        }
        await new Promise(r => setImmediate(r)); // Избегаем блокировки потока
    }
}

function loadEntityCacheFromFile() {
    if (fs.existsSync(ENTITY_FILE)) {
        try {
            const data = fs.readFileSync(ENTITY_FILE, 'utf8');
            entityCache = JSON.parse(data) || {};
        } catch (err) {
            console.error("Ошибка чтения entities.json:", err.message);
        }
    } else {
        fs.writeFileSync(ENTITY_FILE, '{}', 'utf8');
    }
}

function attackEntityByName(displayName) {
    // Ищем ближайшего моба с нужным displayName
    let closestEntity = null;
    let minDistance = Infinity;

    for (const id in bot.entities) {
        const entity = bot.entities[id];

        // Пропускаем самого бота и несуществующие сущности
        if (!entity || entity.id === bot.entity.id) continue;

        // Сравниваем displayName (регистронезависимо)
        if (entity.displayName && entity.displayName.toLowerCase() === displayName.toLowerCase()) {
            const distance = bot.entity.position.distanceTo(entity.position);
            if (distance < minDistance) {
                minDistance = distance;
                closestEntity = entity;
            }
        }
    }

    if (!closestEntity) {
        console.log(`Не найдено сущностей с названием "${displayName}" рядом`);
        return;
    }

    console.log(`Найдена цель: ${closestEntity.displayName} на расстоянии ${minDistance.toFixed(2)} блоков`);

    const sword = bot.inventory.items().find(item => item.name.includes('sword'));

      if (sword) {
        bot.equip(sword, 'hand', (err) => {
          if (err) {
            console.log('Не удалось экипировать меч:', err.message);
          } else {
            console.log(`Меч ${sword.name} экипирован`);
          }})};
    // Устанавливаем цель для pathfinder и начинаем атаку
    currentAggressor = closestEntity;
    const goal = new goals.GoalFollow(closestEntity, 1.0);
    bot.pathfinder.setGoal(goal, true);

    bot.pvp.attack(closestEntity);

    clearInterval(bot._attackInterval);
}

function saveEntityCacheToFile() {
    try {
        fs.writeFileSync(ENTITY_FILE, JSON.stringify(entityCache, null, 2), 'utf8');
    } catch (err) {
        console.error("Ошибка записи entities.json:", err.message);
    }
}

function castRay(start, direction, stepSize, maxDistance, outputBlocks) {
    for (let t = 0; t <= maxDistance; t += stepSize) {
        const x = start.x + direction.x * t;
        const y = start.y + direction.y * t;
        const z = start.z + direction.z * t;

        // Сначала проверяем блоки
        const blockPos = new Vec3(Math.floor(x), Math.floor(y), Math.floor(z));
        if (blockPos.y < 0 || blockPos.y >= 256) continue;
        const block = bot.blockAt(blockPos);
        if (block && block.type !== 0) {
            const key = `${blockPos.x},${blockPos.y},${blockPos.z}`;
            const name = block.displayName || `id:${block.type}`;
            if (!outputBlocks[key]) {
                outputBlocks[key] = name;
            }
            return; // Прерываем луч при нахождении блока
        }

        // Теперь проверяем сущности
        const entities = bot.entities;
        for (const id in entities) {
            const entity = entities[id];
            if (!entity.position) continue;

            const distance = entity.position.distanceTo(new Vec3(x, y, z));
            if (distance < 0.7) {
                const entityType = entity.displayName;
                const uuid = entity.uuid;

                if (!entityType || !uuid) continue;

                // === ИСПРАВЛЕНИЕ ЗДЕСЬ: всегда работаем с объектом ===
                if (!entityCache[entityType]) {
                    entityCache[entityType] = {};
                }

                // Если такой UUID ещё не был добавлен
                if (!entityCache[entityType][uuid]) {
                    entityCache[entityType][uuid] = {
                        x: Math.round(entity.position.x * 10) / 10,
                        y: Math.round(entity.position.y * 10) / 10,
                        z: Math.round(entity.position.z * 10) / 10
                    };
                    saveEntityCacheToFile();
                    console.log(`Обнаружена сущность: ${entityType} | UUID: ${uuid}`);
                }
                return;
            }
        }
    }
}
// Вспомогательные функции

function getDirectionVector(yaw, pitch) {
    const radYaw = toRadians(yaw);
    const radPitch = toRadians(pitch);

    return {
        x: -Math.sin(radYaw) * Math.cos(radPitch),
        y: -Math.sin(radPitch),
        z: Math.cos(radYaw) * Math.cos(radPitch)
    };
}

function rotateDirection(baseDir, yawOffsetDeg, pitchOffsetDeg) {
    const dir = { ...baseDir };

    const yawRad = toRadians(yawOffsetDeg);
    const x = dir.x * Math.cos(yawRad) - dir.z * Math.sin(yawRad);
    const z = dir.x * Math.sin(yawRad) + dir.z * Math.cos(yawRad);
    dir.x = x;
    dir.z = z;

    const pitchRad = toRadians(pitchOffsetDeg);
    const lengthXZ = Math.sqrt(dir.x ** 2 + dir.z ** 2);
    const y = dir.y * Math.cos(pitchRad) - lengthXZ * Math.sin(pitchRad);
    const newLengthXZ = dir.y * Math.sin(pitchRad) + lengthXZ * Math.cos(pitchRad);

    dir.y = y;
    dir.x = (dir.x / lengthXZ) * newLengthXZ;
    dir.z = (dir.z / lengthXZ) * newLengthXZ;

    return normalize(dir);
}


function toRadians(degrees) {
    return degrees * Math.PI / 180;
}

function normalize(v) {
    const length = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
    return {
        x: v.x / length,
        y: v.y / length,
        z: v.z / length
    };
}

// === Логика загрузки/фильтрации/сохранения кэша ===

function loadAllData() {
    try {
        if (fs.existsSync(outputFile)) {
            const data = fs.readFileSync(outputFile, 'utf8');
            return JSON.parse(data) || {};
        }
        return {}; // Если файла нет — пустой кеш
    } catch (err) {
        console.error("❌ Ошибка при чтении кеша:", err.message);
        return {};
    }
}
// === Функция проверки материалов в инвентаре ===
function hasMaterials(bot, requiredItems) {
    for (const itemName in requiredItems) {
        const itemDef = registry?.itemsByName[itemName];
        if (!itemDef) {
            console.log(`[Ошибка] Не найден предмет в mcData: ${itemName}`);
            return false;
        }
        const item = bot.inventory.findInventoryItem(itemDef.id);
        if (!item || item.count < requiredItems[itemName]) {
            console.log(`Не хватает ${itemName}: требуется ${requiredItems[itemName]}, у тебя ${item ? item.count : 0}`);
            return false;
        }
    }
    return true;
}

function findNearbyFreeSpace(bot, distance = 2) {
    const botPos = bot.entity.position;
    const botBlockPos = botPos.offset(0, -bot.entity.height + 1, 0).floored(); // Блок, на котором стоит бот

    for (let x = -distance; x <= distance; x++) {
        for (let y = 1; y <= 3; y++) { // Ищем немного выше
            for (let z = -distance; z <= distance; z++) {
                const testPos = botPos.offset(x, y, z).floored();

                // Пропускаем позицию, где стоит сам бот
                if (testPos.x === botBlockPos.x && testPos.y === botBlockPos.y && testPos.z === botBlockPos.z) {
                    continue;
                }

                const block = bot.blockAt(testPos);
                if (block && block.name === 'air') {
                    const belowPos = testPos.offset(0, -1, 0); // Блок под нами
                    const blockBelow = bot.blockAt(belowPos);

                    // Убеждаемся, что под нами есть твердый блок
                    if (blockBelow && blockBelow.type !== 0 && blockBelow.name !== 'air') {
                        console.log(`Найдено подходящее место для установки: ${testPos}`);
                        return testPos;
                    }
                }
            }
        }
    }

    // Если не нашли места над твердыми блоками — попробуем вокруг
    for (let x = -distance; x <= distance; x++) {
        for (let y = -1; y <= 1; y++) {
            for (let z = -distance; z <= distance; z++) {
                // Пропускаем центральную позицию (где стоит бот)
                if (x === 0 && y === 0 && z === 0) continue;

                const testPos = botPos.offset(x, y, z).floored();
                const block = bot.blockAt(testPos);

                if (block && block.name === 'air') {
                    const belowPos = testPos.offset(0, -1, 0);
                    const blockBelow = bot.blockAt(belowPos);

                    if (blockBelow && blockBelow.type !== 0 && blockBelow.name !== 'air') {
                        console.log(`Найдено свободное место рядом: ${testPos}`);
                        return testPos;
                    }
                }
            }
        }
    }

    console.log("Не найдено подходящего места для установки");
    return null;
}

async function placeBlock(bot, itemName) {
    const itemId = registry.itemsByName[itemName].id;
    if (!itemId) {
        console.log(`Неизвестный предмет: ${itemName}`);
        return;
    }

    const itemInInventory = bot.inventory.findInventoryItem(itemId);
    if (!itemInInventory) {
        console.log(`Нет ${itemName} в инвентаре`);
        return;
    }

    const posToPlace = findNearbyFreeSpace(bot);
    if (!posToPlace) {
        console.log("Нет свободного места рядом для установки");
        return;
    }

    try {
        // Выбираем верстак в руку
        const item = bot.inventory.findInventoryItem(itemId);
        if (!item) {
            console.log("Предмет не найден в инвентаре");
            return;
        }
        await bot.equip(item, 'hand');
        console.log("Предмет взят в руку");

        // Ставим блок
        const belowPos = posToPlace.offset(0, -1, 0);
        const referenceBlock = bot.blockAt(belowPos);

        if (!referenceBlock || referenceBlock.name === 'air') {
            console.log("Невозможно поставить блок: нет твердой поверхности под целевой позицией");
            return;
        }
        await bot.placeBlock(referenceBlock, new Vec3(0, 1, 0));
        console.log(`Установлен ${itemName} на позиции: ${posToPlace}`);
        console.log("EVENT placed");
    } catch (err) {
        console.error("Ошибка при установке блока:", err.message);
    }
}


function filterByRadius(cache, center, radius) {
    const result = {};
    const r2 = radius * radius;
    for (const key in cache) {
        const [x, y, z] = key.split(',').map(Number);
        const dx = x - center.x;
        const dy = y - center.y;
        const dz = z - center.z;
        const distSq = dx * dx + dy * dy + dz * dz;
        if (distSq <= r2) {
            result[key] = cache[key];
        }
    }
    return result;
}

function sendMessageToChat(message) {
    if (!message || typeof message !== 'string') {
        console.log("Сообщение не может быть отправлено: неверный формат");
        return;
    }
    bot.chat(message);
}

function followPlayer(playerName, distance = 2) {
    const player = bot.players[playerName];
    if (!player || !player.entity) {
        console.log(`Игрок ${playerName} не найден или вне зоны видимости.`);
        process.stdout.write(`EVENT player_not_found ${playerName}\n`);
        return;
    }

    const targetPos = player.entity.position.offset(0, -player.entity.height + 1, 0).floored();
    const goal = new goals.GoalNear(targetPos.x, targetPos.y, targetPos.z, distance);
    bot.pathfinder.setGoal(goal);

    console.log(`Бот идёт к игроку ${playerName}...`);

    // После достижения цели — посмотреть на игрока
    const interval = setInterval(() => {
        if (bot.pathfinder.isMoving()) return;

        clearInterval(interval);
        lookAtEntity(player.entity);
    }, 500);
}


function lookAtEntity(entity) {
    if (!entity) {
        console.log("Сущность не найдена.");
        return;
    }

    const center = entity.position.offset(0, entity.height / 2, 0);
    bot.lookAt(center, true);
    console.log(`Посмотрел на игрока ${entity.username || 'неизвестный'}`);
    process.stdout.write(`EVENT looked_at_player ${entity.username}\n`);
}

let currentAggressor = null;


// === Цикл сканирования ===

async function startScanningCycle() {
    while (true) {
        console.log("🔄 Запуск нового сканирования...");

        // Загружаем полный кеш из файла
        const fullCache = loadAllData();
        const currentPos = bot.entity.position;

        // Получаем данные о видимых блоках
        const newScanned = await scanEnvironmentAsync();

        // Фильтруем кеш по радиусу
        const relevantCache = filterByRadius(fullCache, currentPos, SCAN_RADIUS);

        // Определяем изменения
        const added = {};
        const removed = {};

        for (const key in newScanned) {
            if (!(key in relevantCache)) {
                added[key] = newScanned[key];
            }
        }

        for (const key in relevantCache) {
            if (!(key in newScanned)) {
                removed[key] = relevantCache[key];
            }
        }

        // Обновляем релевантную часть кеша
        for (const key in added) relevantCache[key] = added[key];
        for (const key in removed) delete relevantCache[key];

        // Объединяем актуальный кеш с полным
        for (const key in relevantCache) {
            fullCache[key] = relevantCache[key];
        }

        // Сохраняем обновлённый кеш в файл
        try {
            fs.writeFileSync(outputFile, JSON.stringify(fullCache, null, 2));
            console.log(`💾 Данные сохранены в ${outputFile}`);
        } catch (err) {
            console.error("❌ Ошибка при записи кеша:", err.message);
        }

        // Отправляем данные в Python
        const botPosition = bot.entity.position;
        const dataToExport = {
            position: {
                x: Math.floor(botPosition.x),
                y: Math.floor(botPosition.y),
                z: Math.floor(botPosition.z)
            },
            cache: fullCache,
            changes: { added, removed }
        };

        console.log("CACHE_UPDATE"); // Событие для Python
        console.log(JSON.stringify(dataToExport));

        for (const id in bot.entities) {
            const entity = bot.entities[id];

            // Пропускаем игрока
            if (entity.username) continue;

            const entityType = entity.displayName;
            if (!entityType || entityType === 'player') continue;

            const uuid = entity.uuid;
            const pos = entity.position;
            if (!pos) continue;

            // Инициализируем тип моба в кеше, если ещё не было
            if (!entityCache[entityType]) {
                entityCache[entityType] = {};
            }

            // Создаем новую позицию с округлением
            const newPos = {
                x: Math.round(pos.x * 10) / 10,
                y: Math.round(pos.y * 10) / 10,
                z: Math.round(pos.z * 10) / 10
            };

            // Проверяем, есть ли такая запись или изменилась ли позиция
            const existing = entityCache[entityType][uuid];
            if (!existing || existing.x !== newPos.x || existing.y !== newPos.y || existing.z !== newPos.z) {
                entityCache[entityType][uuid] = newPos;
                console.log(`Моб обновлён: ${entityType} | UUID: ${uuid} | Позиция: ${newPos.x}, ${newPos.y}, ${newPos.z}`);
            }
        }

        // === Удаление умерших/исчезнувших мобов ===
        for (const entityType in entityCache) {
            const mobs = entityCache[entityType];
            for (const uuid in mobs) {
                // Проверяем, существует ли такой моб сейчас
                const exists = Object.values(bot.entities).some(e => e.uuid === uuid);
                if (!exists) {
                    delete entityCache[entityType][uuid];
                    console.log(`Моб удалён из кеша: ${entityType} | UUID: ${uuid}`);
                }
            }
            // Удаляем тип моба, если он стал пустым
            if (Object.keys(entityCache[entityType]).length === 0) {
                delete entityCache[entityType];
            }
        }

        // === Сохранение изменений ===
        saveEntityCacheToFile();
        console.log(`💾 Координаты мобов обновлены в ${ENTITY_FILE}`);

        // Пауза между сканированиями
        await new Promise(r => setTimeout(r, 1000)); // 1 секунда
    }
}

// === Обработка остановки через Ctrl+C ===

process.on('SIGINT', () => {
    console.log("\nПолучен сигнал остановки (Ctrl+C). Сохраняем последние данные...");
    process.exit(0);
});


// === В конец файла добавляем обработку stdin ===

process.stdin.on('data', (data) => {
    const command = data.toString().trim();
    handleCommand(command);
});

async function lookAround() {
    const yaw = bot.entity.yaw;
    const pitch = bot.entity.pitch;

    bot.look(yaw, 0, true);

    // === Поворот влево на 70 градусов ===
    for (let i = 1; i <= 110; i++) {
        bot.look(yaw - toRadians(i), pitch, true);
        await new Promise(resolve => setTimeout(resolve, 10)); // 20 мс между шагами
    }

    // === Плавный поворот вправо на 100 градусов (всего от исходного положения) ===
    for (let i = 1; i <= 180; i++) {
        bot.look(yaw - toRadians(110 - i), pitch, true); // уменьшаем угол
        await new Promise(resolve => setTimeout(resolve, 10));
    }

    // === Возврат к исходному направлению ===
    for (let i = 1; i <= 70; i++) {
        bot.look(yaw - toRadians(i), pitch, true);
        await new Promise(resolve => setTimeout(resolve, 10)); // 20 мс между шагами
    }

    console.log("EVENT look_finished"); // сигнал Python-боту
}
function goToPosition(x, y, z) {
    const goal = new goals.GoalBlock(x, y, z, 1);
    bot.pathfinder.setGoal(goal);
}

function clickSlot(bot, slotIndex, mouseButton = 0, mode = 0) {
    return new Promise((resolve) => {
        bot.clickWindow(slotIndex, mouseButton, mode, (err) => {
            if (err) {
                console.error(`Ошибка при клике на слот ${slotIndex}:`, err.message);
                resolve(false);
            } else {
                console.log(`Кликнул на слот ${slotIndex}`);
                resolve(true);
            }
        });
    });
}

function lookAtBlock(x, y, z) {
    const blockPos = new Vec3(x + 0.5, y + 0.5, z + 0.5); // Центр блока
    const position = bot.entity.position.offset(0, bot.entity.height, 0);
    const lookVector = blockPos.minus(position).normalize();

    const yaw = Math.atan2(-lookVector.x, -lookVector.z);
    const pitch = Math.asin(-lookVector.y);

    bot.look(yaw, pitch, true);
    console.log("EVENT look_at_complete"); // <<< НОВАЯ СТРОКА
}
async function digBlock(x, y, z) {
    x = Math.floor(x);
    y = Math.floor(y);
    z = Math.floor(z);

    const pos = new Vec3(x, y, z);
    let block = bot.blockAt(pos);

    if (!block || block.type === 0 || block.name === 'air') {
        console.log(`[digBlock] ❌ Блок не найден или это воздух: ${x}, ${y}, ${z}`);
        process.stdout.write("EVENT digging_completed air\n");
        return;
    }

    console.log(`[digBlock] Найден блок: ${block.displayName} (${block.name})`);

    // Поворачиваемся на блок
    const center = block.position.offset(0.5, 0.5, 0.5);
    await bot.lookAt(center, true);

    console.log(`[digBlock] 💣 Начинаем копание: ${block.displayName}`);
    await bot.dig(block);
    console.log(`[digBlock] 🎯 Блок успешно сломан: ${block.displayName}`);

    // УДАЛЯЕМ СЛОМАННЫЙ БЛОК ИЗ КЕША
    const key = `${x},${y},${z}`;
    try {
        const fullCache = loadAllData(); // Загружаем текущий кеш
        delete fullCache[key]; // Удаляем сломанный блок

        fs.writeFileSync(outputFile, JSON.stringify(fullCache, null, 2)); // Перезаписываем файл
        console.log(`[digBlock] 🔥 Блок удалён из кеша: ${key}`);
    } catch (err) {
        console.error(`[digBlock] Ошибка при обновлении кеша:`, err.message);
    }

    process.stdout.write(`EVENT digging_completed ${block.displayName}\n`);
}

let lastInventoryState = {};

function sendInventoryUpdate() {
    if (!registry) {
        console.log("mcData ещё не загружен. Пропускаем обновление инвентаря.");
        return;
    }

    const inventory = {};
    for (const item of bot.inventory.items()) {
        const itemName = registry.items[item.type]?.name || `unknown_${item.type}`;
        inventory[itemName] = item.count;
    }

    // Проверяем, изменился ли инвентарь
    const inventoryChanged = JSON.stringify(inventory) !== JSON.stringify(lastInventoryState);

    if (inventoryChanged) {
        console.log("INVENTORY_UPDATE");
        console.log(JSON.stringify(inventory));
        lastInventoryState = { ...inventory }; // Сохраняем новое состояние
    }
}

async function requiresWorkbench(bot, itemName) {
    const itemEntry = registry.itemsByName[itemName];
    if (!itemEntry) {
        console.log(`Неизвестный предмет для проверки верстака: ${itemName}`);
        return false;
    }

    const itemId = itemEntry.id;
    const recipesList = await bot.recipesAll(itemId, null, null); // все рецепты

    if (!recipesList || recipesList.length === 0) {
        console.log(`Нет рецептов для предмета: ${itemName}`);
        return false;
    }

    return recipesList.some(recipe => recipe.requiresTable);
}

async function handleCommand(cmd) {
    const args = cmd.trim().split(' ');
    switch (args[0]) {
        case 'look_around':
            lookAround();
            break;

        case 'goto':
            if (args.length === 4) {
                const x = parseInt(args[1]);
                const y = parseInt(args[2]);
                const z = parseInt(args[3]);
                goToPosition(x, y, z);
            }
            break;

        case 'craft':
            if (args.length < 3) {
                console.log("Использование: craft <item_name> <count>");
                return;
            }
            const itemName = args[1];
            const itemcount = args[2];
            const itemEntry = registry.itemsByName[itemName].id
            // Сначала проверяем, можно ли скрафтить без верстака
            const ItemRecipe = await Recipe.find(itemEntry)
            const isTableNeed = await ItemRecipe[0]["requiresTable"];
            if (isTableNeed) {
                const table = bot.findBlock({
                    matching: registry.blocksByName.crafting_table.id,
                    maxDistance: 5
                });

                if (!table) {
                    console.log("Верстак не найден рядом");
                    return;
                }

                // Подходим к верстаку
                await bot.pathfinder.goto(new goals.GoalBlock(table.position.x, table.position.y, table.z));

                if (ItemRecipe && ItemRecipe.length > 0) {
                    console.log(`Крафтим ${itemName} на верстаке`);
                    await bot.craft(ItemRecipe[0], 1, table);
                    console.log("EVENT crafted_successfully");
                } else {
                    console.log(`Нет доступных рецептов для ${itemName} на верстаке`);
                    return;
                    }
                }
            else{
                console.log(`Крафтим ${itemName} без верстака`);
                try {
                    await bot.craft(ItemRecipe[0], itemcount, null);
                } catch (err) {
                console.error("Ошибка при крафте:", err.message);
                process.stdout.write(`EVENT craft_error ${err.message}\n`);
                await bot.craft(ItemRecipe[1], itemcount, null);
                }
                console.log("EVENT crafted_successfully");
            }
            break;

        case 'look_at':
            if (args.length === 4) {
                const x = parseInt(args[1]);
                const y = parseInt(args[2]);
                const z = parseInt(args[3]);
                lookAtBlock(x, y, z);
            }
            break;

        case 'dig':
            if (args.length === 4) {
                const x = parseInt(args[1]);
                const y = parseInt(args[2]);
                const z = parseInt(args[3]);
                digBlock(x, y, z);
            }
            break;

        case 'place':
            if (args.length < 2) {
                console.log("Использование: place <item_name>");
                return;
            }
            const itemNamePlace = args[1];
            placeBlock(bot, itemNamePlace);
            break;

        case 'shutdown':
            console.log("Получена команда shutdown: бот выключается");
            bot.chat("Нет, иди нахуй");
            bot.quit("");
            break;

        case 'testdig':
            if (args.length === 4) {
                const x = parseInt(args[1]);
                const y = parseInt(args[2]);
                const z = parseInt(args[3]);
                await digBlock(x, y, z);
            }
            break;

        case 'stop_kill':
            if (currentAggressor) {
                bot.pvp.stop();
                bot.pathfinder.setGoal(null);
                currentAggressor = null;
                isHunting=false;
                console.log("Атака прекращена");
            } else {
                console.log("Нет активной цели для атаки");
            }
            break;

        case 'toss':
            if (args.length === 2){
            const itemEntry = registry.itemsByName[args[1]].id
            bot.toss(itemEntry, null, 1)
            }
            break;

        case 'say':
            if (args.length < 2) {
                console.log("Использование: say <сообщение>");
                return;
            }
            const messageToSend = args.slice(1).join(' ');
            sendMessageToChat(messageToSend);
            console.log("EVENT said");
            break;

        case 'follow':
            if (args.length < 2) {
                console.log("Использование: follow <имя_игрока>");
                return;
            }
            const playerName = args[1];
            followPlayer(playerName);
            break;

        case 'kill':
            if (args.length < 3) {
                console.log("Использование: kill <entityDisplayName> <количество>");
                return;
            }
            isHunting = true;
            const targetName = args[1];
            const repetitions = args[2];
            if (repetitions>0){
                let count = 0;

                function loop() {
                    if (count >= repetitions) return;
                    attackEntityByName(targetName);
                    count++;
                    if (isHunting===false){return false;}
                    setTimeout(loop, 15000);
                    }

                loop();
                }
            else{
                const intervalId = setInterval(() => {
                    if (isHunting===false){clearInterval(intervalId);}
                    attackEntityByName(targetName);
                }, 2000);
            }
                break;




        default:
            console.log(`Неизвестная команда: ${cmd}`);
    }
}