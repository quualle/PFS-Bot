import React from 'react';
import { Box, Typography, Button, Paper } from '@mui/material';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

const NotFoundPage: React.FC = () => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: 'calc(100vh - 160px)',
        }}
      >
        <Paper
          elevation={3}
          sx={{
            textAlign: 'center',
            p: 5,
            maxWidth: 500,
            borderRadius: 4,
          }}
        >
          <motion.div
            initial={{ scale: 0.5 }}
            animate={{ scale: 1 }}
            transition={{ duration: 0.3, delay: 0.2 }}
          >
            <ErrorOutlineIcon color="error" sx={{ fontSize: 100, mb: 2 }} />
          </motion.div>
          
          <Typography variant="h3" component="h1" gutterBottom>
            404
          </Typography>
          
          <Typography variant="h5" gutterBottom>
            Page Not Found
          </Typography>
          
          <Typography color="text.secondary" paragraph sx={{ mb: 3 }}>
            Sorry, the page you are looking for does not exist or has been moved.
          </Typography>
          
          <Button
            component={Link}
            to="/"
            variant="contained"
            color="primary"
            size="large"
          >
            Back to Home
          </Button>
        </Paper>
      </Box>
    </motion.div>
  );
};

export default NotFoundPage;
