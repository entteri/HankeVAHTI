"""Stable field/Word mapping for the supplied EURA example (zero-based indices)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WordTarget:
    table: int
    row: int = 1
    column: int = 0
    paragraph: int = 0
    label_row: int = 0
    label_column: int = 0
    label_paragraph: int = 0
    placeholder: str = "Kirjoita vastaus tähän"
    shape: tuple[int, int] = (2, 1)


@dataclass(frozen=True)
class ApplicationField:
    id: str
    section: str
    label: str
    ai_enabled: bool
    type: str
    word: WordTarget


SECTIONS = {
    "3": "3 Hankkeen perustiedot",
    "3.2": "3.2 Julkinen kuvaus",
    "4.1": "4.1 Hankkeen kohderyhmä, tarve ja tavoitteet",
    "4.2": "4.2 Toteutus ja tulokset",
    "5.2": "5.2 Yhteydet muihin hankkeisiin",
    "5.3": "5.3 Hakijan osaaminen, hankkeen riskiarviointi, ohjausryhmä sekä saavutettavuusnäkökulma",
    "5.4": "5.4 Horisontaaliset periaatteet: EU:n perusoikeuskirja, YK:n vammaisyleissopimus ja sukupuolten tasa-arvo",
    "5.6": "5.6 Kestävä kehitys: Ekologinen kestävyys",
    "5.7": "5.7 Kestävä kehitys: Taloudellinen kestävyys",
    "5.8": "5.8 Kestävä kehitys: Sosiaalinen ja kulttuurinen kestävyys sekä yhdenvertaisuus",
}

_TEXT_FIELDS = (
    ("public_summary", "3.2", 10, "Hankkeen julkinen tiivistelmä"),
    ("english_name", "3.2", 11, "Hankkeen nimi englannin kielellä"),
    ("english_summary", "3.2", 12, "Hankkeen julkinen tiivistelmä englannin kielellä"),
    ("primary_target_groups", "4.1", 16, "Mitkä ovat hankkeen varsinaiset kohderyhmät?"),
    ("secondary_target_groups", "4.1", 17, "Mitkä ovat hankkeen välilliset kohderyhmät?"),
    ("need", "4.1", 18, "Minkä tarpeen tai ongelman hanke ratkaisee?"),
    ("preparation", "4.1", 19, "Miten hanke on valmisteltu? Miten hankkeen kohteena olevia sisältöjä on aiemmin pyritty kehittämään?"),
    ("objectives", "4.1", 20, "Mitkä ovat hankkeen tavoitteet?"),
    ("novelty", "4.1", 21, "Mitä muutosta nykytilaan hanke tuo? Mikä on hankkeen uutuus/lisäarvo?"),
    ("support_effect", "4.1", 22, "Arvioi tuen ensisijainen vaikutus hankkeen toteuttamiseen"),
    ("support_justification", "4.1", 23, "Perustelut tuen vaikutukselle"),
    ("actions", "4.2", 24, "Millä konkreettisilla toimenpiteillä hanke saavuttaa kuvatut tavoitteet?"),
    ("results", "4.2", 25, "Mikä tai mitkä ovat hankkeen konkreettiset tulokset? Mitä hankkeella saadaan aikaan? Miten tulokset voidaan laadullisesti todentaa ja määrällisesti mitata?"),
    ("long_term_impacts", "4.2", 26, "Mitä pitkän aikavälin vaikutuksia hankkeella saadaan aikaan? Miten vaikutukset voidaan laadullisesti todentaa ja määrällisesti mitata?"),
    ("utilisation", "4.2", 27, "Miten tuloksia ja kokemuksia hyödynnetään hankkeen päättymisen jälkeen?"),
    ("continuation", "4.2", 28, "Vaihtoehto suunnitelmaksi toiminnan jatkumisesta hankkeen päättymisen jälkeen"),
    ("public_results", "4.2", 29, "Kuvaa hankkeen yleisesti hyödynnettävät tulokset ja missä ne tulevat olemaan julkisesti saatavilla."),
    ("related_projects", "5.2", 32, "Liittyykö hakemus muihin alue- ja rakennepolitiikan rahastoista tai muista rahoituslähteistä rahoitettaviin hankkeisiin tai hankekokonaisuuksiin?"),
    ("experience", "5.3", 33, "Minkälainen on hakijan osaaminen ja kokemus hankkeiden toteuttamisesta ja hankesuunnitelman mukaisesta sisällöllisestä teemasta?"),
    ("gender_equality", "5.4", 36, "Miten sukupuolten tasa-arvon tavoite on huomioitu hankkeen suunnitelmassa?"),
    ("natural_resources", "5.6", 37, "Luonnonvarojen käytön kestävyys"),
    ("climate_risks", "5.6", 38, "Ilmastonmuutoksen aiheuttamien riskien vähentäminen"),
    ("biodiversity", "5.6", 39, "Kasvillisuus, eliöt ja luonnon monimuotoisuus"),
    ("water_soil_air", "5.6", 40, "Pinta- ja pohjavedet, maaperä sekä ilma (ja kasvihuonekaasujen väheneminen)"),
    ("natura", "5.6", 41, "Natura 2000 -ohjelman kohteet"),
    ("materials", "5.7", 42, "Materiaalit ja jätteet"),
    ("renewable_energy", "5.7", 43, "Uusiutuvien energialähteiden käyttö"),
    ("local_economy", "5.7", 44, "Paikallisen elinkeinorakenteen kestävä kehittäminen"),
    ("intangible_services", "5.7", 45, "Aineettomien tuotteiden ja palvelujen kehittäminen"),
    ("mobility", "5.7", 46, "Liikkuminen ja logistiikka"),
    ("cultural_environment", "5.8", 47, "Kulttuuriympäristö"),
    ("environmental_skills", "5.8", 48, "Ympäristöosaaminen"),
)

APPLICATION_FIELDS = (
    ApplicationField("project_name", "3", "Hankkeen julkinen nimi", False, "text",
                     WordTarget(4, row=0, paragraph=1, placeholder="Täytä tähän", shape=(3, 2))),
    *(ApplicationField(key, section, label, True, "text", WordTarget(table))
      for key, section, table, label in _TEXT_FIELDS),
    # The original risk table has five rows. Each cell is independently editable/AI-assisted.
    *(ApplicationField(f"risk_{row}_{key}", "5.3", label, True, "risk",
                       WordTarget(34, row=row, column=column, label_column=column,
                                  placeholder=" ", shape=(6, 3)))
      for row in range(1, 6)
      for column, key, label in (
          (0, "category", "Riskikategoria"), (1, "risk", "Riski"),
          (2, "mitigation", "Toimenpiteet riskin toteutumisen todennäköisyyden pienentämiseksi"))),
)
FIELDS_BY_ID = {field.id: field for field in APPLICATION_FIELDS}

KNOWN_FIELDS = (
    ApplicationField("call_title", "", "Hankehaun nimi", False, "metadata",
                     WordTarget(0, row=1, paragraph=1, label_row=1, placeholder="Täytä tähän", shape=(2, 2))),
    ApplicationField("call_identifier", "", "Hakuilmoituksen tunnus", False, "metadata",
                     WordTarget(0, row=1, column=1, paragraph=1, label_row=1, label_column=1,
                                placeholder="Täytä tähän", shape=(2, 2))),
)
