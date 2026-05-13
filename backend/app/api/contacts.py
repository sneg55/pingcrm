from fastapi import APIRouter
from app.api.contacts_routes.taxonomy import router as taxonomy_router
from app.api.contacts_routes.listing import router as listing_router
from app.api.contacts_routes.crud import router as crud_router
from app.api.contacts_routes.duplicates import router as duplicates_router
from app.api.contacts_routes.imports import router as imports_router
from app.api.contacts_routes.sync import router as sync_router
from app.api.contacts_routes.messaging import router as messaging_router
from app.api.contacts_routes.map import router as map_router
from app.api.contacts_routes.enrichment import router as enrichment_router
from app.api.contacts_routes.bulk_ops import router as bulk_ops_router

router = APIRouter()
# CRITICAL: Include order matters — static routes BEFORE parameterized
# taxonomy routes (/tags/*) must come before crud (/{contact_id})
router.include_router(taxonomy_router)
router.include_router(listing_router)
router.include_router(imports_router)
router.include_router(sync_router)
router.include_router(map_router)
router.include_router(bulk_ops_router)
router.include_router(crud_router)
router.include_router(enrichment_router)
router.include_router(duplicates_router)
router.include_router(messaging_router)
