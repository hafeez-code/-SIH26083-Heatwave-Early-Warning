import React, { useState, useEffect } from 'react';
import { getAreas, getEarlyWarning, getAlerts, getForecast } from '../services/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Loader } from '../components/ui/Loader';
import { EmptyState, ErrorState } from '../components/ui/ErrorState';
import { RiskMap } from '../components/map/RiskMap';
import { ForecastChart } from '../components/charts/ForecastChart';
import { Thermometer, Droplets, Wind, CloudRain, Sun, AlertOctagon, Activity, Users, Bell, ShieldAlert } from 'lucide-react';

const Dashboard = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [areas, setAreas] = useState([]);
  const [primaryAreaWarning, setPrimaryAreaWarning] = useState(null);
  const [forecast, setForecast] = useState([]);
  const [globalAlerts, setGlobalAlerts] = useState([]);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const areasData = await getAreas();
      setAreas(areasData);

      if (areasData && areasData.length > 0) {
        // Pick the first area or the one with highest risk if we wanted to compute it
        // For dashboard simplicity, let's load intelligence for the first area
        const primaryId = areasData[0].id;
        try {
          const warningData = await getEarlyWarning(primaryId);
          setPrimaryAreaWarning(warningData);
        } catch (e) {
          console.warn("Primary area early warning fetch failed", e);
          setPrimaryAreaWarning(null);
        }

        try {
          const forecastData = await getForecast(primaryId, true);
          if (forecastData && forecastData.forecasts) {
            setForecast(forecastData.forecasts);
          }
        } catch (e) {
          console.warn("Primary area forecast fetch failed", e);
          setForecast([]);
        }
      }

      try {
        const alertsData = await getAlerts();
        setGlobalAlerts(alertsData || []);
      } catch (e) {
        console.warn("Global alerts fetch failed", e);
        setGlobalAlerts([]);
      }

    } catch (err) {
      console.error(err);
      setError("Failed to fetch dashboard intelligence.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const handleRefresh = () => fetchData();
    window.addEventListener('app:refresh', handleRefresh);
    return () => window.removeEventListener('app:refresh', handleRefresh);
  }, []);

  if (loading) return <Loader />;
  if (error) return <ErrorState message={error} onRetry={fetchData} />;
  if (!areas || areas.length === 0) return <EmptyState title="No Monitored Areas" message="Please add areas to the system via the backend API to begin monitoring." />;

  const p = primaryAreaWarning;
  const w = p?.weather;
  
  // Transform areas to include dummy riskLevel for map if we don't have it fetched individually
  // In a real app we'd fetch all warnings, but for performance we just use primary area or defaults
  const mapAreas = areas.map(a => {
    if (a.id === p?.area_id) {
      return { ...a, riskLevel: p.overall_status, temperature: w?.temperature, heatwaveRisk: p.heatwave_risk?.level };
    }
    return { ...a, riskLevel: 'NORMAL' };
  });

  return (
    <div className="space-y-6">
      <div className="grid-3">
        {/* HERO / OVERALL STATUS */}
        <Card className="col-span-1 md:col-span-2 lg:col-span-1 border-l-4" style={{borderLeftColor: p ? `var(--color-${p.overall_status.toLowerCase()})` : 'var(--color-normal)'}}>
          <h2 className="text-gray-400 text-sm font-semibold tracking-wider mb-2">CURRENT HEATWAVE STATUS</h2>
          <div className="text-5xl font-black mb-4" style={{color: p ? `var(--color-${p.overall_status.toLowerCase()})` : 'var(--text-secondary)'}}>
            {p ? p.overall_status : 'UNKNOWN'}
          </div>
          {w && (
            <div className="grid grid-cols-2 gap-4 mt-6">
              <div>
                <p className="text-gray-400 text-xs">Temperature</p>
                <p className="text-xl font-bold">{w.temperature}°C</p>
              </div>
              <div>
                <p className="text-gray-400 text-xs">Humidity</p>
                <p className="text-xl font-bold">{w.humidity}%</p>
              </div>
              <div>
                <p className="text-gray-400 text-xs">Heat Risk</p>
                <Badge level={p.heatwave_risk?.level}>{p.heatwave_risk?.level}</Badge>
              </div>
              <div>
                <p className="text-gray-400 text-xs">Thermal Stress</p>
                <Badge level={p.thermal_stress?.level}>{p.thermal_stress?.level}</Badge>
              </div>
            </div>
          )}
          {!p && <p className="text-sm text-secondary">No recent weather intelligence collected for primary area.</p>}
        </Card>

        {/* WEATHER METRICS */}
        <div className="col-span-1 md:col-span-2 lg:col-span-2 grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card title="Temp" icon={Thermometer} className="flex flex-col justify-center text-center">
            <span className="text-3xl font-bold text-white">{w?.temperature ?? '--'}°C</span>
          </Card>
          <Card title="Humidity" icon={Droplets} className="flex flex-col justify-center text-center">
            <span className="text-3xl font-bold text-white">{w?.humidity ?? '--'}%</span>
          </Card>
          <Card title="Wind" icon={Wind} className="flex flex-col justify-center text-center">
            <span className="text-3xl font-bold text-white">{w?.wind_speed ?? '--'} km/h</span>
          </Card>
          <Card title="Solar Rad." icon={Sun} className="flex flex-col justify-center text-center">
            <span className="text-3xl font-bold text-white">{w?.solar_radiation ?? '--'} W/m²</span>
          </Card>
        </div>
      </div>

      {/* RISK INTELLIGENCE */}
      {p && (
        <div className="grid-3">
          <Card title="Heatwave Risk" icon={AlertOctagon}>
            <div className="mb-3 flex items-center justify-between">
              <Badge level={p.heatwave_risk?.level}>{p.heatwave_risk?.level}</Badge>
              <span className="text-lg font-bold">{p.heatwave_risk?.score}/100</span>
            </div>
            <ul className="text-sm text-gray-300 space-y-1 mb-4 list-disc pl-4">
              {p.heatwave_risk?.contributing_factors?.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
          </Card>
          
          <Card title="Human Thermal Stress" icon={Activity}>
            <div className="mb-3 flex items-center justify-between">
              <Badge level={p.thermal_stress?.level}>{p.thermal_stress?.level}</Badge>
              <span className="text-lg font-bold">{p.thermal_stress?.score}/100</span>
            </div>
            <ul className="text-sm text-gray-300 space-y-1 mb-4 list-disc pl-4">
              {p.thermal_stress?.contributing_factors?.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
            <p className="text-xs text-gray-500 italic mt-auto">{p.thermal_stress?.methodology_note}</p>
          </Card>

          <Card title="Mortality Vulnerability" icon={Users}>
            <div className="mb-3 flex items-center justify-between">
              <Badge level={p.mortality_vulnerability?.level}>{p.mortality_vulnerability?.level}</Badge>
              <span className="text-lg font-bold">{p.mortality_vulnerability?.score}/100</span>
            </div>
            <div className="text-sm text-gray-300 mb-2 font-semibold">
              Multiplier: x{p.mortality_vulnerability?.vulnerability_factor?.toFixed(2)}
            </div>
            <ul className="text-xs text-gray-400 space-y-1 mb-4 list-disc pl-4 max-h-24 overflow-y-auto">
              {p.mortality_vulnerability?.contributing_factors?.map((f, i) => <li key={i}>{f}</li>)}
            </ul>
            <p className="text-[10px] text-gray-500 italic leading-tight">{p.mortality_vulnerability?.methodology_note}</p>
          </Card>
        </div>
      )}

      {/* LOWER SECTION: MAP & FORECAST & ALERTS */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card title="Global Risk Map">
            <RiskMap areas={mapAreas} />
          </Card>
          <Card title="48-Hour Forecast Intelligence">
            <ForecastChart data={forecast} height={300} />
          </Card>
        </div>
        
        <div className="lg:col-span-1 space-y-6">
          <Card title="Active Alerts" icon={Bell} className="h-full">
            {globalAlerts.length === 0 ? (
              <div className="text-center p-6 text-gray-400">
                <ShieldAlert className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No active heatwave alerts.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {globalAlerts.slice(0, 5).map(alert => (
                  <div key={alert.id} className="p-3 bg-gray-800/50 rounded-lg border border-gray-700">
                    <div className="flex justify-between items-start mb-1">
                      <Badge level={alert.severity}>{alert.severity}</Badge>
                      <span className="text-xs text-gray-500">{new Date(alert.created_at).toLocaleTimeString()}</span>
                    </div>
                    <p className="text-sm text-white mt-2">{alert.message}</p>
                  </div>
                ))}
                {globalAlerts.length > 5 && (
                  <p className="text-center text-xs text-blue-400 cursor-pointer hover:underline">View all {globalAlerts.length} alerts</p>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
