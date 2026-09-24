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

## Testit

```powershell
python -m pytest
```

Testit käyttävät erillistä väliaikaista SQLite-tietokantaa eivätkä tarvitse verkkopalveluja.

## Nykyinen rajaus

Pääsivun mittarikortit sekä Hakuehdot- ja Asetukset-painikkeet ovat paikkamerkkejä. Soveltuvuuspisteytys, hakuprofiilien hallinta ja varsinainen hanke-API eivät vielä kuulu tähän vaiheeseen.
