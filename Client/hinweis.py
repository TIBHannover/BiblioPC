#!/usr/bin/env python3
import tkinter as tk
from tkinter import font
import socket

# --- DESIGN FARBEN ---
COLOR_BG = "#121212"
COLOR_ACCENT = "#3498db"
COLOR_TEXT = "#E0E0E0"
COLOR_LOGOUT = "#e74c3c" # Das Orange/Rot deines Buttons

class UnaHinweis:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Wichtiger Hinweis")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.configure(bg=COLOR_BG)

        self.f_title = font.Font(family="Ubuntu", size=12, weight="bold")
        self.f_body = font.Font(family="Ubuntu", size=10)
        self.f_btn = font.Font(family="Ubuntu", size=10, weight="bold")

        outer = tk.Frame(self.root, bg=COLOR_ACCENT, padx=1, pady=1)
        outer.pack()
        
        inner = tk.Frame(outer, bg=COLOR_BG, padx=25, pady=25)
        inner.pack()

        # Titel
        tk.Label(inner, text="Willkommen! / Welcome!", 
                 bg=COLOR_BG, fg=COLOR_ACCENT, font=self.f_title).pack(anchor="w")

        # Das Text-Widget als Container für gemischte Farben
        text_area = tk.Text(inner, bg=COLOR_BG, fg=COLOR_TEXT, font=self.f_body,
                            relief="flat", highlightthickness=0, height=8, width=55, spacing2=10)
        text_area.pack(anchor="w", pady=15)

        # Hier definieren wir den "Button-Look" für den Text
        # background: Die orange/rote Farbe vom OK-Button
        # foreground: Weiß (bleibt weiß)
        text_area.tag_configure("logout_style", 
                                background=COLOR_LOGOUT, 
                                foreground="white", 
                                font=self.f_btn)

        # Text zusammensetzen
        line1 = "Am Ende der Recherche/Arbeit abmelden mit "
        line2 = "\nBeim Abmelden werden alle lokalen Dateien gelöscht.\nSichern Sie Ihre Daten rechtzeitig!\n\n"
        line3 = "Log out at the end of your research/work session with "
        line4 = "\nNote that all local files will be deleted when you log out.\nMake sure to back up your data in time!"

        # Einfügen mit dem Tag für die [ LOGOUT ] Stellen
        text_area.insert("end", line1)
        text_area.insert("end", " ⏻ LOGOUT ", "logout_style") 
        text_area.insert("end", line2)
        text_area.insert("end", line3)
        text_area.insert("end", " ⏻ LOGOUT ", "logout_style")
        text_area.insert("end", line4)

        # Interaktion verhindern
        text_area.config(state="disabled")

        # OK Button
        btn = tk.Button(inner, text="OK", bg=COLOR_LOGOUT, fg="white",
                        relief="flat", font=self.f_btn, bd=0,
                        padx=30, pady=8, command=self.root.destroy)
        btn.pack(anchor="w")

        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f"+{x}+{y}")
        
        self.root.mainloop()

if __name__ == "__main__":
    UnaHinweis()