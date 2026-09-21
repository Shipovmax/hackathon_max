import { CellList, CellSimple, IconButton, Typography } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { Dashboard as DashboardData } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';
import { healthTone, HealthBadge, Progress, StatusDot } from '../components/StatusBadge';
import { formatDate, plural } from '../lib/format';

export function Dashboard() {
  const navigate = useNavigate();
  const state = useApi<DashboardData>('/dashboard/');

  return (
    <AsyncView state={state}>
      {(data) => {
        const problems = data.stores.filter((store) => store.health !== 'ok');
        const done = data.stores.reduce((sum, store) => sum + store.done, 0);
        const total = data.stores.reduce((sum, store) => sum + store.total, 0);

        return (
          <Screen
            title="Мои точки"
            subtitle={`Сегодня, ${formatDate(data.date)}`}
            action={
              <IconButton
                size="small"
                variant="secondary"
                aria-label="Обновить"
                loading={state.loading}
                onClick={state.reload}
              >
                ↻
              </IconButton>
            }
          >
            <div className="screen__block">
              <div className={`summary summary--${problems.length === 0 ? 'ok' : 'bad'}`}>
                <Typography.Title variant="small-strong">
                  {data.stores.length === 0
                    ? 'Точек пока нет'
                    : problems.length === 0
                      ? 'Все точки без замечаний'
                      : `${problems.length} ${plural(problems.length, ['точка требует', 'точки требуют', 'точек требуют'])} внимания`}
                </Typography.Title>
                <Typography.Body variant="small">
                  {total > 0
                    ? `Выполнено ${done} из ${total} ${plural(total, ['задачи', 'задач', 'задач'])} за день`
                    : 'Добавьте точку и задачи, чтобы бот начал вести смену'}
                </Typography.Body>
                <Progress done={done} total={total} tone={problems.length === 0 ? 'ok' : 'warn'} />
              </div>
            </div>

            <CellList mode="island">
              {data.stores.length === 0 && (
                <CellSimple title="Добавьте первую точку" subtitle="Экран «Точки и сотрудники»" />
              )}
              {data.stores.map((store) => (
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
                  onClick={() => navigate(`/stores/${store.id}`)}
                />
              ))}
            </CellList>

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
