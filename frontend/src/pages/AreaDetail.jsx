import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getEarlyWarning, getForecast } from '../services/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Loader } from '../components/ui/Loader';
import { ErrorState } from '../components/ui/ErrorState';
import { ForecastChart } from '../components/charts/ForecastChart';
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import { ArrowLeft, MapPin } from 'lucide-react';

const createDotIcon = (color) => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="${color}" width="32" height="32" stroke="white" stroke-width="2"><circle cx="12" cy="12" r="8"></circle></svg>`;
  return L.divIcon({ className: 'custom-leaflet-icon', html: svg, iconSize: [32, 32], iconAnchor: [16, 16] });
};

const AreaDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [intel, setIntel] = useState(null);
  const [forecast, setForecast] = useState([]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getEarlyWarning(id);
      setIntel(data);

      try {
        const fc = await getForecast(id, true);
        if (fc && fc.forecasts) setForecast(fc.forecasts);
      } catch (e) { console.warn("Forecast unavailable"); setForecast([]); }

    } catch (err) {
      if (err.response?.status === 404) {
        setError("Area or intelligence data not found. Make sure the scheduler has collected data.");
      } else {
        setError("Failed to fetch area intelligence.");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const handleRefresh = () => fetchData();
    window.addEventListener('app:refresh', handleRefresh);
    return () => window.removeEventListener('app:refresh', handleRefresh);
  }, [id]);

  if (loading) return <Loader />;
  if (error) return (
    <div className="space-y-4">
      <button onClick={() => navigate('/areas')} className="flex items-center gap-2 text-blue-400 hover:text-blue-300">
        <ArrowLeft className="w-4 h-4" /> Back to Areas
      </button>
      <ErrorState message={error} onRetry={fetchData} />
    </div>
  );

  const { area, weather, heatwave_risk, thermal_stress, mortality_vulnerability, demographics, overall_status } = intel;

  let markerColor = '#10B981';
  if (overall_status === 'WATCH') markerColor = '#F59E0B';
  if (overall_status === 'WARNING') markerColor = '#F97316';
  if (overall_status === 'CRITICAL') markerColor = '#EF4444';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4 border-b border-gray-800 pb-4">
        <button onClick={() => navigate('/areas')} className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div>
          <h1 className="text-3xl font-bold">{area.name}</h1>
          <p className="text-gray-400 flex items-center gap-1 mt-1">
            <MapPin className="w-4 h-4" /> {area.latitude.toFixed(4)}, {area.longitude.toFixed(4)}
          </p>
        </div>
        <div className="ml-auto">
          <Badge level={overall_status}>{overall_status}</Badge>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* LEFT COL */}
        <div className="space-y-6 lg:col-span-2">
          {weather && (
            <Card title="Current Observation" className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
              <div><p className="text-gray-400 text-xs">Temp</p><p className="text-2xl font-bold">{weather.temperature}°C</p></div>
              <div><p className="text-gray-400 text-xs">Humidity</p><p className="text-2xl font-bold">{weather.humidity}%</p></div>
              <div><p className="text-gray-400 text-xs">Wind</p><p className="text-2xl font-bold">{weather.wind_speed} km/h</p></div>
              <div><p className="text-gray-400 text-xs">Solar</p><p className="text-2xl font-bold">{weather.solar_radiation || '--'} W/m²</p></div>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card title="Heatwave Risk">
              <Badge level={heatwave_risk?.level}>{heatwave_risk?.level} ({heatwave_risk?.score})</Badge>
              <ul className="mt-4 text-sm text-gray-300 list-disc pl-4 space-y-1">
                {heatwave_risk?.contributing_factors?.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            </Card>

            <Card title="Thermal Stress">
              <Badge level={thermal_stress?.level}>{thermal_stress?.level} ({thermal_stress?.score})</Badge>
              <ul className="mt-4 text-sm text-gray-300 list-disc pl-4 space-y-1">
                {thermal_stress?.contributing_factors?.map((f, i) => <li key={i}>{f}</li>)}
              </ul>
            </Card>
          </div>

          <Card title="Mortality & Vulnerability Assessment">
            <div className="flex gap-4 items-center mb-4 border-b border-gray-800 pb-4">
              <Badge level={mortality_vulnerability?.level}>{mortality_vulnerability?.level} ({mortality_vulnerability?.score})</Badge>
              <span className="text-sm text-gray-400 font-mono">Mult: x{mortality_vulnerability?.vulnerability_factor?.toFixed(2)}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h4 className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wider">Demographic Drivers</h4>
                {demographics ? (
                  <div className="space-y-2 text-sm text-gray-300 bg-gray-800/30 p-3 rounded-lg border border-gray-700/50">
                    <div className="flex justify-between"><span>Pop:</span> <span>{demographics.population_total?.toLocaleString() || 'N/A'}</span></div>
                    <div className="flex justify-between"><span>Elderly:</span> <span className="text-red-400">{demographics.pct_elderly}%</span></div>
                    <div className="flex justify-between"><span>Children:</span> <span className="text-orange-400">{demographics.pct_children}%</span></div>
                    <p className="text-xs text-gray-400 mt-2 italic">"{demographics.vulnerability_notes || 'No notes'}"</p>
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No demographic data loaded.</p>
                )}
              </div>
              <div>
                <h4 className="text-xs font-semibold text-gray-500 mb-2 uppercase tracking-wider">Risk Factors</h4>
                <ul className="text-xs text-gray-300 list-disc pl-4 space-y-1">
                  {mortality_vulnerability?.contributing_factors?.map((f, i) => <li key={i}>{f}</li>)}
                </ul>
              </div>
            </div>
            <p className="text-[10px] text-gray-500 italic mt-4">{mortality_vulnerability?.methodology_note}</p>
          </Card>

          <Card title="48-Hour Local Forecast">
            <ForecastChart data={forecast} />
          </Card>
        </div>

        {/* RIGHT COL */}
        <div className="space-y-6">
          <Card title="Location Map" className="p-0 overflow-hidden">
            <div className="h-[300px] w-full z-0 relative">
              <MapContainer center={[area.latitude, area.longitude]} zoom={12} style={{ height: '100%', width: '100%', backgroundColor: '#0B101E' }} attributionControl={false}>
                <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png" subdomains="abcd" />
                <Marker position={[area.latitude, area.longitude]} icon={createDotIcon(markerColor)}>
                  <Popup className="custom-popup">{area.name}</Popup>
                </Marker>
              </MapContainer>
            </div>
          </Card>

          <Card title="Active Area Alerts">
            {intel.alerts?.length === 0 ? (
              <p className="text-sm text-gray-400">No active alerts for this area.</p>
            ) : (
              <div className="space-y-3">
                {intel.alerts?.map(alert => (
                  <div key={alert.id} className="p-3 bg-gray-800/50 rounded border border-gray-700">
                    <Badge level={alert.severity}>{alert.severity}</Badge>
                    <p className="text-sm mt-2">{alert.message}</p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};

export default AreaDetail;
