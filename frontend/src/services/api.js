import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000/api',
});

// Generic response unwrapper
const unwrap = (response) => response.data.data;

export const getAreas = () => api.get('/areas').then(unwrap);
export const getArea = (id) => api.get(`/areas/${id}`).then(unwrap);
export const getAreaDemographics = (id) => api.get(`/areas/${id}/demographics`).then(unwrap);
export const getEarlyWarning = (id) => api.get(`/areas/${id}/early-warning`).then(unwrap);
export const getWeatherHistory = (id) => api.get(`/weather`, { params: { area_id: id } }).then(unwrap);
export const getForecast = (id, stored = false) => api.get(`/weather/forecast`, { params: { area_id: id, stored } }).then(unwrap);
export const getRiskForecast = (id) => api.get(`/risk/forecast`, { params: { area_id: id } }).then(unwrap);
export const getAlerts = () => api.get('/alerts').then(unwrap);

// Export singleton
export default api;
