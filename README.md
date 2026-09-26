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

Tuonnin jälkeen pääsivun **Kaikki hankkeet** avaa selattavan ja haettavan listan. **Arvioi hankkeita** näyttää `NEW`-tilaiset haut. Hankkeen **Lisätiedot** avaa kuvauksen ja hakuajan, ja **Osallistu** tai **Hylkää** tallentaa päätöksen. Osallistuttavat ja hylätyt hankkeet löytyvät omista näkymistään. Osallistumispäätökselle luodaan myös osallistumisrivi, joka näkyy **Käynnissä olevat** -näkymässä. Jos tuonti ei löydä uusia hankkeita, käyttöliittymä kertoo sen ja näyttää erikseen päivitettyjen määrän.

**Hakuehdot**-sivulla voi tallentaa EURA-hakuilmoituksille rahaston, haun kohdealueen, viranomaisen, maakunnat ja hakutunnuksen. Valintojen nimet ja koodit haetaan EURA:n koodistosta sivun avaamisen yhteydessä. Oletuksena tuodaan vain avoimet ESR+-haut. Haeavustuksia.fi-hakuilmoituksille voi valita avustuslajin, tulevat ja käynnissä olevat haut sekä valtionapuviranomaisen. Kummallakin lähteellä on oma tallennuspainike ja hakuehdot vaikuttavat seuraaviin tuonteihin; aiemmin tallennettuja hankkeita tai niiden arvioita ei poisteta. Sivulla näytetään voimassa olevat hakuehdot, ja tuonnin ilmoitus kertoo uusien hankkeiden määrän lähteittäin. EURA-hankkeen **Lisätiedot**-ikkunassa oleva linkki avaa yksittäisen hakuilmoituksen UUID-tunnisteella.

Haeavustuksia-hankkeen **Lisätiedot**-ikkunassa lähdelinkki avaa kyseisen haun osoitteessa `https://www.haeavustuksia.fi/fi/haku/{asianumero}`.

**Asetukset**-sivulla voi tyhjentää kaikki haetut hankkeet ja aloittaa tuonnin alusta. Painike avaa vahvistusikkunan. Tyhjennys poistaa myös hankkeiden arviot ja osallistumistiedot pysyvästi, mutta säilyttää tallennetut hakuehdot.

REST-rajapinnassa hankkeet löytyvät reiteistä `GET /api/funding-calls`, `GET /api/funding-calls/{id}` ja päätös tallennetaan reitillä `PATCH /api/funding-calls/{id}/status` käyttäen esimerkiksi JSON-runkoa `{"status":"PARTICIPATE"}` tai `{"status":"REJECTED"}`.

Hankelistojen **Lajittelu**-valinnasta voi valita **Relevanssi: suurin ensin**, **Relevanssi: pienin ensin**, **Deadline: lähin ensin** tai **Oletusjärjestys**. Relevanssilajittelussa pisteyttämättömät haut tulevat loppuun molemmissa suunnissa. Deadline-lajittelussa päivämäärät järjestetään aikaisimmasta alkaen ja puuttuvat päivämäärät viimeiseksi. Oletusjärjestys säilyy entisenä: viimeksi tuodut ensin. Lajittelu koskee koko suodatettua tulosjoukkoa ennen sivutusta; valinnan vaihtaminen palauttaa ensimmäiselle sivulle. Se ei muuta tallennettuja tietoja. API:ssa vastaavat `sort`-arvot ovat `relevance_desc`, `relevance_asc`, `deadline_asc` ja `default`.

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

**Pisteytys ei poista hakuja eikä muuta Osallistu/Hylkää-päätöksiä tai osallistumistietoja.** Hakusanojen tallennus ja tuonti eivät automaattisesti pisteytä hakuja. Aja pisteytys uudelleen tuonnin tai hakusanojen muuttamisen jälkeen. Vanhat pisteet ja niiden perustelut säilyvät siihen asti; jo päättyneiden hakujen pisteitä ei päivitetä. Uudelleenanalyysi korvaa edellisen pistemäärän ja perustelun, erillistä analyysihistoriaa ei tallenneta.

MVP käyttää yhtä `SearchProfile`-riviä nimeltä `HankeVAHTI: relevanssi`. Muut mahdolliset profiilit säilyvät ennallaan eikä niitä yhdistetä tähän pisteytykseen. Tulos tallennetaan olemassa oleviin `Evaluation.suitability_score`- ja `suitability_summary`-kenttiin, joten ominaisuus ei vaadi uutta migraatiota. Pelkkä sivun avaaminen ei luo profiilia tai pisteytä hakuja.

Pisteytys on erillisessä `app/services/relevance.py`-palvelussa. `score_funding_calls(session)` käsittelee kaikki päättymättömät haut; valinnainen `call_ids` rajaa ajon esimerkiksi uusiin tai muuttuneisiin hakuihin. Importerien nykyistä toimintaa ei ole muutettu. Pistepainot ja luokkarajat ovat keskitetysti tiedostossa `app/evaluators/relevance.py`.

## Gemini AI -sparraaja (prototyyppi)

Yksittäisen haun **Lisätiedot → AI-sparraaja** avaa dialogin, jossa voit kirjoittaa oman kysymyksen tai käyttää toimintoja **Analysoi rahoitushaku**, **Ehdota hankeideaa**, **Mitä pitää tarkistaa?** ja **Arvioi soveltuvuutta**. Valmis toimintopainike lähettää kysymyksen suoraan; oma kysymys lähetetään **Lähetä**-painikkeella. Pelkkä dialogin avaaminen ei tee Gemini-kutsua

Sparraaja käyttää [Googlen virallista google-genai SDK:ta](https://googleapis.github.io/python-genai/). Asenna riippuvuudet nykyiseen virtuaaliympäristöön:

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

Avaa `http://localhost:8080`, valitse haku ja avaa **Lisätiedot → AI-sparraaja**. Jos avain tai mallin nimi puuttuu, dialogi näyttää suomenkielisen ohjeen; muu HankeVAHTI toimii normaalisti. Verkkovirhe, aikakatkaisu, käyttöraja, API-virhe ja tyhjä vastaus käsitellään dialogissa. Lähetyspainikkeet ovat pois käytöstä pyynnön ajan. HTTP-pyynnön aikakatkaisuksi on asetettu 60 sekuntia, eikä kutsua toisteta automaattisesti.

Gemini saa vain käyttäjän kysymyksen sekä haun nimen, kuvauksen, lähteen, rahaston, kategorian, hakuajan, relevanssipisteet ja pisteytyksen perustelun. `raw_data`, osallistumisen muistiinpanot, vastuuhenkilö ja seuraava tehtävä eivät kuulu kontekstiin. Nykyisessä mallissa ei ole erillistä rahoittajakenttää, joten lähdepalvelua ei esitetä varmistettuna rahoittajana. TARKISTA ETTEI BILLING OLE AKTIIVINEN ETTEI KÄY VAHINKO JA MENE MAKSETTUJA TOKENEITA

Ohjeistus pyytää Geminiä toimimaan Suomen eOppimiskeskuksen hankesuunnittelun sparraajana, erottamaan annetut faktat omista ehdotuksista, tunnistamaan puuttuvat tiedot ja jättämään päätökset ihmiselle. Mallin vastaus ei silti ole varmennettu tieto. Vastaukset näytetään tavallisena tekstinä, eikä niiden sisältämiä komentoja tai HTML:ää suoriteta.

Prototyyppi käsittelee jokaisen kysymyksen itsenäisesti: aiempia kysymyksiä ja vastauksia ei välitetä seuraavaan pyyntöön. Uusi lähetys korvaa dialogissa näkyvän vastauksen. HankeVAHTI ei tallenna keskustelua tietokantaan. Dialogin sulkeminen ei peru jo lähetettyä pyyntöä. Sparraaja käyttää listan avaamisen yhteydessä luettuja hakutietoja eikä nouda lähdesivuja tai muuta pisteitä, päätöksiä tai muita tietokantatietoja. **ILMAISESSA EI HIRVEÄSTI VAIHTOEHTOJA**

## Testit

```powershell
python -m pytest
```

Tietokantatestit käyttävät erillistä väliaikaista SQLite-tietokantaa eivätkä tarvitse verkkopalveluja. Nykyinen `test_app.py`-tiedoston etusivutesti lukee kuitenkin sovelluksen normaalia tietokantaa, joten käynnistysohjeen migraatiot tulee suorittaa ennen koko testisarjaa. Uudet relevanssi- ja käyttöliittymätestit käyttävät väliaikaista kantaa.

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
- Nykyisessä MVP-versiossa ovat käytettävissä hakusanat ja poissulkusanat, sääntöpohjainen relevanssipisteytys, pisteisiin ja deadlineen perustuva lajittelu sekä Gemini AI -sparraajan prototyyppi
- Relevanssipisteytys käynnistetään tällä hetkellä käsin eikä analyysihistoriaa tallenneta. Käytössä on yksi yhteinen hakusanaprofiili johon AI ei tee mitään
- Gemini AI -sparraaja vaatii käyttäjän oman Gemini API -avaimen paikalliseen `.env`-tiedostoon. **API-AVAINTA EI TALLENNETA VERSIONHALLINTAAN**
