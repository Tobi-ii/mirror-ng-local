// App.jsx — The root component. Controls which page the user sees (Landing vs Dashboard vs Secret)
// and manages the login/logout flow plus cloud sync preference.
import React, { useState, useEffect, useCallback } from 'react';
import Dashboard from './pages/Dashboard';
import { Landing } from './pages/Landing';
import SecretImap from './pages/SecretImap';

import { BalanceProvider } from './contexts/BalanceContext';
import { BlurProvider } from './hooks/useBlurContext';
import { setCloudSync, setUserId, api } from './services/api';

function App() {
  // Which screen to show: 'loading' | 'landing' | 'dashboard' | 'secret'
  const [view, setView] = useState('loading');
  // The logged-in user's data (id, email, token), null until they log in
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const handleUnlock = useCallback(() => setView('secret'), []);
  const handleCloseSecret = useCallback(() => setView('landing'), []);
  useEffect(() => {
    const checkAuth = async () => {
      const params = new URLSearchParams(window.location.search.substring(1));
      const justLoggedIn = params.get('logged_in') === '1';
      if (justLoggedIn) {
        window.history.replaceState({}, document.title, window.location.pathname);
      }

      try {
        const me = await api.authMe();
        if (me && me.user_id) {
          const balances = await api.getBalances(me.user_id);
          const hasData = balances && balances.length > 0;
          setUserId(me.user_id);
          setUser({ user_id: me.user_id });
          if (hasData) {
            setView('dashboard');
          } else {
            setView('landing');
          }
        } else {
          setUser(null);
          setView('landing');
        }
      } catch (error) {
        console.error('Auth check failed:', error);
        setUser(null);
        setView('landing');
      } finally {
        setLoading(false);
      }
    };
    checkAuth();
  }, []);

  useEffect(() => {
    const handleAuthExpired = () => {
      setUserId(null);
      setUser(null);
      setView('landing');
    };
    window.addEventListener('auth:expired', handleAuthExpired);
    return () => window.removeEventListener('auth:expired', handleAuthExpired);
  }, []);

  // Called when the user logs in via email. Saves user data, auth token,
  // fetches their cloud sync preference, then shows the Dashboard.
  const handleLogin = async (userData, tokenData, password) => {
    const fullUser = { ...userData };
    setUser(fullUser);
    setUserId(fullUser.user_id);
    localStorage.removeItem(`mirror_onboarded_${fullUser.user_id}`);
    // Ask the server whether this user has cloud sync turned on
    try {
      const res = await api.getCloudSync(fullUser.user_id);
      if (res?.success) {
        setCloudSync(res.cloud_sync);
      }
    } catch (e) {
      // If the server is unreachable, default to cloud sync ON
      setCloudSync(true);
    }
    setView('dashboard');
  };

  // Called when an authenticated-but-no-data user clicks "Get Started" on Landing
  const handleStartSync = () => setView('dashboard');

  // Logs the user out: clears auth token, resets state, returns to landing
  const handleLogout = async () => {
    try { await api.logout(); } catch {}
    localStorage.removeItem('mirror_chat_history');
    setCloudSync(true);
    setUserId(null);
    setUser(null);
    setView('landing');
  };

  // Toggle cloud sync on/off. The new setting will be picked up when Dashboard re-renders.
  const handleCloudSyncChange = (enabled) => {
    setCloudSync(enabled);
  };

  if (loading) {
    return (
      <div className="bg-[#050608] h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin" />
      </div>
    );
  }

  if (view === 'secret') {
    return <SecretImap onClose={handleCloseSecret} />;
  }

  if (view === 'landing') {
    return (
      <Landing
        onLogin={handleLogin}
        onEasterEggClick={handleUnlock}
        user={user}
        onStartSync={handleStartSync}
      />
    );
  }

  return (
    <BlurProvider>
      <BalanceProvider userId={user?.user_id}>
        <Dashboard 
          userId={user?.user_id}
          onLogout={handleLogout}
          onCloudSyncChange={handleCloudSyncChange}
        />
      </BalanceProvider>
    </BlurProvider>
  );
}

export default App;