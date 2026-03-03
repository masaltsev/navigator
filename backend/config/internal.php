<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Internal API Token
    |--------------------------------------------------------------------------
    |
    | Bearer token used to authenticate requests from the AI pipeline
    | (Harvester) to the internal import API. Must match the value
    | configured in the Harvester's CORE_API_TOKEN env variable.
    |
    */

    'api_token' => env('INTERNAL_API_TOKEN'),

];
