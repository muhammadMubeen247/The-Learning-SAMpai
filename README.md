# The Learning SAMpai

An innovative learning platform built with FastAPI and React.

## Project Structure

- `backend/`: FastAPI application
  - `app/`: Main application code
    - `models/`: Database models
    - `routes/`: API endpoints
    - `schemas/`: Pydantic schemas
    - `utils/`: Utility functions
- `frontend/`: React application
  - `src/`: Source code
    - `components/`: React components
    - `pages/`: Page components
    - `api/`: API integration

## Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Features

- User authentication
- Classroom management
- Interactive learning interface