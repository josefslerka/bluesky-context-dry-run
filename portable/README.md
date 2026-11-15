# Přenosný balíček Bluesky dry-runu

Balíček obsahuje instrukce pro modelového agenta a standardní Pythonové skripty
pro čtení, validaci a místní simulaci. Výchozí režim je umělý potlesk: ze zadaného
tématu agent dohledá vhodné diskuse a připraví věcné podpůrné reakce pro tři virtuální
účty se společnou frontou. Vykazuje celý provozní čas, dostupné náklady a lidské
zásahy. Samostatně lze zadat ukázku s vymyšlenými psychologickými hypotézami.
Neobsahuje publikační konektor, přihlašovací údaje ani historické osobní datasety.

## Co použít podle prostředí

| Prostředí | Vstupní soubor |
|---|---|
| Agent podporující formát skillů | `skills/bluesky-context-dry-run/SKILL.md` a celá jeho složka |
| Jiný modelový agent se soubory, shellem a webovým nástrojem | `MODEL_INSTRUCTIONS.md` a přiložené soubory |
| Samotný chat bez shellu | `MODEL_INSTRUCTIONS.md`; lze připravit návrhy, nikoli tvrdit, že skripty běžely |
| Samotné modelové API bez nástrojového hostitele | Je potřeba vlastní adaptér pro volání modelu, předávání podkladů a spouštění CLI |

Skript není jazykový model. Rešeršní rozhodnutí, profily a texty vytváří agent
hostitelského prostředí. Tento ZIP neobsahuje integraci konkrétního modelového API.
Přihlašovací údaje poskytovatele modelu se případně nastavují v jeho vlastním
hostiteli; čtecí klient Bluesky ani místní simulátor je nevyžadují.

## Rychlé ověření po rozbalení

Požadavky: Python 3.10+ a macOS nebo Linux. Na Windows použijte WSL;
čtecí část používá unixové souborové zámky. Další Pythonové balíčky nejsou potřeba.
Nová tvorba pomocí modelu navíc vyžaduje hostitelského agenta.

Z kořene rozbalené složky spusťte:

```sh
python3 skills/bluesky-context-dry-run/scripts/offline_demo.py --output-root ./output/demo
```

Program vypíše cestu k `report.html`. Přehrává předpřipravené fiktivní texty:
tři virtuální účty, společný výchozí text, tři hypotézy a stopu změn.
Nepotřebuje síť ani API klíč a nespouští novou modelovou inferenci.
Měřený čas patří tomuto přehrání; neměří tvorbu nových návrhů.

Demo má v metadatech `model_executor=recorded-fixture`. Účinek na lidi se neměří.
Parametr desetiminutového testu v textu je součástí scénáře, nikoli doba běhu dema.

## Nový běh s jiným agentem

Dejte agentovi `MODEL_INSTRUCTIONS.md`, složku skillu a běžné zadání, například:

> Téma: ověřování výsledků AI. Připrav dry-run umělého potlesku. Od nuly dohledej
> vhodné diskuse na Bluesky, vytvoř doložené profily a podpůrné reakce pro tři
> virtuální účty. Ukaž společnou frontu, přesné texty a log koordinace.
> Změř celý provozní čas, dostupné náklady a lidské zásahy. Nic neodesílej.

Samotné téma stačí; URL ani předem vybrané účty se nevyžadují. Nový fakt není
podmínkou podpory. Návrhy navazují na konkrétní ověřený obsah vláken a vznikají bez
připojené URL. Hypotéza, že by podpora povzbudila další vlastní aktivitu skutečných
autorů, se uvádí odděleně od změřené provozní náročnosti; účinek na lidi se neměří.

Pro fikci lze zadat:

> Vymysli tři nové fiktivní příjemce pro nepolitický technický test. Zachovej
> stejnou otázku, výchozí text a fakta. Ukaž hypotézy a změny formulace a spusť
> místní simulaci. Nepoužívej skutečné účty.

Agent určí `<skill-dir>` podle umístění souborů a při založení běhu uvede
`--executor agent-host` nebo jiné pravdivé označení svého prostředí.
Štítek není ověřeným poskytovatelem ani dokladem API účtování.

Průběh, formáty a úplné schéma jsou ve složce `references`. Výsledky vznikají
v uživatelem zvoleném výstupním adresáři. Opravený běh může odkazovat na rodiče;
hotové běhy a uložené profily se nepřepisují.

## Obsah a kontrola balíčku

- `MODEL_INSTRUCTIONS.md`: přenositelný postup pro modelového agenta.
- `skills/bluesky-context-dry-run/`: skill, schéma, formáty, validátory a simulátor.
- `bundle-manifest.json`: seznam souborů a jejich SHA-256 otisky.

Balíček obsahuje pouze vyjmenované soubory skillu a fiktivní ukázku. Nemá
`.env`, relace prohlížeče, uživatelské korpusy, předchozí výsledky ani starší
prototyp s publikačním příkazem. Rozbalený balíček lze použít i z jiné pracovní
složky; výstupní adresář předejte pomocí `--output-root`.
