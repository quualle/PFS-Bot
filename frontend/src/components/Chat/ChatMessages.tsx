import React, { useRef, useEffect } from 'react';
import { Box, Typography, CircularProgress, Alert } from '@mui/material';
import { useChat } from '../../contexts/ChatContext';
import ChatMessage from './ChatMessage';

const ChatMessages: React.FC = () => {
  const { messages, isLoading, error, isStreaming } = useChat();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages come in
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  if (isLoading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100%',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        <CircularProgress />
        <Typography variant="body2" color="text.secondary">
          Loading conversation...
        </Typography>
      </Box>
    );
  }

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        flexGrow: 1,
        pb: 2,
      }}
    >
      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {messages.length === 0 ? (
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            height: '100%',
            flexDirection: 'column',
            gap: 2,
            opacity: 0.7,
          }}
        >
          <Typography variant="h6" color="text.secondary">
            Start a conversation with XORA
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Ask a question about care stays, agencies, or customer details
          </Typography>
        </Box>
      ) : (
        <>
          {messages.map((message, index) => (
            <ChatMessage key={message.id} message={message} index={index} />
          ))}
        </>
      )}

      {isStreaming && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mt: 1,
          }}
        >
          <CircularProgress size={16} />
          <Typography variant="caption" color="text.secondary">
            XORA is responding...
          </Typography>
        </Box>
      )}

      <div ref={messagesEndRef} />
    </Box>
  );
};

export default ChatMessages;
