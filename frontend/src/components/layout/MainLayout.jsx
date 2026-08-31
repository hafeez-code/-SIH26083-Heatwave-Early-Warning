import React, { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

export const MainLayout = () => {
  const [isRefreshing, setIsRefreshing] = useState(false);

  // We can use a simple event bus or React Context, but for a lightweight
  // architecture, triggering a custom event is very simple and effective.
  const handleRefresh = () => {
    setIsRefreshing(true);
    window.dispatchEvent(new Event('app:refresh'));
    setTimeout(() => setIsRefreshing(false), 1000);
  };

  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content">
        <Topbar onRefresh={handleRefresh} isRefreshing={isRefreshing} />
        <main className="page-content animate-fade-in">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
