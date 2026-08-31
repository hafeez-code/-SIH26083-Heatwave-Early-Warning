import React from 'react';

export const Card = ({ title, children, className = '', icon: Icon, action }) => {
  return (
    <div className={`glass-panel p-5 ${className}`}>
      {(title || Icon || action) && (
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {Icon && <Icon className="w-5 h-5 text-secondary" />}
            {title && <h3 className="font-semibold text-primary">{title}</h3>}
          </div>
          {action && <div>{action}</div>}
        </div>
      )}
      <div>{children}</div>
    </div>
  );
};
