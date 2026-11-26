# SFTP Merger

Application desktop moderne (customtkinter) pour lister, filtrer, télécharger et
fusionner des exports CSV depuis un serveur SFTP.

## Installation

```bash
pip install -e ".[dev]"
```

## Lancement

```bash
python -m sftp_merger
# ou, après installation :
sftp-merger
```

## Configuration

- `config.ini` (créé automatiquement à la première connexion réussie) :
  serveur, port, utilisateur, mot de passe, répertoire distant.
  Le mot de passe est stocké en clair dans ce fichier (choix assumé pour la
  simplicité) ; le fichier est créé avec les permissions `600`.
- `mapping.csv` : correspondance `reference;titre` (séparateur `;`, encodage
  cp1252, sans ligne d'en-tête). Voir `mapping.example.csv`.

## Clé d'hôte du serveur (TOFU)

À la **première connexion** à un serveur, l'application affiche l'empreinte
SHA256 de sa clé et demande confirmation. Si vous acceptez, la clé est
enregistrée dans `~/.ssh/known_hosts` : les connexions suivantes sont
automatiques et toute clé modifiée sera refusée (protection MITM, sans
`AutoAddPolicy` aveugle).

## Tests

```bash
pytest
```

## Structure

```
src/sftp_merger/
├── app.py                  # point d'entrée
├── config.py               # SftpConfig : chargement/sauvegarde de config.ini
├── models.py               # RemoteFile, MergeReport (dataclasses)
├── columns.py              # indices des colonnes CSV, résolus depuis l'en-tête
├── workers.py              # exécution en thread + file de messages vers l'UI
├── services/
│   ├── sftp_client.py      # connexion SFTP (paramiko, host keys vérifiées)
│   ├── mapping.py          # chargement de mapping.csv
│   └── csv_merger.py       # logique de fusion pure, testable sans UI
└── ui/
    └── main_window.py      # fenêtre customtkinter
tests/                      # tests pytest de la logique métier
```

La logique métier (`services/`) n'importe jamais tkinter : elle est testable
unitairement. L'UI ne fait qu'orchestrer les services via `workers.run_in_thread`
pour ne jamais bloquer la fenêtre pendant le réseau.
