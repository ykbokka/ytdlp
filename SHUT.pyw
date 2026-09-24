import os
import re
import json
import time
import sys
import urllib.parse
import urllib.request
import subprocess
import threading
import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

# --- Windows Taskbar AppUserModelID Initialization ---
if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ytmusic.universal.downloader.v1")
    except Exception:
        pass

def get_resource_dir():
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.abspath(".")

RESOURCE_DIR = get_resource_dir()
os.environ["PATH"] = RESOURCE_DIR + os.pathsep + os.environ.get("PATH", "")

try:
    import pyi_splash
except ImportError:
    pyi_splash = None

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

APP_FONT = "Segoe UI"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".ytdl_cookie_config.json")

TASKBAR_AVAILABLE = False
if os.name == "nt":
    try:
        from ctypes import wintypes
        comtypes_available = True
    except Exception:
        comtypes_available = False
else:
    comtypes_available = False


class WindowsTaskbarProgress:
    def __init__(self, root):
        self.hwnd = None
        self.tbl_inst = None
        if comtypes_available:
            try:
                root.update_idletasks()
                hwnd_val = int(root.wm_frame(), 16) if hasattr(root, "wm_frame") else root.winfo_id()
                self.hwnd = wintypes.HWND(hwnd_val)

                ctypes.oledll.ole32.CoInitialize(None)
                import comtypes.client as cc
                cc.GetModule("TaskbarLib.tlb")
                import comtypes.gen.TaskbarLib as tbl
                self.tbl_inst = cc.CreateObject("{56FDF344-FD6D-11d0-958A-006097C9A090}", interface=tbl.ITaskbarList3)
                self.tbl_inst.HrInit()
                global TASKBAR_AVAILABLE
                TASKBAR_AVAILABLE = True
            except Exception:
                TASKBAR_AVAILABLE = False

    def set_progress(self, current, total):
        if not TASKBAR_AVAILABLE or not self.hwnd or not self.tbl_inst:
            return
        try:
            if current <= 0:
                self.tbl_inst.SetProgressState(self.hwnd.value, 0)
            else:
                self.tbl_inst.SetProgressState(self.hwnd.value, 2)
                self.tbl_inst.SetProgressValue(self.hwnd.value, int(current), int(total))
        except Exception:
            pass

    def set_state(self, state_flag):
        if not TASKBAR_AVAILABLE or not self.hwnd or not self.tbl_inst:
            return
        try:
            self.tbl_inst.SetProgressState(self.hwnd.value, state_flag)
        except Exception:
            pass


class YTDLGui(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("YouTube Music & Video Downloader")
        self.geometry("620x820")
        self.minsize(580, 760)
        self.configure(fg_color="#090d16")

        icon_path = os.path.join(RESOURCE_DIR, "app.ico")
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(default=icon_path)
            except Exception:
                pass

        self.grid_columnconfigure(0, weight=1)
        self.custom_path = os.path.join(os.path.expanduser("~"), "Downloads")
        self.cookie_file_path = ""
        
        self.load_config()

        self.is_animating = False
        self.current_process = None
        self.is_paused = False

        self.taskbar_progress = WindowsTaskbarProgress(self)

        self.build_ui()

        if pyi_splash and pyi_splash.is_alive():
            pyi_splash.close()

    def build_ui(self):
        # Header / Title Block
        header_frame = ctk.CTkFrame(self, fg_color="#111827", corner_radius=12)
        header_frame.grid(row=0, column=0, padx=20, pady=(16, 8), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="YouTube Music Engine",
            font=(APP_FONT, 18, "bold"),
            text_color="#f8fafc"
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(
            header_frame,
            text="Paste YT Music link, playlist, or search directly by song name",
            font=(APP_FONT, 12),
            text_color="#94a3b8"
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        # Target Input Block
        input_frame = ctk.CTkFrame(self, fg_color="#111827", corner_radius=12)
        input_frame.grid(row=1, column=0, padx=20, pady=8, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        self.url_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Paste Link or Search YT Music (e.g. 'Artist - Song')",
            height=46,
            font=(APP_FONT, 14),
            fg_color="#030712",
            text_color="#ffffff",
            placeholder_text_color="#6b7280",
            border_width=1,
            border_color="#1f2937",
            corner_radius=8
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=16, pady=16)

        # Download Options & Format Engine
        opts_frame = ctk.CTkFrame(self, fg_color="#111827", corner_radius=12)
        opts_frame.grid(row=2, column=0, padx=20, pady=8, sticky="ew")
        opts_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            opts_frame,
            text="Audio / Video Quality",
            font=(APP_FONT, 14, "bold"),
            text_color="#f8fafc"
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 4))

        self.format_dropdown = ctk.CTkComboBox(
            opts_frame,
            values=[
                "🎵 MP3 320kbps (HQ)",
                "🎼 FLAC Lossless Audio",
                "🎧 M4A / AAC Audio",
                "🎬 Best Video Quality",
                "🌟 4K UHD (2160p)",
                "📺 1080p Full HD",
                "📱 720p HD"
            ],
            state="readonly",
            fg_color="#030712",
            text_color="#ffffff",
            button_color="#1f2937",
            button_hover_color="#374151",
            dropdown_fg_color="#111827",
            dropdown_text_color="#ffffff",
            corner_radius=8,
            font=(APP_FONT, 13),
            dropdown_font=(APP_FONT, 13),
            height=40
        )
        self.format_dropdown.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.format_dropdown.set("🎵 MP3 320kbps (HQ)")

        # Subtitles & Cookie Settings
        config_subframe = ctk.CTkFrame(opts_frame, fg_color="transparent")
        config_subframe.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        config_subframe.grid_columnconfigure(0, weight=1)

        self.embed_subs_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            config_subframe,
            text="Embed Subtitles (EN/AR)",
            variable=self.embed_subs_var,
            font=(APP_FONT, 12),
            text_color="#d1d5db",
            border_width=1,
            corner_radius=4
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            config_subframe,
            text="🍪 Netscape Cookies",
            command=self.select_cookie_file,
            width=130,
            height=28,
            font=(APP_FONT, 11, "bold"),
            fg_color="#1f2937",
            hover_color="#374151",
            text_color="#f3f4f6",
            corner_radius=6
        ).grid(row=0, column=1, sticky="e")

        # Path Selection
        path_frame = ctk.CTkFrame(self, fg_color="#111827", corner_radius=12)
        path_frame.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
        path_frame.grid_columnconfigure(0, weight=1)

        self.path_label = ctk.CTkLabel(
            path_frame,
            text=f"Save Location: {self.custom_path}",
            font=(APP_FONT, 12),
            text_color="#9ca3af",
            anchor="w"
        )
        self.path_label.grid(row=0, column=0, sticky="ew", padx=(16, 8), pady=12)

        ctk.CTkButton(
            path_frame,
            text="Browse",
            command=self.select_directory,
            width=80,
            height=28,
            font=(APP_FONT, 12, "bold"),
            fg_color="#1f2937",
            hover_color="#374151",
            text_color="#ffffff",
            corner_radius=6
        ).grid(row=0, column=1, padx=(0, 16), pady=12)

        # Preview & Active State Frame
        self.preview_frame = ctk.CTkFrame(self, fg_color="#111827", corner_radius=12)
        self.preview_frame.grid(row=4, column=0, padx=20, pady=8, sticky="ew")
        self.preview_frame.grid_columnconfigure(1, weight=1)

        self.cover_label = ctk.CTkLabel(
            self.preview_frame,
            text="NO\nCOVER",
            width=80,
            height=80,
            fg_color="#030712",
            corner_radius=8,
            font=(APP_FONT, 10, "bold"),
            text_color="#4b5563"
        )
        self.cover_label.grid(row=0, column=0, rowspan=3, padx=12, pady=12)

        self.title_display_label = ctk.CTkLabel(
            self.preview_frame,
            text="Ready for Download",
            font=(APP_FONT, 14, "bold"),
            text_color="#f3f4f6",
            anchor="w"
        )
        self.title_display_label.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=(12, 2))

        self.progress_bar = ctk.CTkProgressBar(
            self.preview_frame,
            orientation="horizontal",
            height=10,
            corner_radius=5,
            fg_color="#030712",
            progress_color="#2563eb"
        )
        self.progress_bar.grid(row=1, column=1, sticky="ew", padx=(0, 12), pady=2)
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            self.preview_frame,
            text="Status: Idle",
            font=(APP_FONT, 12),
            text_color="#9ca3af",
            anchor="w"
        )
        self.status_label.grid(row=2, column=1, sticky="ew", padx=(0, 12), pady=(2, 12))

        # Controls & Action Buttons
        self.action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.action_frame.grid(row=5, column=0, padx=20, pady=(8, 20), sticky="ew")
        self.action_frame.grid_columnconfigure(0, weight=1)

        self.download_btn = ctk.CTkButton(
            self.action_frame,
            text="Execute Download",
            command=self.start_download_thread,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            text_color="#ffffff",
            font=(APP_FONT, 14, "bold"),
            height=44,
            corner_radius=8
        )
        self.download_btn.grid(row=0, column=0, sticky="ew")

        self.pause_btn = ctk.CTkButton(self.action_frame, text="Pause", command=self.toggle_pause_download, fg_color="#374151", hover_color="#4b5563", font=(APP_FONT, 13, "bold"), height=44, corner_radius=8, state="disabled")
        self.resume_btn = ctk.CTkButton(self.action_frame, text="Resume", command=self.toggle_pause_download, fg_color="#059669", hover_color="#10b981", font=(APP_FONT, 13, "bold"), height=44, corner_radius=8, state="disabled")
        self.stop_btn = ctk.CTkButton(self.action_frame, text="Stop", command=self.stop_download, fg_color="#dc2626", hover_color="#b91c1c", font=(APP_FONT, 13, "bold"), height=44, corner_radius=8, state="disabled")

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    saved_path = data.get("cookie_file", "")
                    if saved_path and os.path.exists(saved_path):
                        self.cookie_file_path = saved_path
        except Exception:
            pass

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"cookie_file": self.cookie_file_path}, f)
        except Exception:
            pass

    def select_cookie_file(self):
        file_path = filedialog.askopenfilename(title="Select Netscape Cookie File", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if file_path:
            self.cookie_file_path = file_path
            self.save_config()

    def select_directory(self):
        dir_path = filedialog.askdirectory(initialdir=self.custom_path)
        if dir_path:
            self.custom_path = dir_path
            short_path = dir_path if len(dir_path) <= 35 else "..." + dir_path[-32:]
            self.path_label.configure(text=f"Save Location: {short_path}")

    def update_cover_art_preview(self, image_url):
        try:
            res = requests.get(image_url, stream=True, timeout=5)
            if res.status_code == 200:
                img = Image.open(res.raw)
                img = img.resize((80, 80), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(80, 80))
                self.cover_label.configure(image=ctk_img, text="")
        except Exception:
            self.cover_label.configure(image="", text="NO\nCOVER")

    def start_download_thread(self):
        user_input = self.url_entry.get().strip()
        if not user_input:
            messagebox.showerror("Error", "Please enter a valid YT Music link or search query.")
            return

        self.download_btn.configure(state="disabled", text="Processing...")
        self.action_frame.grid_columnconfigure(0, weight=1)
        self.action_frame.grid_columnconfigure(1, weight=1)
        self.action_frame.grid_columnconfigure(2, weight=1)

        self.download_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.pause_btn.configure(state="normal", text="Pause")
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=2)
        self.resume_btn.grid_forget()
        self.stop_btn.configure(state="normal", text="Stop")
        self.stop_btn.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        self.progress_bar.set(0)
        self.taskbar_progress.set_progress(0, 100)
        self.title_display_label.configure(text="Resolving Query...")
        self.status_label.configure(text="Status: Fetching metadata stream...")

        self.is_paused = False
        threading.Thread(target=self.run_ytdlp, args=(user_input,), daemon=True).start()

    def toggle_pause_download(self):
        if not self.current_process:
            return
        try:
            import psutil
            parent = psutil.Process(self.current_process.pid)
            all_procs = [parent] + parent.children(recursive=True)

            if not self.is_paused:
                for p in all_procs:
                    try:
                        p.suspend()
                    except Exception:
                        pass
                self.is_paused = True
                self.pause_btn.grid_forget()
                self.resume_btn.configure(state="normal", text="Resume")
                self.resume_btn.grid(row=0, column=1, sticky="ew", padx=2)
                self.status_label.configure(text="Status: Paused")
                self.taskbar_progress.set_state(8)
            else:
                for p in all_procs:
                    try:
                        p.resume()
                    except Exception:
                        pass
                self.is_paused = False
                self.resume_btn.grid_forget()
                self.pause_btn.configure(state="normal", text="Pause")
                self.pause_btn.grid(row=0, column=1, sticky="ew", padx=2)
                self.status_label.configure(text="Status: Resuming...")
                self.taskbar_progress.set_state(2)
        except Exception:
            messagebox.showwarning("Notice", "Pause functionality requires 'psutil' package.")

    def stop_download(self):
        if self.current_process and self.current_process.poll() is None:
            try:
                import psutil
                parent = psutil.Process(self.current_process.pid)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
            except Exception:
                try:
                    self.current_process.terminate()
                except Exception:
                    pass
        self.is_paused = False
        self.status_label.configure(text="Status: Aborted by user")
        self.title_display_label.configure(text="Ready for Download")
        self.reset_ui_state()

    def get_hidden_subprocess_kwargs(self):
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW
        return {"startupinfo": startupinfo, "creationflags": creationflags}

    def run_ytdlp(self, user_input):
        output_template = os.path.join(self.custom_path, "%(artist)s - %(title)s.%(ext)s")
        selected_format = self.format_dropdown.get()
        win_kwargs = self.get_hidden_subprocess_kwargs()

        # Direct YouTube Music search query routing if no direct URL is passed
        if not (user_input.startswith("http://") or user_input.startswith("https://")):
            target_url = f"ytsearch1:{user_input}"
        else:
            target_url = user_input

        cookie_arg = ["--cookies", self.cookie_file_path] if self.cookie_file_path and os.path.exists(self.cookie_file_path) else []

        # Step 1: Query YouTube Music Metadata directly
        meta_cmd = ["yt-dlp", "--dump-json", "--no-playlist"] + cookie_arg + [target_url]
        track_title = ""
        highres_cover_url = None

        try:
            meta_proc = subprocess.Popen(meta_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", **win_kwargs)
            stdout, _ = meta_proc.communicate(timeout=20)
            if meta_proc.returncode == 0:
                json_data = json.loads(stdout.split('\n')[0])
                
                # Retrieve artist and title for clean formatting
                artist = json_data.get("artist") or json_data.get("uploader") or ""
                title = json_data.get("track") or json_data.get("title") or ""
                
                track_title = f"{artist} - {title}" if artist and title != artist else title
                
                # Fetch highest resolution thumbnail from YouTube Music
                thumbnails = json_data.get("thumbnails", [])
                if thumbnails:
                    sorted_thumbs = sorted(thumbnails, key=lambda x: x.get("width", 0) * x.get("height", 0), reverse=True)
                    highres_cover_url = sorted_thumbs[0].get("url")

                if track_title:
                    self.after(0, lambda t=track_title: self.title_display_label.configure(
                        text=t if len(t) <= 40 else t[:37] + "..."
                    ))

                if highres_cover_url:
                    self.after(0, lambda url=highres_cover_url: self.update_cover_art_preview(url))

        except Exception:
            pass

        # Step 2: Main Download Execution Command using native YTM Metadata
        cmd = [
            "yt-dlp",
            "--newline",
            "--windows-filenames",
            "--concurrent-fragments", "4",
            "--embed-thumbnail",
            "--embed-metadata",
            "--parse-metadata", "title:%(artist)s - %(title)s"
        ] + cookie_arg + ["-o", output_template]

        # Quality Mapping
        if "MP3" in selected_format or "FLAC" in selected_format or "M4A" in selected_format:
            if "FLAC" in selected_format:
                cmd.extend(["-x", "--audio-format", "flac"])
            elif "M4A" in selected_format:
                cmd.extend(["-f", "ba[ext=m4a]/ba", "-x"])
            else:
                cmd.extend(["-x", "--audio-format", "mp3", "--audio-quality", "0"])
        else:
            if "2160p" in selected_format or "4K" in selected_format:
                cmd.extend(["-f", "bestvideo[height<=2160]+bestaudio/best"])
            elif "1080p" in selected_format:
                cmd.extend(["-f", "bestvideo[height<=1080]+bestaudio/best"])
            elif "720p" in selected_format:
                cmd.extend(["-f", "bestvideo[height<=720]+bestaudio/best"])
            else:
                cmd.extend(["-f", "bv*+ba/b"])
            cmd.extend(["--merge-output-format", "mp4"])

        if self.embed_subs_var.get():
            cmd.extend(["--write-sub", "--write-auto-sub", "--embed-subs", "--sub-lang", "en,ar"])

        cmd.extend(["--", target_url])

        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **win_kwargs
            )

            while True:
                line = self.current_process.stdout.readline()
                if not line and self.current_process.poll() is not None:
                    break
                if line:
                    clean_line = line.strip()
                    match_pct = re.search(r"([\d\.]+)%", clean_line)
                    if match_pct:
                        p = float(match_pct.group(1)) / 100.0
                        self.after(0, lambda p=p: [
                            self.progress_bar.set(p),
                            self.taskbar_progress.set_progress(p * 100, 100)
                        ])
                        self.after(0, lambda cl=clean_line: self.status_label.configure(
                            text=f"Status: {cl[:45]}"
                        ))

            rc = self.current_process.poll()
            if rc == 0:
                self.after(0, lambda: [
                    self.progress_bar.set(1.0),
                    self.status_label.configure(text="Status: Download Complete!"),
                    messagebox.showinfo("Success", "YT Music track and metadata saved successfully!")
                ])
            else:
                self.after(0, lambda: messagebox.showerror("Error", "Download process failed."))

        except Exception as ex:
            self.after(0, lambda: messagebox.showerror("Critical Exception", str(ex)))
        finally:
            self.taskbar_progress.set_state(0)
            self.reset_ui_state()

    def reset_ui_state(self):
        self.is_paused = False
        self.current_process = None
        self.after(0, lambda: [
            self.pause_btn.grid_forget(),
            self.resume_btn.grid_forget(),
            self.stop_btn.grid_forget(),
            self.download_btn.grid(row=0, column=0, sticky="ew", padx=0),
            self.download_btn.configure(state="normal", text="Execute Download")
        ])


if __name__ == "__main__":
    app = YTDLGui()
    app.mainloop()