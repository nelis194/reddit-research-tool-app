# 🔎 Reddit Research Tool

Een **generieke** tool om voor elk bedrijf, product, niche, markt, concurrent,
doelgroep of onderwerp Reddit-discussies te **verzamelen, analyseren en
exporteren**. Bedoeld voor customer research, market research, persona research,
copywriting research en product research.

Werkt voor o.a.: `artery plaque`, `huidverzorging`, `supplementen`, `SaaS`,
`AI tools`, `crypto`, `fitness`, concurrent-namen, product reviews, customer
complaints, pain points, B2B/B2C niches — letterlijk elk keyword.

> **Privacy by design:** de tool verzamelt **geen gebruikersdata** (geen
> usernames, user-ids, karma, profielen of accountinformatie). Alleen de inhoud
> van discussies wordt bewaard en geanalyseerd.

---

## ✨ Wat krijg je

Voor elk keyword/onderwerp ontdek je:
- wat mensen zeggen, welke **problemen** en **frustraties** terugkomen;
- welke **oplossingen** mensen proberen en wat wél/niet werkt;
- welke **bezwaren** en **koopmotieven** spelen;
- welke **taal, woorden, zinnen en emoties** vaak voorkomen;
- welke **subreddits** en **persona-segmenten** relevant zijn;
- bruikbare **marketing hooks, ad-hoeken, content-ideeën en FAQ's**.

---

## 📦 Installatie

Vereist **Python 3.9+** (getest op 3.9; werkt ook op 3.11+).

```bash
cd reddit_research_tool_v2
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

PostgreSQL is optioneel — installeer dan ook `psycopg2-binary` (zie
`requirements.txt`).

---

## ⚙️ Configuratie

Kopieer `.env.example` naar `.env` en pas aan. **Niets is verplicht** — alle
waarden hebben veilige defaults.

```bash
cp .env.example .env
```

### Uitleg per variabele

| Variabele | Default | Betekenis |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` (Claude) of `openai`. |
| `ANTHROPIC_API_KEY` | _(leeg)_ | Claude-key (`sk-ant-...`). Leeg = lokale analyse. |
| `ANTHROPIC_MODEL` | `claude-opus-4-8` | Claude-model voor verrijking. |
| `OPENAI_API_KEY` | _(leeg)_ | OpenAI-key (alleen bij `LLM_PROVIDER=openai`). |
| `OPENAI_MODEL` | `gpt-4o-mini` | OpenAI-model voor verrijking. |
| `DATABASE_URL` | _(leeg)_ | Leeg = SQLite in `data/`. Supabase/Postgres: `postgresql://...`. |
| `MAX_POSTS_PER_QUERY` | `500` | Max posts per zoekterm. |
| `MAX_COMMENTS_PER_POST` | `500` | Max comments per post (0 = geen comments). |
| `SEARCH_TIME_FILTER` | `all` | `day` / `week` / `month` / `year` / `all`. |
| `SEARCH_SORT` | `relevance` | `relevance` / `hot` / `top` / `new` / `comments`. |
| `REQUESTS_PER_MINUTE` | `30` | Hard maximum requests/min (rolling window). |
| `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` | `1` / `5` | Willekeurige delay tussen requests. |
| `MAX_RETRIES` | `5` | Aantal retries bij 429/5xx. |
| `BACKOFF_BASE_SECONDS` / `BACKOFF_MAX_SECONDS` | `2` / `60` | Exponentiële backoff. |
| `DRY_RUN` | `false` | `true` = simuleer scraping zonder HTTP. |
| `USER_AGENT` | _(zie .env)_ | Reddit blokkeert lege/standaard user-agents. |
| `REDDIT_BASE_URL` | `https://www.reddit.com` | Reddit-basis. |

### Bright Data proxy (aanbevolen)

Reddit blokkeert directe scraping inmiddels vaak met **HTTP 403/429**. Om dit
te omzeilen routeer je verzoeken via **Bright Data**:

```env
# Optie 1 — volledige proxy-URL:
BRIGHTDATA_PROXY_URL=http://brd-customer-XXX-zone-YYY:PASSWORD@brd.superproxy.io:33335

# Optie 2 — losse velden:
BRIGHTDATA_USERNAME=brd-customer-XXX-zone-YYY
BRIGHTDATA_PASSWORD=jouw-wachtwoord
BRIGHTDATA_HOST=brd.superproxy.io
BRIGHTDATA_PORT=33335

# Bright Data Web Unlocker / residential gebruikt een eigen CA:
BRIGHTDATA_SSL_VERIFY=true
# BRIGHTDATA_CA_BUNDLE=/pad/naar/brightdata_ca.crt   # veiliger dan SSL uitzetten
```

Zodra deze velden gevuld zijn, loopt **al het verkeer automatisch via de proxy**
(je ziet in de zijbalk en logs "Bright Data proxy actief"). Zonder proxy blijft
de tool werken, maar kun je tegen 403/429 aanlopen.

---

## ▶️ Streamlit dashboard starten

```bash
streamlit run app.py
```

Daarna in de browser:
1. Voer **keywords/onderwerpen/concurrenten** in (één per regel of komma's).
2. Optioneel: beperk tot specifieke **subreddits** en geef **concurrent-termen**.
3. Kies **sortering** en **periode**, stel limieten in.
4. Klik **🚀 Scrape**, daarna **🧠 Analyseer**.
5. Bekijk de tabbladen en exporteer in het **⬇️ Export**-tabblad.

---

## 🔍 Voorbeeldzoekopdrachten

| Doel | Keywords | Subreddits |
|---|---|---|
| Pijnpunten huidverzorging | `acne`, `rosacea`, `dry skin` | `SkincareAddiction` |
| Supplement-research | `artery plaque`, `CoQ10`, `cholesterol` | `Supplements`, `AskDocs` |
| SaaS-concurrentie | `Notion`, `Obsidian`, `competitor name` | `productivity` |
| Dropshipping pains | `dropshipping problems`, `supplier issues` | `dropship` |
| Crypto-sentiment | `staking`, `cold wallet`, `gas fees` | `CryptoCurrency` |

---

## 📊 Analysemogelijkheden

**Lokaal (altijd, zonder API-key):** top pijnpunten, frustraties, gewenste
uitkomsten, geslaagde/mislukte oplossingen, genoemde producten/merken/
concurrenten, voice-of-customer quotes, veelgebruikte woorden & zinnen (n-grams),
TF-IDF, sentiment, persona-clusters (op taalgebruik), koopbezwaren & -motieven,
content angles, ad hooks, FAQ's, before/after, trends en herhalende klachten/
complimenten.

**LLM (met `ANTHROPIC_API_KEY`, of `OPENAI_API_KEY` bij `LLM_PROVIDER=openai`):**
thematische samenvattingen, persona cards & clusters, marketing- & customer-
insights, content-ideeën, ad-hoeken, FAQ's met antwoorden, landing-page-hooks en
offer-ideeën. Standaard model: **Claude `claude-opus-4-8`** (adaptive thinking).

### ⚕️ Medische onderwerpen
Bij gezondheid/supplementen/aandoeningen/behandelingen voegt de tool
automatisch een **disclaimer** toe, labelt claims als **door gebruikers
gerapporteerd / anekdotisch** en benadrukt dat het **geen medisch advies** is.

---

## ⬇️ Exportmogelijkheden

Exports landen in `exports/<run-slug>/`:

- `raw_posts.csv`, `raw_comments.csv`, `cleaned_comments.csv`
- `insights_summary.md`, `persona_report.md`
- `voice_of_customer_quotes.csv`
- `solution_mentions.csv`, `pain_points.csv`, `frustrations.csv`
- `content_angles.csv`, `ad_hooks.csv`
- `analysis.json` (volledige analyse)

---

## 🗄️ Databasestructuur

SQLite (`data/reddit_research.db`) of PostgreSQL. Tabellen:

- **searches** — elke zoekopdracht (keywords, subreddits, sort, time_filter, tellingen).
- **posts** — verzamelde posts (zonder gebruikersdata), uniek op `dedup_key`.
- **comments** — verzamelde comments (zonder gebruikersdata), uniek op `dedup_key`.
- **analysis_results** — opgeslagen analyse-payloads (JSON).
- **exports** — gegenereerde exportbestanden.

---

## 🧩 Dashboard-uitleg

| Tab | Inhoud |
|---|---|
| 📋 Resultaten | Posts & comments met filters (subreddit, keyword, score). |
| 😖 Pijnpunten | Top pijnpunten + terugkerende klachten. |
| 😤 Frustraties | Top frustraties met voorbeeldcitaten. |
| 🛠️ Oplossingen | Geslaagde/mislukte oplossingen, merken, concurrenten. |
| 💬 Quotes | Voice-of-customer quotes per categorie. |
| 👥 Persona's | Persona-clusters (+ LLM persona cards). |
| 📈 Inzichten | Koopmotieven/-bezwaren, content angles, ad hooks, sentiment, FAQ's. |
| ⬇️ Export | Genereer en download alle exportbestanden. |

---

## 🧱 Projectstructuur

```
reddit_research_tool_v2/
├── app.py                 # Streamlit-dashboard
├── requirements.txt
├── .env.example
├── README.md
├── src/
│   ├── config.py          # .env-config + Bright Data proxy
│   ├── web_client.py      # HTTP: rate limiting, backoff, proxy
│   ├── scraper.py         # zoekmodule + comments + dedup
│   ├── parser.py          # Reddit JSON/HTML -> modellen (geen userdata)
│   ├── database.py        # SQLite/Postgres
│   ├── cleaner.py         # filtering, normalisatie, taal, dedup, groepering
│   ├── analyzer.py        # lokale analyse-pipeline
│   ├── llm_analyzer.py    # optionele OpenAI-verrijking
│   ├── exporter.py        # CSV/JSON/Markdown export
│   └── utils.py           # logging, hashing, helpers
├── data/                  # SQLite-db
├── exports/               # gegenereerde exports
├── logs/                  # logbestanden
└── tests/                 # pytest (cleaner, analyzer, parser)
```

---

## 🧪 Tests

```bash
pytest -q
```

---

## ☁️ Online hosting (zodat je partner erbij kan)

> **Belangrijk:** Streamlit draait **niet** op Vercel (Vercel is voor
> serverless/Next.js; Streamlit heeft een continu draaiende server nodig).
> Gebruik **Streamlit Community Cloud** voor de app en **Supabase** als gedeelde
> database. Vercel kun je blijven gebruiken voor je andere (Next.js) tools.

**Architectuur:** Streamlit Cloud (app) → Supabase (Postgres, gedeelde data) →
Anthropic (Claude) + Bright Data (proxy).

### Stap 1 — Supabase database
1. Maak een project op [supabase.com](https://supabase.com).
2. **Project Settings → Database → Connection string → "Transaction pooler"**
   (poort `6543`). Kopieer de string en vervang `[YOUR-PASSWORD]`.
3. Dit is je `DATABASE_URL`. De tool maakt de tabellen automatisch aan bij de
   eerste run (`init_db`).

### Stap 2 — Code naar GitHub
Streamlit Cloud deployt vanaf een GitHub-repo:
```bash
cd reddit_research_tool_v2
git init && git add . && git commit -m "Reddit Research Tool"
# maak een (private) repo op github.com en push:
git remote add origin https://github.com/<jij>/reddit-research-tool.git
git push -u origin main
```
`.env` wordt **niet** meegepusht (staat in `.gitignore`) — secrets gaan via stap 3.

### Stap 3 — Deploy op Streamlit Community Cloud
1. Ga naar [share.streamlit.io](https://share.streamlit.io) en log in met GitHub.
2. **New app** → kies je repo, branch `main`, main file `app.py`.
3. **Advanced settings → Secrets**: plak de inhoud van
   `.streamlit/secrets.toml.example` met je echte waarden (`ANTHROPIC_API_KEY`,
   `DATABASE_URL`, `BRIGHTDATA_*`). Streamlit zet die als environment variables.
4. **Deploy.** Je krijgt een URL zoals `https://<app>.streamlit.app`.

### Stap 4 — Partner toegang geven
- Streamlit Cloud → app → **Settings → Sharing**: nodig je partner uit via e-mail
  (private app), of zet de app op public als dat mag.
- Je partner gebruikt dezelfde URL; data is gedeeld omdat jullie dezelfde Supabase
  database gebruiken.

### Alternatieven voor de hosting
- **Render** of **Railway**: meer controle, app blijft draaien, eigen auth mogelijk
  (`streamlit run app.py` als start-command). Iets meer setup dan Streamlit Cloud.
- **Hugging Face Spaces** (type: Streamlit): ook gratis en eenvoudig.

---

## 🛟 Troubleshooting

- **HTTP 403 / 429 / geen resultaten** → Reddit blokkeert directe scraping.
  Vul de **Bright Data**-velden in `.env`. Verlaag eventueel
  `REQUESTS_PER_MINUTE` en verhoog `MIN/MAX_DELAY_SECONDS`.
- **SSL-fout via proxy** → zet `BRIGHTDATA_CA_BUNDLE` (aanbevolen) of tijdelijk
  `BRIGHTDATA_SSL_VERIFY=false`.
- **`langdetect` mist** → taalfilter wordt dan stil overgeslagen; `pip install langdetect`.
- **PostgreSQL-fout** → `pip install psycopg2-binary` en controleer `DATABASE_URL`.
- **Geen LLM-output** → controleer `ANTHROPIC_API_KEY` (of bij OpenAI: `LLM_PROVIDER=openai` + `OPENAI_API_KEY`). Bij een 400-fout over `thinking`/`budget_tokens`: gebruik een Claude 4.x-model (default `claude-opus-4-8`).
- **Supabase: "password authentication failed"** → gebruik de **pooler**-string (poort 6543) en het juiste database-wachtwoord; URL-encode speciale tekens in het wachtwoord.
- **Niets gebeurt / wil testen zonder HTTP** → zet `DRY_RUN=true`.
- **Wees nette burger** → respecteer Reddit's voorwaarden en gebruik redelijke
  limieten; deze tool is voor research, niet voor massascraping.
