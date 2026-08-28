# +3 — il banco della tua asta

Due applicazioni che si parlano: **+3** è quella che usi all'asta, **Studio**
serve a decidere come deve apparire. Nessuna delle due ha bisogno di internet
per funzionare.

## Installarle sul telefono o sull'iPad

Carica tutti i file nella root del repo, poi Settings → Pages → Deploy from
branch `main`, cartella `/ (root)`.

Apri `https://imwade021.github.io/fanta-master-ai/astanote.html` in Safari e fai
**Condividi → Aggiungi a Home**. Da quel momento parte a tutto schermo, con la
sua icona, e non serve più la rete: al primo avvio si mette da parte tutto.
Ripeti con `studio.html` se vuoi anche lo Studio sulla Home.

Un file `.html` scaricato nell'app File **non** può diventare un'applicazione:
Apple ha disabilitato l'apertura di file locali in Safari. Il passaggio da
Pages è l'unico modo, e si fa una volta sola.

## L'aspetto

Da +3: Piano → **Personalizza l'aspetto**. Si apre lo Studio, che carica +3
dentro di sé: le manopole agiscono sull'applicazione vera, non su una copia.
Quaranta comandi divisi per pezzo — sfondo, pannelli, testi, numero, righe,
pulsanti, schede, materiale (vetro, grana, vignettatura).

**Tieni questo aspetto** lo salva. Torni su +3 con **Vai a +3** e c'è già.
Niente da copiare. I ritocchi restano separati fra tema chiaro e scuro.

## Prima dell'asta — scheda Piano

Budget, quante squadre, quante caselle per reparto, la strategia, se la lega usa
il modificatore di difesa, e chi paga quando sfori. Se giochi su un tavolo,
attiva **tieni acceso lo schermo**.

## Durante — scheda Asta

*Ho comprato* per i tuoi, *Venduto ad altri* per gli altri: di quelli serve solo
il prezzo. Il numero grande dice quanti crediti puoi mettere su questa casella
adesso, col conto per esteso — un tetto che non sai spiegare, a metà asta non lo
rispetti. Sotto, quante caselle di quel ruolo restano scoperte in tutta la lega.

Se sbagli, **Annulla** in alto torna indietro di dieci passi.

## Dopo

Piano → *La mia rosa*: negli appunti già formattata, o stampata.

## Se qualcosa va storto

**Salva una copia** scrive un file con tutta l'asta dentro; **Rimetti dentro** lo
rilegge. Fallo una volta a metà asta.

## Aggiornare il listone

Lancia `motore.py` accanto al `Lista_Finale_Master.csv` aggiornato e carica il
`dati_asta.json` che produce da Piano → *Listone aggiornato*.

## Cosa NON fa

Non prevede il rendimento di nessuno. Le fasce sono la fila d'attesa: con dodici
squadre i primi dodici di un ruolo sono fascia 1, uno a testa. L'affidabilità
sono presenze e minuti già giocati, col motivo scritto sotto. Chi non ha mai
giocato in Serie A non ha numeri: c'è scritto "nessuno storico", e basta.

## I file

| file | cosa fa |
|---|---|
| `astanote.html` | +3: l'applicazione, dati e icone incorporati |
| `studio.html` | lo Studio: modifica l'aspetto di +3 |
| `sw.js` | fa funzionare tutto senza rete |
| `piu3.webmanifest`, `studio.webmanifest` | nome e icone sulla schermata Home |
| `icona-*.png` | le icone |
| `motore.py` | rigenera `dati_asta.json` dal Master |
