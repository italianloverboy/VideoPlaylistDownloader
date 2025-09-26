import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import os
import sys
import urllib.request
import zipfile
import webbrowser
import subprocess

# Try to import yt_dlp, if not found, we can't run
try:
    import yt_dlp
    from yt_dlp.update import Updater, detect_variant
    from yt_dlp.version import __version__
except ImportError:
    messagebox.showerror("Critical Error", "yt-dlp module not found. The application cannot start.\n" \
                                           "Please run the compiled executable or install yt-dlp.")
    sys.exit(1)


class MyLogger:
    def __init__(self, gui_log_func):
        self.gui_log_func = gui_log_func

    def debug(self, msg):
        if msg.startswith('[debug] '):
            pass
        else:
            self.info(msg)

    def info(self, msg):
        self.gui_log_func(msg + '\n')

    def warning(self, msg):
        self.gui_log_func(f"[WARNING] {msg}\n")

    def error(self, msg):
        self.gui_log_func(f"[ERROR] {msg}\n")

# Mock YDL object for the Updater class
class MockYDL:
    def __init__(self, logger):
        self.logger = logger
        self.params = {}

    def to_screen(self, msg):
        self.logger.info(msg)

    def report_warning(self, msg):
        self.logger.warning(msg)
    
    def report_error(self, msg, tb=None):
        self.logger.error(msg)

    def write_debug(self, msg):
        pass # We don't need debug logs from the updater

    def urlopen(self, req):
        # A basic urlopen to avoid needing the full networking stack of yt-dlp
        if isinstance(req, str):
            return urllib.request.urlopen(req)
        
        headers = {key: val for key, val in req.headers.items()}
        py_req = urllib.request.Request(req.get_full_url(), headers=headers)
        return urllib.request.urlopen(py_req)


class YtDlpGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"VPD - Video Playlist Downloader (v{__version__})")
        self.geometry("800x700")

        self.create_menu()

        self.ffmpeg_path = os.path.join(self.get_application_path(), "bin")
        self.after(100, self.initial_checks)
        self.after(500, self.start_update_check_thread) # Check for updates on startup

        self.queue = []
        self.stop_event = threading.Event()
        self.is_downloading = False

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.grid_rowconfigure(4, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)

        url_frame = ttk.LabelFrame(main_frame, text="Add URL to Queue")
        url_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        url_frame.grid_columnconfigure(0, weight=1)
        self.url_entry = ttk.Entry(url_frame, width=80)
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.add_button = ttk.Button(url_frame, text="Add", command=self.add_to_queue)
        self.add_button.grid(row=0, column=1, padx=5, pady=5)
        self.make_entry_context_menu(self.url_entry)

        queue_frame = ttk.LabelFrame(main_frame, text="Download Queue")
        queue_frame.grid(row=1, column=0, columnspan=2, sticky="ewns", padx=5, pady=5)
        queue_frame.grid_rowconfigure(0, weight=1)
        queue_frame.grid_columnconfigure(0, weight=1)
        self.queue_listbox = tk.Listbox(queue_frame)
        self.queue_listbox.grid(row=0, column=0, sticky="ewns")
        queue_scrollbar = ttk.Scrollbar(queue_frame, orient=tk.VERTICAL, command=self.queue_listbox.yview)
        self.queue_listbox.config(yscrollcommand=queue_scrollbar.set)
        queue_scrollbar.grid(row=0, column=1, sticky="ns")
        queue_buttons_frame = ttk.Frame(queue_frame)
        queue_buttons_frame.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.remove_button = ttk.Button(queue_buttons_frame, text="Remove Selected", command=self.remove_selected)
        self.remove_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.clear_button = ttk.Button(queue_buttons_frame, text="Clear Queue", command=self.clear_queue)
        self.clear_button.pack(side=tk.LEFT, padx=5, pady=5)

        options_frame = ttk.LabelFrame(main_frame, text="Options")
        options_frame.grid(row=2, column=0, sticky="ewns", padx=5, pady=5)
        options_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(options_frame, text="Format:").grid(row=0, column=0, sticky="w", padx=5, pady=2)
        self.format_var = tk.StringVar(value="Video + Audio")
        self.format_menu = ttk.Combobox(options_frame, textvariable=self.format_var, values=["Video + Audio", "Audio Only (mp3)", "Audio Only (m4a)", "Video Only"])
        self.format_menu.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(options_frame, text="Video Quality:").grid(row=1, column=0, sticky="w", padx=5, pady=2)
        self.quality_var = tk.StringVar(value="best")
        self.quality_menu = ttk.Combobox(options_frame, textvariable=self.quality_var, values=["best", "1080p", "720p", "480p"])
        self.quality_menu.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(options_frame, text="Container:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.container_var = tk.StringVar(value="Auto (mkv)")
        self.container_menu = ttk.Combobox(options_frame, textvariable=self.container_var, values=["Auto (mkv)", "MP4 (compatible)"])
        self.container_menu.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        ttk.Label(options_frame, text="Save to:").grid(row=3, column=0, sticky="w", padx=5, pady=2)
        self.path_var = tk.StringVar(value="")
        path_entry = ttk.Entry(options_frame, textvariable=self.path_var, state="readonly")
        path_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        self.browse_button = ttk.Button(options_frame, text="Browse...", command=self.browse_path)
        self.browse_button.grid(row=3, column=2, padx=5, pady=2)

        self.write_subs_var = tk.BooleanVar()
        subs_check = ttk.Checkbutton(options_frame, text="Download subtitles", variable=self.write_subs_var)
        subs_check.grid(row=4, column=0, sticky="w", padx=5, pady=2)

        ttk.Label(options_frame, text="Languages (e.g., en,it):").grid(row=5, column=0, sticky="w", padx=5, pady=2)
        self.sub_langs_var = tk.StringVar(value="en,it")
        subs_lang_entry = ttk.Entry(options_frame, textvariable=self.sub_langs_var)
        subs_lang_entry.grid(row=5, column=1, sticky="ew", padx=5, pady=2)

        self.no_playlist_var = tk.BooleanVar(value=False)
        no_playlist_check = ttk.Checkbutton(options_frame, text="Download single video only (if URL is in a playlist)", variable=self.no_playlist_var)
        no_playlist_check.grid(row=6, column=0, columnspan=3, sticky="w", padx=5, pady=2)

        download_frame = ttk.Frame(main_frame)
        download_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        download_frame.grid_columnconfigure(0, weight=1)
        self.start_button = ttk.Button(download_frame, text="Start Download", command=self.start_download_thread)
        self.start_button.grid(row=0, column=0, sticky="ew")
        self.stop_button = ttk.Button(download_frame, text="Stop Queue", command=self.stop_download, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=10)

        log_frame = ttk.LabelFrame(main_frame, text="Log")
        log_frame.grid(row=4, column=0, columnspan=2, sticky="ewns", padx=5, pady=5)
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=10, state=tk.DISABLED, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky="ewns")
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=log_scrollbar.set)
        log_scrollbar.grid(row=0, column=1, sticky="ns")

    def make_entry_context_menu(self, entry):
        menu = tk.Menu(entry, tearoff=0)
        menu.add_command(label="Cut", command=lambda: entry.event_generate('<<Cut>>'))
        menu.add_command(label="Copy", command=lambda: entry.event_generate('<<Copy>>'))
        menu.add_command(label="Paste", command=lambda: entry.event_generate('<<Paste>>'))
        entry.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def create_menu(self):
        menubar = tk.Menu(self)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Quick Guide", command=self.show_help_window)
        help_menu.add_command(label="Supported Sites", command=self.show_supported_sites_window)
        help_menu.add_separator()
        help_menu.add_command(label="Check for Updates", command=self.start_update_check_thread)
        help_menu.add_separator()
        help_menu.add_command(label="About VPD", command=self.show_about_window)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menubar)

    def show_help_window(self):
        messagebox.showinfo("Quick Guide",
            "1. Paste a link (video or playlist) into the top field and click \"Add\".\n\n" \
            "2. Repeat for all the links you want to download.\n\n" \
            "3. Select your desired options (format, quality, folder, subtitles).\n\n" \
            "4. Click \"Start Download\" to begin processing the queue.")

    def show_supported_sites_window(self):
        # ... (omitted for brevity, no changes here)

    def show_about_window(self):
        # ... (omitted for brevity, no changes here)

    def open_link(self, url):
        webbrowser.open_new(url)

    def get_application_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    # --- Update Logic ---
    def start_update_check_thread(self, on_startup=True):
        update_thread = threading.Thread(target=self.run_update_check, args=(on_startup,), daemon=True)
        update_thread.start()

    def run_update_check(self, on_startup=True):
        self.log("---" + " Checking for updates... " + "---\n")
        mock_ydl = MockYDL(MyLogger(self.log))
        updater = Updater(mock_ydl)
        
        try:
            update_info = updater.query_update()
            if not update_info:
                self.log("yt-dlp is up to date.\n")
                if not on_startup:
                    self.after(0, lambda: messagebox.showinfo("No Updates", "You are already using the latest version."))
                return

            self.after(0, self.prompt_for_update, updater, update_info)

        except Exception as e:
            self.log(f"Update check failed: {e}\n")
            if not on_startup:
                self.after(0, lambda: messagebox.showerror("Update Check Failed", f"Could not check for updates.\n\nError: {e}"))

    def prompt_for_update(self, updater, update_info):
        variant = detect_variant()
        
        if variant == 'source':
            messagebox.showinfo("Update Available", 
                f"A new version ({update_info.version}) is available.\n" \
                "Please run \"git pull\" in your terminal to update.")
        elif variant in ('zip', 'unknown'):
            if messagebox.askyesno("Update Available",
                f"A new version ({update_info.version}) is available.\n" \
                "Do you want to open the download page to get the new ZIP file?"):
                self.open_link("https://github.com/yt-dlp/yt-dlp/releases/latest")
        else: # Executable
            if messagebox.askyesno("Update Available", 
                f"A new version ({update_info.version}) is available.\n" \
                "Do you want to download and install it now? The application will restart."):
                
                self.log("Starting automatic update...")
                update_thread = threading.Thread(target=self.apply_exe_update, args=(updater, update_info), daemon=True)
                update_thread.start()

    def apply_exe_update(self, updater, update_info):
        try:
            updater.update(update_info)
            # The updater class will handle the restart if successful
        except Exception as e:
            self.log(f"Automatic update failed: {e}\n")
            self.after(0, lambda: messagebox.showerror("Update Failed", f"An error occurred during the update process:\n{e}"))

    # --- End of Update Logic ---

    def initial_checks(self):
        if not self.check_ffmpeg():
            if messagebox.askyesno("FFmpeg Not Found", "Warning: FFmpeg is required to merge audio and video.\n\nDo you want the application to download and set it up automatically?"):
                self.download_ffmpeg_thread()

    def check_ffmpeg(self):
        # ... (omitted for brevity, no changes here)

    def download_ffmpeg_thread(self):
        # ... (omitted for brevity, no changes here)

    def download_and_setup_ffmpeg(self):
        # ... (omitted for brevity, no changes here)

    def download_progress_hook(self, count, block_size, total_size):
        # ... (omitted for brevity, no changes here)

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        if '\r' in message:
            current_line = self.log_text.index("end-1c").split('.')[0]
            self.log_text.delete(f"{current_line}.0", f"{current_line}.end")
            self.log_text.insert(f"{current_line}.0", message.strip())
        else:
            self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.update_idletasks()

    def add_to_queue(self):
        # ... (omitted for brevity, no changes here)

    def remove_selected(self):
        # ... (omitted for brevity, no changes here)

    def clear_queue(self):
        # ... (omitted for brevity, no changes here)

    def browse_path(self):
        # ... (omitted for brevity, no changes here)

    def start_download_thread(self):
        # ... (omitted for brevity, no changes here)

    def stop_download(self):
        # ... (omitted for brevity, no changes here)

    def run_download_queue(self):
        # ... (omitted for brevity, no changes here)

    def download_finished(self):
        # ... (omitted for brevity, no changes here)

    def build_ydl_opts(self):
        # ... (omitted for brevity, no changes here)

    def progress_hook(self, d):
        # ... (omitted for brevity, no changes here)

if __name__ == "__main__":
    if hasattr(sys, 'frozen'):
        import yt_dlp.extractor.youtube

    app = YtDlpGui()
    app.mainloop()
