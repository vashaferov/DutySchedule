#!/usr/bin/env node
/**
 * Регрессионный тест на XSS: проверяет, что функции рендера из frontend/index.html
 * экранируют данные, пришедшие из БД (даты, имена, названия песен, цвета).
 *
 * Запуск:            node tests/frontend/xss.test.js
 * Другой файл:       node tests/frontend/xss.test.js path/to/index.html
 * Без зависимостей — работает на голом Node (есть на раннерах GitHub Actions).
 */
'use strict';

const fs = require('fs');
const path = require('path');

const DEFAULT_INDEX = path.join(__dirname, '..', '..', 'frontend', 'index.html');
const INDEX_HTML = process.argv[2] ? path.resolve(process.argv[2]) : DEFAULT_INDEX;
const src = fs.readFileSync(INDEX_HTML, 'utf8');

/** Вырезает исходник функции вместе с телом по балансу фигурных скобок. */
function extractFunction(source, name) {
  const start = source.indexOf('function ' + name + '(');
  if (start === -1) {
    throw new Error('Не найдена функция ' + name + ' в ' + INDEX_HTML);
  }
  let depth = 0;
  for (let i = source.indexOf('{', start); i < source.length; i++) {
    const ch = source[i];
    if (ch === '{') depth++;
    else if (ch === '}') {
      depth--;
      if (depth === 0) return source.slice(start, i + 1);
    }
  }
  throw new Error('Не сбалансированы скобки в функции ' + name);
}

const NEEDED = [
  'escapeHtml',
  'formatDateDisplay',
  'getActionHTML',
  'buildCardsHTML',
  'buildRepertoireTableHTML',
];

// 0. Инлайновый скрипт целиком должен парситься. Проверка нужна потому, что
//    ниже мы вырезаем отдельные функции: опечатка в любом другом месте
//    index.html иначе осталась бы незамеченной.
const inlineStart = src.indexOf('<script>', src.indexOf('</script>'));
const inlineEnd = src.lastIndexOf('</script>');
if (inlineStart === -1 || inlineEnd === -1 || inlineEnd < inlineStart) {
  console.error('FAIL не найден инлайновый <script> в ' + INDEX_HTML);
  process.exit(1);
}
const inlineScript = src.slice(inlineStart + '<script>'.length, inlineEnd);
try {
  new Function(inlineScript);
  console.log('ok   инлайновый скрипт парсится');
} catch (err) {
  console.error('FAIL синтаксис инлайнового скрипта: ' + err.message);
  process.exit(1);
}

const code = NEEDED.map((name) => extractFunction(src, name)).join('\n\n');
const factory = new Function(
  'MAX_PER_DAY',
  'currentUser',
  'isAdmin',
  code + '\nreturn { buildCardsHTML: buildCardsHTML, buildRepertoireTableHTML: buildRepertoireTableHTML };'
);
const render = factory(2, 'admin', true);

// Полезные нагрузки, которые при отсутствии экранирования выполнились бы как разметка.
const PAYLOADS = {
  date: '10.10.2026 (<img src=x onerror=alert(1)>)',
  name: '<img src=x onerror=alert(2)>',
  song: '</span><script>alert(3)</script>',
  color: 'red" onmouseover="alert(4)',
};

// Теги, которые функции рендера действительно создают. Всё остальное — инъекция.
const ALLOWED_TAGS = new Set([
  'div', 'span', 'button', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'br',
]);

let failures = 0;

function check(label, html, payloads) {
  const problems = [];

  // 1. Ни одна полезная нагрузка не должна попасть в разметку в исходном виде.
  //    После экранирования < > " & ' превращаются в сущности, и строка не совпадёт.
  payloads.forEach((p) => {
    if (html.includes(p)) problems.push('полезная нагрузка не экранирована: ' + p);
  });

  // 2. Никаких тегов, которых рендер не создаёт.
  for (const m of html.matchAll(/<\s*([a-zA-Z][a-zA-Z0-9]*)/g)) {
    if (!ALLOWED_TAGS.has(m[1].toLowerCase())) problems.push('лишний тег <' + m[1] + '>');
  }

  if (problems.length > 0) {
    failures++;
    console.error('FAIL ' + label);
    problems.forEach((p) => console.error('       - ' + p));
    console.error('       вывод: ' + html.replace(/\s+/g, ' ').slice(0, 240));
  } else {
    console.log('ok   ' + label);
  }
  return html;
}

// --- Карточки графика -------------------------------------------------------
const cardsHtml = check(
  'buildCardsHTML: дата + имя дежурного',
  render.buildCardsHTML(
    [{ dateStr: PAYLOADS.date, names: [PAYLOADS.name], matrixRow: [true] }],
    false
  ),
  [PAYLOADS.date, PAYLOADS.name]
);

// --- Таблица репертуара -----------------------------------------------------
check(
  'buildRepertoireTableHTML: дата + песня + цвет',
  render.buildRepertoireTableHTML(
    [{ dateStr: PAYLOADS.date, songs: [{ name: PAYLOADS.song, text: 'текст' }], colors: [PAYLOADS.color] }],
    false
  ),
  [PAYLOADS.date, PAYLOADS.song, PAYLOADS.color]
);

// --- Обычные данные не должны пострадать ------------------------------------
const plain = render.buildCardsHTML(
  [{ dateStr: '10.10.2026 (утро 10-12)', names: ['Слава'], matrixRow: [true] }],
  false
);
if (!plain.includes('10.10.2026 (утро 10-12)') || !plain.includes('Слава')) {
  failures++;
  console.error('FAIL обычные данные отрисовались неверно');
} else {
  console.log('ok   обычные данные не пострадали');
}

// --- data-атрибуты должны декодироваться обратно в исходное значение --------
// Иначе обработчики кликов не найдут дату/песню через dataset.
const expectedAttr = PAYLOADS.date
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');
if (!cardsHtml.includes('data-date="' + expectedAttr + '"')) {
  failures++;
  console.error('FAIL data-date не соответствует ожидаемому экранированию');
} else {
  console.log('ok   data-date экранирован предсказуемо');
}

if (failures > 0) {
  console.error('\nПровалено проверок: ' + failures);
  process.exit(1);
}
console.log('\nXSS-проверки фронтенда пройдены.');
