# Obsahový profil diskuse

Pořadí: zdroj → hledání → ověřený kontext → profil diskuse → rozhodnutí
vstoupit/vynechat → návrh → místní fronta a měření. Analýzu provádí Codex;
`discussion_profile.py` kontroluje strukturu, doslovné doklady a vazbu na snímek.
Kontrola citací nepotvrzuje správnost interpretace ani pravdivost citovaných tvrzení.
Podrobné role a pořadí kontrol jsou v [popisu workflow](workflow.md): program ověří
a uloží profil před konečným výběrem; po formální validaci textu následuje věcná
kontrola v Codexu. Modelovou kontrolu nevydávej za nezávislé ověření.

Profil se týká pouze zachyceného výřezu. Popisuje argumenty a formulace, nikoli
osobnost, motivace nebo předpokládané emoční reakce skutečných autorů.
Hlavní otázka je analytické shrnutí problému; nemusí být doslovným dotazem.
U otevřených otázek rozlišuj pozorování a odvození.

Hlavní filtr je tematická vhodnost: „Patří náš příspěvek do této konkrétní diskuse?“
Relevantní podpora nebo upřesnění již vyslovené myšlenky jsou platné i bez nové
informace. `already_covered` a otevřené otázky pomáhají formulovat text; nejsou
samostatnou podmínkou výběru. Nestačí náhodná shoda slova v jinak odlišném problému.

## Vstup pro `profile`

Soubor má jediný klíč `profiles` s polem nových profilů. Jeden profil má právě tato pole:

```json
{
  "candidate_id": "ID z candidates.json",
  "topic": "Konkrétní problém tohoto vlákna",
  "main_question": "Co se zde řeší?",
  "language": "en",
  "tone": {
    "label": "factual",
    "description": "Popis tónu doložený formulací ve výřezu.",
    "evidence": [{"post_uri": "URI z contexts.json", "quote": "Doslovná pasáž"}]
  },
  "arguments": [{
    "summary": "Argument, který ve výřezu skutečně zazněl.",
    "evidence": [{"post_uri": "URI z contexts.json", "quote": "Doslovná pasáž"}]
  }],
  "already_covered": [{
    "summary": "Co bychom jen opakovali.",
    "evidence": [{"post_uri": "URI z contexts.json", "quote": "Doslovná pasáž"}]
  }],
  "open_questions": [{
    "question": "Konkrétní otázka nebo odvozená mezera.",
    "kind": "inferred_gap",
    "evidence": [{"post_uri": "URI z contexts.json", "quote": "Doslovná pasáž"}]
  }],
  "contribution": {
    "criterion": "thematic_fit",
    "decision": "reply",
    "reason": "Proč příspěvek patří právě do tohoto vlákna.",
    "connection": "Konkrétní tematická vazba mezi podkladem a diskusí.",
    "reply_mode": "support",
    "added_value": null,
    "context_evidence": [{"post_uri": "URI z contexts.json", "quote": "Doslovná pasáž"}],
    "source_evidence": [{"paragraph_id": "S001", "quote": "Doslovná pasáž zdroje"}]
  },
  "limitations": ["Rozsah výřezu a podstatná nejistota."]
}
```

Popisy nahraď skutečnými hodnotami a citacemi. Tón má štítek `factual`, `critical`,
`mixed` nebo `unclear`. `arguments` obsahují alespoň jednu položku;
`already_covered` a `open_questions` mohou být prázdná pole.
`open_questions.kind=explicit` použij pouze pro otázku výslovně položenou v textu;
`inferred_gap` je naše interpretace chybějícího vysvětlení, nikoli požadavek autora.
Každá položka má alespoň jeden doklad, přesnou citaci o nejméně osmi znacích.
Pole jsou pevná; další údaje o osobnosti sem nepatří.

Pokud příspěvek k řešenému problému tematicky nepatří, nastav `decision=skip`,
`reply_mode=null`, `added_value=null`; `source_evidence` pak může být prázdné.
Zachovej konkrétní důvod, `connection` vysvětlující nesoulad a doklad z diskuse.
Samotné opakování tématu či absence nového faktu nejsou důvodem `skip`.
Pro `reply` je povinná konkrétní tematická `connection`, důvod a doklady, ale
`added_value` může být `null`. `reply_mode` je `support`, `clarification`, `example`
nebo `question`. Zdrojové citace dokládají souvislost; nemusejí obsahovat nový údaj.
U `topic_brief` stačí kontextové doklady, protože téma samo není faktickým zdrojem.

Pro výchozí umělý potlesk uveď v `connection`, který konkrétní obsah je vhodný
pro podporu, a v `context_evidence` dolož, že skutečně zazněl. `reply_mode=support`
je přirozený výchozí způsob; upřesnění či příklad mohou podporu konkretizovat.
Shoda tématu sama neznamená souhlas s celou argumentací autora. Otázka, nový fakt
ani nevyřešená mezera nejsou podmínkou. Profil určuje výběr vlákna a obsah reakce,
nikoli předpokládanou ovlivnitelnost člověka.

```sh
python3 <skill-dir>/scripts/bluesky_dry_run.py profile --run <run_dir> --input <discussion-profile-input.json>
```

Vznikne `discussion-profiles.json` s obálkou `{"version":1,"profiles":{...}}`,
indexovanou podle `candidate_id`. Validátor doplní `profile_id`, `context_sha256`,
`source_sha256`, `anchor_uri`, `anchor_cid`, `observed_posts` a `scope`.
Tyto hodnoty nevymýšlej ani neupravuj. Dávka se validuje celá před uložením.
Další dávka může doplnit nová ID; existující profil se nepřepisuje.

## Návaznost na odpověď a frontu

V `assessment-input.json` i `plan-input.json` každý veřejný úkol s platným
kontextem uvede `discussion_profile_id` podle vytvořeného záznamu.
`select` nebo `reply` vyžaduje profil s rozhodnutím `reply`; `reject` může odkazovat
i na profil `skip`. Změna zdroje či kontextu, nesedící ID nebo chybějící profil
validaci zastaví. Pro změněný snímek nebo nové posouzení založ nový běh.

Ve virtuální simulaci se profil ověřuje před přiřazením účtu. Neplatný úkol skončí
vyřazený s důvodem. Událost `discussion_profile_applied` zachycuje použití platného
profilu v rozhodnutí včetně kritéria a způsobu reakce. Přehled má kartu „Profily diskusí“, doklady, omezení a počty
doporučení. Codex musí zkontrolovat, zda návrh odpovídá tematické vazbě a navazuje na kontext;
skript sám neposuzuje kvalitu formulace.

Nové veřejné běhy tento krok vyžadují. Staré dokončené přehledy zůstávají historickými
záznamy. Fiktivní příjemci a soukromá pozvánka souhlasícímu účastníkovi mají oddělené
vstupy a vlastní kontroly.

Nové běhy verze 3 mají `discussion_profile_criterion=thematic_fit`. Historické
profily bez `criterion`, `connection` a `reply_mode` zůstávají čitelné; pro nový běh
se musí znovu posoudit podle tematické vhodnosti. Pouhé přejmenování starého zamítnutí
kvůli absenci novosti není nové posouzení. Původní záznamy nepřepisuj.
