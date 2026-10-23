'use strict';

/* =========================================================================
   MediaHLG · график дежурств и репертуар
   Клиентская логика SPA: API, рендер, роли, темы и адаптивные сценарии.
   ========================================================================= */

/* ---------- Константы ---------- */
const TODAY = (() => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
})();

const TONES = ['steel', 'amber', 'coral', 'slate', 'blue'];
const TONE_COLORS = {
  steel: '#42617d',
  amber: '#a97420',
  coral: '#b65a3f',
  slate: '#6f8092',
  blue: '#4d74a0',
};

const USER_PALETTE = [
  '#3f5b78', '#56749a', '#4e7699', '#5b728c',
  '#6f7c8a', '#8a7448', '#a86754', '#8f7550',
];

let USERS = [];
let SYNC_HISTORY = [];

/* ---------- Утилиты ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];
const MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function icon(name, cls = '') {
  return `<svg class="icon ${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

function plural(n, forms) {
  const num = Math.abs(n) % 100;
  const last = num % 10;
  if (num > 10 && num < 20) return forms[2];
  if (last > 1 && last < 5) return forms[1];
  if (last === 1) return forms[0];
  return forms[2];
}

function parseIso(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function capitalize(str) {
  return str ? str.charAt(0).toUpperCase() + str.slice(1) : str;
}

function weekday(iso) {
  return capitalize(new Intl.DateTimeFormat('ru-RU', { weekday: 'long' }).format(parseIso(iso)));
}

function formatFull(iso) {
  const d = parseIso(iso);
  return `${weekday(iso)}, ${d.getDate()} ${MONTHS_GEN[d.getMonth()]}`;
}

function formatShort(iso) {
  const d = parseIso(iso);
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}

function dayNumber(iso) {
  return String(parseIso(iso).getDate()).padStart(2, '0');
}

function monthShort(iso) {
  return MONTHS_SHORT[parseIso(iso).getMonth()];
}

function daysFromToday(iso) {
  const diff = Date.parse(iso + 'T00:00:00Z') - Date.parse(TODAY + 'T00:00:00Z');
  return Math.round(diff / 86400000);
}

function relativeDays(iso) {
  const n = daysFromToday(iso);
  if (n === 0) return 'сегодня';
  if (n === 1) return 'завтра';
  if (n > 1) return `через ${n} ${plural(n, ['день', 'дня', 'дней'])}`;
  const past = Math.abs(n);
  return `${past} ${plural(past, ['день', 'дня', 'дней'])} назад`;
}

function formatPeriod(list) {
  if (!list.length) return 'График дежурств';
  const first = parseIso(list[0].date);
  const last = parseIso(list[list.length - 1].date);
  if (Number.isNaN(first.getTime()) || Number.isNaN(last.getTime())) return 'График дежурств';
  const firstMonth = capitalize(MONTHS_GEN[first.getMonth()]);
  const lastMonth = capitalize(MONTHS_GEN[last.getMonth()]);
  if (first.getFullYear() === last.getFullYear()) {
    if (first.getMonth() === last.getMonth()) return `${firstMonth} ${first.getFullYear()}`;
    return `${firstMonth} — ${lastMonth} ${first.getFullYear()}`;
  }
  return `${firstMonth} ${first.getFullYear()} — ${lastMonth} ${last.getFullYear()}`;
}

function initials(name) {
  const parts = String(name).trim().split(/\s+/);
  if (parts.length > 1) return (parts[0][0] + parts[1][0]).toUpperCase();
  return String(name).slice(0, 2);
}

function userById(id) {
  return USERS.find((u) => u.id === id) || null;
}

function noteFromRaw(raw) {
  const m = String(raw).match(/\(([^)]+)\)/);
  return m ? m[1].trim() : '';
}

function dateFromRaw(raw) {
  const m = String(raw).match(/(\d{2})\.(\d{2})\.(\d{4})/);
  if (!m) return null;
  const iso = `${m[3]}-${m[2]}-${m[1]}`;
  return Number.isNaN(parseIso(iso).getTime()) ? null : iso;
}

function safeTone(tone) {
  return TONES.includes(tone) ? tone : 'steel';
}

function datesForSong(songId) {
  return state.dates.filter((d) => d.songs.includes(songId));
}

function songById(id) {
  return state.songs.find((s) => s.id === id) || null;
}

function dateById(id) {
  return state.dates.find((d) => d.id === id) || null;
}

function sortByDateAsc(a, b) {
  return a.date.localeCompare(b.date);
}

function sortByDateDesc(a, b) {
  return b.date.localeCompare(a.date);
}

function isPast(d) {
  return d.date < TODAY;
}

function upcomingDates() {
  return state.dates.filter((d) => !isPast(d)).sort(sortByDateAsc);
}

function archiveDates() {
  return state.dates.filter(isPast).sort(sortByDateDesc);
}

function readStore(key, fallback = null) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch (e) {
    return fallback;
  }
}

function writeStore(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch (e) { /* storage disabled */ }
}

/* ---------- Цвета и данные ---------- */
function hashString(value) {
  let hash = 0;
  for (let i = 0; i < String(value).length; i += 1) {
    hash = ((hash << 5) - hash + String(value).charCodeAt(i)) | 0;
  }
  return Math.abs(hash);
}

function colorForName(name) {
  return USER_PALETTE[hashString(name) % USER_PALETTE.length];
}

function toneForName(name) {
  return TONES[hashString('tone:' + name) % TONES.length];
}

function toneFromHex(value) {
  const match = String(value || '').trim().match(/^#?([0-9a-f]{6})$/i);
  if (!match) return null;
  const hex = match[1];
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  let best = null;
  let bestDistance = Infinity;
  TONES.forEach((tone) => {
    const toneHex = TONE_COLORS[tone].slice(1);
    const tr = parseInt(toneHex.slice(0, 2), 16);
    const tg = parseInt(toneHex.slice(2, 4), 16);
    const tb = parseInt(toneHex.slice(4, 6), 16);
    const distance = (r - tr) ** 2 + (g - tg) ** 2 + (b - tb) ** 2;
    if (distance < bestDistance) {
      best = tone;
      bestDistance = distance;
    }
  });
  return best;
}

function toneForDate(raw, colors) {
  const firstColor = Array.isArray(colors) ? colors.find((color) => toneFromHex(color)) : null;
  return (firstColor && toneFromHex(firstColor)) || toneForName(raw);
}

function normalizeRepertoireSongs(entry) {
  const songs = entry && Array.isArray(entry.songs) ? entry.songs : [];
  return songs
    .map((song) => (typeof song === 'string' ? song : song && (song.name || song.song_name)))
    .filter(Boolean);
}

function mapSyncRow(row) {
  const status = String(row.status || '').toLowerCase();
  const started = row.started_at ? new Date(row.started_at) : null;
  const finished = row.finished_at ? new Date(row.finished_at) : null;
  let duration = '—';
  if (started && finished && !Number.isNaN(started.getTime()) && !Number.isNaN(finished.getTime())) {
    duration = ((finished - started) / 1000).toFixed(1).replace('.', ',') + ' с';
  }
  const date = started && !Number.isNaN(started.getTime()) ? started : finished;
  const at = date && !Number.isNaN(date.getTime())
    ? new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
      }).format(date)
    : '—';
  return {
    at,
    by: row.triggered_by || 'Автосинхронизация',
    changes: row.changes_summary || 'Без изменений',
    duration,
    status: status === 'error' ? 'error' : (status === 'success' || status === 'ok' ? 'ok' : 'skip'),
    note: row.details || '',
  };
}

async function loadLoginUsers() {
  const data = await apiJson('/auth/getUserNames');
  state.loginUsers = Array.isArray(data.names) ? data.names : [];
  if (!state.loginUser || !state.loginUsers.includes(state.loginUser)) {
    state.loginUser = state.loginUsers[0] || null;
  }
}

async function loadData() {
  state.loading = true;
  const [matrix, repData] = await Promise.all([
    apiJson('/duty/matrix'),
    apiJson('/repertoire/'),
  ]);
  let songsData = [];
  try {
    songsData = await apiJson('/songs/');
  } catch (e) {
    songsData = [];
  }

  if (!matrix || !Array.isArray(matrix.dates) || !Array.isArray(matrix.names) || !Array.isArray(matrix.matrix)) {
    throw new Error('Некорректный ответ загрузки графика');
  }

  let adminUsers = [];
  if (isAdmin()) {
    try {
      const usersData = await apiJson('/users/');
      adminUsers = Array.isArray(usersData) ? usersData : (usersData.users || []);
    } catch (e) {
      adminUsers = [];
    }
  }
  const roleByName = new Map(adminUsers.map((user) => [user.name, user.role]));
  const allNames = matrix.names.slice();
  if (state.currentUserId && !allNames.includes(state.currentUserId)) allNames.push(state.currentUserId);
  state.loginUsers = allNames.slice();
  if (!state.loginUser || !state.loginUsers.includes(state.loginUser)) {
    state.loginUser = state.loginUsers[0] || null;
  }
  USERS = allNames.map((name) => ({
    id: name,
    name,
    role: roleByName.get(name) || (name === state.currentUserId ? state.role : 'user'),
    color: colorForName(name),
    last: 'PIN защищён',
  }));

  const songsByName = new Map();
  const songs = Array.isArray(songsData) ? songsData : (songsData && Array.isArray(songsData.songs) ? songsData.songs : []);
  songs.forEach((song) => {
    const name = song.name || song.title;
    if (!name) return;
    songsByName.set(name, {
      id: name,
      title: name,
      text: song.text || '',
      color: toneForName(name),
    });
  });

  const repertoire = repData && typeof repData === 'object' && !Array.isArray(repData) ? repData : {};
  const dates = matrix.dates.map((raw, index) => {
    const entry = repertoire[raw] || {};
    const songsForDate = normalizeRepertoireSongs(entry);
    songsForDate.forEach((name) => {
      if (!songsByName.has(name)) {
        songsByName.set(name, {
          id: name,
          title: name,
          text: '',
          color: toneForName(name),
        });
      }
    });
    return {
      id: raw,
      raw,
      date: dateFromRaw(raw) || raw,
      color: toneForDate(raw, entry.colors, index),
      duties: matrix.names.filter((name, userIndex) => Boolean(matrix.matrix[index] && matrix.matrix[index][userIndex])),
      songs: songsForDate,
    };
  }).filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date.date));

  dates.sort(sortByDateAsc);
  state.dates = dates;
  state.songs = Array.from(songsByName.values()).sort((a, b) => a.title.localeCompare(b.title, 'ru'));

  if (state.personFilter && !USERS.some((user) => user.id === state.personFilter)) state.personFilter = '';
  if (!state.openReps.size) {
    const next = dates.find((date) => !isPast(date));
    if (next) state.openReps.add(next.id);
  } else {
    const ids = new Set(dates.map((date) => date.id));
    state.openReps.forEach((id) => { if (!ids.has(id)) state.openReps.delete(id); });
  }

  if (isAdmin()) {
    try {
      const history = await apiJson('/sync/history');
      SYNC_HISTORY = (Array.isArray(history) ? history : []).map(mapSyncRow);
    } catch (e) {
      SYNC_HISTORY = [];
    }
  } else {
    SYNC_HISTORY = [];
  }
  state.lastSync = SYNC_HISTORY[0] ? SYNC_HISTORY[0].at : 'нет данных';
  state.nextSync = 60;
  state.loading = false;
  state.loadError = '';
}

async function refreshData(options = {}) {
  const { silent = true } = options;
  try {
    await loadData();
    renderAll();
  } catch (e) {
    state.loading = false;
    state.loadError = e.message;
    if (!silent) toast(e.message, 'error');
    renderAll();
  }
}

async function bootstrap() {
  try {
    await loadLoginUsers();
  } catch (e) {
    state.loginUsers = [];
  }

  if (authToken) {
    try {
      const resp = await fetch(API_BASE + '/auth/me', {
        headers: { Authorization: 'Bearer ' + authToken },
      });
      if (resp.ok) {
        const me = await resp.json();
        state.role = me.role === 'admin' ? 'admin' : 'user';
        state.currentUserId = me.name;
        state.loginUser = me.name;
      } else {
        clearSession();
      }
    } catch (e) {
      clearSession();
    }
  }

  try {
    await loadData();
  } catch (e) {
    state.loading = false;
    state.loadError = e.message;
    toast('Не удалось загрузить данные: ' + e.message, 'error');
  }

  renderAll();
  const hash = (location.hash || '').replace('#', '');
  let page = PAGE_META[hash] ? hash : 'schedule';
  if ((page === 'users' || page === 'sync') && !isAdmin()) page = 'schedule';
  if (!location.hash) history.replaceState(null, '', '#schedule');
  go(page, { push: false, silent: true });
}

function toast(message, type = 'success') {
  const box = $('#toasts');
  if (!box) return;
  while (box.querySelectorAll('.toast:not(.toast--out)').length >= 3) {
    box.querySelector('.toast:not(.toast--out)')?.remove();
  }
  const el = document.createElement('div');
  el.className = 'toast toast--' + type;
  el.innerHTML = `${icon(type === 'error' ? 'alert' : type === 'info' ? 'info' : 'check')}<span>${esc(message)}</span>`;
  box.appendChild(el);
  setTimeout(() => {
    el.classList.add('toast--out');
    setTimeout(() => el.remove(), 200);
  }, 3200);
}

/* ---------- API ---------- */
const API_BASE = typeof API_URL === 'string' ? API_URL : '/api';
let authToken = readStore('currentUserToken', '') || '';

async function parseApiError(resp) {
  try {
    const data = await resp.json();
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => item.msg || item.detail || '').filter(Boolean).join('; ');
    }
    return data.error || data.message || 'Ошибка запроса';
  } catch (e) {
    return `Ошибка запроса (${resp.status})`;
  }
}

async function apiFetch(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  const resp = await fetch(API_BASE + path, Object.assign({}, options, { headers }));
  if (resp.status === 401 && authToken) {
    handleSessionExpired();
  }
  if (!resp.ok) throw new Error(await parseApiError(resp));
  return resp;
}

async function apiJson(path, options = {}) {
  const resp = await apiFetch(path, options);
  return resp.json();
}

function setSession(name, role, token) {
  authToken = token || '';
  state.role = role === 'admin' ? 'admin' : 'user';
  state.currentUserId = name || null;
  state.loginUser = name || null;
  writeStore('currentUserToken', authToken);
  writeStore('currentUser', name || '');
  writeStore('currentUserRole', state.role);
}

function clearSession() {
  authToken = '';
  state.role = 'guest';
  state.currentUserId = null;
  state.lastSync = 'нет данных';
  state.nextSync = 60;
  SYNC_HISTORY = [];
  writeStore('currentUserToken', null);
  writeStore('currentUser', null);
  writeStore('currentUserRole', null);
  writeStore('currentUserPin', null);
}

function handleSessionExpired() {
  if (!authToken) return;
  clearSession();
  toast('Сессия истекла, войдите заново', 'error');
  renderAll();
  if (state.page === 'users' || state.page === 'sync') go('schedule', { push: true, silent: true });
  openLogin();
}

/* ---------- Состояние ---------- */
const state = {
  role: 'guest',
  currentUserId: null,
  page: 'schedule',
  dates: [],
  songs: [],
  theme: readStore('theme', null) || document.documentElement.dataset.theme || 'light',
  scheduleTab: 'upcoming',
  datePage: 1,
  personFilter: '',
  openReps: new Set(),
  songsQuery: '',
  songsFilter: 'all',
  songsSort: 'title',
  songPage: 1,
  selectedSongId: null,
  syncing: false,
  nextSync: 60,
  lastSync: 'нет данных',
  loginUser: null,
  loginUsers: [],
  dateDraft: null,
  editingSongId: null,
  pinUserId: null,
  confirmAction: null,
  loading: true,
  loadError: '',
};

const PAGE_META = {
  schedule: { title: 'График дежурств' },
  songs: { title: 'Песни' },
  stats: { title: 'Статистика' },
  users: { title: 'Пользователи' },
  sync: { title: 'Синхронизация' },
};

function currentUser() {
  return state.currentUserId ? userById(state.currentUserId) : null;
}

function isAdmin() {
  return state.role === 'admin';
}

function isLoggedIn() {
  return state.role === 'user' || state.role === 'admin';
}

/* ---------- Маршрутизация ---------- */
function go(page, options = {}) {
  const { push = true, silent = false } = options;
  let target = PAGE_META[page] ? page : 'schedule';
  if ((target === 'users' || target === 'sync') && !isAdmin()) {
    target = 'schedule';
    if (!silent) toast('Раздел доступен только администратору', 'error');
  }
  state.page = target;

  $$('.page').forEach((el) => el.classList.toggle('active', el.id === 'page-' + target));
  $$('[data-page]').forEach((el) => el.classList.toggle('active', el.dataset.page === target));
  const title = $('#page-title');
  if (title) title.textContent = PAGE_META[target].title;

  const addBtn = $('#topbar-add');
  if (addBtn) addBtn.hidden = !(target === 'schedule' && isAdmin());

  if (push && location.hash !== '#' + target) {
    history.pushState(null, '', '#' + target);
  }

  if (target === 'songs') renderSongs();
  if (target === 'stats') renderStats();
  if (target === 'users') renderUsers();
  if (target === 'sync') renderSync();

  closeSidebar();
  window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
}

/* ---------- Роль и профиль ---------- */
function applyRole() {
  document.body.classList.toggle('role-admin', isAdmin());
  document.body.classList.toggle('role-user', state.role === 'user');
  document.body.classList.toggle('role-guest', state.role === 'guest');
  $$('.admin-only').forEach((el) => {
    if (el.closest('#profile-popover')) return;
    el.hidden = !isAdmin();
  });

  const addBtn = $('#topbar-add');
  if (addBtn) addBtn.hidden = !(state.page === 'schedule' && isAdmin());
}

function renderProfile() {
  const user = currentUser();
  const avatar = $('#profile-avatar');
  const nameEl = $('#profile-name');
  const roleEl = $('#profile-role');
  const popover = $('#profile-popover');
  if (!avatar || !nameEl || !roleEl || !popover) return;

  if (user) {
    avatar.textContent = initials(user.name);
    avatar.style.background = user.color;
    avatar.style.color = '';
    nameEl.textContent = user.name;
    roleEl.textContent = user.role === 'admin' ? 'Администратор' : 'Участник';
  } else {
    avatar.textContent = '?';
    avatar.style.background = 'var(--surface-2)';
    avatar.style.color = 'var(--muted)';
    nameEl.textContent = 'Гость';
    roleEl.textContent = 'Войдите в систему';
  }

  const head = user
    ? `<div class="popover__head">
        <span class="avatar avatar--lg" style="background:${user.color}">${esc(initials(user.name))}</span>
        <span class="popover__head-text">
          <strong>${esc(user.name)}</strong>
          <small>${user.role === 'admin' ? 'Администратор' : 'Участник'}</small>
        </span>
      </div>`
    : `<div class="popover__head">
        <span class="avatar avatar--lg" style="background:var(--surface-2);color:var(--muted)">?</span>
        <span class="popover__head-text">
          <strong>Гостевой режим</strong>
          <small>Только просмотр графика</small>
        </span>
      </div>`;

  const mine = user
    ? `<button class="popover__item" type="button" data-action="profile-mine">
        ${icon('calendar')} Мои дежурства
      </button>`
    : '';

  const authItem = user
    ? `<button class="popover__item" type="button" data-action="profile-switch">${icon('users')} Сменить пользователя</button>
       <button class="popover__item popover__item--danger" type="button" data-action="logout">${icon('logout')} Выйти</button>`
    : `<button class="popover__item" type="button" data-action="open-login">${icon('lock')} Войти в систему</button>`;

  popover.innerHTML = `
    ${head}
    ${mine}
    <button class="popover__item" type="button" data-action="toggle-theme">
      ${icon(state.theme === 'dark' ? 'sun' : 'moon')} ${state.theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
    </button>
    <div class="popover__sep"></div>
    ${authItem}
    <p class="popover__note">MediaHLG · график и репертуар</p>
  `;
}

function toggleProfile(force) {
  const btn = $('#profile-btn');
  const popover = $('#profile-popover');
  if (!btn || !popover) return;
  const open = typeof force === 'boolean' ? force : !popover.classList.contains('open');
  popover.classList.toggle('open', open);
  btn.setAttribute('aria-expanded', String(open));
}

/* ---------- Тема ---------- */
function setTheme(theme) {
  state.theme = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.dataset.theme = state.theme;
  writeStore('theme', state.theme);
  const themeIcon = $('#theme-icon use');
  if (themeIcon) themeIcon.setAttribute('href', state.theme === 'dark' ? '#i-sun' : '#i-moon');
  const btn = $('#theme-toggle');
  if (btn) btn.setAttribute('aria-label', state.theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему');
  renderProfile();
}

function toggleTheme() {
  setTheme(state.theme === 'dark' ? 'light' : 'dark');
}

/* ---------- Прокрутка и меню ---------- */
function openSidebar() {
  document.body.classList.add('sidebar-open');
  const scrim = $('#sidebar-scrim');
  if (scrim) scrim.hidden = false;
  const btn = $('#menu-btn');
  if (btn) btn.setAttribute('aria-expanded', 'true');
}

function closeSidebar() {
  document.body.classList.remove('sidebar-open');
  const scrim = $('#sidebar-scrim');
  if (scrim) scrim.hidden = true;
  const btn = $('#menu-btn');
  if (btn) btn.setAttribute('aria-expanded', 'false');
}

/* ---------- Общий рендер ---------- */
function renderAll() {
  applyRole();
  renderProfile();
  renderSidebar();
  renderSchedule();
  renderSongs();
  renderStats();
  renderUsers();
  renderSync();
}

function renderSidebar() {
  const up = upcomingDates().length;
  const scheduleCount = $('#nav-schedule-count');
  const songsCount = $('#nav-songs-count');
  if (scheduleCount) scheduleCount.textContent = String(up);
  if (songsCount) songsCount.textContent = String(state.songs.length);
  const syncTitle = $('#sidebar-sync-title');
  const syncText = $('#sidebar-sync-text');
  const hasSync = state.lastSync && state.lastSync !== 'нет данных';
  if (syncTitle) syncTitle.textContent = hasSync ? 'Всё синхронизировано' : 'Google Sheets';
  if (syncText) syncText.textContent = hasSync ? `${state.lastSync} · Google Sheets` : 'Данные из таблицы';
}

/* ---------- График ---------- */
function personChip(user, options = {}) {
  const { interactive = false, me = false, action = 'toggle-duty', dateId = '', empty = false, small = false } = options;
  const avatar = `<span class="avatar ${small ? 'avatar--sm' : ''}" style="background:${user.color}">${esc(initials(user.name))}</span>`;
  const inner = `${avatar}<span>${esc(user.name)}</span>${me && !empty ? icon('check') : ''}`;
  const cls = `person ${me ? 'person--me' : ''} ${interactive ? 'person--clickable' : 'person--readonly'}`;
  if (!interactive) {
    return `<span class="${cls}">${inner}</span>`;
  }
  return `<button type="button" class="${cls}" data-action="${action}" data-date="${esc(dateId)}" data-user="${esc(user.id)}" title="${options.title || 'Изменить дежурство'}">${inner}</button>`;
}

function dutyChips(date) {
  const html = date.duties.map((uid) => {
    const user = userById(uid);
    if (!user) return '';
    const me = uid === state.currentUserId;
    const can = isAdmin() || (state.role === 'user' && me);
    return personChip(user, {
      interactive: can,
      me,
      dateId: date.id,
      title: can ? (me ? 'Снять своё дежурство' : 'Снять дежурство') : user.name,
    });
  });

  const free = Math.max(0, MAX_PER_DAY - date.duties.length);
  let canJoin = free > 0 && state.role === 'user' && state.currentUserId && !date.duties.includes(state.currentUserId);
  for (let i = 0; i < free; i += 1) {
    if (isAdmin()) {
      html.push(`<button type="button" class="person person--empty person--clickable" data-action="edit-date" data-id="${esc(date.id)}">${icon('plus')} Свободно</button>`);
    } else if (canJoin) {
      canJoin = false;
      html.push(`<button type="button" class="person person--empty person--clickable person--join" data-action="toggle-duty" data-date="${esc(date.id)}" data-user="${esc(state.currentUserId)}" title="Записаться на дежурство">${icon('plus')} Я дежурю</button>`);
    } else {
      html.push(`<span class="person person--empty">${icon('plus')} Свободно</span>`);
    }
  }
  return html.join('');
}

function repSection(date) {
  const open = state.openReps.has(date.id);
  const count = date.songs.length;
  const items = date.songs.map((sid, index) => {
    const song = songById(sid);
    if (!song) return '';
    return `<button type="button" class="rep-item" data-action="open-song" data-song="${esc(song.id)}" title="Открыть текст песни">
      <span class="rep-item__num">${index + 1}</span>
      <span class="dot tone-${safeTone(song.color)}"></span>
      <span class="rep-item__name">${esc(song.title)}</span>
      ${icon('chevron-right')}
    </button>`;
  }).join('');

  return `<div class="rep">
    <button type="button" class="rep-toggle" data-action="toggle-rep" data-id="${esc(date.id)}" aria-expanded="${open}">
      ${icon('songs')}
      <span>Репертуар</span>
      <span class="rep-count">${count}</span>
      ${icon('chevron-down', 'rep-chev')}
    </button>
    ${open ? (count ? `<div class="rep-list">${items}</div>` : `<p class="rep-empty">Песни ещё не добавлены</p>`) : ''}
  </div>`;
}

function dateCard(date) {
  const tone = safeTone(date.color);
  const note = noteFromRaw(date.raw);
  const free = Math.max(0, MAX_PER_DAY - date.duties.length);
  return `<article class="date-card tone-${tone}" aria-label="${esc(formatFull(date.date))}">
    <div class="date-card__head">
      <span class="date-badge">
        <span class="date-badge__day">${dayNumber(date.date)}</span>
        <span class="date-badge__month">${monthShort(date.date)}</span>
      </span>
      <div class="date-card__titles">
        <h3 class="date-card__title">${esc(weekday(date.date))}</h3>
        <p class="date-card__sub">
          <span>${formatShort(date.date)}</span>
          ${note ? `<span>·</span><span>${esc(note)}</span>` : ''}
        </p>
      </div>
      <div class="date-card__actions">
        <button type="button" class="icon-btn icon-btn--sm" data-action="edit-date" data-id="${esc(date.id)}" aria-label="Открыть дату" title="Открыть дату">
          ${icon(isAdmin() ? 'edit' : 'arrow-up-right')}
        </button>
      </div>
    </div>
    <div class="duties">
      <p class="duties__label">Дежурные <span>${date.duties.length} из ${MAX_PER_DAY}</span></p>
      <div class="people">${dutyChips(date)}</div>
    </div>
    ${repSection(date)}
    <div class="date-card__foot">
      ${free > 0
        ? `<span class="muted-note muted-note--warn"><span class="status-dot"></span>${free} ${plural(free, ['место', 'места', 'мест'])} свободно</span>`
        : `<span class="muted-note"><span class="status-dot"></span>Состав заполнен</span>`}
      <button type="button" class="link-btn" data-action="edit-date" data-id="${esc(date.id)}">
        Открыть ${icon('arrow-right')}
      </button>
    </div>
  </article>`;
}

function archiveTable(list) {
  if (!list.length) {
    return emptyState('archive', 'В архиве пока пусто', 'Здесь появятся даты, которые уже прошли.', '');
  }
  const rows = list.map((date) => {
    const tone = safeTone(date.color);
    const people = date.duties.map((uid) => {
      const user = userById(uid);
      if (!user) return '';
      return `<span class="avatar avatar--sm" style="background:${user.color}" title="${esc(user.name)}">${esc(initials(user.name))}</span>`;
    }).join('');
    const names = date.duties.map((uid) => userById(uid)).filter(Boolean).map((u) => u.name).join(', ');
    return `<tr>
      <td>
        <div class="table-date tone-${tone}">
          <span class="table-date__badge"><strong>${dayNumber(date.date)}</strong><span>${monthShort(date.date)}</span></span>
          <span class="table-date__text">
            <strong>${esc(weekday(date.date))}</strong>
            <small>${formatShort(date.date)}${noteFromRaw(date.raw) ? ' · ' + esc(noteFromRaw(date.raw)) : ''}</small>
          </span>
        </div>
      </td>
      <td>
        <div class="table-people">
          <span class="avatar-stack">${people}</span>
          <span class="table-muted">${esc(names || 'Не назначены')}</span>
        </div>
      </td>
      <td><span class="table-muted">${date.songs.length} ${plural(date.songs.length, ['песня', 'песни', 'песен'])}</span></td>
      <td><span class="status-pill status-pill--skip">Прошло</span></td>
      <td class="ta-right">
        <div class="row-actions">
          ${isAdmin() ? `<button type="button" class="icon-btn" data-action="edit-date" data-id="${esc(date.id)}" aria-label="Редактировать дату" title="Редактировать">${icon('edit')}</button>` : ''}
          <button type="button" class="icon-btn" data-action="edit-date" data-id="${esc(date.id)}" aria-label="Открыть дату" title="Открыть">${icon('arrow-up-right')}</button>
        </div>
      </td>
    </tr>`;
  }).join('');

  return `<div class="table-card">
    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>Дата</th>
            <th>Дежурные</th>
            <th>Репертуар</th>
            <th>Статус</th>
            <th class="ta-right">Действия</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </div>`;
}

function emptyState(iconName, title, text, actionHtml = '') {
  return `<div class="empty">
    <span class="empty__icon">${icon(iconName)}</span>
    <h3>${esc(title)}</h3>
    <p>${esc(text)}</p>
    ${actionHtml}
  </div>`;
}

function renderSpotlight(dates) {
  const box = $('#spotlight');
  if (!box) return;
  const next = dates[0];
  if (!next) {
    box.innerHTML = `<div class="spotlight__main">
      <p class="spotlight__label">${icon('calendar')} Ближайшее дежурство</p>
      <h2 class="spotlight__month" style="margin-top:10px;font-size:22px">Пока не запланировано</h2>
      <p class="spotlight__empty" style="margin-top:6px">Добавьте первую дату, чтобы начать график.</p>
    </div>`;
    return;
  }
  const note = noteFromRaw(next.raw);
  const users = next.duties.map((uid) => userById(uid)).filter(Boolean);
  const songNames = next.songs.map((sid) => songById(sid)).filter(Boolean).map((s) => s.title);
  const me = state.currentUserId && next.duties.includes(state.currentUserId);
  const canJoin = state.role === 'user' && !me && next.duties.length < MAX_PER_DAY && state.currentUserId;

  const people = users.length
    ? users.map((u) => `<span class="spotlight__person"><span class="avatar avatar--sm" style="background:${u.color}">${esc(initials(u.name))}</span>${esc(u.name)}</span>`).join('')
    : `<span class="spotlight__empty">Дежурные ещё не назначены</span>`;

  box.innerHTML = `<div class="spotlight__main">
    <p class="spotlight__label">${icon('calendar')} Ближайшее дежурство</p>
    <div class="spotlight__date">
      <span class="spotlight__day">${dayNumber(next.date)}</span>
      <span class="spotlight__date-text">
        <span class="spotlight__month">${esc(formatFull(next.date))}</span>
        <span class="spotlight__time">${icon('clock')}${note ? esc(note) : 'Время не указано'}</span>
      </span>
    </div>
    <div class="spotlight__people">${people}</div>
  </div>
  <div class="spotlight__side">
    <span class="spotlight__chip">${relativeDays(next.date)}</span>
    <p class="spotlight__rep">
      <strong>Репертуар</strong>
      ${songNames.length ? esc(songNames.slice(0, 3).join(' · ')) + (songNames.length > 3 ? ` и ещё ${songNames.length - 3}` : '') : 'Песни не добавлены'}
    </p>
    <div class="spotlight__actions">
      ${canJoin ? `<button type="button" class="btn btn--light btn--sm" data-action="toggle-duty" data-date="${esc(next.id)}" data-user="${esc(state.currentUserId)}">${icon('check')} Я дежурю</button>` : ''}
      ${me ? `<span class="spotlight__chip">${icon('check')} Вы в составе</span>` : ''}
      <button type="button" class="btn ${canJoin || me ? 'btn--on-dark' : 'btn--light'} btn--sm" data-action="edit-date" data-id="${esc(next.id)}">
        Открыть дату ${icon('arrow-right')}
      </button>
    </div>
  </div>`;
}

function renderSchedule() {
  const up = upcomingDates();
  const archive = archiveDates();
  const user = currentUser();
  const mine = user ? state.dates.filter((d) => d.duties.includes(user.id)).sort(sortByDateAsc) : [];

  const countUpcoming = $('#count-upcoming');
  const countArchive = $('#count-archive');
  const countMine = $('#count-mine');
  if (countUpcoming) countUpcoming.textContent = String(up.length);
  if (countArchive) countArchive.textContent = String(archive.length);
  if (countMine) countMine.textContent = String(mine.length);

  const view = $('#dates-view');
  const pagination = $('#dates-pagination');
  if (state.loading) {
    if (view) view.innerHTML = emptyState('sync', 'Загружаем график', 'Получаем даты, дежурных и репертуар.', '');
    if (pagination) pagination.innerHTML = '';
    return;
  }
  if (state.loadError) {
    if (view) {
      view.innerHTML = emptyState('alert', 'Ошибка загрузки', state.loadError,
        `<button type="button" class="btn btn--primary" data-action="reload">${icon('sync')} Повторить</button>`);
    }
    if (pagination) pagination.innerHTML = '';
    return;
  }

  renderSpotlight(up);

  const filter = $('#person-filter');
  if (filter) {
    const current = state.personFilter;
    filter.innerHTML = `<option value="">Все дежурные</option>` +
      USERS.map((u) => `<option value="${u.id}" ${u.id === current ? 'selected' : ''}>${esc(u.name)}</option>`).join('');
    filter.value = current;
  }
  const reset = $('#reset-filter');
  if (reset) reset.hidden = !state.personFilter;

  $$('[data-schedule-tab]').forEach((btn) => {
    const active = btn.dataset.scheduleTab === state.scheduleTab;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', String(active));
  });

  if (!view) return;

  const applyFilter = (list) => state.personFilter
    ? list.filter((d) => d.duties.includes(state.personFilter))
    : list;

  if (state.scheduleTab === 'archive') {
    view.innerHTML = archiveTable(applyFilter(archive));
    if (pagination) pagination.innerHTML = '';
    return;
  }

  if (state.scheduleTab === 'mine') {
    if (!user) {
      view.innerHTML = emptyState('lock', 'Войдите, чтобы увидеть свои дежурства', 'После входа здесь появятся даты, где вы назначены дежурным.',
        `<button type="button" class="btn btn--primary" data-action="open-login">${icon('lock')} Войти</button>`);
      if (pagination) pagination.innerHTML = '';
      return;
    }
    const list = applyFilter(mine);
    if (!list.length) {
      view.innerHTML = emptyState('calendar', 'У вас пока нет дежурств', 'Администратор назначит вас на дату, или отметьтесь самостоятельно в графике.',
        `<button type="button" class="btn btn--primary" data-action="go-tab" data-tab="upcoming">${icon('calendar')} К графику</button>`);
    } else {
      view.innerHTML = `<div class="date-grid">${list.map(dateCard).join('')}</div>`;
    }
    if (pagination) pagination.innerHTML = '';
    return;
  }

  const list = applyFilter(up);
  if (!list.length) {
    view.innerHTML = emptyState('calendar', 'Ничего не найдено', state.personFilter ? 'У выбранного участника нет актуальных дежурств.' : 'Актуальных дат пока нет.',
      state.personFilter ? `<button type="button" class="btn btn--ghost" data-action="reset-person">${icon('close')} Сбросить фильтр</button>` : '');
    if (pagination) pagination.innerHTML = '';
    return;
  }

  const pageSize = 4;
  const pages = Math.max(1, Math.ceil(list.length / pageSize));
  if (state.datePage > pages) state.datePage = pages;
  const start = (state.datePage - 1) * pageSize;
  const pageItems = list.slice(start, start + pageSize);
  view.innerHTML = `<div class="date-grid">${pageItems.map(dateCard).join('')}</div>`;

  if (pagination) {
    if (pages <= 1) {
      pagination.innerHTML = '';
    } else {
      const numButtons = Array.from({ length: pages }, (_, i) => {
        const n = i + 1;
        return `<button type="button" class="page-btn ${n === state.datePage ? 'active' : ''}" data-action="date-page" data-page="${n}" aria-label="Страница ${n}" ${n === state.datePage ? 'aria-current="page"' : ''}>${n}</button>`;
      }).join('');
      pagination.innerHTML = `
        <button type="button" class="page-btn" data-action="date-page" data-page="${state.datePage - 1}" ${state.datePage === 1 ? 'disabled' : ''} aria-label="Предыдущая страница">${icon('chevron-left')}</button>
        ${numButtons}
        <button type="button" class="page-btn" data-action="date-page" data-page="${state.datePage + 1}" ${state.datePage === pages ? 'disabled' : ''} aria-label="Следующая страница">${icon('chevron-right')}</button>
        <span class="page-info">${start + 1}–${Math.min(start + pageSize, list.length)} из ${list.length}</span>`;
    }
  }
}

async function toggleDuty(dateId, userId) {
  const date = dateById(dateId);
  if (!date) return;
  const user = userById(userId);
  if (!user) return;

  if (!isAdmin() && !(state.role === 'user' && userId === state.currentUserId)) {
    toast('Можно менять только своё дежурство', 'error');
    return;
  }

  const assigned = date.duties.includes(userId);
  if (!assigned && date.duties.length >= MAX_PER_DAY) {
    toast(`На одну дату можно назначить не больше ${MAX_PER_DAY} дежурных`, 'error');
    return;
  }

  try {
    await apiFetch('/duty/toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date_str: date.raw, user_name: user.name, value: !assigned }),
    });
    if (assigned) {
      date.duties = date.duties.filter((id) => id !== userId);
      toast(isAdmin() ? `${user.name} снят(а) с дежурства` : 'Дежурство снято', 'info');
    } else {
      date.duties.push(userId);
      toast(isAdmin() ? `${user.name} назначен(а) на ${formatShort(date.date)}` : `Вы записаны на ${formatShort(date.date)}`);
    }
    renderSchedule();
    renderSidebar();
    renderStats();
    renderSpotlight(upcomingDates());
  } catch (e) {
    toast('Не удалось изменить дежурство: ' + e.message, 'error');
    await refreshData();
  }
}

function setScheduleTab(tab) {
  if (!['upcoming', 'archive', 'mine'].includes(tab)) return;
  state.scheduleTab = tab;
  state.datePage = 1;
  renderSchedule();
}

/* ---------- Песни ---------- */
function renderSongs() {
  const box = $('#song-list');
  if (!box) return;

  // const withText = state.songs.filter((s) => s.text.trim()).length;
  // const used = state.songs.filter((s) => datesForSong(s.id).length > 0).length;
  // const metrics = $('#songs-metrics');
  // if (metrics) {
  //   metrics.innerHTML = `
  //     <article class="metric">
  //       <div class="metric__top"><span>Всего песен</span><span class="metric__icon">${icon('songs')}</span></div>
  //       <div class="metric__value">${state.songs.length}</div>
  //       <p class="metric__note">В библиотеке</p>
  //     </article>
  //     <article class="metric">
  //       <div class="metric__top"><span>С текстом</span><span class="metric__icon">${icon('edit')}</span></div>
  //       <div class="metric__value">${withText}</div>
  //       <p class="metric__note">${state.songs.length - withText} ${plural(state.songs.length - withText, ['без текста', 'без текста', 'без текста'])}</p>
  //     </article>
  //     <article class="metric">
  //       <div class="metric__top"><span>В репертуаре</span><span class="metric__icon">${icon('calendar')}</span></div>
  //       <div class="metric__value">${used}</div>
  //       <p class="metric__note">Используются на датах</p>
  //     </article>
  //     <article class="metric">
  //       <div class="metric__top"><span>Средняя длина</span><span class="metric__icon">${icon('stats')}</span></div>
  //       <div class="metric__value">${Math.round(state.songs.reduce((sum, s) => sum + (s.text ? s.text.split('\n').length : 0), 0) / Math.max(1, withText))}<small>строк</small></div>
  //       <p class="metric__note">В тексте песни</p>
  //     </article>`;
  // }


  const search = $('#songs-search');
  if (search && search.value !== state.songsQuery) search.value = state.songsQuery;

  $$('[data-song-filter]').forEach((btn) => {
    const active = btn.dataset.songFilter === state.songsFilter;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-selected', String(active));
  });

  const sort = $('#songs-sort');
  if (sort) sort.value = state.songsSort;

  const query = state.songsQuery.trim().toLowerCase();
  let list = state.songs.filter((song) => {
    const usedCount = datesForSong(song.id).length;
    if (state.songsFilter === 'used' && usedCount === 0) return false;
    if (state.songsFilter === 'unused' && usedCount > 0) return false;
    if (query) {
      const haystack = `${song.title}\n${song.text}`.toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    return true;
  });

  list = list.slice().sort((a, b) => {
    if (state.songsSort === 'used') return datesForSong(b.id).length - datesForSong(a.id).length || a.title.localeCompare(b.title, 'ru');
    if (state.songsSort === 'length') return (b.text.length - a.text.length);
    return a.title.localeCompare(b.title, 'ru');
  });

  const pagination = $('#songs-pagination');
  if (!list.length) {
    box.innerHTML = emptyState('songs', 'Песни не найдены', query ? 'Попробуйте изменить запрос или сбросить фильтр.' : 'В этой категории пока нет песен.',
      `<button type="button" class="btn btn--ghost" data-action="reset-songs">${icon('close')} Сбросить фильтры</button>`);
    if (pagination) pagination.innerHTML = '';
    return;
  }

  const pageSize = 5;
  const pages = Math.max(1, Math.ceil(list.length / pageSize));
  if (state.songPage > pages) state.songPage = pages;
  const start = (state.songPage - 1) * pageSize;
  const pageItems = list.slice(start, start + pageSize);

  box.innerHTML = pageItems.map((song) => {
    const usedCount = datesForSong(song.id).length;
    const firstLine = song.text ? song.text.split('\n').find((line) => line.trim()) || 'Текст пока не добавлен' : 'Текст пока не добавлен';
    const lines = song.text ? song.text.split('\n').length : 0;
    const tone = safeTone(song.color);
    return `<div class="song-row">
      <button type="button" class="song-row__open" data-action="open-song" data-song="${esc(song.id)}">
        <span class="song-row__tone tone-${tone}">${icon('songs')}</span>
        <span class="song-row__text">
          <span class="song-row__title">${esc(song.title)}</span>
          <span class="song-row__snippet">${esc(firstLine)}</span>
        </span>
      </button>
      <span class="song-row__meta">
        ${usedCount ? `<span class="tag tag--accent">${usedCount} ${plural(usedCount, ['дата', 'даты', 'дат'])}</span>` : '<span class="tag">Не используется</span>'}
      </span>
      <span class="song-row__length">${lines ? lines + ' ' + plural(lines, ['строка', 'строки', 'строк']) : 'Без текста'}</span>
      <span class="song-row__actions">
        <button type="button" class="icon-btn" data-action="copy-song" data-song="${esc(song.id)}" aria-label="Копировать текст" title="Копировать текст">${icon('copy')}</button>
        ${isAdmin() ? `<button type="button" class="icon-btn" data-action="edit-song" data-song="${esc(song.id)}" aria-label="Редактировать песню" title="Редактировать">${icon('edit')}</button>` : ''}
      </span>
    </div>`;
  }).join('');

  if (pagination) {
    if (pages <= 1) {
      pagination.innerHTML = '';
    } else {
      const nums = Array.from({ length: pages }, (_, i) => {
        const n = i + 1;
        return `<button type="button" class="page-btn ${n === state.songPage ? 'active' : ''}" data-action="song-page" data-page="${n}" ${n === state.songPage ? 'aria-current="page"' : ''}>${n}</button>`;
      }).join('');
      pagination.innerHTML = `
        <button type="button" class="page-btn" data-action="song-page" data-page="${state.songPage - 1}" ${state.songPage === 1 ? 'disabled' : ''} aria-label="Предыдущая страница">${icon('chevron-left')}</button>
        ${nums}
        <button type="button" class="page-btn" data-action="song-page" data-page="${state.songPage + 1}" ${state.songPage === pages ? 'disabled' : ''} aria-label="Следующая страница">${icon('chevron-right')}</button>
        <span class="page-info">${start + 1}–${Math.min(start + pageSize, list.length)} из ${list.length}</span>`;
    }
  }
}

function copyText(text) {
  if (!text) {
    toast('У этой песни пока нет текста', 'error');
    return;
  }
  const done = () => toast('Текст песни скопирован');
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
  } else {
    fallbackCopy(text, done);
  }
}

function fallbackCopy(text, done) {
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand('copy');
    done();
  } catch (e) {
    toast('Не удалось скопировать текст', 'error');
  }
  area.remove();
}

function openSongDrawer(songId) {
  const song = songById(songId);
  if (!song) return;
  state.selectedSongId = songId;
  const used = datesForSong(songId);
  const lines = song.text ? song.text.split('\n').length : 0;

  const title = $('#drawer-title');
  const meta = $('#drawer-meta');
  const body = $('#drawer-body');
  const foot = $('#drawer-foot');
  const eyebrow = $('#drawer-eyebrow');
  if (!title || !meta || !body || !foot) return;

  if (eyebrow) eyebrow.textContent = 'Песня · ' + (used.length ? 'в репертуаре' : 'не используется');
  title.textContent = song.title;
  meta.innerHTML = `<span class="dot tone-${safeTone(song.color)}"></span>
    <span>${used.length} ${plural(used.length, ['дата', 'даты', 'дат'])}</span>
    ${lines ? `<span>·</span><span>${lines} ${plural(lines, ['строка', 'строки', 'строк'])}</span>` : '<span>·</span><span>без текста</span>'}`;

  body.innerHTML = `
    ${used.length ? `<div class="drawer__dates">${used.map((d) => `<button type="button" class="date-chip" data-action="search-date" data-id="${esc(d.id)}">${icon('calendar')} ${formatShort(d.date)}</button>`).join('')}</div>` : ''}
    ${song.text
      ? `<pre class="lyrics">${esc(song.text)}</pre>`
      : `<div class="drawer__empty">Текст пока не добавлен.${isAdmin() ? ' Нажмите «Редактировать», чтобы добавить его.' : ''}</div>`}`;

  foot.innerHTML = `
    <button type="button" class="btn btn--ghost btn--sm" data-action="copy-song" data-song="${esc(song.id)}">${icon('copy')} Копировать текст</button>
    <span class="spacer"></span>
    ${isAdmin() ? `
      <button type="button" class="btn btn--ghost btn--sm" data-action="delete-song" data-song="${esc(song.id)}" aria-label="Удалить песню" title="Удалить песню">${icon('trash')}</button>
      <button type="button" class="btn btn--primary btn--sm" data-action="edit-song" data-song="${esc(song.id)}">${icon('edit')} Редактировать</button>` : ''}`;

  const drawer = $('#song-drawer');
  const scrim = $('#scrim');
  if (drawer) {
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
  }
  if (scrim) scrim.classList.add('show');
  document.body.classList.add('no-scroll');
}

function closeDrawer() {
  const drawer = $('#song-drawer');
  const scrim = $('#scrim');
  if (drawer) {
    drawer.classList.remove('open');
    drawer.setAttribute('aria-hidden', 'true');
  }
  if (scrim) scrim.classList.remove('show');
  state.selectedSongId = null;
  if (!$$('.modal.open').length) document.body.classList.remove('no-scroll');
}

/* ---------- Статистика ---------- */
function buildMonthSeries() {
  const counts = new Map();
  state.dates.forEach((date) => {
    const d = parseIso(date.date);
    if (Number.isNaN(d.getTime())) return;
    const key = d.getFullYear() * 100 + d.getMonth();
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  const now = parseIso(TODAY);
  const series = [];
  for (let offset = 5; offset >= 0; offset -= 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - offset, 1);
    const key = d.getFullYear() * 100 + d.getMonth();
    series.push({ label: MONTHS_SHORT[d.getMonth()], value: counts.get(key) || 0 });
  }
  return series;
}

function renderStats() {
  const metrics = $('#stats-metrics');
  if (!metrics) return;

  const season = $('#stats-season');
  if (season) season.textContent = `Сезон ${parseIso(TODAY).getFullYear()}`;

  const all = state.dates;
  const totalDuties = all.reduce((sum, d) => sum + d.duties.length, 0);
  const activeUsers = USERS.filter((u) => all.some((d) => d.duties.includes(u.id))).length;
  const avg = all.length ? (totalDuties / all.length) : 0;
  const capacity = all.length * MAX_PER_DAY;
  const fill = capacity ? Math.round((totalDuties / capacity) * 100) : 0;

  metrics.innerHTML = `
    <article class="metric">
      <div class="metric__top"><span>Всего дежурств</span><span class="metric__icon">${icon('calendar')}</span></div>
      <div class="metric__value">${totalDuties}</div>
      <p class="metric__note">За ${parseIso(TODAY).getFullYear()} год</p>
    </article>
    <article class="metric">
      <div class="metric__top"><span>Активных участников</span><span class="metric__icon">${icon('users')}</span></div>
      <div class="metric__value">${activeUsers}<small>из ${USERS.length}</small></div>
      <p class="metric__note metric__note--accent">Все были в графике</p>
    </article>
    <article class="metric">
      <div class="metric__top"><span>Среднее на дату</span><span class="metric__icon">${icon('stats')}</span></div>
      <div class="metric__value">${avg.toFixed(1).replace('.', ',')}<small>чел.</small></div>
      <p class="metric__note">При лимите ${MAX_PER_DAY} человека</p>
    </article>
    <article class="metric">
      <div class="metric__top"><span>Заполненность</span><span class="metric__icon">${icon('check')}</span></div>
      <div class="metric__value">${fill}<small>%</small></div>
      <p class="metric__note">${totalDuties} из ${capacity} слотов</p>
    </article>`;

  const trend = $('#stats-trend');
  if (trend) {
    const series = buildMonthSeries();
    const last = series[series.length - 1]?.value || 0;
    const prev = series[series.length - 2]?.value || 0;
    const change = prev ? Math.round(((last - prev) / prev) * 100) : (last ? 100 : 0);
    trend.textContent = `${change >= 0 ? '+' : ''}${change}%`;
    trend.classList.toggle('is-negative', change < 0);
  }

  const bars = $('#month-bars');
  if (bars) {
    const series = buildMonthSeries();
    const max = Math.max(...series.map((m) => m.value), 1);
    bars.innerHTML = series.map((m, index) => {
      const last = index === series.length - 1;
      return `<div class="bar-col ${last ? 'bar-col--last' : ''}">
        <span class="bar-value">${m.value}</span>
        <span class="bar" style="--h:${Math.round((m.value / max) * 100)}%" title="${m.label}: ${m.value}"></span>
        <span class="bar-label">${m.label}</span>
      </div>`;
    }).join('');
  }

  const counts = USERS.map((u) => ({
    user: u,
    count: all.reduce((sum, d) => sum + (d.duties.includes(u.id) ? 1 : 0), 0),
  })).sort((a, b) => b.count - a.count || a.user.name.localeCompare(b.user.name, 'ru'));

  const top = counts.slice(0, 5);
  const rest = counts.slice(5).reduce((sum, item) => sum + item.count, 0);
  const donut = $('#duty-donut');
  const legend = $('#duty-legend');
  const total = $('#donut-total');
  if (total) total.textContent = String(totalDuties);

  if (donut && legend) {
    let cursor = 0;
    const segments = top.map((item) => {
      const share = totalDuties ? (item.count / totalDuties) * 100 : 0;
      const from = cursor;
      cursor += share;
      return `${item.user.color} ${from}% ${cursor}%`;
    });
    if (rest > 0) {
      const share = totalDuties ? (rest / totalDuties) * 100 : 0;
      segments.push(`#b6bec6 ${cursor}% ${cursor + share}%`);
    }
    donut.style.background = totalDuties
      ? `conic-gradient(${segments.join(', ')})`
      : 'conic-gradient(var(--surface-2) 0 100%)';

    legend.innerHTML = top.map((item) => `<li>
      <span class="legend__dot" style="background:${item.user.color}"></span>
      <span class="legend__name">${esc(item.user.name)}</span>
      <span class="legend__value">${item.count}</span>
    </li>`).join('') + (rest > 0 ? `<li>
      <span class="legend__dot" style="background:#b6bec6"></span>
      <span class="legend__name">Другие</span>
      <span class="legend__value">${rest}</span>
    </li>` : '');
  }

  const topSongs = $('#top-songs');
  if (topSongs) {
    const ranked = state.songs
      .map((song) => ({ song, count: datesForSong(song.id).length }))
      .filter((item) => item.count > 0)
      .sort((a, b) => b.count - a.count || a.song.title.localeCompare(b.song.title, 'ru'))
      .slice(0, 5);
    const maxCount = ranked.length ? ranked[0].count : 1;
    topSongs.innerHTML = ranked.length ? ranked.map((item, index) => `<div class="rank">
      <span class="rank__num">${index + 1}</span>
      <div class="rank__main">
        <div class="rank__title"><span>${esc(item.song.title)}</span><span>${item.count} ${plural(item.count, ['раз', 'раза', 'раз'])}</span></div>
        <div class="rank__bar"><span class="rank__fill tone-${safeTone(item.song.color)}" style="width:${Math.round((item.count / maxCount) * 100)}%"></span></div>
      </div>
      <span class="rank__value">${item.count}</span>
    </div>`).join('') : `<p class="muted-text">Пока нет данных о репертуаре.</p>`;
  }

  const fillStats = $('#fill-stats');
  if (fillStats) {
    const archive = archiveDates();
    const up = upcomingDates();
    const archiveDuties = archive.reduce((sum, d) => sum + d.duties.length, 0);
    const archiveCapacity = archive.length * MAX_PER_DAY;
    const archiveFill = archiveCapacity ? Math.round((archiveDuties / archiveCapacity) * 100) : 0;
    const free = up.reduce((sum, d) => sum + Math.max(0, MAX_PER_DAY - d.duties.length), 0);
    fillStats.innerHTML = `
      <div class="fill-row">
        <div class="fill-row__top"><strong>Архив графика</strong><span>${archive.length} ${plural(archive.length, ['дата', 'даты', 'дат'])}</span></div>
        <div class="fill-track"><span style="width:${archiveFill}%"></span></div>
      </div>
      <div class="fill-row">
        <div class="fill-row__top"><strong>Прошедшие дежурства</strong><span>${archiveDuties} назначений</span></div>
        <div class="fill-track"><span style="width:${archiveFill}%"></span></div>
      </div>
      <div class="fill-row">
        <div class="fill-row__top"><strong>Будущие дежурства</strong><span>${free ? free + ' свободно' : 'всё занято'}</span></div>
        <div class="fill-track"><span style="width:${up.length ? Math.round((up.reduce((s, d) => s + d.duties.length, 0) / (up.length * MAX_PER_DAY)) * 100) : 0}%"></span></div>
      </div>`;
  }
}

/* ---------- Пользователи ---------- */
function dutyCountFor(userId) {
  return state.dates.reduce((sum, d) => sum + (d.duties.includes(userId) ? 1 : 0), 0);
}

function renderUsers() {
  const tbody = $('#users-tbody');
  if (!tbody || !isAdmin()) return;

  const admins = USERS.filter((u) => u.role === 'admin').length;
  const withDuties = USERS.filter((u) => dutyCountFor(u.id) > 0).length;
  const metrics = $('#users-metrics');
  if (metrics) {
    metrics.innerHTML = `
      <article class="metric">
        <div class="metric__top"><span>Всего пользователей</span><span class="metric__icon">${icon('users')}</span></div>
        <div class="metric__value">${USERS.length}</div>
        <p class="metric__note">С доступом по PIN</p>
      </article>
      <article class="metric">
        <div class="metric__top"><span>Администраторы</span><span class="metric__icon">${icon('shield')}</span></div>
        <div class="metric__value">${admins}</div>
        <p class="metric__note">Могут управлять графиком</p>
      </article>
      <article class="metric">
        <div class="metric__top"><span>В графике</span><span class="metric__icon">${icon('calendar')}</span></div>
        <div class="metric__value">${withDuties}<small>из ${USERS.length}</small></div>
        <p class="metric__note">Имеют назначения</p>
      </article>
      <article class="metric">
        <div class="metric__top"><span>Без дежурств</span><span class="metric__icon">${icon('clock')}</span></div>
        <div class="metric__value">${USERS.length - withDuties}</div>
        <p class="metric__note">Можно назначить</p>
      </article>`;
  }

  tbody.innerHTML = USERS.map((user) => {
    const count = dutyCountFor(user.id);
    const self = user.id === state.currentUserId;
    return `<tr>
      <td>
        <div class="table-user">
          <span class="avatar" style="background:${user.color}">${esc(initials(user.name))}</span>
          <span class="table-user__text">
            <strong>${esc(user.name)} ${self ? '<span class="self-badge">вы</span>' : ''}</strong>
            <small>PIN защищён</small>
          </span>
        </div>
      </td>
      <td>
        <span class="role-pill ${user.role === 'admin' ? 'role-pill--admin' : ''}">
          ${icon(user.role === 'admin' ? 'shield' : 'users')}
          ${user.role === 'admin' ? 'Администратор' : 'Участник'}
        </span>
      </td>
      <td><span class="table-muted">${count} ${plural(count, ['дежурство', 'дежурства', 'дежурств'])}</span></td>
      <td><span class="table-muted">PIN защищён</span></td>
      <td class="ta-right">
        <div class="row-actions">
          <button type="button" class="icon-btn" data-action="change-pin" data-user="${esc(user.id)}" aria-label="Сменить PIN" title="Сменить PIN">${icon('key')}</button>
          <button type="button" class="icon-btn" data-action="toggle-role" data-user="${esc(user.id)}" aria-label="${user.role === 'admin' ? 'Сделать участником' : 'Сделать администратором'}" title="${user.role === 'admin' ? 'Сделать участником' : 'Сделать администратором'}">${icon(user.role === 'admin' ? 'users' : 'shield')}</button>
          <button type="button" class="icon-btn icon-btn--danger" data-action="delete-user" data-user="${esc(user.id)}" aria-label="Удалить пользователя" title="Удалить пользователя" ${self ? 'disabled' : ''}>${icon('trash')}</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function openUserModal() {
  const name = $('#user-name');
  const pin = $('#user-pin');
  const role = $('#user-role');
  const error = $('#user-error');
  if (name) name.value = '';
  if (pin) pin.value = '';
  if (role) role.value = 'user';
  if (error) error.textContent = '';
  openModal('user-modal');
  setTimeout(() => name && name.focus(), 60);
}

async function saveUser() {
  const name = ($('#user-name')?.value || '').trim();
  const pin = ($('#user-pin')?.value || '').trim();
  const role = $('#user-role')?.value === 'admin' ? 'admin' : 'user';
  const error = $('#user-error');
  const fail = (message) => {
    if (error) {
      error.textContent = message;
      error.classList.remove('shake');
      void error.offsetWidth;
      error.classList.add('shake');
    }
  };

  if (name.length < 2) return fail('Введите имя пользователя');
  if (USERS.some((u) => u.name.toLowerCase() === name.toLowerCase())) return fail('Пользователь с таким именем уже существует');
  if (!/^\d{4,12}$/.test(pin)) return fail('PIN должен состоять из 4–12 цифр');

  const saveBtn = $('#user-save');
  if (saveBtn) saveBtn.disabled = true;
  try {
    await apiFetch('/users/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, pin, role }),
    });
    closeModal('user-modal');
    toast(`Пользователь ${name} создан`);
    await refreshData();
  } catch (e) {
    fail(e.message);
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

function openPinModal(userId) {
  const user = userById(userId);
  if (!user) return;
  state.pinUserId = userId;
  const title = $('#pin-modal-title');
  const text = $('#pin-modal-user');
  const input = $('#pin-new');
  const error = $('#pin-error');
  if (title) title.textContent = 'Сменить PIN';
  if (text) text.innerHTML = `Новый PIN для <strong>${esc(user.name)}</strong>. Старый PIN перестанет действовать.`;
  if (input) input.value = '';
  if (error) error.textContent = '';
  openModal('pin-modal');
  setTimeout(() => input && input.focus(), 60);
}

async function savePin() {
  const user = userById(state.pinUserId);
  const pin = ($('#pin-new')?.value || '').trim();
  const error = $('#pin-error');
  if (!user) return;
  if (!/^\d{4,12}$/.test(pin)) {
    if (error) error.textContent = 'PIN должен состоять из 4–12 цифр';
    return;
  }
  const saveBtn = $('#pin-save');
  if (saveBtn) saveBtn.disabled = true;
  try {
    await apiFetch(`/users/${encodeURIComponent(user.name)}/pin`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_pin: pin }),
    });
    closeModal('pin-modal');
    toast(`PIN пользователя ${user.name} обновлён`);
  } catch (e) {
    if (error) error.textContent = e.message;
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

async function toggleUserRole(userId) {
  const user = userById(userId);
  if (!user) return;
  if (user.id === state.currentUserId) {
    toast('Нельзя изменить роль самому себе', 'error');
    return;
  }
  const admins = USERS.filter((u) => u.role === 'admin').length;
  if (user.role === 'admin' && admins <= 1) {
    toast('В системе должен остаться хотя бы один администратор', 'error');
    return;
  }
  const nextRole = user.role === 'admin' ? 'user' : 'admin';
  try {
    await apiFetch(`/users/${encodeURIComponent(user.name)}/role`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: nextRole }),
    });
    toast(`${user.name} — теперь ${nextRole === 'admin' ? 'администратор' : 'участник'}`, 'info');
    await refreshData();
  } catch (e) {
    toast(e.message, 'error');
  }
}

function deleteUser(userId) {
  const user = userById(userId);
  if (!user) return;
  if (user.id === state.currentUserId) {
    toast('Нельзя удалить свою учётную запись', 'error');
    return;
  }
  askConfirm({
    title: `Удалить ${user.name}?`,
    text: 'Пользователь потеряет доступ, а его дежурства будут сняты с дат.',
    confirmLabel: 'Удалить пользователя',
    onConfirm: async () => {
      try {
        await apiFetch(`/users/${encodeURIComponent(user.name)}`, { method: 'DELETE' });
        closeModal('confirm-modal');
        toast('Пользователь удалён', 'info');
        await refreshData();
      } catch (e) {
        toast(e.message, 'error');
      }
    },
  });
}

/* ---------- Синхронизация ---------- */
function renderSync() {
  const hero = $('#sync-hero');
  const cards = $('#sync-cards');
  const tbody = $('#sync-tbody');
  if (!hero || !cards || !tbody) return;

  const up = upcomingDates();
  const archive = archiveDates();
  const songsInRep = new Set();
  state.dates.forEach((d) => d.songs.forEach((sid) => songsInRep.add(sid)));
  const last = SYNC_HISTORY[0];
  const lastFailed = last && last.status === 'error';

  hero.innerHTML = `<section class="sync-hero">
    <div class="sync-hero__main">
      <p class="sync-hero__label">${icon('spreadsheet')} Google Sheets</p>
      <h2>${state.syncing ? 'Синхронизируем…' : !last ? 'Нет данных' : lastFailed ? 'Требует внимания' : 'Всё актуально'}</h2>
      <p class="sync-hero__text">${last
        ? `Последняя синхронизация <strong>${esc(state.lastSync)}</strong> · следующая через <strong id="sync-countdown">${state.nextSync}</strong> с`
        : 'Запустите синхронизацию, чтобы получить статус.'}</p>
      <div class="sync-hero__meta">
        <span class="sync-hero__chip">${icon('spreadsheet')} Google Sheets</span>
        <span class="sync-hero__chip">${icon('sync')} Листы: График, Репертуар</span>
      </div>
    </div>
    <button type="button" class="btn btn--light" id="sync-run" data-action="run-sync" ${state.syncing ? 'disabled' : ''}>
      ${state.syncing ? icon('sync', 'spin') + ' Синхронизируем…' : icon('sync') + ' Запустить сейчас'}
    </button>
  </section>`;

  cards.innerHTML = `
    <section class="panel">
      <header class="panel__head">
        <div><h2>Лист «График»</h2><p>Даты и дежурные</p></div>
        <span class="panel-badge">${icon('check')} Синхронизирован</span>
      </header>
      <div class="info-row"><span>Актуальных дат</span><strong>${up.length}</strong></div>
      <div class="info-row"><span>В архиве</span><strong>${archive.length}</strong></div>
      <div class="info-row"><span>Назначений</span><strong>${state.dates.reduce((sum, d) => sum + d.duties.length, 0)}</strong></div>
      <div class="info-row"><span>Обновлён</span><strong>${esc(state.lastSync)}</strong></div>
    </section>
    <section class="panel">
      <header class="panel__head">
        <div><h2>Лист «Репертуар»</h2><p>Песни и цветовые метки</p></div>
        <span class="panel-badge">${icon('check')} Синхронизирован</span>
      </header>
      <div class="info-row"><span>Песен в репертуаре</span><strong>${songsInRep.size}</strong></div>
      <div class="info-row"><span>Строк в таблице</span><strong>${state.dates.reduce((sum, d) => sum + d.songs.length, 0)}</strong></div>
      <div class="info-row"><span>Цветовых меток</span><strong>${new Set(state.dates.map((d) => d.color)).size}</strong></div>
      <div class="info-row"><span>Обновлён</span><strong>${esc(state.lastSync)}</strong></div>
    </section>
    <section class="panel">
      <header class="panel__head">
        <div><h2>Подключение</h2><p>Сервисный аккаунт</p></div>
        <span class="panel-badge">${icon('lock')} Защищено</span>
      </header>
      <div class="info-row"><span>Сервис</span><strong>Google Sheets</strong></div>
      <div class="info-row"><span>Интервал</span><strong>каждые 60 секунд</strong></div>
      <div class="info-row"><span>Режим</span><strong>односторонний</strong></div>
      <div class="info-row"><span>Последний статус</span><strong style="color:${lastFailed ? 'var(--danger)' : 'var(--accent)'}">${lastFailed ? 'ошибка' : last ? 'успешно' : 'нет данных'}</strong></div>
    </section>`;

  tbody.innerHTML = SYNC_HISTORY.length ? SYNC_HISTORY.map((row) => {
    const statusClass = row.status === 'ok' ? 'status-pill--ok' : row.status === 'error' ? 'status-pill--error' : 'status-pill--skip';
    const statusLabel = row.status === 'ok' ? 'Успешно' : row.status === 'error' ? 'Ошибка' : 'Без изменений';
    return `<tr title="${esc(row.note)}">
      <td><span class="table-muted" style="white-space:nowrap">${esc(row.at)}</span></td>
      <td>${esc(row.by)}</td>
      <td>${esc(row.changes)}</td>
      <td><span class="table-muted">${esc(row.duration)}</span></td>
      <td><span class="status-pill ${statusClass}">${statusLabel}</span></td>
    </tr>`;
  }).join('') : '<tr><td colspan="5"><span class="table-muted">История синхронизаций пока пуста.</span></td></tr>';

  const refresh = $('#sync-refresh');
  if (refresh) refresh.disabled = state.syncing;
}

async function runSync() {
  if (state.syncing) return;
  if (!isAdmin()) {
    toast('Синхронизацию может запускать только администратор', 'error');
    return;
  }
  state.syncing = true;
  renderSync();
  toast('Запущена синхронизация с Google Sheets', 'info');

  try {
    await apiFetch('/sync/run', { method: 'POST' });
    state.syncing = false;
    state.nextSync = 60;
    await refreshData();
    if (state.loadError) toast('Синхронизация выполнена, но данные не обновились: ' + state.loadError, 'error');
    else toast('График и репертуар синхронизированы');
  } catch (e) {
    state.syncing = false;
    renderSync();
    toast('Ошибка синхронизации: ' + e.message, 'error');
  }
}

function tickSync() {
  if (state.syncing) return;
  state.nextSync -= 1;
  if (state.nextSync <= 0) state.nextSync = 60;
  const countdown = $('#sync-countdown');
  if (countdown) countdown.textContent = String(state.nextSync);
}

/* ---------- Оверлеи ---------- */
function openModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  toggleProfile(false);
  modal.classList.add('open');
  modal.setAttribute('aria-hidden', 'false');
  document.body.classList.add('no-scroll');
  setTimeout(() => {
    const target = modal.querySelector('input:not([type="hidden"]):not([disabled]), textarea:not([disabled]), select:not([disabled]), button[type="submit"]');
    if (target) target.focus({ preventScroll: true });
  }, 70);
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return;
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden', 'true');
  if (id === 'date-modal') state.dateDraft = null;
  if (!$$('.modal.open').length && !$('#song-drawer')?.classList.contains('open')) {
    document.body.classList.remove('no-scroll');
  }
}

function closeTopModal() {
  const open = $$('.modal.open');
  if (open.length) closeModal(open[open.length - 1].id);
}

/* ---------- Управление датой ---------- */
function openDateModal(dateId) {
  const date = dateById(dateId);
  if (!date) return;
  state.dateDraft = {
    id: date.id,
    raw: date.raw,
    color: date.color,
    duties: [...date.duties],
    songs: [...date.songs],
  };
  renderDateModal();
  openModal('date-modal');
}

function captureDraftRaw() {
  const input = $('#edit-date-raw');
  if (input && state.dateDraft) state.dateDraft.raw = input.value;
}

function renderDateModal() {
  const draft = state.dateDraft;
  if (!draft) return;
  const date = dateById(draft.id);
  if (!date) return;
  const admin = isAdmin();
  const iso = dateFromRaw(draft.raw) || date.date;
  const title = $('#date-modal-title');
  const eyebrow = $('#date-modal-eyebrow');
  const body = $('#date-modal-body');
  const foot = $('#date-modal-foot');
  if (!title || !body || !foot) return;

  if (eyebrow) eyebrow.textContent = admin ? 'Управление датой' : 'Информация о дате';
  title.textContent = formatFull(iso);

  const dutyOptions = USERS.map((u) => {
    const on = draft.duties.includes(u.id);
    return `<button type="button" class="duty-option ${on ? 'is-on' : ''}" data-action="draft-duty" data-user="${esc(u.id)}" ${admin ? '' : 'disabled'}>
      <span class="avatar avatar--sm" style="background:${u.color}">${esc(initials(u.name))}</span>
      <span>${esc(u.name)}</span>
      ${on ? icon('check') : ''}
    </button>`;
  }).join('');

  const repItems = draft.songs.map((sid, index) => {
    const song = songById(sid);
    if (!song) return '';
    return `<div class="edit-rep__item">
      <span class="rep-item__num">${index + 1}</span>
      <span class="dot tone-${safeTone(song.color)}"></span>
      <span class="edit-rep__name">${esc(song.title)}</span>
      ${admin ? `<span class="rep-actions">
        <button type="button" class="icon-btn" data-action="draft-move-song" data-song="${esc(song.id)}" data-dir="-1" aria-label="Поднять песню" title="Выше" ${index === 0 ? 'disabled' : ''}>${icon('chevron-down', 'rep-move--up')}</button>
        <button type="button" class="icon-btn" data-action="draft-move-song" data-song="${esc(song.id)}" data-dir="1" aria-label="Опустить песню" title="Ниже" ${index === draft.songs.length - 1 ? 'disabled' : ''}>${icon('chevron-down')}</button>
        <button type="button" class="icon-btn" data-action="draft-remove-song" data-song="${esc(song.id)}" aria-label="Убрать песню" title="Убрать из репертуара">${icon('close')}</button>
      </span>` : ''}
    </div>`;
  }).join('');

  const available = state.songs.filter((song) => !draft.songs.includes(song.id));
  const addSelect = admin && available.length
    ? `<div class="edit-rep-add">
        <select class="select select--block" id="edit-add-song" aria-label="Добавить песню в репертуар">
          <option value="">Добавить песню…</option>
          ${available.map((song) => `<option value="${esc(song.id)}">${esc(song.title)}</option>`).join('')}
        </select>
        <button type="button" class="btn btn--ghost btn--sm" data-action="draft-add-song">${icon('plus')} Добавить</button>
      </div>`
    : '';

  const colors = TONES.map((tone) => `<span class="color-dot tone-${tone} ${draft.color === tone ? 'active' : ''}" aria-hidden="true"></span>`).join('');

  body.innerHTML = `
    <section class="modal__section">
      <div class="modal__section-head"><h3>Дата и пояснение</h3><span>ДД.ММ.ГГГГ (пояснение)</span></div>
      ${admin
        ? `<input class="input" id="edit-date-raw" value="${esc(draft.raw)}" placeholder="25.10.2026 (утро 10-12)" autocomplete="off" />`
        : `<p class="readonly-line">${esc(draft.raw)}</p>`}
      <div class="duties" style="margin-top:10px">
        <p class="duties__label">Цветовая метка</p>
        <div class="color-picker">${colors}</div>
        <p class="muted-text" style="margin-top:6px">Метка синхронизируется из Google Sheets.</p>
      </div>
      <p class="inline-error" id="date-modal-error"></p>
    </section>

    <section class="modal__section">
      <div class="modal__section-head"><h3>Дежурные</h3><span>${draft.duties.length} из ${MAX_PER_DAY}</span></div>
      <div class="duty-picker">${dutyOptions}</div>
      <p class="inline-error" id="duty-modal-error"></p>
    </section>

    <section class="modal__section">
      <div class="modal__section-head"><h3>Репертуар</h3><span>${draft.songs.length} ${plural(draft.songs.length, ['песня', 'песни', 'песен'])}</span></div>
      ${draft.songs.length ? `<div class="edit-rep">${repItems}</div>` : '<p class="muted-text">Песни не добавлены.</p>'}
      ${addSelect}
    </section>

    ${admin ? `<section class="modal__section modal__section--danger">
      <p>Удаление даты снимет дежурных и репертуар. Действие нельзя отменить.</p>
      <button type="button" class="btn btn--danger btn--sm" data-action="delete-date">${icon('trash')} Удалить дату</button>
    </section>` : ''}`;

  foot.innerHTML = admin
    ? `<button type="button" class="btn btn--ghost" data-close-modal="date-modal">Отмена</button>
       <button type="button" class="btn btn--primary" data-action="save-date">${icon('check')} Сохранить изменения</button>`
    : `<button type="button" class="btn btn--primary" data-close-modal="date-modal">Закрыть</button>`;
}

async function saveDateDraft() {
  const draft = state.dateDraft;
  const date = draft ? dateById(draft.id) : null;
  if (!draft || !date) return;
  captureDraftRaw();
  const raw = draft.raw.trim();
  const iso = dateFromRaw(raw);
  const error = $('#date-modal-error');
  if (!raw) {
    if (error) error.textContent = 'Введите дату';
    return;
  }
  if (!iso) {
    if (error) error.textContent = 'Не удалось распознать дату. Используйте формат ДД.ММ.ГГГГ';
    return;
  }
  if (state.dates.some((d) => d.id !== date.id && d.raw.trim().toLowerCase() === raw.toLowerCase())) {
    if (error) error.textContent = 'Такая дата уже есть в графике';
    return;
  }

  const saveBtn = $('[data-action="save-date"]');
  if (saveBtn) saveBtn.disabled = true;
  const oldRaw = date.raw;
  const oldDuties = [...date.duties];
  const oldSongs = [...date.songs];
  const newSongs = [...draft.songs];
  let targetRaw = oldRaw;

  try {
    if (raw !== oldRaw) {
      const renamed = await apiJson(`/duty/dates/${encodeURIComponent(oldRaw)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_date_str: raw }),
      });
      targetRaw = renamed.date_str || raw;
    }

    const dutyNames = new Set([...oldDuties, ...draft.duties]);
    for (const name of dutyNames) {
      const was = oldDuties.includes(name);
      const now = draft.duties.includes(name);
      if (was === now) continue;
      await apiFetch('/duty/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date_str: targetRaw, user_name: name, value: now }),
      });
    }

    if (oldSongs.join('\u0000') !== newSongs.join('\u0000')) {
      await apiFetch(`/repertoire/${encodeURIComponent(targetRaw)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ songs: newSongs }),
      });
    }

    state.dateDraft = null;
    closeModal('date-modal');
    toast('Изменения сохранены');
    await refreshData();
  } catch (e) {
    if (error) error.textContent = e.message;
    toast('Не удалось сохранить дату: ' + e.message, 'error');
    await refreshData();
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

function deleteDateDraft() {
  const draft = state.dateDraft;
  const date = draft ? dateById(draft.id) : null;
  if (!draft || !date) return;
  askConfirm({
    title: `Удалить ${formatShort(date.date)}?`,
    text: 'Дата, дежурные и репертуар будут удалены из графика и Google Sheets.',
    confirmLabel: 'Удалить дату',
    onConfirm: async () => {
      try {
        await apiFetch(`/duty/dates/${encodeURIComponent(date.raw)}`, { method: 'DELETE' });
        state.dateDraft = null;
        closeModal('confirm-modal');
        closeModal('date-modal');
        toast('Дата удалена', 'info');
        await refreshData();
      } catch (e) {
        toast('Не удалось удалить дату: ' + e.message, 'error');
      }
    },
  });
}

/* ---------- Новая дата ---------- */
function openAddDateModal() {
  const input = $('#add-date-input');
  const error = $('#add-date-error');
  if (input) input.value = '';
  if (error) error.textContent = '';
  openModal('add-date-modal');
  setTimeout(() => input && input.focus(), 60);
}

async function saveNewDate() {
  const input = $('#add-date-input');
  const error = $('#add-date-error');
  const raw = (input?.value || '').trim();
  if (!raw) {
    if (error) error.textContent = 'Введите дату';
    return;
  }
  const iso = dateFromRaw(raw);
  if (!iso) {
    if (error) error.textContent = 'Не удалось распознать дату. Используйте формат ДД.ММ.ГГГГ';
    return;
  }
  if (state.dates.some((d) => d.raw.trim().toLowerCase() === raw.toLowerCase())) {
    if (error) error.textContent = 'Такая дата уже есть в графике';
    return;
  }

  const saveBtn = $('#add-date-save');
  if (saveBtn) saveBtn.disabled = true;
  try {
    await apiFetch('/duty/dates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date_str: raw }),
    });
    closeModal('add-date-modal');
    toast(`Дата ${formatShort(iso)} добавлена`);
    state.scheduleTab = 'upcoming';
    state.datePage = 1;
    await refreshData();
    go('schedule', { silent: true });
  } catch (e) {
    if (error) error.textContent = e.message;
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

/* ---------- Песня: форма ---------- */
function openSongForm(songId = null) {
  const song = songId ? songById(songId) : null;
  state.editingSongId = song ? song.id : null;
  state.reopenDrawerAfterSongSave = !!song && $('#song-drawer')?.classList.contains('open');
  if ($('#song-drawer')?.classList.contains('open')) closeDrawer();

  const title = $('#song-modal-title');
  const eyebrow = $('#song-modal-eyebrow');
  const name = $('#song-name');
  const text = $('#song-text');
  const error = $('#song-error');
  if (title) title.textContent = song ? 'Редактировать песню' : 'Добавить песню';
  if (eyebrow) eyebrow.textContent = song ? 'Песня · ' + song.title : 'Библиотека';
  if (name) {
    name.value = song ? song.title : '';
    name.readOnly = !!song;
    name.title = song ? 'Название песни нельзя изменить' : '';
  }
  if (text) text.value = song ? song.text : '';
  if (error) error.textContent = '';
  openModal('song-modal');
  setTimeout(() => {
    if (!name) return;
    if (song) text?.focus();
    else name.focus();
  }, 60);
}

async function saveSongForm() {
  const nameInput = $('#song-name');
  const name = (nameInput?.value || '').trim();
  const text = ($('#song-text')?.value || '').replace(/\r\n/g, '\n').trim();
  const error = $('#song-error');
  const editing = state.editingSongId;
  if (name.length < 2) {
    if (error) error.textContent = 'Введите название песни';
    return;
  }
  if (!editing && state.songs.some((song) => song.title.toLowerCase() === name.toLowerCase())) {
    if (error) error.textContent = 'Песня с таким названием уже есть';
    return;
  }

  const saveBtn = $('#song-save');
  if (saveBtn) saveBtn.disabled = true;
  try {
    if (editing) {
      await apiFetch(`/songs/${encodeURIComponent(editing)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      toast('Песня обновлена');
    } else {
      await apiFetch('/songs/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, text }),
      });
      toast('Песня добавлена');
    }

    closeModal('song-modal');
    const reopenId = editing || name;
    await refreshData();
    if (state.reopenDrawerAfterSongSave && reopenId) {
      state.reopenDrawerAfterSongSave = false;
      openSongDrawer(reopenId);
    }
  } catch (e) {
    if (error) error.textContent = e.message;
  } finally {
    if (saveBtn) saveBtn.disabled = false;
  }
}

function deleteSong(songId) {
  const song = songById(songId);
  if (!song) return;
  const used = datesForSong(songId).length;
  askConfirm({
    title: `Удалить «${song.title}»?`,
    text: used
      ? `Песня используется на ${used} ${plural(used, ['дате', 'датах', 'датах'])} и будет убрана из репертуара.`
      : 'Песня будет удалена из библиотеки.',
    confirmLabel: 'Удалить песню',
    onConfirm: async () => {
      try {
        await apiFetch(`/songs/${encodeURIComponent(song.title)}`, { method: 'DELETE' });
        if (state.selectedSongId === songId) closeDrawer();
        closeModal('confirm-modal');
        toast('Песня удалена', 'info');
        await refreshData();
      } catch (e) {
        toast('Не удалось удалить песню: ' + e.message, 'error');
      }
    },
  });
}

/* ---------- Подтверждение ---------- */
function askConfirm({ title, text, confirmLabel = 'Удалить', onConfirm }) {
  const titleEl = $('#confirm-title');
  const textEl = $('#confirm-text');
  const btn = $('#confirm-yes');
  if (titleEl) titleEl.textContent = title;
  if (textEl) textEl.textContent = text;
  if (btn) btn.textContent = confirmLabel;
  state.confirmAction = typeof onConfirm === 'function' ? onConfirm : null;
  openModal('confirm-modal');
}

/* ---------- Вход ---------- */
function renderLoginUsers() {
  const list = $('#login-user-list');
  if (!list) return;
  if (!state.loginUsers.length) {
    list.innerHTML = '<p class="muted-text">Пользователи не найдены</p>';
    return;
  }
  list.innerHTML = state.loginUsers.map((name) => {
    const user = userById(name) || { id: name, name, role: 'user', color: colorForName(name) };
    const selected = name === state.loginUser;
    return `<button type="button" class="user-option ${selected ? 'is-selected' : ''}" data-action="login-pick" data-user="${esc(name)}" role="option" aria-selected="${selected}">
      <span class="avatar avatar--sm" style="background:${user.color}">${esc(initials(user.name))}</span>
      <span class="user-option__name">${esc(user.name)}</span>
      ${selected ? icon('check') : ''}
    </button>`;
  }).join('');
}

async function openLogin() {
  if (!state.loginUsers.length) {
    try {
      await loadLoginUsers();
    } catch (e) {
      state.loginUsers = [];
    }
  }
  if (!state.loginUser || !state.loginUsers.includes(state.loginUser)) {
    state.loginUser = state.currentUserId && state.loginUsers.includes(state.currentUserId)
      ? state.currentUserId
      : (state.loginUsers[0] || null);
  }
  const pin = $('#login-pin');
  const error = $('#login-error');
  const submit = $('#login-submit');
  if (pin) {
    pin.value = '';
    pin.type = 'password';
  }
  if (error) error.textContent = '';
  if (submit) {
    submit.disabled = false;
    submit.textContent = 'Войти';
  }
  const eye = $('#login-eye');
  if (eye) {
    eye.setAttribute('aria-pressed', 'false');
    eye.innerHTML = icon('eye');
  }
  renderLoginUsers();
  openModal('login-modal');
  setTimeout(() => pin && pin.focus(), 80);
}

async function submitLogin(event) {
  event.preventDefault();
  const pin = ($('#login-pin')?.value || '').trim();
  const error = $('#login-error');
  const submit = $('#login-submit');
  const fail = (message) => {
    if (error) {
      error.textContent = message;
      error.classList.remove('shake');
      void error.offsetWidth;
      error.classList.add('shake');
    }
  };
  if (!state.loginUser) return fail('Выберите пользователя');
  if (!/^\d{4,12}$/.test(pin)) return fail('Введите PIN-код (4–12 цифр)');

  if (submit) {
    submit.disabled = true;
    submit.innerHTML = `${icon('sync', 'spin')} Проверяем…`;
  }

  try {
    const resp = await fetch(API_BASE + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: state.loginUser, pin }),
    });
    if (!resp.ok) throw new Error(await parseApiError(resp));
    const data = await resp.json();
    if (!data.success || !data.token) throw new Error('Не удалось войти');

    setSession(state.loginUser, data.role, data.token);
    writeStore('lastLoginUser', state.loginUser);
    closeModal('login-modal');
    closeDrawer();
    await refreshData();
    const user = currentUser();
    if (state.loadError) toast('Вы вошли, но данные не загрузились: ' + state.loadError, 'error');
    else toast(`Добро пожаловать, ${user ? user.name : state.loginUser}`);
    if (!isAdmin() && (state.page === 'users' || state.page === 'sync')) {
      go('schedule', { push: true, silent: true });
    }
  } catch (e) {
    fail(e.message === 'Invalid credentials' ? 'Неверный PIN-код' : e.message);
    if (submit) {
      submit.disabled = false;
      submit.textContent = 'Войти';
    }
    const pinInput = $('#login-pin');
    if (pinInput) pinInput.select();
  }
}

function logout(options = {}) {
  clearSession();
  toggleProfile(false);
  closeDrawer();
  renderAll();
  if (!options.silent) toast('Вы вышли из системы', 'info');
  if (state.page === 'users' || state.page === 'sync') {
    go('schedule', { push: true, silent: true });
  }
}

/* ---------- Обработчики действий ---------- */
function handleAction(el) {
  const action = el.dataset.action;
  const dateId = el.dataset.date || el.dataset.id;
  const userId = el.dataset.user;
  const songId = el.dataset.song;

  switch (action) {
    case 'toggle-rep':
      if (state.openReps.has(dateId)) state.openReps.delete(dateId);
      else state.openReps.add(dateId);
      renderSchedule();
      break;
    case 'toggle-duty':
      toggleDuty(dateId, userId);
      break;
    case 'edit-date':
      openDateModal(dateId);
      break;
    case 'date-page':
      state.datePage = Number(el.dataset.page) || 1;
      renderSchedule();
      break;
    case 'open-song':
      openSongDrawer(songId);
      break;
    case 'copy-song': {
      const song = songById(songId);
      copyText(song ? song.text : '');
      break;
    }
    case 'edit-song':
      openSongForm(songId);
      break;
    case 'delete-song':
      deleteSong(songId);
      break;
    case 'song-page':
      state.songPage = Number(el.dataset.page) || 1;
      renderSongs();
      break;
    case 'open-login':
      openLogin();
      break;
    case 'login-pick':
      state.loginUser = userId;
      renderLoginUsers();
      break;
    case 'profile-mine':
      toggleProfile(false);
      state.scheduleTab = 'mine';
      state.datePage = 1;
      go('schedule');
      renderSchedule();
      break;
    case 'profile-switch':
      toggleProfile(false);
      logout({ silent: true });
      openLogin();
      break;
    case 'logout':
      logout();
      break;
    case 'toggle-theme':
      toggleTheme();
      break;
    case 'go-tab':
      setScheduleTab(el.dataset.tab || 'upcoming');
      break;
    case 'reset-person':
      state.personFilter = '';
      state.datePage = 1;
      renderSchedule();
      break;
    case 'reset-songs':
      state.songsQuery = '';
      state.songsFilter = 'all';
      state.songPage = 1;
      renderSongs();
      break;
    case 'change-pin':
      openPinModal(userId);
      break;
    case 'toggle-role':
      toggleUserRole(userId);
      break;
    case 'delete-user':
      deleteUser(userId);
      break;
    case 'search-date':
      closeDrawer();
      openDateModal(el.dataset.id);
      break;
    case 'draft-duty': {
      if (!isAdmin() || !state.dateDraft) break;
      captureDraftRaw();
      const draft = state.dateDraft;
      const index = draft.duties.indexOf(userId);
      const error = $('#duty-modal-error');
      if (index >= 0) {
        draft.duties.splice(index, 1);
      } else if (draft.duties.length >= MAX_PER_DAY) {
        if (error) error.textContent = `Не больше ${MAX_PER_DAY} дежурных на дату`;
        break;
      } else {
        draft.duties.push(userId);
      }
      renderDateModal();
      break;
    }
    case 'draft-add-song': {
      if (!isAdmin() || !state.dateDraft) break;
      captureDraftRaw();
      const select = $('#edit-add-song');
      const selected = select ? select.value : '';
      if (selected && !state.dateDraft.songs.includes(selected)) {
        state.dateDraft.songs.push(selected);
        renderDateModal();
      }
      break;
    }
    case 'draft-move-song': {
      if (!isAdmin() || !state.dateDraft) break;
      captureDraftRaw();
      const direction = Number(el.dataset.dir) || 0;
      const index = state.dateDraft.songs.indexOf(songId);
      const target = index + direction;
      if (!direction || index < 0 || target < 0 || target >= state.dateDraft.songs.length) break;
      [state.dateDraft.songs[index], state.dateDraft.songs[target]] = [state.dateDraft.songs[target], state.dateDraft.songs[index]];
      renderDateModal();
      break;
    }
    case 'draft-remove-song': {
      if (!isAdmin() || !state.dateDraft) break;
      captureDraftRaw();
      state.dateDraft.songs = state.dateDraft.songs.filter((id) => id !== songId);
      renderDateModal();
      break;
    }
    case 'save-date':
      saveDateDraft();
      break;
    case 'delete-date':
      deleteDateDraft();
      break;
    case 'run-sync':
      runSync();
      break;
    case 'reload':
      bootstrap();
      break;
    default:
      break;
  }
}

/* ---------- События ---------- */
function bindEvents() {
  $('#menu-btn')?.addEventListener('click', openSidebar);
  $('#sidebar-scrim')?.addEventListener('click', closeSidebar);
  $('#theme-toggle')?.addEventListener('click', toggleTheme);
  $('#profile-btn')?.addEventListener('click', (event) => {
    event.stopPropagation();
    toggleProfile();
  });
  $('#head-add-date')?.addEventListener('click', openAddDateModal);
  $('#head-add-song')?.addEventListener('click', () => openSongForm());
  $('#head-add-user')?.addEventListener('click', openUserModal);

  $('#person-filter')?.addEventListener('change', (event) => {
    state.personFilter = event.target.value;
    state.datePage = 1;
    renderSchedule();
  });
  $$('[data-schedule-tab]').forEach((btn) => {
    btn.addEventListener('click', () => setScheduleTab(btn.dataset.scheduleTab));
  });
  $('#reset-filter')?.addEventListener('click', () => {
    state.personFilter = '';
    state.datePage = 1;
    renderSchedule();
  });

  $('#songs-search')?.addEventListener('input', (event) => {
    state.songsQuery = event.target.value;
    state.songPage = 1;
    renderSongs();
  });
  $$('[data-song-filter]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.songsFilter = btn.dataset.songFilter;
      state.songPage = 1;
      renderSongs();
    });
  });
  $('#songs-sort')?.addEventListener('change', (event) => {
    state.songsSort = event.target.value;
    state.songPage = 1;
    renderSongs();
  });

  $('#login-form')?.addEventListener('submit', submitLogin);
  $('#login-guest')?.addEventListener('click', () => closeModal('login-modal'));
  $('#login-eye')?.addEventListener('click', () => {
    const input = $('#login-pin');
    const eye = $('#login-eye');
    if (!input || !eye) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    eye.setAttribute('aria-pressed', String(show));
    eye.setAttribute('aria-label', show ? 'Скрыть PIN-код' : 'Показать PIN-код');
    eye.innerHTML = icon(show ? 'eye-off' : 'eye');
  });

  $('#add-date-save')?.addEventListener('click', saveNewDate);
  $('#add-date-input')?.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      saveNewDate();
    }
  });
  $('#add-date-presets')?.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-preset]');
    if (!btn) return;
    const input = $('#add-date-input');
    if (input) {
      input.value = btn.dataset.preset;
      input.focus();
    }
  });

  $('#song-save')?.addEventListener('click', saveSongForm);
  $('#user-save')?.addEventListener('click', saveUser);
  $('#pin-save')?.addEventListener('click', savePin);
  $('#confirm-yes')?.addEventListener('click', () => {
    const fn = state.confirmAction;
    if (fn) fn();
  });
  $('#sync-refresh')?.addEventListener('click', async () => {
    if (state.syncing) return;
    await refreshData();
    if (state.loadError) toast('Не удалось обновить журнал: ' + state.loadError, 'error');
    else toast('Журнал обновлён', 'info');
  });

  $('#drawer-close')?.addEventListener('click', closeDrawer);
  $('#scrim')?.addEventListener('click', closeDrawer);

  document.addEventListener('click', (event) => {
    const closeEl = event.target.closest('[data-close-modal]');
    if (closeEl) {
      closeModal(closeEl.dataset.closeModal);
      return;
    }
    const actionEl = event.target.closest('[data-action]');
    if (actionEl) {
      if (actionEl.tagName === 'A') event.preventDefault();
      handleAction(actionEl);
    }
    const pageEl = event.target.closest('[data-page]');
    if (pageEl) {
      event.preventDefault();
      go(pageEl.dataset.page);
    }
    if (!event.target.closest('#profile')) toggleProfile(false);
  });

  document.addEventListener('keydown', (event) => {
    const key = event.key;

    if (key === 'Escape') {
      const openModals = $$('.modal.open');
      if (openModals.length) {
        closeTopModal();
        return;
      }
      if ($('#song-drawer')?.classList.contains('open')) {
        closeDrawer();
        return;
      }
      toggleProfile(false);
      closeSidebar();
    }
  });

  window.addEventListener('hashchange', () => {
    const page = (location.hash || '').replace('#', '');
    go(PAGE_META[page] ? page : 'schedule', { push: false, silent: true });
  });
}

/* ---------- Запуск ---------- */
function init() {
  setTheme(state.theme);
  bindEvents();
  applyRole();
  renderProfile();
  renderSidebar();
  renderSchedule();
  setInterval(tickSync, 1000);
  bootstrap();
}

init();
