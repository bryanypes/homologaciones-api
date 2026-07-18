from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1 import auth, solicitudes, documentos, homologaciones, catalogos, academico, usuarios
from app.core.database import AsyncSessionLocal
from app.core.seed import seed_catalogos, crear_usuario_inicial


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_catalogos(db)
        await crear_usuario_inicial(db)
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
app.include_router(usuarios.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}