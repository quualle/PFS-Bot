# XORA PFS Bot

A chatbot application for Pflegehilfe für Senioren (PFS), providing assistance with customer information, care stays, and agency details.

## New Design Version 2.0

This repository contains a completely redesigned version of the PFS Bot, featuring:

- Modern React frontend with TypeScript
- Material UI components for a clean, responsive interface
- Dark/light theme support
- Enhanced chat capabilities with streaming responses
- Better error handling and user feedback
- Full context management with React Hooks

## Project Structure

```
/
├── frontend/            # React frontend application
│   ├── public/          # Static assets
│   └── src/             # React source code
│       ├── components/  # UI components
│       ├── contexts/    # React contexts
│       ├── hooks/       # Custom hooks
│       ├── pages/       # Page components
│       ├── services/    # API services
│       ├── styles/      # CSS styles
│       └── types/       # TypeScript types
│
├── backend/             # Flask backend application
│   ├── api/             # API routes
│   ├── static/          # Static files for Flask
│   └── templates/       # Template files for Flask
└── original/            # Original application code (for reference)
```

## Getting Started

### Prerequisites

- Node.js (>= 14.x)
- npm (>= 7.x)
- Python (>= 3.9)
- pip

### Installation

1. Clone the repository

```bash
git clone https://github.com/your-organization/pfs-bot.git
cd pfs-bot
```

2. Install frontend dependencies

```bash
cd frontend
npm install
```

3. Install backend dependencies

```bash
cd ../backend
pip install -r requirements.txt
```

### Running the Application

#### Development Mode

To run both frontend and backend in development mode:

```bash
npm run dev
```

This will start:
- Frontend development server on http://localhost:3000
- Backend API server on http://localhost:5000

#### Production Mode

To build and run the application in production mode:

```bash
npm run build
npm start
```

This will:
1. Build the React frontend
2. Start the Flask server which will serve both the API and the built frontend

## Features

- **Authentication**: Simple user authentication and admin authentication
- **Chat Interface**: Modern chat interface with streaming responses
- **Emergency Mode**: Special handling for emergency inquiries
- **Feedback System**: Allow users to rate responses and provide feedback
- **Admin Panel**: Admin interface for managing knowledge base and users
- **Dark/Light Theme**: Support for user preference on theme
- **Mobile Responsive**: Fully responsive design for all device sizes

## License

Private - All rights reserved

## Contact

For any questions or support, please contact the XORA team.
