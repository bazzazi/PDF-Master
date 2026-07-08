"""
PDF Master v1.0.1 — Professional PDF Management Suite
======================================================
A powerful cross-platform desktop application for managing PDF files with
a modern, professional multi-theme user interface built on PyQt5.

Author : Mohammad Ali Bazzazi  (https://github.com/bazzazi)
Website: https://mohammadalibazzazi.ir
LinkedIn: https://www.linkedin.com/in/bazzazi/
License: All rights reserved
Version: 1.0.1

Modules
-------
  * Reader       — smooth PDF viewer (zoom, fit-width, Ctrl+wheel, arrows)
  * Merge        — combine PDFs (drag to reorder, per-file page count)
  * Split        — split by single page or extract page range
  * Compress     — reduce PDF size with 3 quality presets
  * Extract      — text / images / pages-as-PNG
  * Organize     — rotate, delete & reorder pages visually
  * Security     — encrypt / decrypt with password (AES-256 when available)
  * Watermark    — customizable diagonal text watermark
  * Metadata     — view & edit document metadata
  * About        — developer information (Mohammad Ali Bazzazi)

Localization
------------
  * English  (LTR)
  * فارسی    (RTL)

All heavy operations run on a background thread with a live progress bar
so the UI never freezes.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
import webbrowser
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Missing dependency: PyMuPDF  ->  pip install PyMuPDF")

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit("Missing dependency: pypdf   ->  pip install pypdf")

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QEvent, QSettings, QTimer, QUrl, QSize
from PyQt5.QtGui import QPixmap, QImage, QKeySequence, QDesktopServices, QFont, QIcon, QPainter, QColor
from PyQt5.QtCore import QRect, QPoint
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QStackedWidget, QScrollArea,
    QListWidget, QListWidgetItem, QLineEdit, QSpinBox, QComboBox, QTextEdit,
    QProgressBar, QStatusBar, QFrame, QFormLayout, QSlider, QGroupBox,
    QShortcut, QDialog, QDialogButtonBox, QMenu, QAction, QActionGroup,
    QCheckBox, QInputDialog, QStyle, QSizePolicy, QLayout, QWidgetItem, QToolTip,
)


# =============================================================================
#  FlowLayout — responsive wrapping horizontal layout (Qt example, adapted)
# =============================================================================
class FlowLayout(QLayout):
    """A layout that arranges items left-to-right and wraps to a new line
    when the available width is exceeded. Used to keep the reader toolbar
    fully usable at any window size without horizontal scrollbars."""

    def __init__(self, parent=None, margin=0, hspacing=8, vspacing=10):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self._hspace = hspacing
        self._vspace = vspacing
        self._items: List[QWidgetItem] = []

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self):
        return self._hspace

    def verticalSpacing(self):
        return self._vspace

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        # First pass: gather each wrapped row so we can vertically-center
        # items within a row (uniform baseline across differing item heights).
        rows = []
        cur_row = []
        x = effective.x()
        cur_h = 0
        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisible():
                continue
            sh = item.sizeHint()
            space_x = self._hspace
            need = sh.width() + space_x
            if x + need - space_x > effective.right() and cur_row:
                rows.append((cur_row, cur_h))
                cur_row = []
                x = effective.x()
                cur_h = 0
            cur_row.append((item, sh))
            x += need
            cur_h = max(cur_h, sh.height())
        if cur_row:
            rows.append((cur_row, cur_h))
        # Second pass: place items, vertically centered on row baseline.
        y = effective.y()
        total_h = 0
        for row, row_h in rows:
            rx = effective.x()
            for item, sh in row:
                iy = y + (row_h - sh.height()) // 2
                if not test_only:
                    item.setGeometry(QRect(QPoint(rx, iy), sh))
                rx += sh.width() + self._hspace
            y += row_h + self._vspace
            total_h += row_h + self._vspace
        if rows:
            total_h -= self._vspace
        return total_h + m.bottom()

APP_NAME     = "PDF Master"
APP_VERSION  = "1.0.2"
APP_AUTHOR   = "Mohammad Ali Bazzazi"
APP_HANDLE   = "bazzazi"
APP_GITHUB   = "https://github.com/bazzazi"
APP_WEBSITE  = "https://mohammadalibazzazi.ir"
APP_LINKEDIN = "https://www.linkedin.com/in/bazzazi/"
APP_TAGLINE  = "Full-Stack Developer"
APP_LICENSE  = "All rights reserved"
APP_ROOT     = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ICON_DIR     = APP_ROOT / "icons"
ICON_SIZE    = 18
APP_BIO_EN   = ("Hi everyone! I'm Mohammad Ali Bazzazi, a Full-Stack Developer "
                "passionate about learning and solving problems.")
APP_BIO_FA   = ("سلام! من محمدعلی بزازی هستم، توسعه‌دهنده‌ی فول‌استک، علاقه‌مند "
                "به یادگیری و حل مسئله.")

# =============================================================================
#  Internationalization (i18n)
# =============================================================================

I18N: Dict[str, Dict[str, str]] = {
    "en": {
        # generic
        "app_subtitle": "Professional PDF Suite",
        "ready": "Ready",
        "busy": "Busy",
        "busy_msg": "Another operation is still running.",
        "working": "Working...",
        "success": "Success",
        "done": "Done",
        "saved": "Saved",
        "operation_failed": "Operation failed",
        "overwrite_source_title": "Overwrite source?",
        "overwrite_source_msg": "You are about to save over the source file.\nContinue?",
        # menu
        "menu_file": "&File",
        "menu_language": "&Language",
        "menu_help": "&Help",
        "menu_about": "&About",
        "menu_exit": "E&xit",
        "about_license": "All rights reserved",
        "select_folder": "Select Folder",
        "reader_password_prompt": "Enter the password for this PDF:",
        "reader_wrong_password": "Incorrect password.",
        "move_up": "Move up",
        "move_down": "Move down",
        "menu_english": "English",
        "menu_persian": "فارسی (Persian)",
        "language_changed": "Language changed. The interface will now reload.",
        # nav
        "nav_reader":    "Reader",
        "nav_merge":     "Merge",
        "nav_split":     "Split",
        "nav_compress":  "Compress",
        "nav_extract":   "Extract",
        "nav_organize":  "Organize",
        "nav_security":  "Security",
        "nav_watermark": "Watermark",
        "nav_metadata":  "Metadata",
        "nav_about":     "About",
        # reader
        "reader_title": "PDF Reader",
        "reader_sub": "A distraction-free PDF reading experience — full-screen mode, thumbnails, outline, search, themes and more.",
        "reader_open": "Open PDF",
        "reader_fit": "Fit Width",
        "reader_placeholder": "Open a PDF to start reading.",
        "reader_encrypted": "This PDF is password-protected. Use the Security tab to decrypt it first.",
        "reader_cannot_open": "Cannot open PDF",
        "reader_file_not_found": "The selected file does not exist.",
        "reader_empty_pdf": "The selected PDF contains no pages.",
        "reader_fit_page": "Fit Page",
        "reader_actual":   "Actual Size",
        "reader_rotate_l": "Rotate Left",
        "reader_rotate_r": "Rotate Right",
        "reader_prev": "Previous page",
        "reader_next": "Next page",
        "reader_zoom_in": "Zoom in",
        "reader_zoom_out": "Zoom out",
        "reader_goto":     "Go to page",
        "reader_present":  "Presentation Mode (F11)",
        "reader_present_exit": "Exit Presentation (Esc)",
        "reader_sidebar":  "Toggle Sidebar (Ctrl+B)",
        "reader_search":   "Search in document (Ctrl+F)",
        "reader_search_placeholder": "Search text… (Enter = next, Shift+Enter = prev)",
        "reader_no_match": "No matches",
        "reader_matches":  "{cur} / {total} matches",
        "reader_theme":    "Reading theme",
        "reader_theme_day":   "Day",
        "reader_theme_night": "Night",
        "reader_theme_sepia": "Sepia",
        "reader_continuous": "Continuous scroll",
        "reader_single":     "Single page",
        "reader_two_page":   "Two-page (book) view",
        "reader_tab_thumbs": "Thumbnails",
        "reader_tab_outline": "Outline",
        "reader_tab_search":  "Search",
        "reader_no_outline":  "This document has no outline / bookmarks.",
        "reader_recent":   "Recent files",
        "reader_recent_none": "No recent files",
        "reader_recent_clear": "Clear recent files",
        "reader_copy_text": "Copy selected text",
        "reader_hand":     "Hand tool (drag to pan)",
        "reader_hint": "Tip: drag to select text · right-click for Copy / Highlight · F11 full-screen · Ctrl+F search · Ctrl+G jump · Ctrl+B sidebar · Ctrl+±/0 zoom · R rotate · Space next · Ctrl+S save with highlights",
        "reader_rendering": "Rendering pages…",
        "reader_loading": "Opening PDF, please wait…",
        "reader_copy": "Copy selected text",
        "reader_highlight": "Highlight selection",
        "reader_clear_highlights": "Clear highlights on this page",
        "reader_save_annot": "Save PDF with highlights…",
        "reader_no_selection": "Nothing selected. Drag on the page to select text first.",
        "reader_no_highlights": "No highlights to save yet.",
        "reader_saved": "Saved to:\n{}",
        "encrypted_pdf": "Encrypted PDF",
        # merge
        "merge_title": "Merge PDFs",
        "merge_sub": "Combine multiple PDF files into a single document. Drag items to reorder.",
        "merge_add": "Add Files",
        "merge_remove": "Remove Selected",
        "merge_clear": "Clear",
        "merge_do": "Merge & Save",
        "merge_need_two": "Add at least two PDF files.",
        "merge_working": "Merging...",
        "merge_success": "Merged PDF saved to:\n{}",
        "skipped_file": "Skipped file",
        # split
        "split_title": "Split PDF",
        "split_sub": "Split a PDF into individual pages or extract a range of pages.",
        "split_file": "PDF File:",
        "split_pages": "Pages:",
        "split_mode": "Mode:",
        "split_range": "Range:",
        "split_from": "From",
        "split_to": "To",
        "split_mode_single": "Split into single pages",
        "split_mode_range":  "Extract page range",
        "split_do": "Split PDF",
        "split_need_valid": "Choose a valid PDF file.",
        "split_bad_range": "Start page must be <= end page.",
        "split_working_single": "Splitting...",
        "split_working_range":  "Extracting range...",
        "split_result_single":  "Split into {} files.",
        "split_result_range":   "Saved to:\n{}",
        # compress
        "compress_title": "Compress PDF",
        "compress_sub": "Reduce PDF file size using PyMuPDF's built-in optimization.",
        "compress_quality": "Quality:",
        "compress_low":    "Low (smallest file)",
        "compress_medium": "Medium (recommended)",
        "compress_high":   "High (best quality)",
        "compress_do":     "Compress",
        "compress_working": "Compressing...",
        "compress_original": "Original size: {:.1f} KB",
        "compress_report": ("Original:  {orig:.1f} KB\n"
                            "Compressed: {new:.1f} KB\n"
                            "Saved: {pct:.1f}%\n\nSaved to:\n{path}"),
        # extract
        "extract_title": "Extract Content",
        "extract_sub": "Extract text, embedded images, or render pages as PNG.",
        "extract_text_btn":  "Extract Text",
        "extract_save_text": "Save Text",
        "extract_images":    "Extract Images",
        "extract_pages_png": "Pages to PNG",
        "extract_placeholder": "Extracted text will appear here...",
        "extract_need_valid": "Choose a valid PDF file.",
        "extract_click_first": "Click 'Extract Text' first.",
        "extract_working_text":   "Extracting text...",
        "extract_working_images": "Extracting images...",
        "extract_working_pages":  "Rendering pages...",
        "extract_images_done": "Extracted {} image(s) to:\n{}",
        "extract_pages_done":  "Exported {} page image(s) to:\n{}",
        "extract_text_saved":  "Text saved to:\n{}",
        "save_failed": "Save failed",
        # organize
        "organize_title": "Organize Pages",
        "organize_sub": "Rotate, delete, and reorder pages, then save as a new PDF.",
        "organize_rot_l":  "Rotate Left",
        "organize_rot_r":  "Rotate Right",
        "organize_rot_2":  "180 degrees",
        "organize_delete": "Delete Page",
        "organize_save":   "Save As...",
        "organize_load_first": "Load a PDF first.",
        "organize_no_pages":   "No pages to save.",
        "organize_select_page": "Select at least one page.",
        "organize_working": "Saving...",
        "organize_saved":   "Saved to:\n{}",
        # security
        "security_title": "Security",
        "security_sub": "Protect a PDF with a password or remove existing encryption.",
        "security_encrypt_group": "Encrypt PDF",
        "security_decrypt_group": "Decrypt / Remove Password",
        "security_pw":      "Password:",
        "security_confirm": "Confirm:",
        "security_enc_do":  "Encrypt & Save",
        "security_dec_do":  "Decrypt & Save",
        "security_enter_pw":  "Enter a password.",
        "security_pw_mismatch": "Passwords do not match.",
        "security_wrong_pw": "Wrong password.",
        "security_choose_pdf": "Choose a valid PDF.",
        "security_encrypted": "Saved to:\n{}",
        "security_decrypted": "Saved to:\n{}",
        "security_working_enc": "Encrypting...",
        "security_working_dec": "Decrypting...",
        # watermark
        "watermark_title": "Watermark",
        "watermark_sub": "Add a customizable diagonal text watermark to every page.",
        "watermark_text": "Watermark Text:",
        "watermark_opacity": "Opacity:",
        "watermark_size": "Font Size:",
        "watermark_angle": "Angle (deg):",
        "watermark_do": "Apply Watermark",
        "watermark_working": "Applying watermark...",
        "watermark_saved": "Saved to:\n{}",
        "watermark_choose": "Choose a valid PDF.",
        # metadata
        "metadata_title": "Metadata",
        "metadata_sub": "View and edit the PDF document metadata fields.",
        "metadata_title_f":    "Title:",
        "metadata_author_f":   "Author:",
        "metadata_subject_f":  "Subject:",
        "metadata_keywords_f": "Keywords:",
        "metadata_creator_f":  "Creator:",
        "metadata_save": "Save Metadata",
        "metadata_working": "Saving...",
        "metadata_saved":   "Saved to:\n{}",
        "metadata_load_first": "Load a PDF first.",
        # about
        "about_title": "About the Developer",
        "about_sub": "Meet the person behind PDF Master.",
        "about_bio": APP_BIO_EN,
        "about_role": "Full-Stack Developer",
        "about_github":  "GitHub",
        "about_website": "Website",
        "about_linkedin": "LinkedIn",
        "about_app":    "About " + APP_NAME,
        "about_close":  "Close",
        "about_open_link": "Open link",
        "about_thanks": "Thank you for using PDF Master!",
        "splash_dontshow": "Don't show this again on startup",
        "sidebar_hide": "Hide sidebar",
        "sidebar_show": "Show sidebar",
        # common labels
        "browse": "Browse",
        "pdf_file_label": "PDF File:",
    },
    "fa": {
        "app_subtitle": "مجموعه حرفه‌ای مدیریت PDF",
        "ready": "آماده",
        "busy": "مشغول",
        "busy_msg": "یک عملیات دیگر در حال اجراست.",
        "working": "در حال اجرا...",
        "success": "موفق",
        "done": "انجام شد",
        "saved": "ذخیره شد",
        "operation_failed": "عملیات ناموفق بود",
        "overwrite_source_title": "بازنویسی فایل مبدا؟",
        "overwrite_source_msg": "شما در حال ذخیره روی فایل اصلی هستید.\nادامه می‌دهید؟",
        "menu_file": "&فایل",
        "menu_language": "&زبان",
        "menu_help": "&راهنما",
        "menu_about": "&درباره",
        "menu_exit": "&خروج",
        "about_license": "تمام حقوق محفوظ است",
        "select_folder": "انتخاب پوشه",
        "reader_password_prompt": "رمز عبور این PDF را وارد کنید:",
        "reader_wrong_password": "رمز عبور نادرست است.",
        "move_up": "انتقال به بالا",
        "move_down": "انتقال به پایین",
        "menu_english": "English",
        "menu_persian": "فارسی",
        "language_changed": "زبان تغییر کرد. رابط کاربری بارگذاری مجدد می‌شود.",
        "nav_reader":    "خواننده",
        "nav_merge":     "ادغام",
        "nav_split":     "جداسازی",
        "nav_compress":  "فشرده‌سازی",
        "nav_extract":   "استخراج",
        "nav_organize":  "سازماندهی",
        "nav_security":  "امنیت",
        "nav_watermark": "واترمارک",
        "nav_metadata":  "متادیتا",
        "nav_about":     "درباره",
        "reader_title": "خواننده PDF",
        "reader_sub": "تجربه‌ای بی‌حاشیه برای مطالعه PDF — حالت تمام‌صفحه، بندانگشتی‌ها، فهرست مطالب، جستجو، تم‌های مطالعه و امکانات فراوان.",
        "reader_open": "باز کردن PDF",
        "reader_fit": "تطبیق عرض",
        "reader_placeholder": "برای شروع یک PDF باز کنید.",
        "reader_encrypted": "این PDF با رمز عبور محافظت شده است. ابتدا از بخش امنیت آن را رمزگشایی کنید.",
        "reader_cannot_open": "امکان باز کردن PDF وجود ندارد",
        "reader_file_not_found": "فایل انتخاب‌شده وجود ندارد.",
        "reader_empty_pdf": "PDF انتخاب‌شده هیچ صفحه‌ای ندارد.",
        "reader_fit_page": "تطبیق صفحه",
        "reader_actual":   "اندازه واقعی",
        "reader_rotate_l": "چرخش به چپ",
        "reader_rotate_r": "چرخش به راست",
        "reader_prev": "صفحه قبل",
        "reader_next": "صفحه بعد",
        "reader_zoom_in": "بزرگ‌نمایی",
        "reader_zoom_out": "کوچک‌نمایی",
        "reader_goto":     "پرش به صفحه",
        "reader_present":  "حالت مطالعه تمام‌صفحه (F11)",
        "reader_present_exit": "خروج از حالت تمام‌صفحه (Esc)",
        "reader_sidebar":  "نمایش/مخفی کردن نوار کناری (Ctrl+B)",
        "reader_search":   "جستجو در سند (Ctrl+F)",
        "reader_search_placeholder": "جستجوی متن… (Enter بعدی، Shift+Enter قبلی)",
        "reader_no_match": "موردی یافت نشد",
        "reader_matches":  "{cur} از {total} مورد",
        "reader_theme":    "حالت مطالعه",
        "reader_theme_day":   "روز",
        "reader_theme_night": "شب",
        "reader_theme_sepia": "سپیا",
        "reader_continuous": "پیمایش پیوسته",
        "reader_single":     "تک‌صفحه",
        "reader_two_page":   "دوصفحه‌ای (کتاب)",
        "reader_tab_thumbs": "بندانگشتی",
        "reader_tab_outline": "فهرست مطالب",
        "reader_tab_search":  "جستجو",
        "reader_no_outline":  "این سند فهرست مطالب ندارد.",
        "reader_recent":   "فایل‌های اخیر",
        "reader_recent_none": "فایل اخیری وجود ندارد",
        "reader_recent_clear": "پاک کردن فایل‌های اخیر",
        "reader_copy_text": "کپی متن انتخاب‌شده",
        "reader_hand":     "ابزار دست (کشیدن برای جابجایی)",
        "reader_hint": "نکته: برای انتخاب متن روی صفحه بکشید · کلیک راست برای کپی/هایلایت · F11 تمام‌صفحه · Ctrl+F جستجو · Ctrl+G پرش · Ctrl+B نوار کناری · Ctrl+±/0 زوم · R چرخش · Space بعد · Ctrl+S ذخیره با هایلایت‌ها",
        "reader_rendering": "در حال رندر صفحات…",
        "reader_loading": "در حال باز کردن PDF، لطفاً صبر کنید…",
        "reader_copy": "کپی متن انتخاب‌شده",
        "reader_highlight": "هایلایت انتخاب",
        "reader_clear_highlights": "پاک کردن هایلایت‌های این صفحه",
        "reader_save_annot": "ذخیره PDF همراه با هایلایت‌ها…",
        "reader_no_selection": "چیزی انتخاب نشده است. ابتدا روی صفحه بکشید تا متن انتخاب شود.",
        "reader_no_highlights": "هنوز هایلایتی برای ذخیره وجود ندارد.",
        "reader_saved": "ذخیره شد در:\n{}",
        "encrypted_pdf": "PDF رمزگذاری‌شده",
        "merge_title": "ادغام PDFها",
        "merge_sub": "چند فایل PDF را در یک سند ترکیب کنید. برای مرتب‌سازی، آیتم‌ها را بکشید.",
        "merge_add": "افزودن فایل‌ها",
        "merge_remove": "حذف انتخاب‌شده‌ها",
        "merge_clear": "پاک کردن",
        "merge_do": "ادغام و ذخیره",
        "merge_need_two": "حداقل دو فایل PDF اضافه کنید.",
        "merge_working": "در حال ادغام...",
        "merge_success": "فایل ادغام‌شده ذخیره شد در:\n{}",
        "skipped_file": "فایل رد شد",
        "split_title": "جداسازی PDF",
        "split_sub": "یک PDF را به صفحات جداگانه تقسیم کنید یا محدوده‌ای از صفحات را استخراج کنید.",
        "split_file": "فایل PDF:",
        "split_pages": "صفحات:",
        "split_mode": "حالت:",
        "split_range": "محدوده:",
        "split_from": "از",
        "split_to":   "تا",
        "split_mode_single": "جداسازی به صفحات تکی",
        "split_mode_range":  "استخراج محدوده صفحات",
        "split_do": "جداسازی PDF",
        "split_need_valid": "یک فایل PDF معتبر انتخاب کنید.",
        "split_bad_range": "صفحه شروع باید کوچکتر یا مساوی صفحه پایان باشد.",
        "split_working_single": "در حال جداسازی...",
        "split_working_range":  "در حال استخراج محدوده...",
        "split_result_single":  "به {} فایل جدا شد.",
        "split_result_range":   "ذخیره شد در:\n{}",
        "compress_title": "فشرده‌سازی PDF",
        "compress_sub": "با استفاده از بهینه‌سازی داخلی PyMuPDF حجم فایل PDF را کاهش دهید.",
        "compress_quality": "کیفیت:",
        "compress_low":    "پایین (کوچک‌ترین حجم)",
        "compress_medium": "متوسط (پیشنهادی)",
        "compress_high":   "بالا (بهترین کیفیت)",
        "compress_do":     "فشرده‌سازی",
        "compress_working": "در حال فشرده‌سازی...",
        "compress_original": "حجم اصلی: {:.1f} کیلوبایت",
        "compress_report": ("اصلی:  {orig:.1f} KB\n"
                            "فشرده: {new:.1f} KB\n"
                            "کاهش: {pct:.1f}%\n\nذخیره شد در:\n{path}"),
        "extract_title": "استخراج محتوا",
        "extract_sub": "متن، تصاویر جاسازی‌شده را استخراج کنید یا صفحات را به PNG تبدیل کنید.",
        "extract_text_btn":  "استخراج متن",
        "extract_save_text": "ذخیره متن",
        "extract_images":    "استخراج تصاویر",
        "extract_pages_png": "صفحات به PNG",
        "extract_placeholder": "متن استخراج‌شده در اینجا نمایش داده می‌شود...",
        "extract_need_valid": "یک فایل PDF معتبر انتخاب کنید.",
        "extract_click_first": "ابتدا روی «استخراج متن» کلیک کنید.",
        "extract_working_text":   "در حال استخراج متن...",
        "extract_working_images": "در حال استخراج تصاویر...",
        "extract_working_pages":  "در حال رندر صفحات...",
        "extract_images_done": "{} تصویر استخراج شد در:\n{}",
        "extract_pages_done":  "{} تصویر صفحه ذخیره شد در:\n{}",
        "extract_text_saved":  "متن ذخیره شد در:\n{}",
        "save_failed": "ذخیره ناموفق بود",
        "organize_title": "سازماندهی صفحات",
        "organize_sub": "صفحات را بچرخانید، حذف کنید و ترتیب دهید، سپس به عنوان PDF جدید ذخیره کنید.",
        "organize_rot_l":  "چرخش چپ",
        "organize_rot_r":  "چرخش راست",
        "organize_rot_2":  "۱۸۰ درجه",
        "organize_delete": "حذف صفحه",
        "organize_save":   "ذخیره به عنوان...",
        "organize_load_first": "ابتدا یک PDF بارگذاری کنید.",
        "organize_no_pages":   "صفحه‌ای برای ذخیره وجود ندارد.",
        "organize_select_page": "حداقل یک صفحه انتخاب کنید.",
        "organize_working": "در حال ذخیره...",
        "organize_saved":   "ذخیره شد در:\n{}",
        "security_title": "امنیت",
        "security_sub": "یک PDF را با رمز محافظت کنید یا رمزگذاری موجود را حذف کنید.",
        "security_encrypt_group": "رمزگذاری PDF",
        "security_decrypt_group": "رمزگشایی / حذف رمز",
        "security_pw":      "رمز عبور:",
        "security_confirm": "تکرار:",
        "security_enc_do":  "رمزگذاری و ذخیره",
        "security_dec_do":  "رمزگشایی و ذخیره",
        "security_enter_pw":  "یک رمز وارد کنید.",
        "security_pw_mismatch": "رمزها یکسان نیستند.",
        "security_wrong_pw": "رمز اشتباه است.",
        "security_choose_pdf": "یک PDF معتبر انتخاب کنید.",
        "security_encrypted": "ذخیره شد در:\n{}",
        "security_decrypted": "ذخیره شد در:\n{}",
        "security_working_enc": "در حال رمزگذاری...",
        "security_working_dec": "در حال رمزگشایی...",
        "watermark_title": "واترمارک",
        "watermark_sub": "یک واترمارک متنی مورب قابل تنظیم به هر صفحه اضافه کنید.",
        "watermark_text": "متن واترمارک:",
        "watermark_opacity": "شفافیت:",
        "watermark_size": "اندازه فونت:",
        "watermark_angle": "زاویه (درجه):",
        "watermark_do": "اعمال واترمارک",
        "watermark_working": "در حال اعمال واترمارک...",
        "watermark_saved": "ذخیره شد در:\n{}",
        "watermark_choose": "یک PDF معتبر انتخاب کنید.",
        "metadata_title": "متادیتا",
        "metadata_sub": "فیلدهای متادیتای سند PDF را مشاهده و ویرایش کنید.",
        "metadata_title_f":    "عنوان:",
        "metadata_author_f":   "نویسنده:",
        "metadata_subject_f":  "موضوع:",
        "metadata_keywords_f": "کلیدواژه‌ها:",
        "metadata_creator_f":  "سازنده:",
        "metadata_save": "ذخیره متادیتا",
        "metadata_working": "در حال ذخیره...",
        "metadata_saved":   "ذخیره شد در:\n{}",
        "metadata_load_first": "ابتدا یک PDF بارگذاری کنید.",
        "about_title": "درباره توسعه‌دهنده",
        "about_sub": "با فردی که PDF Master را ساخته است آشنا شوید.",
        "about_bio": APP_BIO_FA,
        "about_role": "توسعه‌دهنده فول‌استک",
        "about_github":  "گیت‌هاب",
        "about_website": "وب‌سایت",
        "about_linkedin": "لینکدین",
        "about_app":    "درباره " + APP_NAME,
        "about_close":  "بستن",
        "about_open_link": "باز کردن لینک",
        "about_thanks": "از استفاده شما از PDF Master سپاسگزاریم!",
        "splash_dontshow": "این پیام را دیگر در راه‌اندازی نشان نده",
        "sidebar_hide": "مخفی کردن نوار کناری",
        "sidebar_show": "نمایش نوار کناری",
        "browse": "انتخاب",
        "pdf_file_label": "فایل PDF:",
    },
}

# ---- Additional i18n strings for new features (theme / auto-scroll / pin) ----
_EXTRA_I18N = {
    "en": {
        "menu_view": "View",
        "menu_theme": "Theme",
        "app_theme_dark":  "Dark (Nebula)",
        "app_theme_light": "Light",
        "app_theme_sepia": "Sepia",
        "reader_pin":         "Pin toolbar (keep visible in fullscreen)",
        "reader_pin_off":     "Auto-hide toolbar in fullscreen",
        "reader_autoscroll":  "Auto-scroll (play/pause)",
        "reader_autoscroll_speed": "Auto-scroll speed",
    },
    "fa": {
        "menu_view": "نما",
        "menu_theme": "پوسته",
        "app_theme_dark":  "تیره (Nebula)",
        "app_theme_light": "روشن",
        "app_theme_sepia": "سپیا",
        "reader_pin":         "پین کردن نوار ابزار (نمایش دائمی در تمام‌صفحه)",
        "reader_pin_off":     "پنهان‌سازی خودکار نوار ابزار در تمام‌صفحه",
        "reader_autoscroll":  "اسکرول خودکار (پخش/توقف)",
        "reader_autoscroll_speed": "سرعت اسکرول خودکار",
    },
}
for _lang, _vals in _EXTRA_I18N.items():
    I18N.setdefault(_lang, {}).update(_vals)

# Current UI language ("en" | "fa"). Read/written via QSettings.
LANG: str = "en"
# Current global app theme ("dark" | "light" | "sepia"). Read/written via QSettings.
APP_THEME: str = "dark"


def T(key: str) -> str:
    """Translate a key using the current language, falling back to English then key."""
    return I18N.get(LANG, {}).get(key) or I18N["en"].get(key, key)


_ICON_TINT_CACHE: Dict[str, QIcon] = {}


def _tint_icon(path: str, hex_color: str) -> QIcon:
    """Load an SVG and recolor its strokes/fills for the requested color."""
    key = f"{path}::{hex_color}"
    cached = _ICON_TINT_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from PyQt5.QtSvg import QSvgRenderer  # optional; PyQt5 always ships it
        from PyQt5.QtCore import QByteArray
        with open(path, "rb") as f:
            data = f.read()
        try:
            txt = data.decode("utf-8", errors="ignore")
            # Recolor common stroke/fill values used by the bundled icon set.
            for old in ("#E4E7F1", "#EDEFF7", "#DBE2FF", "#FFFFFF", "#ffffff",
                        "#1A1D2C", "#0B0D14", "#3B2E1E", "currentColor"):
                txt = txt.replace(old, hex_color)
            # Also flip generic dark strokes so light-theme icons show up on light bg.
            txt = re.sub(r'stroke="#(?:0|1|2)[0-9A-Fa-f]{5}"',
                         f'stroke="{hex_color}"', txt)
            txt = re.sub(r'fill="#(?:0|1|2)[0-9A-Fa-f]{5}"',
                         f'fill="{hex_color}"', txt)
            data = txt.encode("utf-8")
        except Exception:
            pass
        renderer = QSvgRenderer(QByteArray(data))
        size = QSize(64, 64)
        pix = QPixmap(size); pix.fill(Qt.transparent)
        p = QPainter(pix); renderer.render(p); p.end()
        icon = QIcon(pix)
    except Exception:
        icon = QIcon(path)
    _ICON_TINT_CACHE[key] = icon
    return icon


def _theme_icon_color() -> str:
    """The default tint used for icons on neutral surfaces of the current theme."""
    if APP_THEME == "light":
        return "#1A1D2C"
    if APP_THEME == "sepia":
        return "#3B2E1E"
    return "#EDEFF7"  # dark theme: light icon on dark bg


def _icon_color_for_widget(widget) -> str:
    """Pick a tint that stays readable given the widget's background variant."""
    try:
        obj = widget.objectName() if hasattr(widget, "objectName") else ""
    except Exception:
        obj = ""
    icon_only = False
    try:
        icon_only = bool(widget.property("iconOnly"))
    except Exception:
        icon_only = False
    # Primary / accent surfaces always want a white icon regardless of theme.
    if obj == "" and isinstance(widget, QPushButton) and not icon_only:
        return "#FFFFFF"
    if obj == "Danger":
        return "#FFFFFF"
    # Secondary / ghost / iconOnly / link buttons use theme text tint.
    return _theme_icon_color()


def _local_icon(name: str, color: Optional[str] = None) -> QIcon:
    """Load a local SVG icon, tinted to the requested color (or theme default)."""
    try:
        path = ICON_DIR / f"{name}.svg"
        if path.exists():
            tint = color or _theme_icon_color()
            return _tint_icon(str(path), tint)
    except Exception:
        pass
    return QIcon()


# =============================================================================
#  Stylesheet — "Nebula" modern dark theme (indigo accent, unified iconography)
# =============================================================================
#  Design tokens
#    bg-0 #0B0D14   deepest canvas
#    bg-1 #12141F   main surface / content area
#    bg-2 #1A1D2C   elevated cards & inputs
#    bg-3 #232739   hover / selected surface
#    border #2A2F42
#    text-hi  #EDEFF7   text-mid #A8AECB   text-lo #6B7290
#    accent   #6D7CFF   accent-hover #8290FF   accent-press #4C5FE0
#    success  #43D18F   danger #F26B7B   warning #F5C86A
#  Icon color (#E4E7F1) is baked into every SVG in ./icons and is designed to
#  read on any button variant (accent / secondary / transparent).

# =============================================================================
#  Stylesheet template — parameterised by a theme color dictionary.
#  Every theme provides the same token set so contrast stays correct across
#  the dark, light and sepia variants.
# =============================================================================

_QSS_TEMPLATE = """
* {
    font-family: 'Segoe UI', 'Tahoma', 'Vazirmatn', 'IRANSans', 'DejaVu Sans', sans-serif;
    font-size: 10pt;
    outline: 0;
}

QMainWindow, QDialog { background-color: {bg0}; color: {text_hi}; }
QWidget            { color: {text_hi}; }
QToolTip {
    background-color: {bg2}; color: {text_hi};
    border: 1px solid {border}; border-radius: 6px; padding: 6px 9px;
}

/* -------- Menu bar & menus -------- */
QMenuBar { background: {bg_menu}; color: {text_hi}; padding: 4px 8px; border-bottom: 1px solid {border}; }
QMenuBar::item { background: transparent; padding: 6px 12px; border-radius: 8px; color: {text_hi}; }
QMenuBar::item:selected { background: {bg_hover}; color: {text_on_hover}; }
QMenu {
    background: {bg_menu}; color: {text_hi}; border: 1px solid {border};
    padding: 6px; border-radius: 12px;
}
QMenu::item { padding: 8px 22px; border-radius: 8px; color: {text_hi}; }
QMenu::item:selected { background: {bg_hover}; color: {text_on_hover}; }
QMenu::separator { height: 1px; background: {border}; margin: 6px 8px; }

/* -------- Sidebar -------- */
#Sidebar { background-color: {bg_sidebar}; border-right: 1px solid {border}; }
#SidebarTitle {
    color: {text_hi}; font-size: 14pt; font-weight: 800; letter-spacing: 0.3px;
}
#SidebarSubtitle {
    color: {text_lo}; font-size: 9pt;
}
#SidebarScroll { background: transparent; border: none; }
#SidebarScroll > QWidget > QWidget { background: transparent; }
#SidebarFooter {
    color:{text_lo}; padding: 8px 10px; font-size: 8.5pt;
    border-top: 1px solid {border}; background:{bg_menu};
}

QPushButton#NavButton {
    text-align: left; padding: 11px 14px 11px 12px;
    background: transparent; color: {text_mid};
    border: 1px solid transparent; border-left: 3px solid transparent;
    font-size: 10.5pt; margin: 3px 10px; border-radius: 12px;
    min-height: 34px;
}
QPushButton#NavButton:hover {
    background-color: {bg_hover}; color: {text_hi};
}
QPushButton#NavButton:checked {
    background-color: {bg_selected}; color: {text_hi};
    border-left: 3px solid {accent}; font-weight: 600;
}

/* -------- Content area -------- */
#ContentArea { background-color: {bg0}; }
#PageTitle {
    font-size: 22pt; font-weight: 800; color: {text_hi}; padding-bottom: 2px;
    letter-spacing: 0.2px;
}
#PageSubtitle {
    color: {text_mid}; font-size: 10.5pt; padding-bottom: 18px;
}
#Placeholder { color: {text_mid}; padding: 80px; font-size: 11pt; }
#PageIndicator, #HintLabel, #SearchStatus { color: {text_mid}; }

QFrame#Card {
    background-color: {bg1}; border: 1px solid {border};
    border-radius: 16px; padding: 18px;
}

QFrame#ToolbarSeparator {
    background: {border}; max-width: 1px; min-width: 1px;
    margin: 6px 4px;
}

/* -------- Inputs -------- */
QLineEdit, QSpinBox, QComboBox, QTextEdit {
    background-color: {bg_input}; border: 1px solid {border};
    border-radius: 10px; padding: 8px 12px; color: {text_hi};
    selection-background-color: {accent}; selection-color: #FFFFFF;
    min-height: 22px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid {accent}; background-color: {bg_input_focus};
}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled, QTextEdit:disabled {
    background-color: {bg_input}; color: {text_lo}; border-color: {border};
}
QComboBox { padding-right: 30px; }
QComboBox::drop-down {
    border: 0px; width: 26px; subcontrol-origin: padding; subcontrol-position: top right;
}
QComboBox::down-arrow { image: url({combo_down_icon}); width: 12px; height: 12px; margin-right: 8px; }
QComboBox QAbstractItemView {
    background-color: {bg1}; color: {text_hi};
    selection-background-color: {accent}; selection-color: #FFFFFF;
    outline: 0px; border: 1px solid {border}; border-radius: 10px; padding: 4px;
}
QComboBox QAbstractItemView::item { min-height: 26px; padding: 4px 10px; border-radius: 6px; }

QSpinBox::up-button {
    subcontrol-origin: border; subcontrol-position: top right;
    background: {bg_hover}; border: none; width: 18px; margin: 2px;
    border-top-right-radius: 6px;
}
QSpinBox::down-button {
    subcontrol-origin: border; subcontrol-position: bottom right;
    background: {bg_hover}; border: none; width: 18px; margin: 2px;
    border-bottom-right-radius: 6px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: {bg_selected}; }
QSpinBox::up-arrow {
    image: url({spin_up_icon}); width: 10px; height: 10px;
}
QSpinBox::down-arrow {
    image: url({spin_down_icon}); width: 10px; height: 10px;
}

/* -------- Buttons -------- */
QPushButton {
    background-color: {accent}; color: #FFFFFF; border: none;
    border-radius: 10px; padding: 9px 18px; font-weight: 600; min-height: 34px;
}
QPushButton:hover   { background-color: {accent_hi}; }
QPushButton:pressed { background-color: {accent_press}; }
QPushButton:focus   { border: 1px solid {accent_hi}; }
QPushButton:disabled { background-color: {bg_selected}; color: {text_lo}; }

QPushButton#Secondary {
    background-color: {bg_input}; color: {text_hi}; border: 1px solid {border};
}
QPushButton#Secondary:hover  { background-color: {bg_hover}; border-color: {border_hi}; }
QPushButton#Secondary:pressed{ background-color: {bg_selected}; }
QPushButton#Secondary:checked{
    background-color: {bg_selected}; color: {text_hi}; border: 1px solid {accent};
}

QPushButton#Danger  { background-color: {danger}; color: #FFFFFF; }
QPushButton#Danger:hover  { background-color: {danger_hi}; }
QPushButton#Danger:pressed{ background-color: {danger_press}; }

QPushButton#Ghost { background: transparent; color: {text_hi}; border: 1px solid transparent; }
QPushButton#Ghost:hover { background: {bg_hover}; border-color: {border}; }

QPushButton#Link {
    background: transparent; color: {accent}; text-decoration: underline;
    padding: 2px; font-weight: 500; min-height: 0px;
}
QPushButton#Link:hover { color: {accent_hi}; }

QPushButton[iconOnly="true"] {
    padding: 0px; min-width: 38px; min-height: 38px;
    background-color: {bg_input}; color: {text_hi}; border: 1px solid {border};
    border-radius: 10px;
}
QPushButton[iconOnly="true"]:hover   { background-color: {bg_hover}; border-color: {border_hi}; }
QPushButton[iconOnly="true"]:pressed { background-color: {bg_selected}; }
QPushButton[iconOnly="true"]:checked {
    background-color: {bg_selected}; border: 1px solid {accent};
}

/* -------- Lists -------- */
QListWidget {
    background-color: {bg1}; border: 1px solid {border};
    border-radius: 12px; padding: 6px;
    alternate-background-color: {bg_alt};
    color: {text_hi};
}
QListWidget::item {
    padding: 9px 10px; border-radius: 8px; color: {text_hi}; margin: 1px 2px;
}
QListWidget::item:hover    { background-color: {bg_hover}; }
QListWidget::item:selected { background-color: {accent}; color: #FFFFFF; }

QListWidget#ThumbList {
    background: {bg_menu}; border: 1px solid {border}; border-radius: 12px; padding: 8px;
}
QListWidget#ThumbList::item {
    color: {text_hi}; padding: 8px; margin: 3px; border-radius: 10px;
    border: 1px solid transparent;
}
QListWidget#ThumbList::item:hover { background: {bg_hover}; }
QListWidget#ThumbList::item:selected {
    background: {bg_selected}; color: {text_hi}; border: 1px solid {accent};
}

/* -------- Scrollbars -------- */
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent; border: none; margin: 0;
}
QScrollBar:vertical   { width: 12px; }
QScrollBar:horizontal { height: 12px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: {scroll_handle}; border-radius: 6px; min-height: 28px; min-width: 28px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: {scroll_handle_hover};
}
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* -------- Progress bar -------- */
QProgressBar {
    background-color: {bg_input}; border: 1px solid {border};
    border-radius: 8px; text-align: center; color: {text_hi}; height: 18px;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: {accent};
    border-radius: 7px;
}

/* -------- Status bar -------- */
QStatusBar {
    background: {bg_menu}; color: {text_mid};
    border-top: 1px solid {border}; padding: 3px 8px;
}
QStatusBar::item { border: none; }

/* -------- Group box -------- */
QGroupBox {
    border: 1px solid {border}; border-radius: 14px;
    margin-top: 18px; padding: 18px 14px 14px 14px;
    color: {text_hi}; font-weight: 700;
    background-color: {bg1};
}
QGroupBox::title {
    subcontrol-origin: margin; left: 14px; padding: 0 8px;
    color: {accent};
}

/* -------- Checkbox -------- */
QCheckBox { color: {text_hi}; spacing: 8px; padding: 4px 2px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid {border_hi}; background: {bg_input};
}
QCheckBox::indicator:hover    { border-color: {accent}; }
QCheckBox::indicator:checked  {
    background: {accent}; border-color: {accent};
}

/* -------- Slider -------- */
QSlider::groove:horizontal {
    background: {bg_selected}; height: 6px; border-radius: 3px;
}
QSlider::sub-page:horizontal { background: {accent}; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #FFFFFF; border: 2px solid {accent};
    width: 16px; height: 16px; margin: -6px 0; border-radius: 10px;
}
QSlider::handle:horizontal:hover { border-color: {accent_hi}; }

/* -------- Message box -------- */
QMessageBox { background-color: {bg1}; }
QMessageBox QLabel { color: {text_hi}; }
"""


# ---- Theme color palettes ---------------------------------------------------
_THEME_TOKENS: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg0": "#0B0D14", "bg1": "#12141F", "bg2": "#1A1D2C",
        "bg_alt": "#14172A", "bg_menu": "#0F1220", "bg_sidebar": "#0F1220",
        "bg_input": "#1A1D2C", "bg_input_focus": "#1D2033",
        "bg_hover": "#232739", "bg_selected": "#2E3450",
        "border": "#2A2F42", "border_hi": "#363B57",
        "text_hi": "#EDEFF7", "text_mid": "#A8AECB", "text_lo": "#7C82A3",
        "text_on_hover": "#FFFFFF",
        "accent": "#6D7CFF", "accent_hi": "#8290FF", "accent_press": "#4C5FE0",
        "danger": "#F26B7B", "danger_hi": "#F58493", "danger_press": "#D5566A",
        "scroll_handle": "#2A2F42", "scroll_handle_hover": "#3A415E",
    },
    "light": {
        "bg0": "#F4F6FA", "bg1": "#FFFFFF", "bg2": "#F1F3F9",
        "bg_alt": "#F6F8FC", "bg_menu": "#FFFFFF", "bg_sidebar": "#FFFFFF",
        "bg_input": "#FFFFFF", "bg_input_focus": "#F6F8FF",
        "bg_hover": "#EEF1F8", "bg_selected": "#E1E6F7",
        "border": "#D6DAE6", "border_hi": "#B4BACC",
        "text_hi": "#131627", "text_mid": "#3F4661", "text_lo": "#6B7290",
        "text_on_hover": "#131627",
        "accent": "#4C5FE0", "accent_hi": "#6474FF", "accent_press": "#3746B8",
        "danger": "#DC3B4F", "danger_hi": "#E7566A", "danger_press": "#B72C3E",
        "scroll_handle": "#C3C9D9", "scroll_handle_hover": "#A3AAC0",
    },
    "sepia": {
        "bg0": "#EDE3CC", "bg1": "#F6ECD3", "bg2": "#EDE1BF",
        "bg_alt": "#EFE4C8", "bg_menu": "#F1E7CF", "bg_sidebar": "#F1E7CF",
        "bg_input": "#F6ECD3", "bg_input_focus": "#F9F0DB",
        "bg_hover": "#E4D8BC", "bg_selected": "#DBCC9C",
        "border": "#C7B37A", "border_hi": "#A8925A",
        "text_hi": "#2A2418", "text_mid": "#4A3F27", "text_lo": "#6D5D3A",
        "text_on_hover": "#2A2418",
        "accent": "#8A5A1C", "accent_hi": "#A46A25", "accent_press": "#6B4614",
        "danger": "#B24327", "danger_hi": "#C55538", "danger_press": "#8E351F",
        "scroll_handle": "#C7B37A", "scroll_handle_hover": "#A8925A",
    },
}


def _svg_data_url(svg: str) -> str:
    """Return a Qt-compatible url() argument for an inline SVG."""
    import base64
    b = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b}"


def _arrow_svg(direction: str, color: str) -> str:
    # direction: 'up' | 'down'
    if direction == "up":
        d = "M4 12 L10 6 L16 12"
    else:
        d = "M4 8 L10 14 L16 8"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="none" '
        f'stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
        f'<path d="{d}"/></svg>'
    )


def _build_qss(tokens: Dict[str, str]) -> str:
    out = _QSS_TEMPLATE
    # Theme-tinted arrows for spinbox/combobox (embedded as data URLs so they
    # stay bundled and adapt to every theme automatically).
    stroke = tokens.get("text_hi", "#EDEFF7")
    extras = {
        "spin_up_icon":   _svg_data_url(_arrow_svg("up", stroke)),
        "spin_down_icon": _svg_data_url(_arrow_svg("down", stroke)),
        "combo_down_icon": _svg_data_url(_arrow_svg("down", stroke)),
    }
    merged = {**tokens, **extras}
    for k, v in merged.items():
        out = out.replace("{" + k + "}", v)
    return out


APP_QSS       = _build_qss(_THEME_TOKENS["dark"])
APP_QSS_LIGHT = _build_qss(_THEME_TOKENS["light"])
APP_QSS_SEPIA = _build_qss(_THEME_TOKENS["sepia"])

APP_THEMES: Dict[str, str] = {
    "dark":  APP_QSS,
    "light": APP_QSS_LIGHT,
    "sepia": APP_QSS_SEPIA,
}



def _apply_tooltip_palette(tokens):
    """Force QToolTip to use theme colors on every platform (Qt draws tooltips
    through QPalette even when a stylesheet is present)."""
    try:
        from PyQt5.QtGui import QPalette, QColor
        pal = QToolTip.palette()
        pal.setColor(QPalette.ToolTipBase, QColor(tokens.get("bg2", "#1A1D2C")))
        pal.setColor(QPalette.ToolTipText, QColor(tokens.get("text_hi", "#EDEFF7")))
        QToolTip.setPalette(pal)
        QToolTip.setFont(QApplication.font())
    except Exception:
        pass






def _apply_menu_theme(menu) -> None:
    """Force a QMenu to use the current theme's high-contrast colors, regardless
    of any inherited widget stylesheet that might make it transparent/unreadable.
    """
    try:
        tokens = _THEME_TOKENS.get(APP_THEME, _THEME_TOKENS["dark"])
        menu.setStyleSheet(
            "QMenu { background: %s; color: %s; border: 1px solid %s;"
            "        padding: 6px; border-radius: 12px; }"
            "QMenu::item { padding: 8px 26px 8px 14px; border-radius: 8px;"
            "              color: %s; background: transparent; }"
            "QMenu::item:selected { background: %s; color: %s; }"
            "QMenu::item:disabled { color: %s; }"
            "QMenu::separator { height: 1px; background: %s; margin: 6px 8px; }"
            % (tokens["bg_menu"], tokens["text_hi"], tokens["border"],
               tokens["text_hi"], tokens["bg_hover"], tokens["text_on_hover"],
               tokens["text_lo"], tokens["border"])
        )
    except Exception:
        pass


def apply_app_theme(name: str) -> None:
    """Apply a global theme. Persists selection and re-tints icons."""
    global APP_THEME
    if name not in APP_THEMES:
        name = "dark"
    APP_THEME = name
    _ICON_TINT_CACHE.clear()
    app = QApplication.instance()
    if app is not None:
        app.setStyleSheet(APP_THEMES[name])
        _apply_tooltip_palette(_THEME_TOKENS.get(name, _THEME_TOKENS["dark"]))
        try:
            QSettings("bazzazi", "PDFMaster").setValue("app_theme", name)
        except Exception:
            pass
        # Re-apply icons on every top-level widget so tints update immediately.
        for w in app.topLevelWidgets():
            try:
                apply_semantic_icons(w)
            except Exception:
                pass






# =============================================================================
#  Common helpers
# =============================================================================

def show_error(parent, title: str, msg: str) -> None:
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(title)
    if "\n\n" in msg:
        brief, details = msg.split("\n\n", 1)
    else:
        brief, details = msg, ""
    box.setText(brief or title)
    if details:
        box.setDetailedText(details)
    box.exec_()


def show_info(parent, title: str, msg: str) -> None:
    QMessageBox.information(parent, title, msg)


def confirm(parent, title: str, msg: str) -> bool:
    return QMessageBox.question(
        parent, title, msg, QMessageBox.Yes | QMessageBox.No
    ) == QMessageBox.Yes


def pick_open_pdf(parent) -> Optional[str]:
    path, _ = QFileDialog.getOpenFileName(parent, T("reader_open"), "", "PDF Files (*.pdf)")
    return path or None


def pick_open_pdfs(parent) -> List[str]:
    paths, _ = QFileDialog.getOpenFileNames(parent, T("merge_add"), "", "PDF Files (*.pdf)")
    return paths or []


def pick_save_pdf(parent, default_name: str = "output.pdf",
                  source: Optional[str] = None) -> Optional[str]:
    path, _ = QFileDialog.getSaveFileName(parent, T("saved"), default_name, "PDF Files (*.pdf)")
    if not path:
        return None
    if not path.lower().endswith(".pdf"):
        path += ".pdf"
    if source and os.path.abspath(path) == os.path.abspath(source):
        if not confirm(parent, T("overwrite_source_title"), T("overwrite_source_msg")):
            return None
    return path


def pick_folder(parent) -> Optional[str]:
    path = QFileDialog.getExistingDirectory(parent, T("select_folder"))
    return path or None


def pixmap_from_page(page: "fitz.Page", zoom: float, rotation: int = 0) -> QPixmap:
    """Render a PyMuPDF page to QPixmap safely."""
    pix = page.get_pixmap(matrix=_render_matrix(zoom, rotation), alpha=False)
    return _pixmap_to_qpixmap(pix)


def open_url(url: str) -> None:
    """Open a URL in the user's default browser (Qt-native, works on all OSes)."""
    if not QDesktopServices.openUrl(QUrl(url)):
        try:
            webbrowser.open(url)
        except Exception:
            pass


def _load_pdf_reader(handle, *, allow_encrypted: bool = False):
    """Create a PdfReader with friendlier handling for encrypted or corrupted PDFs."""
    reader = PdfReader(handle)
    if getattr(reader, "is_encrypted", False):
        if allow_encrypted:
            return reader
        try:
            if reader.decrypt("") == 0:
                raise ValueError(T("reader_encrypted"))
        except Exception as exc:
            raise ValueError(T("reader_encrypted")) from exc
    return reader


def _render_matrix(zoom: float, rotation: int = 0) -> fitz.Matrix:
    """Build a safe render matrix for PyMuPDF page rendering."""
    zoom = max(0.05, float(zoom))
    mat = fitz.Matrix(zoom, zoom)
    rotation = int(rotation) % 360
    if rotation:
        mat.prerotate(rotation)
    return mat


def _pixmap_to_qpixmap(pix: "fitz.Pixmap") -> QPixmap:
    """Convert a PyMuPDF pixmap to QPixmap without relying on fragile constructors."""
    data = pix.tobytes("png")
    img = QImage.fromData(data, "PNG")
    if img.isNull():
        # Fallback for unusual Qt builds or malformed PNG byte streams.
        try:
            buffer = bytes(pix.samples)
            if pix.alpha:
                fmt = QImage.Format_RGBA8888
            else:
                fmt = QImage.Format_RGB888
            img = QImage(buffer, pix.width, pix.height, pix.stride, fmt).copy()
        except Exception:
            img = QImage()
    if img.isNull():
        raise ValueError("Unable to render the PDF page preview.")
    return QPixmap.fromImage(img)


def _normalize_label(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return text


def _style_icon(fallback: QStyle.StandardPixmap) -> QIcon:
    app = QApplication.instance()
    style = app.style() if app else None
    return style.standardIcon(fallback) if style else QIcon()


def _icon_from_names(*names: str, fallback: QStyle.StandardPixmap = QStyle.SP_FileIcon,
                     color: Optional[str] = None) -> QIcon:
    for name in names:
        icon = _local_icon(name, color=color)
        if not icon.isNull():
            return icon
    return _style_icon(fallback)


def _semantic_icon_candidates() -> List[tuple]:
    # Matched against current-language labels, tooltips and some common glyph-only buttons.
    return [
        ("reader_open", (_icon_from_names("document-open", "folder-open"), QStyle.SP_DialogOpenButton)),
        ("reader_recent", (_icon_from_names("document-open-recent", "history"), QStyle.SP_DirOpenIcon)),
        ("reader_sidebar", (_icon_from_names("view-sidebar", "sidebar-show", "view-list-details"), QStyle.SP_FileDialogDetailedView)),
        ("reader_rotate_l", (_icon_from_names("object-rotate-left", "rotate-left"), QStyle.SP_BrowserReload)),
        ("reader_rotate_r", (_icon_from_names("object-rotate-right", "rotate-right"), QStyle.SP_BrowserReload)),
        ("reader_prev", (_icon_from_names("go-previous", "arrow-left"), QStyle.SP_ArrowBack)),
        ("reader_next", (_icon_from_names("go-next", "arrow-right"), QStyle.SP_ArrowForward)),
        ("reader_zoom_in", (_icon_from_names("zoom-in"), QStyle.SP_FileDialogDetailedView)),
        ("reader_zoom_out", (_icon_from_names("zoom-out"), QStyle.SP_FileDialogDetailedView)),
        ("reader_hand", (_icon_from_names("pan-tool", "input-touchpad", "edit-select-all"), QStyle.SP_ArrowUp)),
        ("reader_continuous", (_icon_from_names("view-list-text"), QStyle.SP_FileDialogDetailedView)),
        ("reader_search", (_icon_from_names("edit-find", "search"), QStyle.SP_FileDialogContentsView)),
        ("reader_present", (_icon_from_names("view-fullscreen", "view-expand"), QStyle.SP_TitleBarMaxButton)),
        ("reader_tab_thumbs", (_icon_from_names("view-preview", "view-grid"), QStyle.SP_FileDialogInfoView)),
        ("reader_tab_outline", (_icon_from_names("view-list-tree", "outline"), QStyle.SP_FileDialogListView)),
        ("reader_tab_search", (_icon_from_names("edit-find", "search"), QStyle.SP_FileDialogContentsView)),
        ("reader_recent_clear", (_icon_from_names("edit-clear-history", "user-trash"), QStyle.SP_TrashIcon)),
        ("merge_add", (_icon_from_names("list-add", "document-open", "folder-open"), QStyle.SP_DialogOpenButton)),
        ("merge_remove", (_icon_from_names("edit-delete", "user-trash"), QStyle.SP_TrashIcon)),
        ("merge_clear", (_icon_from_names("edit-clear", "edit-delete"), QStyle.SP_DialogResetButton)),
        ("merge_do", (_icon_from_names("edit-copy", "document-save-as", "merge"), QStyle.SP_DialogSaveButton)),
        ("split_do", (_icon_from_names("application-x-executable", "scissors"), QStyle.SP_FileDialogContentsView)),
        ("move_up", (_icon_from_names("go-up", "arrow-up"), QStyle.SP_ArrowUp)),
        ("move_down", (_icon_from_names("go-down", "arrow-down"), QStyle.SP_ArrowDown)),
        ("compress_do", (_icon_from_names("document-save", "archive"), QStyle.SP_DialogSaveButton)),
        ("extract_text_btn", (_icon_from_names("document-text", "text-x-generic"), QStyle.SP_FileIcon)),
        ("extract_save_text", (_icon_from_names("document-save", "save"), QStyle.SP_DialogSaveButton)),
        ("extract_images", (_icon_from_names("image-x-generic", "folder-pictures"), QStyle.SP_FileDialogContentsView)),
        ("extract_pages_png", (_icon_from_names("image-x-generic", "media-record"), QStyle.SP_FileDialogContentsView)),
        ("organize_rot_l", (_icon_from_names("object-rotate-left", "rotate-left"), QStyle.SP_BrowserReload)),
        ("organize_rot_r", (_icon_from_names("object-rotate-right", "rotate-right"), QStyle.SP_BrowserReload)),
        ("organize_rot_2", (_icon_from_names("view-refresh", "rotate"), QStyle.SP_BrowserReload)),
        ("organize_delete", (_icon_from_names("edit-delete", "user-trash"), QStyle.SP_TrashIcon)),
        ("organize_save", (_icon_from_names("document-save", "save"), QStyle.SP_DialogSaveButton)),
        ("security_encrypt_group", (_icon_from_names("lock", "object-locked"), QStyle.SP_MessageBoxWarning)),
        ("security_decrypt_group", (_icon_from_names("unlock", "object-unlocked"), QStyle.SP_MessageBoxInformation)),
        ("security_enc_do", (_icon_from_names("lock", "document-save"), QStyle.SP_DialogSaveButton)),
        ("security_dec_do", (_icon_from_names("unlock", "document-open"), QStyle.SP_DialogOpenButton)),
        ("watermark_do", (_icon_from_names("format-text-color", "draw-freehand", "watermark"), QStyle.SP_FileDialogDetailedView)),
        ("metadata_save", (_icon_from_names("document-save", "help-about"), QStyle.SP_DialogSaveButton)),
        ("about_github", (_icon_from_names("link", "internet-web-browser"), QStyle.SP_DialogOpenButton)),
        ("about_website", (_icon_from_names("link", "internet-web-browser"), QStyle.SP_DialogOpenButton)),
        ("about_linkedin", (_icon_from_names("link", "internet-web-browser"), QStyle.SP_DialogOpenButton)),
        ("menu_exit", (_icon_from_names("application-exit", "window-close"), QStyle.SP_TitleBarCloseButton)),
        ("menu_about", (_icon_from_names("help-about", "dialog-information"), QStyle.SP_MessageBoxInformation)),
        ("menu_language", (_icon_from_names("preferences-desktop-locale", "preferences-system-language"), QStyle.SP_FileDialogDetailedView)),
        ("about_close", (_icon_from_names("window-close", "application-exit"), QStyle.SP_TitleBarCloseButton)),
        ("nav_reader", (_icon_from_names("view-readme", "document-open"), QStyle.SP_FileIcon)),
        ("nav_merge", (_icon_from_names("insert-link", "document-merge"), QStyle.SP_FileIcon)),
        ("nav_split", (_icon_from_names("scissors", "edit-cut"), QStyle.SP_FileIcon)),
        ("nav_compress", (_icon_from_names("archive", "view-restore"), QStyle.SP_FileIcon)),
        ("nav_extract", (_icon_from_names("document-export", "folder-pictures"), QStyle.SP_FileIcon)),
        ("nav_organize", (_icon_from_names("view-sort-ascending", "view-list-tree"), QStyle.SP_FileIcon)),
        ("nav_security", (_icon_from_names("lock", "security-high"), QStyle.SP_FileIcon)),
        ("nav_watermark", (_icon_from_names("draw-freehand", "format-text-italic"), QStyle.SP_FileIcon)),
        ("nav_metadata", (_icon_from_names("document-properties", "help-about"), QStyle.SP_FileIcon)),
        ("nav_about", (_icon_from_names("help-about", "user-info"), QStyle.SP_FileIcon)),
        ("reader_pin", (_icon_from_names("view-pin", "emblem-important", "bookmark-new"), QStyle.SP_DialogApplyButton)),
        ("reader_pin_off", (_icon_from_names("view-pin", "bookmark-new", "document-properties"), QStyle.SP_DialogResetButton)),
        ("reader_autoscroll", (_icon_from_names("media-playback-start"), QStyle.SP_MediaPlay)),
        ("reader_autoscroll_pause", (_icon_from_names("media-playback-pause"), QStyle.SP_MediaPause)),
        ("reader_autoscroll_speed", (_icon_from_names("chronometer"), QStyle.SP_MediaSeekForward)),
        ("browse", (_icon_from_names("folder-open", "document-open"), QStyle.SP_DirOpenIcon)),
        ("open", (_icon_from_names("document-open"), QStyle.SP_DialogOpenButton)),
        ("prev", (_icon_from_names("go-previous", "back"), QStyle.SP_ArrowBack)),
        ("next", (_icon_from_names("go-next", "forward"), QStyle.SP_ArrowForward)),
        ("zoom_in", (_icon_from_names("zoom-in"), QStyle.SP_ArrowUp)),
        ("zoom_out", (_icon_from_names("zoom-out"), QStyle.SP_ArrowDown)),
        ("close", (_icon_from_names("window-close", "dialog-close"), QStyle.SP_TitleBarCloseButton)),
        ("add", (_icon_from_names("list-add", "document-new"), QStyle.SP_FileDialogNewFolder)),
        ("remove", (_icon_from_names("edit-delete", "user-trash"), QStyle.SP_TrashIcon)),
        ("save", (_icon_from_names("document-save", "save"), QStyle.SP_DialogSaveButton)),
    ]


def _set_widget_icon(widget, icon: QIcon) -> None:
    if icon.isNull():
        return
    try:
        widget.setIcon(icon)
        _sync_widget_icon_metrics(widget)
    except Exception:
        pass


def _sync_widget_icon_metrics(widget) -> None:
    """Keep icon-only buttons visually balanced so icons do not spill out."""
    try:
        if not isinstance(widget, QPushButton):
            return
        text = (widget.text() or "").strip()
        icon_only = bool(widget.property("iconOnly")) or not text
        # Uniform, generous icon size across all themes; the QSS makes icon
        # buttons at least 38x38 so a 20px glyph reads clearly.
        size = 20 if icon_only else 18
        widget.setIconSize(QSize(size, size))
    except Exception:
        pass


def _should_icon_only(widget, text: str, tooltip: str = "") -> bool:
    """Decide whether a button should be icon-only because it has too little space."""
    try:
        if bool(widget.property("iconOnly")):
            return True
    except Exception:
        pass
    width = 0
    try:
        width = int(widget.width() or 0)
    except Exception:
        width = 0
    label = (text or "").strip()
    if not label and tooltip:
        label = tooltip.strip()
    if width and width <= 60:
        return True
    if len(label) <= 2 and label:
        return True
    if label in {"◀", "▶", "+", "−", "-", "⟲", "⟳", "✋", "☰", "☰↕", "🔍", "⛶", "✕", "▾", "📂"}:
        return True
    return False


def _semantic_key_for_text(text: str, tooltip: str = "") -> Optional[str]:
    raw = f"{text} {tooltip}"
    norm = _normalize_label(raw)
    if not norm:
        return None
    # Exact glyph-only / toolbar cases first.
    glyph_map = {
        "+": "zoom_in",
        "−": "zoom_out",
        "-": "zoom_out",
        "⟲": "reader_rotate_l",
        "⟳": "reader_rotate_r",
        "✋": "reader_hand",
        "☰": "reader_sidebar",
        "☰↕": "reader_continuous",
        "🔍": "reader_search",
        "⛶": "reader_present",
        "✕": "close",
        "↑": "move_up",
        "↓": "move_down",
        "➕": "add",
        "🗑": "remove",
        "✂": "split_do",
        "🗜": "compress_do",
        "📄": "extract_text_btn",
        "💾": "save",
        "🖼": "extract_images",
        "🎞": "extract_pages_png",
        "🔒": "security_encrypt_group",
        "🔓": "security_decrypt_group",
        "💧": "watermark_do",
        "ℹ": "metadata_save",
        "▾": "reader_recent",
        "📂": "reader_open",
        "🔗": "about_github",
    }
    t = text.strip()
    if t in glyph_map:
        return glyph_map[t]
    # Current-language labels / tooltips.
    # Build from current i18n keys we care about.
    keys = [
        "reader_open", "reader_recent", "reader_sidebar", "reader_pin", "reader_pin_off", "reader_autoscroll", "reader_autoscroll_pause", "reader_autoscroll_speed", "reader_rotate_l", "reader_rotate_r",
        "reader_hand", "reader_continuous", "reader_search", "reader_present", "reader_tab_thumbs",
        "reader_tab_outline", "reader_tab_search", "reader_recent_clear", "merge_add", "merge_remove",
        "merge_clear", "merge_do", "split_do", "compress_do", "extract_text_btn", "extract_save_text",
        "extract_images", "extract_pages_png", "organize_rot_l", "organize_rot_r", "organize_rot_2",
        "organize_delete", "organize_save", "security_enc_do", "security_dec_do", "watermark_do",
        "metadata_save", "about_github", "about_website", "about_linkedin", "menu_exit", "menu_about",
        "menu_language", "nav_reader", "nav_merge", "nav_split", "nav_compress", "nav_extract",
        "nav_organize", "nav_security", "nav_watermark", "nav_metadata", "nav_about", "browse",
        "reader_fit", "reader_fit_page", "reader_actual", "reader_recent_clear", "about_close",
    ]
    for key in keys:
        label = _normalize_label(T(key))
        if label and label in norm:
            return key
    # Some English-only words still help when translations are unavailable.
    english_keywords = {
        "open": "reader_open", "recent": "reader_recent", "sidebar": "reader_sidebar",
        "previous": "prev", "next": "next", "zoom": "zoom_in", "rotate": "reader_rotate_r",
        "search": "reader_search", "fullscreen": "reader_present", "thumb": "reader_tab_thumbs",
        "outline": "reader_tab_outline", "merge": "merge_do", "split": "split_do", "compress": "compress_do",
        "extract": "extract_text_btn", "organize": "organize_save", "security": "security_enc_do",
        "moveup": "move_up", "movedown": "move_down",
        "watermark": "watermark_do", "metadata": "metadata_save", "browse": "browse", "save": "save",
        "close": "close", "about": "menu_about", "language": "menu_language", "github": "about_github",
        "website": "about_website", "linkedin": "about_linkedin", "delete": "remove", "remove": "remove",
        "add": "add", "clear": "merge_clear", "info": "menu_about", "lock": "security_enc_do",
        "unlock": "security_dec_do", "page": "extract_pages_png", "image": "extract_images",
    }
    for needle, key in english_keywords.items():
        if needle in norm:
            return key
    return None


def _icon_for_key(key: str, widget=None, color: Optional[str] = None) -> QIcon:
    """Return the icon registered for `key`, tinted for the given widget's role."""
    # Reuse the candidate list only for the names + fallback; rebuild icons with
    # the requested tint so accent/danger buttons always show a white glyph.
    for candidate_key, (icon, fallback) in _semantic_icon_candidates():
        if candidate_key == key:
            # Rebuild with per-widget color when provided
            if color is not None:
                # Extract the SVG name from the same registry
                names = _KEY_TO_SVG_NAMES.get(key, ())
                for n in names:
                    ic = _local_icon(n, color=color)
                    if not ic.isNull():
                        return ic
            if icon and not icon.isNull():
                return icon
            style = widget.style() if widget else (QApplication.instance().style() if QApplication.instance() else None)
            return style.standardIcon(fallback) if style else QIcon()
    return QIcon()


def apply_semantic_icons(widget) -> None:
    """Assign icons to buttons and actions using current localized labels/tooltip text."""
    children = []
    try:
        children.extend(widget.findChildren(QPushButton))
    except Exception:
        pass
    try:
        children.extend(widget.findChildren(QAction))
    except Exception:
        pass
    for child in children:
        try:
            text = child.text() if hasattr(child, "text") else ""
            tooltip = child.toolTip() if hasattr(child, "toolTip") else ""
            key = _semantic_key_for_text(text, tooltip)
            if not key:
                continue
            # Per-widget tint: primary/danger buttons need white icons; others
            # follow the theme's foreground color. QActions use theme default.
            if isinstance(child, QPushButton):
                tint = _icon_color_for_widget(child)
            else:
                tint = _theme_icon_color()
            icon = _icon_for_key(key, widget if not isinstance(child, QAction) else None, color=tint)
            _set_widget_icon(child, icon)

            if isinstance(child, QPushButton):
                _sync_widget_icon_metrics(child)
                if not tooltip and text:
                    try:
                        child.setToolTip(text)
                    except Exception:
                        pass
                if _should_icon_only(child, text, tooltip):
                    try:
                        child.setProperty("iconOnly", True)
                        child.setText("")
                        child.setToolTip(tooltip or text or child.toolTip())
                        child.setAccessibleName(tooltip or text)
                        # Icon-only variant lives on a neutral surface -> re-tint.
                        ic2 = _icon_for_key(key, widget, color=_theme_icon_color())
                        if not ic2.isNull():
                            _set_widget_icon(child, ic2)
                        if child.style():
                            child.style().unpolish(child)
                            child.style().polish(child)
                    except Exception:
                        pass
        except Exception:
            continue


# Extract the SVG name registry from _semantic_icon_candidates so we can
# re-tint icons per widget without rebuilding QIcon objects from scratch.
_KEY_TO_SVG_NAMES: Dict[str, tuple] = {}


def _register_svg_names() -> None:
    """Populate _KEY_TO_SVG_NAMES from _semantic_icon_candidates definitions."""
    import inspect
    src = inspect.getsource(_semantic_icon_candidates)
    # Find every `("key", (_icon_from_names("a", "b", ...), ...))` entry.
    for m in re.finditer(r'\("([^"]+)",\s*\(_icon_from_names\(([^)]+)\)', src):
        key = m.group(1)
        raw = m.group(2)
        names = tuple(n.strip().strip('"').strip("'") for n in raw.split(",")
                      if n.strip() and not n.strip().startswith("fallback"))
        _KEY_TO_SVG_NAMES[key] = names


_register_svg_names()

# =============================================================================
#  Background worker
# =============================================================================

class Worker(QThread):
    """Runs a callable off the UI thread and reports progress + result."""
    progress = pyqtSignal(int, int, str)     # done, total, message
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            def report(done: int, total: int, msg: str = ""):
                self.progress.emit(done, total, msg)
            result = self._fn(report)
            self.finished_ok.emit(result)
        except Exception as e:
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")

# =============================================================================
#  Base page
# =============================================================================

class BasePage(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: Optional[Worker] = None
        self.progress = QProgressBar()
        self.progress.setVisible(False)

    def run_async(self, fn: Callable, on_success: Callable[[object], None],
                  busy_message: str = "") -> None:
        busy_message = busy_message or T("working")
        if self._worker and self._worker.isRunning():
            show_info(self, T("busy"), T("busy_msg"))
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.progress.setFormat(busy_message)
        self.setEnabled(False)
        w = Worker(fn)
        self._worker = w

        def _prog(done: int, total: int, msg: str):
            if total > 0:
                self.progress.setRange(0, total)
                self.progress.setValue(done)
            self.progress.setFormat(msg or busy_message)

        def _done(result):
            self.progress.setVisible(False)
            self.setEnabled(True)
            self._worker = None
            try:
                w.deleteLater()
            except Exception:
                pass
            on_success(result)

        def _fail(err: str):
            self.progress.setVisible(False)
            self.setEnabled(True)
            self._worker = None
            try:
                w.deleteLater()
            except Exception:
                pass
            show_error(self, T("operation_failed"), err)

        w.progress.connect(_prog)
        w.finished_ok.connect(_done)
        w.failed.connect(_fail)
        w.start()

# =============================================================================
#  Loading overlay — animated spinner shown while a PDF is opening
# =============================================================================

class LoadingOverlay(QWidget):
    """Translucent overlay with an animated indigo arc + caption.

    Used to give the user a professional, responsive "opening" affordance
    while a heavy PDF is being decoded and its first page rendered.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._angle = 0
        try:
            self._message = T("reader_loading")
        except Exception:
            self._message = "Opening PDF…"
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._tick)
        self.hide()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def set_message(self, msg: str):
        self._message = msg
        self.update()

    def start(self, message: Optional[str] = None):
        if message:
            self._message = message
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        self.raise_()
        self.show()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        self.hide()

    def resizeEvent(self, e):
        if self.parent() is not None:
            self.setGeometry(self.parent().rect())
        super().resizeEvent(e)

    def paintEvent(self, e):
        from PyQt5.QtGui import QPainter, QColor, QPen, QFont
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # Backdrop
        p.fillRect(self.rect(), QColor(11, 13, 20, 190))
        # Spinner geometry
        cx = self.width() // 2
        cy = self.height() // 2
        r = 34
        rect = QRect(cx - r, cy - r, 2 * r, 2 * r)
        # Track
        pen = QPen(QColor(255, 255, 255, 38))
        pen.setWidth(5); pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawEllipse(rect)
        # Arc (accent indigo)
        pen2 = QPen(QColor(109, 124, 255))
        pen2.setWidth(5); pen2.setCapStyle(Qt.RoundCap)
        p.setPen(pen2)
        span = 110 * 16
        start = -self._angle * 16
        p.drawArc(rect, start, span)
        # Caption
        p.setPen(QColor(237, 239, 247))
        f = QFont(); f.setPointSize(11); f.setBold(True)
        p.setFont(f)
        text_rect = QRect(0, cy + r + 18, self.width(), 30)
        p.drawText(text_rect, Qt.AlignHCenter | Qt.AlignTop, self._message)
        # Subtle sub-caption
        p.setPen(QColor(168, 174, 203))
        f2 = QFont(); f2.setPointSize(9)
        p.setFont(f2)
        sub_rect = QRect(0, cy + r + 44, self.width(), 24)
        p.drawText(sub_rect, Qt.AlignHCenter | Qt.AlignTop, "…")
        p.end()


# =============================================================================
#  Reader
# =============================================================================


class _PageLabel(QLabel):
    """A QLabel that displays a rendered PDF page and lazily renders on demand.

    Supports drag-to-select text (word based) with copy & highlight actions.
    Only accurate when rotation == 0 (matches search-highlight behavior).
    """

    def __init__(self, viewer: "PdfViewer", page_index: int):
        super().__init__()
        self.viewer = viewer
        self.page_index = page_index
        self.rendered_zoom: float = 0.0
        self.rendered_rot: int = -1
        self.words: list = []  # list[(fitz.Rect_pdf, str)]
        self._sel_start = None
        self._sel_end = None
        self._selecting = False
        self.setAlignment(Qt.AlignCenter)
        # Scope the transparent background to this QLabel only so it does NOT
        # cascade into child popups (QMenu inherits the parent QSS otherwise,
        # which made the right-click menu unreadable — transparent bg + no text
        # contrast). Keeping the selector precise fixes that class of bugs.
        self.setStyleSheet("QLabel { background: transparent; }")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)

    def sizeHint(self):
        return self.size()

    def mousePressEvent(self, ev):
        if self.viewer.hand_mode or ev.button() != Qt.LeftButton:
            return super().mousePressEvent(ev)
        self._sel_start = ev.pos()
        self._sel_end = ev.pos()
        self._selecting = True
        self.viewer._active_label = self
        self.update()

    def mouseMoveEvent(self, ev):
        if self._selecting:
            self._sel_end = ev.pos()
            self.update()
        else:
            super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._selecting:
            self._sel_end = ev.pos()
            self._selecting = False
            self.update()
        else:
            super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        # double-click selects & copies the word under the cursor
        if self.rendered_zoom <= 0 or not self.words:
            return super().mouseDoubleClickEvent(ev)
        z = self.rendered_zoom
        x = ev.pos().x() / z
        y = ev.pos().y() / z
        for wr, txt in self.words:
            if wr.x0 <= x <= wr.x1 and wr.y0 <= y <= wr.y1:
                # build a selection rectangle in widget coords that hits this word
                from PyQt5.QtCore import QPoint as _QP
                self._sel_start = _QP(int(wr.x0 * z) + 1, int(wr.y0 * z) + 1)
                self._sel_end   = _QP(int(wr.x1 * z) - 1, int(wr.y1 * z) - 1)
                self.viewer._active_label = self
                try:
                    QApplication.clipboard().setText(txt)
                except Exception:
                    pass
                self.update()
                break


    def selected_rect_pdf(self):
        if self._sel_start is None or self._sel_end is None or self.rendered_zoom <= 0:
            return None
        z = self.rendered_zoom
        x0 = min(self._sel_start.x(), self._sel_end.x()) / z
        y0 = min(self._sel_start.y(), self._sel_end.y()) / z
        x1 = max(self._sel_start.x(), self._sel_end.x()) / z
        y1 = max(self._sel_start.y(), self._sel_end.y()) / z
        try:
            import fitz as _f
            return _f.Rect(x0, y0, x1, y1)
        except Exception:
            return (x0, y0, x1, y1)

    def selected_words(self):
        r = self.selected_rect_pdf()
        if r is None or not self.words:
            return []
        try:
            x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
        except AttributeError:
            x0, y0, x1, y1 = r
        out = []
        for wr, txt in self.words:
            cx = (wr.x0 + wr.x1) / 2
            cy = (wr.y0 + wr.y1) / 2
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                out.append((wr, txt))
        return out

    def selected_text(self) -> str:
        return " ".join(t for _, t in self.selected_words()).strip()

    def clear_selection(self):
        self._sel_start = None
        self._sel_end = None
        self.update()

    def _show_menu(self, pos):
        menu = QMenu(self.viewer)
        # Force a solid, high-contrast palette regardless of any inherited QSS
        # (fixes previously-unreadable transparent right-click menu).
        _tokens = _THEME_TOKENS.get(APP_THEME, _THEME_TOKENS["dark"])
        menu.setStyleSheet(
            "QMenu { background: %s; color: %s; border: 1px solid %s;"
            "        padding: 6px; border-radius: 12px; }"
            "QMenu::item { padding: 8px 26px 8px 14px; border-radius: 8px;"
            "              color: %s; background: transparent; }"
            "QMenu::item:selected { background: %s; color: %s; }"
            "QMenu::separator { height: 1px; background: %s; margin: 6px 8px; }"
            "QMenu::icon { padding-left: 10px; }"
            % (_tokens["bg_menu"], _tokens["text_hi"], _tokens["border"],
               _tokens["text_hi"], _tokens["bg_hover"], _tokens["text_on_hover"],
               _tokens["border"])
        )
        act_copy = menu.addAction(_icon_for_key("save", self) if False else _icon_from_names("edit-copy"), T("reader_copy"))
        act_hl   = menu.addAction(_icon_from_names("format-text-color", "draw-freehand"), T("reader_highlight"))
        menu.addSeparator()
        act_clear = menu.addAction(_icon_from_names("edit-clear", "user-trash"), T("reader_clear_highlights"))
        act_save  = menu.addAction(_icon_from_names("document-save", "save"), T("reader_save_annot"))
        chosen = menu.exec_(self.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is act_copy:
            txt = self.selected_text()
            if txt:
                QApplication.clipboard().setText(txt)
            else:
                show_info(self.viewer, T("app_name"), T("reader_no_selection"))
        elif chosen is act_hl:
            words = self.selected_words()
            if not words:
                show_info(self.viewer, T("app_name"), T("reader_no_selection"))
            else:
                self.viewer._add_highlights(self.page_index, [w for w, _ in words])
                self.clear_selection()
        elif chosen is act_clear:
            self.viewer._clear_highlights(self.page_index)
        elif chosen is act_save:
            self.viewer.save_with_highlights()

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self.rendered_zoom <= 0:
            return
        z = self.rendered_zoom
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        # Saved highlights (canary yellow, semi-transparent)
        hls = self.viewer._highlights.get(self.page_index, [])
        if hls:
            painter.setBrush(QColor(255, 220, 40, 110))
            for r in hls:
                painter.drawRect(int(r.x0 * z), int(r.y0 * z),
                                 max(2, int((r.x1 - r.x0) * z)),
                                 max(2, int((r.y1 - r.y0) * z)))
        # Live selection (indigo tint)
        if self._sel_start is not None and self._sel_end is not None:
            painter.setBrush(QColor(109, 124, 255, 90))
            for wr, _t in self.selected_words():
                painter.drawRect(int(wr.x0 * z), int(wr.y0 * z),
                                 max(2, int((wr.x1 - wr.x0) * z)),
                                 max(2, int((wr.y1 - wr.y0) * z)))
        painter.end()




class PdfViewer(BasePage):
    """
    Advanced PDF reader.
    Features: full-screen presentation mode, thumbnails & outline sidebars,
    text search with highlights, day/night/sepia themes, single / continuous
    layout, arbitrary rotation, page jump, hand-drag pan, recent files,
    per-document last-page memory and a rich keyboard shortcut set.
    """

    THEMES = {
        "day":   {"bg": "#ECEEF3", "page": "#FFFFFF"},   # light canvas, white page (light mode)
        "night": {"bg": "#0B0D14", "page": "#1E2033"},
        "sepia": {"bg": "#2A2418", "page": "#F6ECD3"},
    }

    def __init__(self):
        super().__init__()
        self.doc: Optional[fitz.Document] = None
        self.current_path: Optional[str] = None
        self.current_page: int = 0
        self.zoom: float = 1.25
        self.fit_mode: str = "width"          # "width" | "page" | "custom"
        self.rotation: int = 0                # 0/90/180/270
        self.layout_mode: str = "single"      # "single" | "continuous"
        self.theme: str = "day"
        self.hand_mode: bool = False
        self.sidebar_visible: bool = True
        self.settings = QSettings("bazzazi", "PDFMaster")
        self._page_labels: List[_PageLabel] = []
        self._search_hits: List[tuple] = []   # (page_idx, fitz.Rect)
        self._search_current: int = -1
        self._search_query: str = ""
        self._scroll_lock = False
        self._panning = False
        self._pan_start = None
        self._main_sidebar_visible_before_fullscreen: Optional[bool] = None
        self._highlights: dict = {}          # {page_idx: [fitz.Rect, ...]}
        self._active_label: Optional[_PageLabel] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(6)
        self.setAcceptDrops(True)


        title = QLabel(T("reader_title")); title.setObjectName("PageTitle")
        self._header = QWidget()
        hl = QVBoxLayout(self._header); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(0)
        hl.addWidget(title)
        root.addWidget(self._header)

        # ---- Toolbar --------------------------------------------------------
        # Modernised: uniform 38px icon buttons, logical groups with hairline
        # separators, and clean spacing that reflows via FlowLayout.
        self.toolbar = QWidget()
        tb = FlowLayout(self.toolbar, margin=0, hspacing=6, vspacing=6)

        ICON_BTN_W = 38  # uniform toolbar icon size

        def _mkbtn(tip: str, *, checkable: bool = False, width: int = ICON_BTN_W,
                   with_menu: bool = False) -> QPushButton:
            b = QPushButton()
            b.setObjectName("Secondary")
            b.setProperty("iconOnly", True)
            b.setFixedWidth(width)
            b.setFixedHeight(ICON_BTN_W)
            b.setCheckable(checkable)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self.open_btn = QPushButton(T("reader_open"))
        self.open_btn.setToolTip(T("reader_open"))
        # Smaller, icon-forward primary Open button (was 130px, now 96px).
        self.open_btn.setMinimumWidth(96)
        self.open_btn.setMaximumWidth(140)
        self.open_btn.setFixedHeight(ICON_BTN_W)
        self.open_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.clicked.connect(lambda: self.open_pdf())

        self.recent_btn = _mkbtn(T("reader_recent"))
        self.recent_menu = QMenu(self); self.recent_btn.setMenu(self.recent_menu)
        _apply_menu_theme(self.recent_menu)
        self._rebuild_recent_menu()

        self.sidebar_btn = _mkbtn(T("reader_sidebar"), checkable=True)
        self.sidebar_btn.setChecked(True)
        self.sidebar_btn.clicked.connect(self.toggle_sidebar)

        self.prev_btn = _mkbtn(T("reader_prev"))
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn = _mkbtn(T("reader_next"))
        self.next_btn.clicked.connect(self.next_page)

        self.page_spin = QSpinBox(); self.page_spin.setMinimum(1); self.page_spin.setMaximum(1)
        self.page_spin.setFixedWidth(72); self.page_spin.setFixedHeight(ICON_BTN_W)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setToolTip(T("reader_goto"))
        self.page_spin.editingFinished.connect(self._goto_from_spin)
        self.page_total = QLabel("/ —"); self.page_total.setObjectName("PageIndicator")
        self.page_total.setMinimumWidth(52); self.page_total.setFixedHeight(38); self.page_total.setAlignment(Qt.AlignCenter)

        self.zoom_out_btn = _mkbtn(T("reader_zoom_out"))
        self.zoom_out_btn.clicked.connect(lambda: self.set_zoom(self.zoom - 0.15))

        self.zoom_combo = QComboBox(); self.zoom_combo.setFixedWidth(120)
        self.zoom_combo.setFixedHeight(ICON_BTN_W); self.zoom_combo.setEditable(False)
        self._zoom_presets = [("50%", 0.5), ("75%", 0.75), ("100%", 1.0),
                              ("125%", 1.25), ("150%", 1.5), ("200%", 2.0),
                              ("300%", 3.0), ("400%", 4.0)]
        for lbl, _ in self._zoom_presets:
            self.zoom_combo.addItem(lbl)
        self.zoom_combo.addItem(T("reader_fit"));      # fit width
        self.zoom_combo.addItem(T("reader_fit_page")); # fit page
        self.zoom_combo.addItem(T("reader_actual"))
        self.zoom_combo.setCurrentIndex(3)
        self.zoom_combo.activated.connect(self._zoom_combo_changed)

        self.zoom_in_btn = _mkbtn(T("reader_zoom_in"))
        self.zoom_in_btn.clicked.connect(lambda: self.set_zoom(self.zoom + 0.15))

        self.rot_l_btn = _mkbtn(T("reader_rotate_l"))
        self.rot_l_btn.clicked.connect(lambda: self.rotate(-90))
        self.rot_r_btn = _mkbtn(T("reader_rotate_r"))
        self.rot_r_btn.clicked.connect(lambda: self.rotate(90))

        self.hand_btn = _mkbtn(T("reader_hand"), checkable=True)
        self.hand_btn.clicked.connect(self._toggle_hand)

        self.layout_btn = _mkbtn(T("reader_continuous"), checkable=True)
        self.layout_btn.clicked.connect(self._toggle_layout)

        self.theme_combo = QComboBox(); self.theme_combo.setFixedWidth(120)
        self.theme_combo.setFixedHeight(ICON_BTN_W)
        self.theme_combo.addItems([T("reader_theme_day"), T("reader_theme_night"), T("reader_theme_sepia")])
        self.theme_combo.setToolTip(T("reader_theme"))
        self.theme_combo.currentIndexChanged.connect(self._theme_changed)

        # NOTE: the standalone search toolbar button was removed (Ctrl+F opens
        # the search bar and the sidebar already exposes a Search tab).

        self.present_btn = _mkbtn(T("reader_present"))
        self.present_btn.clicked.connect(self.toggle_fullscreen)

        # Pin toolbar (visible only in fullscreen; when off, toolbar auto-hides)
        self.pin_btn = _mkbtn(T("reader_pin"), checkable=True)
        self.pin_btn.setChecked(True)
        self.pin_btn.clicked.connect(self._toggle_pin)

        # Auto-scroll (play/pause) + speed
        self.autoscroll_btn = _mkbtn(T("reader_autoscroll"), checkable=True)
        self.autoscroll_btn.clicked.connect(self._toggle_autoscroll)
        self.autoscroll_speed = QSpinBox()
        self.autoscroll_speed.setRange(1, 30); self.autoscroll_speed.setValue(3)
        self.autoscroll_speed.setFixedWidth(58)
        self.autoscroll_speed.setFixedHeight(ICON_BTN_W)
        self.autoscroll_speed.setToolTip(T("reader_autoscroll_speed"))
        self._autoscroll_timer = QTimer(self); self._autoscroll_timer.setInterval(30)
        self._autoscroll_timer.timeout.connect(self._autoscroll_tick)

        def _sep() -> QFrame:
            s = QFrame(); s.setObjectName("ToolbarSeparator")
            s.setFrameShape(QFrame.NoFrame); s.setFixedHeight(ICON_BTN_W - 8)
            return s

        # Grouped toolbar: file · nav · zoom · view · session
        # Duplicate / niche tools (hand-drag, auto-scroll + speed, pin toggle)
        # are hidden from the toolbar for a cleaner, modern layout — their
        # objects still exist so the rest of the code can toggle them safely.
        for _hidden in (self.hand_btn, self.autoscroll_btn,
                        self.autoscroll_speed, self.pin_btn):
            _hidden.setVisible(False)
        # Keep the toolbar always visible in fullscreen (pin defaults ON).
        self.pin_btn.setChecked(True)

        for w in (self.open_btn, self.recent_btn, self.sidebar_btn, _sep(),
                  self.prev_btn, self.page_spin, self.page_total, self.next_btn, _sep(),
                  self.zoom_out_btn, self.zoom_combo, self.zoom_in_btn, _sep(),
                  self.rot_l_btn, self.rot_r_btn, self.layout_btn, _sep(),
                  self.theme_combo, self.present_btn):
            tb.addWidget(w)
        root.addWidget(self.toolbar)


        # Debounced resize + fullscreen auto-hide timers
        self._resize_debounce = QTimer(self); self._resize_debounce.setSingleShot(True)
        self._resize_debounce.setInterval(160)
        self._resize_debounce.timeout.connect(self._on_resize_finished)
        self._fs_hide_timer = QTimer(self); self._fs_hide_timer.setSingleShot(True)
        self._fs_hide_timer.setInterval(2200)
        self._fs_hide_timer.timeout.connect(self._maybe_hide_toolbar_in_fullscreen)
        # Polls the cursor while in fullscreen so we can reveal the auto-hidden
        # toolbar no matter which child widget the mouse is currently over.
        self._fs_reveal_poll = QTimer(self); self._fs_reveal_poll.setInterval(120)
        self._fs_reveal_poll.timeout.connect(self._fs_reveal_poll_tick)
        self._toolbar_pinned = True

        # Loading overlay (animated spinner) — created here so it can be
        # shown/hidden by open_pdf() and stays properly sized via resizeEvent.
        self._loading_overlay = LoadingOverlay(self)


        # ---- Body: sidebar + viewport --------------------------------------
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(6)

        self.side_tabs = QWidget(); self.side_tabs.setFixedWidth(240)
        st = QVBoxLayout(self.side_tabs); st.setContentsMargins(0, 0, 0, 0); st.setSpacing(6)
        self.tab_bar = QHBoxLayout(); self.tab_bar.setSpacing(6); self.tab_bar.setContentsMargins(0, 0, 0, 0)
        self.btn_tab_thumbs  = QPushButton(T("reader_tab_thumbs"));  self.btn_tab_thumbs.setObjectName("Secondary");  self.btn_tab_thumbs.setCheckable(True);  self.btn_tab_thumbs.setChecked(True)
        self.btn_tab_outline = QPushButton(T("reader_tab_outline")); self.btn_tab_outline.setObjectName("Secondary"); self.btn_tab_outline.setCheckable(True)
        self.btn_tab_search  = QPushButton(T("reader_tab_search"));  self.btn_tab_search.setObjectName("Secondary");  self.btn_tab_search.setCheckable(True)
        for b in (self.btn_tab_thumbs, self.btn_tab_outline, self.btn_tab_search):
            b.setToolTip(b.text())
            b.setText("")  # icon-only to prevent truncation in tight sidebar
            b.setProperty("iconOnly", True)
            b.setFixedHeight(34)
            b.setCursor(Qt.PointingHandCursor)
            self.tab_bar.addWidget(b, 1)
        st.addLayout(self.tab_bar)
        self.side_stack = QStackedWidget(); st.addWidget(self.side_stack, 1)
        self.btn_tab_thumbs.clicked.connect (lambda: self._select_side_tab(0))
        self.btn_tab_outline.clicked.connect(lambda: self._select_side_tab(1))
        self.btn_tab_search.clicked.connect (lambda: self._select_side_tab(2))

        self.thumb_list = QListWidget(); self.thumb_list.setObjectName("ThumbList")
        self.thumb_list.setIconSize(QSize(160, 220))
        self.thumb_list.setSpacing(4); self.thumb_list.setUniformItemSizes(False)
        self.thumb_list.itemClicked.connect(self._thumb_clicked)
        self.side_stack.addWidget(self.thumb_list)

        self.outline_list = QListWidget()
        self.outline_list.itemClicked.connect(self._outline_clicked)
        self.side_stack.addWidget(self.outline_list)

        self.search_results = QListWidget()
        self.search_results.itemClicked.connect(self._search_result_clicked)
        self.side_stack.addWidget(self.search_results)

        body.addWidget(self.side_tabs)

        # Viewport
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().installEventFilter(self)
        self.viewport_host = QWidget()
        self.viewport_host.setAutoFillBackground(True)
        self.host_layout = QVBoxLayout(self.viewport_host)
        self.host_layout.setContentsMargins(20, 20, 20, 20); self.host_layout.setSpacing(16)
        self.host_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.placeholder = QLabel(T("reader_placeholder"))
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setObjectName("Placeholder")
        self.host_layout.addWidget(self.placeholder)
        self.scroll.setWidget(self.viewport_host)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        body.addWidget(self.scroll, 1)

        root.addLayout(body, 1)

        # ---- Search bar (bottom) -------------------------------------------
        self.search_bar = QWidget(); sbl = QHBoxLayout(self.search_bar)
        sbl.setContentsMargins(4, 4, 4, 4); sbl.setSpacing(6)
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText(T("reader_search_placeholder"))
        self.search_edit.returnPressed.connect(lambda: self._navigate_search(+1))
        self.search_edit.textChanged.connect(self._on_search_changed)
        self.search_prev = QPushButton(); self.search_prev.setObjectName("Secondary"); self.search_prev.setProperty("iconOnly", True); self.search_prev.setFixedWidth(40); self.search_prev.setToolTip(T("reader_prev"))
        self.search_prev.clicked.connect(lambda: self._navigate_search(-1))
        self.search_next = QPushButton(); self.search_next.setObjectName("Secondary"); self.search_next.setProperty("iconOnly", True); self.search_next.setFixedWidth(40); self.search_next.setToolTip(T("reader_next"))
        self.search_next.clicked.connect(lambda: self._navigate_search(+1))
        self.search_status = QLabel(""); self.search_status.setObjectName("SearchStatus")
        self.search_close = QPushButton(); self.search_close.setObjectName("Secondary"); self.search_close.setProperty("iconOnly", True); self.search_close.setFixedWidth(34); self.search_close.setToolTip(T("about_close"))
        self.search_close.clicked.connect(lambda: self.search_bar.setVisible(False))
        sbl.addWidget(QLabel("🔍")); sbl.addWidget(self.search_edit, 1)
        sbl.addWidget(self.search_prev); sbl.addWidget(self.search_next)
        sbl.addWidget(self.search_status); sbl.addWidget(self.search_close)
        self.search_bar.setVisible(False)
        root.addWidget(self.search_bar)

        # bottom hint removed for a cleaner UI; keep an invisible label so any
        # code that references self.hint keeps working without changes.
        self.hint = QLabel("")
        self.hint.setObjectName("HintLabel")
        self.hint.setVisible(False)
        root.addWidget(self.progress)

        # ---- Shortcuts -----------------------------------------------------
        def _sc(seq, fn):
            QShortcut(QKeySequence(seq), self, activated=fn)
        _sc("Ctrl+O", self.open_pdf)
        _sc(Qt.Key_Right, self.next_page); _sc(Qt.Key_Left, self.prev_page)
        _sc(Qt.Key_PageDown, self.next_page); _sc(Qt.Key_PageUp, self.prev_page)
        _sc(Qt.Key_Space, self.next_page); _sc("Shift+Space", self.prev_page)
        _sc(Qt.Key_Home, self.first_page); _sc(Qt.Key_End, self.last_page)
        _sc("Ctrl+=", lambda: self.set_zoom(self.zoom + 0.15))
        _sc("Ctrl++", lambda: self.set_zoom(self.zoom + 0.15))
        _sc("Ctrl+-", lambda: self.set_zoom(self.zoom - 0.15))
        _sc("Ctrl+0", lambda: self._set_fit("width"))
        _sc("Ctrl+1", lambda: self.set_zoom(1.0))
        _sc("Ctrl+2", lambda: self._set_fit("width"))
        _sc("Ctrl+3", lambda: self._set_fit("page"))
        _sc("Ctrl+G", self._focus_page_spin)
        _sc("Ctrl+F", self._focus_search)
        _sc("F3", lambda: self._navigate_search(+1))
        _sc("Shift+F3", lambda: self._navigate_search(-1))
        _sc("Ctrl+B", self.toggle_sidebar)
        _sc("Ctrl+T", self._cycle_theme)
        _sc("R", lambda: self.rotate(90))
        _sc("Shift+R", lambda: self.rotate(-90))
        _sc("F11", self.toggle_fullscreen)
        _sc("Escape", self._on_escape)
        _sc("Ctrl+C", self.copy_selection)
        _sc("Ctrl+S", self.save_with_highlights)
        _sc("Ctrl+H", self.highlight_selection)

        self._apply_theme()
        apply_semantic_icons(self)

    # ---- helpers --------------------------------------------------------

    def _select_side_tab(self, idx: int):
        self.side_stack.setCurrentIndex(idx)
        for i, b in enumerate((self.btn_tab_thumbs, self.btn_tab_outline, self.btn_tab_search)):
            b.setChecked(i == idx)

    def _apply_theme(self):
        colors = self.THEMES[self.theme]
        self.scroll.setStyleSheet(
            f"QScrollArea {{ background:{colors['bg']}; border:none; border-radius:8px; }}"
            f"QScrollArea > QWidget > QWidget {{ background:{colors['bg']}; }}"
        )
        self.viewport_host.setStyleSheet(f"background:{colors['bg']};")

    def _theme_changed(self, idx: int):
        self.theme = ["day", "night", "sepia"][idx]
        self.settings.setValue("reader/theme", self.theme)
        self._apply_theme()
        apply_semantic_icons(self)

    def _cycle_theme(self):
        self.theme_combo.setCurrentIndex((self.theme_combo.currentIndex() + 1) % 3)

    def _toggle_hand(self):
        self.hand_mode = self.hand_btn.isChecked()
        self.scroll.viewport().setCursor(Qt.OpenHandCursor if self.hand_mode else Qt.ArrowCursor)

    def _toggle_layout(self):
        self.layout_mode = "continuous" if self.layout_btn.isChecked() else "single"
        self.settings.setValue("reader/layout", self.layout_mode)
        if self.doc:
            self._rebuild_pages()

    def toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        self.side_tabs.setVisible(self.sidebar_visible)
        self.sidebar_btn.setChecked(self.sidebar_visible)

    def toggle_fullscreen(self):
        w = self.window()
        sb = w.findChild(QWidget, "Sidebar")
        if w.isFullScreen():
            w.showNormal()
            w.menuBar().setVisible(True)
            if sb and self._main_sidebar_visible_before_fullscreen is not None:
                sb.setVisible(self._main_sidebar_visible_before_fullscreen)
            self._main_sidebar_visible_before_fullscreen = None
            self._header.setVisible(True)
            self.hint.setVisible(True)
            self.toolbar.setVisible(True)
            self.setMouseTracking(False)
            try: self.scroll.viewport().setMouseTracking(False)
            except Exception: pass
            self._fs_hide_timer.stop()
            self._fs_reveal_poll.stop()
            self.present_btn.setToolTip(T("reader_present"))
        else:
            # ensure viewer is focused/visible before going full-screen
            if sb:
                self._main_sidebar_visible_before_fullscreen = sb.isVisible()
                sb.setVisible(False)
            w.showFullScreen()
            w.menuBar().setVisible(False)
            self._header.setVisible(False)
            self.hint.setVisible(False)
            self.present_btn.setToolTip(T("reader_present_exit"))
            # Enable mouse tracking to allow reveal-on-hover when unpinned
            self.setMouseTracking(True)
            try: self.scroll.viewport().setMouseTracking(True)
            except Exception: pass
            # Global cursor poll: guarantees toolbar can always be revealed
            # by moving the mouse to the top of the screen, from any widget.
            self._fs_reveal_poll.start()
            if not self._toolbar_pinned:
                self._fs_hide_timer.start()

    def _toggle_pin(self):
        self._toolbar_pinned = self.pin_btn.isChecked()
        self.pin_btn.setToolTip(T("reader_pin") if self._toolbar_pinned else T("reader_pin_off"))
        if self.window().isFullScreen():
            if self._toolbar_pinned:
                self.toolbar.setVisible(True); self._fs_hide_timer.stop()
            else:
                self._fs_hide_timer.start()
        try:
            apply_semantic_icons(self.pin_btn.parentWidget() or self)
        except Exception:
            pass

    def _maybe_hide_toolbar_in_fullscreen(self):
        if self.window().isFullScreen() and not self._toolbar_pinned:
            # Do not hide while the cursor is over the toolbar area
            try:
                pos = self.mapFromGlobal(self.cursor().pos())
                if self.toolbar.geometry().contains(pos):
                    self._fs_hide_timer.start(); return
            except Exception:
                pass
            self.toolbar.setVisible(False)

    def _reveal_toolbar_if_needed(self, global_pos=None):
        """Reveal the auto-hidden toolbar when the user moves the mouse near the
        top edge in fullscreen — guarantees the toolbar is never permanently
        lost (previously it stayed hidden until the app was closed)."""
        try:
            if not self.window().isFullScreen():
                return
            if self._toolbar_pinned:
                return
            if global_pos is None:
                global_pos = self.cursor().pos()
            local = self.mapFromGlobal(global_pos)
            # Reveal when cursor is in the top strip OR toolbar area
            trigger_h = max(60, self.toolbar.sizeHint().height() + 20)
            if local.y() <= trigger_h:
                if not self.toolbar.isVisible():
                    self.toolbar.setVisible(True)
                # Restart the hide countdown while the user keeps hovering
                self._fs_hide_timer.start()
        except Exception:
            pass

    def _fs_reveal_poll_tick(self):
        """Cursor-position poll used only while in fullscreen. Guarantees the
        toolbar always comes back on hover, regardless of which widget the
        mouse is over (mouse events don't always bubble to us)."""
        if not self.window().isFullScreen():
            self._fs_reveal_poll.stop()
            return
        self._reveal_toolbar_if_needed()


    def _toggle_autoscroll(self):
        try:
            running = self.autoscroll_btn.isChecked()
            self.autoscroll_btn.setToolTip(T("reader_autoscroll_pause") if running else T("reader_autoscroll"))
            apply_semantic_icons(self.autoscroll_btn.parentWidget() or self)
        except Exception:
            pass
        if self.autoscroll_btn.isChecked():
            self.autoscroll_btn.setText("⏸")
            self._autoscroll_timer.start()
        else:
            self.autoscroll_btn.setText("▶")
            self._autoscroll_timer.stop()

    def _autoscroll_tick(self):
        if not self.doc:
            self._autoscroll_timer.stop(); self.autoscroll_btn.setChecked(False)
            self.autoscroll_btn.setText("▶"); return
        vb = self.scroll.verticalScrollBar()
        step = max(1, int(self.autoscroll_speed.value()))
        new_val = vb.value() + step
        if new_val >= vb.maximum():
            if self.layout_mode == "single" and self.current_page < len(self.doc) - 1:
                self.next_page()
                self.scroll.verticalScrollBar().setValue(0)
            else:
                self._autoscroll_timer.stop()
                self.autoscroll_btn.setChecked(False)
                self.autoscroll_btn.setText("▶")
            return
        vb.setValue(new_val)

    def _on_escape(self):
        if self.search_bar.isVisible():
            self.search_bar.setVisible(False)
            return
        if self.autoscroll_btn.isChecked():
            self.autoscroll_btn.setChecked(False); self._toggle_autoscroll(); return
        if self.window().isFullScreen():
            self.toggle_fullscreen()


    def _focus_page_spin(self):
        self.page_spin.setFocus(); self.page_spin.selectAll()

    def _focus_search(self):
        self.search_bar.setVisible(True)
        self.search_edit.setFocus(); self.search_edit.selectAll()

    def _goto_from_spin(self):
        if not self.doc: return
        self.goto_page(self.page_spin.value() - 1)

    def _zoom_combo_changed(self, idx: int):
        if idx < len(self._zoom_presets):
            self.set_zoom(self._zoom_presets[idx][1])
        elif idx == len(self._zoom_presets):
            self._set_fit("width")
        elif idx == len(self._zoom_presets) + 1:
            self._set_fit("page")
        else:
            self.set_zoom(1.0)

    def _set_fit(self, mode: str):
        self.fit_mode = mode
        if self.doc: self._rebuild_pages()

    def rotate(self, delta: int):
        self.rotation = (self.rotation + delta) % 360
        if self.doc: self._rebuild_pages()

    # ---- Recent files ---------------------------------------------------

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        recent = self.settings.value("reader/recent", []) or []
        if isinstance(recent, str):
            recent = [recent]
        # Prune entries whose files no longer exist so the menu stays useful.
        recent = [p for p in recent if p and os.path.exists(p)]
        self.settings.setValue("reader/recent", recent)
        if not recent:
            a = QAction(T("reader_recent_none"), self); a.setEnabled(False)
            self.recent_menu.addAction(a); return
        for p in recent[:10]:
            act = QAction(os.path.basename(p) + "   —   " + p, self)
            act.triggered.connect(lambda _=False, path=p: self.open_pdf(path))
            self.recent_menu.addAction(act)
        self.recent_menu.addSeparator()
        clear = QAction(T("reader_recent_clear"), self)
        clear.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear)


    def _clear_recent(self):
        self.settings.setValue("reader/recent", [])
        self._rebuild_recent_menu()

    def _remember_recent(self, path: str):
        recent = self.settings.value("reader/recent", []) or []
        if isinstance(recent, str): recent = [recent]
        recent = [p for p in recent if p != path]
        recent.insert(0, path)
        self.settings.setValue("reader/recent", recent[:10])
        self._rebuild_recent_menu()

    # ---- Open / render --------------------------------------------------

    def open_pdf(self, path: Optional[str] = None):
        if not isinstance(path, str) or not path:
            path = pick_open_pdf(self)
        if not path:
            return
        # Show animated loading overlay immediately so the user gets
        # instant feedback even on very large PDFs that take a moment
        # to decrypt / decode / render the first page.
        overlay = getattr(self, "_loading_overlay", None)
        if overlay is not None:
            try:
                overlay.start(T("reader_loading"))
                QApplication.processEvents()
            except Exception:
                pass
        try:
            if not os.path.exists(path):
                show_error(self, T("reader_cannot_open"), T("reader_file_not_found"))
                return
            new_doc = fitz.open(path)
            if new_doc.needs_pass:
                # Hide overlay while a modal password prompt is shown.
                if overlay is not None: overlay.stop()
                password, ok = QInputDialog.getText(
                    self, T("encrypted_pdf"), T("reader_password_prompt"), QLineEdit.Password
                )
                if not ok:
                    new_doc.close()
                    return
                if overlay is not None:
                    overlay.start(T("reader_loading"))
                    QApplication.processEvents()
                try:
                    if not new_doc.authenticate(password):
                        new_doc.close()
                        show_error(self, T("encrypted_pdf"), T("reader_wrong_password"))
                        return
                except Exception:
                    new_doc.close()
                    show_error(self, T("encrypted_pdf"), T("reader_wrong_password"))
                    return
            if len(new_doc) == 0:
                new_doc.close()
                show_error(self, T("reader_cannot_open"), T("reader_empty_pdf"))
                return
            # persist last page for the previously-open doc
            self._save_last_page()
            if self.doc: self.doc.close()
            self.doc = new_doc
            self.current_path = path
            self._remember_recent(path)
            self.rotation = 0
            self._highlights = {}
            self._active_label = None
            self._page_dims_cache = {}
            self.current_page = int(self.settings.value(f"reader/last/{path}", 0) or 0)
            if self.current_page >= len(self.doc): self.current_page = 0
            self.page_spin.setMaximum(len(self.doc))
            self.page_total.setText(f"/ {len(self.doc)}")
            self._load_outline()
            self._rebuild_pages()
            QTimer.singleShot(0, self._rebuild_thumbs)
            saved_layout = self.settings.value("reader/layout", "single")
            if saved_layout == "continuous" and not self.layout_btn.isChecked():
                self.layout_btn.setChecked(True); self._toggle_layout()
            saved_theme = self.settings.value("reader/theme", "day")
            if saved_theme in self.THEMES:
                idx = ["day", "night", "sepia"].index(saved_theme)
                self.theme_combo.setCurrentIndex(idx)
        except Exception as e:
            show_error(self, T("reader_cannot_open"), str(e))
        finally:
            # Hide the overlay a beat after the first page is scheduled to
            # render so users see a smooth handoff, not a flash.
            if overlay is not None:
                QTimer.singleShot(180, overlay.stop)

    def _clear_pages(self):
        while self.host_layout.count():
            it = self.host_layout.takeAt(0)
            w = it.widget()
            if w is not None: w.setParent(None); w.deleteLater()
        self._page_labels = []

    def _rebuild_pages(self):
        if not self.doc: return
        self._clear_pages()
        n = len(self.doc)
        # SAFETY: continuous mode instantiates one QLabel per page. For very
        # large documents this can cost hundreds of MB and freeze the UI; fall
        # back to single-page mode above the threshold.
        CONTINUOUS_MAX = 300
        if self.layout_mode == "continuous" and n > CONTINUOUS_MAX:
            self.layout_mode = "single"
            try:
                if self.layout_btn.isChecked():
                    self.layout_btn.blockSignals(True)
                    self.layout_btn.setChecked(False)
                    self.layout_btn.blockSignals(False)
            except Exception:
                pass
        pages = list(range(n)) if self.layout_mode == "continuous" else [self.current_page]
        # Do NOT prefetch dimensions of every page here — for large PDFs
        # walking `self.doc` on load turned open-times into multi-second
        # freezes. Dimensions are cached lazily in `_get_page_dims`.
        if not hasattr(self, "_page_dims_cache"):
            self._page_dims_cache = {}
        page_bg = self.THEMES[self.theme]['page']
        for i in pages:
            lbl = _PageLabel(self, i)
            lbl.setStyleSheet(
                f"background:{page_bg}; border-radius:4px; padding:0px;"
            )
            self.host_layout.addWidget(lbl, 0, Qt.AlignHCenter)
            self._page_labels.append(lbl)
        for lbl in self._page_labels:
            try:
                self._reserve_page_size(lbl)
            except Exception:
                pass
        QTimer.singleShot(0, self._render_visible)
        self._update_page_indicator()
        self._sync_thumb_selection()

    def _get_page_dims(self, page_index: int):
        """Return (w, h) for a page, cached, computed on first access only."""
        cache = getattr(self, "_page_dims_cache", None)
        if cache is None:
            cache = {}
            self._page_dims_cache = cache
        d = cache.get(page_index)
        if d is not None:
            return d
        page = self.doc[page_index]
        d = (page.rect.width, page.rect.height)
        cache[page_index] = d
        return d

    def _reserve_page_size(self, lbl: _PageLabel):
        if not self.doc: return
        try:
            w, h = self._get_page_dims(lbl.page_index)
            if self.rotation in (90, 270): w, h = h, w
            zoom = min(self._effective_zoom(w, h), 4.0)
            lbl.setFixedSize(max(50, int(w * zoom)), max(50, int(h * zoom)))
        except Exception:
            lbl.setFixedSize(400, 500)



    def _effective_zoom(self, page_w: float, page_h: float) -> float:
        if self.fit_mode == "width":
            avail = max(200, self.scroll.viewport().width() - 60)
            return avail / max(1.0, page_w)
        if self.fit_mode == "page":
            avail_w = max(200, self.scroll.viewport().width() - 60)
            avail_h = max(200, self.scroll.viewport().height() - 60)
            return min(avail_w / max(1.0, page_w), avail_h / max(1.0, page_h))
        return self.zoom

    def _render_visible(self):
        if not self.doc or not self._page_labels: return
        try:
            vp = self.scroll.viewport()
            top = self.scroll.verticalScrollBar().value()
            bottom = top + vp.height()
            margin = vp.height()  # pre-render one page-height before/after
            for lbl in self._page_labels:
                try:
                    y = lbl.y()
                    if y + lbl.height() < top - margin: continue
                    if y > bottom + margin: continue
                    self._render_page_label(lbl)
                except Exception:
                    continue
            if self.layout_mode == "single" and self._page_labels:
                try:
                    self._render_page_label(self._page_labels[0])
                except Exception:
                    pass
        except Exception:
            pass

    def _render_page_label(self, lbl: _PageLabel):
        if not self.doc: return
        try:
            page = self.doc[lbl.page_index]
            w, h = page.rect.width, page.rect.height
            if self.rotation in (90, 270): w, h = h, w
            zoom = self._effective_zoom(w, h)
            # Clamp zoom so a huge page can never allocate a >~100MP pixmap
            # which would either stall the UI or crash Qt on 32-bit builds.
            max_pixels = 40_000_000
            if w * h * zoom * zoom > max_pixels:
                zoom = (max_pixels / max(1.0, w * h)) ** 0.5
            if abs(lbl.rendered_zoom - zoom) < 0.01 and lbl.rendered_rot == self.rotation and not self._search_query:
                return
            mat = _render_matrix(zoom, self.rotation)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            qpix = _pixmap_to_qpixmap(pix)
            if self._search_query and self.rotation == 0:
                hits = [r for (p, r) in self._search_hits if p == lbl.page_index]
                if hits:
                    painter = QPainter(qpix)
                    painter.setBrush(QColor(255, 220, 0, 90))
                    painter.setPen(Qt.NoPen)
                    for r in hits:
                        rr = r * mat
                        painter.drawRect(int(rr.x0), int(rr.y0),
                                         max(2, int(rr.x1 - rr.x0)),
                                         max(2, int(rr.y1 - rr.y0)))
                    painter.end()
            lbl.setPixmap(qpix)
            lbl.setFixedSize(qpix.size())
            lbl.rendered_zoom = zoom
            lbl.rendered_rot = self.rotation
            if not lbl.words:
                try:
                    lbl.words = [(fitz.Rect(w[:4]), w[4]) for w in page.get_text("words")]
                except Exception:
                    lbl.words = []
        except Exception:
            # A broken/corrupt page must not take the whole viewer down.
            pass


    # ---- Selection / Highlight -----------------------------------------
    def _add_highlights(self, page_idx: int, rects: list):
        if not rects:
            return
        self._highlights.setdefault(page_idx, []).extend(rects)
        for lbl in self._page_labels:
            if lbl.page_index == page_idx:
                lbl.update()

    def _clear_highlights(self, page_idx: int):
        self._highlights.pop(page_idx, None)
        for lbl in self._page_labels:
            if lbl.page_index == page_idx:
                lbl.update()

    def copy_selection(self):
        lbl = self._active_label
        if lbl is None:
            return
        txt = lbl.selected_text()
        if txt:
            QApplication.clipboard().setText(txt)

    def highlight_selection(self):
        lbl = self._active_label
        if lbl is None:
            return
        words = lbl.selected_words()
        if words:
            self._add_highlights(lbl.page_index, [w for w, _ in words])
            lbl.clear_selection()

    def save_with_highlights(self):
        if not self.doc or not self.current_path:
            return
        if not self._highlights:
            show_info(self, T("app_name"), T("reader_no_highlights"))
            return
        base, ext = os.path.splitext(self.current_path)
        default = base + "_highlighted.pdf"
        path, _ = QFileDialog.getSaveFileName(self, T("reader_save_annot"), default, "PDF (*.pdf)")
        if not path:
            return
        try:
            # Apply annotations onto a copy so the in-memory doc stays clean
            doc2 = fitz.open(self.current_path)
            for pidx, rects in self._highlights.items():
                if 0 <= pidx < len(doc2):
                    page = doc2[pidx]
                    for r in rects:
                        try:
                            page.add_highlight_annot(r)
                        except Exception:
                            pass
            doc2.save(path, deflate=True, garbage=3)
            doc2.close()
            show_info(self, T("app_name"), T("reader_saved").format(path))
        except Exception as e:
            show_error(self, T("operation_failed"), str(e))


    def _on_scroll(self, *_):
        if self._scroll_lock: return
        self._render_visible()
        if self.layout_mode == "continuous":
            # figure out which page is centered
            vp_mid = self.scroll.verticalScrollBar().value() + self.scroll.viewport().height() // 2
            for lbl in self._page_labels:
                if lbl.y() <= vp_mid <= lbl.y() + lbl.height():
                    if lbl.page_index != self.current_page:
                        self.current_page = lbl.page_index
                        self._update_page_indicator()
                        self._sync_thumb_selection()
                    break

    # ---- Navigation -----------------------------------------------------

    def goto_page(self, idx: int):
        if not self.doc or len(self.doc) == 0:
            return
        idx = max(0, min(len(self.doc) - 1, idx))
        self.current_page = idx
        if self.layout_mode == "single":
            self._rebuild_pages()
        else:
            # scroll to that page label
            for lbl in self._page_labels:
                if lbl.page_index == idx:
                    self._scroll_lock = True
                    self.scroll.verticalScrollBar().setValue(lbl.y() - 10)
                    self._scroll_lock = False
                    break
            self._render_visible()
        self._update_page_indicator()
        self._sync_thumb_selection()

    def next_page(self): self.doc and self.goto_page(self.current_page + 1)
    def prev_page(self): self.doc and self.goto_page(self.current_page - 1)
    def first_page(self): self.doc and self.goto_page(0)
    def last_page(self):  self.doc and self.goto_page(len(self.doc) - 1)

    def _update_page_indicator(self):
        if not self.doc: return
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(self.current_page + 1)
        self.page_spin.blockSignals(False)

    def set_zoom(self, z: float):
        self.fit_mode = "custom"
        self.zoom = max(0.2, min(6.0, z))
        # sync combo without triggering
        self.zoom_combo.blockSignals(True)
        nearest = min(range(len(self._zoom_presets)),
                      key=lambda i: abs(self._zoom_presets[i][1] - self.zoom))
        if abs(self._zoom_presets[nearest][1] - self.zoom) < 0.02:
            self.zoom_combo.setCurrentIndex(nearest)
        self.zoom_combo.blockSignals(False)
        if self.doc: self._rebuild_pages()

    # ---- Thumbnails / outline ------------------------------------------

    def _rebuild_thumbs(self):
        """Lazy thumbnails: add placeholder items instantly, render on demand
        as the user scrolls. This keeps 1000-page PDFs snappy and avoids the
        memory spike of pre-rendering every page.
        """
        self.thumb_list.clear()
        if not self.doc or not self.current_path:
            return
        n = len(self.doc)
        self.thumb_list.setIconSize(QSize(160, 220))
        # 1) instant placeholder items
        placeholder = QPixmap(160, 220)
        placeholder.fill(QColor("#EEF1F8" if APP_THEME != "dark" else "#1A1D2C"))
        placeholder_icon = QIcon(placeholder)
        for i in range(n):
            item = QListWidgetItem(placeholder_icon, f"  {i + 1}")
            item.setData(Qt.UserRole, i)
            item.setData(Qt.UserRole + 1, False)  # rendered flag
            self.thumb_list.addItem(item)

        # 2) render on demand as list scrolls; batch small chunks per tick
        if not hasattr(self, "_thumb_render_timer"):
            self._thumb_render_timer = QTimer(self)
            self._thumb_render_timer.setInterval(30)
            self._thumb_render_timer.timeout.connect(self._render_visible_thumbs)
            try:
                self.thumb_list.verticalScrollBar().valueChanged.connect(
                    lambda _: self._thumb_render_timer.start())
            except Exception:
                pass
        self._thumb_render_timer.start()
        self._sync_thumb_selection()

    def _render_visible_thumbs(self):
        """Render up to N thumbnails currently visible in the list widget."""
        if not self.doc:
            self._thumb_render_timer.stop(); return
        try:
            vp = self.thumb_list.viewport()
            first = self.thumb_list.indexAt(vp.rect().topLeft()).row()
            last = self.thumb_list.indexAt(vp.rect().bottomLeft()).row()
            if first < 0: first = 0
            if last < 0: last = min(self.thumb_list.count() - 1, first + 6)
            # Pre-render a small margin
            first = max(0, first - 2)
            last = min(self.thumb_list.count() - 1, last + 4)
            budget = 4  # thumbs per tick to stay responsive
            for row in range(first, last + 1):
                if budget <= 0:
                    return  # keep timer running for the next tick
                item = self.thumb_list.item(row)
                if item is None or item.data(Qt.UserRole + 1):
                    continue
                page_idx = int(item.data(Qt.UserRole))
                try:
                    page = self.doc[page_idx]
                    w = page.rect.width or 1
                    zoom = 160.0 / w
                    pix = page.get_pixmap(matrix=_render_matrix(zoom), alpha=False)
                    qpix = _pixmap_to_qpixmap(pix)
                    item.setIcon(QIcon(qpix))
                    item.setData(Qt.UserRole + 1, True)
                    budget -= 1
                except Exception:
                    item.setData(Qt.UserRole + 1, True)  # mark to avoid retry
            # nothing left to render for the visible window -> stop timer
            self._thumb_render_timer.stop()
        except Exception:
            self._thumb_render_timer.stop()


    def _sync_thumb_selection(self):
        for i in range(self.thumb_list.count()):
            it = self.thumb_list.item(i)
            if it.data(Qt.UserRole) == self.current_page:
                self.thumb_list.setCurrentItem(it); break

    def _thumb_clicked(self, item):
        self.goto_page(int(item.data(Qt.UserRole)))

    def _load_outline(self):
        self.outline_list.clear()
        if not self.doc: return
        try:
            toc = self.doc.get_toc()
        except Exception:
            toc = []
        if not toc:
            it = QListWidgetItem(T("reader_no_outline")); it.setFlags(Qt.NoItemFlags)
            self.outline_list.addItem(it); return
        for level, title, page in toc:
            try:
                page_no = int(page)
            except Exception:
                continue
            if page_no < 1 or (self.doc and page_no > len(self.doc)):
                continue
            it = QListWidgetItem(("    " * max(0, level - 1)) + f"• {title}   (p.{page_no})")
            it.setData(Qt.UserRole, page_no - 1)
            self.outline_list.addItem(it)

    def _outline_clicked(self, item):
        p = item.data(Qt.UserRole)
        if isinstance(p, int): self.goto_page(p)

    # ---- Search ---------------------------------------------------------

    def _on_search_changed(self, text: str):
        self._search_query = text.strip()
        self.search_results.clear()
        self._search_hits = []
        self._search_current = -1
        if not self.doc or not self._search_query:
            self.search_status.setText("")
            self._invalidate_render(); return
        for i in range(len(self.doc)):
            try:
                rects = self.doc[i].search_for(self._search_query, quads=False) or []
            except Exception:
                rects = []
            for r in rects:
                self._search_hits.append((i, r))
                self.search_results.addItem(QListWidgetItem(f"p.{i + 1} — {self._search_query}"))
        if not self._search_hits:
            self.search_status.setText(T("reader_no_match"))
        else:
            self._navigate_search(+1)
        self._invalidate_render()

    def _navigate_search(self, direction: int):
        if not self._search_hits: return
        self._search_current = (self._search_current + direction) % len(self._search_hits)
        page, _rect = self._search_hits[self._search_current]
        self.goto_page(page)
        self.search_status.setText(T("reader_matches").format(
            cur=self._search_current + 1, total=len(self._search_hits)))
        self._invalidate_render()

    def _search_result_clicked(self, item):
        row = self.search_results.row(item)
        if 0 <= row < len(self._search_hits):
            self._search_current = row - 1
            self._navigate_search(+1)

    def _invalidate_render(self):
        for lbl in self._page_labels:
            lbl.rendered_zoom = 0.0
        self._render_visible()

    # ---- Events ---------------------------------------------------------

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            self.set_zoom(self.zoom + (0.12 if delta > 0 else -0.12))
            return True
        if self.hand_mode and et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._panning = True; self._pan_start = event.pos()
            self.scroll.viewport().setCursor(Qt.ClosedHandCursor); return True
        if self._panning and et == QEvent.MouseMove:
            d = event.pos() - self._pan_start
            hb = self.scroll.horizontalScrollBar(); vb = self.scroll.verticalScrollBar()
            hb.setValue(hb.value() - d.x()); vb.setValue(vb.value() - d.y())
            self._pan_start = event.pos(); return True
        if self._panning and et == QEvent.MouseButtonRelease:
            self._panning = False
            self.scroll.viewport().setCursor(Qt.OpenHandCursor if self.hand_mode else Qt.ArrowCursor)
            return True
        if et == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            self.toggle_fullscreen(); return True
        # Fullscreen reveal-on-hover: any mouse movement near the top edge
        # brings the auto-hidden toolbar back so the user is never stuck.
        if et == QEvent.MouseMove and self.window().isFullScreen():
            try:
                self._reveal_toolbar_if_needed(event.globalPos())
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        if self.window().isFullScreen():
            try:
                self._reveal_toolbar_if_needed(event.globalPos())
            except Exception:
                pass

    # ---- Drag & drop ---------------------------------------------------
    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls() and any(u.toLocalFile().lower().endswith(".pdf") for u in md.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for u in event.mimeData().urls():
            p = u.toLocalFile()
            if p.lower().endswith(".pdf"):
                self.open_pdf(p)
                event.acceptProposedAction()
                return
        event.ignore()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounce: avoid re-rendering every intermediate pixel during window resize.
        if self.doc and self.fit_mode in ("width", "page"):
            self._resize_debounce.start()

    def _on_resize_finished(self):
        if self.doc and self.fit_mode in ("width", "page"):
            # Cheap path: just re-reserve sizes & re-render visible; avoid full rebuild.
            for lbl in self._page_labels:
                try: self._reserve_page_size(lbl)
                except Exception: pass
            self._render_visible()


    def _save_last_page(self):
        if self.current_path and self.doc:
            self.settings.setValue(f"reader/last/{self.current_path}", self.current_page)

    def closeEvent(self, event):
        self._save_last_page()
        if self.doc:
            try: self.doc.close()
            except Exception: pass
        super().closeEvent(event)

# =============================================================================
#  Merge
# =============================================================================

class MergePage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("merge_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget, 1)

        btns = QHBoxLayout()
        add_btn = QPushButton(T("merge_add")); add_btn.clicked.connect(self.add_files)
        rm_btn  = QPushButton(T("merge_remove")); rm_btn.setObjectName("Danger"); rm_btn.clicked.connect(self.remove_selected)
        clr_btn = QPushButton(T("merge_clear")); clr_btn.setObjectName("Secondary"); clr_btn.clicked.connect(self.list_widget.clear)
        up_btn  = QPushButton(); up_btn.setObjectName("Secondary"); up_btn.setProperty("iconOnly", True); up_btn.setFixedWidth(40); up_btn.setToolTip(T("move_up")); up_btn.clicked.connect(lambda: self.move(-1))
        dn_btn  = QPushButton(); dn_btn.setObjectName("Secondary"); dn_btn.setProperty("iconOnly", True); dn_btn.setFixedWidth(40); dn_btn.setToolTip(T("move_down")); dn_btn.clicked.connect(lambda: self.move(1))
        merge_btn = QPushButton(T("merge_do")); merge_btn.clicked.connect(self.merge)
        btns.addWidget(add_btn); btns.addWidget(rm_btn); btns.addWidget(clr_btn)
        btns.addWidget(up_btn); btns.addWidget(dn_btn); btns.addStretch(); btns.addWidget(merge_btn)
        layout.addLayout(btns)
        layout.addWidget(self.progress)
        apply_semantic_icons(self)

    def add_files(self):
        for p in pick_open_pdfs(self):
            try:
                with open(p, "rb") as fh:
                    n = len(_load_pdf_reader(fh).pages)
                item = QListWidgetItem(f"{os.path.basename(p)}   ·   {n} page(s)")
                item.setData(Qt.UserRole, p)
                item.setToolTip(p)
                self.list_widget.addItem(item)
            except Exception as e:
                show_error(self, T("skipped_file"), f"{p}\n\n{e}")

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(item))

    def move(self, delta: int):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        new = row + delta
        if new < 0 or new >= self.list_widget.count():
            return
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(new, item)
        self.list_widget.setCurrentRow(new)

    def merge(self):
        if self.list_widget.count() < 2:
            show_error(self, T("merge_title"), T("merge_need_two"))
            return
        paths = [self.list_widget.item(i).data(Qt.UserRole)
                 for i in range(self.list_widget.count())]
        out = pick_save_pdf(self, "merged.pdf")
        if not out:
            return

        def task(report):
            writer = PdfWriter()
            for idx, p in enumerate(paths, 1):
                report(idx, len(paths), f"Merging {os.path.basename(p)}")
                with open(p, "rb") as fh:
                    reader = _load_pdf_reader(fh)
                    for page in reader.pages:
                        writer.add_page(page)
            with open(out, "wb") as f:
                writer.write(f)
            return out

        self.run_async(task,
                       lambda r: show_info(self, T("success"), T("merge_success").format(r)),
                       T("merge_working"))

# =============================================================================
#  Split
# =============================================================================

class SplitPage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("split_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)

        self.file_edit = QLineEdit(); self.file_edit.setReadOnly(True)
        browse = QPushButton(T("browse")); browse.setObjectName("Secondary"); browse.clicked.connect(self.pick_file)
        row = QHBoxLayout(); row.addWidget(self.file_edit); row.addWidget(browse)
        rw = QWidget(); rw.setLayout(row)
        form.addRow(T("split_file"), rw)

        self.info = QLabel("—"); self.info.setStyleSheet("color:#A8AECB;")
        form.addRow(T("split_pages"), self.info)

        self.mode = QComboBox()
        self.mode.addItems([T("split_mode_single"), T("split_mode_range")])
        form.addRow(T("split_mode"), self.mode)

        self.start = QSpinBox(); self.start.setMinimum(1); self.start.setMaximum(1)
        self.end   = QSpinBox(); self.end.setMinimum(1);   self.end.setMaximum(1)
        rng = QHBoxLayout(); rng.addWidget(QLabel(T("split_from"))); rng.addWidget(self.start)
        rng.addWidget(QLabel(T("split_to"))); rng.addWidget(self.end); rng.addStretch()
        rw2 = QWidget(); rw2.setLayout(rng)
        form.addRow(T("split_range"), rw2)

        layout.addWidget(card)
        go = QPushButton(T("split_do")); go.clicked.connect(self.split)
        layout.addWidget(go, alignment=Qt.AlignRight)
        layout.addWidget(self.progress)
        layout.addStretch()
        apply_semantic_icons(self)

    def pick_file(self):
        p = pick_open_pdf(self)
        if not p:
            return
        try:
            with open(p, "rb") as fh:
                n = len(_load_pdf_reader(fh).pages)
        except Exception as e:
            show_error(self, T("split_title"), str(e)); return
        self.file_edit.setText(p)
        self.info.setText(f"{n} page(s)")
        self.start.setMaximum(n); self.end.setMaximum(n); self.end.setValue(n)

    def split(self):
        path = self.file_edit.text().strip()
        if not path or not os.path.exists(path):
            show_error(self, T("split_title"), T("split_need_valid")); return

        if self.mode.currentIndex() == 0:
            folder = pick_folder(self)
            if not folder:
                return

            def task(report):
                with open(path, "rb") as fh:
                    reader = _load_pdf_reader(fh)
                    base = os.path.splitext(os.path.basename(path))[0]
                    total = len(reader.pages)
                    for i, page in enumerate(reader.pages, 1):
                        report(i, total, f"Page {i} / {total}")
                        w = PdfWriter(); w.add_page(page)
                        with open(os.path.join(folder, f"{base}_page_{i}.pdf"), "wb") as f:
                            w.write(f)
                return total

            self.run_async(task,
                           lambda n: show_info(self, T("done"), T("split_result_single").format(n)),
                           T("split_working_single"))
        else:
            s, e = self.start.value(), self.end.value()
            if s > e:
                show_error(self, T("split_range"), T("split_bad_range")); return
            out = pick_save_pdf(self, f"pages_{s}-{e}.pdf", source=path)
            if not out:
                return

            def task(report):
                with open(path, "rb") as fh:
                    reader = _load_pdf_reader(fh)
                    w = PdfWriter()
                    total = e - s + 1
                    for i, idx in enumerate(range(s - 1, e), 1):
                        report(i, total, f"Page {i} / {total}")
                        w.add_page(reader.pages[idx])
                    with open(out, "wb") as f:
                        w.write(f)
                return out

            self.run_async(task,
                           lambda r: show_info(self, T("done"), T("split_result_range").format(r)),
                           T("split_working_range"))

# =============================================================================
#  Compress
# =============================================================================

class CompressPage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("compress_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)

        self.file_edit = QLineEdit(); self.file_edit.setReadOnly(True)
        browse = QPushButton(T("browse")); browse.setObjectName("Secondary"); browse.clicked.connect(self.pick_file)
        row = QHBoxLayout(); row.addWidget(self.file_edit); row.addWidget(browse)
        rw = QWidget(); rw.setLayout(row)
        form.addRow(T("pdf_file_label"), rw)

        self.quality = QComboBox()
        self.quality.addItems([T("compress_low"), T("compress_medium"), T("compress_high")])
        self.quality.setCurrentIndex(1)
        form.addRow(T("compress_quality"), self.quality)

        layout.addWidget(card)

        self.info_label = QLabel(""); self.info_label.setStyleSheet("color:#A8AECB;")
        layout.addWidget(self.info_label)

        go = QPushButton(T("compress_do")); go.clicked.connect(self.compress)
        layout.addWidget(go, alignment=Qt.AlignRight)
        layout.addWidget(self.progress)
        layout.addStretch()
        apply_semantic_icons(self)

    def pick_file(self):
        p = pick_open_pdf(self)
        if not p:
            return
        self.file_edit.setText(p)
        self.info_label.setText(T("compress_original").format(os.path.getsize(p) / 1024))

    def compress(self):
        path = self.file_edit.text().strip()
        if not path or not os.path.exists(path):
            show_error(self, T("compress_title"), T("split_need_valid")); return
        out = pick_save_pdf(self, "compressed.pdf", source=path)
        if not out:
            return
        garbage_level = {0: 4, 1: 3, 2: 2}[self.quality.currentIndex()]

        def task(report):
            report(0, 0, T("compress_working"))
            doc = fitz.open(path)
            try:
                doc.save(out, garbage=garbage_level, deflate=True,
                         deflate_images=True, deflate_fonts=True, clean=True)
            finally:
                doc.close()
            return out

        def done(result):
            orig = os.path.getsize(path)
            new = os.path.getsize(result)
            pct = (1 - new / orig) * 100 if orig else 0
            show_info(self, T("done"),
                      T("compress_report").format(
                          orig=orig / 1024, new=new / 1024, pct=pct, path=result))

        self.run_async(task, done, T("compress_working"))

# =============================================================================
#  Extract
# =============================================================================

class ExtractPage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("extract_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        top = QHBoxLayout()
        self.file_edit = QLineEdit(); self.file_edit.setReadOnly(True)
        browse = QPushButton(T("browse")); browse.setObjectName("Secondary"); browse.clicked.connect(self.pick_file)
        top.addWidget(QLabel(T("pdf_file_label"))); top.addWidget(self.file_edit, 1); top.addWidget(browse)
        layout.addLayout(top)

        btns = QHBoxLayout()
        self.text_btn      = QPushButton(T("extract_text_btn"));  self.text_btn.clicked.connect(self.extract_text)
        self.save_text_btn = QPushButton(T("extract_save_text")); self.save_text_btn.setObjectName("Secondary")
        self.save_text_btn.clicked.connect(self.save_text)
        self.img_btn   = QPushButton(T("extract_images"));   self.img_btn.setObjectName("Secondary")
        self.img_btn.clicked.connect(self.extract_images)
        self.pages_btn = QPushButton(T("extract_pages_png")); self.pages_btn.setObjectName("Secondary")
        self.pages_btn.clicked.connect(self.pages_to_png)
        btns.addWidget(self.text_btn); btns.addWidget(self.save_text_btn)
        btns.addWidget(self.img_btn);  btns.addWidget(self.pages_btn); btns.addStretch()
        layout.addLayout(btns)

        self.text_view = QTextEdit(); self.text_view.setReadOnly(True)
        self.text_view.setPlaceholderText(T("extract_placeholder"))
        layout.addWidget(self.text_view, 1)
        layout.addWidget(self.progress)
        apply_semantic_icons(self)

    def pick_file(self):
        p = pick_open_pdf(self)
        if p:
            self.file_edit.setText(p)

    def _require(self) -> Optional[str]:
        path = self.file_edit.text().strip()
        if not path or not os.path.exists(path):
            show_error(self, T("extract_title"), T("extract_need_valid")); return None
        return path

    def extract_text(self):
        path = self._require()
        if not path:
            return

        def task(report):
            doc = fitz.open(path)
            try:
                parts = []
                total = len(doc)
                for i, page in enumerate(doc, 1):
                    report(i, total, f"Reading page {i} / {total}")
                    parts.append(f"───── Page {i} ─────\n{page.get_text()}\n")
                return "\n".join(parts)
            finally:
                doc.close()

        self.run_async(task, lambda t: self.text_view.setPlainText(t), T("extract_working_text"))

    def save_text(self):
        text = self.text_view.toPlainText()
        if not text.strip():
            show_info(self, T("extract_save_text"), T("extract_click_first")); return
        path, _ = QFileDialog.getSaveFileName(self, T("extract_save_text"), "extracted.txt", "Text Files (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            show_info(self, T("saved"), T("extract_text_saved").format(path))
        except Exception as e:
            show_error(self, T("save_failed"), str(e))

    def extract_images(self):
        path = self._require()
        if not path:
            return
        folder = pick_folder(self)
        if not folder:
            return

        def task(report):
            doc = fitz.open(path); count = 0
            try:
                total = len(doc)
                for pno in range(total):
                    report(pno + 1, total, f"Scanning page {pno + 1} / {total}")
                    for idx, img in enumerate(doc.get_page_images(pno)):
                        try:
                            xref = img[0]
                            base_pix = fitz.Pixmap(doc, xref)
                            out_pix = base_pix
                            if base_pix.n - base_pix.alpha >= 4:  # CMYK/other -> RGB
                                out_pix = fitz.Pixmap(fitz.csRGB, base_pix)
                            out_path = os.path.join(folder, f"page{pno+1}_img{idx+1}.png")
                            out_pix.save(out_path)
                            count += 1
                        except Exception:
                            continue

                return count
            finally:
                doc.close()

        self.run_async(task,
                       lambda c: show_info(self, T("done"), T("extract_images_done").format(c, folder)),
                       T("extract_working_images"))

    def pages_to_png(self):
        path = self._require()
        if not path:
            return
        folder = pick_folder(self)
        if not folder:
            return

        def task(report):
            doc = fitz.open(path)
            try:
                total = len(doc)
                for i, page in enumerate(doc, 1):
                    report(i, total, f"Rendering page {i} / {total}")
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    pix.save(os.path.join(folder, f"page_{i}.png"))
                return total
            finally:
                doc.close()

        self.run_async(task,
                       lambda n: show_info(self, T("done"), T("extract_pages_done").format(n, folder)),
                       T("extract_working_pages"))

# =============================================================================
#  Organize
# =============================================================================

class OrganizePage(BasePage):
    ROLE_SRC = Qt.UserRole
    ROLE_ROT = Qt.UserRole + 1

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("organize_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        top = QHBoxLayout()
        self.file_edit = QLineEdit(); self.file_edit.setReadOnly(True)
        browse = QPushButton(T("browse")); browse.setObjectName("Secondary"); browse.clicked.connect(self.load_pdf)
        top.addWidget(QLabel(T("pdf_file_label"))); top.addWidget(self.file_edit, 1); top.addWidget(browse)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget, 1)

        btns = QHBoxLayout()
        rot_l = QPushButton(T("organize_rot_l"));  rot_l.setObjectName("Secondary"); rot_l.clicked.connect(lambda: self.rotate(-90))
        rot_r = QPushButton(T("organize_rot_r"));  rot_r.setObjectName("Secondary"); rot_r.clicked.connect(lambda: self.rotate(90))
        rot_2 = QPushButton(T("organize_rot_2"));  rot_2.setObjectName("Secondary"); rot_2.clicked.connect(lambda: self.rotate(180))
        rm    = QPushButton(T("organize_delete")); rm.setObjectName("Danger"); rm.clicked.connect(self.delete_selected)
        save  = QPushButton(T("organize_save"));   save.clicked.connect(self.save)
        btns.addWidget(rot_l); btns.addWidget(rot_r); btns.addWidget(rot_2); btns.addWidget(rm)
        btns.addStretch(); btns.addWidget(save)
        layout.addLayout(btns)
        layout.addWidget(self.progress)
        apply_semantic_icons(self)

        self._src_path: str = ""

    def _make_item(self, src_index: int, rotation: int = 0) -> QListWidgetItem:
        item = QListWidgetItem()
        item.setData(self.ROLE_SRC, src_index)
        item.setData(self.ROLE_ROT, rotation)
        self._refresh_item(item)
        return item

    def _refresh_item(self, item: QListWidgetItem):
        src = int(item.data(self.ROLE_SRC))
        rot = int(item.data(self.ROLE_ROT) or 0)
        item.setText(f"Page {src + 1}" + (f"   ({rot}°)" if rot else ""))

    def load_pdf(self):
        p = pick_open_pdf(self)
        if not p:
            return
        try:
            with open(p, "rb") as fh:
                n = len(_load_pdf_reader(fh).pages)
        except Exception as e:
            show_error(self, T("organize_title"), str(e)); return
        self._src_path = p
        self.file_edit.setText(p)
        self.list_widget.clear()
        for i in range(n):
            self.list_widget.addItem(self._make_item(i))

    def rotate(self, deg: int):
        items = self.list_widget.selectedItems()
        if not items:
            show_info(self, T("organize_title"), T("organize_select_page")); return
        for it in items:
            cur = int(it.data(self.ROLE_ROT) or 0)
            it.setData(self.ROLE_ROT, (cur + deg) % 360)
            self._refresh_item(it)

    def delete_selected(self):
        for it in self.list_widget.selectedItems():
            self.list_widget.takeItem(self.list_widget.row(it))

    def save(self):
        if not self._src_path:
            show_error(self, T("organize_title"), T("organize_load_first")); return
        count = self.list_widget.count()
        if count == 0:
            show_error(self, T("organize_title"), T("organize_no_pages")); return
        out = pick_save_pdf(self, "organized.pdf", source=self._src_path)
        if not out:
            return

        entries = []
        for i in range(count):
            it = self.list_widget.item(i)
            entries.append((int(it.data(self.ROLE_SRC)), int(it.data(self.ROLE_ROT) or 0)))
        src = self._src_path

        def task(report):
            with open(src, "rb") as fh:
                reader = _load_pdf_reader(fh); writer = PdfWriter()
                total = len(entries)
                for i, (idx, rot) in enumerate(entries, 1):
                    report(i, total, f"Writing page {i} / {total}")
                    page = reader.pages[idx]
                    if rot:
                        # pypdf requires a multiple of 90.
                        safe_rot = (round(rot / 90) * 90) % 360
                        if safe_rot:
                            page.rotate(safe_rot)
                    writer.add_page(page)
                with open(out, "wb") as f:
                    writer.write(f)
            return out

        self.run_async(task,
                       lambda r: show_info(self, T("saved"), T("organize_saved").format(r)),
                       T("organize_working"))

# =============================================================================
#  Security
# =============================================================================

class SecurityPage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("security_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        # Encrypt
        enc = QGroupBox(T("security_encrypt_group"))
        f1 = QFormLayout(enc)
        self.enc_file = QLineEdit(); self.enc_file.setReadOnly(True)
        b1 = QPushButton(T("browse")); b1.setObjectName("Secondary")
        b1.clicked.connect(lambda: self._pick(self.enc_file))
        row1 = QHBoxLayout(); row1.addWidget(self.enc_file); row1.addWidget(b1)
        w1 = QWidget(); w1.setLayout(row1); f1.addRow(T("pdf_file_label"), w1)
        self.enc_pw = QLineEdit(); self.enc_pw.setEchoMode(QLineEdit.Password)
        self.enc_pw2 = QLineEdit(); self.enc_pw2.setEchoMode(QLineEdit.Password)
        f1.addRow(T("security_pw"), self.enc_pw)
        f1.addRow(T("security_confirm"),  self.enc_pw2)
        enc_btn = QPushButton(T("security_enc_do")); enc_btn.clicked.connect(self.encrypt)
        f1.addRow("", enc_btn)
        layout.addWidget(enc)

        # Decrypt
        dec = QGroupBox(T("security_decrypt_group"))
        f2 = QFormLayout(dec)
        self.dec_file = QLineEdit(); self.dec_file.setReadOnly(True)
        b2 = QPushButton(T("browse")); b2.setObjectName("Secondary")
        b2.clicked.connect(lambda: self._pick(self.dec_file))
        row2 = QHBoxLayout(); row2.addWidget(self.dec_file); row2.addWidget(b2)
        w2 = QWidget(); w2.setLayout(row2); f2.addRow(T("pdf_file_label"), w2)
        self.dec_pw = QLineEdit(); self.dec_pw.setEchoMode(QLineEdit.Password)
        f2.addRow(T("security_pw"), self.dec_pw)
        dec_btn = QPushButton(T("security_dec_do")); dec_btn.clicked.connect(self.decrypt)
        f2.addRow("", dec_btn)
        layout.addWidget(dec)

        layout.addWidget(self.progress)
        layout.addStretch()
        apply_semantic_icons(self)

    def _pick(self, target: QLineEdit):
        p = pick_open_pdf(self)
        if p:
            target.setText(p)

    def encrypt(self):
        path = self.enc_file.text().strip()
        pw, pw2 = self.enc_pw.text(), self.enc_pw2.text()
        if not path or not os.path.exists(path):
            show_error(self, T("security_title"), T("security_choose_pdf")); return
        if not pw:
            show_error(self, T("security_title"), T("security_enter_pw")); return
        if pw != pw2:
            show_error(self, T("security_title"), T("security_pw_mismatch")); return
        out = pick_save_pdf(self, "encrypted.pdf", source=path)
        if not out:
            return

        # Prefer AES when the optional `cryptography` package is present;
        # otherwise fall back to pypdf's built-in RC4 so the app still works
        # on a bare install.
        try:
            import cryptography  # noqa: F401
            preferred_algo = "AES-256"
        except Exception:
            preferred_algo = None

        def task(report):
            report(0, 0, T("security_working_enc"))
            with open(path, "rb") as fh:
                reader = _load_pdf_reader(fh); writer = PdfWriter()
                for p in reader.pages:
                    writer.add_page(p)
                if preferred_algo:
                    try:
                        writer.encrypt(user_password=pw, algorithm=preferred_algo)
                    except TypeError:
                        writer.encrypt(pw)
                else:
                    writer.encrypt(pw)
                with open(out, "wb") as f:
                    writer.write(f)
            return out


        def done(r):
            self.enc_pw.clear(); self.enc_pw2.clear()
            show_info(self, T("done"), T("security_encrypted").format(r))

        self.run_async(task, done, T("security_working_enc"))

    def decrypt(self):
        path = self.dec_file.text().strip()
        pw = self.dec_pw.text()
        if not path or not os.path.exists(path):
            show_error(self, T("security_title"), T("security_choose_pdf")); return
        out = pick_save_pdf(self, "decrypted.pdf", source=path)
        if not out:
            return

        def task(report):
            report(0, 0, T("security_working_dec"))
            with open(path, "rb") as fh:
                reader = PdfReader(fh)
                if reader.is_encrypted:
                    if not reader.decrypt(pw):
                        raise ValueError(T("security_wrong_pw"))
                writer = PdfWriter()
                for p in reader.pages:
                    writer.add_page(p)
                with open(out, "wb") as f:
                    writer.write(f)
            return out

        def done(r):
            self.dec_pw.clear()
            show_info(self, T("done"), T("security_decrypted").format(r))

        self.run_async(task, done, T("security_working_dec"))

# =============================================================================
#  Watermark
# =============================================================================

class WatermarkPage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("watermark_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)
        self.file_edit = QLineEdit(); self.file_edit.setReadOnly(True)
        b = QPushButton(T("browse")); b.setObjectName("Secondary"); b.clicked.connect(self.pick)
        row = QHBoxLayout(); row.addWidget(self.file_edit); row.addWidget(b)
        rw = QWidget(); rw.setLayout(row); form.addRow(T("pdf_file_label"), rw)

        self.text = QLineEdit("CONFIDENTIAL"); form.addRow(T("watermark_text"), self.text)

        self.opacity = QSlider(Qt.Horizontal); self.opacity.setMinimum(5); self.opacity.setMaximum(100); self.opacity.setValue(25)
        self.opacity_lbl = QLabel("25%")
        self.opacity.valueChanged.connect(lambda v: self.opacity_lbl.setText(f"{v}%"))
        op = QHBoxLayout(); op.addWidget(self.opacity); op.addWidget(self.opacity_lbl)
        opw = QWidget(); opw.setLayout(op)
        form.addRow(T("watermark_opacity"), opw)

        self.size = QSpinBox(); self.size.setMinimum(20); self.size.setMaximum(200); self.size.setValue(60)
        form.addRow(T("watermark_size"), self.size)

        self.angle = QSpinBox(); self.angle.setRange(-90, 90); self.angle.setValue(45)
        form.addRow(T("watermark_angle"), self.angle)

        layout.addWidget(card)
        go = QPushButton(T("watermark_do")); go.clicked.connect(self.apply)
        layout.addWidget(go, alignment=Qt.AlignRight)
        layout.addWidget(self.progress)
        layout.addStretch()
        apply_semantic_icons(self)

    def pick(self):
        p = pick_open_pdf(self)
        if p:
            self.file_edit.setText(p)

    def apply(self):
        path = self.file_edit.text().strip()
        if not path or not os.path.exists(path):
            show_error(self, T("watermark_title"), T("watermark_choose")); return
        out = pick_save_pdf(self, "watermarked.pdf", source=path)
        if not out:
            return

        opacity = self.opacity.value() / 100.0
        size = self.size.value()
        text = self.text.text() or "WATERMARK"
        angle = self.angle.value()

        def task(report):
            doc = fitz.open(path)
            try:
                total = len(doc)
                for i, page in enumerate(doc, 1):
                    report(i, total, f"Page {i} / {total}")
                    rect = page.rect
                    font = fitz.Font("helv")
                    tw = fitz.TextWriter(rect, color=(0.5, 0.5, 0.5), opacity=opacity)
                    text_w = font.text_length(text, fontsize=size)
                    pos = fitz.Point((rect.width - text_w) / 2, rect.height / 2 + size / 3)
                    tw.append(pos, text, font=font, fontsize=size)

                    rotation = fitz.Matrix(1, 1)
                    rotation.prerotate(angle)
                    morph = (fitz.Point(rect.width / 2, rect.height / 2), rotation)
                    tw.write_text(page, morph=morph)
                doc.save(out, incremental=False, garbage=3, deflate=True)
                return out
            finally:
                doc.close()

        self.run_async(task,
                       lambda r: show_info(self, T("saved"), T("watermark_saved").format(r)),
                       T("watermark_working"))

# =============================================================================
#  Metadata
# =============================================================================

class MetadataPage(BasePage):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel(T("metadata_title")); title.setObjectName("PageTitle")

        layout.addWidget(title)

        top = QHBoxLayout()
        self.file_edit = QLineEdit(); self.file_edit.setReadOnly(True)
        b = QPushButton(T("browse")); b.setObjectName("Secondary"); b.clicked.connect(self.load)
        top.addWidget(QLabel(T("pdf_file_label"))); top.addWidget(self.file_edit, 1); top.addWidget(b)
        layout.addLayout(top)

        card = QFrame(); card.setObjectName("Card")
        form = QFormLayout(card)
        self.title_e    = QLineEdit(); form.addRow(T("metadata_title_f"),    self.title_e)
        self.author_e   = QLineEdit(); form.addRow(T("metadata_author_f"),   self.author_e)
        self.subject_e  = QLineEdit(); form.addRow(T("metadata_subject_f"),  self.subject_e)
        self.keywords_e = QLineEdit(); form.addRow(T("metadata_keywords_f"), self.keywords_e)
        self.creator_e  = QLineEdit(); form.addRow(T("metadata_creator_f"),  self.creator_e)
        layout.addWidget(card)

        save = QPushButton(T("metadata_save")); save.clicked.connect(self.save)
        layout.addWidget(save, alignment=Qt.AlignRight)
        layout.addWidget(self.progress)
        layout.addStretch()
        apply_semantic_icons(self)

    def load(self):
        p = pick_open_pdf(self)
        if not p:
            return
        try:
            with open(p, "rb") as fh:
                r = _load_pdf_reader(fh); m = r.metadata or {}
                self.file_edit.setText(p)
                self.title_e.setText(str(m.get("/Title", "") or ""))
                self.author_e.setText(str(m.get("/Author", "") or ""))
                self.subject_e.setText(str(m.get("/Subject", "") or ""))
                self.keywords_e.setText(str(m.get("/Keywords", "") or ""))
                self.creator_e.setText(str(m.get("/Creator", "") or ""))
        except Exception as e:
            show_error(self, T("metadata_title"), str(e))

    def save(self):
        path = self.file_edit.text().strip()
        if not path:
            show_error(self, T("metadata_title"), T("metadata_load_first")); return
        out = pick_save_pdf(self, "with_metadata.pdf", source=path)
        if not out:
            return

        meta = {
            "/Title":    self.title_e.text(),
            "/Author":   self.author_e.text(),
            "/Subject":  self.subject_e.text(),
            "/Keywords": self.keywords_e.text(),
            "/Creator":  self.creator_e.text(),
        }

        def task(report):
            report(0, 0, T("metadata_working"))
            with open(path, "rb") as fh:
                r = _load_pdf_reader(fh); w = PdfWriter()
                for p in r.pages:
                    w.add_page(p)
                w.add_metadata(meta)
                with open(out, "wb") as f:
                    w.write(f)
            return out

        self.run_async(task,
                       lambda r: show_info(self, T("saved"), T("metadata_saved").format(r)),
                       T("metadata_working"))

# =============================================================================
#  About page (in-app)
# =============================================================================

class AboutPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        title = QLabel(T("about_title")); title.setObjectName("PageTitle")


        layout.addWidget(title)

        card = QFrame(); card.setObjectName("Card")
        card_layout = QVBoxLayout(card)

        name = QLabel(APP_AUTHOR)
        f = QFont(); f.setPointSize(18); f.setBold(True)
        name.setFont(f)
        name.setStyleSheet("color:#8FA2FF;")
        card_layout.addWidget(name)

        handle = QLabel(f"@{APP_HANDLE}  ·  {T('about_role')}")
        handle.setStyleSheet("color:#A8AECB; padding-bottom: 6px;")
        card_layout.addWidget(handle)

        bio = QLabel(T("about_bio"))
        bio.setWordWrap(True)
        bio.setStyleSheet("color:#DBE2FF; padding: 6px 0 12px 0; font-size: 11pt;")
        card_layout.addWidget(bio)

        links = QHBoxLayout()
        for label_key, url in (("about_github", APP_GITHUB),
                               ("about_website", APP_WEBSITE),
                               ("about_linkedin", APP_LINKEDIN)):
            btn = QPushButton(T(label_key))
            btn.setObjectName("Secondary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, u=url: open_url(u))
            links.addWidget(btn)
        links.addStretch()
        card_layout.addLayout(links)

        layout.addWidget(card)

        info = QLabel(f"{APP_NAME}  v{APP_VERSION}  ·  {T('about_license')}")
        info.setStyleSheet("color:#7C82A3; padding-top: 12px;")
        layout.addWidget(info)

        layout.addStretch()
        apply_semantic_icons(self)

# =============================================================================
#  Splash / About dialog (popup on startup)
# =============================================================================

class AboutDialog(QDialog):
    def __init__(self, parent=None, show_dontshow: bool = True):
        super().__init__(parent)
        self.setWindowTitle(T("about_app"))
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        header = QLabel(APP_NAME)
        hf = QFont(); hf.setPointSize(22); hf.setBold(True)
        header.setFont(hf); header.setStyleSheet("color:#8FA2FF;")
        header.setAlignment(Qt.AlignCenter)
        layout.addWidget(header)

        subtitle = QLabel(f"v{APP_VERSION}  ·  {T('app_subtitle')}")
        subtitle.setStyleSheet("color:#A8AECB;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        line = QFrame(); line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:#2A2F42; background:#2A2F42; max-height:1px;")
        layout.addWidget(line)

        name = QLabel(APP_AUTHOR)
        nf = QFont(); nf.setPointSize(14); nf.setBold(True)
        name.setFont(nf); name.setStyleSheet("color:#EDEFF7; padding-top: 6px;")
        name.setAlignment(Qt.AlignCenter)
        layout.addWidget(name)

        role = QLabel(f"@{APP_HANDLE}  ·  {T('about_role')}")
        role.setStyleSheet("color:#A8AECB;")
        role.setAlignment(Qt.AlignCenter)
        layout.addWidget(role)

        bio = QLabel(T("about_bio"))
        bio.setWordWrap(True)
        bio.setAlignment(Qt.AlignCenter)
        bio.setStyleSheet("color:#DBE2FF; padding: 8px 0;")
        layout.addWidget(bio)

        links = QHBoxLayout()
        links.addStretch()
        for label_key, url in (("about_github", APP_GITHUB),
                               ("about_website", APP_WEBSITE),
                               ("about_linkedin", APP_LINKEDIN)):
            btn = QPushButton(T(label_key))
            btn.setObjectName("Secondary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, u=url: open_url(u))
            links.addWidget(btn)
        links.addStretch()
        layout.addLayout(links)

        thanks = QLabel(T("about_thanks"))
        thanks.setStyleSheet("color:#7C82A3; padding-top: 8px;")
        thanks.setAlignment(Qt.AlignCenter)
        layout.addWidget(thanks)

        license_lbl = QLabel(T("about_license"))
        license_lbl.setStyleSheet("color:#7C82A3; padding-top: 2px;")
        license_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(license_lbl)

        # Don't-show-again checkbox (splash mode only)
        self.dont_show = None
        if show_dontshow:
            self.dont_show = QCheckBox(T("splash_dontshow"))
            self.dont_show.setStyleSheet("color:#A8AECB;")
            layout.addWidget(self.dont_show, alignment=Qt.AlignCenter)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(T("about_close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        apply_semantic_icons(self)

    def suppressed(self) -> bool:
        return bool(self.dont_show and self.dont_show.isChecked())

# =============================================================================
#  Main Window
# =============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — {T('app_subtitle')}")
        self.resize(1280, 820)
        self.setMinimumSize(880, 600)

        self._build_menubar()

        self.sidebar_visible = True

        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        # Sidebar
        self.sidebar = QWidget(); self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(248)
        sb = QVBoxLayout(self.sidebar); sb.setContentsMargins(0, 0, 0, 0); sb.setSpacing(2)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 20, 12, 14)
        header_layout.setSpacing(10)
        title_box = QWidget()
        title_layout = QVBoxLayout(title_box)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        brand = QLabel(APP_NAME); brand.setObjectName("SidebarTitle")
        # Ensure Qt reserves enough vertical space for the font ascent + descent
        # (padding in QSS is not counted in QLabel.sizeHint()).
        _fm = brand.fontMetrics()
        brand.setMinimumHeight(_fm.height() + 6)
        brand.setContentsMargins(0, 2, 0, 0)
        tag   = QLabel(f"v{APP_VERSION}  ·  {T('app_subtitle')}"); tag.setObjectName("SidebarSubtitle")
        tag.setWordWrap(True)
        title_layout.addWidget(brand)
        title_layout.addWidget(tag)
        header_layout.addWidget(title_box, 1)

        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setObjectName("Secondary")
        self.sidebar_toggle_btn.setProperty("iconOnly", True)
        self.sidebar_toggle_btn.setFixedSize(34, 34)
        self.sidebar_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.sidebar_toggle_btn.setToolTip(T("sidebar_hide"))
        self.sidebar_toggle_btn.setAccessibleName(T("sidebar_hide"))
        self.sidebar_toggle_btn.clicked.connect(self.toggle_sidebar)
        header_layout.addWidget(self.sidebar_toggle_btn, 0, Qt.AlignVCenter)
        sb.addWidget(header)

        self.nav_buttons: List[QPushButton] = []
        self.stack = QStackedWidget()

        nav_items = [
            (T("nav_reader"),    PdfViewer),
            (T("nav_merge"),     MergePage),
            (T("nav_split"),     SplitPage),
            (T("nav_compress"),  CompressPage),
            (T("nav_extract"),   ExtractPage),
            (T("nav_organize"),  OrganizePage),
            (T("nav_security"),  SecurityPage),
            (T("nav_watermark"), WatermarkPage),
            (T("nav_metadata"),  MetadataPage),
            (T("nav_about"),     AboutPage),
        ]

        # Scrollable nav area; footer stays pinned at the bottom.
        nav_scroll = QScrollArea()
        nav_scroll.setObjectName("SidebarScroll")
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.NoFrame)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        nav_host = QWidget()
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 4, 0, 8)
        nav_layout.setSpacing(2)
        for label, cls in nav_items:
            btn = QPushButton(label); btn.setObjectName("NavButton")
            btn.setCheckable(True); btn.setCursor(Qt.PointingHandCursor)
            page = cls()
            nav_layout.addWidget(btn); self.stack.addWidget(page)
            self.nav_buttons.append(btn)
            btn.clicked.connect(lambda _, b=btn: self._select(b))
        nav_layout.addStretch()
        nav_scroll.setWidget(nav_host)
        sb.addWidget(nav_scroll, 1)

        # Pinned footer (does not scroll)
        footer = QLabel(f"© {APP_AUTHOR}\nv{APP_VERSION}")
        footer.setObjectName("SidebarFooter")
        footer.setAlignment(Qt.AlignCenter)
        footer.setWordWrap(True)
        sb.addWidget(footer, 0)
        apply_semantic_icons(self)
        _set_widget_icon(self.sidebar_toggle_btn, _icon_for_key("reader_sidebar", self))


        # Content
        content = QWidget(); content.setObjectName("ContentArea")
        cl = QVBoxLayout(content); cl.setContentsMargins(22, 20, 22, 20)
        cl.addWidget(self.stack)

        self.sidebar_handle = QPushButton()
        self.sidebar_handle.setObjectName("Secondary")
        self.sidebar_handle.setProperty("iconOnly", True)
        self.sidebar_handle.setFixedWidth(30)
        self.sidebar_handle.setToolTip(T("sidebar_show"))
        self.sidebar_handle.setAccessibleName(T("sidebar_show"))
        self.sidebar_handle.clicked.connect(self.toggle_sidebar)
        self.sidebar_handle.setVisible(False)

        root.addWidget(self.sidebar)
        root.addWidget(self.sidebar_handle)
        root.addWidget(content, 1)
        self._select(self.nav_buttons[0])
        self._apply_sidebar_state()
        apply_semantic_icons(self)

        sbar = QStatusBar(); self.setStatusBar(sbar)
        sbar.showMessage(f"{T('ready')}  ·  {APP_NAME} v{APP_VERSION}")

        # Global F11 -> fullscreen presentation for the reader
        QShortcut(QKeySequence('F11'), self, activated=self._toggle_reader_fullscreen)
        QShortcut(QKeySequence('Escape'), self, activated=self._exit_fullscreen_if_active)

    # ---- fullscreen ----
    def _toggle_reader_fullscreen(self):
        # Switch to Reader tab and toggle fullscreen
        for i, b in enumerate(self.nav_buttons):
            page = self.stack.widget(i)
            if isinstance(page, PdfViewer):
                self._select(b); page.toggle_fullscreen(); return

    def _exit_fullscreen_if_active(self):
        if self.isFullScreen():
            self._toggle_reader_fullscreen()

    def _apply_sidebar_state(self) -> None:
        self.sidebar.setVisible(self.sidebar_visible)
        self.sidebar_handle.setVisible(not self.sidebar_visible)
        self.sidebar_toggle_btn.setToolTip(T("sidebar_hide") if self.sidebar_visible else T("sidebar_show"))
        self.sidebar_handle.setToolTip(T("sidebar_show"))
        _set_widget_icon(self.sidebar_toggle_btn, _icon_for_key("reader_sidebar", self))
        _set_widget_icon(self.sidebar_handle, _icon_for_key("reader_sidebar", self))

    def toggle_sidebar(self):
        self.sidebar_visible = not self.sidebar_visible
        self._apply_sidebar_state()

    # ---- menubar / language ----

    def _build_menubar(self):
        mb = self.menuBar()

        m_file = mb.addMenu(T("menu_file"))

        # Language first
        m_lang = m_file.addMenu(T("menu_language"))
        self._lang_group = QActionGroup(self); self._lang_group.setExclusive(True)
        for code, label_key in (("en", "menu_english"), ("fa", "menu_persian")):
            a = QAction(T(label_key), self, checkable=True)
            a.setChecked(LANG == code)
            a.triggered.connect(lambda _=False, c=code: self._change_language(c))
            self._lang_group.addAction(a)
            m_lang.addAction(a)

        m_file.addSeparator()

        # Exit last
        act_exit = QAction(T("menu_exit"), self)
        act_exit.setShortcut(QKeySequence.Quit)
        act_exit.triggered.connect(self.close)
        m_file.addAction(act_exit)

        # View → Theme
        m_view = mb.addMenu(T("menu_view"))
        m_theme = m_view.addMenu(T("menu_theme"))
        self._theme_group = QActionGroup(self); self._theme_group.setExclusive(True)
        for code, label_key in (("dark", "app_theme_dark"),
                                ("light", "app_theme_light"),
                                ("sepia", "app_theme_sepia")):
            a = QAction(T(label_key), self, checkable=True)
            a.setChecked(APP_THEME == code)
            a.triggered.connect(lambda _=False, c=code: apply_app_theme(c))
            self._theme_group.addAction(a); m_theme.addAction(a)

        m_help = mb.addMenu(T("menu_help"))
        act_about = QAction(T("menu_about"), self)
        act_about.triggered.connect(self._show_about)
        m_help.addAction(act_about)


    def _change_language(self, code: str) -> None:
        global LANG
        if code == LANG:
            return
        LANG = code
        settings = QSettings("bazzazi", "PDFMaster")
        settings.setValue("lang", code)
        show_info(self, T("menu_language"), T("language_changed"))
        # Rebuild UI atomically: create a new main window, swap, close old.
        app = QApplication.instance()
        app.setLayoutDirection(Qt.RightToLeft if code == "fa" else Qt.LeftToRight)
        new_win = MainWindow()
        app._main_window = new_win
        new_win.show()
        self.close()

    def _show_about(self):
        AboutDialog(self, show_dontshow=False).exec_()

    def _select(self, btn: QPushButton):
        for b in self.nav_buttons:
            b.setChecked(b is btn)
        self.stack.setCurrentIndex(self.nav_buttons.index(btn))

# =============================================================================
#  Entry point
# =============================================================================

def _load_language() -> str:
    settings = QSettings("bazzazi", "PDFMaster")
    code = settings.value("lang", "en")
    if code not in I18N:
        code = "en"
    return code


def _maybe_show_splash(parent) -> None:
    """Splash / lazy-opened startup dialog: intentionally disabled per user
    request — the About dialog is still available from Help → About."""
    return





def main():
    global LANG, APP_THEME
    # High-DPI attributes MUST be set before QApplication is created
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("bazzazi")
    app.setOrganizationDomain("mohammadalibazzazi.ir")

    # Load persisted theme BEFORE creating widgets so icons tint correctly.
    _settings = QSettings("bazzazi", "PDFMaster")
    saved_theme = str(_settings.value("app_theme", "dark") or "dark")
    APP_THEME = saved_theme if saved_theme in APP_THEMES else "dark"
    app.setStyleSheet(APP_THEMES[APP_THEME])

    # Bundled app icon (offline, no network dependency)
    _app_icon_path = ICON_DIR / "app.svg"
    if _app_icon_path.exists():
        app.setWindowIcon(QIcon(str(_app_icon_path)))

    LANG = _load_language()
    app.setLayoutDirection(Qt.RightToLeft if LANG == "fa" else Qt.LeftToRight)

    win = MainWindow()
    app._main_window = win
    win.show()


    _maybe_show_splash(win)

    sys.exit(app.exec_())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            input("Press Enter to exit...")
        except EOFError:
            pass
