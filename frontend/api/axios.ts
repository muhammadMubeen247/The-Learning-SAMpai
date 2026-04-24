import axios from "axios";

const API = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

// Attach token and log request
API.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  // For FormData, let axios set Content-Type with boundary automatically
  if (config.data instanceof FormData) {
    delete config.headers["Content-Type"];
  }
  // Record request start time for elapsed logging
  (config as any)._requestStart = Date.now();
  console.log(`[API →] ${config.method?.toUpperCase()} ${config.url}`);
  return config;
});

// Log response or error
API.interceptors.response.use(
  (response) => {
    const elapsed = Date.now() - ((response.config as any)._requestStart || Date.now());
    console.log(
      `[API ✓] ${response.config.method?.toUpperCase()} ${response.config.url} ${response.status} (${elapsed}ms)`
    );
    return response;
  },
  (error) => {
    const elapsed = Date.now() - ((error.config as any)?._requestStart || Date.now());
    console.log(
      `[API ✗] ${error.config?.method?.toUpperCase()} ${error.config?.url} ${error.response?.status ?? "ERR"} (${elapsed}ms)`
    );
    if (error.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default API;
