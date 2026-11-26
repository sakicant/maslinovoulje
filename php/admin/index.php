<?php
/**
 * Order admin. Password from private/config.php (admin_password_hash).
 * List order requests, change status, add invoice and tracking numbers,
 * copy the filled payment-request and shipped emails.
 */
declare(strict_types=1);
require __DIR__ . '/../private/lib.php';

header('X-Robots-Tag: noindex, nofollow');
header('Cache-Control: no-store');
header("Content-Security-Policy: default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'");

session_name('olive_admin');
session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'httponly' => true, 'samesite' => 'Strict',
    'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off']);
session_start();

function h($s): string { return htmlspecialchars((string)$s, ENT_QUOTES, 'UTF-8'); }
function csrf(): string { return $_SESSION['csrf'] ??= bin2hex(random_bytes(16)); }
function csrf_ok(): bool { return hash_equals($_SESSION['csrf'] ?? '', (string)($_POST['csrf'] ?? '')); }
function self_url(array $q = []): string { return strtok($_SERVER['REQUEST_URI'], '?') . ($q ? '?' . http_build_query($q) : ''); }
function go(array $q = []): void { header('Location: ' . self_url($q)); exit; }

$hash = cfg()['admin_password_hash'] ?? '';
$action = $_POST['action'] ?? '';

if ($action === 'login') {
    if (!rate_limit('admin_login', 8, 900)) { $loginError = 'Too many attempts. Wait 15 minutes.'; }
    elseif ($hash !== '' && csrf_ok() && password_verify((string)($_POST['password'] ?? ''), $hash)) {
        session_regenerate_id(true);
        $_SESSION['admin'] = true;
        $_SESSION['seen'] = time();
        go();
    } else { $loginError = 'Wrong password.'; }
}
if ($action === 'logout' && csrf_ok()) { $_SESSION = []; session_destroy(); go(); }

$authed = !empty($_SESSION['admin']) && (time() - ($_SESSION['seen'] ?? 0)) < 8 * 3600;
if ($authed) $_SESSION['seen'] = time();

$STATUS_LABEL = ['new' => 'New', 'payment_requested' => 'Payment requested', 'paid' => 'Paid', 'shipped' => 'Shipped', 'cancelled' => 'Cancelled'];

if ($authed && $action === 'update' && csrf_ok()) {
    $id = (int)($_POST['id'] ?? 0);
    $o = load_order($id);
    if ($o) {
        $status = in_array($_POST['status'] ?? '', ORDER_STATUSES, true) ? $_POST['status'] : $o['status'];
        $fields = [
            'status' => $status,
            'invoice_number' => mb_substr(trim((string)($_POST['invoice_number'] ?? '')), 0, 60),
            'tracking_number' => mb_substr(trim((string)($_POST['tracking_number'] ?? '')), 0, 80),
            'payment_method' => mb_substr(trim((string)($_POST['payment_method'] ?? '')), 0, 60),
            'admin_note' => mb_substr((string)($_POST['admin_note'] ?? ''), 0, 4000),
            'updated_at' => now(),
        ];
        if ($status === 'paid' && !$o['paid_at']) $fields['paid_at'] = now();
        if ($status === 'shipped' && !$o['shipped_at']) $fields['shipped_at'] = now();
        $sets = implode(', ', array_map(fn($k) => "$k = :$k", array_keys($fields)));
        db()->prepare("UPDATE orders SET $sets WHERE id = :id")->execute($fields + ['id' => $id]);
        $changes = [];
        foreach (['status', 'invoice_number', 'tracking_number', 'payment_method'] as $k) {
            if ((string)$o[$k] !== (string)$fields[$k]) $changes[] = "$k: " . ($o[$k] ?: '-') . ' -> ' . ($fields[$k] ?: '-');
        }
        if ($changes) order_event($id, 'admin_update', implode('; ', $changes));
        go(['id' => $id, 'saved' => 1]);
    }
}

$view = isset($_GET['id']) ? 'order' : (isset($_GET['waitlist']) ? 'waitlist' : 'list');
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Orders | <?= h(site()['brand']) ?></title>
<style>
  :root { --g:#2E4A2B; --s:#E3E8D8; --l:#cfd7c2; }
  * { box-sizing: border-box; }
  body { margin: 0; font: 15px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #141414; background: #fff; }
  header { background: var(--g); color: #fff; padding: 10px 16px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
  header a, header button { color: #fff; }
  header strong { margin-right: auto; }
  main { max-width: 1100px; margin: 0 auto; padding: 16px; }
  a { color: var(--g); }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--l); vertical-align: top; }
  .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .tabs { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .tabs a { padding: 6px 10px; border: 1px solid var(--l); border-radius: 4px; text-decoration: none; }
  .tabs a.on { background: var(--g); color: #fff; border-color: var(--g); }
  .st { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; background: var(--s); }
  .st-new { background: #fff3c4; } .st-paid { background: #cde8c5; } .st-shipped { background: #d6e4f5; } .st-cancelled { background: #eee; color: #777; }
  .grid { display: grid; gap: 16px; }
  @media (min-width: 860px) { .grid { grid-template-columns: 1fr 1fr; } }
  .box { border: 1px solid var(--l); border-radius: 6px; padding: 14px; }
  label { display: block; font-weight: 600; font-size: 13px; margin: 10px 0 4px; }
  input, select, textarea { width: 100%; padding: 9px; font: inherit; border: 1px solid #9aa58f; border-radius: 4px; }
  textarea { min-height: 80px; }
  textarea.mail { min-height: 260px; font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
  button.btn, a.btn { display: inline-block; background: var(--g); color: #fff; border: 0; padding: 10px 16px; border-radius: 4px; font: inherit; font-weight: 600; cursor: pointer; text-decoration: none; margin-top: 10px; }
  .ok { background: #cde8c5; padding: 8px 12px; border-radius: 4px; }
  .err { background: #f6d2cc; padding: 8px 12px; border-radius: 4px; }
  .muted { color: #666; font-size: 13px; }
  .linkbtn { background: none; border: 0; text-decoration: underline; cursor: pointer; font: inherit; }
  @media (max-width: 700px) { .hide-sm { display: none; } }
</style>
</head>
<body>
<?php if (!$authed): ?>
<main style="max-width:380px;margin-top:10vh">
  <h1>Orders</h1>
  <?php if ($hash === ''): ?><p class="err">No admin password set. Add admin_password_hash to private/config.php.</p><?php endif; ?>
  <?php if (!empty($loginError)): ?><p class="err"><?= h($loginError) ?></p><?php endif; ?>
  <form method="post">
    <input type="hidden" name="action" value="login">
    <input type="hidden" name="csrf" value="<?= h(csrf()) ?>">
    <label for="pw">Password</label>
    <input id="pw" type="password" name="password" autocomplete="current-password" required autofocus>
    <button class="btn" type="submit">Log in</button>
  </form>
</main>
<?php exit; endif; ?>

<header>
  <strong><?= h(site()['brand']) ?> · orders</strong>
  <a href="<?= h(self_url()) ?>">Orders</a>
  <a href="<?= h(self_url(['waitlist' => 1])) ?>">Waitlist</a>
  <form method="post" style="margin:0">
    <input type="hidden" name="action" value="logout"><input type="hidden" name="csrf" value="<?= h(csrf()) ?>">
    <button class="linkbtn" type="submit">Log out</button>
  </form>
</header>
<main>
<?php if ($view === 'list'):
    $filter = in_array($_GET['status'] ?? '', ORDER_STATUSES, true) ? $_GET['status'] : '';
    $counts = [];
    foreach (db()->query('SELECT status, COUNT(*) n FROM orders GROUP BY status') as $r) $counts[$r['status']] = (int)$r['n'];
    $sql = 'SELECT * FROM orders' . ($filter ? ' WHERE status = ?' : '') . ' ORDER BY id DESC LIMIT 300';
    $st = db()->prepare($sql);
    $st->execute($filter ? [$filter] : []);
    $orders = $st->fetchAll();
?>
  <div class="tabs">
    <a href="<?= h(self_url()) ?>" class="<?= $filter === '' ? 'on' : '' ?>">All (<?= array_sum($counts) ?>)</a>
    <?php foreach ($STATUS_LABEL as $k => $label): ?>
      <a href="<?= h(self_url(['status' => $k])) ?>" class="<?= $filter === $k ? 'on' : '' ?>"><?= h($label) ?> (<?= $counts[$k] ?? 0 ?>)</a>
    <?php endforeach; ?>
  </div>
  <?php if (!$orders): ?><p>No orders yet.</p><?php else: ?>
  <table>
    <thead><tr><th>Ref</th><th>Status</th><th>Customer</th><th class="hide-sm">Country</th><th class="num">Total</th><th class="hide-sm">Received (UTC)</th></tr></thead>
    <tbody>
    <?php foreach ($orders as $o):
        $overdue = $o['status'] === 'new' && strtotime($o['created_at'] . ' UTC') < time() - 3600 * (int)site()['selling']['payment_reply_hours']; ?>
      <tr>
        <td><a href="<?= h(self_url(['id' => $o['id']])) ?>"><?= h($o['ref']) ?></a></td>
        <td><span class="st st-<?= h($o['status']) ?>"><?= h($STATUS_LABEL[$o['status']] ?? $o['status']) ?></span><?= $overdue ? ' <span class="muted">reply overdue</span>' : '' ?></td>
        <td><?= h($o['name']) ?><br><span class="muted"><?= h($o['email']) ?></span></td>
        <td class="hide-sm"><?= h($o['country']) ?><?= $o['delivery'] === 'pickup' ? ' (pickup)' : '' ?></td>
        <td class="num"><?= h(money((int)$o['total_cents'])) ?></td>
        <td class="hide-sm"><?= h(substr($o['created_at'], 0, 16)) ?></td>
      </tr>
    <?php endforeach; ?>
    </tbody>
  </table>
  <?php endif; ?>

<?php elseif ($view === 'order'):
    $o = load_order((int)$_GET['id']);
    if (!$o) { echo '<p>Order not found.</p></main></body></html>'; exit; }
    $items = load_items((int)$o['id']);
    $pay = order_email($o, $items, 'payment_request');
    $shipped = order_email($o, $items, 'shipped');
    $ev = db()->prepare('SELECT * FROM order_events WHERE order_id = ? ORDER BY id');
    $ev->execute([$o['id']]);
?>
  <p><a href="<?= h(self_url()) ?>">&larr; All orders</a></p>
  <?php if (isset($_GET['saved'])): ?><p class="ok">Saved.</p><?php endif; ?>
  <h1 style="margin:.2em 0">Order <?= h($o['ref']) ?> <span class="st st-<?= h($o['status']) ?>"><?= h($STATUS_LABEL[$o['status']]) ?></span></h1>
  <p class="muted">Received <?= h($o['created_at']) ?> UTC · bottles held until <?= h($o['hold_until']) ?> UTC · language <?= h($o['lang']) ?><?= $o['source'] ? ' · tasting card ' . h($o['source']) : '' ?></p>
  <div class="grid">
    <div class="box">
      <table>
        <?php foreach ($items as $it): ?>
          <tr><td><?= (int)$it['qty'] ?> &times; <?= h($it['name']) ?></td><td class="num"><?= h(money((int)$it['line_cents'])) ?></td></tr>
        <?php endforeach; ?>
        <tr><td>Shipping (<?= h($o['parcels'] ?: 'pickup') ?>, <?= h($o['weight_kg']) ?> kg)</td><td class="num"><?= h(money((int)$o['shipping_cents'])) ?></td></tr>
        <tr><th>Total</th><th class="num"><?= h(money((int)$o['total_cents'])) ?></th></tr>
      </table>
      <p><strong><?= h($o['name']) ?></strong><br>
        <a href="mailto:<?= h($o['email']) ?>"><?= h($o['email']) ?></a><?= $o['phone'] ? '<br>' . h($o['phone']) : '' ?></p>
      <p><?php if ($o['delivery'] === 'pickup'): ?><strong>Pickup in Piramatovci</strong><br><?= h(country_name($o['country'], 'en')) ?>
        <?php else: ?><?= h($o['address1']) ?><br><?= $o['address2'] ? h($o['address2']) . '<br>' : '' ?><?= h($o['postal'] . ' ' . $o['city']) ?><br><?= h(country_name($o['country'], 'en')) ?><?php endif; ?></p>
      <?php if ($o['note']): ?><p><strong>Note:</strong><br><?= nl2br(h($o['note'])) ?></p><?php endif; ?>
    </div>
    <form class="box" method="post">
      <input type="hidden" name="action" value="update"><input type="hidden" name="csrf" value="<?= h(csrf()) ?>">
      <input type="hidden" name="id" value="<?= (int)$o['id'] ?>">
      <label for="status">Status</label>
      <select id="status" name="status">
        <?php foreach ($STATUS_LABEL as $k => $label): ?><option value="<?= h($k) ?>" <?= $o['status'] === $k ? 'selected' : '' ?>><?= h($label) ?></option><?php endforeach; ?>
      </select>
      <label for="pm">Payment method</label>
      <input id="pm" name="payment_method" value="<?= h($o['payment_method']) ?>" placeholder="card link / bank transfer / cash at pickup">
      <label for="inv">Invoice number</label>
      <input id="inv" name="invoice_number" value="<?= h($o['invoice_number']) ?>">
      <label for="trk">Tracking number</label>
      <input id="trk" name="tracking_number" value="<?= h($o['tracking_number']) ?>">
      <label for="note">Internal note</label>
      <textarea id="note" name="admin_note"><?= h($o['admin_note']) ?></textarea>
      <button class="btn" type="submit">Save</button>
      <p class="muted">Paid: <?= h($o['paid_at'] ?: '-') ?> · Shipped: <?= h($o['shipped_at'] ?: '-') ?></p>
    </form>
  </div>

  <h2>Emails to copy</h2>
  <p class="muted">Fill in the payment details by hand before sending. Save invoice and tracking numbers first, then reload, so they appear in the shipped email.</p>
  <div class="grid">
    <?php foreach (['Payment request' => $pay, 'Shipped' => $shipped] as $title => $m): ?>
    <div class="box">
      <strong><?= h($title) ?></strong>
      <label>Subject</label><input readonly value="<?= h($m['subject']) ?>">
      <label>Body</label><textarea class="mail" readonly><?= h($m['body']) ?></textarea>
      <a class="btn" href="mailto:<?= h(rawurlencode($o['email'])) ?>?subject=<?= h(rawurlencode($m['subject'])) ?>&amp;body=<?= h(rawurlencode($m['body'])) ?>">Open in mail app</a>
    </div>
    <?php endforeach; ?>
  </div>

  <h2>History</h2>
  <table>
    <?php foreach ($ev as $e): ?><tr><td class="muted" style="white-space:nowrap"><?= h($e['at']) ?></td><td><?= h($e['event']) ?></td><td><?= h($e['detail']) ?></td></tr><?php endforeach; ?>
  </table>

<?php else:
    $rows = db()->query('SELECT * FROM waitlist ORDER BY id DESC')->fetchAll(); ?>
  <h1>Waitlist (<?= count($rows) ?>)</h1>
  <?php foreach (site()['languages'] as $lg):
      $emails = array_column(array_filter($rows, fn($r) => $r['lang'] === $lg), 'email'); if (!$emails) continue; ?>
    <label><?= h(strtoupper($lg)) ?>: <?= count($emails) ?> addresses (copy into BCC)</label>
    <textarea readonly><?= h(implode(', ', $emails)) ?></textarea>
  <?php endforeach; ?>
  <table style="margin-top:16px">
    <thead><tr><th>Email</th><th>Lang</th><th class="hide-sm">Card</th><th>Added (UTC)</th></tr></thead>
    <?php foreach ($rows as $r): ?><tr><td><?= h($r['email']) ?></td><td><?= h($r['lang']) ?></td><td class="hide-sm"><?= h($r['source']) ?></td><td><?= h(substr($r['created_at'], 0, 16)) ?></td></tr><?php endforeach; ?>
  </table>
<?php endif; ?>
</main>
</body>
</html>
