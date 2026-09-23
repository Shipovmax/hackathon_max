// Проверка покрытия: сливаем интервалы смен и сравниваем с рабочим днём точки.
// Тот же расчёт делает бэкенд; здесь он нужен для режима демо-данных и для мгновенной
// проверки черновика до отправки.
import type { Gap, ShiftInput } from '../api/types';
import { minutesOf } from './format';

/** Допуск на границах: смена до 21:55 при закрытии в 22:00 — это покрытие, а не окно. */
export const EDGE_TOLERANCE_MINUTES = 5;

interface Interval {
  start: number;
  end: number;
}

function merge(intervals: Interval[]): Interval[] {
  const sorted = [...intervals].sort((a, b) => a.start - b.start);
  const merged: Interval[] = [];
  for (const interval of sorted) {
    const last = merged[merged.length - 1];
    if (last && interval.start <= last.end + EDGE_TOLERANCE_MINUTES) {
      last.end = Math.max(last.end, interval.end);
    } else {
      merged.push({ ...interval });
    }
  }
  return merged;
}

const label = (minutes: number) =>
  `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`;

function gapsOfDay(date: string, shifts: ShiftInput[], open: number, close: number): Gap[] {
  const covered = merge(shifts.map((shift) => ({ start: minutesOf(shift.start), end: minutesOf(shift.end) })));
  const gaps: Gap[] = [];
  let cursor = open;

  for (const interval of covered) {
    if (interval.end <= cursor) continue;
    if (interval.start > cursor + EDGE_TOLERANCE_MINUTES) {
      gaps.push({ date, start: label(cursor), end: label(Math.min(interval.start, close)) });
    }
    cursor = Math.max(cursor, interval.end);
    if (cursor >= close) break;
  }
  if (cursor < close - EDGE_TOLERANCE_MINUTES) {
    gaps.push({ date, start: label(cursor), end: label(close) });
  }
  return gaps;
}

/**
 * Окна за неделю: дни идут по порядку, внутри дня — по времени. Выходные точки
 * пропускаем: пустой день, когда магазин закрыт, — не окно.
 */
export function findGaps(
  dates: string[],
  shifts: ShiftInput[],
  openTime: string,
  closeTime: string,
  closedDates: string[] = [],
): Gap[] {
  const open = minutesOf(openTime);
  const close = minutesOf(closeTime);
  return dates.filter((date) => !closedDates.includes(date)).flatMap((date) =>
    gapsOfDay(
      date,
      shifts.filter((shift) => shift.date === date),
      open,
      close,
    ),
  );
}
