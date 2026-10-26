from .routes import router
from .groundmovement import router as ground_movement_router

router.include_router(ground_movement_router)
