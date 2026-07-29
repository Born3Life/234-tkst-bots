from bot.handlers.coursework import router as coursework_router
from bot.handlers.drawing_check import router as drawing_check_router
from bot.handlers.common import router

routers = [coursework_router, drawing_check_router, router]
