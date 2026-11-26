# Šakić olive oil website (working title)

Small direct-to-consumer site for the family olive oil from Piramatovci, near Skradin.
Order **requests** only: no payment on the site. The owner sends payment details by email.

**Status: staging. Not public, not indexed.** `staging = true` in `config/site.toml`.

## Build

```
python build.py
```

Python 3.11+ only, no packages. Output goes to `dist/`. Upload the contents of `dist/` by FTP (binary mode).
Never edit files in `dist/`; they are overwritten.

## Where things live

| What | File |
|---|---|
| Brand name, tagline, domain, contact, staging switch, category wording ("olive oil") | `config/site.toml` |
| Bottles, prices, stock, sets | `data/products.json` |
| Shipping zones and parcel prices (PLACEHOLDERS) | `data/shipping.json` |
| Photo slots (grey placeholders until real photos exist) | `data/photos.json` |
| All text, per language, incl. the 3 email templates | `lang/en.toml`, `lang/de.toml`, `lang/hr.toml` |
| Page layouts | `templates/` |
| CSS, JS, images, fonts | `static/` (served as `/assets/`) |
| Order API, admin, mail, database | `php/` |

Croatian is served at the site root; English and German under `/en/` and `/de/`.

To add a language: copy `lang/en.toml` to `lang/xx.toml`, translate, add `"xx"` to `languages.order` in `config/site.toml`, add country names in `data/countries.json`.

## How an order works

1. Cart lives in the browser (localStorage). It stores only item ids and quantities.
2. `api/quote.php` calculates bottles, shipping and total on the server from `products.json` and `shipping.json`.
3. `api/order.php` re-calculates, checks spam protection (honeypot, signed timing token, rate limit), saves to SQLite, emails the customer ("order request received, nothing charged") and the owner.
4. Owner opens `/admin/`, sends the payment request (template filled in, copy or open in mail app), later sets status, invoice and tracking number and sends the shipped email.

Order statuses: `new`, `payment_requested`, `paid`, `shipped`, `cancelled`.
Payment fields (`payment_method`, `payment_provider_ref`, `paid_at`) are separate so a real checkout can be added later.

## Server setup (once)

1. Upload `dist/`.
2. Copy `private/config.sample.php` to `private/config.php` on the server and fill it in (secret, emails, admin password hash).
   Best: point `data_dir` to a folder outside the web root.
3. Check `https://DOMAIN/private/config.php` returns 403.
4. Rename the admin folder (`admin.dir` in `config/site.toml`) to something not guessable before launch.

## Local testing

- Put a `config.php` in the project root (gitignored) with `'mail_mode' => 'log'`. `build.py` copies it to `dist/private/`.
- Run PHP's built-in server with SQLite enabled:
  `php -d extension_dir=<php>/ext -d extension=pdo_sqlite -d extension=mbstring -S localhost:8091 -t dist`
- Emails are written to `dist/private/storage/mail.log`.

## Vercel preview

`vercel.json` runs `python3 build.py` and serves `dist/`. Vercel cannot run PHP, so on Vercel the
order API, admin and private data are left out: pages and design can be checked there, but the cart
shows "total could not be calculated". Test ordering on the local PHP server or on the real hosting.

## Fonts

Self-hosted only. See `static/fonts/README.txt`. Until the files are added, Georgia and system fonts are used.

## Rules (from the brief)

- No "extra virgin", no variety name, no "cold pressed", no "organic/bio", no "Skradin olive oil" as a product name. `build.py` fails if any of these reach a page.
- No em dashes.
- No invented reviews, awards, statistics. No stock photos. No tracking scripts.
- Owner answers in English and Croatian only.

## Launch checklist

- [ ] Brand, tagline, domain final (`config/site.toml`)
- [ ] Real shipping prices (`data/shipping.json`, set `placeholder` false and remove the note in the lang files)
- [ ] Final stock (`data/products.json`) and harvest totals (`config/site.toml`)
- [ ] Legal pages written (business registered)
- [ ] Base prices are ON with a placeholder date (26 Nov 2026): set `pricing.base_price_date` in `config/site.toml` to the launch day
- [ ] Machine-readable price list (`pricing.cjenik_file`) once the business is registered
- [ ] Lab analysis done, then category wording updated
- [ ] Real photos in `static/img/`, paths in `data/photos.json`
- [ ] `staging = false`, rebuild, upload
