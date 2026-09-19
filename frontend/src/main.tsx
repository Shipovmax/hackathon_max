import '@maxhub/max-ui/dist/styles.css';
import './styles.css';

import { MaxUI } from '@maxhub/max-ui';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './App';
import { getPlatform } from './max/bridge';

const colorScheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MaxUI className="app-root" resetBody platform={getPlatform() === 'ios' ? 'ios' : 'android'} colorScheme={colorScheme}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </MaxUI>
  </StrictMode>,
);
