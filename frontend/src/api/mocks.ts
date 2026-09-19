// Demo data for UI work without a backend (VITE_USE_MOCKS=1). Test data, not real stores or people.
import { ApiError } from './errors';
import type {
  Dashboard,
  Me,
  Schedule,
  StoreDay,
  StoreWithPeople,
  TaskTemplateItem,
} from './types';

const iso = (date: Date) => date.toISOString().slice(0, 10);
const today = new Date();
const nextMonday = new Date(today);
nextMonday.setDate(today.getDate() + ((8 - today.getDay()) % 7 || 7));
const day = (offset: number) => {
  const d = new Date(nextMonday);
  d.setDate(nextMonday.getDate() + offset);
  return iso(d);
};

const me: Me = { max_user_id: 1, first_name: 'Демо', role: 'owner', network: { id: 1, name: 'Демо-сеть' } };

const dashboard: Dashboard = {
  date: iso(today),
  stores: [
    { id: 1, name: 'Ленина, 14', done: 4, total: 6, health: 'overdue', last_event_label: 'открытие в 09:40' },
    { id: 2, name: 'Гагарина, 3', done: 5, total: 6, health: 'ok', last_event_label: 'последнее 14:20' },
    { id: 3, name: 'ТЦ «Восход»', done: 4, total: 5, health: 'ok', last_event_label: 'последнее 13:05' },
  ],
};

const storeDay: StoreDay = {
  store: { id: 1, name: 'Ленина, 14' },
  date: iso(today),
  on_shift: [{ name: 'Анна', start: '09:00', end: '17:00' }],
  tasks: [
    { id: 1, title: 'Открытие магазина', planned_time: '09:00', status: 'done_late', late_minutes: 40, done_by: 'Анна', done_at: '09:40', claimed_by: null, photo_url: null },
    { id: 2, title: 'Подготовка зала', planned_time: '10:00', status: 'done_on_time', late_minutes: 0, done_by: 'Анна', done_at: '09:55', claimed_by: null, photo_url: null },
    { id: 3, title: 'Приёмка поставки', planned_time: '14:00', status: 'unclaimed', late_minutes: null, done_by: null, done_at: null, claimed_by: null, photo_url: null },
    { id: 4, title: 'Закрытие смены', planned_time: '22:00', status: 'scheduled', late_minutes: null, done_by: null, done_at: null, claimed_by: null, photo_url: null },
  ],
};

const schedule: Schedule = {
  week_start: day(0),
  status: 'draft',
  employees: [
    { id: 1, name: 'Анна' },
    { id: 2, name: 'Игорь' },
    { id: 3, name: 'Даша' },
  ],
  shifts: [
    { employee_id: 1, date: day(0), start: '09:00', end: '17:00' },
    { employee_id: 1, date: day(1), start: '09:00', end: '17:00' },
    { employee_id: 1, date: day(3), start: '09:00', end: '17:00' },
    { employee_id: 2, date: day(0), start: '14:00', end: '22:00' },
    { employee_id: 2, date: day(2), start: '09:00', end: '17:00' },
    { employee_id: 2, date: day(3), start: '14:00', end: '17:00' },
    { employee_id: 3, date: day(1), start: '17:00', end: '22:00' },
    { employee_id: 3, date: day(2), start: '17:00', end: '22:00' },
  ],
  gaps: [{ date: day(3), start: '17:00', end: '22:00' }],
};

const taskTemplates: TaskTemplateItem[] = [
  { id: 1, title: 'Открытие магазина', kind: 'daily', planned_time: '09:00', on_date: null, tolerance_minutes: 15, requires_photo: true, requires_claim: false },
  { id: 2, title: 'Подготовка зала', kind: 'daily', planned_time: '10:00', on_date: null, tolerance_minutes: 30, requires_photo: true, requires_claim: false },
  { id: 3, title: 'Приёмка поставки', kind: 'one_time', planned_time: '14:00', on_date: day(3), tolerance_minutes: 30, requires_photo: true, requires_claim: true },
  { id: 4, title: 'Закрытие смены', kind: 'daily', planned_time: '22:00', on_date: null, tolerance_minutes: 20, requires_photo: true, requires_claim: false },
];

const stores: StoreWithPeople[] = [
  {
    id: 1,
    name: 'Ленина, 14',
    address: 'ул. Ленина, 14',
    employees: [
      { id: 1, name: 'Анна К.', status: 'connected' },
      { id: 2, name: 'Игорь М.', status: 'connected' },
      { id: 3, name: 'Даша П.', status: 'invited' },
      { id: 4, name: 'Пётр С.', status: 'dismissed' },
    ],
  },
  { id: 2, name: 'Гагарина, 3', address: 'ул. Гагарина, 3', employees: [] },
  { id: 3, name: 'ТЦ «Восход»', address: 'пр. Мира, 1', employees: [] },
];

const routes: [RegExp, unknown][] = [
  [/^\/me\/$/, me],
  [/^\/dashboard\/(\?.*)?$/, dashboard],
  [/^\/stores\/$/, stores],
  [/^\/stores\/\d+\/day\/(\?.*)?$/, storeDay],
  [/^\/stores\/\d+\/schedule\/(\?.*)?$/, schedule],
  [/^\/stores\/\d+\/task-templates\/$/, taskTemplates],
];

export async function mockGet<T>(path: string): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 200));
  const route = routes.find(([pattern]) => pattern.test(path));
  if (!route) throw new ApiError(404, 'no_mock', `no mock for ${path}`);
  return route[1] as T;
}
