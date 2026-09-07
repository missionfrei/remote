# Missionfrei Auto-Board

Selbst-aktualisierendes Remote-Job-Board. Ein GitHub-Action-Roboter zieht
taeglich Job-Feeds, filtert auf das Profil (deutschsprachig / weltweit-remote,
einsteigerfreundlich, 7 Bereiche) und baut `index.html` neu. Abgelaufene
Stellen fallen automatisch raus. Design (Login, Chips, Favoriten-Sterne,
Freelance, Toolbox) ist identisch zum bestehenden Board.

## Dateien
- `build_auto.py` - Generator: Feeds abrufen -> filtern -> mit manueller Schicht mischen -> `index.html` bauen.
- `template.html` - das bestehende Board-Design (Shell). Nur die 7 Bereichs-Sektionen werden neu erzeugt.
- `manual-jobs.json` - MANUELLE Schicht. Von Hand kuratierte Stellen (Kunden-Picks). Wird eingemischt und NIE automatisch geloescht. `"fd": true` = "Für dich"-Stern.
- `.github/workflows/build.yml` - der Zeitplan-Roboter (taeglich + Knopf).
- `mock/` - Beispiel-Daten fuer lokale Tests ohne Netz.

## Lokal testen (ohne Netz)
    python build_auto.py --mock

## Live (macht die Action automatisch)
    python build_auto.py

## Manuelle Stelle hinzufuegen (Kunden-Nachschub)
Eintrag in `manual-jobs.json` ergaenzen:
    {"title":"...","company":"...","url":"https://...","info":"...",
     "lang":"de","region":"de|eu|world","level":"einsteiger|erfahren",
     "bereich":"service|buero|start|sprache|marketing|vertrieb|it","fd":true}
Beim naechsten Lauf ist sie drauf und bleibt.

## Quellen erweitern (M2)
In `build_auto.py` unter `SOURCES` weitere Feeds ergaenzen (jeweils eine
`from_<name>(raw)`-Funktion, die auf das gemeinsame Format normalisiert):
Jobicy, RemoteOK, WeWorkRemotely (RSS), Himalayas, Working Nomads u.a.

## Setup (einmalig)
1. Repo anlegen, diese Dateien reinlegen.
2. Settings -> Pages -> Branch `main` -> Speichern.
3. Settings -> Actions -> General -> Workflow permissions -> "Read and write".
4. Actions-Tab -> "Build Auto-Board" -> "Run workflow" (erster Lauf).
