<?php

/**
 * Clinical Co-Pilot — OpenEMR Module Bootstrap
 *
 * Registers the Co-Pilot panel into OpenEMR's main tab frame.
 * The panel is injected as a persistent floating sidebar visible
 * across all encounter views, using the Main\Tabs\RenderEvent hook.
 */

namespace OpenEMR\Modules\CopilotModule;

$classLoader->registerNamespaceIfNotExists(
    'OpenEMR\\Modules\\CopilotModule\\',
    __DIR__ . DIRECTORY_SEPARATOR . 'src'
);

$bootstrap = new Bootstrap($eventDispatcher);
$bootstrap->subscribeToEvents();
