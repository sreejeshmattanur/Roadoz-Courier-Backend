import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Numeric, Integer, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from enum import Enum
from sqlalchemy import Enum as SqlEnum




class OrderStatus(str, Enum):
    PROCESSING = "Processing"
    MANIFESTED = "Manifested"
    IN_TRANSIT = "In_transit"
    NDR = "Ndr"
    OFD = "Ofd"
    DELIVERED = "Delivered"
    RTO_IN_TRANSIT = "Rto_in_transit"
    RTO_DELIVERED = "Rto_delivered"
    RETURNED = "Returned"
    CANCELLED = "Cancelled"
    LOST = "Lost"
    PICKED = "Picked"           
    DISPATCHED = "Dispatched" 

class BulkOrder(Base):
    __tablename__ = "bulk_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    pickup_address_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pickup_addresses.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="Processing")
    total_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_orders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    franchise_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), onupdate=datetime.utcnow
    )

    orders = relationship("Order", back_populates="bulk_order", lazy="selectin")

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    bulk_order_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bulk_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)

    # B2C | B2B | International
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Pickup & Delivery
    pickup_address_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pickup_addresses.id", ondelete="RESTRICT"), nullable=False
    )
    consignee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("consignees.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_addresses_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("warehouse_addresses.id", ondelete="RESTRICT"), nullable=True
    )
    # Payment
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False)  # COD | Prepaid | To Pay
    cod_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # required when COD
    to_pay_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # required when To Pay
    rov: Mapped[str] = mapped_column(String(20), nullable=False)  # owner_risk | carrier_risk

    # Product summary
    order_value: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # Package summary (computed at creation)
    total_weight_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    total_vol_weight_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    applicable_weight_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default=text("0"))
    total_boxes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    # Shipping charge (debited from wallet)
    shipping_charge: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, server_default=text("0"))

    # Other details
    gst_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    eway_bill_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Barcode (base64 PNG)
    barcode: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status
    # status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'pending'"))
    status: Mapped[OrderStatus] = mapped_column(
                SqlEnum(OrderStatus),
                nullable=False,
                default=OrderStatus.PROCESSING
            )

    # Ownership
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    franchise_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    # Relationships
    bulk_order = relationship("BulkOrder", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    packages = relationship("OrderPackage", back_populates="order", cascade="all, delete-orphan", lazy="selectin")
    pickup_address = relationship("PickupAddress", lazy="selectin")
    consignee = relationship("Consignee", lazy="selectin")
    warehouseaddress = relationship("WareHouseAddress", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    order = relationship("Order", back_populates="items")


class OrderPackage(Base):
    __tablename__ = "order_packages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    length_cm: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    breadth_cm: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    height_cm: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    vol_weight_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    physical_weight_kg: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    order = relationship("Order", back_populates="packages")



 

class ConsigneeToDelivery(Base):
    __tablename__ = "consigneestodelivery"

    id = Column(Integer, primary_key=True, index=True)
    pincode = Column(String(10), nullable=False)
    status = Column(String(20), default="pending")

    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"))
    consignee_id = Column(String(36), ForeignKey("consignees.id", ondelete="CASCADE"))

    order = relationship("Order", backref="consignees_to_delivery")
    consignee = relationship("Consignee", backref="consignees_to_delivery")
    
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True) 
    
    created_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)

    
class PickupToConsignees(Base):
    __tablename__ = "pickupstoconsignees"

    id = Column(Integer, primary_key=True, index=True)
    pincode = Column(String(10), nullable=False)
    status = Column(String(20), default="pending")

    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"))
    pickup_addresses_id = Column(String(36), ForeignKey("pickup_addresses.id", ondelete="CASCADE"))

    order = relationship("Order", backref="pickup_to_consignees")
    pickup_address = relationship("PickupAddress", backref="pickup_to_consignees") 
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True) 
    created_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)
 
    
    
class WarehouseToDelivery(Base):
    __tablename__ = "warehousetodelivery"

    id = Column(Integer, primary_key=True, index=True)
    pincode = Column(String(10), nullable=False)
    status = Column(String(20), default="pending")

    order_id = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"))
    warehouse_addresses_id = Column(String(36), ForeignKey("warehouse_addresses.id", ondelete="CASCADE"))

    order = relationship("Order", backref="warehouse_to_delivery")
    warehouse_address = relationship("WareHouseAddress", backref="warehouse_to_delivery") 
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True) 
    created_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime,default=datetime.utcnow,onupdate=datetime.utcnow,nullable=False)
    
