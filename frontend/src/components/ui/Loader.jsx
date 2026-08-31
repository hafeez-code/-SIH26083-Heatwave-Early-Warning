import React from 'react';

export const Loader = ({ message = 'Loading intelligence...' }) => (
  <div className="flex flex-col items-center justify-center p-10 h-full min-h-[200px]">
    <div className="spinner mb-4"></div>
    <p className="text-secondary">{message}</p>
  </div>
);
