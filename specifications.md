# HankeVAHTI

## Projektin tavoite

Rakenna toimiva MVP-versio sovelluksesta nimeltä HankeVAHTI.

Sovellus auttaa löytämään, arvioimaan ja seuraamaan rahoitushankkeita.

Tietolähteet:

- EURA 2021
- Haeavustuksia.fi

Sovelluksen tarkoitus on:

1. hakea automaattisesti uusia hankkeita
2. tallentaa hankkeet paikalliseen tietokantaan
3. arvioida hankkeiden soveltuvuutta käyttäjän kiinnostusprofiilien perusteella
4. mahdollistaa osallistumispäätösten hallinta
5. seurata hankkeen etenemistä

Kyseessä on yhden käyttäjän paikallinen sovellus.

Ei kirjautumista.

Ei käyttäjähallintaa.

Ei Entra ID -integraatiota MVP-vaiheessa.

---

# Teknologiat

Käytä seuraavia teknologioita:

Backend:

- Python 3.12+
- FastAPI
- SQLAlchemy
- Alembic
- SQLite
- Pydantic

Frontend:

- NiceGUI

Testaus:

- pytest

Muut:

- .env
- logging

Älä käytä:

- Reactia
- TypeScriptiä
- Node.js frontendin rakentamiseen

Sovelluksen tulee käynnistyä:

```bash
python main.py
```

Selain:

```text
http://localhost:8080
```

---

# Projektirakenne

```text
hankevahti/

app/
    api/
    core/
    db/
    models/
    repositories/
    services/
    importers/
    evaluators/
    ui/

    main.py

tests/

data/
    hankevahti.db

.env.example
requirements.txt
README.md
```

---

# Tietolähteet

## Haeavustuksia.fi

Hankelistaus:

https://www.haeavustuksia.fi/api/haku/list-items

Esimerkkikutsu:

https://www.haeavustuksia.fi/api/haku/list-items?Pagination.Page=1&Pagination.PageSize=20&Language=fi&SearchTerm=&VaOrgLyhenne=&ShowFuture=true&ShowOngoing=true&ShowEnded=false&HideExternal=false

Importer:

- käy läpi kaikki sivut
- estää duplikaatit
- päivittää muuttuneet tiedot

Uniikki tunniste:

```text
hakuasianAsianumero
```

Tallenna:

- source
- source_id
- call_identifier
- raw_data

---

## EURA 2021

Lähde:

https://eura2021.fi/hakuilmoitukset/

Data löytyy:

```text
__PREACT_CLI_DATA__
```

Importer hakee:

- vain tila = haettavissa
- vain rahasto = ESR+

Kentät:

- id
- hakutunnus
- otsikko
- alku
- loppu

Älä käytä lopullisessa toteutuksessa laajaa regex-hakua.

Pyri jäsentämään data rakenteellisesti.

Tallenna alkuperäinen data raw_data-kenttään.

---

# Tietokantamallit

## FundingCall

Lähdedata.

Kentät:

- id
- source
- source_id
- call_identifier
- title
- description
- fund
- category
- source_url
- application_start_date
- application_end_date
- raw_data
- created_at
- updated_at

Uniikki:

```text
source + source_id
```

---

## Evaluation

Kentät:

- id
- funding_call_id
- status
- suitability_score
- suitability_summary
- created_at
- updated_at

Tilat:

- NEW
- UNDER_REVIEW
- INTERESTING
- PARTICIPATE
- REJECTED
- ARCHIVED

---

## Participation

Kentät:

- id
- funding_call_id
- stage
- responsible_person
- notes
- next_action
- created_at
- updated_at

Vaiheet:

- NOT_STARTED
- PLANNING
- PREPARING_APPLICATION
- WAITING_FOR_DECISION
- APPROVED
- REJECTED
- COMPLETED

---

## SearchProfile

Kentät:

- id
- name
- fund
- category
- keywords
- excluded_keywords
- active

Esimerkki:

```text
nimi: Oppiminen

rahasto: ESR+

kategoria: 4.2

avainsanat:

- oppiminen
- koulutus
- digitaalisuus
```

---

# Importointi

Painike:

```text
Hae uudet hankkeet
```

Suorittaa:

- EURA importer
- Haeavustuksia importer

Importoinnin tulee olla idempotentti.

Sama hanke ei saa muodostua kahdesti.

Omia arvioita ei saa koskaan ylikirjoittaa.

---

# Soveltuvuusarviointi

Ensimmäinen MVP:

Ei käytä LLM:ää.

Toteuta sääntöpohjainen pisteytys.

Esimerkkejä:

```text
ESR+ = +20

Oppiminen = +15

Koulutus = +15

Digitaalisuus = +15

Kyberturvallisuus = +10
```

Tuloksena:

- pistemäärä 0-100
- perustelu
- osuneet hakuehdot

Rakenteen tulee mahdollistaa myöhemmin OpenAI- tai Azure OpenAI -adapterin lisääminen.

---

# Käyttöliittymä

## Dashboard

Näytä:

- Uusia hankkeita
- Arvioimattomia hankkeita
- Osallistuttavia hankkeita
- Hylättyjä hankkeita
- Käynnissä olevia hankkeita

Yläpainikkeet:

- Hae uudet hankkeet
- Hakuehdot
- Asetukset

---

## Arvioi hankkeita

Näytä vain:

```text
status = NEW
```

Sarakkeet:

- Nimi
- Hakutunnus
- Lähde
- Haku päättyy
- Soveltuvuuspisteet

Painikkeet:

- Lisätiedot
- Osallistu
- Hylkää

---

## Lisätiedot

Avaa NiceGUI-dialogi.

Näytä:

- otsikko
- hakutunnus
- lähdejärjestelmä
- kuvaus
- hakuaika
- pisteytys
- perustelu

---

## Käynnissä olevat hankkeet

Näytä:

- nimi
- nykyinen vaihe
- vastuuhenkilö
- seuraava tehtävä

---

## Hakuehdot

CRUD-toiminnot:

- lisää
- muokkaa
- poista
- aktivoi
- passivoi

---

# REST API

## Funding Calls

GET

```text
/api/funding-calls
```

GET

```text
/api/funding-calls/{id}
```

PATCH

```text
/api/funding-calls/{id}/status
```

---

## Participation

GET

```text
/api/participations
```

PATCH

```text
/api/participations/{id}
```

---

## Search Profiles

CRUD-endpointit.

---

## Import

POST

```text
/api/imports/run
```

---

# Testit

Toteuta testit:

- EURA importer
- Haeavustuksia importer
- pisteytys
- API
- tietokantamallit

Käytä fixture-dataa.

Älä tee testejä riippuvaisiksi live-palveluista.

---

# Hyväksymiskriteerit

MVP on valmis kun:

- sovellus käynnistyy komennolla

```bash
python main.py
```

- SQLite toimii
- molemmat importerit toimivat
- uusi hanke näkyy arviointijonossa
- hanke voidaan hyväksyä osallistuttavaksi
- hanke voidaan hylätä
- arvioitu hanke poistuu arviointijonosta
- pisteytys toimii
- hakuprofiilit toimivat
- testit menevät läpi

---

# Työskentelyohje agentille

1. Luo projektirakenne.
2. Luo tietokantamallit.
3. Luo migraatiot.
4. Luo importerit.
5. Luo pisteytyslogiikka.
6. Luo REST API.
7. Luo NiceGUI-käyttöliittymä.
8. Kirjoita testit.
9. Korjaa virheet.
10. Päivitä README.

Älä jää suunnittelemaan.

Luo oikeat tiedostot.

Aja testit jokaisen vaiheen jälkeen.

Näytä lopuksi:

- projektirakenne
- luodut tiedostot
- testitulokset
- tunnetut puutteet