import React, { useState } from 'react';
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Button,
  useTheme,
} from '@mui/material';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import { useChat, Message } from '../../contexts/ChatContext';
import { motion } from 'framer-motion';

interface ChatMessageProps {
  message: Message;
  index: number;
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message, index }) => {
  const theme = useTheme();
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackType, setFeedbackType] = useState<'positive' | 'negative' | null>(null);
  const [comment, setComment] = useState('');
  const { provideMessageFeedback } = useChat();

  const handleFeedback = (type: 'positive' | 'negative') => {
    setFeedbackType(type);
    setFeedbackOpen(true);
  };

  const handleSubmitFeedback = () => {
    if (feedbackType) {
      provideMessageFeedback(message.id, feedbackType, comment);
      setFeedbackOpen(false);
      setComment('');
    }
  };

  const isBot = message.role === 'bot';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ 
        duration: 0.3, 
        delay: index * 0.1 > 0.5 ? 0.5 : index * 0.1, // Cap delay at 0.5s for long chats
      }}
    >
      <Box
        sx={{
          display: 'flex',
          justifyContent: isBot ? 'flex-start' : 'flex-end',
          mb: 2,
          maxWidth: '100%',
        }}
      >
        <Paper
          elevation={1}
          sx={{
            p: 2,
            maxWidth: { xs: '85%', md: '70%' },
            borderRadius: 3,
            borderBottomLeftRadius: isBot ? 0 : 3,
            borderBottomRightRadius: isBot ? 3 : 0,
            bgcolor: isBot ? 'background.paper' : 'primary.main',
            color: isBot ? 'text.primary' : 'primary.contrastText',
            position: 'relative',
            wordBreak: 'break-word',
            '&:hover .feedback-buttons': {
              opacity: 1,
            },
          }}
        >
          <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
            {isBot ? 'XORA' : 'You'}
          </Typography>
          
          <Typography variant="body1" component="div">
            {message.content}
          </Typography>
          
          {isBot && (
            <Box
              className="feedback-buttons"
              sx={{
                position: 'absolute',
                bottom: 2,
                right: 2,
                opacity: 0,
                transition: 'opacity 0.2s ease-in-out',
                display: 'flex',
                gap: 0.5,
              }}
            >
              <IconButton 
                size="small" 
                onClick={() => handleFeedback('positive')}
                color={message.feedback === 'positive' ? 'success' : 'default'}
              >
                <ThumbUpIcon fontSize="small" />
              </IconButton>
              <IconButton 
                size="small" 
                onClick={() => handleFeedback('negative')}
                color={message.feedback === 'negative' ? 'error' : 'default'}
              >
                <ThumbDownIcon fontSize="small" />
              </IconButton>
            </Box>
          )}
        </Paper>
      </Box>

      <Dialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)}>
        <DialogTitle>
          {feedbackType === 'positive' ? 'Positive Feedback' : 'Negative Feedback'}
        </DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="feedback-comment"
            label="Additional comments (optional)"
            fullWidth
            multiline
            rows={4}
            variant="outlined"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFeedbackOpen(false)}>Cancel</Button>
          <Button onClick={handleSubmitFeedback} variant="contained" color="primary">
            Submit Feedback
          </Button>
        </DialogActions>
      </Dialog>
    </motion.div>
  );
};

export default ChatMessage;
