from bot.handlers.coursework import router as coursework_router
from bot.handlers.drawing_check import router as drawing_check_router
from bot.handlers.calculator import router as calculator_router
from bot.handlers.literature import router as literature_router
from bot.handlers.common import router

routers = [coursework_router, drawing_check_router, calculator_router, literature_router, router]
