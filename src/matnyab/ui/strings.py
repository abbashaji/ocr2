"""Every user-visible string of the interface (Persian). No literals in widgets.

Placeholders use ``str.format`` names, e.g. ``S.uncertain_counter.format(i=..., n=...)``;
numbers must be passed through ``ui.format.fa_digits`` before formatting.
"""

from __future__ import annotations

from typing import Iterator


class _Strings:
    # ------------------------------------------------------------- app ---
    app_name = "متن‌یاب"
    app_tagline = "تبدیل تصویر به متن فارسی"
    app_monogram = "م"
    window_title = "متن‌یاب"

    # ---------------------------------------------------------- header ---
    btn_open = "انتخاب تصویر"
    tt_open = "انتخاب یک یا چند تصویر"
    tt_queue = "نمایش یا پنهان‌کردن صف پردازش"
    tt_history = "تاریخچهٔ نتیجه‌ها"
    tt_theme_to_dark = "تغییر به پوستهٔ تاریک"
    tt_theme_to_light = "تغییر به پوستهٔ روشن"
    tt_settings = "تنظیمات"
    tt_about = "دربارهٔ برنامه"
    tt_shortcuts = "میانبرهای صفحه‌کلید"

    # ----------------------------------------------------- empty state ---
    empty_title = "تصویر را اینجا رها کنید"
    empty_title_drag = "رها کنید تا تشخیص متن شروع شود"
    empty_hint = (
        "یا با Ctrl+V تصویر کلیپ‌بورد را بچسبانید؛ "
        "مثلاً عکسی که با Win+Shift+S از صفحه گرفته‌اید."
    )
    btn_choose = "انتخاب تصویر…"
    btn_paste = "چسباندن از کلیپ‌بورد"
    empty_formats = "فرمت‌های پشتیبانی‌شده: PNG، JPG، BMP، TIFF، WebP و GIF (فریم اول)"
    empty_privacy = (
        "همه‌چیز روی همین رایانه انجام می‌شود؛ "
        "تصویر و متن شما هرگز به اینترنت فرستاده نمی‌شود."
    )
    empty_drop_access = "ناحیهٔ رهاکردن تصویر"

    # ----------------------------------------------------------- viewer ---
    zoom_in = "بزرگ‌نمایی"
    zoom_out = "کوچک‌نمایی"
    zoom_fit = "اندازهٔ پنجره"
    zoom_actual = "اندازهٔ واقعی"
    zoom_label_access = "میزان بزرگ‌نمایی تصویر"
    viewer_access = "نمایشگر تصویر"
    viewer_access_desc = "تصویر اصلی؛ با Ctrl و چرخ ماوس بزرگ‌نمایی کنید و با کشیدن جابه‌جا شوید."
    highlight_uncertain = "نمایش واژه‌های مشکوک"
    show_boxes = "نمایش کادر واژه‌ها"
    viewer_loading = "در حال بارگذاری تصویر…"
    viewer_no_image = "تصویر این مورد ذخیره نشده است"
    viewer_no_image_hint = "برای نمایش دوبارهٔ تصویر، آن را دوباره باز کنید."

    # ----------------------------------------------------------- editor ---
    editor_access = "ویرایشگر متن نتیجه"
    editor_access_desc = "متن شناسایی‌شده؛ واژه‌های مشکوک با خط موجی زیرشان مشخص شده‌اند."
    editor_placeholder = "متن شناسایی‌شده اینجا نمایش داده می‌شود."
    copy_all = "کپی همه"
    copy_sel = "کپی انتخاب"
    save = "ذخیره…"
    rerun = "اجرای دوباره"
    rerun_other = "اجرای دوباره با حالت دیگر"
    clear = "پاک‌کردن"
    undo = "واگرد"
    redo = "ازنو"
    find = "جست‌وجو"
    font_inc = "بزرگ‌تر کردن متن"
    font_dec = "کوچک‌تر کردن متن"
    next_uncertain = "واژهٔ مشکوک بعدی"
    prev_uncertain = "واژهٔ مشکوک قبلی"
    uncertain_counter = "{i} از {n}"
    uncertain_total = "{n} واژهٔ مشکوک"
    uncertain_none = "واژهٔ مشکوکی نیست"
    uncertain_counter_access = "شمارندهٔ واژه‌های مشکوک"
    find_placeholder = "جست‌وجو در متن"
    find_next = "نتیجهٔ بعدی"
    find_prev = "نتیجهٔ قبلی"
    find_close = "بستن نوار جست‌وجو"
    find_none = "بدون نتیجه"
    find_count = "{i} از {n}"
    counter_words_chars = "{w} واژه · {c} نویسه"
    counter_access = "شمارندهٔ واژه و نویسه"

    # ------------------------------------------------------------ modes ---
    mode_auto = "خودکار"
    mode_raw = "خام"
    mode_lex = "واژه‌نامه‌ای"
    mode_auto_desc = "برنامه خودش بهترین حالت را برای هر تصویر انتخاب می‌کند."
    mode_raw_desc = "خروجی مستقیم موتور تشخیص، بدون اصلاح؛ سریع و بدون دخالت."
    mode_lex_desc = "واژه‌ها با فرهنگ لغت فارسی اصلاح می‌شوند؛ مناسب تصویرهای کم‌کیفیت."

    # ------------------------------------------------------------ chips ---
    conf_high = "اطمینان بالا"
    conf_mid = "اطمینان متوسط"
    conf_low = "اطمینان کم"
    chip_confidence = "{label}"
    conf_high_short = "بالا"
    conf_mid_short = "متوسط"
    conf_low_short = "کم"
    conf_tip = "برآورد خود موتور از اطمینانش است، نه دقت واقعی. واژه‌های مشکوک را مرور کنید."
    chip_mode = "حالت: {mode}"
    chip_time = "{s} ثانیه"
    chip_words_uncertain = "{n} واژهٔ مشکوک"

    # ------------------------------------------------------ status bar ---
    stage_idle = "آماده"
    stage_preparing = "آماده‌سازی تصویر…"
    stage_segmenting = "تشخیص خط‌ها…"
    stage_recognizing = "خواندن متن…"
    stage_correcting = "اصلاح و بررسی…"
    stage_done = "انجام شد"
    stage_cancelling = "در حال لغو…"
    stage_cancelled = "لغو شد"
    stage_queued = "در انتظار نوبت"
    stage_error = "خطا در پردازش"
    stage_with_queue = "{stage} ({i} از {n})"
    elapsed_access = "زمان سپری‌شده"
    progress_access = "پیشرفت پردازش"
    status_access = "وضعیت پردازش"

    # ---------------------------------------------------- processing card ---
    proc_title = "در حال تشخیص متن"
    proc_title_queued = "این تصویر در صف است"
    proc_hint = "می‌توانید تصویر را همین حالا بررسی کنید؛ متن به‌محض آماده‌شدن اینجا ظاهر می‌شود."
    proc_hint_queued = "برای شروع پردازش، دکمهٔ زیر را بزنید."
    btn_cancel = "لغو"
    btn_start = "شروع پردازش"

    # ------------------------------------------------------------ queue ---
    queue_title = "صف پردازش"
    queue_empty = "صف خالی است"
    queue_add = "افزودن تصویر"
    queue_process_all = "پردازش همه"
    queue_save_all = "ذخیرهٔ همه…"
    queue_save_all_tip = "ذخیرهٔ نتیجهٔ همهٔ تصویرها در یک پوشه (یک فایل TXT برای هر تصویر)"
    queue_remove_done = "برداشتن تمام‌شده‌ها"
    queue_overall = "{done} از {total} انجام شد"
    queue_list_access = "فهرست صف پردازش"
    queue_item_access = "{name}، {status}"
    st_queued = "در صف"
    st_processing = "در حال پردازش"
    st_done = "تمام شد · {pct}"
    st_error = "خطا"
    st_history = "از تاریخچه"
    item_open = "باز کردن"
    item_retry = "تلاش دوباره"
    item_remove = "حذف از صف"
    pasted_image_name = "تصویر چسبانده‌شده {n}"
    save_all_done = "{n} فایل ذخیره شد"
    save_all_none = "هنوز نتیجه‌ای برای ذخیره نیست"
    save_all_choose_dir = "پوشهٔ ذخیره را انتخاب کنید"

    # ---------------------------------------------------------- history ---
    history_title = "تاریخچه"
    history_empty = "هنوز چیزی در تاریخچه نیست"
    history_empty_hint = "نتیجهٔ هر تصویر پس از پردازش اینجا ذخیره می‌شود."
    history_open = "باز کردن در ویرایشگر"
    history_delete = "حذف"
    history_clear = "پاک‌کردن همه"
    history_close = "بستن تاریخچه"
    history_confirm_clear = "همهٔ موردهای تاریخچه حذف شوند؟ این کار قابل بازگشت نیست."
    history_list_access = "فهرست تاریخچه"
    history_item_access = "{source}، {when}"

    # --------------------------------------------------------- settings ---
    settings_title = "تنظیمات"
    settings_close = "بستن"
    set_section_appearance = "ظاهر"
    set_theme = "پوسته"
    theme_system = "همسو با سیستم"
    theme_light = "روشن"
    theme_dark = "تاریک"
    set_section_recognition = "تشخیص متن"
    set_mode = "حالت تشخیص"
    set_section_text = "متن خروجی"
    set_digits = "شکل ارقام"
    digits_keep = "بدون تغییر"
    digits_keep_desc = "ارقام همان‌طور که در تصویر هستند می‌مانند."
    digits_fa = "فارسی (۱۲۳)"
    digits_fa_desc = "همهٔ ارقام هنگام کپی و ذخیره به فارسی تبدیل می‌شوند."
    digits_en = "انگلیسی (123)"
    digits_en_desc = "همهٔ ارقام هنگام کپی و ذخیره به انگلیسی تبدیل می‌شوند."
    set_normalize = "یکسان‌سازی حرف‌های عربی (ي ← ی، ك ← ک)"
    set_normalize_desc = "هنگام کپی و ذخیره اعمال می‌شود؛ متن داخل ویرایشگر دست‌نخورده می‌ماند."
    set_font_size = "اندازهٔ متن ویرایشگر"
    set_font_pt = "{n} پوینت"
    set_font_preview = "متن‌یاب: این یک نمونه برای دیدن اندازهٔ نوشته است."
    set_applies_live = "تغییرها بلافاصله اعمال و ذخیره می‌شوند."

    # -------------------------------------------------- shortcuts, about ---
    shortcuts_title = "میانبرهای صفحه‌کلید"
    shortcuts_close = "بستن"
    sc_group_files = "فایل"
    sc_group_text = "متن"
    sc_group_view = "نما"
    sc_group_app = "برنامه"
    sc_open = "انتخاب تصویر"
    sc_open_folder = "انتخاب پوشه"
    sc_paste = "چسباندن تصویر از کلیپ‌بورد"
    sc_save = "ذخیرهٔ متن"
    sc_copy_all = "کپی همهٔ متن"
    sc_copy_sel = "کپی بخش انتخاب‌شده"
    sc_find = "جست‌وجو در متن"
    sc_next_unc = "واژهٔ مشکوک بعدی"
    sc_prev_unc = "واژهٔ مشکوک قبلی"
    sc_font_inc = "بزرگ‌تر کردن متن"
    sc_font_dec = "کوچک‌تر کردن متن"
    sc_zoom_in = "بزرگ‌نمایی تصویر"
    sc_zoom_out = "کوچک‌نمایی تصویر"
    sc_zoom_fit = "اندازهٔ پنجره"
    sc_zoom_actual = "اندازهٔ واقعی"
    sc_zoom_wheel = "بزرگ‌نمایی با چرخ ماوس"
    sc_process_all = "پردازش همهٔ صف"
    sc_cancel = "لغو پردازش یا بستن جست‌وجو"
    sc_queue = "نمایش یا پنهان‌کردن صف"
    sc_history = "تاریخچه"
    sc_settings = "تنظیمات"
    sc_theme = "تغییر پوسته"
    sc_shortcuts = "همین راهنما"

    about_title = "دربارهٔ متن‌یاب"
    about_close = "بستن"
    about_version = "نسخهٔ {v}"
    about_offline = (
        "متن‌یاب کاملاً آفلاین کار می‌کند: تصویرها و متن‌ها روی همین رایانه "
        "پردازش می‌شوند و هیچ داده‌ای به اینترنت فرستاده نمی‌شود."
    )
    about_licences_title = "پروانه‌ها و سپاس"
    about_licences = (
        "تشخیص متن با موتور Tesseract (پروانهٔ Apache 2.0)؛ "
        "رابط کاربری با Qt for Python (پروانهٔ LGPLv3)؛ "
        "قلم وزیرمتن (پروانهٔ SIL OFL 1.1)."
    )

    # ------------------------------------------------------------ toasts ---
    toast_copied = "متن کپی شد"
    toast_copied_sel = "بخش انتخاب‌شده کپی شد"
    toast_saved = "ذخیره شد: {name}"
    toast_nothing_to_copy = "متنی برای کپی وجود ندارد"
    toast_no_image_in_clipboard = "تصویری در کلیپ‌بورد پیدا نشد"
    toast_cleared = "متن پاک شد"
    toast_undo = "بازگردانی"
    toast_added = "{n} تصویر به صف اضافه شد"
    toast_no_supported = "هیچ تصویر پشتیبانی‌شده‌ای پیدا نشد"
    toast_font_size = "اندازهٔ متن: {n}"
    toast_cancelled = "پردازش لغو شد"
    toast_docx_unavailable = "ذخیره به‌صورت DOCX هنوز در این نسخه آماده نیست؛ لطفاً قالب TXT را انتخاب کنید."
    toast_save_failed = "ذخیره انجام نشد. مسیر یا دسترسی پوشه را بررسی کنید."

    # ------------------------------------------------------- file dialogs ---
    dlg_open_title = "انتخاب تصویر"
    dlg_open_filter = "تصویرها (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif);;همهٔ فایل‌ها (*)"
    dlg_folder_title = "انتخاب پوشهٔ تصویرها"
    dlg_save_title = "ذخیرهٔ متن"
    dlg_save_filter_txt = "متن ساده (*.txt)"
    dlg_save_filter_docx = "سند Word (*.docx)"
    dlg_ok = "تأیید"
    dlg_cancel = "انصراف"
    dlg_yes_continue = "ادامه"
    dlg_no_skip = "رد کردن"

    # ------------------------------------------------------------ errors ---
    err_unreadable_title = "این فایل خوانده نشد"
    err_unreadable_msg = (
        "فایل خراب است یا تصویر معتبری نیست. "
        "فایل دیگری را امتحان کنید یا دوباره آن را ذخیره کنید."
    )
    err_engine_title = "تشخیص متن با خطا روبه‌رو شد"
    err_engine_msg = (
        "پردازش این تصویر کامل نشد. می‌توانید دوباره تلاش کنید؛ "
        "اگر مشکل ادامه داشت، جزئیات فنی را برای پشتیبانی بفرستید."
    )
    err_unavailable_title = "موتور تشخیص متن آماده نیست"
    err_unavailable_msg = (
        "موتور تشخیص متن بارگذاری نشد. برنامه را دوباره باز کنید "
        "یا آن را دوباره نصب کنید."
    )
    err_missing_title = "فایل پیدا نشد"
    err_missing_msg = "این فایل دیگر در مسیر خود نیست؛ شاید جابه‌جا یا حذف شده باشد."
    err_details = "جزئیات فنی"
    err_details_hide = "پنهان‌کردن جزئیات"
    err_retry = "تلاش دوباره"
    err_remove = "حذف از صف"
    err_details_access = "متن فنی خطا"
    big_title = "تصویر بسیار بزرگ است"
    big_msg = (
        "این تصویر حدود {mp} مگاپیکسل است (بیش از {limit}). "
        "پردازش ممکن است کند باشد و حافظهٔ زیادی بگیرد. ادامه می‌دهید؟"
    )
    big_msg_many = (
        "{n} تصویر بیش از {limit} مگاپیکسل دارند. "
        "پردازش آن‌ها ممکن است کند باشد و حافظهٔ زیادی بگیرد. ادامه می‌دهید؟"
    )
    confirm_rerun_title = "اجرای دوباره"
    confirm_rerun_msg = "ویرایش‌های شما در متن فعلی با نتیجهٔ تازه جایگزین می‌شود. ادامه می‌دهید؟"
    crash_title = "مشکلی پیش آمد"
    crash_msg = (
        "یک خطای غیرمنتظره رخ داد، اما برنامه همچنان باز است. "
        "اگر کار شما درست ادامه نیافت، برنامه را ببندید و دوباره باز کنید."
    )
    crash_details = "جزئیات فنی (برای پشتیبانی)"
    crash_log_at = "گزارش در این فایل ذخیره شد: {path}"

    # -------------------------------------------------------------- date ---
    months = (
        "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
        "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
    )
    date_format = "{d} {month} {y}، {hh}:{mm}"
    decimal_sep = "٫"
    percent_sign = "٪"
    ellipsis_words = "…"

    def __getitem__(self, key: str) -> str:
        try:
            return getattr(self, key)
        except AttributeError as exc:
            raise KeyError(key) from exc

    def keys(self) -> Iterator[str]:
        for name in dir(type(self)):
            if not name.startswith("_") and name != "keys":
                yield name


S = _Strings()
