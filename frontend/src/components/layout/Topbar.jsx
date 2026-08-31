import React from 'react';
import { RefreshCw, Radio } from 'lucide-react';

export const Topbar = ({ onRefresh, isRefreshing, status = 'ONLINE' }) => {
  return (
    <header className="topbar">
      <div className="flex items-center gap-2">
        <Radio className={`w-5 h-5 ${status === 'ONLINE' ? 'text-green-400' : 'text-red-400'} animate-pulse`} />
        <span className="text-sm font-semibold tracking-wider text-gray-300">
          SYSTEM STATUS: {status}
        </span>
      </div>
      
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-400">
          {new Date().toLocaleString()}
        </span>
        <button 
          onClick={onRefresh}
          disabled={isRefreshing}
          className={`p-2 rounded-full bg-gray-800 border border-gray-700 hover:bg-gray-700 transition-colors ${isRefreshing ? 'opacity-50' : ''}`}
          title="Refresh Data"
        >
          <RefreshCw className={`w-4 h-4 text-gray-300 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>
    </header>
  );
};
