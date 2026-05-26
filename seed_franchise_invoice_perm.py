import asyncio
from app.core.database import AsyncSessionLocal
import app.main  # Import main to ensure all models and relationships are loaded
from app.models.role import Role
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from sqlalchemy import select
import uuid

async def seed_permission():
    async with AsyncSessionLocal() as db:
        # Find the franchise role
        role_result = await db.execute(select(Role).where(Role.name == "franchise"))
        role = role_result.scalar_one_or_none()
        
        if not role:
            print("Franchise role not found. Creating it...")
            role = Role(id=str(uuid.uuid4()), name="franchise")
            db.add(role)
            await db.flush()

        # Find the invoices:generate permission
        perm_result = await db.execute(select(Permission).where(Permission.code == "invoices:generate"))
        perm = perm_result.scalar_one_or_none()
        
        if not perm:
            print("invoices:generate permission not found. Attempting to create it...")
            perm = Permission(
                id=str(uuid.uuid4()),
                code="invoices:generate",
                module="invoices",
                action="generate",
                description="Admin: generate and manage invoices"
            )
            db.add(perm)
            await db.flush()

        # Check if already assigned
        exists = await db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == perm.id,
            )
        )
        if not exists.scalar_one_or_none():
            db.add(RolePermission(
                id=str(uuid.uuid4()),
                role_id=role.id,
                permission_id=perm.id,
            ))
            await db.commit()
            print("Permission 'invoices:generate' seeded successfully for 'franchise' role.")
        else:
            print("Permission already exists for 'franchise' role.")

if __name__ == "__main__":
    asyncio.run(seed_permission())
