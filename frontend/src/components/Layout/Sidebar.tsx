import React from 'react';
import {
  Drawer,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Box,
  IconButton,
  useTheme as useMuiTheme,
  useMediaQuery,
} from '@mui/material';
import { Link, useLocation } from 'react-router-dom';
import ChatIcon from '@mui/icons-material/Chat';
import SettingsIcon from '@mui/icons-material/Settings';
import AdminPanelSettingsIcon from '@mui/icons-material/AdminPanelSettings';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import { useAuth } from '../../contexts/AuthContext';

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

const Sidebar: React.FC<SidebarProps> = ({ open, onClose }) => {
  const { user } = useAuth();
  const location = useLocation();
  const muiTheme = useMuiTheme();
  const isMobile = useMediaQuery(muiTheme.breakpoints.down('md'));

  const drawerWidth = 240;

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  return (
    <Drawer
      variant={isMobile ? 'temporary' : 'persistent'}
      open={open}
      onClose={onClose}
      sx={{
        width: drawerWidth,
        flexShrink: 0,
        '& .MuiDrawer-paper': {
          width: drawerWidth,
          boxSizing: 'border-box',
          borderRight: '1px solid',
          borderColor: 'divider',
          pt: 8, // Space for the app bar
        },
      }}
    >
      {isMobile && (
        <Box sx={{ display: 'flex', alignItems: 'center', p: 1 }}>
          <IconButton onClick={onClose}>
            <ChevronLeftIcon />
          </IconButton>
        </Box>
      )}
      
      <List component="nav">
        <ListItem
          button
          component={Link}
          to="/chat"
          selected={isActive('/chat')}
          onClick={isMobile ? onClose : undefined}
        >
          <ListItemIcon>
            <ChatIcon color={isActive('/chat') ? 'primary' : undefined} />
          </ListItemIcon>
          <ListItemText primary="Chat with XORA" />
        </ListItem>
        
        {user?.role === 'admin' && (
          <>
            <Divider sx={{ my: 1 }} />
            <ListItem
              button
              component={Link}
              to="/admin"
              selected={isActive('/admin')}
              onClick={isMobile ? onClose : undefined}
            >
              <ListItemIcon>
                <AdminPanelSettingsIcon color={isActive('/admin') ? 'primary' : undefined} />
              </ListItemIcon>
              <ListItemText primary="Admin Panel" />
            </ListItem>
          </>
        )}
      </List>
    </Drawer>
  );
};

export default Sidebar;
