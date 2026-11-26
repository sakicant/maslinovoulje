# Olive oil site (Šakić, Piramatovci)

Read README.md first. The original planning brief is the source of truth for facts and claims.

## Conventions

- Static site from `python build.py` (stdlib only) + small PHP scripts for orders. Same approach as the owner's taxi sites.
- Never hand-edit `dist/`.
- Prices, stock and shipping live only in `data/*.json`. Never hard-code them in templates or JS.
- Totals are calculated only in PHP (`php/private/lib.php`, function `quote`). The browser sends ids, quantities, country, delivery.
- Text lives in `lang/<code>.toml`. Use `[[...]]` for anything still OPEN; it shows as a yellow note.
- Staging until the owner says otherwise: `staging = true` keeps noindex and robots Disallow.

## Content rules (non-negotiable)

- Only the harvest facts from the brief. Mark anything else as a placeholder.
- Banned until cleared: extra virgin, variety names (Oblica), cold pressed / cold extraction, organic / bio / untreated, place name in the product name. `build.py` checks rendered pages.
- No em dashes in any language.
- The owner answers in English and Croatian only. Never claim German support.
- No invented reviews, awards, press, statistics. No stock photos. No tracking scripts or third-party embeds.
- Mobile first: check every change at 375 px.

## Git

Descriptive commit messages explaining why. Remind the owner about uncommitted changes.
