# HankeVAHTI

Yhden käyttäjän paikallinen sovellus rahoitushankkeiden seurantaan. Sovellus sisältää tietokantamallit, migraation, FastAPI-rungon, NiceGUI-pääsivun sekä EURA- ja Haeavustuksia-importerit. Pisteytys ja hakuprofiilien toiminnot tulevat seuraavissa vaiheissa.

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

**Hakuehdot**-sivulla voi tallentaa EURA-hakuilmoituksille rahaston, haun kohdealueen, viranomaisen, maakunnat ja hakutunnuksen. Valintojen nimet ja koodit haetaan EURA:n koodistosta sivun avaamisen yhteydessä. Oletuksena tuodaan vain avoimet ESR+-haut. Tallennetut ehdot vaikuttavat seuraaviin EURA-tuonteihin; jo tallennettuja hankkeita tai niiden arvioita ei poisteta. EURA-hankkeen **Lisätiedot**-ikkunassa oleva linkki avaa yksittäisen hakuilmoituksen UUID-tunnisteella.

REST-rajapinnassa hankkeet löytyvät reiteistä `GET /api/funding-calls`, `GET /api/funding-calls/{id}` ja päätös tallennetaan reitillä `PATCH /api/funding-calls/{id}/status` käyttäen esimerkiksi JSON-runkoa `{"status":"PARTICIPATE"}` tai `{"status":"REJECTED"}`.

## Testit

```powershell
python -m pytest
```

Testit käyttävät erillistä väliaikaista SQLite-tietokantaa eivätkä tarvitse verkkopalveluja.

## Nykyinen rajaus

Asetukset-painike on vielä paikkamerkki. Toteutuskunnan rajaus, soveltuvuuspisteytys, yleisten hakuprofiilien hallinta ja osallistumisen vaiheiden muokkaus tulevat myöhemmin.
