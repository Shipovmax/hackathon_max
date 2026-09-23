import { CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { Fragment, useCallback, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { apiGet } from '../api/client';
import { useApi } from '../api/hooks';
import type { DayTask, StoreDay as StoreDayData, TaskTemplateItem } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Empty } from '../components/Empty';
import { DateNav } from '../components/DateNav';
import { Icon } from '../components/Icon';
import { PhotoView } from '../components/PhotoView';
import { Screen } from '../components/Screen';
import { useToast } from '../components/Toast';
import { StatusDot, TaskStatusBadge, taskTone } from '../components/StatusBadge';
import { TaskEditor } from '../components/TaskEditor';
import { formatRange, minutesOf, today } from '../lib/format';

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
  const [editing, setEditing] = useState<TaskTemplateItem | null>(null);
  const [opening, setOpening] = useState(false);
  const toast = useToast();
  const state = useApi<StoreDayData>(`/stores/${storeId}/day/?date=${date}`);

  /**
   * Правка задачи прямо из списка дня.
   *
   * В списке лежит задача на дату, а править надо шаблон точки, поэтому берём его
   * с сервера по `template_id`. Отдельного эндпоинта для одного шаблона нет,
   * а список задач точки короткий, так что читаем его целиком.
   */
  const openTask = async (task: DayTask) => {
    if (opening) return;
    setOpening(true);
    try {
      const templates = await apiGet<TaskTemplateItem[]>(`/stores/${storeId}/task-templates/`);
      const template = templates.find((item) => item.id === task.template_id);
      if (template) setEditing(template);
      else toast.show('Задача больше не настроена на точке', 'bad');
    } catch {
      toast.show('Не удалось открыть задачу, попробуйте ещё раз', 'bad');
    } finally {
      setOpening(false);
    }
  };

  // Черта «сейчас» показывает, что уже должно было произойти, а что впереди.
  const nowMinutes = new Date().getHours() * 60 + new Date().getMinutes();

  return (
    <AsyncView state={state}>
      {(data) => {
        const upcoming = data.tasks.findIndex((task) => minutesOf(task.planned_time) > nowMinutes);
        // Все задачи дня позади — черта уходит под список.
        const nowIndex = date !== today() ? -1 : upcoming === -1 ? data.tasks.length : upcoming;
        return (
        <Screen
          title={data.store.name}
          subtitle={date === today() ? 'Сегодня' : undefined}
          back
          backTo="/"
        >
          <div className="screen__block">
            {/* Вперёд листать можно: задачи будущих дней строятся по шаблонам точки. */}
            <DateNav date={date} onChange={setDate} maxDate={null} />
          </div>

          <div className="screen__block">
            <Typography.Label variant="small" className="muted">
              {data.on_shift.length ? 'На смене' : 'Никого на смене'}
            </Typography.Label>
            {data.on_shift.length > 0 && (
              <ul className="onshift">
                {data.on_shift.map((person) => (
                  <li key={`${person.name}-${person.start}`} className="onshift__item">
                    <span className="onshift__name">{person.name}</span>
                    <span className="onshift__time">{formatRange(person.start, person.end)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="screen__block" aria-live="polite">
            {state.loading && (
              <Typography.Label variant="small" className="muted">
                Обновляем…
              </Typography.Label>
            )}
          </div>

          {data.tasks.length === 0 ? (
            <div className="screen__block">
              <Empty
                icon="clock"
                title={data.closed ? 'Выходной: точка закрыта' : 'Задач на этот день нет'}
                text={
                  data.closed
                    ? 'Ежедневные задачи в выходной не ставятся. Выходные меняются в «Точки и сотрудники».'
                    : 'Задачи точки задаются шаблонами: ежедневные повторяются, разовая ставится на дату.'
                }
                action={{ label: 'Задачи точки', onClick: () => navigate(`/stores/${data.store.id}/tasks`) }}
              />
            </div>
          ) : (
            <CellList mode="island" className="timeline__list">
              {data.tasks.map((task, index) => (
                <Fragment key={task.id}>
                  {nowIndex === index && <NowMarker />}
                  <CellSimple
                    title={task.title}
                    subtitle={subtitle(task)}
                    after={<TaskStatusBadge status={task.status} lateMinutes={task.late_minutes} />}
                    before={
                      <span className="timeline">
                        <span className="timeline__time">{task.planned_time}</span>
                        <StatusDot tone={taskTone(task.status)} />
                      </span>
                    }
                    showChevron
                    onClick={() => openTask(task)}
                  />
                  {task.photo_url && (
                    <CellSimple
                      height="compact"
                      before={<Icon name="camera" />}
                      title="Посмотреть фото"
                      onClick={() => setPhoto(task)}
                    />
                  )}
                </Fragment>
              ))}
              {nowIndex === data.tasks.length && <NowMarker />}
            </CellList>
          )}

          <CellList mode="island">
            <CellSimple title="График смен" showChevron onClick={() => navigate(`/stores/${data.store.id}/schedule`)} />
            <CellSimple title="Задачи точки" showChevron onClick={() => navigate(`/stores/${data.store.id}/tasks`)} />
          </CellList>

          <TaskEditor
            storeId={Number(storeId)}
            task={editing}
            onClose={() => setEditing(null)}
            onDone={() => {
              setEditing(null);
              state.reload();
            }}
          />

          <PhotoView
            url={photo?.photo_url ?? null}
            title={photo ? `${photo.title} · ${photo.done_by ?? ''} ${photo.done_at ?? ''}`.trim() : ''}
            onClose={() => setPhoto(null)}
          />
        </Screen>
        );
      }}
    </AsyncView>
  );
}

function NowMarker() {
  const now = new Date();
  const label = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  return (
    <div className="nowline">
      <span className="nowline__time">{label}</span>
      <span className="nowline__rule" />
      <span className="nowline__label">сейчас</span>
    </div>
  );
}
