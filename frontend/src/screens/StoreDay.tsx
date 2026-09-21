import { CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useCallback, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { DayTask, StoreDay as StoreDayData } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { DateNav } from '../components/DateNav';
import { PhotoView } from '../components/PhotoView';
import { Screen } from '../components/Screen';
import { TaskStatusBadge } from '../components/StatusBadge';
import { formatRange, today } from '../lib/format';

// Плановое время стоит слева, поэтому в подписи только то, что произошло.
function subtitle(task: DayTask): string {
  if (task.done_by && task.done_at) {
    const late = task.late_minutes ? `, с опозданием на ${task.late_minutes} мин` : '';
    return `Отметил ${task.done_by} в ${task.done_at}${late}`;
  }
  if (task.claimed_by) return `Принимает ${task.claimed_by}`;
  if (task.status === 'unclaimed') return 'Задачу никто не взял';
  if (task.status === 'awaiting_photo') return 'Ждём фото от сотрудника';
  if (task.status === 'overdue' || task.status === 'missed') return 'Срок прошёл, отметки нет';
  return 'Ожидается';
}

export function StoreDay() {
  const { storeId } = useParams();
  const navigate = useNavigate();
  // Дата живёт в адресе: диплинк из уведомления открывает нужный день сразу.
  const [params, setParams] = useSearchParams();
  const date = params.get('date') ?? today();
  const setDate = useCallback(
    (next: string) => setParams(next === today() ? {} : { date: next }, { replace: true }),
    [setParams],
  );
  const [photo, setPhoto] = useState<DayTask | null>(null);
  const state = useApi<StoreDayData>(`/stores/${storeId}/day/?date=${date}`);

  return (
    <AsyncView state={state}>
      {(data) => (
        <Screen
          title={data.store.name}
          subtitle={
            data.on_shift.length
              ? `На смене: ${data.on_shift.map((s) => `${s.name} ${formatRange(s.start, s.end)}`).join(', ')}`
              : 'Никого на смене'
          }
          back
        >
          <div className="screen__block">
            <DateNav date={date} onChange={setDate} />
          </div>

          {state.loading ? (
            <div className="screen__block">
              <Typography.Label variant="small">Обновляем…</Typography.Label>
            </div>
          ) : null}

          <CellList mode="island">
            {data.tasks.length === 0 && <CellSimple title="Задач на этот день нет" />}
            {data.tasks.map((task) => (
              <CellSimple
                key={task.id}
                title={task.title}
                subtitle={subtitle(task)}
                after={<TaskStatusBadge status={task.status} lateMinutes={task.late_minutes} />}
                before={<span className="timeline">{task.planned_time}</span>}
                showChevron={Boolean(task.photo_url)}
                onClick={task.photo_url ? () => setPhoto(task) : undefined}
              />
            ))}
          </CellList>

          <CellList mode="island">
            <CellSimple title="График смен" showChevron onClick={() => navigate(`/stores/${data.store.id}/schedule`)} />
            <CellSimple title="Задачи точки" showChevron onClick={() => navigate(`/stores/${data.store.id}/tasks`)} />
          </CellList>

          <PhotoView
            url={photo?.photo_url ?? null}
            title={photo ? `${photo.title} · ${photo.done_by ?? ''} ${photo.done_at ?? ''}`.trim() : ''}
            onClose={() => setPhoto(null)}
          />
        </Screen>
      )}
    </AsyncView>
  );
}
