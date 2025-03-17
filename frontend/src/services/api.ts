import axios from 'axios';

// Create axios instance with default config
const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  },
  withCredentials: true  // Include cookies in requests for session-based auth
});

// Add request interceptor for error handling
api.interceptors.request.use(config => {
  // You can add CSRF token here if needed
  return config;
});

// Add response interceptor for error handling
api.interceptors.response.use(
  response => response,
  error => {
    // Handle common error cases
    if (error.response) {
      // The request was made and the server responded with a status code outside of 2xx range
      if (error.response.status === 401) {
        // Unauthorized - redirect to login page
        window.location.href = '/login';
      }
    } else if (error.request) {
      // The request was made but no response was received
      console.error('Network error, no response received:', error.request);
    } else {
      // Something happened in setting up the request that triggered an Error
      console.error('Error setting up request:', error.message);
    }
    return Promise.reject(error);
  }
);

export default api;
