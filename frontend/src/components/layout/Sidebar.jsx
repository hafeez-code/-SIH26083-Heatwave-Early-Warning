import React from 'react';
import { NavLink } from 'react-router-dom';
import { Activity, Map, BarChart2, Bell, ShieldAlert } from 'lucide-react';

export const Sidebar = () => {
  const links = [
    { to: '/', icon: Activity, label: 'Dashboard' },
    { to: '/areas', icon: Map, label: 'Areas & Mapping' },
    { to: '/forecast', icon: BarChart2, label: 'Forecast Intel' },
    { to: '/alerts', icon: Bell, label: 'Alert Center' },
  ];

  return (
    <div className="sidebar p-4">
      <div className="flex items-center gap-3 mb-10 mt-2 px-2">
        <ShieldAlert className="w-8 h-8 text-blue-500" />
        <div>
          <h1 className="font-bold text-sm tracking-wider text-white">SIH26083</h1>
          <p className="text-xs text-blue-400">COMMAND CENTER</p>
        </div>
      </div>
      
      <nav className="flex flex-col gap-2">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            className={({ isActive }) => 
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                isActive 
                  ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30' 
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              }`
            }
          >
            <link.icon className="w-5 h-5" />
            <span className="font-medium">{link.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto px-4 py-4 text-xs text-gray-500 border-t border-gray-800">
        <p>Heatwave Early Warning System</p>
        <p>v0.20 Backend Link</p>
      </div>
    </div>
  );
};
