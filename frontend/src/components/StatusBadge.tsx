import type { StoreHealth, TaskStatus } from '../api/types';

type Tone = 'ok' | 'warn' | 'bad' | 'idle';

const TASK: Record<TaskStatus, [string, Tone]> = {
  scheduled: ['', 'idle'],
  reminded: ['ожидается', 'idle'],
  awaiting_photo: ['ждём фото', 'warn'],
  done_on_time: ['вовремя', 'ok'],
  done_late: ['с опозданием', 'warn'],
  overdue: ['просрочка', 'bad'],
  unclaimed: ['не взята', 'bad'],
  missed: ['не выполнена', 'bad'],
};

const HEALTH: Record<StoreHealth, [string, Tone]> = {
  ok: ['в порядке', 'ok'],
  late: ['с опозданием', 'warn'],
  overdue: ['просрочка', 'bad'],
  unclaimed: ['не взята', 'bad'],
};

export const healthTone = (health: StoreHealth): Tone => HEALTH[health][1];
export const taskTone = (status: TaskStatus): Tone => TASK[status][1];

function Badge({ label, tone }: { label: string; tone: Tone }) {
  if (!label) return null;
  return <span className={`badge badge--${tone}`}>{label}</span>;
}

export function TaskStatusBadge({ status, lateMinutes }: { status: TaskStatus; lateMinutes?: number | null }) {
  const [label, tone] = TASK[status];
  const text = status === 'done_late' && lateMinutes ? `+${lateMinutes} мин` : label;
  return <Badge label={text} tone={tone} />;
}

export function HealthBadge({ health }: { health: StoreHealth }) {
  const [label, tone] = HEALTH[health];
  return <Badge label={label} tone={tone} />;
}

/** Точка статуса слева от строки: цвет видно раньше, чем прочитан текст. */
export function StatusDot({ tone }: { tone: Tone }) {
  return <span className={`dot dot--${tone}`} aria-hidden="true" />;
}

/** Полоса «сколько задач закрыто» — счётчик читается за один взгляд. */
export function Progress({ done, total, tone }: { done: number; total: number; tone: Tone }) {
  const percent = total === 0 ? 0 : Math.round((done / total) * 100);
  return (
    <span className="progress" role="img" aria-label={`Выполнено ${done} из ${total}`}>
      <span className={`progress__fill progress__fill--${tone}`} style={{ width: `${percent}%` }} />
    </span>
  );
}
