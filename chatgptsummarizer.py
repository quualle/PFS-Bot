import os
import tkinter as tk
from tkinter import filedialog, messagebox

# Pfad zum Projektverzeichnis anpassen
PROJECT_DIR = r"/Users/marcoheer/Desktop/privat/Programmierung/XORA/PFS-Bot"

class FileCombinerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Project File Combiner")
        self.geometry("800x600")
        self.file_vars = []

        self.create_widgets()
        self.load_files()

        # Tastenkombinationen
        self.bind_all("<Control-Key-1>", self.copy_selected_files_to_clipboard)
        self.bind_all("<Control-Key-2>", self.combine_selected_files)

    def create_widgets(self):
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Scrollable Area für die Checkboxen
        self.canvas = tk.Canvas(frame)
        self.scrollbar = tk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Buttons unten
        button_frame = tk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))

        copy_button = tk.Button(button_frame, text="Copy Selected Paths (Ctrl+1)", command=self.copy_selected_files_to_clipboard)
        copy_button.pack(side="left", padx=5)

        combine_button = tk.Button(button_frame, text="Combine Selected Files (Ctrl+2)", command=self.combine_selected_files)
        combine_button.pack(side="left", padx=5)

        select_all_button = tk.Button(button_frame, text="Select All", command=self.select_all)
        select_all_button.pack(side="left", padx=5)

        deselect_all_button = tk.Button(button_frame, text="Deselect All", command=self.deselect_all)
        deselect_all_button.pack(side="left", padx=5)


    def load_files(self):
        # Clear existing checkboxes
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.file_vars = []

        # Recursively find files
        try:
            # Ignorierte Ordner und Dateien (Beispiel)
            ignored_dirs = {".git", ".vscode", "__pycache__", "node_modules", "backups_20250319"}
            ignored_files = {".DS_Store"}

            for root, dirs, files in os.walk(PROJECT_DIR):
                # Filter ignored directories
                dirs[:] = [d for d in dirs if d not in ignored_dirs]

                for filename in sorted(files):
                    if filename in ignored_files:
                        continue

                    full_path = os.path.join(root, filename)
                    # Zeige den relativen Pfad im UI für bessere Lesbarkeit
                    relative_path = os.path.relpath(full_path, PROJECT_DIR)

                    var = tk.BooleanVar()
                    chk = tk.Checkbutton(self.scrollable_frame, text=relative_path, variable=var)
                    chk.pack(anchor="w")
                    # Store the full path for processing
                    self.file_vars.append((var, full_path, relative_path))

        except FileNotFoundError:
            messagebox.showerror("Error", f"Project directory not found: {PROJECT_DIR}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred while loading files: {e}")

    def select_all(self):
        for var, _, _ in self.file_vars:
            var.set(True)

    def deselect_all(self):
        for var, _, _ in self.file_vars:
            var.set(False)

    def copy_selected_files_to_clipboard(self, event=None):
        selected_files = [path for var, path, _ in self.file_vars if var.get()]
        if not selected_files:
            messagebox.showwarning("Keine Auswahl", "Es wurden keine Dateien ausgewählt.")
            return

        combined_content = []
        for file_path in selected_files:
            combined_content.append(f"----- {os.path.basename(file_path)} -----\n")
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as infile:
                    content = infile.read()
                combined_content.append(content + "\n\n")
            except Exception as e:
                combined_content.append(f"Fehler beim Lesen der Datei: {e}\n\n")

        total_text = "".join(combined_content)
        self.clipboard_clear()
        self.clipboard_append(total_text)
        messagebox.showinfo("Fertig", "Ausgewählte Dateien wurden in den Zwischenspeicher kopiert.")

    def combine_selected_files(self, event=None):
        selected_files = [path for var, path, _ in self.file_vars if var.get()]
        if not selected_files:
            messagebox.showwarning("Keine Auswahl", "Es wurden keine Dateien ausgewählt.")
            return

        summary_file = os.path.join(PROJECT_DIR, "combined_summary.txt")
        try:
            with open(summary_file, "w", encoding="utf-8") as outfile:
                for file_path in selected_files:
                    outfile.write(f"----- {os.path.basename(file_path)} -----\n")
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="replace") as infile:
                            content = infile.read()
                        outfile.write(content + "\n\n")
                    except Exception as e:
                        outfile.write(f"Fehler beim Lesen der Datei: {e}\n\n")

            messagebox.showinfo("Fertig", f"Die Dateien wurden erfolgreich in '{summary_file}' zusammengefasst.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Erstellen der Zusammenfassung: {e}")

if __name__ == "__main__":
    app = FileCombinerApp()
    app.mainloop()
