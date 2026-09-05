from fastapi import APIRouter

from app.api import branches, conversations, guest_sessions, messages, projects, workflows

api_router = APIRouter(prefix="/api")
api_router.include_router(guest_sessions.router)
api_router.include_router(projects.router)
api_router.include_router(workflows.router)
api_router.include_router(conversations.router)
api_router.include_router(messages.router)
api_router.include_router(branches.router)
