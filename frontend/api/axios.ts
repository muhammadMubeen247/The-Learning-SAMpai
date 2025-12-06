import axios from "axios";

const API = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

// Attach token automatically if it exists
API.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  // For FormData, let axios set Content-Type with boundary automatically
  if (config.data instanceof FormData) {
    // Remove any manually set Content-Type to let axios handle it
    delete config.headers["Content-Type"];
  }
  return config;
});

// Add response interceptor for better error handling
API.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && typeof window !== "undefined") {
      // Clear auth data on 401
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      // Redirect to login
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default API;
