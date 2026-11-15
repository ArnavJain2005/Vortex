// Template for secrets.h. Copy this file to secrets.h in the same folder
// (secrets.h is gitignored) and replace the password. WPA2 needs at least
// 8 characters; the sketch refuses to compile with a shorter one.
#pragma once

// Optional: soft-AP name shown to the dashboard laptop.
#define DASHBOARD_SSID_VALUE "PHYS-XR-Station"

// Required: soft-AP password.
#define DASHBOARD_PASSWORD_VALUE "change-me-please"
