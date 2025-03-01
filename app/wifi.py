"""WifiManager class provides methods to manage WiFi settings on a system."""
import subprocess
import os
from typing import Union, Literal
from pydantic_extra_types.country import CountryAlpha2

WifiCountryCode = Union[CountryAlpha2, Literal["00"]]


class WifiManager:
    """
    WifiManager is a class that provides methods to manage WiFi settings on a system.
    Methods
    -------
    __init__():
        Initializes the WifiManager instance.
    get_country():
        Retrieves the current WiFi regulatory domain country code.
    set_country(country_code):
        Sets the WiFi regulatory domain to the specified country code.
    restart_wifi():
        Restarts the WiFi service on the system.
    """
    def __init__(self):
        pass

    def get_country(self) -> WifiCountryCode:
        """
        Retrieves the current WiFi regulatory domain country code.
        """
        country_code = None
        try:
            result = os.popen("iw reg get").read()
            lines = result.splitlines()
            for i, line in enumerate(lines):
                if line.strip() == "global":
                    if i + 1 < len(lines) and lines[i + 1].startswith("country"):
                        country_code = lines[i + 1].split()[1].split(":")[0]
                        break
        except Exception as e:
            print(f"Error getting country: {e}")
            raise e
        return country_code

    def set_country(self, country_code: WifiCountryCode):
        try:
            subprocess.run(['sudo', 'raspi-config', 'nonint', 'do_wifi_country', country_code], check=True)
            print(f"Country set to {country_code}")
        except Exception as e:
            print(f"Error setting country: {e}")

    def restart_wifi(self):
        try:
            # Respond to the client first
            print("WiFi restart initiated")
            
            # Restart WiFi in a separate subprocess
            subprocess.Popen(['sudo', 'systemctl', 'restart', 'NetworkManager'])
        except Exception as e:
            print(f"Error restarting WiFi: {e}")

# Example usage:
# wifi_manager = WifiManager()
# print(wifi_manager.get_country())
# wifi_manager.set_country('US')
# wifi_manager.restart_wifi()