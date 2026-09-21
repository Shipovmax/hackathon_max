import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { apiDelete, apiPatch, apiPost } from '../api/client';
import { useAction, useApi } from '../api/hooks';
import type { TaskTemplateInput, TaskTemplateItem } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { ErrorNote } from '../components/ErrorNote';
import { SwitchField, TextField } from '../components/Field';
import { Screen } from '../components/Screen';
import { Sheet } from '../components/Sheet';
import { useToast } from '../components/Toast';
import { formatDate, isValidTime, normalizeTime, today } from '../lib/format';

function describe(task: TaskTemplateItem): string {
  const when = task.kind === 'daily' ? `Ежедневно в ${task.planned_time}` : `${formatDate(task.on_date ?? '')} в ${task.planned_time}`;
  return [when, `допуск +${task.tolerance_minutes} мин`, task.requires_claim && '«Беру»', task.requires_photo && 'фото']
    .filter(Boolean)
    .join(' · ');
}

const blank = (kind: TaskTemplateItem['kind']): TaskTemplateInput => ({
  title: '',
  kind,
  planned_time: kind === 'daily' ? '09:00' : '14:00',
  on_date: kind === 'daily' ? null : today(),
  tolerance_minutes: 15,
  requires_photo: true,
  requires_claim: kind === 'one_time',
});

export function StoreTasks() {
  const { storeId } = useParams();
  const state = useApi<TaskTemplateItem[]>(`/stores/${storeId}/task-templates/`);
  const [editing, setEditing] = useState<TaskTemplateItem | TaskTemplateInput | null>(null);

  const daily = (state.data ?? []).filter((task) => task.kind === 'daily');
  const once = (state.data ?? []).filter((task) => task.kind === 'one_time');

  return (
    <AsyncView state={state}>
      {() => (
        <Screen title="Задачи точки" subtitle="Из них бот составляет список дня" back>
          <CellList mode="island" header={<CellHeader>Каждый день</CellHeader>}>
            {daily.length === 0 && <CellSimple title="Ежедневных задач нет" />}
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

          <CellList mode="island" header={<CellHeader>Разовые задачи</CellHeader>}>
            {once.length === 0 && <CellSimple title="Разовых задач нет" />}
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

          <div className="screen__block">
            <Button stretched onClick={() => setEditing(blank('daily'))}>
              Добавить ежедневную задачу
            </Button>
            <Button variant="secondary" stretched onClick={() => setEditing(blank('one_time'))}>
              Добавить разовую задачу на дату
            </Button>
            <Typography.Label variant="small">
              Разовая задача нужна, когда поставщик назвал дату приёмки.
            </Typography.Label>
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

interface TaskEditorProps {
  storeId: number;
  task: TaskTemplateItem | TaskTemplateInput | null;
  onClose: () => void;
  onDone: () => void;
}

function TaskEditor({ storeId, task, onClose, onDone }: TaskEditorProps) {
  const toast = useToast();
  const save = useAction();
  const remove = useAction();
  const [form, setForm] = useState<TaskTemplateInput | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!task) return;
    const { title, kind, planned_time, on_date, tolerance_minutes, requires_photo, requires_claim } = task;
    setForm({ title, kind, planned_time, on_date, tolerance_minutes, requires_photo, requires_claim });
    setProblem(null);
    setConfirmDelete(false);
  }, [task]);

  if (!task || !form) return null;
  const existing = 'id' in task ? task : null;
  const patch = (fields: Partial<TaskTemplateInput>) => setForm({ ...form, ...fields });

  const submit = async () => {
    if (form.title.trim().length < 2) {
      setProblem('Введите название задачи');
      return;
    }
    if (!isValidTime(form.planned_time)) {
      setProblem('Плановое время в формате ЧЧ:ММ, например 09:00');
      return;
    }
    if (form.kind === 'one_time' && !form.on_date) {
      setProblem('Укажите дату разовой задачи');
      return;
    }
    const body = { ...form, title: form.title.trim() };
    const result = await save.run(() =>
      existing
        ? apiPatch<TaskTemplateItem>(`/task-templates/${existing.id}/`, body)
        : apiPost<TaskTemplateItem>(`/stores/${storeId}/task-templates/`, body),
    );
    if (!result) return;
    toast.show(existing ? 'Задача изменена' : 'Задача добавлена');
    onDone();
  };

  const submitDelete = async () => {
    if (!existing) return;
    const result = await remove.run(() => apiDelete(`/task-templates/${existing.id}/`));
    if (result === undefined) return;
    toast.show('Задача удалена');
    onDone();
  };

  return (
    <Sheet title={existing ? 'Задача точки' : form.kind === 'daily' ? 'Новая ежедневная задача' : 'Новая разовая задача'} open onClose={onClose}>
      <TextField label="Название" value={form.title} onChange={(title) => patch({ title })} placeholder="Открытие магазина" />
      <TextField
        label="Плановое время"
        value={form.planned_time}
        onChange={(value) => patch({ planned_time: normalizeTime(value) })}
        inputMode="numeric"
        placeholder="09:00"
      />
      {form.kind === 'one_time' && (
        <label className="field">
          <Typography.Label variant="small">Дата</Typography.Label>
          <input
            className="field__date"
            type="date"
            value={form.on_date ?? ''}
            onChange={(event) => patch({ on_date: event.target.value })}
          />
        </label>
      )}
      <TextField
        label="Допустимая задержка, мин"
        value={String(form.tolerance_minutes)}
        onChange={(value) => patch({ tolerance_minutes: Number(value.replace(/\D/g, '')) || 0 })}
        inputMode="numeric"
        hint="После этого времени задача считается просроченной и владелец получает уведомление"
      />
      <SwitchField
        label="Нужно фото"
        checked={form.requires_photo}
        onChange={(requires_photo) => patch({ requires_photo })}
      />
      <SwitchField
        label="Требуется «Беру»"
        hint="Бот спросит смену, кто принимает, и закрепит задачу за первым откликнувшимся"
        checked={form.requires_claim}
        onChange={(requires_claim) => patch({ requires_claim })}
      />

      {problem && <div className="alert alert--bad">{problem}</div>}
      <ErrorNote error={save.error ?? remove.error} />

      <Button stretched loading={save.running} onClick={submit}>
        {existing ? 'Сохранить' : 'Добавить'}
      </Button>
      {existing &&
        (confirmDelete ? (
          <Button variant="destructive" stretched loading={remove.running} onClick={submitDelete}>
            Точно удалить задачу
          </Button>
        ) : (
          <Button variant="secondary" stretched onClick={() => setConfirmDelete(true)}>
            Удалить задачу
          </Button>
        ))}
    </Sheet>
  );
}
