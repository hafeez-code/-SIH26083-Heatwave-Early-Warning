import React, { useState, useEffect } from 'react';
import { getAreas } from '../services/api';
import { Card } from '../components/ui/Card';
import { Loader } from '../components/ui/Loader';
import { ErrorState, EmptyState } from '../components/ui/ErrorState';
import { useNavigate } from 'react-router-dom';

const AreasList = () => {
  const [areas, setAreas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getAreas();
      setAreas(data || []);
    } catch (err) {
      setError("Failed to fetch areas.");
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
  if (areas.length === 0) return <EmptyState title="No Areas Found" message="Configure areas via the backend." />;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Monitored Areas</h2>
      <div className="grid-3">
        {areas.map(area => (
          <Card key={area.id} className="clickable" title={area.name}>
            <div className="space-y-2 mt-4 text-sm text-gray-300" onClick={() => navigate(`/areas/${area.id}`)}>
              <div className="flex justify-between">
                <span>Latitude:</span>
                <span className="text-white">{area.latitude.toFixed(4)}</span>
              </div>
              <div className="flex justify-between">
                <span>Longitude:</span>
                <span className="text-white">{area.longitude.toFixed(4)}</span>
              </div>
            </div>
            <button 
              onClick={() => navigate(`/areas/${area.id}`)}
              className="mt-4 w-full bg-gray-800 hover:bg-gray-700 text-white py-2 rounded-md transition-colors border border-gray-700"
            >
              View Full Intelligence
            </button>
          </Card>
        ))}
      </div>
    </div>
  );
};

export default AreasList;
