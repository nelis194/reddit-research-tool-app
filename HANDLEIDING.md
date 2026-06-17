# 📘 Handleiding — Reddit Research Tool

## Wat doet deze tool?
Je voert één of meer **zoekwoorden** in (bijv. een onderwerp, product, merk of
concurrent). De tool verzamelt daarover **echte discussies van Reddit** en
analyseert ze automatisch. Je krijgt overzichtelijk terug wat mensen écht zeggen:
hun pijnpunten, frustraties, oplossingen, koopmotieven en letterlijke citaten.
Handig voor markt-, klant- en copy-onderzoek.

De data is gedeeld — wat jij of je collega ophaalt, staat voor jullie beiden klaar.

---

## De velden links (zijbalk) — wat vul je in?

| Veld | Wat vul je in | Uitleg |
|---|---|---|
| **Keywords / onderwerpen** | Eén zoekopdracht **per regel** | Dit is het belangrijkste veld. Zie de voorbeelden hieronder. |
| **Subreddits** (optioneel) | Bijv. `Supplements, nutrition` | Leeg laten = heel Reddit doorzoeken (aanbevolen). Vul je iets in, dan zoekt hij alleen in die groepen. |
| **Concurrent-termen** (optioneel) | Merknamen, bijv. `merk A, merk B` | De tool telt hoe vaak die genoemd worden. |
| **Sortering** | `relevance` (standaard) | Hoe de resultaten gerangschikt worden: meest relevante, populairste (`top`), nieuwste (`new`), enz. |
| **Periode** | `all` (standaard) | Tijdvenster: alles, of bijv. laatste week/maand/jaar. |
| **Max posts per zoekterm** | Bijv. `100` | Hoeveel posts maximaal per zoekopdracht. |
| **Max comments per post** | **Begin met `0`** | Reacties geven diepgang, maar maken het traag. Eerst posts-only draaien is het slimst. |
| **Taalfilter** | `(geen)` of `en` | Houd alleen resultaten in die taal. |

---

## Zoekwoorden goed invullen (belangrijk!)
Je kunt slim combineren met **aanhalingstekens** (exacte woorden) en **`AND`**
(beide moeten voorkomen). Zet hiervoor het **Subreddit-veld leeg**.

**Voorbeeld** (één regel = één zoekopdracht):

```
"cocoa" AND "blood pressure"
"dark chocolate" AND "heart health"
"epicatechin" AND "cacao"
```

- `" "` = zoek exact dat woord / die zin
- `AND` (in hoofdletters) = beide moeten in het bericht staan
- Gebruik **rechte** aanhalingstekens `"` (niet de krullende)
- Géén komma's binnen één zoekopdracht (die splitsen hem op)

---

## De 3 knoppen onderaan
1. **Scrape starten** → haalt de Reddit-discussies op voor je zoekwoorden.
2. **Analyseren** → verwerkt alles tot inzichten (pijnpunten, quotes, persona's…).
   Even geduld: na de snelle analyse denkt de AI (Claude) nog ~½–1 minuut mee.
3. **Laad opgeslagen scrape** → haalt de laatst opgehaalde data er weer bij,
   zónder opnieuw te scrapen.

**Volgorde:** Zoekwoorden invullen → **Scrape starten** → **Analyseren** →
bekijk de tabbladen.

---

## De tabbladen (bovenin)
| Tab | Wat zie je |
|---|---|
| **Resultaten** | De ruwe posts & reacties, met filters. |
| **Pijnpunten** | Problemen die steeds terugkomen. |
| **Frustraties** | Waar mensen zich aan ergeren. |
| **Oplossingen** | Wat wél en níét werkt volgens mensen. |
| **Quotes** | Letterlijke citaten (goud voor copywriting). |
| **Persona's** | Welke type gebruikers zichtbaar worden (beginner, prijsbewust, enz.). |
| **Inzichten** | Koopmotieven, bezwaren, content-ideeën, advertentiehoeken, FAQ's. |
| **Export** | Download alles als **Word-rapport** of losse bestanden. |

---

## Het eindresultaat
In het tabblad **Export** staat bovenaan **"Download Word-rapport (.docx)"** —
één net document met alle hoofdstukken (samenvatting, pijnpunten, frustraties,
oplossingen, quotes, persona's, AI-inzichten). Klaar om te delen of te presenteren.

---

## Handige tips
- **Eerste keer: comments op 0** zetten → snel en betrouwbaar.
- Wil je diepgang? Draai daarna een **kleine** run (2-3 zoekwoorden) mét comments.
- Niets te zien na een herstart? Klik **"Laad opgeslagen scrape"**.
- Rustig aan: te veel zoekopdrachten tegelijk kan Reddit even afknijpen.
