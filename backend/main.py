from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routes.auth import router as auth_router
from routes.upload import router as upload_router
from routes.analysis import router as analysis_router
from routes.reports import router as reports_router
from routes.text_analysis import router as text_analysis_router
from routes.notifications import router as notifications_router
from routes.content import router as content_router
from routes.files import router as files_router
from routes.admin import router as admin_router
from routes.link_analysis import router as link_analysis_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="DeepShield AI",
    description="Forensic-grade deepfake detection platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(analysis_router)
app.include_router(reports_router)
app.include_router(text_analysis_router)
app.include_router(link_analysis_router)
app.include_router(notifications_router)
app.include_router(content_router)
app.include_router(files_router)
app.include_router(admin_router)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "DeepShield AI", "version": "1.0.0"}
