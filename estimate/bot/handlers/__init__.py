from bot.handlers.coursework import router as coursework_router
from bot.handlers.trainer import router as trainer_router
from bot.handlers.common import router

routers = [coursework_router, trainer_router, router]
