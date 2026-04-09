import { createSlice } from '@reduxjs/toolkit';

const initialState = {
  isAuthenticated: false,
  hydrated: false,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    login(state) {
      state.isAuthenticated = true;
      localStorage.setItem('isAuthenticated', 'true');
    },
    logout(state) {
      state.isAuthenticated = false;
      localStorage.removeItem('isAuthenticated');
    },
    setAuthFromStorage(state) {
      const persisted = localStorage.getItem('isAuthenticated') === 'true';
      state.isAuthenticated = persisted;
      state.hydrated = true;
    },
  },
});

export const { login, logout, setAuthFromStorage } = authSlice.actions;
export default authSlice.reducer; // ✅ Don't forget this!
