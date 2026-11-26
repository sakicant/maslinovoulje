<?php
// GET -> signed timestamp for the waitlist form (timing check).
declare(strict_types=1);
require __DIR__ . '/../private/lib.php';

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
echo json_encode(['token' => form_token()]);
