<?php
// POST {items:[{id,qty}], country, delivery, lang} -> totals calculated on the server.
declare(strict_types=1);
require __DIR__ . '/../private/lib.php';

$in = json_in();
if (!rate_limit('quote', 120, 600)) json_out(['ok' => false, 'error' => 'rate'], 429);
if (empty(site()['selling']['enabled'])) json_out(['ok' => false, 'error' => 'closed']);

$lang = clean_lang($in['lang'] ?? '');
$q = quote(is_array($in['items'] ?? null) ? $in['items'] : [], (string)($in['country'] ?? ''), (string)($in['delivery'] ?? ''), $lang);
if (!$q['ok']) json_out($q);

json_out([
    'ok' => true,
    'lines' => array_map(fn($l) => ['id' => $l['id'], 'qty' => $l['qty'], 'name' => $l['name'], 'unit' => $l['unit'], 'line' => $l['line']], $q['lines']),
    'subtotal' => $q['subtotal'],
    'shipping' => $q['shipping'],
    'total' => $q['total'],
    'parcels' => count($q['parcels']),
    'token' => form_token(),
]);
