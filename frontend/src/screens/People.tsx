import { CellHeader, CellList, CellSimple } from '@maxhub/max-ui';

import { useApi } from '../api/hooks';
import type { Person, StoreWithPeople } from '../api/types';
import { AsyncView } from '../components/AsyncView';
import { Screen } from '../components/Screen';

const STATUS: Record<Person['status'], string> = {
  connected: 'в боте',
  invited: 'код выдан',
  dismissed: 'уволен',
};

export function People() {
  const state = useApi<StoreWithPeople[]>('/stores/');

  return (
    <AsyncView state={state}>
      {(stores) => (
        <Screen
          title="Точки и сотрудники"
          subtitle={`${stores.length} точки · ${stores.reduce((sum, s) => sum + s.employees.length, 0)} сотрудников`}
          back
        >
          {stores.map((store) => (
            <CellList key={store.id} mode="island" header={<CellHeader>{store.name}</CellHeader>}>
              {store.employees.length === 0 && <CellSimple title="Сотрудников пока нет" />}
              {store.employees.map((person) => (
                <CellSimple key={person.id} title={person.name} after={STATUS[person.status]} />
              ))}
            </CellList>
          ))}
        </Screen>
      )}
    </AsyncView>
  );
}
