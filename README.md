# HankeVAHTI

Yhden käyttäjän paikallinen sovellus rahoitushankkeiden seurantaan. Sovellus sisältää tietokantamallit, migraatiot, FastAPI-rungon, NiceGUI-käyttöliittymän, EURA- ja Haeavustuksia-importerit sekä sääntöpohjaisen relevanssipisteytyksen käyttäjän omilla hakusanoilla.

## Käynnistys

Vaatii Python 3.12:n tai uudemman.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m alembic upgrade head
python main.py
```

Selain: <http://localhost:8080>. Health endpoint: <http://localhost:8080/health>.

Tietokanta sijaitsee oletuksena tiedostossa `data/hankevahti.db`. Sovellus ei luo tauluja käynnistyessään; tee tai päivitä taulut Alembicilla. Yhteyden voi vaihtaa `DATABASE_URL`-ympäristömuuttujalla. Paikallinen `.env` luetaan automaattisesti.

Pääsivun **Hae uudet hankkeet** -painike tai `POST /api/imports/run` hakee molemmat lähteet. Tuonti käsittelee Haeavustuksia-palvelun kaikki sivut, tuo EURAsta vain haettavissa olevat ESR+-haut ja päivittää muuttuneet lähdetiedot. Uudelle haulle luodaan `NEW`-arvio; aiempaa arviota tai osallistumistietoja ei muuteta. Molemmat lähteet tallennetaan yhdessä transaktiossa, joten virhe ei jätä osittaista tuontia.

## Mahdolliset duplikaatit

Etusivun **Mahdolliset duplikaatit** avaa EURA- ja Haeavustuksia.fi-hakujen mahdolliset vastinparit. Etusivu näyttää parien lukumäärän, ja hankelistassa molemmat ilmoitukset saavat **Mahdollinen duplikaatti** -merkinnän. Lisätiedoissa ja duplikaattisivulla näkyy vertailun peruste sekä linkki toiseen alkuperäiseen ilmoitukseen.

Tunnistus vertaa eri lähteiden hakuja. Pari näytetään, kun normalisoidut hakutunnukset ovat samat tai nimet ovat hyvin samankaltaiset ja tiedossa olevat hakuajat eroavat enintään seitsemän päivää. Lyhyitä nimiä ei hyväksytä pelkän nimivertailun perusteella. Tulos on tarkistettava ehdotus: samankaltainen nimi ja hakuaika eivät todista, että kyseessä on sama haku. Tunnistus toimii myös jo tallennetuille hauille ilman uutta tuontia. Se ei yhdistä tai poista ilmoituksia eikä muuta arvioita tai osallistumistietoja.

Tuonnin jälkeen pääsivun **Kaikki hankkeet** avaa selattavan ja haettavan listan. **Arvioi hankkeita** näyttää `NEW`-tilaiset haut. Hankkeen **Lisätiedot** avaa kuvauksen ja hakuajan, ja **Osallistu** tai **Hylkää** tallentaa päätöksen. Osallistuttavat ja hylätyt hankkeet löytyvät omista näkymistään. Osallistumispäätökselle luodaan myös osallistumisrivi, joka näkyy **Käynnissä olevat** -näkymässä. Jos tuonti ei löydä uusia hankkeita, käyttöliittymä kertoo sen ja näyttää erikseen päivitettyjen määrän.

**Hakuehdot**-sivulla voi tallentaa EURA-hakuilmoituksille rahaston, haun kohdealueen, viranomaisen, maakunnat ja hakutunnuksen. Valintojen nimet ja koodit haetaan EURA:n koodistosta sivun avaamisen yhteydessä. Oletuksena tuodaan vain avoimet ESR+-haut. Haeavustuksia.fi-hakuilmoituksille voi valita avustuslajin, tulevat ja käynnissä olevat haut sekä valtionapuviranomaisen. Kummallakin lähteellä on oma tallennuspainike ja hakuehdot vaikuttavat seuraaviin tuonteihin; aiemmin tallennettuja hankkeita tai niiden arvioita ei poisteta. Sivulla näytetään voimassa olevat hakuehdot, ja tuonnin ilmoitus kertoo uusien hankkeiden määrän lähteittäin. EURA-hankkeen **Lisätiedot**-ikkunassa oleva linkki avaa yksittäisen hakuilmoituksen UUID-tunnisteella.

Haeavustuksia-hankkeen **Lisätiedot**-ikkunassa lähdelinkki avaa kyseisen haun osoitteessa `https://www.haeavustuksia.fi/fi/haku/{asianumero}`.

**Asetukset**-sivulla voi tyhjentää kaikki haetut hankkeet ja aloittaa tuonnin alusta. Painike avaa vahvistusikkunan. Tyhjennys poistaa myös hankkeiden arviot ja osallistumistiedot pysyvästi, mutta säilyttää tallennetut hakuehdot.

**Lisätiedot → Muodosta AI-soveltuvuusarvio** arvioi rahoitushaun soveltuvuutta Suomen eOppimiskeskus ry:lle jo ennen osallistumispäätöstä. Myös **Osallistuttavat**-näkymän **AI-soveltuvuusarvio** -painike säilyy. Molemmat käyttävät projektin juuressa olevien UTF-8-tiedostojen `organisaatioprofiili.md` ja `ai-summary-prompt.md` koko sisältöä. Tiedostot luetaan jokaisella pyynnöllä projektin sijainnista riippumatta; puuttuva tai tyhjä tiedosto estää pyynnön ja näyttää virheilmoituksen. `asiakas.md` ja `arviointikriteerit.md` säilyvät, mutta niitä ei enää välitetä yhteenvetoon.

Yhteenveto käsittelee sopivuutta, rajoituksia, itsenäistä hakijuutta ja kumppanuutta, mahdollisia rahoituslinjoja, kokonaisarviota, haun tilaa, lisäselvityksiä ja lähdettä. Pyyntö sisältää tallennetun haun tiedot, lähdelinkin ja arviointipäivän Helsingin ajassa. Alkuperäistä hakusivua ei lueta eikä puuttuvia ehtoja täydennetä verkkohakuna. Vastauksen oikeellisuus on tarkistettava alkuperäisestä ilmoituksesta.

AI-soveltuvuusarvio ja hakemustekstin muotoilu käyttävät oletuksena Geminiä (`AI_PROVIDER=gemini`) ja nykyisiä `GEMINI_API_KEY`- ja `GEMINI_MODEL`-asetuksia. OpenAI on edelleen valittavissa asetuksella `AI_PROVIDER=openai`, jolloin käytetään `OPENAI_API_KEY`- ja `OPENAI_MODEL`-asetuksia. Virhetilanteessa palvelua ei vaihdeta automaattisesti. Yhteenveto tallennetaan nykyiseen tietokantakenttään; pisteytys, osallistumispäätös ja osallistumistiedot säilyvät. Uusi onnistunut yhteenveto korvaa vanhan. Epäonnistunut pyyntö säilyttää aiemman yhteenvedon. Lisätiedot-ikkuna näyttää pitkän vastauksen kokonaan vieritettävänä tekstinä. Tämä päivitys ei vaadi uutta tietokantamigraatiota.

Gemini-kokeilua varten täytä paikallisen `.env`-tiedoston `GEMINI_API_KEY` ja `GEMINI_MODEL`. Aseta tarvittaessa `AI_PROVIDER=gemini` ja käynnistä sovellus uudelleen. Mallin nimi tulee omista asetuksistasi; sovellus ei valitse Gemini-mallia automaattisesti. Älä kopioi oikeaa avainta README:hen tai `.env.example`-tiedostoon. Uusia riippuvuuksia tai tietokantamigraatioita ei tarvita.

Paikallinen tarkistus:

1. Käynnistä sovellus projektikansiossa: `.\.venv\Scripts\python.exe main.py`.
2. Avaa `http://localhost:8080` ja **Arvioi hankkeita → Lisätiedot**. Pelkkä ikkunan avaaminen ei lähetä tekoälypyyntöä.
3. **Muodosta AI-soveltuvuusarvio** lähettää oikean pyynnön valitulle AI-palvelulle omalla API-avaimellasi. Paina sitä vain, kun haluat käyttää palvelua.
4. Tarkista vastauksen otsikot, perustelut, haun tila ja lähde. Varmista, että haku pysyy arvioimattomana ja sen pisteet säilyvät.
5. Sulje ja avaa Lisätiedot uudelleen: tallennetun vastauksen pitäisi näkyä. Tarkista myös nykyinen yhteenvetopainike Osallistuttavat-näkymässä.

Automaattiset testit eivät kutsu oikeaa tekoälypalvelua: `.\.venv\Scripts\python.exe -m pytest tests/test_ai_summary.py -q`.

## Hankehakemustekstin muotoilu

**Lisätiedot → Muotoile hakemustekstiä** avaa yksittäisen hakemusosion muotoilun. Kirjoita osion kysymys tai otsikko, liitä oma luonnos ja anna tarvittaessa rahoittajan arviointikriteerit sekä positiivinen kokonaisluku merkkimäärärajaksi. Tyhjä merkkiraja tarkoittaa, ettei rajaa ole annettu.

**Muotoile teksti** lähettää syötteet ja tallennetun rahoitushaun tiedot valitulle AI-palvelulle (oletuksena Google Gemini). Toiminto lukee jokaisella pyynnöllä `organisaatioprofiili.md`- ja `hakemusteksti-prompt.md`-tiedostojen koko sisällön. Gemini käyttää `GEMINI_API_KEY`- ja `GEMINI_MODEL`-asetuksia. OpenAI-vaihtoehto käyttää `OPENAI_API_KEY`- ja `OPENAI_MODEL`-asetuksia. Alkuperäistä hakusivua ei lueta. Työohjeet ovat erillään käyttäjän luonnoksesta ja rahoitushaun aineistosta. Vastauksen siirtoa varten pyydetään JSON-muoto (Geminillä JSON-skeema): kopioitava teksti ja mahdolliset lisätietokysymykset erikseen. Sovellus näyttää promptin tarkoittamat teksti- ja merkkimääräosiot käyttöliittymässä.

Tuloksesta lasketaan merkit ohjelmassa, välilyönnit, välimerkit ja rivinvaihdot mukaan lukien. Otsikot ja lisätietokysymykset eivät kuulu laskentaan. Ylitys näytetään merkkien määränä, eikä tekstiä katkaista tai lyhennetä automaattisesti. **Kopioi valmis teksti** kopioi vain hakemustekstin. Tarvittaessa voit myös valita tekstin tuloskentästä ja kopioida sen Ctrl+C:llä. Tarkista tosiasiat ja rahoittajan oma merkkilaskenta ennen käyttöä.

Tallennettua AI-soveltuvuusarviota ei välitetä automaattisesti muotoiluun. Tekstiä ei tallenneta tietokantaan. Kopioi tulos talteen ennen ikkunan sulkemista. Epäonnistunut uusi pyyntö säilyttää ikkunassa edellisen tuloksen; tulos kuuluu edelliseen onnistuneeseen pyyntöön. Puuttuvat asiakirjat, avain, virheellinen merkkiraja, verkkovirheet ja käyttökelvottomat vastaukset näytetään virheilmoituksina. AI-ohjeet kieltävät tietojen keksimisen, mutta ohjelma ei voi varmistaa kaikkien vastausten asiasisältöä automaattisesti.

### Käyttöliittymän tarkistus ilman API-avainta

Avaa uusi PowerShell-terminaali projektikansiossa. Voit estää paikallisen `.env`-avaimen käyttämisen tässä käynnistyksessä asettamalla prosessin avainarvoksi yhden välilyönnin (tiedostoa ei muuteta):

```powershell
$env:AI_PROVIDER = 'gemini'
$env:GEMINI_API_KEY = ' '
.\.venv\Scripts\python.exe main.py
```

Avaa `http://localhost:8080`, valitse rahoitushaun **Lisätiedot → Muotoile hakemustekstiä** ja täytä kysymys sekä luonnos. Paina **Muotoile teksti**: näet ilmoituksen puuttuvasta API-avaimesta, eikä Gemini-pyyntöä tehdä. Merkkirajaksi esimerkiksi `-1` näyttää syötteen tarkistusvirheen. Pelkkä ikkunan avaaminen ei tee kutsua. Ilman avainta ei voi saada aitoa muotoilutulosta; tulos-, ylitys- ja kopiointikäyttäytyminen testataan automaattisesti korvatuilla vastauksilla. Sulje tämä terminaali tarkistuksen jälkeen ja käytä tavalliseen käynnistykseen uutta terminaalia.

Muotoilun automaattiset testit: `.\.venv\Scripts\python.exe -m pytest tests/test_application_text.py -q`. Ne eivät tee oikeita API-kutsuja.


REST-rajapinnassa hankkeet löytyvät reiteistä `GET /api/funding-calls`, `GET /api/funding-calls/{id}` ja päätös tallennetaan reitillä `PATCH /api/funding-calls/{id}/status` käyttäen esimerkiksi JSON-runkoa `{"status":"PARTICIPATE"}` tai `{"status":"REJECTED"}`.

Hankelistojen **Lajittelu**-valinnasta voi valita **Relevanssi: suurin ensin**, **Relevanssi: pienin ensin**, **Deadline: lähin ensin**, **Deadline: kaukaisin ensin**, **Hylkäyspäivä: uusin ensin**, **Hylkäyspäivä: vanhin ensin** tai **Oletusjärjestys**. Puuttuvat pisteet tai päivämäärät tulevat kyseisessä lajittelussa loppuun molemmissa suunnissa. Oletusjärjestys säilyy entisenä: viimeksi tuodut ensin. Lajittelu koskee koko suodatettua tulosjoukkoa ennen sivutusta; valinnan vaihtaminen palauttaa ensimmäiselle sivulle. Se ei muuta tallennettuja tietoja. API:ssa vastaavat `sort`-arvot ovat `relevance_desc`, `relevance_asc`, `deadline_asc`, `deadline_desc`, `rejected_at_desc`, `rejected_at_asc` ja `default`.

**Hylkää** tallentaa päätöksen ajankohdan UTC:ssa. Hylätyn hankkeen kortti ja Lisätiedot näyttävät päivämäärän ja kellonajan Helsingin ajassa. **Arvioimatta** tai muu tilanvaihto pois hylätystä poistaa aikaleiman; uusi hylkäys saa uuden ajan. Toistettu hylkäys säilyttää aiemman ajan. Vanhoille hylkäyksille, joiden aikaa ei ole tallennettu, näytetään **Hylätty: Ei tiedossa**.

## Relevanssin hakusanat ja pisteytys

1. Avaa **Asetukset → Relevanssin hakusanat**.
2. Kirjoita kiinnostavat hakusanat ja poissulkusanat omiin kenttiinsä, yksi sana tai ilmaus riville. Esimerkiksi `tekoäly`, `koulutus` ja `osaamisen kehittäminen`. Voit muokata sanoja tai poistaa ne tyhjentämällä rivin.
3. Paina **Tallenna hakusanat**. Ylimääräiset välilyönnit, tyhjät rivit ja saman sanan toistot siivotaan. Hakusanat ovat yhteiset molemmille tietolähteille.
4. Paina **Pisteytä päättymättömät haut**. Toiminto käsittelee kaikki tietokannassa olevat haut, joiden päättymispäivä on tänään tai myöhemmin, sekä haut ilman päättymispäivää. Myös tulevat haut ovat mukana. Päivämäärä määräytyy Helsingin aikavyöhykkeessä.
5. Avaa **Näytä hankkeet → Lisätiedot**. Listassa näkyvät pisteet ja relevanssiluokka. Lisätiedoissa näkyvät tallennetun pisteytyksen hakusanaosumat, poissulkevat osumat ja laskentasääntö.

Pisteytys lukee nimen, kuvauksen, rahaston ja kategorian. Kukin eri kiinnostava hakusana antaa **20 pistettä**, positiivinen summa rajataan **100 pisteeseen**, ja sen jälkeen kukin eri poissulkusana vähentää **20 pistettä**. Lopputulos on vähintään **0**. Esimerkiksi neljä hakusanaosumaa ja yksi poissulkeva osuma antaa 60 pistettä. Sama sana useasti tekstissä antaa pisteet vain kerran. Jos sana on molemmilla listoilla, se lasketaan molempiin. Ilman osumia tai tyhjillä listoilla tulos on 0; vielä pisteyttämätön haku näytetään erikseen.

| Pisteet | Luokka |
|---|---|
| 80–100 | Hyvin relevantti |
| 60–79 | Mahdollisesti relevantti |
| 30–59 | Tarkistettava |
| 0–29 | Todennäköisesti ei relevantti |

Vertailu tunnistaa kokonaiset sanat ja ilmaukset kirjainkoosta riippumatta. Ääkköset ja ilmauksen sisäiset välilyönnit/rivinvaihdot huomioidaan. Esimerkiksi `AI` ei osu sanaan `taidot`. Suomen taivutusmuotoja tai synonyymejä ei tunnisteta: `koulutus` ei osu sanaan `koulutuksen`. Lisää tarvittavat muodot erillisille riveille. Tulos on yksinkertainen suositus, eikä se käytä kielimallia tai ulkoista analyysipalvelua.

**Pisteytys ei poista hakuja eikä muuta Osallistu/Hylkää-päätöksiä tai osallistumistietoja.** Hakusanojen tallennus ja tuonti eivät automaattisesti pisteytä hakuja. Aja pisteytys uudelleen tuonnin tai hakusanojen muuttamisen jälkeen. Vanhat pisteet ja niiden perustelut säilyvät siihen asti. **Pisteytä kaikki haut** päivittää myös päättyneiden hakujen pisteet, perustelut ja osumat nykyisillä tallennetuilla hakusanoilla. Uudelleenanalyysi korvaa edellisen pistemäärän ja perustelun, erillistä analyysihistoriaa ei tallenneta.

MVP käyttää yhtä `SearchProfile`-riviä nimeltä `HankeVAHTI: relevanssi`. Muut mahdolliset profiilit säilyvät ennallaan eikä niitä yhdistetä tähän pisteytykseen. Pisteiden ja perustelun lisäksi viimeisimmän pisteytyksen osumat tallennetaan `Evaluation.matched_keywords`- ja `matched_excluded_keywords`-kenttiin. Lisätiedot näyttää listat erikseen ja lihavoi kuvauksessa esiintyvät positiiviset hakusanaosumat. Korostus käyttää tallennettua pisteytystä, joten hakusanojen muuttaminen vaikuttaa siihen vasta uudelleenpisteytyksessä. Pelkkä sivun avaaminen ei luo profiilia tai pisteytä hakuja.

Hylkäysajan ja rakenteisten osumien käyttöönotto vaatii migraation **0006_evaluation_decisions_matches**. Ota nykyisestä tietokannasta varmuuskopio sovelluksen ollessa suljettuna ja suorita `python -m alembic upgrade head` ennen päivitetyn sovelluksen käynnistämistä. Vanhojen arvioiden uudet kentät jäävät tyhjiksi. Paina **Asetukset → Pisteytä kaikki haut**, jotta myös vanhojen päättyneiden hakujen osumat tallentuvat. Tallentamattomat osumat erotetaan pisteytetystä tyhjästä listasta (**Ei osumia**). Migraation downgrade poistaa vain kolme uutta kenttää ja niiden tiedot.

Pisteytys on erillisessä `app/services/relevance.py`-palvelussa. `score_funding_calls(session)` käsittelee kaikki päättymättömät haut; valinnainen `call_ids` rajaa ajon esimerkiksi uusiin tai muuttuneisiin hakuihin. `include_ended=True` ottaa myös päättyneet haut mukaan. Importerien nykyistä toimintaa ei ole muutettu. Pistepainot ja luokkarajat ovat keskitetysti tiedostossa `app/evaluators/relevance.py`.

## Gemini-asetukset

Gemini-yhteys käyttää [Googlen virallista google-genai SDK:ta](https://googleapis.github.io/python-genai/). Asenna riippuvuudet nykyiseen virtuaaliympäristöön:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Lisää olemassa olevaan paikalliseen `.env`-tiedostoon nämä rivit ja täytä niiden arvot:
**ÄLÄ TALLENNA API-AVAINTA MISSÄÄN NIMESSÄ TÄNNE GIT:tiin**

```dotenv
GEMINI_API_KEY=
GEMINI_MODEL=
```

API-avaimen voi luoda Google AI Studiossa [Googlen avainohjeen](https://ai.google.dev/gemini-api/docs/api-key) mukaan. Aseta `GEMINI_MODEL`-arvoksi tililläsi käytettävissä olevan tekstimallin tarkka tunniste [Googlen malliluettelosta](https://ai.google.dev/gemini-api/docs/models); mallin tulee tukea `generate_content`-kutsua. Sovelluksessa ei ole oletusmallia. Älä korvaa olemassa olevaa `.env`-tiedostoa mallipohjalla, jotta muut paikalliset asetukset säilyvät. `.env` on Gitin ohituslistalla, ja avain pysyy palvelinpuolella.

Käynnistä sovellus asetusten muuttamisen jälkeen uudelleen:

```powershell
.\.venv\Scripts\python.exe main.py
```

Avaa `http://localhost:8080` ja valitse **Lisätiedot → Muodosta AI-soveltuvuusarvio** tai **Muotoile hakemustekstiä**. Pelkkä Lisätiedot-ikkunan avaaminen ei lähetä AI-pyyntöä. Puuttuva avain tai malli sekä verkkovirheet, aikakatkaisu, käyttöraja, API-virhe ja tyhjä vastaus näytetään suomeksi; muu HankeVAHTI toimii ilman avainta. Gemini-pyynnön aikakatkaisu on 60 sekuntia, eikä kutsua toisteta automaattisesti.

Soveltuvuusarvio tallentuu hankkeelle. Muotoiltu hakemusteksti on kopioitava erikseen talteen. Mallin vastaus on tarkistettava alkuperäisestä hakuilmoituksesta. Vastaukset näytetään tavallisena tekstinä, eikä niiden sisältämää HTML:ää suoriteta.

## Testit

```powershell
python -m pytest
```

Tietokantatestit, etusivutesti ja käyttöliittymätestit käyttävät erillistä väliaikaista SQLite-tietokantaa eivätkä tarvitse verkkopalveluja. Migraation upgrade ja downgrade testataan väliaikaisessa kannassa; omaa tietokantaa ei tarvitse päivittää testisarjan ajamista varten.

Relevanssitestit voi ajaa erikseen:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_relevance.py tests/test_relevance_ui.py -q
```

Gemini-testit käyttävät mockattua SDK-clientiä ja väliaikaista tietokantaa. Ne eivät kutsu oikeaa Gemini API:a eivätkä tarvitse oikeaa avainta:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_gemini.py -q
```

## Nykyinen rajaus

- Toteutuskunnan rajaus, yleisten hakuprofiilien hallinta ja osallistumisen vaiheiden laajempi muokkaus ei mahdollista tässä
- Nykyisessä MVP-versiossa ovat käytettävissä hakusanat ja poissulkusanat, sääntöpohjainen relevanssipisteytys, pisteisiin ja deadlineen perustuva lajittelu sekä AI-soveltuvuusarvio ja hakemustekstin muotoilu
- Relevanssipisteytys käynnistetään tällä hetkellä käsin eikä analyysihistoriaa tallenneta. Käytössä on yksi yhteinen hakusanaprofiili johon AI ei tee mitään
- Geminin käyttö vaatii käyttäjän oman Gemini API -avaimen paikalliseen `.env`-tiedostoon. **API-AVAINTA EI TALLENNETA VERSIONHALLINTAAN**
