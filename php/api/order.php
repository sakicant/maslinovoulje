<?php
/**
 * POST order request. Stores it, emails the customer ("order request received",
 * no payment taken) and the owner. Payment is arranged by hand afterwards.
 */
declare(strict_types=1);
require __DIR__ . '/../private/lib.php';

$in = json_in();
$lang = clean_lang($in['lang'] ?? '');

// Honeypot: bots fill every field. Answer like a success so they move on, store nothing.
if (str_field($in, 'website', 200) !== '') {
    json_out(['ok' => true, 'ref' => date('Y') . '-' . str_pad((string)random_int(1000, 9999), 4, '0', STR_PAD_LEFT)]);
}
// Attempts (typos included) and saved orders are limited separately.
if (!rate_limit('order_try', 20, 900)) json_out(['ok' => false, 'error' => 'rate'], 429);
if (!token_ok($in['token'] ?? null, 4)) json_out(['ok' => false, 'error' => 'token']);
if (empty(site()['selling']['enabled'])) json_out(['ok' => false, 'error' => 'closed']);

$country = str_field($in, 'country', 2);
$delivery = ($in['delivery'] ?? '') === 'pickup' ? 'pickup' : 'address';
$q = quote(is_array($in['items'] ?? null) ? $in['items'] : [], $country, $delivery, $lang);
if (!$q['ok']) json_out($q);

$f = [
    'name' => one_line(str_field($in, 'name', 120)),
    'email' => one_line(str_field($in, 'email', 160)),
    'phone' => one_line(str_field($in, 'phone', 40)),
    'address' => one_line(str_field($in, 'address', 160)),
    'address2' => one_line(str_field($in, 'address2', 160)),
    'postal' => one_line(str_field($in, 'postal', 20)),
    'city' => one_line(str_field($in, 'city', 80)),
    'note' => str_field($in, 'note', 1000),
];
$src = preg_match('/^[A-Za-z0-9_-]{1,40}$/', (string)($in['src'] ?? '')) ? (string)$in['src'] : '';

$bad = [];
if (mb_strlen($f['name']) < 2) $bad[] = 'name';
if (!filter_var($f['email'], FILTER_VALIDATE_EMAIL)) $bad[] = 'email';
if ($f['phone'] !== '' && !preg_match('/^[0-9 +()\/.-]{5,40}$/', $f['phone'])) $bad[] = 'phone';
if ($delivery === 'address') {
    foreach (['address', 'postal', 'city'] as $k) if (mb_strlen($f[$k]) < 2) $bad[] = $k;
}
if (empty($in['consent'])) $bad[] = 'consent';
if ($bad) json_out(['ok' => false, 'error' => 'fields', 'fields' => $bad]);

if (!rate_limit('order_saved', 5, 3600)) json_out(['ok' => false, 'error' => 'rate'], 429);

$hold = gmdate('Y-m-d H:i:s', time() + 3600 * (int)site()['selling']['hold_hours']);
$pdo = db();
try {
    $pdo->beginTransaction();
    $pdo->prepare('INSERT INTO orders (created_at, updated_at, status, lang, name, email, phone, address1, address2,
            postal, city, country, delivery, note, source, currency, subtotal_cents, shipping_cents, total_cents,
            parcels, weight_kg, hold_until, ip_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
        ->execute([
            now(), now(), 'new', $lang, $f['name'], $f['email'], $f['phone'],
            $delivery === 'address' ? $f['address'] : '', $delivery === 'address' ? $f['address2'] : '',
            $delivery === 'address' ? $f['postal'] : '', $delivery === 'address' ? $f['city'] : '',
            $country, $delivery, $f['note'], $src, 'EUR', $q['subtotal'], $q['shipping'], $q['total'],
            implode(',', $q['parcels']), $q['weight_kg'], $hold, client_ip_hash(),
        ]);
    $id = (int)$pdo->lastInsertId();
    $ref = site()['harvest_year'] . '-' . str_pad((string)$id, 4, '0', STR_PAD_LEFT);
    $pdo->prepare('UPDATE orders SET ref = ? WHERE id = ?')->execute([$ref, $id]);
    $ins = $pdo->prepare('INSERT INTO order_items (order_id, item_id, item_type, name, qty, unit_cents, line_cents, bottles)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    foreach ($q['lines'] as $l) {
        $ins->execute([$id, $l['id'], $l['type'], $l['name'], $l['qty'], $l['unit'], $l['line'], json_encode($l['bottles'])]);
    }
    order_event($id, 'created', 'order request from website');
    $pdo->commit();
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    error_log('order save failed: ' . $e->getMessage());
    json_out(['ok' => false, 'error' => 'server'], 500);
}

$order = load_order($id);
$items = load_items($id);
$c = cfg();

$mail = order_email($order, $items, 'order_received');
$sentCustomer = send_mail($order['email'], $mail['subject'], $mail['body'], $c['reply_to'] ?: $c['owner_email']);
$ownerMail = owner_email($order, $items);
$sentOwner = send_mail($c['owner_email'], $ownerMail['subject'], $ownerMail['body'], $order['email']);
order_event($id, 'mail', 'customer:' . ($sentCustomer ? 'sent' : 'FAILED') . ' owner:' . ($sentOwner ? 'sent' : 'FAILED'));

json_out(['ok' => true, 'ref' => $ref]);
