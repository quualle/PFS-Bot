import api from './api';

export interface User {
  id: string;
  name: string;
  email?: string;
  role?: string;
}

export interface AuthResponse {
  user: User;
  token?: string;
  success: boolean;
  message?: string;
}

// Check authentication status
export const checkAuthStatus = async (): Promise<AuthResponse> => {
  const response = await api.get('/auth/status');
  return response.data;
};

// Regular user login (name-only)
export const loginUser = async (username: string): Promise<AuthResponse> => {
  const response = await api.post('/auth/login', { username });
  return response.data;
};

// Admin login with credentials
export const loginAdmin = async (email: string, password: string): Promise<AuthResponse> => {
  const response = await api.post('/auth/admin-login', { email, password });
  return response.data;
};

// Logout user
export const logoutUser = async (): Promise<{ success: boolean; message?: string }> => {
  const response = await api.post('/auth/logout');
  return response.data;
};
