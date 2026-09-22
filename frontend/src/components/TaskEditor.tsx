import { Button, Typography } from '@maxhub/max-ui';
import { useEffect, useState } from 'react';

import { apiDelete, apiPatch, apiPost } from '../api/client';
import { useAction } from '../api/hooks';
import type { TaskTemplateInput, TaskTemplateItem } from '../api/types';
import { DEFAULT_LEAD_MINUTES, earlierBy, isValidTime, minutesOf } from '../lib/format';
import { DateField, SwitchField, TextField } from './Field';
import { ErrorNote } from './ErrorNote';
import { Sheet } from './Sheet';
import { TimeField } from './TimeField';
import { useToast } from './Toast';

/**
 * Форма задачи точки. Живёт отдельно от экрана «Задачи точки», потому что ту же задачу
 * правят из карточки точки, прямо из списка дня.
 */
interface TaskEditorProps {
  storeId: number;
  task: TaskTemplateItem | TaskTemplateInput | null;
  onClose: () => void;
  onDone: () => void;
}

export function TaskEditor({ storeId, task, onClose, onDone }: TaskEditorProps) {
  const toast = useToast();
  const save = useAction();
  const remove = useAction();
  const [form, setForm] = useState<TaskTemplateInput | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!task) return;
    const { title, kind, planned_time, available_from, on_date, tolerance_minutes, requires_photo, requires_claim } = task;
    setForm({ title, kind, planned_time, available_from, on_date, tolerance_minutes, requires_photo, requires_claim });
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
    if (!isValidTime(form.available_from)) {
      setProblem('Время начала в формате ЧЧ:ММ, например 08:30');
      return;
    }
    if (minutesOf(form.available_from) > minutesOf(form.planned_time)) {
      setProblem('Отмечать можно начиная не позже планового времени');
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
      <TimeField
        label="Плановое время"
        value={form.planned_time}
        onChange={(planned_time) =>
          patch({
            planned_time,
            // Окно едет за плановым временем, пока владелец не задал своё.
            available_from: form.available_from === earlierBy(form.planned_time, DEFAULT_LEAD_MINUTES)
              ? earlierBy(planned_time, DEFAULT_LEAD_MINUTES)
              : form.available_from,
          })
        }
      />
      <TimeField
        label="Отмечать можно с"
        value={form.available_from}
        onChange={(available_from) => patch({ available_from })}
        hint="Раньше этого времени кнопки у задачи не будет: закрытие смены не закрыть в обед"
      />
      {form.kind === 'one_time' && (
        <div className="field">
          <Typography.Label variant="small">Дата</Typography.Label>
          <DateField value={form.on_date ?? ''} onChange={(on_date) => patch({ on_date })} />
        </div>
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
