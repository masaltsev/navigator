<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Database dump directory (PostgreSQL only)
    |--------------------------------------------------------------------------
    |
    | Production backups must NOT live under the web root or in git. Default is
    | deploy home — override with DB_BACKUP_DIRECTORY in .env if needed.
    |
    */

    'database_directory' => env('DB_BACKUP_DIRECTORY', '/home/deploy/backups/navigator'),

    'retention_days' => (int) env('DB_BACKUP_RETENTION_DAYS', 14),

];
