# AutomatedQlikSenseLicenseDeallocator

Python script for automated license deallocation in a Qlik Sense Enterprise environment.

---

## Overview

This repository contains a Python-based automation that helps Qlik Sense administrators **identify and deallocate licenses for inactive users**. The primary goal is to reclaim unused licenses and maintain license hygiene in large or regulated Qlik Sense environments.

The current implementation focuses on **deallocating licenses for users who have not accessed Qlik Sense for more than 30 days**, based on user activity metadata retrieved from Qlik Sense APIs. The workflow is modular and can be easily extended to support additional scenarios such as:

* Deallocating licenses for a predefined list of users
* Deallocating licenses by user directory or role
* Running in audit-only mode (report without deallocation)
* Integrating with scheduling or alerting tools

---

## Key Features

* Secure authentication using **Qlik Sense certificates**
* Uses **Qlik Proxy Service (QPS)** session creation (recommended approach)
* Identifies inactive users based on last activity timestamp
* Automatically deallocates licenses for eligible users
* Configurable and environment-agnostic using a JSON configuration file

---

## Prerequisites

To use this script, you need the following:

1. **Python 3.8+**
2. **Qlik Sense Enterprise (Client-Managed)** environment
3. Access to Qlik Sense APIs (QPS and QRS)
4. A valid **Qlik Sense client certificate and key**
5. A service or admin account with permission to:

   * Read user activity
   * Modify license assignments

---

## Required Files

### 1. `LicenseCleanup.py`

The main Python script that:

* Authenticates with Qlik Sense
* Fetches licensed users
* Evaluates last activity date
* Deallocates licenses for inactive users

### 2. `config.json`

Holds all environment-specific and sensitive configuration values. Keeping this separate avoids hardcoding credentials.

Example structure:

```json
{
  "xrfkey": "<random_xrf_key>",
  "user_id": "<service_user>",
  "user_directory": "<user_directory>",
  "proxy_server": "https://<qlik_proxy_host>:4243",
  "client_cert": "client.pem",
  "client_key": "client_key.pem",
  "licenseType": "Professional",
  "url": "<qlik_sense_url>",
  "cookie_name": "X-Qlik-Session-<vp_name>"
}
```

---

## Configuration Parameters Explained

| Parameter        | Description                                                 |
| ---------------- | ----------------------------------------------------------- |
| `xrfkey`         | Anti-CSRF key required by Qlik APIs (must be 16 characters) |
| `user_id`        | Service account user ID used to create Qlik session         |
| `user_directory` | User directory of the service account                       |
| `proxy_server`   | Qlik Proxy Service (QPS) URL                                |
| `client_cert`    | Path to the client certificate file                         |
| `client_key`     | Path to the client private key file                         |
| `licenseType`    | License type to target (e.g., Professional or Analyzer)     |
| `url`            | Qlik Sense base URL                                         |
| `cookie_name`    | Session cookie name for the virtual proxy                   |

---

## How the Script Works (High-Level Flow)

1. **Session Creation**

   * Establishes a secure session with Qlik Sense via QPS using certificates
   * Stores session cookies for reuse

2. **User Retrieval**

   * Queries Qlik Repository Service (QRS) to retrieve licensed users
   * Filters users based on the configured license type

3. **Activity Evaluation**

   * Checks each user’s last activity timestamp
   * Compares it against the inactivity threshold (default: 30 days)

4. **License Deallocation**

   * Deallocates licenses for users exceeding the inactivity threshold
   * Logs actions for traceability

---

## Inactivity Threshold

* Default threshold: **30 days**
* This value is defined in the script and can be easily modified

Example use cases:

* 15 days for non-production environments
* 60–90 days for business-critical environments

---

## Customization Options

You can extend or modify the workflow to:

* Deallocate licenses based on a **static user list**
* Exclude specific users or directories
* Run the script in **dry-run mode** (no deallocation)
* Export inactive user reports to CSV
* Integrate with schedulers like Windows Task Scheduler or Control-M

---

## Security Considerations

* Store certificates securely and restrict file permissions
* Never commit `config.json` or certificate files to source control
* Use a dedicated service account with minimum required privileges

---

## Recommended Usage

* Test in a **non-production** environment first
* Run initially in audit-only mode to validate results
* Schedule during off-peak hours
* Maintain logs for compliance and audit requirements

---

## Disclaimer

This script modifies license assignments in Qlik Sense. Use with caution. Always validate behavior in a lower environment before running in production.

---

## Author

**Abhijith V**

---

## License

This project can be licensed as per your organization’s standards. Add an open-source license if you plan to distribute it publicly.
