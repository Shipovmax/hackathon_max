import { CellList, CellSimple } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { useApi } from '../api/hooks';
import type { Dashboard as DashboardData } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';
import { HealthBadge } from '../components/StatusBadge';
import { formatDate } from '../lib/format';

export function Dashboard() {
  const navigate = useNavigate();
  const state = useApi<DashboardData>('/dashboard/');

  return (
    <AsyncView state={state}>
      {(data) => {
        const clean = data.stores.filter((store) => store.health === 'ok').length;
        return (
          <Screen title="Мои точки" subtitle={`Сегодня, ${formatDate(data.date)} · ${clean} из ${data.stores.length} без замечаний`}>
            <CellList mode="island">
              {data.stores.map((store) => (
                <CellSimple
                  key={store.id}
                  title={store.name}
                  subtitle={`${store.done} из ${store.total}${store.last_event_label ? ` · ${store.last_event_label}` : ''}`}
                  after={<HealthBadge health={store.health} />}
                  showChevron
                  onClick={() => navigate(`/stores/${store.id}`)}
                />
              ))}
            </CellList>
            <CellList mode="island">
              <CellSimple title="Точки и сотрудники" showChevron onClick={() => navigate('/people')} />
            </CellList>
          </Screen>
        );
      }}
    </AsyncView>
  );
}
