import '@maxhub/max-ui/dist/styles.css';
import './styles.css';

import { MaxUI } from '@maxhub/max-ui';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { getPlatform, startRoute } from './max/bridge';
import { useTheme } from './max/theme';

// Диплинк из уведомления подставляем в адрес до старта роутера, чтобы «Назад»
// вёл на сводку, а не наружу из приложения.
const deepLink = startRoute();
if (deepLink && window.location.pathname === '/') {
  // Сводка остаётся в истории, поэтому «Назад» из карточки ведёт на неё, а не
  // закрывает приложение.
  window.history.pushState(null, '', deepLink);
}

function Root() {
  const { scheme } = useTheme();
  const platform = getPlatform();

  return (
    <MaxUI
      className={`app-root app-root--${platform}`}
      resetBody
      platform={platform === 'ios' ? 'ios' : 'android'}
      colorScheme={scheme}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MaxUI>
  );
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
