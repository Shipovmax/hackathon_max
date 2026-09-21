import { Button, IconButton, Typography } from '@maxhub/max-ui';
import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';

import { apiPost, apiPut } from '../api/client';
import { useAction, useApi } from '../api/hooks';
import type { Coverage, Gap, Schedule as ScheduleData, ShiftInput } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { ErrorNote } from '../components/ErrorNote';
import { Screen } from '../components/Screen';
import { Sheet } from '../components/Sheet';
import { TextField } from '../components/Field';
import { useToast } from '../components/Toast';
import { findGaps } from '../lib/coverage';
import {
  addDays,
  formatDayLabel,
  formatRange,
  formatWeekRange,
  isValidTime,
  minutesOf,
  normalizeTime,
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
  // Владелец обычно заполняет следующую неделю, с неё и начинаем.
  const [week, setWeek] = useState(() => addDays(weekStart(today()), 7));
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
    setDirty(false);
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
    <Screen title="График смен" subtitle={`${formatWeekRange(data.week_start)} · ${data.status === 'draft' ? 'черновик' : 'опубликован'}`} back>
      <div className="screen__block">
        <div className="datenav">
          <IconButton
            size="small"
            variant="secondary"
            aria-label="Предыдущая неделя"
            disabled={dirty}
            onClick={() => onWeek(addDays(week, -7))}
          >
            ‹
          </IconButton>
          <Typography.Body variant="medium-strong">{formatWeekRange(data.week_start)}</Typography.Body>
          <IconButton
            size="small"
            variant="secondary"
            aria-label="Следующая неделя"
            disabled={dirty}
            onClick={() => onWeek(addDays(week, 7))}
          >
            ›
          </IconButton>
        </div>

        <Typography.Label variant="small">
          Рабочий день {formatRange(data.open_time, data.close_time)}. Нажмите на ячейку, чтобы задать смену. Пустая
          ячейка — выходной.
        </Typography.Label>

        {data.employees.length === 0 ? (
          <div className="alert">
            <Typography.Body variant="medium">
              На точке нет сотрудников. Добавьте их на экране «Точки и сотрудники».
            </Typography.Body>
          </div>
        ) : (
          <div className="schedule__scroll">
            <table className="schedule">
              <thead>
                <tr>
                  <th />
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
                    <td className="schedule__name">
                      <Typography.Body variant="small-strong">{employee.name}</Typography.Body>
                    </td>
                    {days.map((day) => {
                      const shift = shifts.find((item) => item.employee_id === employee.id && item.date === day.date);
                      return (
                        <td key={day.date} className={cellClass(day.date, day.weekend)}>
                          <button
                            type="button"
                            className={`schedule__cell${shift ? ' schedule__cell--filled' : ''}`}
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
              Правки пока только на экране. {data.status === 'draft' ? 'Опубликуйте' : 'Сохраните'} их, чтобы график
              увидели сотрудники.
            </Typography.Body>
          </div>
        )}

        <ErrorNote error={check.error ?? save.error} />

        <Button variant="secondary" stretched loading={check.running} onClick={runCheck}>
          Проверить покрытие
        </Button>
        {data.status === 'draft' ? (
          <Button
            stretched
            loading={save.running}
            disabled={data.employees.length === 0}
            onClick={() => runSave(true)}
          >
            Опубликовать
          </Button>
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
    <Sheet title={`${state.employeeName} · ${formatDayLabel(state.date)}`} open onClose={onClose}>
      <TextField label="Начало" value={start} onChange={(value) => setStart(normalizeTime(value))} inputMode="numeric" placeholder="09:00" />
      <TextField label="Конец" value={end} onChange={(value) => setEnd(normalizeTime(value))} inputMode="numeric" placeholder="17:00" />
      {problem && <div className="alert alert--bad">{problem}</div>}
      <Button stretched onClick={submit}>
        Сохранить смену
      </Button>
      {state.existing && (
        <Button variant="secondary" stretched onClick={() => onClear(state)}>
          Сделать выходным
        </Button>
      )}
    </Sheet>
  );
}
