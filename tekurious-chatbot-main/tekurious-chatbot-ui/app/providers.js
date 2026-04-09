'use client';

import { Provider } from 'react-redux';
import { store } from '@/app/store/store';
import { useEffect } from 'react';
import { setAuthFromStorage } from '@/app/store/authSlice';

function ReduxInitializer() {
  useEffect(() => {
    store.dispatch(setAuthFromStorage());
  }, []);

  return null;
}

export default function Providers({ children }) {
  return (
    <Provider store={store}>
      <ReduxInitializer />
      {children}
    </Provider>
  );
}
