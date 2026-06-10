from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import auth, solicitudes, documentos, homologaciones, catalogos
from app.workers.homologacion_worker import iniciar_worker_en_background
from app.core.database import AsyncSessionLocal
from app.core.seed import seed_catalogos
from app.api.v1 import auth, solicitudes, documentos, homologaciones, catalogos, academico



@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_catalogos(db)
    iniciar_worker_en_background()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(solicitudes.router, prefix="/api/v1")
app.include_router(documentos.router, prefix="/api/v1")
app.include_router(homologaciones.router, prefix="/api/v1")
app.include_router(catalogos.router, prefix="/api/v1")
app.include_router(academico.router, prefix="/api/v1")



@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}