import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from "axios";

export interface ApiResponse<T> {
  data: T;
  error: string | null;
  meta?: {
    total: number;
    page: number;
    page_size: number;
    total_pages: number;
  };
}

const apiClient = axios.create({
  baseURL: "/api/v1",
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token =
    typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("access_token");
        // Redirect to login unless already on an auth page
        if (!window.location.pathname.startsWith("/auth")) {
          window.location.href = "/auth/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

export { apiClient as api };
export default apiClient;
