from app.models.projectreview import ProjectReview
from app.models.rate_calculator import RateZone, RateCard, FuelConfig, GSTConfig, PincodeServiceability
from app.modules.rate_calculator.models.pricing_rule import PricingRule
from app.modules.rate_calculator.models.pricing_zone import PricingZone
from app.models.operations import Expense, CashVoucher, StaffAttendance, Manifest, ManifestOrder, PodRecord

# Import all other models to ensure they are registered in the SQLAlchemy metadata
from app.models import activity_log
from app.models import consigeeauth
from app.models import consigeereview
from app.models import consignee
from app.models import franchise
from app.models import franchise_code_counter
from app.models import invoice
from app.models import kyc
from app.models import notification
from app.models import order
from app.models import orderreview
from app.models import permission
from app.models import pickup_address
from app.models import remittance
from app.models import role
from app.models import role_permission
from app.models import rate_master
from app.models import ticket
from app.models import user
from app.models import user_admincommunication
from app.models import user_role
from app.models import warehouse
from app.models import webconfiguration
