<?php
/**
 * Returns the current session patient PID and name as JSON.
 * Called by the Co-Pilot JavaScript panel every 3 seconds to
 * detect when the physician navigates to a new patient chart.
 */

// Bootstrap OpenEMR session context
$ignoreAuth = false;
require_once dirname(__FILE__, 5) . '/interface/globals.php';

header('Content-Type: application/json');

$pid = isset($_SESSION['pid']) ? (int)$_SESSION['pid'] : null;
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
