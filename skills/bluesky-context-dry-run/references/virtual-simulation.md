# Téma → umělý potlesk → tři virtuální účty

Codex zajišťuje rešerši, posouzení relevance a skutečné autorské návrhy. Místní
`scripts/virtual_amplifier.py` provádí koordinaci a export. Nemá síťového klienta,
nečte hesla, nevolá modelové API a nemá přepínač k publikaci. Vstupem je téma,
výstupem jsou věcné podpůrné komentáře bez připojené URL. Toto je výchozí režim
skillu; tři účty a společná fronta se připraví i bez dalšího upřesnění uživatele.
Scénář ukazuje společně řízenou podporu konkrétních příspěvků. Předpokládané
povzbuzení autorů k dalšímu vlastnímu publikování zůstává neměřenou hypotézou.
V jiném prostředí může modelovou práci dodat jeho agent; při `start` uveď
`--executor <označení-prostředí>`. Postup je v
[přenositelných instrukcích](model-instructions.md). Výchozí označení je `codex`.
Rozdělení rolí, operacionalizace cíle, kontroly a zachování historie jsou popsány
v [Člověk, model a program](workflow.md). G a W vykonává Codex a zaznamenává je
událostí `model_stage`; samotný simulátor kvůli nim model nespouští.

## Začátek a rešerše

Založ simulaci před přípravou textů, aby její nástěnný čas zahrnoval přípravu:

```sh
python3 <skill-dir>/scripts/virtual_amplifier.py start --topic "<téma>"
```

Pro měření stavby nástroje či další předchozí práce lze předat `--session-log`
s doloženou skutečnou značkou `task_started_at`. Značku zpětně nevymýšlej. Samotný
průchod frontou má samostatný čas; jeho milisekundy nejsou cenou ani dobou rešerše.

Pro nové zadání vytvoř oddělený čtecí běh a dohledej účty od nuly podle tématu:

```sh
python3 <skill-dir>/scripts/bluesky_dry_run.py start-topic "<téma>"
```

Podle hlavního postupu dohledej účty a příspěvky, připrav `discovery-input.json`,
spusť `collect`, `context` a potom `profile` podle
[profilu diskuse](discussion-profile.md). Profil a rozhodnutí o tematické vhodnosti vznikají
před texty. U tématu není třeba URL ani příkaz `source`. Výběr
nositelů zakládej na konkrétním příspěvku, ne na odhadovaných vlastnostech člověka.
Rešerše a psaní probíhají v Codexu, nikoli uvnitř samostatného simulátoru.

Zadaný účel „umělý potlesk“ ulož při operacionalizaci cíle do skutečné události
`model_stage` s `stage=goal_operationalization`. Popiš podporovanou myšlenku,
provozní výsledek a hypotézu o další lidské aktivitě odděleně. Téma samo nestačí
k předpokladu, že všichni nalezení autoři zastávají stejný názor. Najdi doložený
obsah vhodný pro podporu; při nejasném či nepodloženém tvrzení nepiš automatický souhlas.

Při uživatelem požadovaném opakování nad posledním článkem lze použít jeho uložený
čtecí běh. Přiznej stáří snímku a opětovné použití; nevydávej je za nové hledání.
Čtecí adresář musí obsahovat `source.json`, `candidates.json`, `contexts.json`.
Pro nový veřejný simulační běh je povinný také `discussion-profiles.json`:
pokud ve starší rešerši chybí, připrav nový čtecí běh s přiznaným archivním importem
a doplň profily nad ním. Dokončený původní běh nepřepisuj.
Nový běh vyžaduje profily s `criterion=thematic_fit`; starší výběr podle novosti
znovu posuď. Relevantní podporu nevyřazuj pouze proto, že nepřináší nový fakt.
Snímek `topic_brief` není důkazem faktů. Při použití čerstvé rešerše uveď zvlášť
její GET a modelovou práci; nulová síťová aktivita lokálního simulátoru je nevynuluje.

## Plán a role

Tři přiznané identity jsou `virtual:V1` (konkrétní údaje, cs/en), `virtual:V2`
(rozlišení a upřesnění, cs/en), `virtual:V3` (vysvětlení, cs/en/es). Každá má v jednom
kole kapacitu na jeden komentář. Nepřidávej nevhodný cíl jen kvůli zaplnění účtů.

## Jak psát podpůrné reakce

- U každého návrhu dolož, **co přesně podporuje**: tvrzení, rozlišení, vysvětlení
  nebo otázku z ověřeného výřezu. `support_basis` tuto návaznost výslovně pojmenuje.
- Reaguj na konkrétní formulaci a argument, jazyk a tón diskuse. Obecné „souhlasím“
  či „skvělý příspěvek“ nenahrazuje kontextovou reakci. Nová informace se nevyžaduje.
- V1 může ocenit konkrétní práci s údaji, V2 podpořit důležité rozlišení a V3
  srozumitelně rozvést vysvětlení. Jde o různé funkce podpory, ne tři kopie textu.
  Nepřidávej povinně otázku nebo polemiku tam, kde cílem je podpora.
- Podporu vztahuj k doloženému obsahu, nikoli automaticky k celé osobě či všem jejím
  názorům. Zachovej význam a nejistoty; nevymýšlej osobní zkušenost, vztah s autorem
  ani další nezávislé podporovatele. Původ BotyLab AI zůstává v místních textech přiznaný.
- Odlišení tří hlasů vzniká z role a kontextu vlákna. Odhad osobnosti, emocí nebo
  ovlivnitelnosti skutečného autora do této veřejné větve nepatří. Fiktivní
  psychologický experiment se spouští pouze jako samostatně zadaná větev.

## Příprava plánu

Vytvoř místní `plan-input.json`. Tvar jednoho skutečně vyplněného úkolu:

```json
{
  "topic": "Stejné téma jako při startu",
  "intent": "support_factual_contribution",
  "jobs": [{
    "candidate_id": "ID z čtecího běhu",
    "discussion_profile_id": "profile_id příslušné diskuse",
    "decision": "reply",
    "role": "data",
    "language": "en",
    "reason": "Proč toto místo dává smysl.",
    "support_basis": "Na který konkrétní obsah diskuse podpůrný text navazuje.",
    "draft_body": "Vlastní podpůrný text bez URL, prefix přidá simulátor.",
    "context_evidence": [{"post_uri": "URI z ověřeného kontextu", "quote": "Doslovná existující pasáž"}],
    "source_evidence": []
  }],
  "synthetic_reactions": [],
  "limitations": ["Skutečná omezení tohoto výběru a interpretace."]
}
```

Použij skutečná ID a přesné citace; příkladové popisy validací neprojdou.
`intent=support_factual_contribution` je programové označení plánu i pro scénář
umělého potlesku; nepřejmenovávej ho ani nepřidávej neexistující publikační režim.
`role`: `data`, `clarification`, `explanation`. `reply_to_uri` lze zadat jen z
ověřeného výřezu; jinak se cílí na nalezený příspěvek. Pokud text přidává fakta
z článku, přidej `source_evidence` s `paragraph_id` a přesnou citací. Jinak musí
věcná opora být v samotném cílovém kontextu. Prefix a text mají nejvýše 300 znaků.

Každý veřejný úkol odkazuje na svůj zmrazený profil. Validace ověří jeho citace,
otisky kontextu a zdroje i rozhodnutí před přidělením účtu. `skip` zablokuje odpověď;
chybějící nebo zastaralý profil úkol vyřadí. Log obsahuje `discussion_profile_applied`.
Obsahový rozbor a doklady jsou v kartě „Profily diskusí“ a samostatném JSON.

Pro odmítnutý úkol stačí známé `candidate_id`, `discussion_profile_id`, `decision=reject`, `reason`;
žádný text odpovědi. Další úkol ve stejném vlákně zablokuje fronta. Nadbytečný
platný úkol může zůstat pozastavený pro nedostupnou roli nebo vyčerpanou kapacitu.

```sh
python3 <skill-dir>/scripts/virtual_amplifier.py load --run <sim-dir> --research <read-dir> --input <plan-input.json>
python3 <skill-dir>/scripts/virtual_amplifier.py run --run <sim-dir>
```

Frontu skutečně obsluhují tři místní pracovníci. SQLite transakce zajišťují vlastnictví
úkolu, jednu rezervaci vlákna a idempotentní místní doručenku `sim://...`. Ilustrativní
časy 10/20/30 s nejsou měřením rychlosti sítě. Po přerušeném běhu se stav kontroluje
příkazem `status`; automatické pokračování po nejasném výsledku není implementováno.

Volitelné `synthetic_reactions` mají `job_id`, `kind=like|reply|repost`,
`actor=virtual:V1|virtual:V2|virtual:V3|synthetic:<jméno>`. Jde výhradně o místní
testovací scénář; nikdy je nevydávej za pozorované reakce ani nezávislý dosah.
Vlastní síť se vykazuje odděleně od syntetických externích aktérů. Bez potřeby
testovat toto počítání ponech prázdné pole.

## Měření a výstup

Příkaz `event --run <sim-dir> --input <event.json>` přijímá skutečné události
`human_request`, `human_response`, `human_correction`, `human_review`, `usage`, `note`, `model_stage`.
Požadavek vrátí `event_seq`, odpověď jej uvede jako `request_id`. Čekání se měří
odděleně. Aktivní lidské sekundy vyžadují skutečný čas a `time_basis=user_reported`
nebo `timed_editor_session`. Modelová kontrola návrhů není redakční kontrola člověkem.
Usage vyžaduje `provider`, `measurement_source`, případně číselné `cost_usd`,
`input_tokens`, `output_tokens`. Chybějící údaje jsou null. Úplné účtování potvrď
`run --usage-complete` jen pro doložený celý běh.

Výstupy: interaktivní `report.html`, `report.json`, `queue.json`, `queue.csv`,
`coordination.jsonl`, `local-posts.json`, `queue.sqlite3`; importované podklady jsou
v `research.json` s otisky. Dokončený běh se nepřepisuje. Přehled ukazuje skutečné
pořadí koordinace i přehrávání ilustrativního času.
Výstup `discussion-profiles.json` uchovává obsahové profily importované veřejné rešerše.
Oddělené větve fiktivních příjemců a soukromé technické pozvánky tento veřejný krok
nevyžadují a zachovávají svá vlastní pravidla.

Uživateli vždy ukaž:

1. Téma, účel „umělý potlesk“ a samostatně označenou hypotézu o účinku na lidi.
2. Profily diskusí, konkrétní odkazy a důvod tematické vhodnosti i vynechání.
3. Společnou frontu **účet → vlákno → podporovaný obsah → přesný text → stav**,
   včetně neobsazených účtů a blokací. Dolož, jak profil ovlivnil výběr a formulaci.
4. Skutečný čas od založení simulace před rešerší do dokončení přehledu; zvlášť
   čtecí běh, místní zpracování fronty a případnou předchozí stavbu nástroje.
5. Dostupné doložené náklady a pokrytí účtování; nezjištěná cena není nula.
6. Dodatečné lidské zásahy, redakční kontroly, čekání a dostupný aktivní lidský čas.
7. Záznam koordinace, původ podkladů a počet skutečných veřejných zápisů: nula.

Celý provozní čas zahrnuje rešerši, profilování, tvorbu, opravy a kontrolu přehledu;
případné dokončovací kroky po `run` vykazuj zvlášť vedle času v `report.json`.
Náklady a lidskou práci z čtecího běhu také zahrň nebo zvlášť přiznej jejich
nedostupnost. Stejnou událost nepočítej dvakrát, pokud je ve více protokolech.
Nulové síťové požadavky simulátoru neznamenají, že veřejná čtečka nic nenačítala.
Uveď, zda znovu proběhla rešerše, a že skutečný
účinek nebyl měřen. Nezaměň sdílení tématu za automatický souhlas s celou argumentací
autora. Pro politická témata zachovej věcné vysvětlení; nevytvářej osobně cílené
politické přesvědčování podle názorů nalezených lidí.
Případné externí studie uveď jako samostatnou oporu výzkumné hypotézy, nikdy jako
naměřený účinek tohoto běhu. Syntetickou odezvu nelze vykázat jako lidské publikování.

## Fiktivní psychologické hypotézy

Tato větev zkouší formulaci pro vymyšlené příjemce. Neodvozuje skutečnou osobnost,
motivace ani emoce reálných autorů a nepropojuje hypotézy s veřejnými účty.
Vytvoř nový adresář čtecího podkladu se stejnými třemi povinnými soubory. Článek
může zůstat faktickým zdrojem, ale všechny cílové příspěvky jsou nové fiktivní texty.

V `candidates.json` nastav `context_origin=synthetic`. Každý příspěvek kontextu má
`origin=synthetic`, `uri` a `root_uri` začínající `sim://`, `cid` začínající
`synthetic:`, `url=null`, `author_did=handle=synthetic:persona:<ID>`. Nezaměň ani
nepřejmenovávej skutečné autory za fiktivní; příjemce i kontext nově vymysli.

Úkol vedle běžných polí nese:

```json
{
  "psychological_profile": {
    "kind": "fictional_hypothesis",
    "id": "synthetic:persona:A",
    "motivation": "Výslovně vymyšlená motivace příjemce.",
    "anticipated_emotion": "Výslovně vymyšlená reakce v situaci.",
    "formulation_strategy": "Jakou konkrétní změnu formulace hypotéza předepisuje.",
    "empirical_support": null
  },
  "baseline_draft_body": "Výchozí text bez připojené URL.",
  "adaptation_trace": [{
    "field": "motivation",
    "before": "Doslovná pasáž výchozího textu",
    "after": "Doslovná pasáž pole draft_body",
    "reason": "Stručná deklarovaná vazba mezi hypotézou a formulací."
  }]
}
```

`draft_body` je skutečná upravená formulace. Povolené `field` jsou `motivation`,
`anticipated_emotion`, `formulation_strategy`. Stopa musí odpovídat oběma textům,
text se musí skutečně změnit a číselné údaje musí zůstat stejné. Kontrola čísel
nenahrazuje významovou kontrolu obou variant. Nejsou podporovány profily obsahující
odkazy na skutečné lidi, tvrzení o empirické opodstatněnosti nebo spojení s reálnými
příspěvky; takové úkoly skončí jako vyřazené.

Pro názorný pokus použij stejnou vymyšlenou otázku a stejný výchozí text ve všech
podmínkách. Uveď, že stejné autorské prostředí i deklarovaná stopa změn nejsou
zaslepený test ani kauzální důkaz vlivu profilu. Účinek na čtenáře se bez skutečného
měření nevykazuje. V přehledu se objeví karta „Fiktivní psychologické profily“
s motivací, předpokládanou emocí, výchozím textem, upraveným textem a změnami.

## Oslovení souhlasícího účastníka

Tato samostatná větev připravuje jednu místní nepolitickou pozvánku k technickému
experimentu s AI amplifikátory. Počítá s předchozím výslovným souhlasem účastníka
s vlastním rozborem a s ukázkou oslovení. Uživatelův souhlas z probíhajícího chatu
zachovej; nevyžaduj jej znovu. Nejde o profilování nositelů veřejných politických
témat. Cílem je místní zadání `sim://local-participant-invitations/...`, nikdy
skutečný veřejný příspěvek.

Codex připraví pracovní kvalitativní odhad a jeho doklady z vlastních veřejných
textů. Rozlišuj pozorování, interpretaci a to, co se z dat odhadnout nedá. Nepřidávej
numerická skóre ani jistotu, která nebyla měřena. Pokud odhad již existuje, lze jej
znovu použít s uvedeným obdobím vzorku. Tento příkaz neprovádí novou rešerši nebo
novou modelovou inferenci.

Vstupy pro `invite`:

- `--profile`: JSON s `participant`, `validated=false`, `corpus` (`posts`, `date_from`,
  `date_to`), `interpretations` a `evidence`.
- `--posts`: JSON s `participant_did` a vlastními záznamy `posts`, každý s `id`, `uri`,
  `cid`, `date`, `url`, `text`. URI všech záznamů musí patřit tomuto účastníkovi.
- `--consent`: JSON s `scope=private_nonpolitical_technical_invitation`,
  `participant_name`, `participant_handle`, `participant_did`, `salutation`,
  `profile_permission_quote`, `invitation_permission_quote`. Citace musí odpovídat
  skutečnému zadání či vyjádření účastníka; program sám jeho identitu neověřuje.

Z odhadu se používá jen doložená `open_mindedness` s neprázdným `estimate` a alespoň
dvěma jedinečnými `evidence_ids`. Uvedené texty, data i URL se musí shodovat s korpusem.
Ostatní dimenze se do formulace nepřenášejí. Volitelná `confirmed_preference` v souhlasu
má `pattern=testable_experiment` a skutečnou citaci `quote` ze zpětné vazby účastníka.
Přímá preference se nevydává za důkaz osobnostního rysu.

```sh
python3 <skill-dir>/scripts/virtual_amplifier.py start --topic "Technická pozvánka"
python3 <skill-dir>/scripts/virtual_amplifier.py invite --run <sim-dir> --profile <estimate.json> --posts <posts.json> --consent <consent.json>
python3 <skill-dir>/scripts/virtual_amplifier.py run --run <sim-dir>
```

`participant_invitation.py` vybírá mezi neutrální pozvánkou a schváleným vzorem
„co tu tezi vystavit testu“. Doklady z odhadu nebo potvrzená preference aktivují druhou
variantu; bez obojího zůstane neutrální. V této verzi je obsah pevně omezen na technické
porovnání jednoho a tří účtů. Jde o deterministický výběr formulace, nikoli automatické
vytvoření či validaci osobnostního profilu.

Vznikne jeden úkol pro V3; ostatní účty zůstanou nečinné. Přehled má kartu „Oslovení
účastníka“, která ukazuje použitou hypotézu, přímou preferenci, doklady, stáří vzorku,
neutrální variantu a zvolený text. Souhlas i podklady jsou uloženy místně. Validace
odmítne jiné příjemce, chybějící souhlas, nesedící doklady, libovolný jiný text a pokus
připojit pozvánku k veřejnému příspěvku. Účinek na příjemce zůstává neměřený.
