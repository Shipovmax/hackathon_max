import { Spinner, Typography } from '@maxhub/max-ui';
import { Navigate, Route, Routes } from 'react-router-dom';

import { useApi } from './api/hooks';
import type { Me } from './api/types';
import { ToastProvider } from './components/Toast';
import { AccessProblem } from './screens/AccessProblem';
import { Dashboard } from './screens/Dashboard';
import { People } from './screens/People';
import { Schedule } from './screens/Schedule';
import { StoreDay } from './screens/StoreDay';
import { StoreTasks } from './screens/StoreTasks';

export function App() {
  const me = useApi<Me>('/me/');

  if (me.loading && me.data === null) {
    return (
      <div className="center">
        <Spinner />
        <Typography.Label variant="small">Открываем приложение</Typography.Label>
      </div>
    );
  }
  if (me.data === null) return <AccessProblem error={me.error} onRetry={me.reload} />;
  if (me.data.role !== 'owner') {
    return <AccessProblem error={null} onRetry={me.reload} notOwner />;
  }

  return (
    <ToastProvider>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/stores/:storeId" element={<StoreDay />} />
        <Route path="/stores/:storeId/schedule" element={<Schedule />} />
        <Route path="/stores/:storeId/tasks" element={<StoreTasks />} />
        <Route path="/people" element={<People />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ToastProvider>
  );
}
