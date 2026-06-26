import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Import Base and all models so Alembic detects them
from app.core.database import Base
from app.models.user import User       # noqa: F401
from app.models.franchise import Franchise  # noqa: F401
from app.models.franchise_code_counter import FranchiseCodeCounter  # noqa: F401
from app.models.role import Role  # noqa: F401
from app.models.permission import Permission  # noqa: F401
from app.models.role_permission import RolePermission  # noqa: F401
from app.models.user_role import UserRole  # noqa: F401
from app.models.order import Order, BulkOrder, OrderItem, OrderPackage, ConsigneeToDelivery, PickupToConsignees, WarehouseToDelivery
from app.models.pickup_address import PickupAddress
from app.models.consignee import Consignee
from app.models.warehouse import WareHouseAddress
from app.models.activity_log import ActivityLog
from app.models.remittance import Remittance, RemittanceOrder
from app.models.invoice import Invoice, InvoiceOrder
from app.models.orderreview import OrderReview
from app.core.config import settings
from app.models.consigeeauth import AuthUser,AuthUserProfile
from app.models.consigeereview import ProductReview
from app.models.user_franchise import FranchiseApplicationbyUser
from app.models.projectreview import ProjectReview
from app.models.user_admincommunication import AdminandUserMessage
from app.models.warehouse import OrderWarehouseAddress
from app.models.webconfiguration import WebConfiguration


config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
