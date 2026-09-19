import { Spinner } from '@maxhub/max-ui';
import { Route, Routes } from 'react-router-dom';

import { useApi } from './api/hooks';
import type { Me } from './api/types';
import { AccessProblem } from './screens/AccessProblem';
import { Dashboard } from './screens/Dashboard';
import { People } from './screens/People';
import { Schedule } from './screens/Schedule';
import { StoreDay } from './screens/StoreDay';
import { StoreTasks } from './screens/StoreTasks';

export function App() {
  const me = useApi<Me>('/me/');

  if (me.loading) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  if (me.error) return <AccessProblem error={me.error} onRetry={me.reload} />;

  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/stores/:storeId" element={<StoreDay />} />
      <Route path="/stores/:storeId/schedule" element={<Schedule />} />
      <Route path="/stores/:storeId/tasks" element={<StoreTasks />} />
      <Route path="/people" element={<People />} />
    </Routes>
  );
}
