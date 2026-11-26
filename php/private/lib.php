<?php
/**
 * Shared backend: config, data, server-side pricing, SQLite storage, mail, spam checks.
 *
 * Money is handled in integer cents everywhere. The browser sends only item ids,
 * quantities, country and delivery method; all amounts are computed here from
 * private/data/products.json and private/data/shipping.json (copied there by build.py).
 */
declare(strict_types=1);

const ORDER_STATUSES = ['new', 'payment_requested', 'paid', 'shipped', 'cancelled'];
const MAX_QTY_PER_LINE = 60;

function cfg(): array
{
    static $c = null;
    if ($c === null) {
        $path = __DIR__ . '/config.php';
        if (!is_file($path)) {
            http_response_code(500);
            header('Content-Type: application/json');
            exit(json_encode(['ok' => false, 'error' => 'config']));
        }
        $c = (require $path) + [
            'mail_mode' => 'mail',
            'data_dir' => __DIR__ . '/storage',
            'owner_lang' => 'hr',
            'reply_to' => '',
        ];
    }
    return $c;
}

function data_file(string $name): array
{
    static $cache = [];
    if (!isset($cache[$name])) {
        $raw = file_get_contents(__DIR__ . '/data/' . $name);
        $cache[$name] = json_decode((string)$raw, true, 64, JSON_THROW_ON_ERROR);
    }
    return $cache[$name];
}

function site(): array { return data_file('site.json'); }

function lang_strings(string $lang): array
{
    static $cache = [];
    $lang = in_array($lang, site()['languages'], true) ? $lang : site()['default_lang'];
    if (!isset($cache[$lang])) {
        $cache[$lang] = json_decode((string)file_get_contents(__DIR__ . "/lang/$lang.json"), true);
    }
    return $cache[$lang];
}

function clean_lang($lang): string
{
    return is_string($lang) && in_array($lang, site()['languages'], true) ? $lang : site()['default_lang'];
}

function to_cents($amount): int { return (int)round(((float)$amount) * 100); }

/** 18,00 € on every language: the Croatian form, as the price rules expect. */
function money(int $cents): string
{
    return number_format($cents / 100, 2, ',', ' ') . ' €';
}

function fill(string $tpl, array $vars): string
{
    return preg_replace_callback('/\{(\w+)\}/', function ($m) use ($vars) {
        return array_key_exists($m[1], $vars) ? (string)$vars[$m[1]] : $m[0];
    }, $tpl);
}

function base_vars(string $lang): array
{
    $s = site();
    return [
        'brand' => $s['brand'], 'category' => $s['category'][$lang] ?? '', 'year' => $s['harvest_year'],
        'email' => $s['contact']['email'], 'phone' => $s['contact']['phone'],
        'reply_hours' => $s['selling']['payment_reply_hours'], 'hold_hours' => $s['selling']['hold_hours'],
    ];
}

// ------------------------------------------------------------------ catalogue
/** id => ['type','price','bottles'=>[product_id=>qty],'online','weight','count', 'names'=>[lang=>name]] */
function catalog(): array
{
    static $cat = null;
    if ($cat !== null) return $cat;
    $p = data_file('products.json');
    $names = site()['product_names'];
    $cat = [];
    $products = [];
    foreach ($p['products'] as $prod) {
        if (empty($prod['active'])) continue;
        $products[$prod['id']] = $prod;
        $n = [];
        foreach ($names as $lang => $map) $n[$lang] = $map[$prod['id']] ?? $prod['id'];
        $cat[$prod['id']] = [
            'type' => 'product', 'price' => to_cents($prod['price']), 'bottles' => [$prod['id'] => 1],
            'online' => $prod['online'] ?? true, 'names' => $n,
        ];
    }
    foreach ($p['bundles'] as $b) {
        if (empty($b['active'])) continue;
        $bottles = [];
        $sum = 0;
        $online = true;
        foreach ($b['items'] as $it) {
            if (!isset($products[$it['product']])) continue 2;
            $bottles[$it['product']] = ($bottles[$it['product']] ?? 0) + (int)$it['qty'];
            $sum += to_cents($products[$it['product']]['price']) * (int)$it['qty'];
            $online = $online && ($products[$it['product']]['online'] ?? true);
        }
        $cat[$b['id']] = [
            'type' => 'bundle', 'price' => $b['price'] === null ? $sum : to_cents($b['price']),
            'bottles' => $bottles, 'online' => $online, 'names' => $b['name'],
        ];
    }
    return $cat;
}

function product_rows(): array
{
    $out = [];
    foreach (data_file('products.json')['products'] as $p) $out[$p['id']] = $p;
    return $out;
}

function shippable_countries(): array
{
    $list = [];
    foreach (data_file('shipping.json')['zones'] as $z) foreach ($z['countries'] as $c) $list[$c] = $z;
    return $list;
}

function country_name(string $code, string $lang): string
{
    $c = data_file('countries.json');
    return $c[$code][$lang] ?? $code;
}

/** Split bottles into parcels: smallest parcel that fits count and weight; big orders use several. */
function parcels_for(int $bottles, float $weight): array
{
    $defs = data_file('shipping.json')['parcels'];
    usort($defs, fn($a, $b) => $a['max_bottles'] <=> $b['max_bottles']);
    $biggest = end($defs);
    $avg = $bottles > 0 ? $weight / $bottles : 0;
    $out = [];
    while ($bottles > 0) {
        $chosen = null;
        foreach ($defs as $d) {
            if ($bottles <= $d['max_bottles'] && $bottles * $avg <= $d['max_weight_kg'] + 1e-9) { $chosen = $d; break; }
        }
        if ($chosen === null) {
            $chosen = $biggest;
            $n = min($biggest['max_bottles'], max(1, (int)floor($biggest['max_weight_kg'] / max($avg, 0.001))));
        } else {
            $n = $bottles;
        }
        $out[] = $chosen['id'];
        $bottles -= $n;
    }
    return $out;
}

/**
 * The one place where totals are calculated.
 * Returns ['ok'=>true, lines, subtotal, shipping, total, parcels, bottles] or ['ok'=>false, 'error'=>..., ...]
 */
function quote(array $rawItems, string $country, string $delivery, string $lang): array
{
    $cat = catalog();
    $rows = product_rows();
    $ship = data_file('shipping.json');
    $zones = shippable_countries();
    $delivery = $delivery === 'pickup' ? 'pickup' : 'address';

    if (!isset($zones[$country])) return ['ok' => false, 'error' => 'country'];
    if ($delivery === 'pickup' && !in_array($country, $ship['pickup_countries'], true)) {
        return ['ok' => false, 'error' => 'delivery'];
    }

    $qty = [];
    foreach ($rawItems as $it) {
        if (!is_array($it)) continue;
        $id = is_string($it['id'] ?? null) ? $it['id'] : '';
        $q = filter_var($it['qty'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1, 'max_range' => MAX_QTY_PER_LINE]]);
        if ($id === '' || !isset($cat[$id]) || $q === false) return ['ok' => false, 'error' => 'items'];
        $qty[$id] = ($qty[$id] ?? 0) + $q;
    }
    if (!$qty) return ['ok' => false, 'error' => 'empty'];

    // Stock is counted in bottles across products and sets.
    $need = [];
    foreach ($qty as $id => $q) {
        if (!$cat[$id]['online'] && $delivery !== 'pickup') return ['ok' => false, 'error' => 'pickup_only', 'id' => $id];
        foreach ($cat[$id]['bottles'] as $pid => $n) $need[$pid] = ($need[$pid] ?? 0) + $n * $q;
    }
    $short = false;
    foreach ($need as $pid => $n) if ($n > (int)$rows[$pid]['stock']) $short = true;
    if ($short) {
        $available = [];
        foreach ($qty as $id => $q) {
            $max = PHP_INT_MAX;
            foreach ($cat[$id]['bottles'] as $pid => $n) $max = min($max, intdiv(max(0, (int)$rows[$pid]['stock']), $n));
            $available[$id] = $max;
        }
        return ['ok' => false, 'error' => 'stock', 'available' => $available];
    }

    $lines = [];
    $subtotal = 0;
    $bottles = 0;
    $weight = 0.0;
    foreach ($qty as $id => $q) {
        $line = $cat[$id]['price'] * $q;
        $subtotal += $line;
        $lines[] = [
            'id' => $id, 'type' => $cat[$id]['type'], 'qty' => $q, 'name' => $cat[$id]['names'][$lang] ?? $id,
            'unit' => $cat[$id]['price'], 'line' => $line, 'bottles' => $cat[$id]['bottles'],
        ];
    }
    foreach ($need as $pid => $n) {
        $bottles += $n;
        $weight += $n * (float)$rows[$pid]['weight_kg'];
    }

    $parcels = [];
    $shipping = 0;
    if ($delivery === 'address') {
        $parcels = parcels_for($bottles, $weight);
        foreach ($parcels as $pid) $shipping += to_cents($zones[$country]['prices'][$pid]);
    }
    return [
        'ok' => true, 'lines' => $lines, 'subtotal' => $subtotal, 'shipping' => $shipping,
        'total' => $subtotal + $shipping, 'parcels' => $parcels, 'bottles' => $bottles,
        'weight_kg' => round($weight, 2), 'country' => $country, 'delivery' => $delivery,
    ];
}

// ------------------------------------------------------------------ storage
function data_dir(): string
{
    $d = rtrim(cfg()['data_dir'], '/\\');
    if (!is_dir($d)) @mkdir($d, 0700, true);
    return $d;
}

function db(): PDO
{
    static $pdo = null;
    if ($pdo) return $pdo;
    $pdo = new PDO('sqlite:' . data_dir() . '/orders.sqlite', null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('PRAGMA journal_mode = WAL; PRAGMA foreign_keys = ON; PRAGMA busy_timeout = 5000;');
    migrate($pdo);
    return $pdo;
}

/**
 * Schema. An order is a request first; payment fields are separate so a real
 * checkout (payment provider id, paid_at) can be added later without a rewrite.
 */
function migrate(PDO $pdo): void
{
    $pdo->exec("CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ref TEXT UNIQUE,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'new',
        lang TEXT NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        address1 TEXT, address2 TEXT, postal TEXT, city TEXT,
        country TEXT NOT NULL,
        delivery TEXT NOT NULL,
        note TEXT,
        source TEXT,
        currency TEXT NOT NULL DEFAULT 'EUR',
        subtotal_cents INTEGER NOT NULL,
        shipping_cents INTEGER NOT NULL,
        total_cents INTEGER NOT NULL,
        parcels TEXT,
        weight_kg REAL,
        hold_until TEXT,
        payment_method TEXT,
        payment_provider_ref TEXT,
        paid_at TEXT,
        invoice_number TEXT,
        tracking_number TEXT,
        shipped_at TEXT,
        admin_note TEXT,
        ip_hash TEXT
    )");
    $pdo->exec("CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        item_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        name TEXT NOT NULL,
        qty INTEGER NOT NULL,
        unit_cents INTEGER NOT NULL,
        line_cents INTEGER NOT NULL,
        bottles TEXT NOT NULL
    )");
    $pdo->exec("CREATE TABLE IF NOT EXISTS order_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        at TEXT NOT NULL,
        event TEXT NOT NULL,
        detail TEXT
    )");
    $pdo->exec("CREATE TABLE IF NOT EXISTS waitlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE,
        lang TEXT NOT NULL,
        source TEXT,
        created_at TEXT NOT NULL,
        notified_at TEXT
    )");
    $pdo->exec("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, created_at)");
}

function now(): string { return gmdate('Y-m-d H:i:s'); }

function order_event(int $orderId, string $event, string $detail = ''): void
{
    db()->prepare('INSERT INTO order_events (order_id, at, event, detail) VALUES (?, ?, ?, ?)')
        ->execute([$orderId, now(), $event, $detail]);
}

// ------------------------------------------------------------------ spam protection
function secret(): string
{
    $s = cfg()['secret'] ?? '';
    if (strlen($s) < 32) {
        http_response_code(500);
        exit(json_encode(['ok' => false, 'error' => 'config']));
    }
    return $s;
}

/** Signed timestamp; the form must be at least a few seconds old and at most a day. */
function form_token(): string
{
    $t = (string)time();
    return $t . '.' . hash_hmac('sha256', $t, secret());
}

function token_ok($token, int $minAge = 3, int $maxAge = 86400): bool
{
    if (!is_string($token) || !preg_match('/^(\d{9,11})\.([a-f0-9]{64})$/', $token, $m)) return false;
    if (!hash_equals(hash_hmac('sha256', $m[1], secret()), $m[2])) return false;
    $age = time() - (int)$m[1];
    return $age >= $minAge && $age <= $maxAge;
}

function client_ip_hash(): string
{
    return substr(hash_hmac('sha256', $_SERVER['REMOTE_ADDR'] ?? '0', secret()), 0, 24);
}

/** File-based per-IP limiter: max $max hits per $window seconds for a bucket. */
function rate_limit(string $bucket, int $max, int $window): bool
{
    $dir = data_dir() . '/ratelimit';
    if (!is_dir($dir)) @mkdir($dir, 0700, true);
    $fp = @fopen("$dir/{$bucket}_" . client_ip_hash(), 'c+');
    if (!$fp) return true;
    flock($fp, LOCK_EX);
    $now = time();
    $raw = stream_get_contents($fp);
    $times = array_values(array_filter(array_map('intval', $raw === '' ? [] : explode(',', $raw)), fn($t) => $t > $now - $window));
    $ok = count($times) < $max;
    if ($ok) $times[] = $now;
    ftruncate($fp, 0);
    rewind($fp);
    fwrite($fp, implode(',', $times));
    flock($fp, LOCK_UN);
    fclose($fp);
    return $ok;
}

// ------------------------------------------------------------------ http helpers
function json_out(array $data, int $code = 200): void
{
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Robots-Tag: noindex');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}

function json_in(): array
{
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') json_out(['ok' => false, 'error' => 'method'], 405);
    $raw = file_get_contents('php://input', false, null, 0, 20000);
    $data = json_decode((string)$raw, true);
    if (!is_array($data)) json_out(['ok' => false, 'error' => 'bad_request'], 400);
    return $data;
}

function str_field(array $in, string $key, int $max): string
{
    $v = $in[$key] ?? '';
    if (!is_string($v)) return '';
    $v = trim(preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $v) ?? '');
    return mb_substr($v, 0, $max);
}

function one_line(string $s): string { return trim(preg_replace('/[\r\n]+/', ' ', $s) ?? ''); }

// ------------------------------------------------------------------ mail
/** Sends plain-text UTF-8 mail. mail_mode 'log' writes to data_dir/mail.log instead (local testing). */
function send_mail(string $to, string $subject, string $body, string $replyTo = ''): bool
{
    $c = cfg();
    $to = one_line($to);
    $subject = one_line($subject);
    if ($c['mail_mode'] === 'log') {
        $entry = "==== " . date('c') . "\nTo: $to\nReply-To: $replyTo\nSubject: $subject\n\n$body\n\n";
        return (bool)file_put_contents(data_dir() . '/mail.log', $entry, FILE_APPEND | LOCK_EX);
    }
    $from = one_line($c['mail_from']);
    $headers = [
        'From: ' . '=?UTF-8?B?' . base64_encode(site()['brand']) . '?= <' . $from . '>',
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'Content-Transfer-Encoding: 8bit',
    ];
    if ($replyTo !== '' && filter_var($replyTo, FILTER_VALIDATE_EMAIL)) $headers[] = 'Reply-To: ' . one_line($replyTo);
    $encSubject = '=?UTF-8?B?' . base64_encode($subject) . '?=';
    return @mail($to, $encSubject, $body, implode("\r\n", $headers), '-f' . $from);
}

/** Email text for one of the three templates, filled for a stored order. */
function order_email(array $order, array $items, string $template, array $extra = []): array
{
    $lang = clean_lang($order['lang']);
    $L = lang_strings($lang);
    $tpl = $L['email'][$template];
    $lines = [];
    foreach ($items as $it) {
        $lines[] = sprintf('%d x %s   %s', $it['qty'], $it['name'], money((int)$it['line_cents']));
    }
    if ($order['delivery'] === 'pickup') {
        $delivery = $L['cart']['delivery_pickup'];
        $address = '';
    } else {
        $delivery = $L['cart']['delivery_address'];
        $address = implode("\n", array_filter([
            $order['name'], $order['address1'], $order['address2'],
            trim(($order['postal'] ?? '') . ' ' . ($order['city'] ?? '')), country_name($order['country'], $lang),
        ]));
    }
    $vars = base_vars($lang) + [
        'ref' => $order['ref'], 'name' => $order['name'], 'items' => implode("\n", $lines),
        'subtotal' => money((int)$order['subtotal_cents']), 'shipping' => money((int)$order['shipping_cents']),
        'total' => money((int)$order['total_cents']), 'delivery' => $delivery, 'address' => $address,
        'tracking' => $order['tracking_number'] ?: '[tracking]', 'invoice' => $order['invoice_number'] ?: '[invoice]',
        'pay_until' => $order['hold_until'] ? date('d.m.Y. H:i', strtotime($order['hold_until'] . ' UTC')) : '',
    ] + $extra;
    return ['subject' => fill($tpl['subject'], $vars), 'body' => trim(fill($tpl['body'], $vars)) . "\n"];
}

function owner_email(array $order, array $items): array
{
    $lines = [];
    foreach ($items as $it) $lines[] = sprintf('%3d x %-40s %10s', $it['qty'], $it['name'], money((int)$it['line_cents']));
    $addr = $order['delivery'] === 'pickup'
        ? 'PICKUP in Piramatovci'
        : implode("\n", array_filter([$order['address1'], $order['address2'], trim($order['postal'] . ' ' . $order['city']), country_name($order['country'], 'en')]));
    $body = "New order request {$order['ref']}\n"
        . "Received: {$order['created_at']} UTC   Hold until: {$order['hold_until']} UTC\n\n"
        . implode("\n", $lines) . "\n\n"
        . "Bottles:  " . money((int)$order['subtotal_cents']) . "\n"
        . "Shipping: " . money((int)$order['shipping_cents']) . "   parcels: {$order['parcels']}  ({$order['weight_kg']} kg)\n"
        . "TOTAL:    " . money((int)$order['total_cents']) . "\n\n"
        . "Name:     {$order['name']}\nEmail:    {$order['email']}\nPhone:    {$order['phone']}\n"
        . "Language: {$order['lang']}\nCountry:  {$order['country']}\n\nDelivery:\n$addr\n\n"
        . "Note:\n{$order['note']}\n\n"
        . ($order['source'] ? "Tasting card: {$order['source']}\n\n" : '')
        . "Next step: send the payment request from the admin page within " . site()['selling']['payment_reply_hours'] . " hours.\n";
    return ['subject' => "[Order request] {$order['ref']}  " . money((int)$order['total_cents']) . "  {$order['name']}", 'body' => $body];
}

function load_order(int $id): ?array
{
    $st = db()->prepare('SELECT * FROM orders WHERE id = ?');
    $st->execute([$id]);
    $o = $st->fetch();
    return $o ?: null;
}

function load_items(int $orderId): array
{
    $st = db()->prepare('SELECT * FROM order_items WHERE order_id = ? ORDER BY id');
    $st->execute([$orderId]);
    return $st->fetchAll();
}
