import { CellList, CellSimple } from '@maxhub/max-ui';
import { useParams } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { TaskTemplateItem } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';
import { formatDate } from '../lib/format';

function describe(task: TaskTemplateItem): string {
  const when = task.kind === 'daily' ? `Ежедневно ${task.planned_time}` : `${formatDate(task.on_date ?? '')} ${task.planned_time}`;
  return [when, `+${task.tolerance_minutes} мин`, task.requires_claim && '«Беру»', task.requires_photo && 'фото']
    .filter(Boolean)
    .join(' · ');
}

export function StoreTasks() {
  const { storeId } = useParams();
  const state = useApi<TaskTemplateItem[]>(`/stores/${storeId}/task-templates/`);

  return (
    <AsyncView state={state}>
      {(tasks) => (
        <Screen title="Задачи точки" back>
          <CellList mode="island">
            {tasks.map((task) => (
              <CellSimple key={task.id} title={task.title} subtitle={describe(task)} />
            ))}
          </CellList>
        </Screen>
      )}
    </AsyncView>
  );
}
