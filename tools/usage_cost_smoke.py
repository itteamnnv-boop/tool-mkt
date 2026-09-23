"""Offline pricing arithmetic and dashboard coverage/refresh checks."""
import os
from pathlib import Path
import sys
import unittest
from decimal import Decimal
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
if sys.platform == "win32":
    os.environ["QT_QPA_FONTDIR"] = "C:/Windows/Fonts"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from app.core.usage_cost import CostEstimate, estimate_cost, summarize_costs
from app.ui.dashboard_tab import DashboardTab


class CostTests(unittest.TestCase):
    def test_text_and_claude_prices(self):
        self.assertEqual(estimate_cost("Grok", "grok-4.7", 1_000_000, 1_000_000).low, Decimal("8"))
        self.assertEqual(estimate_cost("OpenAI", "gpt-5.4", 1_000_000, 1_000_000).low, Decimal("17.5"))
        self.assertEqual(estimate_cost("OpenAI", "gpt-4o-mini", 1_000_000, 1_000_000).low, Decimal("0.75"))
        self.assertEqual(estimate_cost("Claude", "claude-sonnet-5", 1_000_000, 1_000_000).high, Decimal("12"))
        self.assertEqual(estimate_cost("Anthropic", "claude-sonnet-5", 1_000_000, 0).low, Decimal("2"))

    def test_image_inputs_have_range(self):
        cost = estimate_cost("OpenAI", "gpt-image-1", 4622, 87360)
        self.assertEqual(cost.low, Decimal("3.517510"))
        self.assertEqual(cost.high, Decimal("3.540620"))
        self.assertEqual(cost.display(), "$3.5175 – $3.5406")

    def test_unknown_model_does_not_inherit_similar_price(self):
        self.assertIsNone(estimate_cost("OpenAI", "gpt-image-1-future", 1000, 2000))
        self.assertIsNone(estimate_cost("Other", "gpt-4o-mini", 1000, 2000))
        self.assertIsNone(estimate_cost("OpenAI", "gpt-image-1", 0, 0))

    def test_partial_totals_exclude_unknown_and_count_requests(self):
        rows, total, missing = summarize_costs([
            ("OpenAI", "gpt-4o-mini", 59737, 10445, 50),
            ("OpenAI", "gpt-image-1", 4622, 87360, 14),
            ("Other", "unknown", 500, 500, 3)])
        self.assertEqual(total.low, Decimal("3.53273755"))
        self.assertEqual(total.high, Decimal("3.55584755"))
        self.assertEqual(missing, 3)
        self.assertIsNone(rows[-1])
        self.assertEqual(summarize_costs([])[1].display(), "$0.0000")

    def test_small_positive_cost_is_not_displayed_as_zero(self):
        self.assertEqual(CostEstimate(Decimal("0.0000001"), Decimal("0.0000001")).display(), "< $0.0001")

    def test_dashboard_refresh_and_layout(self):
        app = QApplication.instance() or QApplication([])
        stats = dict(totals=dict(contents=33, images=14, videos=6, posts=16),
                     today=dict(contents=0, images=10, videos=2, posts=0),
                     input_tokens=64359, output_tokens=97805, token_requests=64,
                     providers=[("OpenAI", "gpt-4o-mini", 59737, 10445, 50),
                                ("OpenAI", "gpt-image-1", 4622, 87360, 14)])
        with patch("app.storage.history_store.dashboard_stats", return_value=stats):
            from run import apply_theme
            apply_theme(app)
            widget = DashboardTab()
            widget.resize(960, 960)
            widget.show()
            app.processEvents()
            self.assertEqual(widget.width(), 960)
            self.assertEqual(widget.cost_total.text(), "$3.5327 – $3.5558")
            self.assertEqual(widget.provider_table.columnCount(), 5)
            self.assertEqual(widget.provider_table.horizontalScrollBar().maximum(), 0)
            folder = Path("output/ui-review")
            folder.mkdir(parents=True, exist_ok=True)
            widget.grab().save(str(folder / "dashboard-cost.png"))
            stats["providers"] = [("Other", "unknown", 100, 100, 2)]
            widget.refresh()
            self.assertEqual(widget.cost_total.text(), "Chưa đủ dữ liệu")
            self.assertIn("2 yêu cầu", widget.cost_detail.text())
            stats["providers"] = []
            widget.refresh()
            self.assertEqual(widget.cost_total.text(), "$0.0000")
            self.assertEqual(widget.provider_table.rowCount(), 0)
            widget.close()


if __name__ == "__main__":
    unittest.main()
