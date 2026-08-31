import React from 'react';

export const Badge = ({ level, children }) => {
  const getBadgeClass = (level) => {
    switch (level?.toUpperCase()) {
      case 'NORMAL':
        return 'badge-normal';
      case 'WATCH':
        return 'badge-watch';
      case 'WARNING':
      case 'HIGH':
        return 'badge-warning';
      case 'CRITICAL':
      case 'EXTREME':
        return 'badge-critical';
      default:
        return 'badge-normal'; // Fallback
    }
  };

  return (
    <span className={`badge ${getBadgeClass(level)}`}>
      {children || level}
    </span>
  );
};
