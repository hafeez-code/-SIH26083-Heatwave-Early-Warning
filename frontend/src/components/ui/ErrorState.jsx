import React from 'react';
import { AlertTriangle } from 'lucide-react';

export const ErrorState = ({ message = 'An error occurred fetching intelligence.', onRetry }) => (
  <div className="flex flex-col items-center justify-center p-10 h-full min-h-[200px] text-center">
    <AlertTriangle className="w-12 h-12 text-warning mb-4" />
    <h3 className="text-lg font-semibold mb-2">System Error</h3>
    <p className="text-secondary mb-4 max-w-md">{message}</p>
    {onRetry && (
      <button 
        onClick={onRetry}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
      >
        Retry Connection
      </button>
    )}
  </div>
);

export const EmptyState = ({ title = 'No Data', message = 'No intelligence data available.' }) => (
  <div className="flex flex-col items-center justify-center p-10 h-full min-h-[200px] text-center">
    <div className="w-16 h-16 bg-gray-800 rounded-full flex items-center justify-center mb-4 border border-gray-700">
      <span className="text-2xl opacity-50">?</span>
    </div>
    <h3 className="text-lg font-semibold mb-2">{title}</h3>
    <p className="text-secondary max-w-md">{message}</p>
  </div>
);
