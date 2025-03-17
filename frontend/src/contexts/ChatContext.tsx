import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from './AuthContext';

export interface Message {
  id: string;
  role: 'user' | 'bot';
  content: string;
  timestamp: Date;
  feedback?: 'positive' | 'negative' | null;
}

interface ChatContextType {
  messages: Message[];
  isStreaming: boolean;
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => Promise<void>;
  provideMessageFeedback: (messageId: string, feedbackType: 'positive' | 'negative', comment?: string) => Promise<void>;
  notfallMode: boolean;
  toggleNotfallMode: () => void;
}

const ChatContext = createContext<ChatContextType>({
  messages: [],
  isStreaming: false,
  isLoading: false,
  error: null,
  sendMessage: async () => {},
  clearMessages: async () => {},
  provideMessageFeedback: async () => {},
  notfallMode: false,
  toggleNotfallMode: () => {},
});

export const useChat = () => useContext(ChatContext);

export const ChatProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notfallMode, setNotfallMode] = useState(false);
  const { user } = useAuth();

  // Load chat history when user is authenticated
  useEffect(() => {
    if (user) {
      const loadChatHistory = async () => {
        try {
          setIsLoading(true);
          const response = await axios.get('/api/chat/history');
          
          if (response.data.history && Array.isArray(response.data.history)) {
            const formattedMessages = response.data.history.map((msg: any, index: number) => ({
              id: `history-${index}`,
              role: msg.role || (msg.user ? 'user' : 'bot'),
              content: msg.content || msg.user || msg.bot || '',
              timestamp: new Date(msg.timestamp || Date.now()),
              feedback: msg.feedback || null,
            }));
            
            setMessages(formattedMessages);
          }
        } catch (error) {
          console.error('Error loading chat history:', error);
          setError('Failed to load chat history.');
        } finally {
          setIsLoading(false);
        }
      };

      loadChatHistory();
    }
  }, [user]);

  // Function to handle streaming responses from the API
  const handleStreamedResponse = async (userMessage: string, controller: AbortController) => {
    const msgId = Date.now().toString();
    
    // Add user message immediately
    const userMsg: Message = {
      id: `user-${msgId}`,
      role: 'user',
      content: userMessage,
      timestamp: new Date(),
    };
    
    // Add a placeholder for the bot's message
    const botMsg: Message = {
      id: `bot-${msgId}`,
      role: 'bot',
      content: '',
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, userMsg, botMsg]);
    
    try {
      setIsStreaming(true);
      const response = await fetch('/api/chat/message', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
          'Accept': 'text/event-stream',
        },
        body: JSON.stringify({
          message: userMessage,
          notfallmodus: notfallMode ? '1' : '0',
          stream: true,
        }),
        signal: controller.signal,
      });
      
      if (!response.ok || !response.body) {
        throw new Error('Network response was not ok');
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let responseText = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        
        // Parse SSE events
        const events = chunk.split('\\n\\n');
        for (const event of events) {
          if (event.startsWith('data:')) {
            try {
              const data = JSON.parse(event.substring(5).trim());
              if (data.type === 'text' && data.content) {
                responseText += data.content;
                // Update bot message content as it streams in
                setMessages(prev => 
                  prev.map(msg => 
                    msg.id === botMsg.id 
                      ? { ...msg, content: responseText } 
                      : msg
                  )
                );
              }
            } catch (e) {
              console.error('Error parsing SSE event:', e);
            }
          }
        }
      }
      
      // Ensure complete message is set in state
      setMessages(prev => 
        prev.map(msg => 
          msg.id === botMsg.id 
            ? { ...msg, content: responseText } 
            : msg
        )
      );
      
    } catch (error) {
      if ((error as Error).name !== 'AbortError') {
        console.error('Error in streaming request:', error);
        setError('Failed to get response from the bot. Please try again.');
        
        // Show error message in the bot response
        setMessages(prev => 
          prev.map(msg => 
            msg.id === botMsg.id 
              ? { ...msg, content: 'Sorry, I encountered an error while processing your request. Please try again.' } 
              : msg
          )
        );
      }
    } finally {
      setIsStreaming(false);
    }
  };

  // Function to send a message to the bot
  const sendMessage = async (content: string) => {
    if (!content.trim() || isStreaming) return;
    
    setError(null);
    const controller = new AbortController();
    
    await handleStreamedResponse(content, controller);
  };

  // Function to clear all messages
  const clearMessages = async () => {
    try {
      setIsLoading(true);
      await axios.post('/api/chat/clear');
      setMessages([]);
    } catch (error) {
      console.error('Error clearing messages:', error);
      setError('Failed to clear messages. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  // Function to provide feedback on a message
  const provideMessageFeedback = async (messageId: string, feedbackType: 'positive' | 'negative', comment?: string) => {
    try {
      await axios.post('/api/feedback', {
        message_id: messageId,
        feedback_type: feedbackType,
        comment: comment || '',
      });
      
      // Update message with feedback in state
      setMessages(prev => 
        prev.map(msg => 
          msg.id === messageId 
            ? { ...msg, feedback: feedbackType } 
            : msg
        )
      );
    } catch (error) {
      console.error('Error sending feedback:', error);
      setError('Failed to send feedback. Please try again.');
    }
  };

  // Function to toggle notfall mode
  const toggleNotfallMode = () => {
    setNotfallMode(prev => !prev);
  };

  return (
    <ChatContext.Provider
      value={{
        messages,
        isStreaming,
        isLoading,
        error,
        sendMessage,
        clearMessages,
        provideMessageFeedback,
        notfallMode,
        toggleNotfallMode,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
};