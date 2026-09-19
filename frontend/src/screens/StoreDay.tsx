import { CellList, CellSimple } from '@maxhub/max-ui';
import { useNavigate, useParams } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { StoreDay as StoreDayData } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';
import { TaskStatusBadge } from '../components/StatusBadge';
import { formatRange } from '../lib/format';

export function StoreDay() {
  const { storeId } = useParams();
  const navigate = useNavigate();
  const state = useApi<StoreDayData>(`/stores/${storeId}/day/`);

  return (
    <AsyncView state={state}>
      {(data) => (
        <Screen
          title={data.store.name}
          subtitle={
            data.on_shift.length
              ? `На смене: ${data.on_shift.map((s) => `${s.name} ${formatRange(s.start, s.end)}`).join(', ')}`
              : 'Сегодня никого на смене'
          }
          back
        >
          <CellList mode="island">
            {data.tasks.map((task) => (
              <CellSimple
                key={task.id}
                title={task.title}
                subtitle={
                  task.done_by
                    ? `${task.done_by}, ${task.done_at}`
                    : task.claimed_by
                      ? `${task.planned_time} · берёт ${task.claimed_by}`
                      : task.planned_time
                }
                after={<TaskStatusBadge status={task.status} lateMinutes={task.late_minutes} />}
              />
            ))}
          </CellList>
          <CellList mode="island">
            <CellSimple title="График смен" showChevron onClick={() => navigate(`/stores/${data.store.id}/schedule`)} />
            <CellSimple title="Задачи точки" showChevron onClick={() => navigate(`/stores/${data.store.id}/tasks`)} />
          </CellList>
        </Screen>
      )}
    </AsyncView>
  );
}
