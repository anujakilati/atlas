import axios from 'axios';

const api = axios.create({ baseURL: 'http://localhost:8000' });

export async function fetchEvents() {
  const res = await api.get('/events/');
  return res.data;
}

export async function deleteEvent(id: number) {
  await api.delete(`/events/${id}`);
}

export default api;
