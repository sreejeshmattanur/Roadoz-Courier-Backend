from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException
import httpx
from app.models.rate_calculator import PincodeServiceability

async def get_pincode_details(db: AsyncSession, pincode: str) -> PincodeServiceability:
    result = await db.execute(
        select(PincodeServiceability).where(PincodeServiceability.pincode == pincode)
    )
    pc = result.scalar_one_or_none()
    
    if pc:
        if not pc.serviceable:
            raise HTTPException(status_code=400, detail=f"Pincode {pincode} is not serviceable by courier.")
        return pc
        
    # PERFECT SOLUTION: Auto-learning dynamic pincode fetching!
    # If the pincode is not in our DB, we instantly query the Indian Postal API, 
    # learn its State and City, and cache it in our DB permanently!
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"https://api.postalpincode.in/pincode/{pincode}", timeout=5.0)
            data = response.json()
            
            if data and isinstance(data, list) and data[0].get("Status") == "Success":
                post_office = data[0]["PostOffice"][0]
                state = post_office.get("State")
                city = post_office.get("District", post_office.get("Region"))
                
                # Auto-save to our DB for blazing fast future lookups
                new_pc = PincodeServiceability(
                    pincode=pincode,
                    city=city or "Unknown",
                    state=state or "Unknown",
                    serviceable=True
                )
                db.add(new_pc)
                await db.flush()
                return new_pc
    except Exception as e:
        # If the API is down or httpx isn't installed, we can safely ignore the error 
        # and fall through to the manual exception below.
        pass
        
    # If API fails or pincode is genuinely invalid
    raise HTTPException(status_code=400, detail=f"Pincode {pincode} is strictly invalid or not found.")
