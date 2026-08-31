import React from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { format, parseISO } from 'date-fns';

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div className="glass-panel p-3 text-sm">
        <p className="font-bold text-white mb-1">
          {format(parseISO(label), 'MMM d, HH:mm')}
        </p>
        {payload.map((entry, index) => (
          <p key={`item-${index}`} style={{ color: entry.color }} className="font-medium">
            {entry.name}: {entry.value} {entry.name === 'Temperature' ? '°C' : '%'}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export const ForecastChart = ({ data = [], height = 300 }) => {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-secondary">
        No forecast data available.
      </div>
    );
  }

  const formattedData = data.map(item => ({
    ...item,
    formattedTime: item.forecast_timestamp, // parseISO will handle this
  }));

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <AreaChart
          data={formattedData}
          margin={{ top: 10, right: 10, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorTemp" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#F97316" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#F97316" stopOpacity={0}/>
            </linearGradient>
            <linearGradient id="colorHum" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.3}/>
              <stop offset="95%" stopColor="#3B82F6" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
          <XAxis 
            dataKey="formattedTime" 
            tickFormatter={(timeStr) => format(parseISO(timeStr), 'HH:mm')}
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            tickMargin={10}
            minTickGap={30}
          />
          <YAxis 
            yAxisId="temp"
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            domain={['dataMin - 2', 'dataMax + 2']}
            tickFormatter={(val) => `${val}°`}
          />
          <YAxis 
            yAxisId="hum"
            orientation="right"
            stroke="#9CA3AF"
            tick={{ fill: '#9CA3AF', fontSize: 12 }}
            domain={[0, 100]}
            hide={true}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area 
            yAxisId="temp"
            type="monotone" 
            dataKey="temperature" 
            name="Temperature"
            stroke="#F97316" 
            strokeWidth={3}
            fillOpacity={1} 
            fill="url(#colorTemp)" 
          />
          <Area 
            yAxisId="hum"
            type="monotone" 
            dataKey="humidity" 
            name="Humidity"
            stroke="#3B82F6" 
            strokeWidth={2}
            fillOpacity={1} 
            fill="url(#colorHum)" 
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};
