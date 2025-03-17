import React, { useState } from 'react';
import {
  Box,
  Button,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
  useTheme,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Typography
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import StorageIcon from '@mui/icons-material/Storage';
import { useChat } from '../../contexts/ChatContext';

const ChatControls: React.FC = () => {
  const { clearMessages } = useChat();
  const [clearDialogOpen, setClearDialogOpen] = useState(false);
  const [dataSource, setDataSource] = useState('json');
  const theme = useTheme();

  const handleClearChat = () => {
    clearMessages();
    setClearDialogOpen(false);
  };

  return (
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 2,
        mb: 3,
      }}
    >
      <FormControl component="fieldset">
        <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5 }}>
          Data Source
        </Typography>
        <RadioGroup
          row
          name="data-source"
          value={dataSource}
          onChange={(e) => setDataSource(e.target.value)}
        >
          <FormControlLabel 
            value="json" 
            control={<Radio color="primary" size="small" />} 
            label={
              <Typography variant="body2">JSON Database</Typography>
            } 
          />
          <FormControlLabel 
            value="vector" 
            control={<Radio color="primary" size="small" />} 
            label={
              <Typography variant="body2">Vector Database</Typography>
            } 
          />
        </RadioGroup>
      </FormControl>

      <Box>
        <Tooltip title="Clear chat history">
          <Button
            variant="outlined"
            color="error"
            startIcon={<DeleteIcon />}
            onClick={() => setClearDialogOpen(true)}
            size="small"
          >
            Clear Chat
          </Button>
        </Tooltip>
      </Box>

      <Dialog
        open={clearDialogOpen}
        onClose={() => setClearDialogOpen(false)}
      >
        <DialogTitle>Clear Chat History</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to clear the entire chat history? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setClearDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleClearChat} color="error" variant="contained">
            Clear
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ChatControls;