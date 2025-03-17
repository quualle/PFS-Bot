import React, { useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Tabs,
  Tab,
  CircularProgress,
  Button,
  Alert,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { motion } from 'framer-motion';

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

const TabPanel: React.FC<TabPanelProps> = ({ children, value, index, ...other }) => {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`admin-tabpanel-${index}`}
      aria-labelledby={`admin-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
};

const AdminPage: React.FC = () => {
  const { user, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const [tabValue, setTabValue] = React.useState(0);

  // Redirect if not authenticated or not admin
  useEffect(() => {
    if (!isLoading && (!isAuthenticated || user?.role !== 'admin')) {
      navigate('/login');
    }
  }, [isAuthenticated, isLoading, navigate, user]);

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

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
        <CircularProgress />
      </Box>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" gutterBottom>
          Admin Dashboard
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          Manage knowledge base, users, and system settings
        </Typography>
      </Box>

      <Paper sx={{ width: '100%', mb: 4, borderRadius: 3 }} elevation={3}>
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs
            value={tabValue}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label="Knowledge Base" id="admin-tab-0" aria-controls="admin-tabpanel-0" />
            <Tab label="User Management" id="admin-tab-1" aria-controls="admin-tabpanel-1" />
            <Tab label="Chat Statistics" id="admin-tab-2" aria-controls="admin-tabpanel-2" />
            <Tab label="System Settings" id="admin-tab-3" aria-controls="admin-tabpanel-3" />
          </Tabs>
        </Box>

        <TabPanel value={tabValue} index={0}>
          <Alert severity="info" sx={{ mb: 3 }}>
            This feature is coming soon in a future update.
          </Alert>
          <Typography variant="h6" gutterBottom>
            Knowledge Base Management
          </Typography>
          <Typography paragraph>
            Add, edit, and remove entries from the knowledge base. Organize information into topics
            and subtopics.  This functionality will be implemented in a future update.
          </Typography>
          <Button variant="contained" color="primary" disabled>
            Add New Entry
          </Button>
        </TabPanel>

        <TabPanel value={tabValue} index={1}>
          <Alert severity="info" sx={{ mb: 3 }}>
            This feature is coming soon in a future update.
          </Alert>
          <Typography variant="h6" gutterBottom>
            User Management
          </Typography>
          <Typography paragraph>
            Manage user accounts, roles, and permissions. Admin tools for user activity monitoring
            will be available in a future update.
          </Typography>
        </TabPanel>

        <TabPanel value={tabValue} index={2}>
          <Alert severity="info" sx={{ mb: 3 }}>
            This feature is coming soon in a future update.
          </Alert>
          <Typography variant="h6" gutterBottom>
            Chat Statistics
          </Typography>
          <Typography paragraph>
            View usage statistics, popular topics, and user feedback. Analytics dashboards will be
            available in a future update.
          </Typography>
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
          <Alert severity="info" sx={{ mb: 3 }}>
            This feature is coming soon in a future update.
          </Alert>
          <Typography variant="h6" gutterBottom>
            System Settings
          </Typography>
          <Typography paragraph>
            Configure system behavior, API connections, and notification preferences. Advanced
            settings will be available in a future update.
          </Typography>
        </TabPanel>
      </Paper>
    </motion.div>
  );
};

export default AdminPage;
