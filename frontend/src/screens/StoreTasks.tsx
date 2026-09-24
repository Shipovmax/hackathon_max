import { Button, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { TaskTemplateInput, TaskTemplateItem } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Empty } from '../components/Empty';
import { Screen } from '../components/Screen';
import { TaskEditor } from '../components/TaskEditor';
import { DEFAULT_LEAD_MINUTES, earlierBy, formatDate, today } from '../lib/format';

function describe(task: TaskTemplateItem): string {
  const when = task.kind === 'daily' ? `Ежедневно в ${task.planned_time}` : `${formatDate(task.on_date ?? '')} в ${task.planned_time}`;
  return [
    when,
    `отметить с ${task.available_from}`,
    `допуск +${task.tolerance_minutes} мин`,
    task.requires_claim && '«Беру»',
    task.requires_photo && 'фото',
  ]
    .filter(Boolean)
    .join(' · ');
}

const blank = (kind: TaskTemplateItem['kind']): TaskTemplateInput => {
  const planned = kind === 'daily' ? '09:00' : '14:00';
  return {
    title: '',
    kind,
    planned_time: planned,
    available_from: earlierBy(planned, DEFAULT_LEAD_MINUTES),
    on_date: kind === 'daily' ? null : today(),
    tolerance_minutes: 15,
    requires_photo: true,
    // «Беру» — осознанный выбор владельца, а не значение по умолчанию: задача
    // с ним требует, чтобы кто-то из смены её принял.
    requires_claim: false,
  };
};

export function StoreTasks() {
  const { storeId } = useParams();
  const state = useApi<TaskTemplateItem[]>(`/stores/${storeId}/task-templates/`);
  const [editing, setEditing] = useState<TaskTemplateItem | TaskTemplateInput | null>(null);

  const daily = (state.data ?? []).filter((task) => task.kind === 'daily');
  const once = (state.data ?? []).filter((task) => task.kind === 'one_time');

  return (
    <AsyncView state={state}>
      {() => (
        <Screen
          title="Задачи точки"
          back
          backTo={`/stores/${storeId}`}
        >
          {daily.length === 0 && once.length === 0 && (
            <div className="screen__block">
              <Empty
                icon="clock"
                title="Задач ещё нет"
                text="Начните с открытия, подготовки зала и закрытия смены — бот будет напоминать о них каждый день."
                action={{ label: 'Добавить задачу', onClick: () => setEditing(blank('daily')) }}
              />
            </div>
          )}

          {daily.length > 0 && (
          <CellList mode="island" header={<CellHeader>Каждый день</CellHeader>}>
            {daily.map((task) => (
              <CellSimple
                key={task.id}
                title={task.title}
                subtitle={describe(task)}
                showChevron
                onClick={() => setEditing(task)}
              />
            ))}
          </CellList>
          )}

          {once.length > 0 && (
          <CellList mode="island" header={<CellHeader>Разовые задачи</CellHeader>}>
            {once.map((task) => (
              <CellSimple
                key={task.id}
                title={task.title}
                subtitle={describe(task)}
                showChevron
                onClick={() => setEditing(task)}
              />
            ))}
          </CellList>
          )}

          <div className="screen__block">
            <Button stretched onClick={() => setEditing(blank('daily'))}>
              Добавить ежедневную задачу
            </Button>
            <Button variant="secondary" stretched onClick={() => setEditing(blank('one_time'))}>
              Добавить разовую задачу на дату
            </Button>
          </div>

          <TaskEditor
            storeId={Number(storeId)}
            task={editing}
            onClose={() => setEditing(null)}
            onDone={() => {
              setEditing(null);
              state.reload();
            }}
          />
        </Screen>
      )}
    </AsyncView>
  );
}
