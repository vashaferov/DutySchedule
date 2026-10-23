#!/usr/bin/env node
/**
 * Регрессионный тест на XSS для фронтенда.
 *
 * Проверяет, что клиентский рендер экранирует пользовательские данные
 * (даты, имена, песни, цветовые метки) перед вставкой в HTML.
 *
 * Запуск: node tests/frontend/xss.test.js [path/to/index.html]
 */
'use strict';

const fs = require('fs');
const path = require('path');

const INDEX_HTML = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(__dirname, '..', '..', 'frontend', 'index.html');
const APP_JS = path.join(path.dirname(INDEX_HTML), 'app.js');

const indexSrc = fs.readFileSync(INDEX_HTML, 'utf8');
const appSrc = fs.readFileSync(APP_JS, 'utf8');

function extractFunction(source, name) {
  const start = source.indexOf('function ' + name + '(');
  if (start === -1) throw new Error('Не найдена функция ' + name + ' в ' + APP_JS);
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i += 1) {
    if (source[i] === '{') depth += 1;
    else if (source[i] === '}') {
      depth -= 1;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error('Не найден конец функции ' + name);
}

let failures = 0;
const ok = (label) => console.log('ok   ' + label);
const fail = (label, detail) => {
  failures += 1;
  console.error('FAIL ' + label);
  if (detail) console.error('       - ' + detail);
};
const check = (condition, label, detail) => {
  if (condition) ok(label);
  else fail(label, detail);
};

// 0. Инлайновый скрипт вынесен в app.js, он должен подключаться и парситься.
check(/src="app\.js(\?[^"]*)?"/.test(indexSrc), 'index.html подключает app.js');
try {
  new Function(appSrc);
  ok('app.js парсится');
} catch (err) {
  fail('app.js не парсится', err.message);
}

const PAYLOADS = {
  date: '10.10.2026 (<img src=x onerror=alert(1)>)',
  name: '<img src=x onerror=alert(2)>',
  song: '</span><script>alert(3)</script>',
  color: 'red" onmouseover="alert(4)',
  title: '<img src=x onerror=alert(5)>',
  text: '</p><script>alert(6)</script>',
};

const escSrc = extractFunction(appSrc, 'esc');
const esc = new Function(escSrc + '\nreturn esc;')();

// 1. esc экранирует все спецсимволы HTML.
for (const [key, value] of Object.entries(PAYLOADS)) {
  const escaped = esc(value);
  check(!escaped.includes(value), 'esc экранирует payload: ' + key);
  check(/[<>]/.test(escaped) === false, 'esc не оставляет угловые скобки: ' + key);
}

// 2. Обычный текст не должен меняться.
check(esc('Великий Бог') === 'Великий Бог', 'esc сохраняет обычный текст');
check(esc('10.10.2026 (утро 10-12)') === '10.10.2026 (утро 10-12)', 'esc сохраняет дату с пояснением');

// 3. Кавычки экранируются для data-атрибутов.
const attr = esc(PAYLOADS.color);
check(attr.includes('&quot;'), 'кавычки экранируются для data-атрибутов');
check(!attr.includes('onmouseover="'), 'инъекция атрибута не проходит');

// 4. emptyState экранирует заголовок и текст.
const emptyStateSrc = extractFunction(appSrc, 'emptyState');
const emptyState = new Function('esc', 'icon', emptyStateSrc + '\nreturn emptyState;')(esc, () => '<svg></svg>');
const emptyHtml = emptyState('calendar', PAYLOADS.title, PAYLOADS.text, '');
check(!emptyHtml.includes(PAYLOADS.title), 'emptyState экранирует заголовок');
check(!emptyHtml.includes(PAYLOADS.text), 'emptyState экранирует текст');
check(!/<script|<img/i.test(emptyHtml), 'emptyState не создаёт опасные теги');

// 5. dateCard экранирует дату и пояснение (payload проходит через noteFromRaw).
const dateCardSrc = extractFunction(appSrc, 'dateCard');
const dateCard = new Function(
  'MAX_PER_DAY', 'esc', 'icon', 'safeTone', 'noteFromRaw', 'formatFull', 'weekday',
  'formatShort', 'dayNumber', 'monthShort', 'isAdmin', 'dutyChips', 'repSection', 'plural',
  dateCardSrc + '\nreturn dateCard;'
)(
  2, esc, () => '<svg></svg>', () => 'steel', (raw) => raw, () => 'Дата',
  () => 'Воскресенье', () => '10.10.2026', () => '10', () => 'окт',
  () => false, () => '', () => '', () => 'мест'
);
const cardHtml = dateCard({
  date: '2026-10-10',
  raw: PAYLOADS.date,
  color: 'steel',
  duties: [],
  songs: [],
});
check(!cardHtml.includes(PAYLOADS.date), 'dateCard экранирует дату и пояснение');
check(!/<script|<img/i.test(cardHtml), 'dateCard не создаёт опасные теги');
check(cardHtml.includes('10.10.2026'), 'dateCard отображает дату');

if (failures > 0) {
  console.error('\nПровалено проверок: ' + failures);
  process.exit(1);
}
console.log('\nXSS-проверки фронтенда пройдены.');
