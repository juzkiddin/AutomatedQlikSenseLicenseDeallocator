import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("license_cleanup")
logger.addHandler(logging.NullHandler())


class LicenseCleanupError(RuntimeError):
    """Raised when a recoverable error occurs while fetching license data."""

def generate_session(xrfkey,user_id,user_directory,proxy_server,client_cert,client_key):
    SESSION_ID = str(uuid.uuid4())
    session = requests.Session()
    session_url = f"{proxy_server}/qps/session?xrfkey={xrfkey}"
    session_headers = {
    "X-Qlik-Xrfkey": xrfkey,
    "Content-Type": "application/json"
    }
    session_payload = {
    "UserDirectory": user_directory,
    "UserId": user_id,
    "Attributes": [],
    "SessionId": SESSION_ID
    }
    session_response = session.post(
    session_url,
    json=session_payload,
    headers=session_headers,
    cert=(client_cert, client_key),
    verify=False
    )
    return SESSION_ID

def delete_session(xrfkey,proxy_server,client_cert,client_key,session_id):
    session = requests.Session()
    session_url = f"{proxy_server}/qps/session/{session_id}?xrfkey={xrfkey}"
    session_headers = {
    "X-Qlik-Xrfkey": xrfkey,
    "Content-Type": "application/json"
    }
    session_response = session.delete(
    session_url,
    headers=session_headers,
    cert=(client_cert, client_key),
    verify=False
    )
    logger.info(f"Deleted session for Session ID : {session_id}")
    return 0


def setup_logger():
    log_dir = Path(__file__).resolve().parent / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    log_file = log_dir / f"{timestamp}.log"

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger = logging.getLogger("license_cleanup")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False

    logger.info("Logging initialized. Output file: %s", log_file)
    return logger

def selection_id_del (xrfkey,selection_id,headers,url):
    url = f"https://{url}/qrs/Selection/{selection_id}?xrfkey={xrfkey}"
    try:
        response = requests.delete(url, headers=headers, verify=False, timeout=120)
        if 200 <= response.status_code < 300:
            return 1
        else:
            error_text = f"{response.status_code}: {response.text}"
            logger.error("Selection delete failed with status code %s", error_text)
            return 0
    except requests.exceptions.RequestException as e:
        logger.error("Selection delete request failed: %s", e)
        return 0

def allocation_id(xrfkey, url, licensetype, headers):
    if not licensetype:
        raise ValueError("Parameter 'licensetype' is required.")

    url = f"https://{url}/qrs/License/{licensetype}AccessType/table?orderAscending=true&skip=0&sortColumn=lastUsed&take=2000&xrfkey={xrfkey}"
    body_object = {
    "entity": f"License.{licensetype}AccessType",
    "columns": [
        {
            "name": "id",
            "columnType": "Property",
            "definition": "id"
        },
        {
            "name": "user.name",
            "columnType": "Property",
            "definition": "user.name"
        },
        {
            "name": "lastUsed",
            "columnType": "Property",
            "definition": "lastUsed"
        }
        ]
    }
    body_json = json.dumps(body_object, separators=(',', ':'))
    try:
        response = requests.post(
            url,
            headers=headers,
            data=body_json,
            verify=False,
            timeout=120,
        )
        if 200 <= response.status_code < 300:
            data = response.json()
            rows = data.get("rows") or []
            if not rows:
                return []

            stale_cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            stale_ids = []

            for row in rows:
                if not isinstance(row, list) or len(row) < 3:
                    continue

                allocation_id_value = row[0]
                user_name_raw = row[1]
                user_name_value = (
                    user_name_raw
                    if isinstance(user_name_raw, str)
                    else str(user_name_raw or "")
                )
                last_used_raw = row[2]

                if user_name_value.lower().startswith("svc") or user_name_value.lower().startswith("sa_"):
                    continue

                last_used_dt = None
                if isinstance(last_used_raw, str) and last_used_raw:
                    if last_used_raw == "1753-01-01T00:00:00.000Z":
                        continue
                    parsed_value = last_used_raw
                    if parsed_value.endswith("Z"):
                        parsed_value = parsed_value[:-1] + "+00:00"
                    try:
                        last_used_dt = datetime.fromisoformat(parsed_value)
                    except ValueError:
                        last_used_dt = None

                if last_used_dt is None or last_used_dt <= stale_cutoff:
                    stale_ids.append([allocation_id_value, user_name_value])

            return stale_ids
        error_text = f"{response.status_code}: {response.text}"
        raise LicenseCleanupError(f"Request failed with status code {error_text}")
    except requests.exceptions.Timeout as e:
        raise LicenseCleanupError("The allocation request timed out.") from e
    except requests.exceptions.RequestException as e:
        raise LicenseCleanupError(f"Request failed: {e}") from e

def license_dealloc(xrfkey,selection_id,headers,url,licensetype):
    url = f"https://{url}/qrs/Selection/{selection_id}/License/{licensetype}AccessType?xrfkey={xrfkey}"
    try:
        response = requests.delete(url, headers=headers, verify=False, timeout=120)
        if 200 <= response.status_code < 300:
            return 1
        else:
            error_text = f"{response.status_code}: {response.text}"
            logger.error("License deallocation failed with status code %s", error_text)
            return 0
    except requests.exceptions.RequestException as e:
        logger.error("License deallocation request failed: %s", e)
        return 0

def load_config(file_path="C:/LicenseCleaner/config.json"):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Configuration file '%s' not found. Please ensure the file exists.", file_path)
        raise
    except PermissionError:
        logger.error("Permission denied when trying to read '%s'. Please check file permissions.", file_path)
        raise
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON format in '%s'. Error: %s", file_path, e)
        raise
    except IOError as e:
        logger.error("I/O error occurred while reading '%s': %s", file_path, e)
        raise
    except Exception as e:
        logger.error("Unexpected error occurred while loading config file '%s': %s", file_path, e)
        raise

def license_deallocator(user_name_variable,alloc_id,licensetype,headers,xrfkey,url):
    logger.info("Allocation ID received for user %s", user_name_variable)
    selec_id = selection_id_dealloc(alloc_id,xrfkey,headers,url,licensetype)
    if selec_id == 0:
        logger.error("Unable to create selection for user %s. Please check the configuration.", user_name_variable)
        logger.error("License deallocation failed for user %s", user_name_variable)
        return 0
    else:
        logger.info("Selection ID received for user %s", user_name_variable)
        dealloc_status=license_dealloc(xrfkey,selec_id,headers,url,licensetype)
        if dealloc_status == 0:
            logger.error("License deallocation request failed for user %s", user_name_variable)
            selec_id_status=selection_id_del(xrfkey,selec_id,headers,url)
            if selec_id_status == 0:
                logger.error("Cannot delete selection id: %s", selec_id)
                return 0
            logger.warning("Deallocation unsuccessful. Selection ID deleted for user %s", user_name_variable)
            return 0
        else:
            logger.info("Deallocation successful for user %s", user_name_variable)
            selec_id_status=selection_id_del(xrfkey,selec_id,headers,url)
            if selec_id_status == 0:
                logger.error("Cannot delete selection id: %s", selec_id)
                return 1
            logger.info("Selection ID deleted for user %s", user_name_variable)
            return 1

def selection_id_dealloc(user_id,xrfkey,headers,url,licensetype):
    url = f"https://{url}/qrs/Selection?xrfkey={xrfkey}"
    body_object = {
        "items": [
            {
                "type": f"License.{licensetype}AccessType",
                "objectID": f"{user_id}"
            }
        ]
    }
    body_json = json.dumps(body_object, separators=(',', ':'))
    try:
        response = requests.post(url, headers=headers, data=body_json, verify=False, timeout=120)
        if 200 <= response.status_code < 300:
            data = response.json()
            main_id = data["id"]
            return main_id
        else:
            error_text = f"{response.status_code}: {response.text}"
            logger.error("Selection creation failed with status code %s", error_text)
            return 0
    except requests.exceptions.RequestException as e:
        logger.error("Selection creation request failed: %s", e)
        return 0

def main():
    setup_logger()
    logger.info("Starting license cleanup run")
    try:
        config = load_config()
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, IOError, Exception):
        logger.error("Cannot proceed without valid configuration. Exiting.")
        return
    user_id = config.get("user_id")
    user_directory = config.get("user_directory")
    proxy_server = config.get("proxy_server")
    client_cert = config.get("client_cert")
    client_key = config.get("client_key")
    url = config.get("url")
    xrfkey = config.get("xrfkey")
    licensetype = config.get("licenseType") or config.get("license_type")
    session_id = generate_session(xrfkey,user_id,user_directory,proxy_server,client_cert,client_key)
    cookie = "X-Qlik-Session-sso-prod="+session_id
    if not url:
        logger.error("'url' not found in configuration file. Please check config.json.")
        return
    if not xrfkey:
        logger.error("'xrfkey' not found in configuration file. Please check config.json.")
        return
    if not licensetype:
        logger.error("'licenseType' not found in configuration file. Please check config.json.")
        return
    if not user_id:
        logger.error("'user_id' not found in configuration file. Please check config.json.")
        return
    if not user_directory:
        logger.error("'user_directory' not found in configuration file. Please check config.json.")
        return
    if not proxy_server:
        logger.error("'proxy_server' not found in configuration file. Please check config.json.")
        return
    if not client_cert:
        logger.error("'client_cert' not found in configuration file. Please check config.json.")
        return
    if not client_key:
        logger.error("'client_key' not found in configuration file. Please check config.json.")
        return
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US",
        "Cookie": cookie,
        "Host": f"{url}",
        "Origin": f"https://{url}",
        "Referer": f"https://{url}/qmc/professionalaccessallocations",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "sec-ch-ua": "\"Chromium\";v=\"142\", \"Google Chrome\";v=\"142\", \"Not_A Brand\";v=\"99\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
        "X-Qlik-xrfkey": xrfkey,
        "Content-Type": "application/json;charset=UTF-8",
    }

    try:
        stale_ids = allocation_id(xrfkey, url, licensetype, headers)
    except ValueError as e:
        logger.error("Configuration error: %s", e)
        delete_session(xrfkey,proxy_server,client_cert,client_key,session_id)
        return
    except LicenseCleanupError as e:
        logger.error("API error: %s", e)
        delete_session(xrfkey,proxy_server,client_cert,client_key,session_id)
        return
    except Exception as e:
        logger.error("Unexpected error while fetching allocation ids: %s", e)
        delete_session(xrfkey,proxy_server,client_cert,client_key,session_id)
        return

    if not stale_ids:
        logger.info("No stale allocations were found.")
        logger.info("Process Completed for current run")
        delete_session(xrfkey,proxy_server,client_cert,client_key,session_id)
        return
    logger.info("Processing stale allocations (>30 days)")
    for allocation_details_value in stale_ids:
        user_name_value = allocation_details_value[1]
        allocation_id_value = allocation_details_value[0]
        logger.info("Beginning license deallocation of %s (%s)", user_name_value, allocation_id_value)
        license_deallocator(user_name_value, allocation_id_value, licensetype, headers, xrfkey, url)
    logger.info("Process Completed for current run")
    delete_session(xrfkey,proxy_server,client_cert,client_key,session_id)
    
if __name__ == "__main__":
    main()