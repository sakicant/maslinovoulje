"""Static site build.

    python build.py

Reads   config/site.toml, data/*.json, lang/*.toml, templates/, static/, php/
Writes  dist/   (upload the contents of dist/ by FTP, in binary mode)

Never hand-edit files in dist/. They are overwritten on every build.
No third-party packages: standard library only (Python 3.11+ for tomllib).
"""
import hashlib
import html
import json
import os
import re
import shutil
import sys
import tomllib
from datetime import date

ROOT = os.path.dirname(os.path.abspath(__file__))
# Vercel is only a design preview: it cannot run PHP, so the order API, admin and
# private data are left out there. The real site (FTP to PHP hosting) gets everything.
ON_VERCEL = bool(os.environ.get("VERCEL"))
DIST = os.path.join(ROOT, "dist")
TEMPLATES = os.path.join(ROOT, "templates")

# page id -> template. Slugs and text live in lang/<code>.toml under [pages.<id>].
PAGES = [
    ("home", "home"),
    ("shop", "shop"),
    ("story", "story"),
    ("harvest", "harvest"),
    ("taste", "taste"),
    ("waitlist", "waitlist"),
    ("shipping", "shipping"),
    ("contact", "contact"),
    ("cart", "cart"),
    ("received", "received"),
    ("terms", "legal"),
    ("withdrawal", "legal"),
    ("privacy", "legal"),
    ("business", "legal"),
]
NOINDEX_ALWAYS = {"cart", "received"}
NAV = ["shop", "story", "harvest", "shipping", "contact"]
LEGAL = ["terms", "withdrawal", "privacy", "business"]

# Wording that must never reach a page until the claims are cleared (brief section 6).
BANNED = [
    r"extra[\s-]*virgin", r"extra\s+vergine", r"nativ(es)?\s+oliven", r"djevičansk",
    r"cold[\s-]*press", r"cold\s+extract", r"kaltgepresst", r"kalt\s+extrahiert", r"hladno\s+prešan",
    r"\borganic\b", r"\bbio-", r"netretiran", r"\bbiologisch", r"\bekološk", r"untreated", r"unbehandelt",
    r"hollow", r"šuplj", r"hohl", r"same night", r"iste noći", r"derselben nacht",  # owner: no hollow trunks on the website (26 Nov 2026)
    r"oblica", r"skradin(er|sko|ian)?\s+(olive|oliven|maslinov)", "—",  # em dash
]


# ------------------------------------------------------------------ loading
def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content, bom=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="\n") as f:
        f.write(content)


def load_json(name):
    return json.loads(read(os.path.join(ROOT, "data", name)))


SITE = tomllib.loads(read(os.path.join(ROOT, "config", "site.toml")))
LANGS = SITE["languages"]["order"]
DEFAULT_LANG = LANGS[0]
T = {code: tomllib.loads(read(os.path.join(ROOT, "lang", f"{code}.toml"))) for code in LANGS}
PRODUCTS = load_json("products.json")
SHIPPING = load_json("shipping.json")
COUNTRIES = load_json("countries.json")
PHOTOS = load_json("photos.json")
YEAR = SITE["harvest"]["year"]


def die(msg):
    sys.exit(f"BUILD FAILED: {msg}")


# ------------------------------------------------------------------ validation
def validate():
    ids = set()
    for p in PRODUCTS["products"]:
        for key in ("id", "size_l", "price", "stock", "active", "weight_kg", "description"):
            if key not in p:
                die(f"product {p.get('id')} is missing '{key}'")
        if p["id"] in ids:
            die(f"duplicate product id {p['id']}")
        ids.add(p["id"])
        for code in LANGS:
            if code not in p["description"]:
                die(f"product {p['id']} has no description in '{code}'")
        if SITE["pricing"]["show_base_price"] and not p.get("base_price"):
            die(f"show_base_price is on but product {p['id']} has no base_price")
    for b in PRODUCTS["bundles"]:
        if b["id"] in ids:
            die(f"duplicate id {b['id']}")
        ids.add(b["id"])
        for item in b["items"]:
            if item["product"] not in {p["id"] for p in PRODUCTS["products"]}:
                die(f"bundle {b['id']} points to unknown product {item['product']}")
    zone_countries = [c for z in SHIPPING["zones"] for c in z["countries"]]
    for c in zone_countries:
        if c not in COUNTRIES:
            die(f"shipping.json country {c} is not an EU country in countries.json")
    if len(zone_countries) != len(set(zone_countries)):
        die("a country appears in two shipping zones")
    for z in SHIPPING["zones"]:
        for parcel in SHIPPING["parcels"]:
            if parcel["id"] not in z["prices"]:
                die(f"zone {z['id']} has no price for parcel {parcel['id']}")
    for code in LANGS:
        missing = [pid for pid, _ in PAGES if pid not in T[code]["pages"]]
        if missing:
            die(f"lang/{code}.toml has no [pages.{missing[0]}]")


# ------------------------------------------------------------------ formatting
def cents(amount):
    return int(round(float(amount) * 100))


def money(c):
    """Croatian format on every language (18,00 €): the form price rules expect."""
    s = f"{c / 100:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def size_label(size_l, lang):
    s = f"{size_l:g}"
    return f"{s} L" if lang == "en" else f"{s.replace('.', ',')} l"


def cap(s):
    return s[:1].upper() + s[1:]


def product_name(p, lang):
    return f"{cap(SITE['category'][lang])} {size_label(p['size_l'], lang)}"


def fill_vars(lang):
    c = SITE["contact"]
    return {
        "brand": SITE["brand_name"], "category": SITE["category"][lang], "year": str(YEAR),
        "email": c["email"], "phone": c["phone"],
        "reply_hours": str(SITE["selling"]["payment_reply_hours"]),
        "hold_hours": str(SITE["selling"]["hold_hours"]),
    }


def fill(text, lang, extra=None):
    v = fill_vars(lang)
    if extra:
        v.update(extra)
    return re.sub(r"\{(\w+)\}", lambda m: v.get(m.group(1), m.group(0)), text)


def address_lines(lang):
    """Postal address for one language; accepts a plain list (same for all languages) too."""
    a = SITE["contact"]["address_lines"]
    return a.get(lang) or a[DEFAULT_LANG] if isinstance(a, dict) else a


def esc(s):
    return html.escape(str(s), quote=True)


# ------------------------------------------------------------------ urls
def slug(page_id, lang):
    return T[lang]["pages"][page_id]["slug"]


def url(page_id, lang):
    s = slug(page_id, lang)
    prefix = "" if lang == DEFAULT_LANG else f"/{lang}"
    return f"{prefix}/{s}/" if s else f"{prefix}/"


def abs_url(page_id, lang):
    return SITE["site_url"].rstrip("/") + url(page_id, lang)


def out_path(page_id, lang):
    return os.path.join(DIST, url(page_id, lang).strip("/"), "index.html")


# ------------------------------------------------------------------ text markup
def inline(text, lang):
    s = esc(fill(text, lang))
    s = re.sub(r"\[\[(.+?)\]\]", r'<mark class="todo">\1</mark>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)

    def link(m):
        label, target = m.group(1), m.group(2)
        if target.startswith("page:"):
            target = url(target[5:], lang)
        return f'<a href="{target}">{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)


def md(text, lang):
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln.strip() for ln in block.strip().splitlines()]
        if all(ln.startswith("- ") for ln in lines):
            items = "".join(f"<li>{inline(ln[2:], lang)}</li>" for ln in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{inline(' '.join(lines), lang)}</p>")
    return "\n".join(out)


# ------------------------------------------------------------------ template engine
TOKEN = re.compile(r"\{\{\s*([\w.:-]+)(?:\|(\w+))?\s*\}\}")


def lookup(ctx, key):
    cur = ctx
    for part in key.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            raise KeyError(key)
    return cur


def render(tpl, ctx, lang):
    def sub(m):
        key, flt = m.group(1), m.group(2)
        if key.startswith("url:"):
            return url(key[4:], lang)
        if key.startswith("photo:"):
            return photo(key[6:], lang)
        try:
            val = lookup(ctx, key)
        except KeyError:
            die(f"template token '{key}' not found ({lang})")
        if flt == "raw":
            return str(val)
        if flt == "md":
            return md(str(val), lang)
        if flt == "inline":
            return inline(str(val), lang)
        return esc(fill(str(val), lang))

    return TOKEN.sub(sub, tpl)


def template(name):
    return read(os.path.join(TEMPLATES, name))


# ------------------------------------------------------------------ components
def photo(key, lang, cls=""):
    ph = PHOTOS[key]
    alt = esc(ph["alt"][lang])
    ratio = ph.get("ratio", "4/3")
    if ph.get("src"):
        src = ph["src"]
        small = re.sub(r"\.jpg$", "-800.jpg", src)
        has_small = os.path.isfile(os.path.join(ROOT, "static", small.replace("/assets/", "", 1)))
        srcset = f' srcset="{esc(small)} 800w, {esc(src)} 1600w" sizes="(min-width: 800px) 50vw, 100vw"' if has_small else ""
        load = 'fetchpriority="high"' if key == "hero" else 'loading="lazy"'
        return (f'<figure class="photo {cls}" style="aspect-ratio:{ratio}">'
                f'<img src="{esc(src)}"{srcset} alt="{alt}" {load} decoding="async"></figure>')
    return (f'<figure class="photo photo--todo {cls}" style="aspect-ratio:{ratio}" role="img" aria-label="{alt}">'
            f'<figcaption><span>{esc(T[lang]["ui"]["photo_todo"])}</span>{esc(ph["todo"])}</figcaption></figure>')


def bottle_svg(size_l):
    """Line drawing of a bottle; height follows the volume so the three read as a family."""
    h = {0.25: 96, 0.5: 128, 1.0: 168}.get(size_l, 128)
    w = round(h * 0.34)
    neck = round(w * 0.36)
    shoulder = round(h * 0.34)
    x0 = (60 - w) / 2
    nx = (60 - neck) / 2
    top = 180 - h
    d = (f"M{nx} {top} h{neck} v{shoulder * 0.45:.0f} "
         f"q0 {shoulder * 0.25:.0f} {(w - neck) / 2:.1f} {shoulder * 0.55:.0f} "
         f"V176 q0 4 -4 4 H{x0 + 4} q-4 0 -4 -4 V{top + shoulder:.0f} "
         f"q0 -{shoulder * 0.3:.0f} {(w - neck) / 2:.1f} -{shoulder * 0.55:.0f} Z")
    label_y = top + shoulder + (h - shoulder) * 0.25
    return (f'<svg class="bottle" viewBox="0 0 60 184" aria-hidden="true" focusable="false">'
            f'<path d="{d}" fill="var(--sage)" stroke="var(--green)" stroke-width="1.6"/>'
            f'<rect x="{x0 + 3}" y="{label_y:.0f}" width="{w - 6}" height="{(h - shoulder) * 0.38:.0f}" '
            f'fill="var(--paper)" stroke="var(--green)" stroke-width="1"/></svg>')


def total_stock():
    return sum(p["stock"] for p in PRODUCTS["products"] if p["active"])


def stock_badge(lang, big=False):
    ui = T[lang]["ui"]
    n = total_stock()
    full = ui["sold_out"] if n <= 0 else fill(ui["stock_left"], lang, {"n": str(n)})
    word = T[lang]["pages"]["harvest"]["f_month"]
    cls = "stamp stamp--big" if big else "stamp"
    if n <= 0:
        inner = f'<strong class="stamp__label stamp__label--out">{esc(ui["sold_out"])}</strong>'
    elif SITE["selling"].get("show_stock", False):
        inner = f'<strong class="stamp__n">{n}</strong><span class="stamp__label">{esc(ui["stamp_label"])}</span>'
    else:
        # no bottle count for now (owner, 26 Nov 2026): the stamp just says "Harvest 2026"
        full = f"{word} {YEAR}"
        return (f'<div class="{cls}" role="img" aria-label="{esc(full)}"><span class="stamp__ring" aria-hidden="true">{esc(word)}</span>'
                f'<span aria-hidden="true" class="stamp__inner"><strong class="stamp__n stamp__n--year">{YEAR}</strong></span></div>')
    return (f'<div class="{cls}" role="img" aria-label="{esc(full)}"><span class="stamp__ring" aria-hidden="true">{esc(word)} {YEAR}</span>'
            f'<span aria-hidden="true" class="stamp__inner">{inner}</span></div>')


MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
             "September", "October", "November", "December"]


def fmt_date(iso, lang):
    """2026-11-26 -> 26. 11. 2026. (hr), 26.11.2026 (de), 26 November 2026 (en)."""
    y, m, d = (int(x) for x in iso.split("-"))
    if lang == "hr":
        return f"{d}. {m}. {y}."
    if lang == "de":
        return f"{d:02d}.{m:02d}.{y}"
    return f"{d} {MONTHS_EN[m - 1]} {y}"


def base_date(item=None):
    """Base price date: the item's own date, else the site-wide one in config/site.toml."""
    d = (item or {}).get("base_price_date") or SITE["pricing"].get("base_price_date", "")
    if not d:
        die("base price shown but no base_price_date (set pricing.base_price_date in config/site.toml)")
    return d


def base_text(base_c, date_iso, lang):
    """Croatian base price rule (17 Nov 2026): label translated, amount always in Croatian format."""
    if not SITE["pricing"]["show_base_price"]:
        return ""
    if base_c is None or base_c <= 0:
        die("a shown price has no base price")
    return fill(T[lang]["ui"]["base_price"], lang, {"date": fmt_date(date_iso, lang), "price": money(base_c)})


def price_block(price_c, lang, base_c=None, date_iso=""):
    out = f'<span class="price">{money(price_c)}</span>'
    if SITE["pricing"]["show_base_price"]:
        out += f'<span class="base-price">{esc(base_text(base_c, date_iso, lang))}</span>'
    return out


def active_products():
    return sorted([p for p in PRODUCTS["products"] if p["active"]], key=lambda p: p.get("sort", 0))


def active_bundles():
    return sorted([b for b in PRODUCTS["bundles"] if b["active"]], key=lambda b: b.get("sort", 0))


def bundle_price_c(b):
    if b.get("price") is not None:
        return cents(b["price"])
    by_id = {p["id"]: p for p in PRODUCTS["products"]}
    return sum(cents(by_id[i["product"]]["price"]) * i["qty"] for i in b["items"])


def product_base_c(p):
    return cents(p["base_price"]) if p.get("base_price") else None


def bundle_base_c(b):
    if b.get("base_price") is not None:
        return cents(b["base_price"])
    by_id = {p["id"]: p for p in PRODUCTS["products"]}
    if any(product_base_c(by_id[i["product"]]) is None for i in b["items"]):
        return None
    return sum(product_base_c(by_id[i["product"]]) * i["qty"] for i in b["items"])


def bundle_stock(b):
    by_id = {p["id"]: p for p in PRODUCTS["products"]}
    return min(by_id[i["product"]]["stock"] // i["qty"] for i in b["items"])


def add_button(item_id, stock, lang, can_buy=True):
    ui = T[lang]["ui"]
    if not SITE["selling"]["enabled"]:
        return f'<a class="btn btn--ghost" href="{url("waitlist", lang)}">{esc(ui["waitlist_cta"])}</a>'
    if stock <= 0:
        return (f'<span class="soldout">{esc(ui["sold_out"])}</span> '
                f'<a class="btn btn--ghost" href="{url("waitlist", lang)}">{esc(ui["waitlist_cta"])}</a>')
    return (f'<button class="btn" type="button" data-add="{esc(item_id)}">{esc(ui["add_to_cart"])}</button>')


def product_card(p, lang, compact=False):
    ui = T[lang]["ui"]
    price_c = cents(p["price"])
    unit_c = round(price_c / p["size_l"])
    stock = p["stock"]
    extra = "" if p.get("online", True) else f'<p class="note">{esc(ui["pickup_only"])}</p>'
    desc = "" if compact else f'<p class="card__desc">{esc(p["description"][lang])}</p>'
    left = "" if stock <= 0 or not SITE["selling"].get("show_stock", False) else f'<span class="card__left">{esc(fill(ui["stock_bottle"], lang, {"n": str(stock)}))}</span>'
    return f"""<article class="card" id="{esc(p['id'])}">
  <div class="card__art">{bottle_svg(p['size_l'])}</div>
  <div class="card__body">
    <h3 class="card__title">{esc(product_name(p, lang))}</h3>
    {desc}
    <p class="card__price">{price_block(price_c, lang, product_base_c(p), base_date(p) if SITE['pricing']['show_base_price'] else '')}
      <span class="unit">{esc(fill(ui['unit_price'], lang, {'price': money(unit_c)}))}</span></p>
    {extra}
    <div class="card__buy">{add_button(p['id'], stock, lang)} {left}</div>
  </div>
</article>"""


def bundle_card(b, lang):
    ui = T[lang]["ui"]
    price_c = bundle_price_c(b)
    note = f'<p class="note">{esc(ui["set_price_note"])}</p>' if b.get("price") is None else ""
    by_id = {p["id"]: p for p in PRODUCTS["products"]}
    art = "".join(bottle_svg(by_id[i["product"]]["size_l"]) for i in b["items"] for _ in range(min(i["qty"], 6)))
    return f"""<article class="card card--set" id="{esc(b['id'])}">
  <div class="card__art card__art--set">{art}</div>
  <div class="card__body">
    <h3 class="card__title">{esc(b['name'][lang])}</h3>
    <p class="card__price">{price_block(price_c, lang, bundle_base_c(b), base_date(b) if SITE['pricing']['show_base_price'] else '')}</p>
    {note}
    <div class="card__buy">{add_button(b['id'], bundle_stock(b), lang)}</div>
  </div>
</article>"""


def products_grid(lang, compact=False):
    return '<div class="grid grid--3">' + "".join(product_card(p, lang, compact) for p in active_products()) + "</div>"


def bundles_grid(lang):
    bs = active_bundles()
    if not bs:
        return ""
    ui = T[lang]["ui"]
    cards = "".join(bundle_card(b, lang) for b in bs)
    return (f'<section class="section"><h2>{esc(ui["sets_title"])}</h2><p class="lead-s">{esc(ui["sets_intro"])}</p>'
            f'<div class="grid grid--3">{cards}</div></section>')


def ship_cell(zone, parcel_id, lang):
    price = cents(zone["prices"][parcel_id])
    if not SITE["pricing"]["show_base_price"]:
        return f'<span class="price price--table">{money(price)}</span>'
    base = cents(zone.get("base_prices", zone["prices"])[parcel_id])
    label = esc(T[lang]["ui"]["base_short"])
    return (f'<span class="price price--table">{money(price)}</span>'
            f'<span class="base-price">{label} {money(base)}</span>')


def shipping_base_note(lang):
    if not SITE["pricing"]["show_base_price"]:
        return ""
    d = SHIPPING.get("base_price_date") or base_date()
    return f'<p class="note">{esc(fill(T[lang]["ui"]["base_note"], lang, {"date": fmt_date(d, lang)}))}</p>'


def shipping_table(lang):
    pg = T[lang]["pages"]["shipping"]
    heads = []
    for parcel in SHIPPING["parcels"]:
        n = parcel["max_bottles"]
        heads.append(pg["col_parcel_one"] if n == 1 else fill(pg["col_parcel"], lang, {"n": str(n)}))
    th = "".join(f'<th scope="col">{esc(h)}</th>' for h in heads)
    rows = []
    for z in SHIPPING["zones"]:
        names = sorted(COUNTRIES[c][lang] for c in z["countries"])
        tds = "".join(f"<td>{ship_cell(z, p['id'], lang)}</td>" for p in SHIPPING["parcels"])
        rows.append(f'<tr><th scope="row">{esc(", ".join(names))}</th>{tds}<td>{esc(z.get("days", ""))}</td></tr>')
    return (f'<div class="table-wrap"><table class="ship"><thead><tr><th scope="col">{esc(pg["col_zone"])}</th>'
            f'{th}<th scope="col">{esc(pg["col_days"])}</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
            + shipping_base_note(lang))


def harvest_facts(lang):
    pg = T[lang]["pages"]["harvest"]
    h = SITE["harvest"]
    bottles = str(h["total_bottles"]) if h["total_bottles"] else f'<mark class="todo">{esc(pg["pending"])}</mark>'
    rows = [
        ("f_month", esc(fill(pg["f_month_v"], lang))),
        ("f_pickers", esc(pg["f_pickers_v"])),
        ("f_batch1", esc(pg["f_batch1_v"])),
        ("f_batch2", esc(fill(pg["f_batch2_v"], lang))),
        ("f_total", esc(f"{h['total_litres']} L") if h["total_litres"] else f'{esc(pg["f_total_expected"])}. <mark class="todo">{esc(pg["pending"])}</mark>'),
        ("f_bottles", bottles),
        ("f_fruit", esc(pg["f_fruit_v"])),
        ("f_year", esc(pg["f_year_v"])),
    ]
    return '<dl class="facts">' + "".join(f"<div><dt>{esc(pg[k])}</dt><dd>{v}</dd></div>" for k, v in rows) + "</dl>"


def catalog_json(lang):
    """Display data for the cart. The server recalculates every amount; nothing here is trusted."""
    items = []
    for p in active_products():
        items.append({"id": p["id"], "name": product_name(p, lang), "price": cents(p["price"]),
                      "stock": p["stock"], "online": p.get("online", True), "size": p["size_l"],
                      "base": base_text(product_base_c(p), base_date(p), lang) if SITE["pricing"]["show_base_price"] else ""})
    for b in active_bundles():
        items.append({"id": b["id"], "name": b["name"][lang], "price": bundle_price_c(b),
                      "stock": bundle_stock(b), "online": True, "set": True,
                      "base": base_text(bundle_base_c(b), base_date(b), lang) if SITE["pricing"]["show_base_price"] else ""})
    shippable = sorted({c for z in SHIPPING["zones"] for c in z["countries"]}, key=lambda c: COUNTRIES[c][lang])
    data = {
        "lang": lang,
        "items": items,
        "countries": [{"code": c, "name": COUNTRIES[c][lang]} for c in shippable],
        "pickup": SHIPPING["pickup_countries"],
        "selling": SITE["selling"]["enabled"],
        "urls": {"received": url("received", lang), "shop": url("shop", lang), "cart": url("cart", lang)},
        "t": {k: fill(v, lang) for k, v in T[lang]["cart"].items() if k != "how"},
        "ui": {k: fill(v, lang) for k, v in T[lang]["ui"].items()},
    }
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


# ------------------------------------------------------------------ head / chrome
def head_meta(page_id, lang, pg):
    staging = SITE["staging"]
    noindex = staging or page_id in NOINDEX_ALWAYS
    tags = []
    if noindex:
        tags.append('<meta name="robots" content="noindex, nofollow">')
    tags.append(f'<link rel="canonical" href="{abs_url(page_id, lang)}">')
    for code in LANGS:
        tags.append(f'<link rel="alternate" hreflang="{code}" href="{abs_url(page_id, code)}">')
    tags.append(f'<link rel="alternate" hreflang="x-default" href="{abs_url(page_id, DEFAULT_LANG)}">')
    title = fill(pg["title"], lang)
    desc = fill(pg["description"], lang)
    og_img = SITE["site_url"].rstrip("/") + SITE["seo"]["og_image"]
    tags += [
        f'<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{esc(SITE["brand_name"])}">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(desc)}">',
        f'<meta property="og:url" content="{abs_url(page_id, lang)}">',
        f'<meta property="og:locale" content="{T[lang]["locale"]}">',
        f'<meta property="og:image" content="{og_img}">',
    ]
    for code in LANGS:
        if code != lang:
            tags.append(f'<meta property="og:locale:alternate" content="{T[code]["locale"]}">')
    if SITE["seo"]["product_schema"] and page_id == "shop":
        tags.append(product_schema(lang))
    return "\n  ".join(tags)


def product_schema(lang):
    data = []
    for p in active_products():
        data.append({
            "@context": "https://schema.org", "@type": "Product",
            "name": f'{SITE["brand_name"]} {product_name(p, lang)}',
            "description": p["description"][lang],
            "brand": {"@type": "Brand", "name": SITE["brand_name"]},
            "countryOfOrigin": "HR",
            "offers": {"@type": "Offer", "price": f'{p["price"]:.2f}', "priceCurrency": "EUR",
                       "availability": "https://schema.org/InStock" if p["stock"] > 0 else "https://schema.org/SoldOut",
                       "url": abs_url("shop", lang)},
        })
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'


def nav_html(page_id, lang):
    ui = T[lang]["ui"]
    keys = {"shop": "nav_shop", "story": "nav_story", "harvest": "nav_harvest",
            "shipping": "nav_shipping", "contact": "nav_contact"}
    items = []
    for pid in NAV:
        cur = ' aria-current="page"' if pid == page_id else ""
        items.append(f'<li><a href="{url(pid, lang)}"{cur}>{esc(fill(ui[keys[pid]], lang))}</a></li>')
    return "".join(items)


def flag_img(code):
    # Self-hosted SVG flags (emoji flags do not render on Windows), same as taxisibenik.hr.
    return f'<img class="flag" src="/assets/img/flags/{code}.svg" width="20" height="15" alt="" decoding="async">'


def lang_switch(page_id, lang):
    items = []
    for code in LANGS:
        cur = ' aria-current="true"' if code == lang else ""
        # short code on screen (HR, EN, DE); full name for screen readers and on hover
        items.append(f'<a class="langdd__item" href="{url(page_id, code)}" hreflang="{code}" lang="{code}"'
                     f' title="{esc(T[code]["label"])}" aria-label="{esc(T[code]["label"])}"{cur}>'
                     f'{flag_img(code)} {code.upper()}</a>')
    label = esc(T[lang]["ui"]["lang_label"])
    return (f'<div class="langdd">'
            f'<button class="langdd__toggle" type="button" aria-expanded="false" aria-haspopup="true" '
            f'aria-label="{label}: {esc(T[lang]["label"])}">{flag_img(lang)} <span>{lang.upper()}</span>'
            f'<span class="caret" aria-hidden="true"></span></button>'
            f'<div class="langdd__menu">{"".join(items)}</div></div>')


def legal_links(lang):
    return "".join(f'<li><a href="{url(pid, lang)}">{esc(T[lang]["pages"][pid]["h1"])}</a></li>' for pid in LEGAL)


def cjenik_link(lang):
    f = SITE["pricing"]["cjenik_file"]
    if not f:
        return ""
    return f'<p><a href="{esc(f)}" download>{esc(T[lang]["ui"]["price_list"])}</a></p>'


# ------------------------------------------------------------------ assets
def asset_version():
    h = hashlib.md5()
    for name in ("css/site.css", "js/site.js"):
        with open(os.path.join(ROOT, "static", name), "rb") as f:
            h.update(f.read())
    return h.hexdigest()[:10]


# ------------------------------------------------------------------ build
def build_page(page_id, tpl_name, lang, ver):
    pg = T[lang]["pages"][page_id]
    ctx = {
        "t": T[lang], "pg": pg, "ui": T[lang]["ui"], "cart": T[lang]["cart"],
        "site": {"brand": SITE["brand_name"], "category": SITE["category"][lang],
                 "tagline": SITE["tagline"][lang], "year": YEAR,
                 "email": SITE["contact"]["email"], "phone": SITE["contact"]["phone"],
                 "phone_href": re.sub(r"[^\d+]", "", SITE["contact"]["phone"]),
                 "address": "<br>".join(esc(x) for x in address_lines(lang))},
        "x": {
            "stamp": stock_badge(lang), "stamp_big": stock_badge(lang, big=True),
            "products": products_grid(lang), "products_compact": products_grid(lang, compact=True),
            "bundles": bundles_grid(lang), "shipping_table": shipping_table(lang),
            "facts": harvest_facts(lang), "catalog": catalog_json(lang),
            "selling_class": "" if SITE["selling"]["enabled"] else "is-closed",
        },
    }
    body = render(template(f"pages/{tpl_name}.html"), ctx, lang)
    # owner: no visible "preview only" bar; staging still means noindex + robots Disallow
    staging_banner = ""
    base_ctx = dict(ctx)
    base_ctx["page"] = {
        "id": page_id, "lang": lang, "title": fill(pg["title"], lang),
        "description": fill(pg["description"], lang), "head": head_meta(page_id, lang, pg),
        "nav": nav_html(page_id, lang), "langs": lang_switch(page_id, lang), "legal": legal_links(lang),
        "cjenik": cjenik_link(lang), "staging": staging_banner, "body": body, "ver": ver,
        "home": url("home", lang), "cart": url("cart", lang),
    }
    out = render(template("base.html"), base_ctx, lang)
    check_banned(out, f"{page_id}/{lang}")
    if SITE["pricing"]["show_base_price"]:
        n_price = len(re.findall(r'class="price[ "]', out))
        n_base = len(re.findall(r'class="base-price"', out))
        if n_price != n_base:
            die(f"{page_id}/{lang}: {n_price} prices but {n_base} base prices")
    write(out_path(page_id, lang), out)


def check_banned(text, where):
    visible = re.sub(r"<script[\s\S]*?</script>", "", text)
    for pat in BANNED:
        m = re.search(pat, visible, re.I)
        if m:
            die(f"banned wording '{m.group(0)}' in {where} (see brief section 6)")


def copy_tree(src, dst):
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True)


def export_private():
    """Data the PHP scripts read. Same files as the build uses, so prices exist in one place."""
    priv = os.path.join(DIST, "private")
    site_public = {
        "brand": SITE["brand_name"], "category": SITE["category"], "site_url": SITE["site_url"],
        "contact": SITE["contact"], "selling": SITE["selling"], "harvest_year": YEAR,
        "languages": LANGS, "default_lang": DEFAULT_LANG,
        "urls": {code: {pid: url(pid, code) for pid, _ in PAGES} for code in LANGS},
        "product_names": {code: {p["id"]: product_name(p, code) for p in PRODUCTS["products"]} for code in LANGS},
    }
    write(os.path.join(priv, "data", "site.json"), json.dumps(site_public, ensure_ascii=False, indent=1))
    for name in ("products.json", "shipping.json", "countries.json"):
        shutil.copy(os.path.join(ROOT, "data", name), os.path.join(priv, "data", name))
    for code in LANGS:
        sub = {"cart": T[code]["cart"], "waitlist": T[code]["waitlist"], "email": T[code]["email"],
               "ui": T[code]["ui"]}
        write(os.path.join(priv, "lang", f"{code}.json"), json.dumps(sub, ensure_ascii=False, indent=1))
    local_cfg = os.path.join(ROOT, "config.php")
    if os.path.isfile(local_cfg):  # local dev only; on the server config.php is created by hand
        shutil.copy(local_cfg, os.path.join(priv, "config.php"))


def robots_and_sitemap():
    if SITE["staging"]:
        write(os.path.join(DIST, "robots.txt"), "# Staging: nothing may be indexed.\nUser-agent: *\nDisallow: /\n")
        return
    write(os.path.join(DIST, "robots.txt"),
          f"User-agent: *\nDisallow: /api/\nDisallow: /private/\n\nSitemap: {SITE['site_url'].rstrip('/')}/sitemap.xml\n")
    urls = []
    today = date.today().isoformat()
    for pid, _ in PAGES:
        if pid in NOINDEX_ALWAYS:
            continue
        for code in LANGS:
            alts = "".join(f'<xhtml:link rel="alternate" hreflang="{c}" href="{abs_url(pid, c)}"/>' for c in LANGS)
            urls.append(f"<url><loc>{abs_url(pid, code)}</loc><lastmod>{today}</lastmod>{alts}</url>")
    write(os.path.join(DIST, "sitemap.xml"),
          '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(urls) + "\n</urlset>\n")


def htaccess():
    lines = [read(os.path.join(ROOT, "php", "htaccess.txt"))]
    if SITE["staging"]:
        lines.append('\n# Staging: tell crawlers not to index anything, including PHP and files.\n'
                     '<IfModule mod_headers.c>\n  Header set X-Robots-Tag "noindex, nofollow"\n</IfModule>\n')
    write(os.path.join(DIST, ".htaccess"), "".join(lines))


def cjenik_csv():
    """Machine-readable price list (Croatian rule). Written only when switched on in site.toml."""
    f = SITE["pricing"]["cjenik_file"]
    if not f:
        return
    rows = ["Šifra;Naziv proizvoda;Neto količina;Jedinica mjere;Maloprodajna cijena;Cijena za jedinicu mjere;"
            "Poseban oblik prodaje (DA/NE);Bazna cijena;Datum bazne cijene"]
    fmt = lambda c: f"{c / 100:.2f}".replace(".", ",")
    for p in active_products():
        pc = cents(p["price"])
        rows.append(";".join([p["id"], product_name(p, "hr"), f"{p['size_l']:g}".replace(".", ","), "l",
                              fmt(pc), fmt(round(pc / p["size_l"])), "NE",
                              fmt(cents(p.get("base_price") or p["price"])), fmt_date(base_date(p), "hr")]))
    write(os.path.join(DIST, f.lstrip("/")), "\r\n".join(rows) + "\r\n", bom=True)


def main():
    validate()
    if os.path.isdir(DIST):
        # keep runtime data of a local test run (orders db, mail log) between builds
        for entry in os.listdir(DIST):
            if entry == "private":
                continue
            p = os.path.join(DIST, entry)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    os.makedirs(DIST, exist_ok=True)
    ver = asset_version()
    copy_tree(os.path.join(ROOT, "static"), os.path.join(DIST, "assets"))
    if not ON_VERCEL:
        copy_tree(os.path.join(ROOT, "php", "api"), os.path.join(DIST, "api"))
        copy_tree(os.path.join(ROOT, "php", "admin"), os.path.join(DIST, SITE["admin"]["dir"]))
        copy_tree(os.path.join(ROOT, "php", "private"), os.path.join(DIST, "private"))
        export_private()
    for pid, tpl in PAGES:
        for lang in LANGS:
            build_page(pid, tpl, lang, ver)
    robots_and_sitemap()
    if not ON_VERCEL:
        htaccess()
    cjenik_csv()
    n = len(PAGES) * len(LANGS)
    mode = "STAGING (noindex)" if SITE["staging"] else "LIVE (indexable)"
    if ON_VERCEL:
        print("Vercel preview build: PHP order API, admin and private data skipped.")
    print(f"Built {n} pages in {len(LANGS)} languages -> dist/   mode: {mode}   stock: {total_stock()} bottles")


if __name__ == "__main__":
    main()
