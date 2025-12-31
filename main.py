from datetime import datetime

import requests
from google.cloud import storage

BUCKET_NAME = "power_state_manager"
STATUS_FILE_NAME = "elec_status.txt"

# Initialize the GCS client
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)


def get_last_status_from_bucket(house: str) -> tuple[str, str] | None:
    """Safely reads the last status from a file in GCS.
    Returns:
        Tuple: status, time the status was last changed
    """
    try:
        blob = bucket.blob(f"{house}_{STATUS_FILE_NAME}")
        # Download the contents of the blob as a string
        last_status = blob.download_as_text()
        return last_status.split(" ")[0], last_status.split(" ")[1]
    except Exception as e:
        # If the file doesn't exist or other error, assume no last status
        print(f"Could not read status file from GCS (this is normal on first run): {e}")
        return None


def save_current_status_to_bucket(house, status):
    """Saves the current status to a file in GCS."""
    blob = bucket.blob(f"{house}_{STATUS_FILE_NAME}")
    blob.upload_from_string(f"{status} {datetime.now().isoformat()}")
    print(f"Successfully saved status '{status}' to GCS.")


def send_notification(house, time_diff, battery_percentage, electricity_on: bool):
    # Send notification
    # Format time difference as "x Hours x Minutes"
    total_seconds = int(time_diff.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60

    if hours > 0 and minutes > 0:
        time_diff_formatted = f"{hours} Hours {minutes} Minutes"
    elif hours > 0:
        time_diff_formatted = f"{hours} Hours"
    elif minutes > 0:
        time_diff_formatted = f"{minutes} Minutes"
    else:
        time_diff_formatted = "Less than a minute"

    TOPIC: str = f"home_elec_detector_{house}"
    TITLE: str = "Electricity is ON!" if electricity_on else "Electricity is OFF."
    MESSAGE: str = (
        f"Battery is charged {battery_percentage}% | Power stayed {'OFF' if electricity_on else 'ON'} for {time_diff_formatted}"
    )
    try:
        requests.post(
            f"https://ntfy.sh/{TOPIC}",
            data=MESSAGE.encode("utf-8"),
            headers={"Title": TITLE, "Priority": "high", "Tags": "electric_plug"},
        )
        print(f"Notification sent: '{TITLE}'\n'{MESSAGE}'")
    except Exception as e:
        print(f"Failed to send notification: {e}")


def check_power_status(houses: dict[str, str]):
    """
    Core logic to check power status for configured houses.
    """
    print("Starting power check...")

    for house, api_link in houses.items():
        try:
            response = requests.get(api_link)
            response.raise_for_status()

            data = response.json()

            # grid_json = [js for js in data["dat"] if js["par"] == "gd_fre"][0]
            grid_json = data["dat"]["gd_status"][0]

            # battery_json = [js for js in data["dat"] if js["par"] == "bt_cap"][0]
            battery_json = data["dat"]["bt_status"][0]
            battery_percentage = int(float(battery_json["val"]))
            current_status = "ON" if grid_json["status"] > 0 else "OFF"
            print("Current Status:", current_status)
        except Exception as e:
            print(f"Error: Could not get or parse API data. {e}")
            return f"Error in watchpower api: {e}", 500

        # Compare with the last known status
        try:
            status = get_last_status_from_bucket(house)
            if status is None:
                print("No previous status found. Saving current status.")
                save_current_status_to_bucket(house, current_status)
                continue

            last_status, last_time = status

            time_diff = datetime.now() - datetime.fromisoformat(last_time)

            print(
                f"Last status: {last_status}, Current Status: {current_status}, Time since last change: {time_diff}"
            )

            if current_status != last_status:
                print("Status has changed! Sending notification.")

                if current_status == "ON":
                    send_notification(house, time_diff, battery_percentage, True)
                else:  # current_status is "OFF"
                    send_notification(house, time_diff, battery_percentage, False)

                #  Save the new status to Google Cloud Storage
                save_current_status_to_bucket(house, current_status)
            else:
                print("Status is unchanged. No notification needed.")

            return "Function executed successfully", 200
        except Exception as e:
            print(
                f"Error in retrieving past status or writing it, or sending notification: {e}"
            )
            return (
                f"Error in retrieving past status or writing it, or sending notification: {e}",
                500,
            )


def cloud_function_entry(request):
    """
    Entry point for Google Cloud Functions (HTTP trigger).
    """
    houses = {
        "samisamisami": "http://android.shinemonitor.com/public/?sign=217e8092d5cdf4a78ecafb688d8631ffa3be7200&salt=1758885888965&token=CN92703a29-c8d8-4eef-a5fe-4c4968a5253a&action=webQueryDeviceEnergyFlowEs&pn=W0052076387745&sn=96342408108045&devaddr=1&devcode=2451&i18n=en_US&lang=en_US&source=1&_app_client_=android&_app_id_=wifiapp.volfw.watchpower&_app_version_=1.5.0.0",
        "tete": "http://android.shinemonitor.com/public/?sign=b275e106bab5ff1a79fd2266162c34cbe45729a2&salt=1767189705811&token=CN1df70a20-0bcc-49e8-b6d7-2a80feac415d&action=queryDeviceFlowPower&pn=W0052131378954&sn=96322408108231&devaddr=1&devcode=2451&i18n=en_US&lang=en_US&source=1&_app_client_=android&_app_id_=wifiapp.volfw.watchpower&_app_version_=1.7.1.0",
    }
    if not houses:
        return "Configuration error: No houses found.", 500

    return check_power_status(houses)


if __name__ == "__main__":
    # Local execution
    houses = {
        "samisamisami": "http://android.shinemonitor.com/public/?sign=217e8092d5cdf4a78ecafb688d8631ffa3be7200&salt=1758885888965&token=CN92703a29-c8d8-4eef-a5fe-4c4968a5253a&action=webQueryDeviceEnergyFlowEs&pn=W0052076387745&sn=96342408108045&devaddr=1&devcode=2451&i18n=en_US&lang=en_US&source=1&_app_client_=android&_app_id_=wifiapp.volfw.watchpower&_app_version_=1.5.0.0",
        "tete": "http://android.shinemonitor.com/public/?sign=b275e106bab5ff1a79fd2266162c34cbe45729a2&salt=1767189705811&token=CN1df70a20-0bcc-49e8-b6d7-2a80feac415d&action=queryDeviceFlowPower&pn=W0052131378954&sn=96322408108231&devaddr=1&devcode=2451&i18n=en_US&lang=en_US&source=1&_app_client_=android&_app_id_=wifiapp.volfw.watchpower&_app_version_=1.7.1.0",
    }
    check_power_status(houses)
