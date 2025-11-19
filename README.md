# The Learning SAMpai 

An intelligent learning management system powered by AI and RAG (Retrieval-Augmented Generation) technology. The Learning SAMpai helps students and educators manage classrooms, process educational materials, and engage in AI-assisted learning conversations.

##  Features

- **Classroom Management**: Create and manage virtual classrooms
- **Document Processing**: Upload and process educational materials (PDFs, documents, presentations)
- **AI-Powered Chat**: Engage with course materials through intelligent Q&A powered by RAG
- **Topic Extraction**: Automatically extract and organize topics from uploaded content
- **File Organization**: Organize materials into folders and topics
- **Vector Search**: Semantic search across educational content using ChromaDB
- **Secure Authentication**: JWT-based user authentication and authorization

##  Tech Stack

### Backend
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Vector Store**: ChromaDB for embeddings
- **AI/ML**: OpenAI GPT models
- **Embeddings**: OpenAI text-embedding-ada-002
- **Storage**: Cloudflare R2 for file storage
- **Authentication**: JWT tokens
- **Migrations**: Alembic

### Frontend
- **Framework**: React + Vite
- **Styling**: CSS
- **HTTP Client**: Axios
- **Routing**: React Router (implied from ProtectedRoute)

##  Prerequisites

- Python 3.8+
- Node.js 16+
- PostgreSQL
- Cloudflare R2 account (for file storage)
- OpenAI API key

##  Getting Started

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file with the following variables:
```env
# Database Configuration
DATABASE_URL=postgresql://postgres:password@localhost:5432/Learning_SAMpai_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=Learning_SAMpai_db

# JWT Configuration
SECRET_KEY=your-secret-key

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key
EMBEDDING_MODEL=text-embedding-ada-002

# Cloudflare R2 Configuration
R2_ENDPOINT=your-r2-endpoint
R2_ACCESS_KEY_ID=your-r2-access-key
R2_SECRET_ACCESS_KEY=your-r2-secret-key
R2_BUCKET_NAME=classroom-files

# ChromaDB Configuration
CHROMA_DATA_DIR=./chroma_data
```

5. Run database migrations:
```bash
alembic upgrade head
```

6. Start the backend server:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Create a `.env` file:
```env
VITE_API_URL=http://localhost:8000
```

4. Start the development server:
```bash
npm run dev
```

The frontend will be available at `http://localhost:5173`

## Project Structure

###  Backend
```
backend/
├── app/
│   ├── config/          # Configuration files (ChromaDB, etc.)
│   ├── database/        # Database setup and session management
│   ├── dependencies/    # FastAPI dependencies (auth, etc.)
│   ├── lib/            # External service integrations (R2)
│   ├── models/         # SQLAlchemy models
│   ├── routes/         # API endpoints
│   ├── schemas/        # Pydantic schemas
│   ├── services/       # Business logic (RAG, document processing, etc.)
│   ├── tests/          # Unit tests
│   └── utils/          # Utility functions (JWT, hashing, etc.)
├── migrations/         # Alembic migrations
└── chroma_data/       # ChromaDB vector store data
```

### Frontend
```
frontend/
├── src/
│   ├── api/           # API integration (axios, endpoints)
│   ├── components/    # Reusable React components
│   ├── pages/         # Page components
│   └── assets/        # Static assets
└── public/           # Public assets
```

## API Endpoints

### Authentication
- `POST /auth/signup` - User registration
- `POST /auth/login` - User login

### Classrooms
- `GET /classrooms` - List user's classrooms
- `POST /classrooms` - Create a classroom
- `GET /classrooms/{id}` - Get classroom details

### Files & Folders
- `POST /files/upload` - Upload files
- `GET /folders` - List folders
- `POST /folders` - Create folder

### Chat
- `POST /chat` - Send message and get AI response

## Running Tests

```bash
cd backend
pytest app/tests/
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is part of a Final Year Project (FYP).

## Authors

- Muhammad Mubeen - [@muhammadMubeen247](https://github.com/muhammadMubeen247)

## Acknowledgments

- OpenAI for GPT models and embeddings API
- ChromaDB for vector storage
- FastAPI and React communities
- Cloudflare R2 for object storage