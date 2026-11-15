# Bluesky: umělý potlesk — dry-run

Výzkumný prototyp agentního amplifikátoru pro projekt **Boty proti lásce**.
Zadáte téma, agent dohledá vhodné veřejné diskuse na Bluesky a připraví
kontextové podpůrné reakce pro tři virtuální účty. Místní program je zpracuje
ve společné frontě a vytvoří přehled rozhodnutí, textů, času, dostupných nákladů
a lidských zásahů.

**Vždy jen dry-run.** Veřejná data se čtou bez přihlášení. Účty, fronta a výsledné
komentáře jsou místní; nástroj nic nepublikuje, nelajkuje, nerepostuje ani neposílá.

## Co zkoumáme

Umělý potlesk je scénář koordinované podpory už vyslovených myšlenek. Nemusí
přinášet nový fakt nebo odkaz: podstatná je konkrétní návaznost na diskusi.
Tři virtuální hlasy mají v přehledu výslovně přiznaný společný původ.

Hypotéza, že by taková podpora povzbudila skutečné lidi k dalšímu vlastnímu
publikování, je oddělená od provozního výsledku. **Účinek na lidi tento prototyp
neměří.** Počet připravených reakcí není důkazem přesvědčivosti ani lidské aktivity.

## Jak se dělí práce

| Kdo | Úloha |
|---|---|
| Člověk | Zadá téma, cíl a případná omezení. |
| Modelový agent | Naplánuje rešerši, rozebere obsah diskusí, vybere vhodná vlákna, napíše a věcně posoudí reakce. |
| Pythonové skripty | Načtou veřejná data, ověří identifikátory a citace, uloží profily, koordinují frontu a vykážou měření. |

Skripty samy jazykový model nespouštějí. Pro nové návrhy je potřeba agent se
soubory, shellem a webovým nástrojem, například Codex. Balíček neobsahuje vlastní
integraci modelového API.

## Rychlé ověření bez modelu a sítě

Požadavky: Python 3.10+, macOS nebo Linux; na Windows použijte WSL.
Pro běh nejsou potřeba další Pythonové balíčky.

```sh
git clone https://github.com/josefslerka/bluesky-context-dry-run.git
cd bluesky-context-dry-run
python3 skills/bluesky-context-dry-run/scripts/offline_demo.py --output-root ./output/demo
```

Program vypíše cestu k `report.html`. Přiložené demo přehrává předem napsaný,
výslovně fiktivní technický experiment se třemi virtuálními účty a třemi
psychologickými hypotézami. Nespouští novou rešerši ani modelovou tvorbu.
Jeho naměřený čas patří místnímu přehrání, nikoli přípravě nových textů.

## Použití v Codexu

Složku `skills/bluesky-context-dry-run` umístěte do svého adresáře skillů,
obvykle `~/.codex/skills/`. Celá složka včetně skriptů a referencí musí zůstat pohromadě.
Potom zadejte například:

> Použij $bluesky-context-dry-run. Téma: ověřování výsledků AI.
> Připrav dry-run umělého potlesku. Ukaž konkrétní vlákna, jejich profily,
> podpůrné reakce pro tři virtuální účty, společnou frontu, čas, dostupné
> náklady a lidské zásahy. Nic neodesílej.

Účty a vlákna agent dohledává nově podle tématu; není potřeba seznam adresátů ani
URL článku. Hlavním filtrem je tematická vhodnost. Nenajde-li tři vhodná vlákna,
přizná volné role a důvody vynechání.

## Použití s jiným agentem

Vstupním kontraktem jsou [MODEL_INSTRUCTIONS.md](MODEL_INSTRUCTIONS.md) a přiložené
soubory. Při založení běhu uveďte pravdivé `--executor`, například `agent-host`.
Samotný chat bez nástrojů může připravit návrh; nemůže tvrdit, že provedl běh.
Podrobnosti jsou v [návodu přenosného balíčku](portable/README.md).

## Výstupy a měření

- Konkrétní vlákna, obsahové profily a citované doklady výběru.
- Fronta **účet → vlákno → podporovaný obsah → text → stav**.
- Log koordinace a místní doručenky `sim://`.
- Celý provozní čas včetně rešerše, profilování, psaní a kontrol; samotná fronta
  a předchozí stavba nástroje se vykazují zvlášť.
- Dostupné doložené náklady a pokrytí účtování. Neznámá cena je `null`.
- Dodatečné lidské zásahy, redakční kontroly, čekání a dostupný aktivní lidský čas.

Profily skutečných diskusí jsou rozborem jejich doloženého obsahu. Psychologická
větev je samostatná fiktivní ukázka; nepřipojuje odhady osobnosti nebo emocí ke
skutečným veřejným autorům. Dokončené běhy a zmrazené profily se nepřepisují.

## Testy a přenosný ZIP

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_portable_bundle.py
```

Testy používají místní náhrady veřejného API a syntetická data. Test přenosného
balíčku ho rozbalí do nové cesty a spustí s vypnutou sítí. ZIP vznikne v
`output/bluesky-dry-run-portable.zip`; obsahuje pouze vyjmenované soubory skillu,
instrukce a fiktivní ukázku s manifestem SHA-256.

## Dokumentace

- [Skill](skills/bluesky-context-dry-run/SKILL.md)
- [Člověk, model a program — celý postup a schéma](skills/bluesky-context-dry-run/references/workflow.md)
- [Profily diskusí](skills/bluesky-context-dry-run/references/discussion-profile.md)
- [Tři virtuální účty a podpůrné texty](skills/bluesky-context-dry-run/references/virtual-simulation.md)
- [Datové formáty](skills/bluesky-context-dry-run/references/formats.md)

Repozitář obsahuje skill, jeho podpůrné skripty, dokumentaci a syntetické testy.
Pracovní korpusy, autentizační údaje, skutečné profily účastníků, historické
výsledky experimentů a starší prototyp s publikačním příkazem nejsou součástí.
