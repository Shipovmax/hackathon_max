import { Button, Typography } from '@maxhub/max-ui';
import { useParams } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { Schedule as ScheduleData } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';
import { addDays, formatDate, formatRange, WEEKDAYS } from '../lib/format';

export function Schedule() {
  const { storeId } = useParams();
  const state = useApi<ScheduleData>(`/stores/${storeId}/schedule/`);

  return (
    <AsyncView state={state}>
      {(data) => {
        const days = WEEKDAYS.map((label, index) => ({ label, date: addDays(data.week_start, index) }));
        return (
          <Screen
            title="График"
            subtitle={`${formatDate(data.week_start)} · ${data.status === 'draft' ? 'черновик' : 'опубликован'}`}
            back
          >
            <div className="screen__block">
              <table className="schedule">
                <thead>
                  <tr>
                    <th />
                    {days.map((day) => (
                      <th key={day.date}>
                        <Typography.Label variant="small">{day.label}</Typography.Label>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.employees.map((employee) => (
                    <tr key={employee.id}>
                      <td>
                        <Typography.Body variant="medium">{employee.name}</Typography.Body>
                      </td>
                      {days.map((day) => {
                        const shift = data.shifts.find((s) => s.employee_id === employee.id && s.date === day.date);
                        return (
                          <td key={day.date}>
                            <Typography.Body variant="small-strong">
                              {shift ? formatRange(shift.start, shift.end) : '—'}
                            </Typography.Body>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              {data.gaps.length > 0 && (
                <div className="alert">
                  <Typography.Body variant="medium-strong">Найдено окон: {data.gaps.length}</Typography.Body>
                  {data.gaps.map((gap) => (
                    <div key={`${gap.date}-${gap.start}`}>
                      {WEEKDAYS[days.findIndex((d) => d.date === gap.date)]}, {gap.start}–{gap.end} — никого
                    </div>
                  ))}
                </div>
              )}
              <Button variant="secondary" stretched disabled>
                Опубликовать
              </Button>
            </div>
          </Screen>
        );
      }}
    </AsyncView>
  );
}
