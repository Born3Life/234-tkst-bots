from bot.handlers.coursework import router as coursework_router
from bot.handlers.trainer import router as trainer_router
from bot.handlers.literature import router as literature_router
from bot.handlers.common import router

routers = [coursework_router, trainer_router, literature_router, router]
