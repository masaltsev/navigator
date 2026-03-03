<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class AuthenticateInternalApi
{
    /**
     * Validate the Bearer token against the configured internal API token.
     *
     * Rejects the request with 401 if no token is provided, or 403 if
     * the token does not match. Uses hash_equals for timing-safe comparison.
     */
    public function handle(Request $request, Closure $next): Response
    {
        $configuredToken = config('internal.api_token');

        if (empty($configuredToken)) {
            return response()->json([
                'message' => 'Internal API authentication is not configured.',
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }

        $bearerToken = $request->bearerToken();

        if (empty($bearerToken)) {
            return response()->json([
                'message' => 'Unauthorized. Bearer token required.',
            ], Response::HTTP_UNAUTHORIZED);
        }

        if (! hash_equals($configuredToken, $bearerToken)) {
            return response()->json([
                'message' => 'Forbidden. Invalid API token.',
            ], Response::HTTP_FORBIDDEN);
        }

        return $next($request);
    }
}
