import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import os
import sys
import urllib.request
import zipfile
import webbrowser

# Try to import yt_dlp, if not found, we can't run
try:
    import yt_dlp
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


class YtDlpGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VPD - Video Playlist Downloader")
        self.geometry("800x650")

        self.create_menu()

        self.ffmpeg_path = os.path.join(self.get_application_path(), "bin")
        self.after(100, self.initial_checks)

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
        ttk.Label(options_frame, text="Save to:").grid(row=2, column=0, sticky="w", padx=5, pady=2)
        self.path_var = tk.StringVar(value="")
        path_entry = ttk.Entry(options_frame, textvariable=self.path_var, state="readonly")
        path_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        self.browse_button = ttk.Button(options_frame, text="Browse...", command=self.browse_path)
        self.browse_button.grid(row=2, column=2, padx=5, pady=2)
        self.write_subs_var = tk.BooleanVar()
        subs_check = ttk.Checkbutton(options_frame, text="Download subtitles", variable=self.write_subs_var)
        subs_check.grid(row=3, column=0, sticky="w", padx=5, pady=2)
        ttk.Label(options_frame, text="Languages (e.g., en,it):").grid(row=4, column=0, sticky="w", padx=5, pady=2)
        self.sub_langs_var = tk.StringVar(value="en,it")
        subs_lang_entry = ttk.Entry(options_frame, textvariable=self.sub_langs_var)
        subs_lang_entry.grid(row=4, column=1, sticky="ew", padx=5, pady=2)

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

    def create_menu(self):
        menubar = tk.Menu(self)
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Quick Guide", command=self.show_help_window)
        help_menu.add_command(label="Supported Sites", command=self.show_supported_sites_window)
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
        sites_win = tk.Toplevel(self)
        sites_win.title("Supported Sites")
        sites_win.geometry("500x300")
        sites_win.resizable(False, False)
        main_frame = ttk.Frame(sites_win, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        text_area = tk.Text(main_frame, wrap=tk.WORD, bg=self.cget('bg'), relief=tk.FLAT)
        text_area.pack(fill=tk.BOTH, expand=True)
        text_area.insert(tk.END, "VPD uses yt-dlp technology and supports thousands of sites.\n\n" \
                                 "Besides YouTube, you can download from all the most popular sites, including:\n" \
                                 "- Vimeo\n- Twitch (VODs and clips)\n- Facebook\n- Twitter / X\n- TikTok\n- SoundCloud\n\n...and many more.\n\nFor the full list, please check the ")
        text_area.insert(tk.END, "official page", "yt-dlp-sites-link")
        text_area.insert(tk.END, ".")
        text_area.tag_config("yt-dlp-sites-link", foreground="blue", underline=True)
        text_area.tag_bind("yt-dlp-sites-link", "<Button-1>", lambda e: self.open_link("https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"))
        text_area.tag_bind("yt-dlp-sites-link", "<Enter>", lambda e: text_area.config(cursor="hand2"))
        text_area.tag_bind("yt-dlp-sites-link", "<Leave>", lambda e: text_area.config(cursor=""))
        text_area.config(state=tk.DISABLED)
        sites_win.transient(self)
        sites_win.grab_set()

    def show_about_window(self):
        about_win = tk.Toplevel(self)
        about_win.title("About VPD")
        about_win.geometry("500x400")
        about_win.resizable(False, False)
        main_frame = ttk.Frame(about_win, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        header_label = ttk.Label(main_frame, text="VPD - Video Playlist Downloader", font=("Segoe UI", 14, "bold"))
        header_label.pack(pady=5)
        purpose_label = ttk.Label(main_frame, text="Built to make video downloading easy for everyone.", justify=tk.CENTER)
        purpose_label.pack(pady=5)
        author_label = ttk.Label(main_frame, text="From an idea by: Warcello, SantaFucina", justify=tk.CENTER)
        author_label.pack(pady=5)
        text_area = tk.Text(main_frame, wrap=tk.WORD, bg=self.cget('bg'), relief=tk.FLAT, height=12)
        text_area.pack(fill=tk.X, expand=True, pady=10)
        text_area.insert(tk.END, "This application is a graphical user interface for the powerful ")
        text_area.insert(tk.END, "yt-dlp", "yt-dlp-link")
        text_area.insert(tk.END, " command-line tool. The goal is to simplify the download process, hiding the complexity of the command line.\n\n")
        text_area.insert(tk.END, "- The yt-dlp source code is released under \"The Unlicense\".\n")
        text_area.insert(tk.END, "- This GUI (Copyright (c) 2025 Warcello, SantaFucina) is released under the MIT License.\n")
        text_area.insert(tk.END, "- The application uses ")
        text_area.insert(tk.END, "FFmpeg", "ffmpeg-link")
        text_area.insert(tk.END, " to merge files, which is licensed under the GPL.")
        text_area.tag_config("yt-dlp-link", foreground="blue", underline=True)
        text_area.tag_bind("yt-dlp-link", "<Button-1>", lambda e: self.open_link("https://github.com/yt-dlp/yt-dlp"))
        text_area.tag_bind("yt-dlp-link", "<Enter>", lambda e: text_area.config(cursor="hand2"))
        text_area.tag_bind("yt-dlp-link", "<Leave>", lambda e: text_area.config(cursor=""))
        text_area.tag_config("ffmpeg-link", foreground="blue", underline=True)
        text_area.tag_bind("ffmpeg-link", "<Button-1>", lambda e: self.open_link("https://ffmpeg.org/"))
        text_area.tag_bind("ffmpeg-link", "<Enter>", lambda e: text_area.config(cursor="hand2"))
        text_area.tag_bind("ffmpeg-link", "<Leave>", lambda e: text_area.config(cursor=""))
        text_area.config(state=tk.DISABLED)
        close_button = ttk.Button(main_frame, text="Close", command=about_win.destroy)
        close_button.pack(pady=10)
        about_win.transient(self)
        about_win.grab_set()

    def open_link(self, url):
        webbrowser.open_new(url)

    def get_application_path(self):
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def initial_checks(self):
        if not self.check_ffmpeg():
            if messagebox.askyesno("FFmpeg Not Found", "Warning: FFmpeg is required to merge audio and video.\n\nDo you want the application to download and set it up automatically?"):
                self.download_ffmpeg_thread()

    def check_ffmpeg(self):
        local_ffmpeg_exe = os.path.join(self.ffmpeg_path, "ffmpeg.exe")
        if os.path.exists(local_ffmpeg_exe):
            return True
        try:
            startupinfo = subprocess.STARTUPINFO() if hasattr(subprocess, 'STARTUPINFO') else None
            if startupinfo:
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, startupinfo=startupinfo)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError, AttributeError):
            return False

    def download_ffmpeg_thread(self):
        self.start_button.config(state=tk.DISABLED)
        self.log("---" + "Starting FFmpeg download" + "---" + "\n")
        download_thread = threading.Thread(target=self.download_and_setup_ffmpeg, daemon=True)
        download_thread.start()

    def download_and_setup_ffmpeg(self):
        url = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip"
        zip_path = os.path.join(self.get_application_path(), "ffmpeg.zip")
        try:
            self.log(f"Downloading from {url}...\n")
            urllib.request.urlretrieve(url, zip_path, self.download_progress_hook)
            self.log("\nFFmpeg download complete.\nExtracting...\n")
            os.makedirs(self.ffmpeg_path, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.infolist():
                    if 'bin/ffmpeg.exe' in member.filename or 'bin/ffprobe.exe' in member.filename:
                        member.filename = os.path.basename(member.filename)
                        zip_ref.extract(member, self.ffmpeg_path)
            self.log("FFmpeg successfully extracted to 'bin' folder.\n")
            messagebox.showinfo("Success", "FFmpeg has been configured correctly. The application is ready.")
        except Exception as e:
            self.log(f"\nERROR: Could not download or install FFmpeg: {e}\n")
            messagebox.showerror("FFmpeg Error", f"Could not complete FFmpeg setup: {e}")
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            self.start_button.config(state=tk.NORMAL)

    def download_progress_hook(self, count, block_size, total_size):
        percent = int(count * block_size * 100 / total_size)
        self.log(f"\rDownloading FFmpeg... {percent}%")

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
        url = self.url_entry.get()
        if url:
            self.queue.append(url)
            self.queue_listbox.insert(tk.END, url)
            self.url_entry.delete(0, tk.END)
        else:
            messagebox.showwarning("Missing URL", "Please enter a URL.")

    def remove_selected(self):
        selected_indices = self.queue_listbox.curselection()
        if not selected_indices:
            return
        for i in sorted(selected_indices, reverse=True):
            self.queue_listbox.delete(i)
            self.queue.pop(i)

    def clear_queue(self):
        self.queue_listbox.delete(0, tk.END)
        self.queue.clear()

    def browse_path(self):
        path = filedialog.askdirectory()
        if path:
            self.path_var.set(path)

    def start_download_thread(self):
        if self.is_downloading:
            messagebox.showwarning("Download in Progress", "A download is already active.")
            return
        if not self.queue:
            messagebox.showwarning("Empty Queue", "Please add at least one URL to the queue.")
            return
        
        self.stop_event.clear()
        self.is_downloading = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        download_thread = threading.Thread(target=self.run_download_queue, daemon=True)
        download_thread.start()

    def stop_download(self):
        if self.is_downloading:
            self.log("\n---" + "Stop request received... The queue will stop after the current item" + "---" + "\n")
            self.stop_event.set()

    def run_download_queue(self):
        while self.queue:
            if self.stop_event.is_set():
                self.log("Download stopped by user.\n")
                break

            url = self.queue[0]
            self.log(f"---" + "Starting download of: " + url + "---" + "\n")
            self.queue_listbox.selection_clear(0, tk.END)
            self.queue_listbox.selection_set(0)
            self.queue_listbox.itemconfig(0, {'bg':'lightblue'})

            try:
                opts = self.build_ydl_opts()
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                self.log(f"---" + "Download finished: " + url + "---" + "\n\n")
            except Exception as e:
                self.log(f"---" + "ERROR downloading " + url + ": {e}" + "---" + "\n\n")
            finally:
                if self.queue:
                    self.queue.pop(0)
                    self.queue_listbox.delete(0)
        
        self.download_finished()

    def download_finished(self):
        self.log("---" + "Download queue finished." + "---" + "\n")
        self.is_downloading = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        if self.queue_listbox.size() > 0:
            self.queue_listbox.itemconfig(0, {'bg':''})
        if not self.stop_event.is_set():
             messagebox.showinfo("Finished!", "All downloads in the queue have been completed.")

    def build_ydl_opts(self):
        opts = {
            'logger': MyLogger(self.log),
            'progress_hooks': [self.progress_hook],
            'ignoreerrors': True,
            # Output template for playlists
            'outtmpl': {'default': '%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s', 
                        'pl_video': '%(playlist)s/%(playlist_index)s - %(title)s.%(ext)s'}
        }

        if os.path.exists(self.ffmpeg_path):
            opts['ffmpeg_location'] = self.ffmpeg_path

        format_choice = self.format_var.get()
        quality_choice = self.quality_var.get()
        
        if format_choice == "Audio Only (mp3)":
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]
            opts['format'] = 'ba/b'
        elif format_choice == "Audio Only (m4a)":
            opts['postprocessors'] = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'm4a'}]
            opts['format'] = 'ba/b'
        elif format_choice == "Video Only":
            quality_filter = f"bv[height<={quality_choice[:-1]}]" if quality_choice != "best" else "bv"
            opts['format'] = quality_filter
        else: # Video + Audio
            quality_filter = f"[height<={quality_choice[:-1]}]" if quality_choice != "best" else ""
            opts['format'] = f"bv*{quality_filter}+ba/b{quality_filter}"

        download_path = self.path_var.get()
        if download_path:
            opts['paths'] = {'home': download_path}

        if self.write_subs_var.get():
            opts['writesubtitles'] = True
            sub_langs = self.sub_langs_var.get()
            if sub_langs:
                opts['subtitleslangs'] = sub_langs.split(',')

        return opts

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total_bytes:
                percent = d['downloaded_bytes'] * 100 / total_bytes
                speed = d.get('speed') or 0
                eta = d.get('eta') or 0
                self.log(f"\r[download] {percent:.1f}% of {total_bytes/1024/1024:.2f}MB at {speed/1024:.2f}KiB/s ETA {eta:.0f}s")
        elif d['status'] == 'finished':
            self.log(f"\r[download] 100% - Finished.")

if __name__ == "__main__":
    if hasattr(sys, 'frozen'):
        import yt_dlp.extractor.youtube

    app = YtDlpGui()
    app.mainloop()