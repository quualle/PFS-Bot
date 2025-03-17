import React, { useState } from 'react';
import {
  Box,
  TextField,
  IconButton,
  Paper,
  useTheme,
  CircularProgress,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import { useChat } from '../../contexts/ChatContext';

const ChatMessageInput: React.FC = () => {
  const { sendMessage, isStreaming } = useChat();
  const [message, setMessage] = useState('');
  const theme = useTheme();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isStreaming) {
      sendMessage(message);
      setMessage('');
    }
  };

  return (
    <Paper
      elevation={3}
      component="form"
      onSubmit={handleSubmit}
      sx={{
        p: 2,
        display: 'flex',
        alignItems: 'center',
        gap: 2,
        borderRadius: 3,
        position: 'sticky',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 10,
        mt: 2,
      }}
    >
      <TextField
        fullWidth
        placeholder="Type your message..."
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        disabled={isStreaming}
        variant="outlined"
        autoComplete="off"
        multiline
        maxRows={4}
        sx={{
          '& .MuiOutlinedInput-root': {
            borderRadius: 3,
          },
        }}
      />
      <Box>
        <IconButton
          color="primary"
          type="submit"
          disabled={!message.trim() || isStreaming}
          sx={{
            bgcolor: message.trim() && !isStreaming ? 'primary.main' : 'action.disabledBackground',
            color: message.trim() && !isStreaming ? 'primary.contrastText' : 'text.disabled',
            '&:hover': {
              bgcolor: message.trim() && !isStreaming ? 'primary.dark' : 'action.disabledBackground',
            },
            width: 48,
            height: 48,
          }}
        >
          {isStreaming ? <CircularProgress size={24} color="inherit" /> : <SendIcon />}
        </IconButton>
      </Box>
    </Paper>
  );
};

export default ChatMessageInput;
