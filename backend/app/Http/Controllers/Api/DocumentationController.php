<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\File;

class DocumentationController extends Controller
{
    /**
     * Serve OpenAPI spec (YAML). Swagger UI 4 accepts YAML.
     */
    public function spec(): Response
    {
        $path = storage_path('app/openapi.yaml');

        if (! File::exists($path)) {
            abort(404, 'OpenAPI spec not found');
        }

        return response(File::get($path), 200, [
            'Content-Type' => 'application/x-yaml',
            'Cache-Control' => 'public, max-age=300',
        ]);
    }

    /**
     * Swagger UI page that loads the OpenAPI spec.
     */
    public function index()
    {
        $specUrl = url('/api/documentation/spec');

        return view('api.documentation', [
            'specUrl' => $specUrl,
        ]);
    }
}
