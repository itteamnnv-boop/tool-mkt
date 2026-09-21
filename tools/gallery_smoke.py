"""Offline gallery checks with synthetic media; no real history is read or changed."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
if sys.platform == 'win32':
    os.environ['QT_QPA_FONTDIR'] = 'C:/Windows/Fonts'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QPushButton
from app.ui.gallery_tab import GalleryTab
from run import apply_theme


def main():
    app = QApplication([])
    apply_theme(app)
    with TemporaryDirectory() as folder:
        path = Path(folder) / 'garden.png'
        pixmap = QPixmap(640, 360)
        pixmap.fill(QColor('#448c80'))
        pixmap.save(str(path))
        video = Path(folder) / 'demo.mp4'
        video.touch()
        images = [dict(id=i, created_at=f'2026-09-{i + 10} 12:00',
                       prompt='A garden with flowers and plants in the afternoon sunshine ' * 3,
                       file_path=str(path)) for i in range(6)]
        videos = [dict(id=8, created_at='2026-09-20 12:00', script='Demo video', file_path=str(video))]
        with patch('app.storage.history_store.list_recent', side_effect=lambda table, limit: images if table == 'images' else videos) as read:
            gallery = GalleryTab()
            gallery.show()
            for width, expected in [(1120, 4), (850, 3), (600, 2)]:
                gallery.resize(width, 720)
                for _ in range(5):
                    app.processEvents()
                assert gallery._columns == expected, (width, gallery._columns)
                assert gallery.scroll.horizontalScrollBar().maximum() == 0
                assert all(card.width() >= 260 for card in gallery._cards)
            assert gallery._cards[0].kind == 'video'
            selected = []
            gallery.use_for_tiktok_video.connect(selected.append)
            use_button = next(b for b in gallery._cards[0].findChildren(QPushButton) if b.objectName() == 'primaryButton')
            use_button.menu().actions()[1].trigger()
            assert selected == [video]
            gallery.filter_combo.setCurrentIndex(1)
            assert len(gallery._cards) == 6
            gallery.sort_combo.setCurrentIndex(1)
            assert gallery._cards[0].item_id == 0
            gallery.search_input.setText('no-match')
            gallery._render_items()
            assert not gallery._cards
            gallery.search_input.setText('garden.png')
            gallery._render_items()
            assert len(gallery._cards) == 6
            assert read.call_count == 2, 'Local filters must not reread the database'
            gallery.resize(1120, 720)
            for _ in range(5):
                app.processEvents()
            output = Path('output/ui-review/gallery-redesign.png')
            output.parent.mkdir(parents=True, exist_ok=True)
            gallery.grab().save(str(output))
            gallery.close()
    print('PASS: responsive populated grid, sorting, filtering, search, reuse signal, no horizontal overflow.')


if __name__ == '__main__':
    main()
