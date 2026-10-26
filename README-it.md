<p align="center">
  <img src="assets/logo.svg" alt="logo mcp-freesound" width="220">
</p>

<p align="center">
  <b>Cerca, esplora e accredita l'audio di Freesound.org da qualsiasi assistente AI.</b><br>
  Server Model Context Protocol in Python puro, senza dipendenze, via stdio o HTTP con bearer token.
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white">
  <img alt="Dipendenze" src="https://img.shields.io/badge/dipendenze%20runtime-0-success">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-2025--06--18-6E56CF">
  <img alt="Licenza" src="https://img.shields.io/badge/licenza-MIT-blue">
</p>

<p align="center">
  <a href="README.md">🇬🇧 Read in English</a>
</p>

---

## Che cos'è?

**mcp-freesound** è un server [Model Context Protocol](https://modelcontextprotocol.io) (MCP)
che collega gli assistenti AI (Claude Desktop, Claude Code, IDE e agenti compatibili MCP) a
[Freesound.org](https://freesound.org), il database collaborativo con oltre 600.000 suoni
Creative Commons.

Una volta collegato, puoi chiedere all'assistente cose come *"trovami tre suoni di tuono brevi,
CC0, per una scena di temporale e dammi i credits"*. L'assistente cerca su Freesound, confronta i
risultati, controlla le licenze, scarica le anteprime e scrive il testo di attribuzione al posto tuo.

È una reimplementazione completa di
[johnkimdw/freesound-mcp-server](https://github.com/johnkimdw/freesound-mcp-server) in Python
puro. L'originale ha un solo tool; questa versione ne ha tredici, più un trasporto HTTP
autenticato e una GUI di configurazione.

## Perché serve?

- **Trovare il suono giusto richiede tempo.** Sfogliare, filtrare, ascoltare e verificare le
  licenze a mano è lento. Un assistente può fare molte ricerche e restringere la scelta per te.
- **Le licenze sono facili da sbagliare.** Su Freesound convivono suoni CC0, CC BY e CC BY-NC.
  `get_attribution` dice quali suoni richiedono attribuzione e quali consentono l'uso
  commerciale, e scrive le righe di credito.
- **Gli assistenti AI non possono raggiungere Freesound da soli.** MCP è lo standard per dar
  loro questo accesso in modo sicuro, tramite tool con input tipizzati.
- **Nessun problema di dipendenze.** Il server funziona con qualunque Python 3.10+ senza
  installare nulla (`python mcp-freesound.py`): va bene anche in ambienti blindati, mirror
  offline e container minimali.
- **Locale o condiviso.** Usa stdio per l'uso personale sul desktop. Usa il trasporto HTTP,
  protetto da bearer token, per condividere un server con il team o eseguirlo su un'altra macchina.

## Quando usarlo

| Usalo quando... | Meglio altro quando... |
|---|---|
| monti video o podcast e ti servono effetti, ambienti o loop | ti servono file originali alla massima qualità in blocco (richiede OAuth2 di Freesound, vedi [Avvertenze](#avvertenze)) |
| vuoi che un assistente cerchi, confronti e preselezioni i suoni | devi caricare, votare o commentare suoni (le operazioni di scrittura non sono esposte) |
| ti servono attribuzioni corrette e verifica licenze prima di pubblicare | ti serve una consulenza legale certa sulle licenze |
| costruisci agenti o pipeline che scelgono l'audio in automatico | ti serve un'integrazione di produzione ad alto volume (rispetta limiti e termini dell'API Freesound) |
| analizzi descrittori audio (bpm, tonalità, loudness) su molti suoni | |

## Funzionalità

- **13 tool**: ricerca con filtri e ordinamento, dettagli suono, suoni simili, analisi audio,
  commenti, utenti, pack, generatore di attribuzioni, download anteprime, consumo API.
- **Due trasporti**: `stdio` (predefinito) e **Streamable HTTP** protetto da **bearer token**,
  con TLS opzionale, controllo `Origin` (protezione DNS-rebinding), sessioni e sonda `/health`.
- **GUI di configurazione** (Tkinter): test della API key, generatore di token, snippet pronti
  per i client, configurazione di Claude Desktop con un clic, avvio del server con log in tempo reale.
- **Zero dipendenze runtime**: solo libreria standard, Python 3.10-3.13, Windows/macOS/Linux.
- **Sicuro di default**: la API key viaggia in un header e mai nell'URL; HTTP ascolta su
  `127.0.0.1`; il server rifiuta di avviare HTTP senza token; i download sono limitati agli
  host Freesound e a una sola cartella.
- **Retrocompatibile**: `search_sounds` accetta gli stessi argomenti e restituisce la stessa
  struttura del server originale.

## Come funziona

<p align="center">
  <img src="assets/infographic.svg" alt="infografica architettura mcp-freesound" width="100%">
</p>

Dettagli in [docs/architecture.md](docs/architecture.md) (in inglese).

---

## Avvio rapido

```bash
git clone https://github.com/jumpnotequal/mcp-freesound.git
cd mcp-freesound
python mcp-freesound.py gui        # incolla la API key, "Test key", poi "Save"
python mcp-freesound.py check      # facoltativo: verifica la chiave da riga di comando
```

Poi, nella scheda **Client setup** della GUI, clicca **Add to Claude Desktop config** (viene
tenuto un backup del file esistente) e riavvia Claude Desktop. Fatto.

## Installazione

Serve **Python 3.10+**. Tkinter serve solo per la GUI: è incluso negli installer di python.org;
su Debian/Ubuntu installa `python3-tk`.

**Opzione A: esecuzione da clone (nessuna installazione)**

```bash
git clone https://github.com/jumpnotequal/mcp-freesound.git
python mcp-freesound/mcp-freesound.py --help
```

**Opzione B: installazione con pip** (aggiunge i comandi `mcp-freesound` e `mcp-freesound-gui`)

```bash
pip install git+https://github.com/jumpnotequal/mcp-freesound.git
mcp-freesound --help
```

### Ottenere una API key di Freesound

1. Crea un account gratuito su [freesound.org](https://freesound.org).
2. Richiedi una credenziale API su <https://freesound.org/apiv2/apply/>.
3. Copia il valore **Client secret/Api key**: è la tua `FREESOUND_API_KEY`.

## Configurazione

Le impostazioni vengono lette da queste fonti; ognuna sovrascrive la precedente:

```text
default  <  file di config  <  ./.env  <  variabili d'ambiente  <  flag CLI
```

La **GUI** (`mcp-freesound gui`) modifica il file di configurazione:

| OS | File di configurazione |
|---|---|
| Windows | `%APPDATA%\mcp-freesound\config.json` |
| macOS | `~/Library/Application Support/mcp-freesound/config.json` |
| Linux | `~/.config/mcp-freesound/config.json` |

| Impostazione | Variabile d'ambiente | Flag CLI | Default |
|---|---|---|---|
| API key Freesound | `FREESOUND_API_KEY` | `--api-key` | (obbligatoria) |
| Trasporto | `MCP_FREESOUND_TRANSPORT` | `--transport` | `stdio` |
| Host HTTP | `MCP_FREESOUND_HOST` | `--host` | `127.0.0.1` |
| Porta HTTP | `MCP_FREESOUND_PORT` | `--port` | `8000` |
| Path HTTP | `MCP_FREESOUND_PATH` | `--path` | `/mcp` |
| Bearer token | `MCP_FREESOUND_AUTH_TOKEN` | `--auth-token` | (obbligatorio per HTTP) |
| Origin aggiuntive consentite | `MCP_FREESOUND_ALLOWED_ORIGINS` | `--allowed-origin` | solo localhost |
| Certificato / chiave TLS | `MCP_FREESOUND_TLS_CERT` / `_TLS_KEY` | `--tls-cert` / `--tls-key` | disattivo |
| Cartella download | `MCP_FREESOUND_DOWNLOAD_DIR` | `--download-dir` | `~/Downloads/freesound` |
| Consenti `download_preview` | `MCP_FREESOUND_ALLOW_DOWNLOADS` | - | `true` |
| Timeout richieste (s) | `MCP_FREESOUND_TIMEOUT` | - | `30` |
| Livello di log | `MCP_FREESOUND_LOG_LEVEL` | `--log-level` | `INFO` |
| Percorso file di config | `MCP_FREESOUND_CONFIG` | `--config` | percorso per-OS sopra |

Vedi [examples/.env.example](examples/.env.example) e
[examples/config.example.json](examples/config.example.json).

> **Windows: le variabili d'ambiente arrivano sempre al server.** Alcuni client MCP (tra cui
> Claude Desktop) avviano i server con un ambiente ridotto, senza le tue variabili. Quando una
> variabile della tabella manca dal processo, mcp-freesound la legge direttamente dal registro
> di Windows: prima le variabili utente, poi quelle di sistema. Imposta `FREESOUND_API_KEY` una
> volta sola in *Impostazioni → Sistema → Informazioni → Impostazioni di sistema avanzate →
> Variabili d'ambiente* (oppure `setx FREESOUND_API_KEY la_tua_key`) e non dovrai mettere la
> chiave nella configurazione di nessun client. Su macOS/Linux usa il blocco `env` del client
> o la GUI.

## Trasporti

### stdio (predefinito)

Il client MCP avvia il server come processo figlio e comunica via stdin/stdout. È la scelta
migliore per l'uso personale sul desktop.

```bash
mcp-freesound                       # equivale a: mcp-freesound serve --transport stdio
```

### HTTP con bearer token

Il server ascolta su un URL. Ogni richiesta deve contenere `Authorization: Bearer <token>`.

```bash
mcp-freesound token                                     # genera un token casuale robusto
mcp-freesound serve --transport http --auth-token <token>
# -> http://127.0.0.1:8000/mcp   (health check: http://127.0.0.1:8000/health)
```

Per raggiungerlo da altre macchine, ascolta su un'interfaccia pubblica **e attiva TLS**, oppure
mettilo dietro un reverse proxy TLS:

```bash
mcp-freesound serve --transport http --host 0.0.0.0 --port 8443 \
  --auth-token <token> --tls-cert cert.pem --tls-key key.pem
```

`--insecure-no-auth` disattiva l'autenticazione: usalo solo per test in locale.

## Configurazione dei client

**Claude Desktop, stdio** (`claude_desktop_config.json`, oppure usa il pulsante della GUI):

```json
{
  "mcpServers": {
    "freesound": {
      "command": "mcp-freesound",
      "args": ["serve", "--transport", "stdio"],
      "env": { "FREESOUND_API_KEY": "la_tua_api_key_freesound" }
    }
  }
}
```

Esegui da clone invece che da pip? Usa `"command": "python"` e
`"args": ["/percorso/mcp-freesound/mcp-freesound.py", "serve"]`.

Hai già `FREESOUND_API_KEY` come variabile d'ambiente di Windows, o hai salvato la chiave con
la GUI? Allora ometti del tutto il blocco `env`:

```json
{
  "mcpServers": {
    "freesound": {
      "command": "C:/Python/python.exe",
      "args": ["C:/percorso/mcp-freesound/mcp-freesound.py", "serve", "--transport", "stdio"]
    }
  }
}
```

**Claude Code**

```bash
claude mcp add freesound -e FREESOUND_API_KEY=la_tua_key -- mcp-freesound serve --transport stdio
claude mcp add --transport http freesound http://127.0.0.1:8000/mcp --header "Authorization: Bearer <token>"
```

**Qualsiasi client che supporta Streamable HTTP**: vedi [examples/http_client.json](examples/http_client.json).
**Claude Desktop verso un server HTTP remoto**: vedi [examples/claude_desktop_http_bridge.json](examples/claude_desktop_http_bridge.json).

**Debug con MCP Inspector**

```bash
npx @modelcontextprotocol/inspector python mcp-freesound.py
```

## Tool

| Tool | Cosa fa |
|---|---|
| `search_sounds` | Ricerca testuale con filtri Freesound (`duration:[0 TO 10] license:"Creative Commons 0"`), ordinamento e paginazione |
| `get_sound` | Dettagli completi: sample rate, bit depth, canali, dimensione, pack, geotag, voti, download, anteprime, waveform |
| `find_similar_sounds` | Suoni acusticamente simili |
| `get_sound_analysis` | Descrittori audio come bpm, tonalità, loudness |
| `get_sound_comments` | Commenti su un suono |
| `get_user` / `get_user_sounds` / `get_user_packs` | Esplora un autore |
| `get_pack` / `get_pack_sounds` | Esplora un pack |
| `get_attribution` | Righe di credito più "attribuzione richiesta?" e "uso commerciale consentito?" per fino a 50 suoni |
| `download_preview` | Salva l'anteprima MP3/OGG nella cartella di download |
| `get_api_usage` | Quante richieste API ha usato la tua chiave |

Riferimento completo con argomenti e output: [docs/tools.md](docs/tools.md) (in inglese).

### Prompt di esempio

- "Trova effetti di tuono per una scena di temporale, sotto i 20 secondi, solo CC0."
- "Cerca suoni ambientali di città ordinati per voto e scarica le anteprime dei due migliori."
- "Mostrami suoni simili al 2523 e dimmi il loro bpm."
- "Nel mio video ho usato i suoni 2523, 41529 e 9834: scrivi i credits e dimmi se posso monetizzarlo."
- "Chi ha caricato il suono 2523 e quali altri pack ha pubblicato?"

## Riferimento CLI

```text
mcp-freesound [serve] [--transport stdio|http] [--host H] [--port P] [--path /mcp]
                      [--auth-token T] [--allowed-origin O]... [--tls-cert F --tls-key F]
                      [--insecure-no-auth]
mcp-freesound gui                       apre la GUI di configurazione (anche: mcp-freesound-gui)
mcp-freesound token                     stampa un nuovo bearer token casuale
mcp-freesound config [--show-secrets]   stampa la configurazione effettiva
mcp-freesound check                     verifica la API key di Freesound
opzioni globali: --config FILE --api-key KEY --download-dir DIR --log-level LEVEL --version
```

`python mcp-freesound.py ...` accetta esattamente gli stessi argomenti.

## Struttura del progetto

```text
mcp-freesound.py      launcher del server (funziona senza installazione)
src/mcp_freesound/    package core: protocollo, tool, client Freesound, trasporti, GUI
docs/                 architettura e riferimento dei tool
examples/             config dei client, template .env e file di config, chiamate curl
assets/               logo e infografica (SVG + PNG)
test/                 test locali e smoke test (output in test/_out, ignorato da git)
publishme.bat         crea il repository GitHub e fa il push (Windows)
```

## Sviluppo

```bash
python -m venv test/.venv
test/.venv/Scripts/python -m pip install pytest ruff build   # Linux/macOS: test/.venv/bin/python
test/.venv/Scripts/python -m pytest -p no:cacheprovider --basetemp=test/_out/pytest test
test/.venv/Scripts/python test/smoke_http.py                 # server reale via HTTP + bearer token
test/.venv/Scripts/ruff check . && test/.venv/Scripts/ruff format --check .
```

Test, virtualenv e output restano tutti dentro `test/`. Dettagli in [test/README.md](test/README.md) (in inglese).

I contributi sono benvenuti: vedi [CONTRIBUTING.md](CONTRIBUTING.md) e [SECURITY.md](SECURITY.md).

## Avvertenze

- **Non affiliato a Freesound.** Freesound è un progetto del Music Technology Group,
  Universitat Pompeu Fabra. Questo è un client indipendente e non ufficiale.
- **La conformità alle licenze è responsabilità tua.** Ogni suono ha la propria licenza (CC0,
  CC BY, CC BY-NC...). L'analisi delle licenze e i credits prodotti da `get_attribution` sono un
  aiuto, non una consulenza legale. Controlla sempre la pagina del suono prima di pubblicare.
- **Termini e limiti dell'API.** L'uso dell'API Freesound è regolato dai
  [termini d'uso dell'API Freesound](https://freesound.org/help/tos_api/). Le chiavi standard
  hanno limiti di richieste e possono essere limitate all'uso non commerciale. Verifica i termini
  aggiornati e contatta Freesound per usi commerciali o ad alto volume.
- **Solo anteprime.** `download_preview` salva le anteprime compresse. Scaricare i file originali
  richiede l'autenticazione utente OAuth2, che questo server non implementa.
- **Sicurezza.** Tratta API key e bearer token come password. Non esporre il trasporto HTTP in
  rete senza TLS. Vedi [SECURITY.md](SECURITY.md).
- **Output dell'AI.** Gli assistenti possono fraintendere i risultati: verifica scelte e credits
  prima di farci affidamento.
- Fornito "così com'è", senza alcuna garanzia (vedi [LICENSE](LICENSE)).

## Crediti

- Idea e prima implementazione:
  [johnkimdw/freesound-mcp-server](https://github.com/johnkimdw/freesound-mcp-server) (MIT).
- Suoni e API: [Freesound.org](https://freesound.org), MTG, UPF.
- Protocollo: [Model Context Protocol](https://modelcontextprotocol.io).

## Licenza

[MIT](LICENSE). L'audio trovato tramite questo server è soggetto alla licenza di ciascun suono.
