#!/usr/bin/env php
<?php

/**
 * Harman Kardon Remote Control Script
 * 
 * Usage:
 *   php control.php --id 192.168.1.112 --source TV
 *   php control.php --id 192.168.1.112 --delta 5
 * 
 * Options:
 *   --id        Device IP/host
 *   --port      Device port (default: 10025)
 *   --zone      Zone name (default: "Main Zone")
 *   --source    Select input source (exact name as in receiver menu; can be mapped by caller)
 *   --delta     Relative volume change in steps (+/-). (HKAPI doesn't support absolute volume)
 */

// Include the autoloader
$loader = require __DIR__ . '/HKAPI/vendor/autoload.php';

// Parse command line arguments
$options = getopt('', ['id:', 'port:', 'zone:', 'source:', 'delta:']);

$deviceIp = $options['id'] ?? null;
$devicePort = isset($options['port']) ? (int)$options['port'] : 10025;
$zoneName = $options['zone'] ?? 'Main Zone';

if (!$deviceIp) {
    echo "Error: --id is required\n";
    exit(1);
}

// Validate and process --source option
$source = null;
if (isset($options['source'])) {
    $source = (string)$options['source'];
    if ($source === '') {
        echo "Error: --source must be non-empty\n";
        exit(1);
    }
}

// Validate and process --delta option
$delta = null;
if (isset($options['delta'])) {
    if (!is_numeric($options['delta'])) {
        echo "Error: --delta must be a number (e.g. 5 or -5)\n";
        exit(1);
    }
    $delta = (int)$options['delta'];
    if ($delta === 0) {
        // no-op is allowed but pointless
    }
}

// Check if at least one option is provided
if ($source === null && $delta === null) {
    echo "Usage:\n";
    echo "  php control.php --id 192.168.1.112 --source TV\n";
    echo "  php control.php --id 192.168.1.112 --delta 5\n";
    echo "\n";
    echo "Options:\n";
    echo "  --id        Device IP/host\n";
    echo "  --port      Device port (default: 10025)\n";
    echo "  --zone      Zone name (default: \"Main Zone\")\n";
    echo "  --source    Select input source (exact name as in receiver menu)\n";
    echo "  --delta     Relative volume change in steps (+/-)\n";
    echo "\n";
    echo "At least one option must be provided.\n";
    exit(1);
}

try {
    // Initialize API connection
    $hk = new \HKAPI\API($deviceIp, $devicePort, new \HKAPI\Devices\AVR());
    $zone = $hk->zone($zoneName);
    
    // Turn on the device if needed (some operations require device to be on)
    // Note: This might wake up the device if it's in standby
    
    // Set source if requested
    if ($source !== null) {
        echo "Setting source to: {$source}\n";
        $zone->selectSource($source);
        // Small delay to ensure command is processed
        usleep(500000); // 0.5 seconds
    }
    
    // Set volume if requested
    if ($delta !== null) {
        echo "Adjusting volume (delta steps: {$delta})\n";
        echo "Note: HKAPI supports only incremental volume changes (volumeUp/volumeDown).\n";

        $steps = abs($delta);
        // Limit adjustments to prevent excessive API calls
        $steps = min($steps, 50);

        if ($steps === 0) {
            echo "No changes requested.\n";
        } else if ($delta > 0) {
            echo "Making {$steps} volume up adjustments...\n";
            for ($i = 0; $i < $steps; $i++) {
                $zone->volumeUp();
                usleep(100000); // 0.1 second delay between adjustments
            }
        } else {
            echo "Making {$steps} volume down adjustments...\n";
            for ($i = 0; $i < $steps; $i++) {
                $zone->volumeDown();
                usleep(100000); // 0.1 second delay between adjustments
            }
        }

        echo "Volume adjustments completed.\n";
    }
    
    echo "Command completed successfully.\n";
    
} catch (\HKAPI\Exceptions\HKAPISocketException $e) {
    echo "Error: Could not connect to device at {$deviceIp}:{$devicePort}\n";
    echo "Details: " . $e->getMessage() . "\n";
    exit(1);
} catch (\HKAPI\Exceptions\HKAPIInvalidZoneException $e) {
    echo "Error: Invalid zone '{$zoneName}'\n";
    echo "Details: " . $e->getMessage() . "\n";
    exit(1);
} catch (\Exception $e) {
    echo "Error: " . $e->getMessage() . "\n";
    exit(1);
}
