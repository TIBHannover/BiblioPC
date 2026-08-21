#!/usr/bin/env python3
import tkinter as tk
from tkinter import font
import requests
import subprocess
import os
import json
import sys
import urllib3

# Konfiguration
CONFIG_PATH = "/usr/local/etc/una-config.json"
BN_FILE = "/dev/shm/benutzernummer"
COLOR_BG = "#121212"        # Tiefes Anthrazit
COLOR_ACCENT = "#3498db"    # Modernes Blau
COLOR_TEXT = "#E0E0E0"      # Off-White
COLOR_LOGOUT = "#e74c3c"    # Sanftes Rot

def get_api_url():
    if not os.path.exists(CONFIG_PATH): return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            return f"{config['server_url'].rstrip('/')}/{config['status_script'].lstrip('/')}"
    except: return None

API_URL = get_api_url()

class ModernTimer:
    def __init__(self):
        self.root = tk.Tk()
                
        # --- Stealth Mode & Dock-Schutz ---
        self.root.withdraw() # Fenster kurz verstecken für Berechnungen
        self.root.attributes('-type', 'utility')
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True) # Rahmenlos für den Clean-Look
        # Verhindert das Schließen des Fensters durch Alt+F4
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)
        
        self.bn = "000000"
        if os.path.exists(BN_FILE):
            try:
                with open(BN_FILE, "r") as f: self.bn = f.read().strip()
            except: pass

        # Styles
        self.root.configure(bg=COLOR_BG)
        self.f_small = font.Font(family="Ubuntu", size=9)
        self.f_big = font.Font(family="Ubuntu", size=14, weight="bold")
        self.f_btn = font.Font(family="Ubuntu", size=10, weight="bold")

        # Container mit dünnem Border-Effekt
        self.outer_frame = tk.Frame(self.root, bg=COLOR_ACCENT, padx=1, pady=1)
        self.outer_frame.pack()
        
        self.inner_frame = tk.Frame(self.outer_frame, bg=COLOR_BG, padx=20, pady=15)
        self.inner_frame.pack()

        # UI Elemente
        tk.Label(self.inner_frame, text=f"{self.bn}", bg=COLOR_BG, 
                 fg=COLOR_ACCENT, font=self.f_small).pack(anchor="w")
        
        self.lbl_time = tk.Label(self.inner_frame, text="--:--", bg=COLOR_BG, 
                                 fg=COLOR_TEXT, font=self.f_big)
        self.lbl_time.pack(pady=(5, 10), anchor="w")

        # Stylischer Button
        self.btn_logout = tk.Button(
            self.inner_frame, text="⏻  LOGOUT", bg=COLOR_LOGOUT, fg="white",
            activebackground="#c0392b", activeforeground="white",
            relief="flat", font=self.f_btn, bd=0, cursor="hand2",
            padx=20, pady=5, command=self.force_logout
        )
        self.btn_logout.pack(fill="x")

        # Drag-Support
        for w in [self.inner_frame, self.lbl_time]:
            w.bind("<Button-1>", self.start_move)
            w.bind("<B1-Motion>", self.do_move)

        self.root.after(100, self.position_top_right)
        self.update_time()
        self.root.deiconify() # Fenster jetzt erst anzeigen
        self.root.mainloop()

    def position_top_right(self):
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        # 30px Abstand vom Rand
        x = self.root.winfo_screenwidth() - w - 30
        y = 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def update_time(self):
        if not API_URL:
            self.lbl_time.config(text="CONFIG ERROR", fg=COLOR_LOGOUT)
            return
        try:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            hostname = "unknown"
            client_ip = "127.0.0.1"

            if os.path.exists("/dev/shm/hostname"):
                with open("/dev/shm/hostname", "r") as f: hostname = f.read().strip()
            if os.path.exists("/dev/shm/ip"):
                with open("/dev/shm/ip", "r") as f: client_ip = f.read().strip()

            payload = {'bn': self.bn, 'host': hostname, 'ip': client_ip}
              
            r = requests.post(API_URL, data=payload, timeout=3, verify=False)
            res = r.text.strip()
            if res in ["ende", "sper", "0:00", "00:00"]: self.force_logout()
            else: self.lbl_time.config(text=f"{res} (hh:mm)")

        except:
            self.lbl_time.config(text="OFFLINE", fg=COLOR_LOGOUT)
        self.root.after(60000, self.update_time)

    def force_logout(self):
        # Beendet die grafische Sitzung des aktuellen Nutzers direkt über systemd
        os.system("systemctl --user exit")

    def start_move(self, e):
        self.offset_x, self.offset_y = e.x, e.y

    def do_move(self, e):
        x = self.root.winfo_x() + (e.x - self.offset_x)
        y = self.root.winfo_y() + (e.y - self.offset_y)
        self.root.geometry(f"+{x}+{y}")

if __name__ == "__main__":
    ModernTimer()
