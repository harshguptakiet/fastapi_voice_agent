'use client';

import { useSelector, useDispatch } from 'react-redux';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { setAuthFromStorage } from '@/app/store/authSlice';

export default function AuthLayout({ children }) {
  const { isAuthenticated, hydrated } = useSelector((state) => state.auth);
  const dispatch = useDispatch();
  const router = useRouter();

  useEffect(() => {
    dispatch(setAuthFromStorage());
  }, [dispatch]);

  useEffect(() => {
    if (hydrated && !isAuthenticated) {
      router.push('/login');
    }
  }, [hydrated, isAuthenticated, router]);

  // ✅ Render nothing until hydration is complete
  if (!hydrated) return null;

  return <>{children}</>;
}
