import React, { useState, useEffect } from 'react';
import { getAlerts, getAreas } from '../services/api';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Loader } from '../components/ui/Loader';
import { ErrorState, EmptyState } from '../components/ui/ErrorState';
import { ShieldAlert } from 'lucide-react';

const Alerts = () => {
  const [alerts, setAlerts] = useState([]);
  const [areas, setAreas] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [alertsData, areasData] = await Promise.all([
        getAlerts(),
        getAreas()
      ]);

      setAlerts(alertsData || []);

      if (areasData) {
        const areaMap = {};
        areasData.forEach((a) => {
          areaMap[a.id] = a.name;
        });
        setAreas(areaMap);
      }
    } catch (err) {
      console.error(err);
      setError("Failed to fetch alert center data.");
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

  if (loading) {
    return <Loader message="Syncing alert systems..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={fetchData} />;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ShieldAlert className="w-8 h-8 text-red-500" />
        <h2 className="text-2xl font-bold">System Alert Center</h2>
      </div>

      <Card>
        {alerts.length === 0 ? (
          <EmptyState
            title="System Clear"
            message="No active heatwave alerts are currently recorded."
          />
        ) : (
          <div className="space-y-4">
            {alerts.map((alert) => {
              const severity = alert.level || alert.risk_level || 'INFORMATIONAL';
              const timestamp =
                alert.timestamp ||
                alert.raised_at_utc ||
                new Date().toISOString();

              const isForecast =
                alert.source === 'forecast' ||
                alert.source === 'ml' ||
                String(alert.message || '').toLowerCase().includes('forecast');

              return (
                <div
                  key={alert.alert_id}
                  className={`p-4 rounded-xl border ${
                    severity === 'WARNING'
                      ? 'bg-red-900/20 border-red-500/30'
                      : severity === 'WATCH'
                        ? 'bg-yellow-900/20 border-yellow-500/30'
                        : 'bg-gray-800/50 border-gray-700'
                  } flex flex-col md:flex-row md:items-center justify-between gap-4`}
                >
                  <div className="space-y-2 flex-1">
                    <div className="flex items-center gap-3">
                      <Badge level={severity}>{severity}</Badge>

                      <span className="text-sm font-semibold text-white">
                        {alert.area_id
                          ? (areas[alert.area_id] ||
                            `Area #${alert.area_id}`)
                          : 'Global System'}
                      </span>

                      <span className="text-xs text-gray-500 ml-auto md:ml-0">
                        {new Date(timestamp).toLocaleString()}
                      </span>
                    </div>

                    <p className="text-gray-300">
                      {alert.message}
                    </p>

                    {alert.risk_level && (
                      <p className="text-xs text-gray-500">
                        Risk level: {alert.risk_level}
                        {alert.risk_score !== null &&
                        alert.risk_score !== undefined
                          ? ` • Score: ${alert.risk_score}`
                          : ''}
                      </p>
                    )}
                  </div>

                  {isForecast && (
                    <div className="shrink-0">
                      <span className="px-2 py-1 bg-blue-900/30 text-blue-400 text-xs rounded border border-blue-800/50">
                        FORECAST ALERT
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
};

export default Alerts;
