import asyncio
import uuid
from app.core.database import AsyncSessionLocal
import app.main  # Ensure models are loaded
from app.models.role import Role
from sqlalchemy import select

async def seed_warehouse_role():
    async with AsyncSessionLocal() as db:
        role_result = await db.execute(select(Role).where(Role.name == "warehouse"))
        role = role_result.scalar_one_or_none()
        
        if not role:
            print("Warehouse role not found. Creating it...")
            role = Role(id=str(uuid.uuid4()), name="warehouse")
            db.add(role)
            await db.commit()
            print("Successfully created 'warehouse' role.")
        else:
            print("'warehouse' role already exists in the database.")

if __name__ == "__main__":
    asyncio.run(seed_warehouse_role())
