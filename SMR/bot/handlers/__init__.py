from bot.handlers.coursework import router as coursework_router
from bot.handlers.calculator import router as calculator_router
from bot.handlers.common import router

routers = [coursework_router, calculator_router, router]
