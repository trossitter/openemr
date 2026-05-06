<?php

/**
 * Returns the current session patient PID and name as JSON.
 * Called by the Co-Pilot JavaScript panel every 3 seconds to
 * detect when the physician navigates to a new patient chart.
 */

$ignoreAuth = false;
require_once dirname(__FILE__, 5) . '/interface/globals.php';

use OpenEMR\Common\Session\SessionWrapperFactory;

header('Content-Type: application/json');

$session = SessionWrapperFactory::getInstance()->getActiveSession();
$pid = $session->get('pid') ? (int)$session->get('pid') : null;
$name = null;

if ($pid) {
    $row = sqlQuery(
        "SELECT fname, lname FROM patient_data WHERE pid = ? LIMIT 1",
        [$pid]
    );
    if ($row) {
        $name = $row['fname'] . ' ' . $row['lname'];
    }
}

echo json_encode(['pid' => $pid, 'name' => $name]);
