import os
from dotenv import load_dotenv
from fastapi import FastAPI
from app.routes import auth,classroom,folder,file
from app.database.init_db import init_db
from fastapi.middleware.cors import CORSMiddleware


load_dotenv()  # Load environment variables from a .env file if present

app = FastAPI(title="Learning Platform API")

origins = [
    "http://localhost:5173", 
    "http://localhost:3000", 
    "http://127.0.0.1:5173", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    init_db()  

app.include_router(auth.router)
app.include_router(classroom.router)
app.include_router(folder.router)
app.include_router(file.router)

@app.get("/")
def root():
    return {"msg": "Hello from FastAPI"}
