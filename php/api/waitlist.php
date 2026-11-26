<?php
// POST {email, consent, website, token, lang, src} -> stores one waitlist address.
declare(strict_types=1);
require __DIR__ . '/../private/lib.php';

$in = json_in();
$lang = clean_lang($in['lang'] ?? '');
$L = lang_strings($lang)['waitlist'];
$ok = ['ok' => true, 'message' => $L['thanks']];

if (str_field($in, 'website', 200) !== '') json_out($ok);
if (!rate_limit('waitlist', 5, 900)) json_out(['ok' => false, 'message' => fill(lang_strings($lang)['cart']['error_rate'], base_vars($lang))], 429);
if (!token_ok($in['token'] ?? null, 3)) json_out(['ok' => false, 'message' => $L['error']]);

$email = one_line(str_field($in, 'email', 160));
if (!filter_var($email, FILTER_VALIDATE_EMAIL) || empty($in['consent'])) json_out(['ok' => false, 'message' => $L['error']]);
$src = preg_match('/^[A-Za-z0-9_-]{1,40}$/', (string)($in['src'] ?? '')) ? (string)$in['src'] : '';

db()->prepare('INSERT OR IGNORE INTO waitlist (email, lang, source, created_at) VALUES (?, ?, ?, ?)')
    ->execute([mb_strtolower($email), $lang, $src, now()]);
json_out($ok);
