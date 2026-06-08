from fastapi import (APIRouter,Depends,HTTPException,)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.webconfiguration import (WebConfiguration,)
from app.schemas.webconfiguration import (WebConfigurationCreate,WebConfigurationPatch,)
from app.dependencies.role_checker import get_current_user, require_permission
from app.models.user import User



router = APIRouter(prefix="/web-config",tags=["Web Configuration"])






@router.post("/create_configration")
async def create_web_configuration(data: WebConfigurationCreate,db: AsyncSession = Depends(get_db),current_user=Depends(get_current_user), _: User = Depends(require_permission("webconfig:edit"))):
    from app.dependencies.role_checker import is_global_user
    if not await is_global_user(db, current_user): 
        raise HTTPException(status_code=403,detail="Only global admins can create config")
    result = await db.execute(select(WebConfiguration))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400,detail="Configuration already exists")
    
    config = WebConfiguration(
        maintenance_mode=data.maintenance_mode,
        allow_order_create=(data.allow_order_create),
        allow_to_pay=data.allow_to_pay,
        app_timezone=data.app_timezone,
        razorpay_key_id=(data.razorpay_key_id),
        razorpay_secret_key=(data.razorpay_secret_key),)
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return {
        "success": True,
        "message": "Web configuration created",
        "data": config
    }
    
    
@router.get("/get_webcongiguration")
async def get_web_configuration(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
    _: User = Depends(require_permission("webconfig:view"))):
    from app.dependencies.role_checker import is_global_user
    if not await is_global_user(db, current_user):
        raise HTTPException(status_code=403,detail="Only global admins can show config")
    result = await db.execute(
        select(WebConfiguration))
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404,detail="Configuration not found")
    return {
        "success": True,"data": config}
    
    
@router.patch("/patch_allwebcongiguration")
async def patch_web_configuration(data: WebConfigurationPatch,db: AsyncSession = Depends(get_db),current_user=Depends(get_current_user), _: User = Depends(require_permission("webconfig:edit"))):
    from app.dependencies.role_checker import is_global_user
    if not await is_global_user(db, current_user):
        raise HTTPException(status_code=403,detail="Only global admins can update")
    result = await db.execute(select(WebConfiguration))
    config = result.scalars().first()
    if not config:
        raise HTTPException(status_code=404,detail="Configuration not found")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    await db.commit()
    await db.refresh(config)
    return {
        "success": True,
        "message": "Configuration updated",
        "data": config
    }        