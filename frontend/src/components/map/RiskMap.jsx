import React, { useEffect } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useNavigate } from 'react-router-dom';
import { Badge } from '../ui/Badge';

// Fix Leaflet's default icon path issues in React
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Map component bounds updater
const MapBounds = ({ areas }) => {
  const map = useMap();
  useEffect(() => {
    if (areas && areas.length > 0) {
      const bounds = L.latLngBounds(areas.map(a => [a.latitude, a.longitude]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 10 });
    }
  }, [areas, map]);
  return null;
};

// Create custom markers based on risk level
const createCustomIcon = (level) => {
  let color = '#10B981'; // normal
  if (level === 'WATCH') color = '#F59E0B';
  if (level === 'WARNING' || level === 'HIGH') color = '#F97316';
  if (level === 'CRITICAL' || level === 'EXTREME') color = '#EF4444';

  const svgIcon = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="${color}" width="32" height="32" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path>
      <circle cx="12" cy="10" r="3" fill="white"></circle>
    </svg>`;

  return L.divIcon({
    className: 'custom-leaflet-icon',
    html: svgIcon,
    iconSize: [32, 32],
    iconAnchor: [16, 32],
    popupAnchor: [0, -32]
  });
};

export const RiskMap = ({ areas = [], onAreaClick }) => {
  const navigate = useNavigate();

  const handlePopupClick = (id) => {
    if (onAreaClick) {
      onAreaClick(id);
    } else {
      navigate(`/areas/${id}`);
    }
  };

  return (
    <div className="h-[500px] w-full rounded-xl overflow-hidden border border-gray-700 shadow-lg relative z-0">
      <MapContainer 
        center={[20.5937, 78.9629]} // Default to India center
        zoom={4} 
        style={{ height: '100%', width: '100%', backgroundColor: '#0B101E' }}
        attributionControl={false}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />
        <MapBounds areas={areas} />
        
        {areas.map((area) => (
          <Marker 
            key={area.id} 
            position={[area.latitude, area.longitude]}
            icon={createCustomIcon(area.riskLevel)}
          >
            <Popup className="custom-popup">
              <div className="p-2 min-w-[200px]">
                <h3 className="font-bold text-lg mb-2 text-white border-b border-gray-700 pb-1">{area.name}</h3>
                <div className="space-y-2 text-sm text-gray-300">
                  <div className="flex justify-between items-center">
                    <span>Overall Status:</span>
                    <Badge level={area.riskLevel}>{area.riskLevel || 'UNKNOWN'}</Badge>
                  </div>
                  {area.temperature && (
                    <div className="flex justify-between">
                      <span>Temperature:</span>
                      <span className="font-semibold text-white">{area.temperature}°C</span>
                    </div>
                  )}
                  {area.heatwaveRisk && (
                    <div className="flex justify-between">
                      <span>Heat Risk:</span>
                      <span className="text-white">{area.heatwaveRisk}</span>
                    </div>
                  )}
                </div>
                <button 
                  onClick={() => handlePopupClick(area.id)}
                  className="mt-4 w-full bg-blue-600 hover:bg-blue-700 text-white py-1.5 rounded-md transition-colors"
                >
                  View Intelligence
                </button>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
};
