from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...config import Settings
from ...contracts import Artifact, artifact_from_path
from ...integrations.wildberries import build_wildberries_client
from .cabinet_monitor import CabinetMonitorConfig, CabinetMonitorResult, build_cabinet_monitor
from .sample_data import SampleWildberriesClient
from .sku_diagnostic import SkuDiagnosticConfig, build_sku_diagnostic
from .supply_planner import SupplyPlanConfig, build_supply_plan
from .tnved_ui_catalog import TnvedUiCatalogConfig, build_tnved_ui_catalog


@dataclass(slots=True)
class MarketplaceWatchArtifacts:
    markdown: Artifact
    summary_markdown: Artifact
    dashboard_html: Artifact
    workbook: Artifact


class MarketplaceService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run_watch(self, *, top_limit: int = 25, sample_data: bool = False, today: date | None = None) -> tuple[CabinetMonitorResult, MarketplaceWatchArtifacts]:
        output_root = self.settings.marketplace_artifact_root
        output_root.mkdir(parents=True, exist_ok=True)
        client = SampleWildberriesClient() if sample_data else build_wildberries_client(self.settings)
        result = build_cabinet_monitor(
            client,
            CabinetMonitorConfig(output_root=output_root, top_limit=top_limit),
            today=today,
        )
        return result, MarketplaceWatchArtifacts(
            markdown=artifact_from_path(result.markdown_path, "markdown", "Cabinet monitor"),
            summary_markdown=artifact_from_path(result.summary_markdown_path, "markdown", "Cabinet summary"),
            dashboard_html=artifact_from_path(result.dashboard_html_path, "html", "Cabinet dashboard"),
            workbook=artifact_from_path(result.xlsx_path, "xlsx", "Cabinet workbook"),
        )

    def run_sku_diagnostic(self, *, nm_id: int, sample_data: bool = False, today: date | None = None):
        output_root = self.settings.marketplace_artifact_root
        output_root.mkdir(parents=True, exist_ok=True)
        client = SampleWildberriesClient() if sample_data else build_wildberries_client(self.settings)
        return build_sku_diagnostic(
            client,
            SkuDiagnosticConfig(nm_id=nm_id, output_root=output_root),
            today=today,
        )

    def run_supply_plan(self, *, date_from: str, sample_data: bool = False, today: date | None = None):
        output_root = self.settings.marketplace_artifact_root
        output_root.mkdir(parents=True, exist_ok=True)
        client = SampleWildberriesClient() if sample_data else build_wildberries_client(self.settings)
        return build_supply_plan(
            client,
            SupplyPlanConfig(date_from=date_from, output_root=output_root),
            today=today,
        )

    def run_wb_tnved_ui_catalog(self, *, today: date | None = None):
        output_root = (self.settings.project_root / "generated" / "marketplace").resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        client = build_wildberries_client(self.settings)
        return build_tnved_ui_catalog(
            client,
            TnvedUiCatalogConfig(
                output_root=output_root,
                browser_user_data_dir=self.settings.wb_ui_browser_user_data_dir,
                browser_profile_directory=self.settings.wb_ui_browser_profile_directory,
                browser_channel=self.settings.wb_ui_browser_channel,
                browser_executable_path=self.settings.wb_ui_browser_executable_path,
                browser_cdp_url=self.settings.wb_ui_browser_cdp_url,
                seller_url=self.settings.wb_ui_seller_url,
                card_url_template=self.settings.wb_ui_card_url_template,
            ),
            today=today,
        )
