# HankeVAHTI

Yhden käyttäjän paikallinen sovellus rahoitushankkeiden seurantaan. Tämä ensimmäinen vaihe sisältää tietokantamallit, migraation, FastAPI-rungon, NiceGUI-pääsivun ja health endpointin. Tuonti, pisteytys ja hakuprofiilien toiminnot tulevat seuraavissa vaiheissa.

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

## Testit

```powershell
python -m pytest
```

Testit käyttävät erillistä väliaikaista SQLite-tietokantaa eivätkä tarvitse verkkopalveluja.

## Ensimmäisen vaiheen rajaus

Pääsivun painikkeet ja mittarikortit ovat paikkamerkkejä. Importerit, soveltuvuuspisteytys, hakuprofiilien hallinta ja varsinainen hanke-API eivät vielä kuulu tähän vaiheeseen.
