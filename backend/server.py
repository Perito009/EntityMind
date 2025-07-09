from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect, File, UploadFile
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import json
import cv2
import numpy as np
import hashlib
import base64
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
import logging
from sklearn.metrics.pairwise import cosine_similarity
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/entitymind")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))
ANONYMIZATION_SALT = os.getenv("ANONYMIZATION_SALT", "your-anonymization-salt")
FACE_RECOGNITION_THRESHOLD = float(os.getenv("FACE_RECOGNITION_THRESHOLD", "0.6"))

# Initialize FastAPI app
app = FastAPI(title="Entity Mind API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# Global variables
mongo_client = None
redis_client = None
face_cascade = None
executor = ThreadPoolExecutor(max_workers=4)

# Pydantic models
class UserBase(BaseModel):
    username: str
    email: str
    role: str = "viewer"  # "admin" or "viewer"
    is_active: bool = True

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class PeopleCount(BaseModel):
    count: int
    timestamp: datetime
    zone_id: str = "default"
    anonymized_faces: List[str] = []

class FaceEmbedding(BaseModel):
    embedding_hash: str
    first_seen: datetime
    last_seen: datetime
    count: int = 1

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# Database initialization
async def init_db():
    global mongo_client, redis_client
    try:
        mongo_client = AsyncIOMotorClient(MONGO_URL)
        redis_client = redis.from_url(REDIS_URL)
        
        # Test connections
        await mongo_client.admin.command('ping')
        await redis_client.ping()
        
        # Create default admin user
        db = mongo_client.entitymind
        admin_exists = await db.users.find_one({"username": "admin"})
        if not admin_exists:
            hashed_password = pwd_context.hash("admin123")
            await db.users.insert_one({
                "id": str(uuid.uuid4()),
                "username": "admin",
                "email": "admin@entitymind.com",
                "password": hashed_password,
                "role": "admin",
                "is_active": True,
                "created_at": datetime.utcnow()
            })
        
        # Initialize Redis with default count
        await redis_client.set("current_count", "0")
        
        logger.info("Database connections initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

# Facial recognition initialization
async def init_face_recognition():
    global face_cascade
    try:
        # Initialize OpenCV face cascade
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        logger.info("Face recognition initialized with OpenCV")
    except Exception as e:
        logger.error(f"Face recognition initialization failed: {e}")

# Utility functions
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def anonymize_face_embedding(face_data):
    """Create anonymized hash from face data"""
    face_str = str(face_data)
    salted_face = f"{face_str}{ANONYMIZATION_SALT}"
    return hashlib.sha256(salted_face.encode()).hexdigest()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    db = mongo_client.entitymind
    user = await db.users.find_one({"username": username})
    if user is None:
        raise credentials_exception
    return user

def require_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

# Face processing functions
async def process_frame_for_faces(frame):
    """Process a single frame to detect faces"""
    try:
        # Convert frame to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(gray, 1.1, 4)
        
        face_data = []
        for (x, y, w, h) in faces:
            # Extract face region
            face_region = gray[y:y+h, x:x+w]
            
            # Create a simple face descriptor using histogram
            face_descriptor = cv2.calcHist([face_region], [0], None, [256], [0, 256])
            face_descriptor = face_descriptor.flatten()
            
            # Anonymize the face data
            anonymized_hash = anonymize_face_embedding(face_descriptor.tolist())
            
            face_data.append({
                "hash": anonymized_hash,
                "bbox": [int(x), int(y), int(w), int(h)],
                "confidence": 0.8  # Mock confidence score
            })
        
        return face_data
    except Exception as e:
        logger.error(f"Frame processing error: {e}")
        return []

async def update_face_database(face_data):
    """Update face database with new face detections"""
    try:
        db = mongo_client.entitymind
        current_time = datetime.utcnow()
        
        for face in face_data:
            face_hash = face["hash"]
            
            # Check if face already exists
            existing_face = await db.face_embeddings.find_one({"embedding_hash": face_hash})
            
            if existing_face:
                # Update existing face
                await db.face_embeddings.update_one(
                    {"embedding_hash": face_hash},
                    {
                        "$set": {"last_seen": current_time},
                        "$inc": {"count": 1}
                    }
                )
            else:
                # Create new face entry
                await db.face_embeddings.insert_one({
                    "embedding_hash": face_hash,
                    "first_seen": current_time,
                    "last_seen": current_time,
                    "count": 1
                })
        
        # Update current count
        unique_faces = len(face_data)
        await redis_client.set("current_count", str(unique_faces))
        
        # Store historical data
        await db.people_counts.insert_one({
            "count": unique_faces,
            "timestamp": current_time,
            "zone_id": "default",
            "anonymized_faces": [face["hash"] for face in face_data]
        })
        
        # Broadcast to WebSocket clients
        await manager.broadcast(json.dumps({
            "count": unique_faces,
            "timestamp": current_time.isoformat()
        }))
        
        return unique_faces
    except Exception as e:
        logger.error(f"Face database update error: {e}")
        return 0

# API Routes
@app.on_event("startup")
async def startup_event():
    await init_db()
    await init_face_recognition()

@app.on_event("shutdown")
async def shutdown_event():
    if mongo_client:
        mongo_client.close()
    if redis_client:
        await redis_client.close()

@app.post("/api/auth/login", response_model=Token)
async def login(username: str, password: str):
    db = mongo_client.entitymind
    user = await db.users.find_one({"username": username})
    
    if not user or not verify_password(password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/users/me", response_model=UserResponse)
async def read_users_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"]
    )

@app.get("/api/count/current")
async def get_current_count(current_user: dict = Depends(get_current_user)):
    """Get current people count"""
    try:
        # Get current count from Redis
        current_count = await redis_client.get("current_count")
        if current_count is None:
            current_count = 0
        else:
            current_count = int(current_count)
        
        return {"count": current_count, "timestamp": datetime.utcnow()}
    except Exception as e:
        logger.error(f"Error getting current count: {e}")
        return {"count": 0, "timestamp": datetime.utcnow()}

@app.get("/api/count/history")
async def get_count_history(current_user: dict = Depends(get_current_user)):
    """Get historical count data"""
    try:
        db = mongo_client.entitymind
        
        # Get last 24 hours of data
        since = datetime.utcnow() - timedelta(hours=24)
        history = await db.people_counts.find(
            {"timestamp": {"$gte": since}}
        ).sort("timestamp", -1).limit(100).to_list(100)
        
        return {"history": history}
    except Exception as e:
        logger.error(f"Error getting count history: {e}")
        return {"history": []}

@app.post("/api/process/frame")
async def process_frame(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """Process an uploaded frame for facial recognition"""
    try:
        # Read uploaded file
        contents = await file.read()
        
        # Convert to OpenCV format
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image format")
        
        # Process frame for faces
        face_data = await process_frame_for_faces(frame)
        
        # Update database
        count = await update_face_database(face_data)
        
        return {
            "status": "processed",
            "faces_detected": len(face_data),
            "current_count": count,
            "faces": face_data
        }
    except Exception as e:
        logger.error(f"Frame processing error: {e}")
        raise HTTPException(status_code=500, detail="Frame processing failed")

@app.post("/api/simulate/count")
async def simulate_count(count: int, current_user: dict = Depends(get_current_user)):
    """Simulate people count for testing (MVP feature)"""
    try:
        # Update Redis
        await redis_client.set("current_count", str(count))
        
        # Store in database
        db = mongo_client.entitymind
        await db.people_counts.insert_one({
            "count": count,
            "timestamp": datetime.utcnow(),
            "zone_id": "default",
            "anonymized_faces": [f"simulated_{i}" for i in range(count)]
        })
        
        # Broadcast to WebSocket clients
        await manager.broadcast(json.dumps({
            "count": count,
            "timestamp": datetime.utcnow().isoformat()
        }))
        
        return {"status": "success", "count": count}
    except Exception as e:
        logger.error(f"Simulation error: {e}")
        raise HTTPException(status_code=500, detail="Simulation failed")

@app.websocket("/ws/live-count")
async def websocket_live_count(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send current count every 2 seconds
            current_count = await redis_client.get("current_count")
            if current_count is None:
                current_count = 0
            else:
                current_count = int(current_count)
            
            await websocket.send_text(json.dumps({
                "count": current_count,
                "timestamp": datetime.utcnow().isoformat()
            }))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)