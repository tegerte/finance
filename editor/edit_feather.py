"""Einfacher GUI-Editor fuer rendite.feather.

Zeigt alle Zeilen, erlaubt Bearbeiten/Loeschen und Speichern.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
FEATHER_PATH = REPO_ROOT / "rendite.feather"
COLUMNS = ("date", "saldo", "rendite")


class FeatherEditor(tk.Tk):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.title(f"Feather-Editor — {path.name}")
        self.geometry("700x500")

        self.df = pd.read_feather(path)
        for col in COLUMNS:
            if col not in self.df.columns:
                raise ValueError(f"Spalte {col} fehlt in {path}")

        self._build_ui()
        self._reload_tree()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=8, pady=6)
        ttk.Button(toolbar, text="Bearbeiten", command=self.edit_selected).pack(side="left")
        ttk.Button(toolbar, text="Loeschen", command=self.delete_selected).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Neu laden", command=self.reload_from_disk).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Speichern", command=self.save).pack(side="right")

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", selectmode="browse")
        for col, width in zip(COLUMNS, (140, 140, 140)):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", lambda _e: self.edit_selected())

        self.status = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(fill="x", padx=8, pady=(0, 6))

    def _reload_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for idx, row in self.df.iterrows():
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(row["date"], f"{row['saldo']:.2f}", f"{row['rendite']:.6f}"),
            )
        last = self.tree.get_children()
        if last:
            self.tree.selection_set(last[-1])
            self.tree.see(last[-1])
        self.status.set(f"{len(self.df)} Zeilen — {self.path}")

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst eine Zeile auswaehlen.")
            return None
        return int(sel[0])

    def edit_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        row = self.df.loc[idx]
        EditDialog(self, idx, row, self._apply_edit)

    def _apply_edit(self, idx: int, date: str, saldo: float, rendite: float) -> None:
        self.df.at[idx, "date"] = date
        self.df.at[idx, "saldo"] = saldo
        self.df.at[idx, "rendite"] = rendite
        self._reload_tree()
        self.tree.selection_set(str(idx))
        self.tree.see(str(idx))

    def delete_selected(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        row = self.df.loc[idx]
        if not messagebox.askyesno(
            "Loeschen",
            f"Zeile loeschen?\n\n{row['date']} | saldo={row['saldo']:.2f} | rendite={row['rendite']:.6f}",
        ):
            return
        self.df = self.df.drop(idx).reset_index(drop=True)
        self._reload_tree()

    def reload_from_disk(self) -> None:
        if not messagebox.askyesno("Neu laden", "Nicht gespeicherte Aenderungen verwerfen?"):
            return
        self.df = pd.read_feather(self.path)
        self._reload_tree()

    def save(self) -> None:
        backup = self.path.with_suffix(self.path.suffix + ".bak")
        try:
            if self.path.exists():
                backup.write_bytes(self.path.read_bytes())
            self.df.reset_index(drop=True).to_feather(self.path)
        except Exception as exc:
            messagebox.showerror("Fehler", f"Speichern fehlgeschlagen:\n{exc}")
            return
        messagebox.showinfo("Gespeichert", f"{self.path.name} gespeichert.\nBackup: {backup.name}")


class EditDialog(tk.Toplevel):
    def __init__(self, master: FeatherEditor, idx: int, row: pd.Series, on_ok) -> None:
        super().__init__(master)
        self.title(f"Zeile {idx} bearbeiten")
        self.idx = idx
        self.on_ok = on_ok
        self.transient(master)
        self.grab_set()

        self.vars = {
            "date": tk.StringVar(value=str(row["date"])),
            "saldo": tk.StringVar(value=f"{row['saldo']:.2f}"),
            "rendite": tk.StringVar(value=f"{row['rendite']:.6f}"),
        }

        for r, label in enumerate(("date", "saldo", "rendite")):
            ttk.Label(self, text=label).grid(row=r, column=0, sticky="e", padx=8, pady=4)
            ttk.Entry(self, textvariable=self.vars[label], width=28).grid(
                row=r, column=1, sticky="we", padx=8, pady=4
            )
        ttk.Label(self, text="Format date: YYYY-MM-DD", foreground="#666").grid(
            row=3, column=0, columnspan=2, padx=8, pady=(0, 4)
        )

        btns = ttk.Frame(self)
        btns.grid(row=4, column=0, columnspan=2, pady=8)
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="left", padx=4)
        self.bind("<Return>", lambda _e: self._ok())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _ok(self) -> None:
        date = self.vars["date"].get().strip()
        try:
            pd.Timestamp(date)
        except Exception:
            messagebox.showerror("Fehler", "Ungueltiges Datum (YYYY-MM-DD).", parent=self)
            return
        try:
            saldo = float(self.vars["saldo"].get().replace(",", "."))
            rendite = float(self.vars["rendite"].get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Fehler", "saldo/rendite muessen Zahlen sein.", parent=self)
            return
        self.on_ok(self.idx, date, saldo, rendite)
        self.destroy()


def main() -> None:
    if not FEATHER_PATH.exists():
        raise SystemExit(f"Datei nicht gefunden: {FEATHER_PATH}")
    FeatherEditor(FEATHER_PATH).mainloop()


if __name__ == "__main__":
    main()
