"""Offline archive checks using an isolated database and synthetic content."""
import os
import sys
import time
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
if sys.platform == 'win32':
    os.environ['QT_QPA_FONTDIR'] = 'C:/Windows/Fonts'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication
from app.storage import sqlite_history_store as db
from app.ui.archive_tab import ArchiveTab, PAGE_SIZE
from run import apply_theme


def settle(app, tab):
    deadline = time.monotonic() + 5
    while tab._busy or tab._search_timer.isActive():
        app.processEvents()
        assert time.monotonic() < deadline, 'Archive request did not complete'
        time.sleep(0.01)
    app.processEvents()


def main():
    app = QApplication([])
    apply_theme(app)
    with TemporaryDirectory() as folder, patch.object(db, 'app_data_dir', return_value=Path(folder)):
        db.init_db()
        for i in range(PAGE_SIZE + 5):
            db.add_content(f'Bài viết {i}', f'Nội dung {i}\nĐoạn thứ hai.\n#hashtag')
        db.add_content('ƯU ĐÃI 100%', 'Nội dung đặc biệt _ giữ nguyên')
        assert len(db.list_contents('ưu đãi')) == 1
        assert len(db.list_contents('%')) == 1
        assert len(db.list_contents('_')) == 1
        with patch('app.storage.history_store.list_contents', side_effect=db.list_contents), \
             patch('app.storage.history_store.list_successful_posts', side_effect=db.list_successful_posts):
            tab = ArchiveTab()
            tab.source_combo.setCurrentIndex(0)
            tab.resize(900, 720)
            tab.show()
            tab.refresh()
            settle(app, tab)
            assert tab.content_list.count() == PAGE_SIZE
            assert tab.next_btn.isEnabled()
            expected = 'Nội dung đặc biệt _ giữ nguyên'
            assert tab.preview.toPlainText() == expected
            tab.copy_btn.click()
            assert app.clipboard().text() == expected
            reused = []
            tab.reuse_requested.connect(lambda *args: reused.append(args))
            for action in tab.reuse_btn.menu().actions():
                action.trigger()
            assert [row[0] for row in reused] == ['content', 'image', 'video', 'facebook']
            assert all(row[2] == expected for row in reused)
            tab.next_btn.click()
            settle(app, tab)
            assert tab.content_list.count() == 6
            assert not tab.next_btn.isEnabled()
            assert tab.previous_btn.isEnabled()
            tab.search_input.setText('ƯU ĐÃI')
            settle(app, tab)
            assert tab.content_list.count() == 1
            assert tab._offset == 0
            tab.search_input.setText('no matching content')
            settle(app, tab)
            assert not tab.preview.toPlainText()
            assert not tab.reuse_btn.isEnabled()
            tab.search_input.clear()
            settle(app, tab)
            output = Path('output/ui-review/archive.png')
            output.parent.mkdir(parents=True, exist_ok=True)
            tab.grab().save(str(output))
            tab._failed('Synthetic connection failure')
            assert not tab.preview.toPlainText()
            assert not tab.reuse_btn.isEnabled()
            assert tab.refresh_btn.isEnabled()
            tab.refresh()
            settle(app, tab)
            assert tab.content_list.count() == PAGE_SIZE
            first = Path(folder) / 'first.png'
            second = Path(folder) / 'second.png'
            first.write_bytes(b'first')
            second.write_bytes(b'second')
            db.add_post('photos', 'Bài đã đăng\nNội dung đầy đủ', json.dumps([str(first), str(second)]),
                        facebook_post_id='123_456', page_id='123', page_name='Trang mẫu')
            db.add_post('text', 'Failed post', ok=False)
            db.add_post('text', 'Scheduled post', scheduled_time='2026-09-25 10:00',
                        facebook_post_id='123_789', page_name='Trang mẫu')
            assert len(db.list_successful_posts()) == 2
            assert len(db.list_successful_posts('TRANG MẪU')) == 2
            assert len(db.list_successful_posts('123_456')) == 1
            tab.source_combo.setCurrentIndex(1)
            settle(app, tab)
            assert tab.content_list.count() == 2
            assert 'Đã lên lịch' in tab.date_label.text()
            tab.content_list.setCurrentRow(1)
            assert tab.preview.toPlainText() == 'Bài đã đăng\nNội dung đầy đủ'
            assert tab._post_url(tab._selected) == 'https://www.facebook.com/123_456'
            assert len(tab.attachments_menu.actions()) == 2
            assert all(action.isEnabled() for action in tab.attachments_menu.actions())
            tab.copy_btn.click()
            assert app.clipboard().text() == 'Bài đã đăng\nNội dung đầy đủ'
            reused.clear()
            tab.reuse_btn.menu().actions()[0].trigger()
            assert reused[0][2] == 'Bài đã đăng\nNội dung đầy đủ'
            second.unlink()
            tab.refresh()
            settle(app, tab)
            assert not tab.attachments_menu.actions()[1].isEnabled()
            tab.grab().save('output/ui-review/archive-posts.png')
            tab.close()
    print('PASS: Unicode/literal search, pagination, full-text reading, copy, all reuse destinations, empty state.')


if __name__ == '__main__':
    main()
