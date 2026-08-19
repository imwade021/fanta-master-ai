# fanta-master-ai

Motore dati per l'asta del Fantacalcio. **Unica fonte di verita'**: produce
`Lista_Finale_Master.csv`, che FantaBot si limita a leggere e mostrare.

## Come funziona

Ogni notte alle 04:00 (UTC) la GitHub Action esegue `build_master.py`, che:

1. legge il file **quotazioni** piu' recente (`Quotazioni_Fantacalcio_Stagione_*.xlsx`)
   per sapere chi e' in Serie A, in che squadra e quanto vale;
2. incrocia per `Id` le **statistiche** della stagione conclusa (`Statistiche.xlsx`);
3. arricchisce con l'**anagrafica** (`Lista-FantaAsta-Fantacalcio.csv`): foto,
   piede, nazionalita', nome completo;
4. interroga **API-Football** per rose aggiornate, foto ufficiali, gare saltate
   e indisponibili di oggi;
5. calcola il **prezzo consigliato** distribuendo il monte crediti della lega
   fra i giocatori che verranno davvero comprati;
6. committa il CSV aggiornato.

Alle 05:00 FantaBot lo scarica.

## Fonti da aggiornare a mano

| File | Quando | Dove prenderlo |
|---|---|---|
| `Quotazioni_Fantacalcio_Stagione_AAAA_AA.xlsx` | a ogni aggiornamento delle quotazioni | area download di Fantacalcio.it |
| `Statistiche.xlsx` | una volta a stagione, a campionato finito | area download di Fantacalcio.it |
| `Lista-FantaAsta-Fantacalcio.csv` | quando cambia l'anagrafica | area download di Fantacalcio.it |

Il file quotazioni piu' recente viene scelto **da solo** in base al nome: basta
caricare quello nuovo. Il vecchio si puo' cancellare.

## Variabili d'ambiente

| Variabile | Default | A cosa serve |
|---|---|---|
| `API_FOOTBALL_KEY` | — | chiave API-Football (secret della repo) |
| `FANTA_SEASON_STATS` | `2025` | stagione conclusa (2025 = 2025/26) |
| `FANTA_SEASON` | `2026` | stagione in corso, per gli infortuni |
| `FANTA_MAX_LOOKUP` | `600` | tetto ai lookup statistiche per giocatore |
| `FANTA_PAUSA` | `0.3` | secondi fra due chiamate (6.5 sul piano free) |
| `FANTA_SQUADRE_LEGA` | `8` | squadre della lega di riferimento |
| `FANTA_BUDGET` | `500` | crediti per squadra |
| `FANTA_ESPONENTE` | `1.0` | quanto e' ripida la scala prezzi (>1 = top piu' cari) |
| `FANTA_FVM` | `ufficiale` | `ufficiale` \| `stima` \| `misto` |
| `FANTA_STRICT` | `1` | se `1`, un dato mancante fa fallire il run |

## Colonne di `Lista_Finale_Master.csv`

Separatore `;`. Le principali:

- **Anagrafica**: `Id`, `Nome`, `Nome_Breve`, `Nome_Completo`, `R`,
  `Ruolo_Esteso`, `Squadra`, `Piede`, `Nazionalita`, `DataNascita`,
  `PhotoURL`, `FotoAPI`
- **Valore**: `Qt.A`, `Qt.I`, `Qt.M`, `Diff.M`, `FVM`, `FVM.M`,
  `FVM_Ufficiale`, `FVM_Stima`, `Scarto`, `Prezzo`
- **Rendimento**: `Pv`, `Mv`, `Fm`, `Gf`, `Gs`, `Rp`, `Rc`, `R+`, `R-`,
  `Ass`, `Amm`, `Esp`
- **Impiego**: `PvTot`, `SquadreStag`, `Tit`, `Min`
- **Disponibilita'**: `GareSaltate` (**solo** assenze fisiche), `MotivoStop`,
  `GareSaltateAltro` (squalifiche, nazionale, turnover), `MotivoAltro`,
  `Infortunio`, `InfortunioTipo`, `InfortunioDal`
- `Aggiornato`

`FVM` e' il valore su cui si calcolano prezzi e fasce. `FVM_Stima` e' il
modello interno; `Scarto` = stima / ufficiale. Uno **scarto alto** segnala un
giocatore che il modello valuta piu' del mercato: e' li' che si cercano le
occasioni, non nella classifica dei piu' cari.

## Regole di progetto

- Si scrivono **fatti**, non deduzioni. "Ha saltato 12 gare per un infortunio
  al ginocchio" e' un fatto; "e' fragile" e' un giudizio, e lo fa chi legge.
- Assenze fisiche e squalifiche stanno in **colonne diverse**.
- Un dato fuori scala (69 presenze in una stagione) viene **scartato**, non
  pubblicato.
- Nessuna logica di presentazione qui dentro: quella e' di FantaBot.
