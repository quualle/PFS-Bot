import api from './api';
import { Message } from '../contexts/ChatContext';

export interface ChatHistoryResponse {
  history: Message[];
  success: boolean;
  message?: string;
}

export interface ChatMessageRequest {
  message: string;
  notfallmodus?: string;
  notfallart?: string;
  stream?: boolean;
}

export interface ChatMessageResponse {
  response: string;
  success: boolean;
  message_id?: string;
  error?: string;
}

export interface FeedbackRequest {
  message_id: string;
  feedback_type: 'positive' | 'negative';
  comment?: string;
}

// Get chat history
export const getChatHistory = async (): Promise<ChatHistoryResponse> => {
  const response = await api.get('/chat/history');
  return response.data;
};

// Send a message (non-streaming)
export const sendChatMessage = async (data: ChatMessageRequest): Promise<ChatMessageResponse> => {
  const response = await api.post('/chat/message', data);
  return response.data;
};

// Clear chat history
export const clearChatHistory = async (): Promise<{ success: boolean; message?: string }> => {
  const response = await api.post('/chat/clear');
  return response.data;
};

// Submit feedback for a message
export const submitFeedback = async (data: FeedbackRequest): Promise<{ success: boolean; message?: string }> => {
  const response = await api.post('/feedback', data);
  return response.data;
};
