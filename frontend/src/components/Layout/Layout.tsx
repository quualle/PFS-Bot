import React from 'react';
import { Outlet } from 'react-router-dom';
import { Box, Container, useMediaQuery } from '@mui/material';
import { useTheme as useMuiTheme } from '@mui/material/styles';
import Header from './Header';
import Sidebar from './Sidebar';
import { useAuth } from '../../contexts/AuthContext';
import { useTheme } from '../../contexts/ThemeContext';

const Layout: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const { mode } = useTheme();
  const muiTheme = useMuiTheme();
  const isMobile = useMediaQuery(muiTheme.breakpoints.down('md'));
  const [sidebarOpen, setSidebarOpen] = React.useState(!isMobile);

  const toggleSidebar = () => {
    setSidebarOpen(!sidebarOpen);
  };

  // Close sidebar by default on mobile
  React.useEffect(() => {
    setSidebarOpen(!isMobile);
  }, [isMobile]);

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: '100vh',
        bgcolor: 'background.default',
        color: 'text.primary',
        transition: 'all 0.3s ease',
      }}
    >
      <Header toggleSidebar={toggleSidebar} sidebarOpen={sidebarOpen} />
      
      <Box
        sx={{
          display: 'flex',
          flex: 1,
          transition: 'all 0.3s ease',
        }}
      >
        {isAuthenticated && (
          <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        )}
        
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            p: 3,
            pt: 10, // Add padding to account for the fixed header
            transition: 'all 0.3s ease',
            ml: isAuthenticated && sidebarOpen && !isMobile ? '240px' : 0,
            width: isAuthenticated && sidebarOpen && !isMobile ? 'calc(100% - 240px)' : '100%',
          }}
        >
          <Container maxWidth="xl" sx={{ height: '100%' }}>
            <Outlet />
          </Container>
        </Box>
      </Box>
    </Box>
  );
};

export default Layout;
