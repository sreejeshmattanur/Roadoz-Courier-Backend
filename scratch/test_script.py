import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.user_role import UserRole
from app.models.franchise import Franchise
from app.models.pickup_address import PickupAddress
from app.models.consignee import Consignee
from sqlalchemy import select
from app.dependencies.role_checker import get_current_user
import json

async def setup_test_data(db):
    # Check if Super Admin exists, if not create
    role_sa = await db.scalar(select(Role).where(Role.name == "Super Admin"))
    if not role_sa:
        role_sa = Role(id=str(uuid.uuid4()), name="Super Admin")
        db.add(role_sa)
    
    sa = await db.scalar(select(User).join(UserRole, UserRole.user_id == User.id).where(UserRole.role_id == role_sa.id))
    if not sa:
        sa = User(id=str(uuid.uuid4()), name="Super Admin", email="sa@test.com", password_hash="123", phone="123")
        db.add(sa)
        db.add(UserRole(user_id=sa.id, role_id=role_sa.id))
    
    await db.flush()
        
    role_fr = await db.scalar(select(Role).where(Role.name == "Franchise Owner"))
    if not role_fr:
        role_fr = Role(id=str(uuid.uuid4()), name="Franchise Owner")
        db.add(role_fr)
        
    fr = await db.scalar(select(User).where(User.email == "fr@test.com"))
    if not fr:
        fr = User(id=str(uuid.uuid4()), name="Franchise", email="fr@test.com", password_hash="123", phone="123")
        db.add(fr)
        await db.flush()

    franchise = await db.scalar(select(Franchise).where(Franchise.email == "fr@test.com"))
    if not franchise:
        franchise = Franchise(id=str(uuid.uuid4()), user_id=fr.id, name="Test Franchise", email="fr@test.com", phone="123", franchise_code="FR123", pincode="682024")
        db.add(franchise)
        await db.flush()
        
    fr.franchise_id = franchise.id
    # check role first
    role_exists = await db.scalar(select(UserRole).where(UserRole.user_id == fr.id, UserRole.role_id == role_fr.id))
    if not role_exists:
        db.add(UserRole(user_id=fr.id, role_id=role_fr.id))
    await db.flush()

    pickup = await db.scalar(select(PickupAddress).where(PickupAddress.phone == "111111"))
    if not pickup:
        pickup = PickupAddress(id=str(uuid.uuid4()), user_id=sa.id, nickname="Home", contact_name="Test Pickup", phone="111111", email="p@t.com", address_line_1="L1", address_line_2="L2", pincode="682024", city="EKM", state="Kerala")
        db.add(pickup)
        
    consignee = await db.scalar(select(Consignee).where(Consignee.mobile == "222222"))
    if not consignee:
        consignee = Consignee(id=str(uuid.uuid4()), user_id=sa.id, name="Test Consignee", mobile="222222", email="c@t.com", address_line_1="L1", address_line_2="L2", pincode="695014", city="TVM", state="Kerala")
        db.add(consignee)

    await db.commit()
    return sa, fr, pickup, consignee

async def test_apis():
    async with AsyncSessionLocal() as db:
        sa, fr, pickup, consignee = await setup_test_data(db)
        
    transport = ASGITransport(app=app)
    
    print("\n--- Testing Super Admin Order Creation (GST Exempt) ---")
    from app.schemas.order import OrderCreate
    from app.services.order_service import create_order
    from app.services.invoice_service import generate_invoice
    from app.schemas.invoice import InvoiceGenerateRequest
    
    order_data = OrderCreate(**{
        "order_type": "B2C",
        "pickup_address_id": pickup.id,
        "consignee_id": consignee.id,
        "payment_method": "Prepaid",
        "rov": "owner_risk",
        "order_value": 1500,
        "service_type": "Surface",
        "is_gst_exempt": True,
        "items": [
            {"product_name": "Book", "unit_price": 500, "qty": 3, "total": 1500, "package_index": 1}
        ],
        "packages": [
            {"count": 1, "length_cm": 10, "breadth_cm": 10, "height_cm": 10, "physical_weight_kg": 2.5, "vol_weight_kg": 0.2}
        ]
    })
    
    # Needs a real DB session for services
    try:
        sa_order = await create_order(db, order_data, sa)
        print("Super Admin Order created successfully. Total Freight:", sa_order.total_freight, "GST Exempt:", sa_order.freight_gst == 0)
    except Exception as e:
        print("Super Admin Order Creation Failed:", e)

    print("\n--- Testing Franchise Order Creation (Not GST Exempt) ---")
    order_data.is_gst_exempt = False
    try:
        fr_order = await create_order(db, order_data, fr)
        print("Franchise Order created successfully. Total Freight:", fr_order.total_freight, "GST:", fr_order.freight_gst)
    except Exception as e:
        print("Franchise Order Creation Failed:", e)

    print("\n--- Testing Invoice Generation (Super Admin) ---")
    try:
        invoice_payload = InvoiceGenerateRequest(
            franchise_id=fr.franchise_id,
            period_start="2020-01-01",
            period_end="2030-01-01",
            tax_rate=18.0
        )
        invoice = await generate_invoice(db, invoice_payload)
        print("Invoice Generated successfully. Invoice Number:", invoice.invoice_number)
        print("Invoice Total Amount:", invoice.total_amount)
    except Exception as e:
        print("Invoice Generation Failed:", e)

if __name__ == "__main__":
    asyncio.run(test_apis())
