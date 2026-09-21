import '@maxhub/max-ui/dist/styles.css';
import './styles.css';

import { MaxUI } from '@maxhub/max-ui';
import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { getPlatform, watchColorScheme } from './max/bridge';

function Root() {
  const [colorScheme, setColorScheme] = useState<'light' | 'dark'>(
    window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
  );

  useEffect(() => watchColorScheme(setColorScheme), []);

  return (
    <MaxUI
      className="app-root"
      resetBody
      platform={getPlatform() === 'ios' ? 'ios' : 'android'}
      colorScheme={colorScheme}
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
