const hour = (time: string) => String(Number(time.slice(0, 2)));
const pad = (n: number) => String(n).padStart(2, '0');

export const WEEKDAYS = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];

export function formatRange(start: string, end: string): string {
  if (start.endsWith(':00') && end.endsWith(':00')) return `${hour(start)}–${hour(end)}`;
  return `${start}–${end}`;
}

export function formatDate(iso: string): string {
  if (!iso) return '';
  return new Date(`${iso}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
}

export function formatShortDate(iso: string): string {
  if (!iso) return '';
  return new Date(`${iso}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

/** «пн, 22 сент» — как подписан день в графике и в списке окон. */
export function formatDayLabel(iso: string): string {
  return `${WEEKDAYS[weekdayIndex(iso)]}, ${formatShortDate(iso)}`;
}

export function toIso(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function today(): string {
  return toIso(new Date());
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return toIso(date);
}

/** 0 — понедельник, 6 — воскресенье. */
export function weekdayIndex(iso: string): number {
  return (new Date(`${iso}T00:00:00`).getDay() + 6) % 7;
}

/** Понедельник недели, в которую попадает дата. */
export function weekStart(iso: string): string {
  return addDays(iso, -weekdayIndex(iso));
}

export function isValidTime(value: string): boolean {
  if (!/^\d{1,2}:\d{2}$/.test(value)) return false;
  const [h, m] = value.split(':').map(Number);
  return h < 24 && m < 60;
}

export function minutesOf(time: string): number {
  const [h, m] = time.split(':').map(Number);
  return h * 60 + m;
}

/** «22–28 сент» — подпись недели в графике. */
export function formatWeekRange(week: string): string {
  const end = addDays(week, 6);
  const short = (iso: string, withMonth: boolean) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString('ru-RU', withMonth ? { day: 'numeric', month: 'short' } : { day: 'numeric' });
  const sameMonth = week.slice(0, 7) === end.slice(0, 7);
  return `${short(week, !sameMonth)}–${short(end, true)}`;
}

/** «1 точка», «2 точки», «5 точек». */
export function plural(count: number, forms: [string, string, string]): string {
  const n = Math.abs(count) % 100;
  const n1 = n % 10;
  if (n > 10 && n < 20) return forms[2];
  if (n1 > 1 && n1 < 5) return forms[1];
  if (n1 === 1) return forms[0];
  return forms[2];
}
