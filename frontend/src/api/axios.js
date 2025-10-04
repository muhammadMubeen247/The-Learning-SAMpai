import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8050", // your FastAPI backend URL
});

// Attach token automatically if it exists
API.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export default API;
