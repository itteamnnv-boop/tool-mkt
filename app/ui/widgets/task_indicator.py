"""Toolbar access to active progress dialogs and their latest results."""
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QMenu, QPushButton

from app.ui.widgets.design import line_icon


class TaskIndicator(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("taskIndicator")
        self.setProperty("iconName", "progress")
        self.setIcon(line_icon("progress"))
        self.setMinimumWidth(52)
        self._dialogs = []
        self._menu = QMenu(self)
        self.clicked.connect(self.open_tasks)
        self.hide()

    def register(self, label, dialog):
        if any(existing is dialog for _, existing in self._dialogs):
            return
        self._dialogs.append((label, dialog))
        dialog.state_changed.connect(self.refresh)
        self.refresh()

    def activities(self):
        return [(label, dialog) for label, dialog in self._dialogs if dialog.has_activity]

    def refresh(self):
        activities = self.activities()
        self.setVisible(bool(activities))
        running = sum(dialog.scene.running for _, dialog in activities)
        self.setText(str(len(activities)))
        title = f"Tiến trình: {running} đang chạy, {len(activities) - running} kết quả"
        self.setAccessibleName(title + ". Bấm để mở lại.")
        self.setToolTip(title + "\n" + "\n".join(f"{label}: {dialog.status_label.text()}" for label, dialog in activities))

    def open_tasks(self):
        activities = self.activities()
        if len(activities) == 1:
            activities[0][1].restore()
        elif activities:
            self._menu.clear()
            for label, dialog in activities:
                state = "Đang chạy" if dialog.scene.running else "Kết quả"
                # Escape ampersands so task text never turns into menu mnemonics.
                title = f"{label} · {state} — {dialog.status_label.text()[:90]}".replace("&", "&&")
                action = self._menu.addAction(title)
                action.triggered.connect(lambda checked=False, target=dialog: target.restore())
            self._menu.popup(self.mapToGlobal(QPoint(0, self.height())))
