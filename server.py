from app.api.app_factory import create_app
from app.api.routes.public_home import router as public_home_router
from app.api.routes.universal_deals import router as universal_deals_router

app = create_app()
app.include_router(public_home_router)
app.include_router(universal_deals_router)
