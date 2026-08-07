TODO:
1. Verbrauchsartikel einblenden/ausblenden sollte ein User-flag sein. DONE
2. user flag: bevorzuge ausleihen/ruecknehmen. DONE
3. cursor per default im bevorzugten feld. DONE
4. responsive design (der button der daneben liegt) DONE
5. Gruppennummer kann weg, Name+interner Name muss her. DONE
6. rental actions sollten den aktuellen Stand speichern, damit total nicht immer neu berechnet werden muss. DONE: Anders gelöst.
7. Auf nen Server bringen. DONE


8. Noch das deployment glattziehen mit nem eigenen Frontend Container, damit Caddy niemals neustarten muss.
8.1. Prüfen, wieso Caddy manchmal abgestürzt ist (vielleicht beim Zugriff wenn das Backend tot war?)

9. Sehen, wie viele Kisten an die aktuelle Gruppe vom eigenen Account innerhalb
   der letzten 30 Minuten ausgegeben wurden (siehe branch
   `start_on_recent_rental_actions`.)

10. DESIGN Entscheidung: Ein Barcode-Feld für alles? In dem Fall Steuerungsbarcodes, die man am PS-Tresen aufklebt machen zum Modus-Wählen?
11. Prüfen, dass Kochgruppen-IDs eindeutig sind.
12. RentalAction löschen muss auch den Barcode von der Gruppe wieder wegnehmen
    und auf den vorherigen Ort setzen, falls diese RentalAction die letzte war.
    Ansonsten ist das schwierig. Man könnte die Historie nachspielen und
    schauen, ob sie noch konsistent ist. Muss man nochmal drüber nachdenken.
13. Eine User-Doku schreiben.
