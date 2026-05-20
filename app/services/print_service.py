from datetime import date, datetime
from html import escape
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.franchise import Franchise
from app.models.invoice import Invoice
from app.models.order import Order, OrderStatus
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole


COMPANY_NAME = "Roadoz Courier & Cargo"
COMPANY_ADDRESS = "Roadoz Courier & Cargo Management System"
COMPANY_GSTIN = "GSTIN: Not Configured"


def _money(value: Any) -> str:
    return f"{float(value or 0):.2f}"


def _text(value: Any) -> str:
    return escape("" if value is None else str(value))


def _date(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")
    return str(value)


def _status_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


async def _get_caller_role_name(db: AsyncSession, user_id: str) -> str | None:
    row = await db.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    role = row.scalar_one_or_none()
    return role.lower() if role else None


async def _resolve_franchise_id(db: AsyncSession, user: User) -> str | None:
    if user.franchise_id:
        return user.franchise_id
    result = await db.execute(select(Franchise).where(Franchise.user_id == user.id))
    franchise = result.scalar_one_or_none()
    return franchise.id if franchise else None


async def _assert_order_access(db: AsyncSession, current_user: User, order: Order) -> None:
    if await _get_caller_role_name(db, current_user.id) == "super_admin":
        return
    franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id and order.franchise_id == franchise_id:
        return
    if order.created_by == current_user.id:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _assert_invoice_access(db: AsyncSession, current_user: User, invoice: Invoice) -> None:
    if await _get_caller_role_name(db, current_user.id) == "super_admin":
        return
    franchise_id = await _resolve_franchise_id(db, current_user)
    if invoice.franchise_id != franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


async def _scoped_franchise_id(db: AsyncSession, current_user: User, franchise_id: str | None) -> str | None:
    if await _get_caller_role_name(db, current_user.id) == "super_admin":
        return franchise_id
    own_franchise_id = await _resolve_franchise_id(db, current_user)
    if franchise_id and own_franchise_id and franchise_id != own_franchise_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return own_franchise_id


async def _get_order(db: AsyncSession, current_user: User, order_id: str) -> Order:
    order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    await _assert_order_access(db, current_user, order)
    return order


async def _get_invoice(db: AsyncSession, current_user: User, invoice_id: str) -> Invoice:
    invoice = (await db.execute(select(Invoice).where(Invoice.id == invoice_id))).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    await _assert_invoice_access(db, current_user, invoice)
    return invoice


def _base_html(title: str, body: str, page_size: str = "A4") -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{_text(title)}</title>
  <style>
    @page {{ size: {page_size}; margin: 12mm; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, sans-serif; color: #111; font-size: 12px; }}
    .page {{ width: 100%; }}
    .header {{ display: flex; justify-content: space-between; gap: 16px; border-bottom: 2px solid #111; padding-bottom: 10px; margin-bottom: 12px; }}
    .brand {{ font-size: 22px; font-weight: 800; letter-spacing: 0; }}
    .muted {{ color: #555; }}
    .box {{ border: 1px solid #222; padding: 10px; margin-bottom: 10px; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .grid-3 {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }}
    .label {{ font-size: 10px; color: #555; text-transform: uppercase; }}
    .value {{ font-size: 13px; font-weight: 700; margin-top: 2px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    th, td {{ border: 1px solid #222; padding: 6px; text-align: left; vertical-align: top; }}
    th {{ background: #f2f2f2; }}
    .right {{ text-align: right; }}
    .center {{ text-align: center; }}
    .barcode {{ max-width: 240px; max-height: 90px; }}
    .signature {{ height: 54px; border-top: 1px solid #222; padding-top: 6px; margin-top: 42px; }}
    .print-actions {{ margin: 12px 0; }}
    .print-actions button {{ padding: 8px 12px; border: 1px solid #111; background: #fff; cursor: pointer; }}
    @media print {{ .print-actions {{ display: none; }} body {{ print-color-adjust: exact; }} }}
  </style>
</head>
<body>
  <div class="print-actions"><button onclick="window.print()">Print</button></div>
  {body}
</body>
</html>"""


def _company_header(title: str, right: str = "") -> str:
    return f"""
<div class="header">
  <div>
    <div class="brand">{COMPANY_NAME}</div>
    <div class="muted">{COMPANY_ADDRESS}</div>
    <div class="muted">{COMPANY_GSTIN}</div>
  </div>
  <div class="right">
    <div class="value">{_text(title)}</div>
    <div>{right}</div>
  </div>
</div>"""


def _address_block(title: str, name: str, phone: str, address: str, city: str, state: str, pincode: str) -> str:
    return f"""
<div class="box">
  <div class="label">{_text(title)}</div>
  <div class="value">{_text(name)}</div>
  <div>{_text(phone)}</div>
  <div>{_text(address)}</div>
  <div>{_text(city)}, {_text(state)} - {_text(pincode)}</div>
</div>"""


async def awb_print_html(db: AsyncSession, current_user: User, order_id: str) -> str:
    order = await _get_order(db, current_user, order_id)
    pickup = order.pickup_address
    consignee = order.consignee
    barcode = f'<img class="barcode" src="data:image/png;base64,{order.barcode}" alt="AWB barcode">' if order.barcode else ""
    body = f"""
<div class="page">
  {_company_header("AWB / Consignment Note", f"AWB: <strong>{_text(order.order_number)}</strong>")}
  <div class="box center">{barcode}<div class="value">{_text(order.order_number)}</div></div>
  <div class="grid-2">
    {_address_block("Sender", pickup.contact_name if pickup else "", pickup.phone if pickup else "", pickup.address_line_1 if pickup else "", pickup.city if pickup else "", pickup.state if pickup else "", pickup.pincode if pickup else "")}
    {_address_block("Receiver", consignee.name if consignee else "", consignee.mobile if consignee else "", consignee.address_line_1 if consignee else "", consignee.city if consignee else "", consignee.state if consignee else "", consignee.pincode if consignee else "")}
  </div>
  <div class="box">
    <div class="grid-3">
      <div><div class="label">Booking Date</div><div class="value">{_date(order.created_at)}</div></div>
      <div><div class="label">Weight</div><div class="value">{_money(order.applicable_weight_kg)} kg</div></div>
      <div><div class="label">Pieces</div><div class="value">{_text(order.total_boxes)}</div></div>
      <div><div class="label">Service Type</div><div class="value">{_text(order.order_type)}</div></div>
      <div><div class="label">Payment Type</div><div class="value">{_text(order.payment_method)}</div></div>
      <div><div class="label">Status</div><div class="value">{_text(_status_value(order.status))}</div></div>
    </div>
  </div>
  <table>
    <tr><th>Freight</th><th>GST Included</th><th>Total</th></tr>
    <tr><td>{_money(order.shipping_charge)}</td><td>Yes</td><td>{_money(order.shipping_charge)}</td></tr>
  </table>
  <div class="grid-2">
    <div class="signature">Sender Signature</div>
    <div class="signature">Office Signature</div>
  </div>
</div>"""
    return _base_html(f"AWB {order.order_number}", body, "A4")


async def shipping_label_html(db: AsyncSession, current_user: User, order_id: str) -> str:
    order = await _get_order(db, current_user, order_id)
    consignee = order.consignee
    barcode = f'<img class="barcode" src="data:image/png;base64,{order.barcode}" alt="AWB barcode">' if order.barcode else ""
    body = f"""
<div class="page">
  <style>
    @page {{ size: 4in 6in; margin: 6mm; }}
    body {{ font-size: 14px; }}
    .label-wrap {{ border: 2px solid #111; padding: 10px; min-height: 5.55in; }}
    .big {{ font-size: 22px; font-weight: 800; }}
    .addr {{ font-size: 16px; line-height: 1.35; margin-top: 10px; }}
  </style>
  <div class="label-wrap">
    <div class="brand">{COMPANY_NAME}</div>
    <div class="center">{barcode}<div class="big">{_text(order.order_number)}</div></div>
    <hr>
    <div class="label">Deliver To</div>
    <div class="big">{_text(consignee.name if consignee else "")}</div>
    <div class="addr">{_text(consignee.address_line_1 if consignee else "")}<br>{_text(consignee.city if consignee else "")}, {_text(consignee.state if consignee else "")} - {_text(consignee.pincode if consignee else "")}</div>
    <div class="value">Phone: {_text(consignee.mobile if consignee else "")}</div>
    <div class="grid-2">
      <div><div class="label">Weight</div><div class="value">{_money(order.applicable_weight_kg)} kg</div></div>
      <div><div class="label">Payment</div><div class="value">{_text(order.payment_method)}</div></div>
    </div>
  </div>
</div>"""
    return _base_html(f"Label {order.order_number}", body, "4in 6in")


async def invoice_print_html(db: AsyncSession, current_user: User, invoice_id: str) -> str:
    invoice = await _get_invoice(db, current_user, invoice_id)
    rows = ""
    for item in invoice.invoice_orders:
        order = item.order
        rows += f"""
<tr>
  <td>{_text(order.order_number if order else item.order_id)}</td>
  <td>{_date(order.created_at if order else item.created_at)}</td>
  <td>{_text(order.consignee.name if order and order.consignee else "")}</td>
  <td class="right">{_money(item.shipping_charge)}</td>
</tr>"""
    body = f"""
<div class="page">
  {_company_header("Customer Invoice", f"Invoice: <strong>{_text(invoice.invoice_number)}</strong>")}
  <div class="grid-2">
    <div class="box">
      <div class="label">Bill To</div>
      <div class="value">{_text(invoice.franchise.name if invoice.franchise else invoice.franchise_id)}</div>
      <div>{_text(invoice.franchise.address if invoice.franchise else "")}</div>
      <div>{_text(invoice.franchise.phone if invoice.franchise else "")}</div>
    </div>
    <div class="box">
      <div><span class="label">Invoice Date</span><div class="value">{_date(invoice.created_at)}</div></div>
      <div><span class="label">Period</span><div class="value">{_date(invoice.period_start)} to {_date(invoice.period_end)}</div></div>
      <div><span class="label">Status</span><div class="value">{_text(invoice.status)}</div></div>
    </div>
  </div>
  <table>
    <tr><th>AWB No</th><th>Date</th><th>Customer</th><th class="right">Amount</th></tr>
    {rows}
  </table>
  <table>
    <tr><th class="right">Taxable Amount</th><td class="right">{_money(invoice.subtotal)}</td></tr>
    <tr><th class="right">GST ({_money(invoice.tax_rate)}%)</th><td class="right">{_money(invoice.tax_amount)}</td></tr>
    <tr><th class="right">Total Amount</th><td class="right"><strong>{_money(invoice.total_amount)}</strong></td></tr>
  </table>
  <div class="signature right">Authorized Signatory</div>
</div>"""
    return _base_html(f"Invoice {invoice.invoice_number}", body, "A4")


async def daily_booking_print_html(
    db: AsyncSession,
    current_user: User,
    report_date: date | None = None,
    franchise_id: str | None = None,
) -> str:
    target_date = report_date or date.today()
    scoped_franchise_id = await _scoped_franchise_id(db, current_user, franchise_id)
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())
    filters = [Order.created_at >= start, Order.created_at <= end]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
    orders = (await db.execute(select(Order).where(and_(*filters)).order_by(Order.created_at.asc()))).scalars().all()
    rows = "".join(
        f"<tr><td>{_text(order.order_number)}</td><td>{_text(order.consignee.name if order.consignee else '')}</td><td>{_text(order.consignee.city if order.consignee else '')}</td><td>{_money(order.applicable_weight_kg)}</td><td class='right'>{_money(order.shipping_charge)}</td></tr>"
        for order in orders
    )
    body = f"""
<div class="page">
  {_company_header("Daily Booking Report", f"Date: <strong>{_date(target_date)}</strong>")}
  <table>
    <tr><th>AWB</th><th>Customer</th><th>Destination</th><th>Weight</th><th class="right">Amount</th></tr>
    {rows}
  </table>
  <div class="box right"><strong>Total: {_money(sum(float(order.shipping_charge or 0) for order in orders))}</strong></div>
</div>"""
    return _base_html("Daily Booking Report", body, "A4")


async def delivery_run_sheet_html(
    db: AsyncSession,
    current_user: User,
    run_date: date | None = None,
    franchise_id: str | None = None,
) -> str:
    target_date = run_date or date.today()
    scoped_franchise_id = await _scoped_franchise_id(db, current_user, franchise_id)
    filters = [Order.status.notin_([OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.LOST])]
    if scoped_franchise_id:
        filters.append(Order.franchise_id == scoped_franchise_id)
    orders = (await db.execute(select(Order).where(and_(*filters)).order_by(Order.created_at.asc()))).scalars().all()
    rows = "".join(
        f"<tr><td>{_text(order.order_number)}</td><td>{_text(order.consignee.name if order.consignee else '')}</td><td>{_text(order.consignee.address_line_1 if order.consignee else '')}</td><td>{_text(order.consignee.mobile if order.consignee else '')}</td><td>{_text(_status_value(order.status))}</td><td></td></tr>"
        for order in orders
    )
    body = f"""
<div class="page">
  {_company_header("Delivery Run Sheet", f"Date: <strong>{_date(target_date)}</strong>")}
  <div class="grid-2">
    <div class="box"><div class="label">Delivery Staff</div><div class="signature"></div></div>
    <div class="box"><div class="label">Route / Area</div><div class="signature"></div></div>
  </div>
  <table>
    <tr><th>AWB</th><th>Customer</th><th>Address</th><th>Phone</th><th>Status</th><th>Signature / Remarks</th></tr>
    {rows}
  </table>
</div>"""
    return _base_html("Delivery Run Sheet", body, "A4")
