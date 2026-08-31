import React, { useState, useEffect } from 'react';
import { getAreas, getForecast } from '../services/api';
import { Card } from '../components/ui/Card';
import { Loader } from '../components/ui/Loader';
import { ErrorState } from '../components/ui/ErrorState';
import { ForecastChart } from '../components/charts/ForecastChart';

const Forecast = () => {
  const [areas, setAreas] = useState([]);
  const [selectedArea, setSelectedArea] = useState('');
  const [forecast, setForecast] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchAreas = async () => {
      try {
        const data = await getAreas();
        setAreas(data || []);
        if (data && data.length > 0) setSelectedArea(data[0].id.toString());
        setLoading(false);
      } catch (err) {
        setError("Failed to load areas");
        setLoading(false);
      }
    };
    fetchAreas();
  }, []);

  useEffect(() => {
    const fetchForecast = async () => {
      if (!selectedArea) return;
      try {
        setLoading(true);
        setError(null);
        // By default use stored forecast for speed, but fallback to live if needed
        const data = await getForecast(selectedArea, true);
        if (data && data.forecasts) setForecast(data.forecasts);
        else setForecast([]);
      } catch (err) {
        if (err.response?.status === 404) {
          setError("No stored forecast found for this area.");
        } else {
          setError("Failed to load forecast.");
        }
        setForecast([]);
      } finally {
        setLoading(false);
      }
    };
    
    fetchForecast();
    const handleRefresh = () => fetchForecast();
    window.addEventListener('app:refresh', handleRefresh);
    return () => window.removeEventListener('app:refresh', handleRefresh);
  }, [selectedArea]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold">Forecast Intelligence</h2>
        
        <select 
          className="bg-gray-800 border border-gray-700 text-white rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:outline-none"
          value={selectedArea}
          onChange={(e) => setSelectedArea(e.target.value)}
          disabled={loading || areas.length === 0}
        >
          {areas.length === 0 && <option value="">No areas available</option>}
          {areas.map(a => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
      </div>

      <Card>
        {loading ? (
          <Loader message="Loading forecast data..." />
        ) : error ? (
          <ErrorState message={error} />
        ) : forecast.length > 0 ? (
          <ForecastChart data={forecast} height={400} />
        ) : (
          <ErrorState message="No forecast data available to display." />
        )}
      </Card>
      
      {forecast.length > 0 && (
        <Card title="Hourly Raw Data" className="overflow-x-auto">
          <table className="w-full text-left text-sm text-gray-300">
            <thead className="bg-gray-800/50 text-gray-400">
              <tr>
                <th className="p-3 rounded-tl-lg">Time</th>
                <th className="p-3">Temp (°C)</th>
                <th className="p-3">Humidity (%)</th>
                <th className="p-3">Wind (km/h)</th>
                <th className="p-3 rounded-tr-lg">Precip (mm)</th>
              </tr>
            </thead>
            <tbody>
              {forecast.slice(0, 24).map((f, i) => (
                <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/30">
                  <td className="p-3">{new Date(f.forecast_timestamp).toLocaleString()}</td>
                  <td className="p-3 font-medium text-orange-400">{f.temperature}</td>
                  <td className="p-3 text-blue-400">{f.humidity}</td>
                  <td className="p-3">{f.wind_speed}</td>
                  <td className="p-3">{f.precipitation}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {forecast.length > 24 && (
            <p className="text-center text-xs text-gray-500 mt-4 py-2">Showing next 24 hours. More data available in chart.</p>
          )}
        </Card>
      )}
    </div>
  );
};

export default Forecast;
