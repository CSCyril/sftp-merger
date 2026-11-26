from __future__ import annotations

import csv
import queue
import tempfile
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from tkcalendar import DateEntry

from ..config import SftpConfig
from ..models import MergeReport, RemoteFile
from ..services.csv_merger import merge_csv
from ..services.mapping import load_mapping
from ..services.sftp_client import SftpClient, SftpError
from ..workers import run_in_thread


class MainWindow(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("SFTP Merger")
        self.geometry("1200x700")
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.client = SftpClient()
        self.config = SftpConfig.load()
        self.files: list[RemoteFile] = []
        self._sort_key = "date"
        self._sort_reverse = True
        self._busy = False
        self._cancel = False

        self._build_sidebar()
        self._build_main()
        self._load_config_into_form()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=280, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        ctk.CTkLabel(
            sidebar, text="Connexion SFTP", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=(20, 10), padx=20, anchor="w")

        self.host = self._add_entry(sidebar, "Serveur")
        self.port = self._add_entry(sidebar, "Port", "22")
        self.user = self._add_entry(sidebar, "Utilisateur")
        self.password = self._add_entry(sidebar, "Mot de passe", show="*")
        self.password.bind("<Return>", lambda _e: self.on_connect())
        self.directory = self._add_entry(sidebar, "Répertoire", "/")

        self.connect_btn = ctk.CTkButton(sidebar, text="Se connecter", command=self.on_connect)
        self.connect_btn.pack(pady=(15, 5), padx=20, fill="x")

        self.disconnect_btn = ctk.CTkButton(
            sidebar,
            text="Se déconnecter",
            command=self.on_disconnect,
            fg_color="transparent",
            border_width=1,
            state="disabled",
        )
        self.disconnect_btn.pack(pady=5, padx=20, fill="x")

    def _add_entry(self, parent, label: str, placeholder: str = "", show: str | None = None):
        ctk.CTkLabel(parent, text=label).pack(padx=20, anchor="w", pady=(10, 0))
        entry = ctk.CTkEntry(parent, placeholder_text=placeholder, show=show or "")
        entry.pack(padx=20, fill="x")
        return entry

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self)
        main.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        filter_bar = ctk.CTkFrame(main)
        filter_bar.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(filter_bar, text="Du").grid(row=0, column=0, padx=(10, 5), pady=10)
        self.start_date = DateEntry(filter_bar, date_pattern="yyyy-mm-dd", width=12)
        self.start_date.grid(row=0, column=1, padx=5)
        ctk.CTkLabel(filter_bar, text="Au").grid(row=0, column=2, padx=(10, 5))
        self.end_date = DateEntry(filter_bar, date_pattern="yyyy-mm-dd", width=12)
        self.end_date.grid(row=0, column=3, padx=5)

        self.search = ctk.CTkEntry(filter_bar, placeholder_text="Rechercher un fichier…", width=200)
        self.search.grid(row=0, column=4, padx=10)
        self.search.bind("<KeyRelease>", lambda _e: self.on_filter())

        ctk.CTkButton(filter_bar, text="Filtrer", width=90, command=self.on_filter).grid(
            row=0, column=5, padx=5
        )
        ctk.CTkButton(filter_bar, text="Réinitialiser", width=110, command=self.on_reset_filter).grid(
            row=0, column=6, padx=5
        )
        self.merge_switch = ctk.CTkSwitch(filter_bar, text="Fusionner les fichiers")
        self.merge_switch.grid(row=0, column=7, padx=10)

        select_bar = ctk.CTkFrame(main)
        select_bar.pack(fill="x", pady=(0, 5))
        ctk.CTkButton(select_bar, text="Tout sélectionner", width=150, command=self.on_select_all).pack(
            side="left", padx=5, pady=5
        )
        ctk.CTkButton(
            select_bar, text="Tout désélectionner", width=160, command=self.on_select_none
        ).pack(side="left", padx=5, pady=5)
        self.count_label = ctk.CTkLabel(select_bar, text="0 fichier(s) affiché(s)")
        self.count_label.pack(side="right", padx=10)

        columns = ("nom", "date", "taille")
        tree_frame = ctk.CTkFrame(main)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("nom", text="Nom", command=lambda: self._sort("nom"))
        self.tree.heading("date", text="Date", command=lambda: self._sort("date"))
        self.tree.heading("taille", text="Taille", command=lambda: self._sort("taille"))
        self.tree.column("nom", width=650)
        self.tree.column("date", width=180)
        self.tree.column("taille", width=120, anchor="e")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        bottom = ctk.CTkFrame(main)
        bottom.pack(fill="x", pady=(10, 0))
        self.progress = ctk.CTkProgressBar(bottom, width=300)
        self.progress.set(0)
        self.progress.pack(side="left", padx=5, pady=10)
        self.status = ctk.CTkLabel(bottom, text="Non connecté", anchor="w")
        self.status.pack(side="left", fill="x", expand=True, padx=10)
        self.cancel_btn = ctk.CTkButton(
            bottom, text="Annuler", width=90, command=self.on_cancel, state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=5)
        self.download_btn = ctk.CTkButton(
            bottom, text="Télécharger / Fusionner", command=self.on_download
        )
        self.download_btn.pack(side="right", padx=5)

    def _load_config_into_form(self) -> None:
        cfg = self.config
        self.host.insert(0, cfg.host)
        self.port.delete(0, "end")
        self.port.insert(0, str(cfg.port))
        self.user.insert(0, cfg.user)
        self.password.insert(0, cfg.password)
        self.directory.delete(0, "end")
        self.directory.insert(0, cfg.directory)

    def _current_config(self) -> SftpConfig:
        try:
            port = int(self.port.get().strip())
        except ValueError:
            port = -1
        return SftpConfig(
            host=self.host.get().strip(),
            port=port,
            user=self.user.get().strip(),
            password=self.password.get(),
            directory=self.directory.get().strip() or "/",
        )

    def _render(self, files: list[RemoteFile]) -> None:
        self.tree.delete(*self.tree.get_children())
        for f in files:
            self.tree.insert(
                "",
                "end",
                iid=f.name,
                values=(f.name, f.modified.strftime("%Y-%m-%d %H:%M:%S"), f.size_human),
            )
        self.count_label.configure(text=f"{len(files)} fichier(s) affiché(s)")

    def _sort(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key, self._sort_reverse = key, False
        attr = {"nom": "name", "date": "modified", "taille": "size"}[key]
        current = [self.tree.item(i)["values"][0] for i in self.tree.get_children()]
        by_name = {f.name: f for f in self.files}
        ordered = sorted((by_name[n] for n in current), key=lambda f: getattr(f, attr),
                         reverse=self._sort_reverse)
        self._render(ordered)

    def on_filter(self) -> None:
        start = self.start_date.get_date()
        end = self.end_date.get_date()
        text = self.search.get().strip().lower()
        result = [
            f
            for f in self.files
            if start <= f.modified.date() <= end and text in f.name.lower()
        ]
        self._render(result)

    def on_reset_filter(self) -> None:
        self.search.delete(0, "end")
        self.start_date.set_date(date(2000, 1, 1))
        self.end_date.set_date(date.today())
        self.on_filter()

    def on_select_all(self) -> None:
        self.tree.selection_set(self.tree.get_children())

    def on_select_none(self) -> None:
        self.tree.selection_set(())

    def on_connect(self) -> None:
        cfg = self._current_config()
        errors = cfg.validate()
        if errors:
            messagebox.showwarning("Champs invalides", "\n".join(errors))
            return
        self._set_busy(True, "Connexion en cours…")

        def target(q):
            def confirm_unknown_host(host, port, fingerprint):
                answer: queue.Queue = queue.Queue()
                q.put(("confirm", ((host, port, fingerprint), answer)))
                return answer.get()

            self.client.connect(
                cfg.host,
                cfg.port,
                cfg.user,
                cfg.password,
                confirm_unknown_host=confirm_unknown_host,
            )
            q.put(("progress", "Liste des fichiers…"))
            return self.client.list_files(cfg.directory)

        run_in_thread(
            self,
            target,
            on_done=lambda files: self._on_connected(cfg, files),
            on_progress=self._set_status,
            on_error=self._on_error,
            on_confirm=self._confirm_host,
        )

    def _confirm_host(self, data) -> bool:
        host, port, fingerprint = data
        return messagebox.askyesno(
            "Hôte inconnu",
            f"Première connexion à {host}:{port}.\n\n"
            f"Empreinte de la clé du serveur (SHA256) :\n{fingerprint}\n\n"
            "Faire confiance à cet hôte et l'enregistrer dans ~/.ssh/known_hosts ?",
            icon="warning",
        )

    def _on_connected(self, cfg: SftpConfig, files: list[RemoteFile]) -> None:
        cfg.save()
        self.config = cfg
        self.files = files
        self.disconnect_btn.configure(state="normal")
        self._set_busy(False)
        self.progress.set(0)
        self.status.configure(text=f"Connecté — {len(files)} fichier(s)")
        self.on_reset_filter()

    def on_disconnect(self) -> None:
        self.client.close()
        self.files = []
        self._render([])
        self.disconnect_btn.configure(state="disabled")
        self.status.configure(text="Non connecté")

    def on_download(self) -> None:
        if not self.client.is_connected:
            messagebox.showwarning("Information", "Connectez-vous d'abord au serveur SFTP.")
            return
        if not self.merge_switch.get():
            messagebox.showwarning("Information", "Activez l'option 'Fusionner les fichiers'.")
            return
        selected = [self.tree.item(i)["values"][0] for i in self.tree.selection()]
        names = selected or [self.tree.item(i)["values"][0] for i in self.tree.get_children()]
        if not names:
            messagebox.showwarning("Information", "Aucun fichier à traiter.")
            return
        output = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV", "*.csv")]
        )
        if not output:
            return

        self._cancel = False
        self._set_busy(True, "Téléchargement…")
        directory = self.directory.get().strip() or "/"

        def target(q):
            mapping = load_mapping("mapping.csv")
            with tempfile.TemporaryDirectory(prefix="sftp-merger-") as tmp:
                tmp_dir = Path(tmp)
                local: list[Path] = []
                for idx, name in enumerate(names, start=1):
                    if self._cancel:
                        raise InterruptedError("Opération annulée par l'utilisateur.")
                    q.put(("progress", (idx - 1, len(names), name)))
                    local.append(self.client.download(directory, name, tmp_dir))
                q.put(("progress", (len(names), len(names), "Fusion en cours…")))
                report = merge_csv(local, Path(output), mapping)
            return report, output

        run_in_thread(
            self,
            target,
            on_done=self._on_merged,
            on_progress=self._on_progress,
            on_error=self._on_error,
        )

    def _on_progress(self, payload) -> None:
        current, total, label = payload
        self.progress.set(current / total if total else 0)
        self.status.configure(text=f"{label} ({current}/{total})")

    def _on_merged(self, result) -> None:
        report: MergeReport
        report, output = result
        self.progress.set(1)
        self._set_busy(False)
        message = f"{report.files_merged} fichier(s) fusionné(s), {report.rows_written} ligne(s) → {output}"
        if report.unmatched_refs:
            unmatched_path = Path(output).with_name("produits_non_matches.csv")
            with open(unmatched_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["reference"])
                for ref in report.unmatched_refs:
                    writer.writerow([ref])
            message += (
                f"\n\n{len(report.unmatched_refs)} référence(s) sans correspondance "
                f"exportées dans :\n{unmatched_path}"
            )
        self.status.configure(text="Fusion terminée")
        messagebox.showinfo("Fusion terminée", message)

    def on_cancel(self) -> None:
        self._cancel = True
        self.status.configure(text="Annulation demandée…")

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.connect_btn.configure(state=state)
        self.download_btn.configure(state=state)
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        if status:
            self.status.configure(text=status)

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    def _on_error(self, exc: BaseException) -> None:
        self._set_busy(False)
        self.progress.set(0)
        if isinstance(exc, InterruptedError):
            self.status.configure(text="Opération annulée")
            return
        if isinstance(exc, SftpError):
            self.status.configure(text="Erreur de connexion")
        else:
            self.status.configure(text=f"Erreur : {exc}")
        messagebox.showerror("Erreur", str(exc))

    def on_close(self) -> None:
        self._cancel = True
        self.client.close()
        self.destroy()
