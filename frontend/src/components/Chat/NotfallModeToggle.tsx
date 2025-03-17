import React from 'react';
import {
  Box,
  Button,
  Chip,
  Paper,
  Typography,
  useTheme,
} from '@mui/material';
import WarningIcon from '@mui/icons-material/Warning';
import { useChat } from '../../contexts/ChatContext';
import { motion } from 'framer-motion';

const NotfallModeToggle: React.FC = () => {
  const { notfallMode, toggleNotfallMode } = useChat();
  const theme = useTheme();

  return (
    <Paper
      elevation={3}
      sx={{
        p: 2,
        borderRadius: 3,
        mb: 3,
        border: notfallMode ? `2px solid ${theme.palette.error.main}` : 'none',
        background: notfallMode 
          ? `linear-gradient(135deg, ${theme.palette.error.dark} 0%, ${theme.palette.error.main} 100%)`
          : theme.palette.background.paper,
        transition: 'all 0.3s ease',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <motion.div
            animate={notfallMode ? { rotate: [0, -10, 10, -10, 10, 0] } : {}}
            transition={{ duration: 0.5, repeat: notfallMode ? Infinity : 0, repeatDelay: 2 }}
          >
            <WarningIcon 
              color={notfallMode ? 'inherit' : 'warning'} 
              sx={{ color: notfallMode ? 'white' : undefined }} 
            />
          </motion.div>
          <Typography 
            variant="h6" 
            sx={{ 
              color: notfallMode ? 'white' : 'text.primary',
              fontWeight: notfallMode ? 600 : 500,
            }}
          >
            Emergency Mode
          </Typography>
        </Box>
        
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          {notfallMode && (
            <Chip 
              label="ACTIVE" 
              color="error" 
              sx={{ 
                backgroundColor: 'rgba(255,255,255,0.2)', 
                color: 'white',
                fontWeight: 'bold',
              }} 
            />
          )}
          
          <Button
            variant={notfallMode ? 'contained' : 'outlined'}
            color={notfallMode ? 'inherit' : 'warning'}
            onClick={toggleNotfallMode}
            sx={{
              color: notfallMode ? theme.palette.error.main : undefined,
              borderColor: notfallMode ? 'white' : undefined,
              backgroundColor: notfallMode ? 'white' : undefined,
              '&:hover': {
                backgroundColor: notfallMode ? 'rgba(255,255,255,0.9)' : undefined,
              }
            }}
          >
            {notfallMode ? 'Deactivate Emergency Mode' : 'Activate Emergency Mode'}
          </Button>
        </Box>
      </Box>
      
      {notfallMode && (
        <Box sx={{ mt: 2, color: 'white' }}>
          <Typography variant="body2">
            Emergency mode is active. Your messages will be prioritized and handled with urgency.
          </Typography>
        </Box>
      )}
    </Paper>
  );
};

export default NotfallModeToggle;