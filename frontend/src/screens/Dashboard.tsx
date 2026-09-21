import { CellList, CellSimple, IconButton, Typography } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { Dashboard as DashboardData } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';
import { HealthBadge } from '../components/StatusBadge';
import { formatDate, plural } from '../lib/format';

export function Dashboard() {
  const navigate = useNavigate();
  const state = useApi<DashboardData>('/dashboard/');

  return (
    <AsyncView state={state}>
      {(data) => {
        const clean = data.stores.filter((store) => store.health === 'ok').length;
        const summary =
          data.stores.length === 0
            ? 'Точек пока нет'
            : clean === data.stores.length
              ? 'Все точки без замечаний'
              : `${clean} ${plural(clean, ['точка', 'точки', 'точек'])} из ${data.stores.length} без замечаний`;

        return (
          <Screen
            title="Мои точки"
            subtitle={`Сегодня, ${formatDate(data.date)} · ${summary}`}
            action={
              <IconButton size="small" variant="secondary" aria-label="Обновить" loading={state.loading} onClick={state.reload}>
                ↻
              </IconButton>
            }
          >
            <CellList mode="island">
              {data.stores.length === 0 && <CellSimple title="Добавьте первую точку" subtitle="Экран «Точки и сотрудники»" />}
              {data.stores.map((store) => (
                <CellSimple
                  key={store.id}
                  title={store.name}
                  subtitle={`Выполнено ${store.done} из ${store.total}${store.last_event_label ? ` · ${store.last_event_label}` : ''}`}
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
              <Typography.Label variant="small">
                В штатном режиме экран молчит. Уведомление приходит только тогда, когда нужно вмешаться.
              </Typography.Label>
            </div>
          </Screen>
        );
      }}
    </AsyncView>
  );
}
