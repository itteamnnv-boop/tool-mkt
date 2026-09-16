"""Production dashboard backed by the local activity history."""
from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.storage import history_store
from app.ui.widgets.page_header import make_page_header


class DashboardTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        header = QHBoxLayout()
        header.addWidget(make_page_header("📊 Dashboard", "Tổng quan hoạt động tạo nội dung và xuất bản."), 1)
        self.refresh_btn = QPushButton("↻ Làm mới")
        self.refresh_btn.setObjectName("linkButton")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)
        layout.addLayout(header)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards: dict[str, tuple[QLabel, QLabel]] = {}
        for index, (key, title) in enumerate((("contents", "Content đã tạo"), ("images", "Hình ảnh đã tạo"), ("videos", "Video đã tạo"), ("posts", "Bài viết đăng thành công"))):
            panel = QWidget()
            panel.setObjectName("metricCard")
            panel_layout = QVBoxLayout(panel)
            title_label, value, today = QLabel(title), QLabel("0"), QLabel("Hôm nay: 0")
            title_label.setObjectName("metricTitle")
            value.setObjectName("metricValue")
            today.setObjectName("metricToday")
            panel_layout.addWidget(title_label)
            panel_layout.addWidget(value)
            panel_layout.addWidget(today)
            grid.addWidget(panel, index // 2, index % 2)
            self.cards[key] = (value, today)
        layout.addLayout(grid)
        token_panel = QWidget()
        token_panel.setObjectName("metricCard")
        token_layout = QHBoxLayout(token_panel)
        self.token_total = QLabel("0 token")
        self.token_total.setObjectName("tokenTotal")
        self.token_detail = QLabel()
        self.token_detail.setObjectName("metricToday")
        self.token_detail.setWordWrap(True)
        token_layout.addWidget(QLabel("Token AI đã sử dụng"), 1)
        token_layout.addWidget(self.token_detail, 2)
        token_layout.addWidget(self.token_total)
        layout.addWidget(token_panel)
        layout.addWidget(QLabel("Chi tiết theo nhà cung cấp / model"))
        self.provider_table = QTableWidget(0, 4)
        self.provider_table.setObjectName("dashboardTable")
        self.provider_table.setHorizontalHeaderLabels(["Nhà cung cấp", "Model", "Input", "Output"])
        self.provider_table.verticalHeader().setVisible(False)
        self.provider_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.provider_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.provider_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.provider_table, 1)

    def refresh(self) -> None:
        stats = history_store.dashboard_stats()
        for key, (value, today) in self.cards.items():
            value.setText(f"{stats['totals'][key]:,}")
            today.setText(f"Hôm nay: {stats['today'][key]:,}")
        input_tokens, output_tokens = stats["input_tokens"], stats["output_tokens"]
        self.token_total.setText(f"{input_tokens + output_tokens:,} token")
        self.token_detail.setText(f"Input: {input_tokens:,}  •  Output: {output_tokens:,}  •  {stats['token_requests']:,} yêu cầu được ghi nhận")
        providers = stats["providers"]
        self.provider_table.setRowCount(len(providers))
        for row, (provider, model, input_count, output_count, _) in enumerate(providers):
            for col, text in enumerate((provider, model, f"{input_count:,}", f"{output_count:,}")):
                self.provider_table.setItem(row, col, QTableWidgetItem(str(text)))
        self.provider_table.resizeColumnsToContents()
