import { CellList, CellSimple, IconButton, Typography } from '@maxhub/max-ui';
import { useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { Dashboard as DashboardData, StoreHealth } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { DateNav } from '../components/DateNav';
import { Empty } from '../components/Empty';
import { Icon } from '../components/Icon';
import { Screen } from '../components/Screen';
import { healthTone, HealthBadge, Progress, StatusDot } from '../components/StatusBadge';
import { addDays, formatDate, plural, today } from '../lib/format';
import { useTheme } from '../max/theme';

// Точки с проблемами поднимаются наверх: красные впереди жёлтых, зелёные — в конце.
const HEALTH_RANK: Record<StoreHealth, number> = { overdue: 0, unclaimed: 0, late: 1, ok: 2 };

export function Dashboard() {
  const navigate = useNavigate();
  const theme = useTheme();
  const [params, setParams] = useSearchParams();
  const date = params.get('date') ?? today();
  const setDate = useCallback(
    (next: string) => setParams(next === today() ? {} : { date: next }, { replace: true }),
    [setParams],
  );
  const state = useApi<DashboardData>(`/dashboard/?date=${date}`);
  const yesterday = addDays(today(), -1);
  const previous = useApi<DashboardData>(`/dashboard/?date=${yesterday}`);

  return (
    <AsyncView state={state}>
      {(data) => {
        // Красные — задача не сделана, туда надо вмешаться. Жёлтые — сделали, но поздно.
        const urgent = data.stores.filter((store) => store.health === 'overdue' || store.health === 'unclaimed');
        const late = data.stores.filter((store) => store.health === 'late');
        const tone = urgent.length ? 'bad' : late.length ? 'warn' : 'ok';
        const sortedStores = [...data.stores].sort((a, b) => HEALTH_RANK[a.health] - HEALTH_RANK[b.health]);
        const done = data.stores.reduce((sum, store) => sum + store.done, 0);
        const total = data.stores.reduce((sum, store) => sum + store.total, 0);
        const previousProblems =
          date === today()
            ? (previous.data?.stores.filter((store) => store.health === 'overdue' || store.health === 'unclaimed') ?? [])
            : [];

        return (
          <Screen
            title="Мои точки"
            subtitle={date === today() ? `Сегодня, ${formatDate(data.date)}` : formatDate(data.date)}
            action={
              <span className="screen__actions">
                <IconButton
                  size="small"
                  variant="secondary"
                  aria-label={theme.scheme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                  onClick={theme.toggle}
                >
                  <Icon name={theme.scheme === 'dark' ? 'sun' : 'moon'} />
                </IconButton>
                <IconButton
                  size="small"
                  variant="secondary"
                  aria-label="Обновить"
                  loading={state.loading}
                  onClick={state.reload}
                >
                  <Icon name="refresh" />
                </IconButton>
              </span>
            }
          >
            <div className="screen__block">
              <DateNav date={date} onChange={setDate} calendar />
            </div>

            {previousProblems.length > 0 && (
              <CellList mode="island">
                <CellSimple
                  title="За вчера остались невыполненные задачи"
                  subtitle={previousProblems.map((store) => store.name).join(', ')}
                  after={<span className="badge badge--bad">{previousProblems.length}</span>}
                  showChevron
                  onClick={() => setDate(yesterday)}
                />
              </CellList>
            )}

            {data.stores.length > 0 && (
              <div className="screen__block">
                <div className={`summary summary--${tone}`}>
                  <Typography.Title variant="small-strong">
                    {urgent.length
                      ? `${urgent.length} ${plural(urgent.length, ['точка требует', 'точки требуют', 'точек требуют'])} внимания`
                      : late.length
                        ? `Всё выполнено, но ${late.length} ${plural(late.length, ['точка', 'точки', 'точек'])} с опозданием`
                        : 'Все точки без замечаний'}
                  </Typography.Title>
                  <Typography.Body variant="small">
                    {total > 0
                      ? `Выполнено ${done} из ${total} ${plural(total, ['задачи', 'задач', 'задач'])} за день`
                      : date === today() ? 'Задач на сегодня нет' : 'Задач за этот день нет'}
                  </Typography.Body>
                  <Progress done={done} total={total} tone={tone === 'ok' ? 'ok' : 'warn'} />
                </div>
              </div>
            )}

            {data.stores.length === 0 && (
              <div className="screen__block">
                <Empty
                  icon="store"
                  title="Точек пока нет"
                  text="Добавьте магазин, сотрудников и задачи — бот начнёт вести смену со следующего дня."
                  action={{ label: 'Добавить точку', onClick: () => navigate('/people') }}
                />
              </div>
            )}

            {data.stores.length > 0 && (
              <CellList mode="island">
                {sortedStores.map((store) => (
                  <CellSimple
                    key={store.id}
                    before={<StatusDot tone={healthTone(store.health)} />}
                    title={store.name}
                    subtitle={
                      <span className="storerow">
                        <span className="storerow__text">
                          {store.done} из {store.total}
                          {store.last_event_label ? ` · ${store.last_event_label}` : ''}
                        </span>
                        <Progress done={store.done} total={store.total} tone={healthTone(store.health)} />
                      </span>
                    }
                    after={<HealthBadge health={store.health} />}
                    showChevron
                    onClick={() => navigate(`/stores/${store.id}${date === today() ? '' : `?date=${date}`}`)}
                  />
                ))}
              </CellList>
            )}

            <CellList mode="island">
              <CellSimple title="Точки и сотрудники" showChevron onClick={() => navigate('/people')} />
            </CellList>

            <div className="screen__block">
              <Typography.Label variant="small" className="muted">
                В штатном режиме приложение молчит. Уведомление приходит только тогда, когда нужно вмешаться.
              </Typography.Label>
            </div>
          </Screen>
        );
      }}
    </AsyncView>
  );
}
