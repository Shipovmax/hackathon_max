// Демо-данные для работы над интерфейсом без бэкенда (VITE_USE_MOCKS=1).
// Это тестовые данные: магазинов, людей и отметок из этого файла не существует.
// Хранилище изменяемое, поэтому редактирование работает так же, как будет с API,
// но живёт до перезагрузки страницы.
import { findGaps } from '../lib/coverage';
import { addDays, DEFAULT_LEAD_MINUTES, earlierBy, minutesOf, today, weekStart } from '../lib/format';
import { ApiError } from './errors';
import type {
  Dashboard,
  DashboardStore,
  DayTask,
  Gap,
  Me,
  Person,
  Schedule,
  ScheduleDraft,
  ShiftInput,
  StoreDay,
  StoreInput,
  StoreWithPeople,
  TaskTemplateInput,
  TaskTemplateItem,
} from './types';

const TODAY = today();

/** Время незадолго до «сейчас»: сценарий с невзятой поставкой должен быть виден
    в демо в любой час, а не только после 14:00. */
function recentTime(minutesBack: number): string {
  const moment = new Date(Date.now() - minutesBack * 60_000);
  const rounded = Math.floor(moment.getMinutes() / 30) * 30;
  return `${String(moment.getHours()).padStart(2, '0')}:${String(rounded).padStart(2, '0')}`;
}

const DELIVERY_TIME = recentTime(90);
const THIS_WEEK = weekStart(TODAY);
const NEXT_WEEK = addDays(THIS_WEEK, 7);

// Заглушка вместо снимка торгового зала: настоящие фото приходят из бота.
const DEMO_PHOTO =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800">
      <rect width="600" height="800" fill="#d8dee8"/>
      <rect x="40" y="300" width="520" height="300" fill="#b9c3d2"/>
      <circle cx="300" cy="180" r="70" fill="#c9d2df"/>
      <text x="300" y="720" font-family="sans-serif" font-size="30" fill="#6b7686" text-anchor="middle">
        демо-фото торгового зала
      </text>
    </svg>`,
  );

interface Store extends StoreWithPeople {
  timezone: string;
}

interface Db {
  stores: Store[];
  templates: Record<number, TaskTemplateItem[]>;
  shifts: Record<number, ShiftInput[]>;
  published: string[];
  nextId: number;
}

const template = (
  id: number,
  title: string,
  planned_time: string,
  tolerance_minutes: number,
  extra: Partial<TaskTemplateItem> = {},
): TaskTemplateItem => ({
  id,
  title,
  kind: 'daily',
  planned_time,
  available_from: earlierBy(planned_time, DEFAULT_LEAD_MINUTES),
  on_date: null,
  tolerance_minutes,
  requires_photo: true,
  requires_claim: false,
  ...extra,
});

const person = (id: number, name: string, status: Person['status'], invite_code: string | null = null): Person => ({
  id,
  name,
  status,
  invite_code,
});

const db: Db = {
  stores: [
    {
      id: 1,
      name: 'Ленина, 14',
      address: 'ул. Ленина, 14',
      open_time: '09:00',
      close_time: '22:00',
      timezone: 'Europe/Moscow',
      employees: [
        person(1, 'Анна К.', 'connected'),
        person(2, 'Игорь М.', 'connected'),
        person(3, 'Даша П.', 'invited', 'K4M7QX'),
        person(4, 'Пётр С.', 'dismissed'),
      ],
    },
    {
      id: 2,
      name: 'Гагарина, 3',
      address: 'ул. Гагарина, 3',
      open_time: '10:00',
      close_time: '21:00',
      timezone: 'Europe/Moscow',
      employees: [person(5, 'Ольга В.', 'connected'), person(6, 'Сергей Л.', 'connected')],
    },
    {
      id: 3,
      name: 'ТЦ «Восход»',
      address: 'пр. Мира, 1',
      open_time: '10:00',
      close_time: '22:00',
      timezone: 'Europe/Moscow',
      employees: [person(7, 'Марина Д.', 'connected')],
    },
  ],
  templates: {
    1: [
      template(1, 'Открытие магазина', '09:00', 15),
      template(2, 'Подготовка зала', '10:00', 30),
      template(3, 'Приёмка поставки', DELIVERY_TIME, 30, { kind: 'one_time', on_date: TODAY, requires_claim: true }),
      template(4, 'Закрытие смены', '22:00', 20),
    ],
    2: [
      template(11, 'Открытие магазина', '10:00', 15),
      template(12, 'Подготовка зала', '11:00', 30),
      template(13, 'Пересчёт кассы', '20:00', 20, { requires_claim: true }),
      template(14, 'Закрытие смены', '21:00', 20),
    ],
    3: [
      template(21, 'Открытие магазина', '10:00', 15),
      template(22, 'Подготовка зала', '11:00', 30),
      template(23, 'Закрытие смены', '22:00', 20),
    ],
  },
  shifts: {
    1: [
      ...weekShifts(THIS_WEEK, 1, [0, 1, 3, 4], '09:00', '17:00'),
      ...weekShifts(THIS_WEEK, 2, [0, 2, 4, 5], '14:00', '22:00'),
      ...weekShifts(THIS_WEEK, 3, [1, 2, 3, 5, 6], '17:00', '22:00'),
      ...weekShifts(NEXT_WEEK, 1, [0, 1, 3], '09:00', '17:00'),
      ...weekShifts(NEXT_WEEK, 2, [0, 2], '14:00', '22:00'),
      ...weekShifts(NEXT_WEEK, 2, [3], '14:00', '17:00'),
      ...weekShifts(NEXT_WEEK, 3, [1, 2], '17:00', '22:00'),
    ],
    2: [
      ...weekShifts(THIS_WEEK, 5, [0, 1, 2, 3, 4], '10:00', '21:00'),
      ...weekShifts(THIS_WEEK, 6, [5, 6], '10:00', '21:00'),
    ],
    3: [...weekShifts(THIS_WEEK, 7, [0, 1, 2, 3, 4, 5, 6], '10:00', '22:00')],
  },
  published: [`1:${THIS_WEEK}`, `2:${THIS_WEEK}`, `3:${THIS_WEEK}`],
  nextId: 100,
};

function weekShifts(week: string, employeeId: number, days: number[], start: string, end: string): ShiftInput[] {
  return days.map((offset) => ({ employee_id: employeeId, date: addDays(week, offset), start, end }));
}

const me: Me = {
  max_user_id: 1,
  first_name: 'Демо',
  role: 'owner',
  network: { id: 1, name: 'Демо-сеть' },
};

const nextId = () => db.nextId++;

function store(id: number): Store {
  const found = db.stores.find((item) => item.id === id);
  if (!found) throw new ApiError(404, 'not_found', 'Точка не найдена');
  return found;
}

function storeOfEmployee(employeeId: number): [Store, Person] {
  for (const item of db.stores) {
    const employee = item.employees.find((person) => person.id === employeeId);
    if (employee) return [item, employee];
  }
  throw new ApiError(404, 'not_found', 'Сотрудник не найден');
}

const inviteCode = () =>
  Array.from({ length: 6 }, () => 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[Math.floor(Math.random() * 32)]).join('');

// --- день точки -------------------------------------------------------------

function onShift(storeId: number, date: string) {
  const people = store(storeId).employees;
  return (db.shifts[storeId] ?? [])
    .filter((shift) => shift.date === date)
    .map((shift) => ({
      name: people.find((person) => person.id === shift.employee_id)?.name ?? 'Сотрудник',
      start: shift.start,
      end: shift.end,
    }))
    .sort((a, b) => minutesOf(a.start) - minutesOf(b.start));
}

/** Статусы выводим из времени, чтобы демо выглядело живым в любой день. */
function dayTasks(storeId: number, date: string): DayTask[] {
  const shift = onShift(storeId, date);
  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();

  return (db.templates[storeId] ?? [])
    .filter((item) => (item.kind === 'daily' ? true : item.on_date === date))
    .sort((a, b) => minutesOf(a.planned_time) - minutesOf(b.planned_time))
    .map((item, index): DayTask => {
      const planned = minutesOf(item.planned_time);
      const passed = date < TODAY || (date === TODAY && nowMinutes >= planned);
      const performer = shift.find((s) => minutesOf(s.start) <= planned && planned <= minutesOf(s.end)) ?? shift[0];
      const base = {
        id: item.id,
        template_id: item.id,
        title: item.title,
        planned_time: item.planned_time,
        available_from: item.available_from,
        kind: item.kind,
        late_minutes: null,
        done_by: null,
        done_at: null,
        claimed_by: null,
        photo_url: null,
      };

      if (!passed) return { ...base, status: 'scheduled' };
      // Сценарий для демо: на первой точке открытие сегодня с опозданием, поставку никто не взял.
      if (storeId === 1 && date === TODAY && item.requires_claim) return { ...base, status: 'unclaimed' };
      if (storeId === 1 && date === TODAY && index === 0) {
        return {
          ...base,
          status: 'done_late',
          late_minutes: 40,
          done_by: performer?.name ?? 'Анна К.',
          done_at: '09:40',
          photo_url: item.requires_photo ? DEMO_PHOTO : null,
        };
      }
      return {
        ...base,
        status: 'done_on_time',
        late_minutes: 0,
        done_by: performer?.name ?? 'Сотрудник',
        done_at: item.planned_time,
        photo_url: item.requires_photo ? DEMO_PHOTO : null,
      };
    });
}

function storeDay(storeId: number, date: string): StoreDay {
  const item = store(storeId);
  return {
    store: { id: item.id, name: item.name },
    date,
    on_shift: onShift(storeId, date),
    tasks: dayTasks(storeId, date),
  };
}

function dashboard(date: string): Dashboard {
  const stores = db.stores.map((item): DashboardStore => {
    const tasks = dayTasks(item.id, date);
    const done = tasks.filter((task) => task.status.startsWith('done')).length;
    const unclaimed = tasks.some((task) => task.status === 'unclaimed');
    const overdue = tasks.some((task) => task.status === 'overdue' || task.status === 'missed');
    const last = [...tasks].reverse().find((task) => task.done_at);
    return {
      id: item.id,
      name: item.name,
      done,
      total: tasks.length,
      health: unclaimed ? 'unclaimed' : overdue ? 'overdue' : 'ok',
      last_event_label: last ? `последнее ${last.done_at}` : null,
    };
  });
  const rank = (health: DashboardStore['health']) => (health === 'ok' ? 1 : 0);
  return { date, stores: stores.sort((a, b) => rank(a.health) - rank(b.health)) };
}

// --- график -----------------------------------------------------------------

const weekDates = (week: string) => Array.from({ length: 7 }, (_, index) => addDays(week, index));

function gapsOf(storeId: number, week: string, shifts?: ShiftInput[]): Gap[] {
  const item = store(storeId);
  const dates = weekDates(week);
  const source = shifts ?? (db.shifts[storeId] ?? []).filter((shift) => dates.includes(shift.date));
  return findGaps(dates, source, item.open_time, item.close_time);
}

function schedule(storeId: number, week: string): Schedule {
  const item = store(storeId);
  const dates = weekDates(week);
  return {
    week_start: week,
    status: db.published.includes(`${storeId}:${week}`) ? 'published' : 'draft',
    open_time: item.open_time,
    close_time: item.close_time,
    employees: item.employees
      .filter((person) => person.status !== 'dismissed')
      .map((person) => ({ id: person.id, name: person.name })),
    shifts: (db.shifts[storeId] ?? []).filter((shift) => dates.includes(shift.date)),
    gaps: gapsOf(storeId, week),
  };
}

function saveSchedule(storeId: number, draft: ScheduleDraft): Schedule {
  const dates = weekDates(draft.week_start);
  const others = (db.shifts[storeId] ?? []).filter((shift) => !dates.includes(shift.date));
  db.shifts[storeId] = [...others, ...draft.shifts];
  return schedule(storeId, draft.week_start);
}

// --- маршруты ---------------------------------------------------------------

type Handler = (params: string[], query: URLSearchParams, body: unknown) => unknown;

const routes: [string, RegExp, Handler][] = [
  ['GET', /^\/me\/$/, () => me],
  ['GET', /^\/completions\/(\d+)\/photo\/$/, () => DEMO_PHOTO],
  ['GET', /^\/dashboard\/$/, (_p, query) => dashboard(query.get('date') ?? TODAY)],
  ['GET', /^\/stores\/$/, () => db.stores],
  ['POST', /^\/stores\/$/, (_p, _q, body) => {
    const input = body as StoreInput;
    const created: Store = { id: nextId(), ...input, timezone: 'Europe/Moscow', employees: [] };
    db.stores.push(created);
    db.templates[created.id] = [];
    db.shifts[created.id] = [];
    return created;
  }],
  ['GET', /^\/stores\/(\d+)\/day\/$/, (p, query) => storeDay(Number(p[0]), query.get('date') ?? TODAY)],
  ['POST', /^\/stores\/(\d+)\/employees\/$/, (p, _q, body) => {
    const created = person(nextId(), (body as { name: string }).name, 'invited', inviteCode());
    store(Number(p[0])).employees.push(created);
    return created;
  }],
  ['GET', /^\/stores\/(\d+)\/task-templates\/$/, (p) => db.templates[Number(p[0])] ?? []],
  ['POST', /^\/stores\/(\d+)\/task-templates\/$/, (p, _q, body) => {
    const created: TaskTemplateItem = { id: nextId(), ...(body as TaskTemplateInput) };
    db.templates[Number(p[0])] = [...(db.templates[Number(p[0])] ?? []), created];
    return created;
  }],
  ['GET', /^\/stores\/(\d+)\/schedule\/$/, (p, query) =>
    schedule(Number(p[0]), query.get('week') ?? THIS_WEEK)],
  ['PUT', /^\/stores\/(\d+)\/schedule\/$/, (p, _q, body) => saveSchedule(Number(p[0]), body as ScheduleDraft)],
  ['POST', /^\/stores\/(\d+)\/schedule\/coverage\/$/, (p, _q, body) => {
    const draft = body as ScheduleDraft;
    return { gaps: gapsOf(Number(p[0]), draft.week_start, draft.shifts) };
  }],
  ['POST', /^\/stores\/(\d+)\/schedule\/publish\/$/, (p, _q, body) => {
    const draft = body as ScheduleDraft;
    saveSchedule(Number(p[0]), draft);
    const key = `${p[0]}:${draft.week_start}`;
    if (!db.published.includes(key)) db.published.push(key);
    return schedule(Number(p[0]), draft.week_start);
  }],
  ['POST', /^\/employees\/(\d+)\/invite\/$/, (p) => {
    const [, employee] = storeOfEmployee(Number(p[0]));
    employee.invite_code = inviteCode();
    employee.status = employee.status === 'connected' ? 'connected' : 'invited';
    return employee;
  }],
  ['POST', /^\/employees\/(\d+)\/dismiss\/$/, (p) => {
    const [, employee] = storeOfEmployee(Number(p[0]));
    employee.status = 'dismissed';
    employee.invite_code = null;
    return employee;
  }],
  ['DELETE', /^\/employees\/(\d+)\/$/, (p) => {
    const [item, employee] = storeOfEmployee(Number(p[0]));
    if (employee.status !== 'dismissed') {
      throw new ApiError(409, 'conflict', 'Сначала отметьте, что сотрудник уволен');
    }
    // На сервере запись с историей остаётся ради отметок, но из списка пропадает так же.
    item.employees = item.employees.filter((person) => person.id !== employee.id);
    return null;
  }],
  ['PATCH', /^\/task-templates\/(\d+)\/$/, (p, _q, body) => {
    const id = Number(p[0]);
    for (const list of Object.values(db.templates)) {
      const found = list.find((item) => item.id === id);
      if (found) return Object.assign(found, body);
    }
    throw new ApiError(404, 'not_found', 'Задача не найдена');
  }],
  ['DELETE', /^\/task-templates\/(\d+)\/$/, (p) => {
    const id = Number(p[0]);
    for (const [storeId, list] of Object.entries(db.templates)) {
      if (list.some((item) => item.id === id)) {
        db.templates[Number(storeId)] = list.filter((item) => item.id !== id);
        return null;
      }
    }
    throw new ApiError(404, 'not_found', 'Задача не найдена');
  }],
];

export async function mockRequest<T>(method: string, path: string, body?: unknown): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, 250));
  const [pathname, search = ''] = path.split('?');
  const query = new URLSearchParams(search);

  for (const [routeMethod, pattern, handler] of routes) {
    if (routeMethod !== method) continue;
    const match = pattern.exec(pathname);
    if (match) return structuredClone(handler(match.slice(1), query, body)) as T;
  }
  throw new ApiError(404, 'no_mock', `нет демо-данных для ${method} ${path}`);
}
