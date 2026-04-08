from __future__ import annotations

from dataclasses import dataclass, field

from ...contracts import utc_now_iso


@dataclass(slots=True)
class ProductMasterRow:
    row_number: int
    product_key: str
    active: bool
    product_name: str
    category: str
    brand: str
    wb_nm_id: int | None = None
    wb_vendor_code: str = ""
    site_product_id: int | None = None
    site_offer_id: int | None = None
    pack_type: str = ""
    pack_weight_g: float | None = None
    length_cm: float | None = None
    width_cm: float | None = None
    height_cm: float | None = None
    purchase_cost_rub: float | None = None
    packaging_cost_rub: float | None = None
    other_unit_cost_rub: float | None = None
    manual_site_price: float | None = None
    manual_wb_price: float | None = None
    manual_ad_pct_cap: float | None = None
    tax_profile: str = ""
    notes: str = ""

    @property
    def unit_cost_rub(self) -> float:
        return (
            (self.purchase_cost_rub or 0.0)
            + (self.packaging_cost_rub or 0.0)
            + (self.other_unit_cost_rub or 0.0)
        )


@dataclass(slots=True)
class WbRawRow:
    product_key: str
    fetched_at: str
    nm_id: int | None = None
    vendor_code: str = ""
    title: str = ""
    brand: str = ""
    subject_name: str = ""
    current_price_rub: float | None = None
    discounted_price_rub: float | None = None
    club_discounted_price_rub: float | None = None
    discount_pct: float | None = None
    stocks_qty: float | None = None
    sales_30d_units: float | None = None
    orders_30d_units: float | None = None
    revenue_30d_rub: float | None = None
    promos_count: int | None = None
    error: str = ""


@dataclass(slots=True)
class SiteRawRow:
    product_key: str
    fetched_at: str
    product_id: int | None = None
    offer_id: int | None = None
    art_no: str = ""
    title: str = ""
    category_name: str = ""
    enabled: bool | None = None
    current_price_rub: float | None = None
    old_price_rub: float | None = None
    discounted_price_rub: float | None = None
    stock_qty: float | None = None
    orders_30d_units: float | None = None
    revenue_30d_rub: float | None = None
    error: str = ""


@dataclass(slots=True)
class CalculatedEconomicsRow:
    product_key: str
    product_name: str
    channel: str
    active: bool
    base_cost_rub: float
    target_price_rub: float | None
    live_price_rub: float | None
    discounted_price_rub: float | None
    commission_rub: float
    logistics_rub: float
    returns_rub: float
    ads_rub: float
    taxes_rub: float
    net_payout_rub: float
    profit_rub: float
    margin_pct: float | None
    roi_pct: float | None
    price_gap_rub: float | None
    sales_30d_units: float | None
    revenue_30d_rub: float | None
    stocks_qty: float | None
    issue_flags: str = ""
    data_status: str = "ok"
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class ActionRow:
    priority: int
    severity: str
    product_key: str
    product_name: str
    channel: str
    action_type: str
    headline: str
    details: str
    suggested_action: str
    metric_value: float | None = None
    metric_context: str = ""
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class SyncStatus:
    scope: str
    status: str
    started_at: str
    finished_at: str
    spreadsheet_id: str
    rows_written: int
    message: str
    error_count: int = 0
