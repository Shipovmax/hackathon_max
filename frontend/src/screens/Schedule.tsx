import { Button, IconButton, Typography } from '@maxhub/max-ui';
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { apiPost, apiPut } from '../api/client';
import { useAction, useApi } from '../api/hooks';
import type { Coverage, Gap, Schedule as ScheduleData, ShiftInput } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Empty } from '../components/Empty';
import { Icon } from '../components/Icon';
import { ErrorNote } from '../components/ErrorNote';
import { Screen } from '../components/Screen';
import { Sheet } from '../components/Sheet';
import { TimeField } from '../components/TimeField';
import { useToast } from '../components/Toast';
import { findGaps } from '../lib/coverage';
import {
  addDays,
  formatDayLabel,
  formatRange,
  formatWeekRange,
  isValidTime,
  minutesOf,
  today,
  WEEKDAYS,
  weekStart,
} from '../lib/format';

/** Сегодняшний столбец подсвечен, выходные приглушены — неделя читается сразу. */
function cellClass(date: string, weekend: boolean): string {
  return [date === today() && 'schedule__col--today', weekend && 'schedule__col--weekend']
    .filter(Boolean)
    .join(' ');
}

interface EditorState {
  employeeId: number;
  employeeName: string;
  date: string;
  start: string;
  end: string;
  existing: boolean;
}

export function Schedule() {
  const { storeId } = useParams();
  // Открываем текущую неделю: чаще смотрят на то, что идёт сейчас, а следующая
  // в одном нажатии стрелкой вперёд.
  const [week, setWeek] = useState(() => weekStart(today()));
  const state = useApi<ScheduleData>(`/stores/${storeId}/schedule/?week=${week}`);

  return (
    <AsyncView state={state}>
      {(data) => (
        <ScheduleWeek
          key={data.week_start}
          storeId={Number(storeId)}
          data={data}
          week={week}
          loading={state.loading}
          onWeek={setWeek}
          onSaved={state.setData}
        />
      )}
    </AsyncView>
  );
}

interface ScheduleWeekProps {
  storeId: number;
  data: ScheduleData;
  week: string;
  loading: boolean;
  onWeek: (week: string) => void;
  onSaved: (data: ScheduleData) => void;
}

function ScheduleWeek({ storeId, data, week, loading, onWeek, onSaved }: ScheduleWeekProps) {
  const toast = useToast();
  const save = useAction();
  const check = useAction();
  const [shifts, setShifts] = useState<ShiftInput[]>(data.shifts);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [serverGaps, setServerGaps] = useState<Gap[] | null>(data.gaps);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    setShifts(data.shifts);
    setServerGaps(data.gaps);
    setDirty(false);
  }, [data]);

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const days = useMemo(
    () =>
      WEEKDAYS.map((label, index) => ({
        label,
        date: addDays(data.week_start, index),
        weekend: index >= 5,
      })),
    [data.week_start],
  );

  // Пересчитываем окна сразу после правки — в том числе в уже опубликованной неделе.
  const gaps = useMemo(
    () => (dirty ? findGaps(days.map((day) => day.date), shifts, data.open_time, data.close_time) : (serverGaps ?? [])),
    [dirty, days, shifts, data.open_time, data.close_time, serverGaps],
  );

  const draft = { week_start: data.week_start, shifts };

  const openEditor = (employeeId: number, employeeName: string, date: string) => {
    const shift = shifts.find((item) => item.employee_id === employeeId && item.date === date);
    setEditor({
      employeeId,
      employeeName,
      date,
      start: shift?.start ?? data.open_time,
      end: shift?.end ?? data.close_time,
      existing: Boolean(shift),
    });
  };

  const applyEditor = (next: EditorState) => {
    setShifts((current) => [
      ...current.filter((item) => !(item.employee_id === next.employeeId && item.date === next.date)),
      { employee_id: next.employeeId, date: next.date, start: next.start, end: next.end },
    ]);
    setDirty(true);
    setEditor(null);
  };

  const clearEditor = (next: EditorState) => {
    setShifts((current) =>
      current.filter((item) => !(item.employee_id === next.employeeId && item.date === next.date)),
    );
    setDirty(true);
    setEditor(null);
  };

  const runCheck = async () => {
    const result = await check.run(() => apiPost<Coverage>(`/stores/${storeId}/schedule/coverage/`, draft));
    if (!result) return;
    setServerGaps(result.gaps);
    toast.show(result.gaps.length === 0 ? 'Окон нет, неделя закрыта' : `Найдено окон: ${result.gaps.length}`, result.gaps.length === 0 ? 'ok' : 'bad');
  };

  const runSave = async (publish: boolean) => {
    const path = publish ? `/stores/${storeId}/schedule/publish/` : `/stores/${storeId}/schedule/`;
    const result = await save.run(() =>
      publish ? apiPost<ScheduleData>(path, draft) : apiPut<ScheduleData>(path, draft),
    );
    if (!result) return;
    onSaved(result);
    toast.show(publish ? 'График опубликован' : 'Изменения сохранены');
  };

  return (
    <Screen
      title="График смен"
      subtitle={`${formatWeekRange(data.week_start)} · ${data.status === 'draft' ? 'черновик' : 'опубликован'}`}
      back
      backTo={`/stores/${storeId}`}
      leaveWarning={dirty ? 'Изменения графика не сохранены. Уйти с экрана?' : undefined}
    >
      <div className="screen__block">
        <div className="datenav">
          <IconButton
            size="small"
            variant="secondary"
            aria-label="Предыдущая неделя"
            disabled={dirty}
            onClick={() => onWeek(addDays(week, -7))}
          >
            <Icon name="back" />
          </IconButton>
          <Typography.Body variant="medium-strong">{formatWeekRange(data.week_start)}</Typography.Body>
          <IconButton
            size="small"
            variant="secondary"
            aria-label="Следующая неделя"
            disabled={dirty}
            onClick={() => onWeek(addDays(week, 7))}
          >
            <Icon name="forward" />
          </IconButton>
        </div>

        <Typography.Label variant="small">
          Рабочий день {formatRange(data.open_time, data.close_time)}. Нажмите на ячейку, чтобы задать смену. Пустая
          ячейка — выходной.
        </Typography.Label>

        {data.employees.length === 0 ? (
          <Empty
            icon="people"
            title="На точке нет сотрудников"
            text="Пока некому ставить смены. Добавьте людей на экране «Точки и сотрудники»."
          />
        ) : (
          <>
            <Typography.Label variant="small" className="schedule__hint">
              Таблица прокручивается по горизонтали. Имена сотрудников остаются слева.
            </Typography.Label>
            <div className="schedule__scroll" tabIndex={0} aria-label="График смен, прокручиваемая таблица">
              <table className="schedule">
                <caption className="visually-hidden">Смены сотрудников по дням недели</caption>
                <thead>
                  <tr>
                    <th className="schedule__corner" scope="col">
                      Сотрудник
                    </th>
                    {days.map((day) => (
                      <th key={day.date} className={cellClass(day.date, day.weekend)}>
                        <span className="schedule__day">{day.label}</span>
                        <span className="schedule__date">{Number(day.date.slice(8))}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.employees.map((employee) => (
                    <tr key={employee.id}>
                      <th className="schedule__name" scope="row">
                        <Typography.Body variant="small-strong">{employee.name}</Typography.Body>
                      </th>
                      {days.map((day) => {
                        const shift = shifts.find(
                          (item) => item.employee_id === employee.id && item.date === day.date,
                        );
                        return (
                          <td key={day.date} className={cellClass(day.date, day.weekend)}>
                            <button
                              type="button"
                              className={`schedule__cell${shift ? ' schedule__cell--filled' : ''}`}
                              aria-label={`${employee.name}, ${formatDayLabel(day.date)}: ${shift ? formatRange(shift.start, shift.end) : 'выходной'}`}
                              onClick={() => openEditor(employee.id, employee.name, day.date)}
                            >
                              {shift ? formatRange(shift.start, shift.end) : '—'}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {data.employees.length > 0 && (
          <CoverageStrip days={days} gaps={gaps} openTime={data.open_time} closeTime={data.close_time} />
        )}

        {gaps.length > 0 ? (
          <div className="alert alert--bad">
            <Typography.Body variant="medium-strong">Найдено окон: {gaps.length}</Typography.Body>
            {gaps.map((gap) => (
              <Typography.Body variant="small" key={`${gap.date}-${gap.start}`}>
                {formatDayLabel(gap.date)}, {gap.start}–{gap.end} — никого
              </Typography.Body>
            ))}
          </div>
        ) : (
          <div className="alert alert--ok">
            <Typography.Body variant="medium">Рабочий день закрыт целиком, окон нет</Typography.Body>
          </div>
        )}

        {dirty && (
          <div className="alert">
            <Typography.Body variant="medium">
              Правки пока только на экране. {data.status === 'draft' ? 'Сохраните черновик или опубликуйте график' : 'Сохраните их'}, чтобы
              изменения не потерялись.
            </Typography.Body>
          </div>
        )}

        <ErrorNote error={check.error ?? save.error} />

        <Button variant="secondary" stretched loading={check.running} onClick={runCheck}>
          Проверить покрытие
        </Button>
        {data.status === 'draft' ? (
          <>
            <Button
              variant="secondary"
              stretched
              loading={save.running}
              disabled={!dirty}
              onClick={() => runSave(false)}
            >
              Сохранить черновик
            </Button>
            <Button
              stretched
              loading={save.running}
              disabled={data.employees.length === 0 || gaps.length > 0}
              onClick={() => runSave(true)}
            >
              Опубликовать
            </Button>
            {gaps.length > 0 && (
              <Typography.Label variant="small" className="muted">
                Перед публикацией закройте все окна в графике.
              </Typography.Label>
            )}
          </>
        ) : (
          <Button stretched loading={save.running} disabled={!dirty} onClick={() => runSave(false)}>
            Сохранить изменения
          </Button>
        )}
        {dirty && (
          <Button
            variant="ghost"
            stretched
            onClick={() => {
              setShifts(data.shifts);
              setServerGaps(data.gaps);
              setDirty(false);
            }}
          >
            Отменить правки
          </Button>
        )}
        {loading && <Typography.Label variant="small">Обновляем…</Typography.Label>}
      </div>

      <ShiftEditor state={editor} onClose={() => setEditor(null)} onApply={applyEditor} onClear={clearEditor} />
    </Screen>
  );
}

interface CoverageStripProps {
  days: { label: string; date: string }[];
  gaps: Gap[];
  openTime: string;
  closeTime: string;
}

/**
 * Полоса покрытия: каждый день рабочего дня показан целиком, красные куски —
 * это часы, на которые никто не поставлен. Список окон словами остаётся ниже,
 * но дыру в неделе видно раньше, чем её читают.
 */
function CoverageStrip({ days, gaps, openTime, closeTime }: CoverageStripProps) {
  const open = minutesOf(openTime);
  const span = minutesOf(closeTime) - open;

  return (
    <div className="coverage">
      {days.map((day) => (
        <div className="coverage__day" key={day.date}>
          <span className="coverage__label">{day.label}</span>
          <span className="coverage__bar">
            {gaps
              .filter((gap) => gap.date === day.date)
              .map((gap) => (
                <span
                  key={gap.start}
                  className="coverage__gap"
                  style={{
                    left: `${((minutesOf(gap.start) - open) / span) * 100}%`,
                    width: `${((minutesOf(gap.end) - minutesOf(gap.start)) / span) * 100}%`,
                  }}
                />
              ))}
          </span>
        </div>
      ))}
    </div>
  );
}

interface ShiftEditorProps {
  state: EditorState | null;
  onClose: () => void;
  onApply: (state: EditorState) => void;
  onClear: (state: EditorState) => void;
}

function ShiftEditor({ state, onClose, onApply, onClear }: ShiftEditorProps) {
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (!state) return;
    setStart(state.start);
    setEnd(state.end);
    setProblem(null);
  }, [state]);

  if (!state) return null;

  const changeStart = (value: string) => {
    setStart(value);
    setProblem(null);
  };
  const changeEnd = (value: string) => {
    setEnd(value);
    setProblem(null);
  };

  const submit = () => {
    if (!isValidTime(start) || !isValidTime(end)) {
      setProblem('Время в формате ЧЧ:ММ, например 09:00');
      return;
    }
    if (minutesOf(start) >= minutesOf(end)) {
      setProblem('Конец смены должен быть позже начала');
      return;
    }
    onApply({ ...state, start, end });
  };

  return (
    <Sheet
      title={`${state.employeeName} · ${formatDayLabel(state.date)}`}
      open
      onClose={onClose}
      actions={
        <>
          <Button stretched onClick={submit}>
            Сохранить смену
          </Button>
          {state.existing && (
            <Button variant="secondary" stretched onClick={() => onClear(state)}>
              Сделать выходным
            </Button>
          )}
        </>
      }
    >
      <TimeField label="Начало" value={start} onChange={changeStart} />
      <TimeField label="Конец" value={end} onChange={changeEnd} />
      {problem && <div className="alert alert--bad" role="alert">{problem}</div>}
    </Sheet>
  );
}
