from app.api.app_factory import create_app
from app.api.routes.public_home import router as public_home_router

app = create_app()
app.include_router(public_home_router)
