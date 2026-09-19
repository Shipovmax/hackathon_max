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
  overdue: ['просрочка', 'bad'],
  unclaimed: ['не взята', 'bad'],
};

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
