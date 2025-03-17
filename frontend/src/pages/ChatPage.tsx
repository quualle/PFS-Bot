import React, { useEffect } from 'react';
import { Box, Paper, Typography, useTheme, useMediaQuery } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { motion } from 'framer-motion';

// Components
import ChatMessages from '../components/Chat/ChatMessages';
import ChatMessageInput from '../components/Chat/ChatMessageInput';
import NotfallModeToggle from '../components/Chat/NotfallModeToggle';
import ChatControls from '../components/Chat/ChatControls';

const ChatPage: React.FC = () => {
  const { user, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, isLoading, navigate]);

  if (isLoading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '80vh',
        }}
      >
        <Typography>Loading...</Typography>
      </Box>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          height: 'calc(100vh - 120px)', // Adjust for header and padding
          gap: 3,
        }}
      >
        <Box sx={{ mb: 2 }}>
          <Typography variant="h4" gutterBottom>
            Chat with XORA
          </Typography>
          <Typography variant="subtitle1" color="text.secondary">
            Ask questions about care stays, agencies, or customer details
          </Typography>
        </Box>

        <NotfallModeToggle />
        
        <ChatControls />

        <Paper 
          elevation={3} 
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            p: 3,
            borderRadius: 4,
            backgroundColor: theme.palette.background.paper,
          }}
        >
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              flex: 1,
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            <Box
              sx={{
                flex: 1,
                overflowY: 'auto',
                pr: 1,
                mr: -1, // Compensate for padding to avoid double scrollbars
              }}
            >
              <ChatMessages />
            </Box>
            
            <ChatMessageInput />
          </Box>
        </Paper>
        
        <Typography variant="caption" color="text.secondary" sx={{ mt: 1, textAlign: 'center' }}>
          XORA Chatbot Version 2.0 | Developed by XORA Team
        </Typography>
      </Box>
    </motion.div>
  );
};

export default ChatPage;
