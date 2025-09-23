from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timedelta, timezone
import jwt
import bcrypt
import aiofiles
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# JWT Configuration
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

# Create the main app
app = FastAPI()

# Create upload directories
upload_dir = Path("uploads")
videos_dir = upload_dir / "videos"
notes_dir = upload_dir / "notes"
thumbnails_dir = upload_dir / "thumbnails"

for directory in [upload_dir, videos_dir, notes_dir, thumbnails_dir]:
    directory.mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")
security = HTTPBearer()

# Enums
class UserRole(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty" 
    ADMIN = "admin"

class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    role: UserRole
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserCreate(BaseModel):
    email: str
    name: str
    password: str
    role: UserRole = UserRole.STUDENT

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    status: UserStatus
    created_at: datetime

class Video(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    filename: str
    original_filename: str
    file_size: int
    duration: Optional[int] = None
    thumbnail_path: Optional[str] = None
    uploaded_by: str  # user_id
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    views: int = 0
    is_active: bool = True

class VideoCreate(BaseModel):
    title: str
    description: str = ""

class VideoResponse(BaseModel):
    id: str
    title: str
    description: str
    filename: str
    original_filename: str
    file_size: int
    duration: Optional[int]
    thumbnail_path: Optional[str]
    uploaded_by: str
    uploader_name: str
    uploaded_at: datetime
    views: int
    is_active: bool

class Note(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    filename: str
    original_filename: str
    file_size: int
    uploaded_by: str  # user_id
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    downloads: int = 0
    is_active: bool = True

class NoteCreate(BaseModel):
    title: str
    description: str = ""

class NoteResponse(BaseModel):
    id: str
    title: str
    description: str
    filename: str
    original_filename: str
    file_size: int
    uploaded_by: str
    uploader_name: str
    uploaded_at: datetime
    downloads: int
    is_active: bool

class Quiz(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    questions: List[Dict[str, Any]] = []
    created_by: str  # user_id
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    time_limit: Optional[int] = None  # minutes

class QuizCreate(BaseModel):
    title: str
    description: str = ""
    questions: List[Dict[str, Any]] = []
    time_limit: Optional[int] = None

class QuizResponse(BaseModel):
    id: str
    title: str
    description: str
    questions: List[Dict[str, Any]]
    created_by: str
    creator_name: str
    created_at: datetime
    is_active: bool
    time_limit: Optional[int]

# Utility Functions
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_current_user(user_id: str = Depends(verify_token)):
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("status") != UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Account is suspended")
    return User(**user)

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# Authentication Routes
@api_router.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate):
    # Check if user already exists
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password
    hashed_password = hash_password(user_data.password)
    
    # Create user
    user = User(
        email=user_data.email,
        name=user_data.name,
        role=user_data.role
    )
    
    user_dict = user.dict()
    user_dict["password"] = hashed_password
    
    await db.users.insert_one(user_dict)
    return UserResponse(**user.dict())

@api_router.post("/auth/login")
async def login(user_data: UserLogin):
    # Find user
    user = await db.users.find_one({"email": user_data.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    if not verify_password(user_data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Check if user is active
    if user.get("status") != UserStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Account is suspended")
    
    # Create access token
    access_token = create_access_token(data={"sub": user["id"]})
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse(**user)
    }

@api_router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    return UserResponse(**current_user.dict())

# Video Routes
@api_router.post("/videos", response_model=VideoResponse)
async def upload_video(
    title: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    # Check user permissions
    if current_user.role not in [UserRole.FACULTY, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only faculty and admin can upload videos")
    
    # Validate file type
    if not file.content_type.startswith('video/'):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = videos_dir / unique_filename
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Create video record
    video = Video(
        title=title,
        description=description,
        filename=unique_filename,
        original_filename=file.filename,
        file_size=len(content),
        uploaded_by=current_user.id
    )
    
    await db.videos.insert_one(video.dict())
    
    # Get uploader info for response
    uploader = await db.users.find_one({"id": current_user.id})
    
    return VideoResponse(
        **video.dict(),
        uploader_name=uploader["name"]
    )

@api_router.get("/videos", response_model=List[VideoResponse])
async def get_videos(current_user: User = Depends(get_current_user)):
    videos = await db.videos.find({"is_active": True}).to_list(1000)
    
    # Get uploader names
    video_responses = []
    for video in videos:
        uploader = await db.users.find_one({"id": video["uploaded_by"]})
        video_responses.append(VideoResponse(
            **video,
            uploader_name=uploader["name"] if uploader else "Unknown"
        ))
    
    return video_responses

@api_router.get("/videos/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str, current_user: User = Depends(get_current_user)):
    video = await db.videos.find_one({"id": video_id, "is_active": True})
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Increment views
    await db.videos.update_one(
        {"id": video_id},
        {"$inc": {"views": 1}}
    )
    video["views"] += 1
    
    # Get uploader info
    uploader = await db.users.find_one({"id": video["uploaded_by"]})
    
    return VideoResponse(
        **video,
        uploader_name=uploader["name"] if uploader else "Unknown"
    )

# Notes Routes
@api_router.post("/notes", response_model=NoteResponse)
async def upload_note(
    title: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    # Check user permissions
    if current_user.role not in [UserRole.FACULTY, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only faculty and admin can upload notes")
    
    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = notes_dir / unique_filename
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    # Create note record
    note = Note(
        title=title,
        description=description,
        filename=unique_filename,
        original_filename=file.filename,
        file_size=len(content),
        uploaded_by=current_user.id
    )
    
    await db.notes.insert_one(note.dict())
    
    # Get uploader info for response
    uploader = await db.users.find_one({"id": current_user.id})
    
    return NoteResponse(
        **note.dict(),
        uploader_name=uploader["name"]
    )

@api_router.get("/notes", response_model=List[NoteResponse])
async def get_notes(current_user: User = Depends(get_current_user)):
    notes = await db.notes.find({"is_active": True}).to_list(1000)
    
    # Get uploader names
    note_responses = []
    for note in notes:
        uploader = await db.users.find_one({"id": note["uploaded_by"]})
        note_responses.append(NoteResponse(
            **note,
            uploader_name=uploader["name"] if uploader else "Unknown"
        ))
    
    return note_responses

# Quiz Routes
@api_router.post("/quizzes", response_model=QuizResponse)
async def create_quiz(
    quiz_data: QuizCreate,
    current_user: User = Depends(get_current_user)
):
    # Check user permissions
    if current_user.role not in [UserRole.FACULTY, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Only faculty and admin can create quizzes")
    
    quiz = Quiz(
        **quiz_data.dict(),
        created_by=current_user.id
    )
    
    await db.quizzes.insert_one(quiz.dict())
    
    return QuizResponse(
        **quiz.dict(),
        creator_name=current_user.name
    )

@api_router.get("/quizzes", response_model=List[QuizResponse])
async def get_quizzes(current_user: User = Depends(get_current_user)):
    quizzes = await db.quizzes.find({"is_active": True}).to_list(1000)
    
    # Get creator names
    quiz_responses = []
    for quiz in quizzes:
        creator = await db.users.find_one({"id": quiz["created_by"]})
        quiz_responses.append(QuizResponse(
            **quiz,
            creator_name=creator["name"] if creator else "Unknown"
        ))
    
    return quiz_responses

# Admin Routes
@api_router.get("/admin/users", response_model=List[UserResponse])
async def get_all_users(current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    users = await db.users.find().to_list(1000)
    return [UserResponse(**user) for user in users]

@api_router.patch("/admin/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    status: UserStatus,
    current_user: User = Depends(get_current_user)
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"message": f"User status updated to {status}"}

# Basic Routes
@api_router.get("/")
async def root():
    return {"message": "YouTube-Style LMS API"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc)}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()