import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8000", // your FastAPI backend URL
});

// Attach token automatically if it exists
API.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // For FormData, let axios set Content-Type with boundary automatically
  if (config.data instanceof FormData) {
    // Remove any manually set Content-Type to let axios handle it
    delete config.headers["Content-Type"];
  }
  return config;
});

export default API;
