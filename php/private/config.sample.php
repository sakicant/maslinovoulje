<?php
/**
 * Copy to private/config.php ON THE SERVER and fill in. config.php is gitignored.
 * For local testing, put a config.php in the project root; build.py copies it into dist/private/.
 */
return [
    // Long random string (at least 32 characters). Signs form tokens.
    // Generate one with:  php -r "echo bin2hex(random_bytes(32));"
    'secret' => 'CHANGE_ME_TO_A_LONG_RANDOM_STRING',

    // Owner inbox for new order requests. OPEN: final address.
    'owner_email' => 'info@sakicolive.com',
    // Sender address. Must be on the site's own domain so mail is not flagged as spoofed.
    'mail_from' => 'noreply@sakicolive.com',
    // Where customer replies go. Empty = owner_email.
    'reply_to' => '',

    // 'mail' sends with PHP mail(). 'log' writes every email to data_dir/mail.log (local testing).
    'mail_mode' => 'mail',

    // Where orders.sqlite, rate-limit files and the mail log live.
    // Best: a folder OUTSIDE the public web root, e.g. '/home/USER/olive-data'.
    // The default (private/storage) is protected by private/.htaccess.
    'data_dir' => __DIR__ . '/storage',

    // Admin login. Create the hash with:
    //   php -r "echo password_hash('your-password', PASSWORD_DEFAULT);"
    'admin_password_hash' => '',
];
