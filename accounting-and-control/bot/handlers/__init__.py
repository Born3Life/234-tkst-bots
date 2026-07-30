from bot.handlers.coursework import router as coursework_router
from bot.handlers.examiner import router as examiner_router
from bot.handlers.literature import router as literature_router
from bot.handlers.common import router

routers = [coursework_router, examiner_router, literature_router, router]
