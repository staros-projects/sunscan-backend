import subprocess
import socket
import logging
import requests

def factory_power_helper():
    if is_battery_system_available():
        return PowerHelper()
    else:
        return MockPowerHelper()


def is_battery_system_available():
    """
    Checks if the battery system is available by sending a command to the PiSugar device.

    Returns:
        bool: True if the battery system is available, False otherwise.
    """
    try:
        response = PowerHelper().send_command_to_pisugar("get battery")
        return "battery" in response.lower()
    except PiSugarError:
        return False


class MockPowerHelper:
    """MockPowerHelper is a mock class that simulates power-related functionalities."""
    def get_battery(self):
        return 42.0
    def battery_power_plugged(self):
        return False
    def set_next_boot_datetime(self, datetime):
        return True
    def sync_time(self):
        pass

class PiSugarError(Exception):
    """Custom exception for PiSugar related errors."""
    def __init__(self, message):
        super().__init__(message)

class PowerHelper:
    """A helper class for managing power-related functions."""

    @classmethod
    def send_command_to_pisugar(cls, command: str) -> str:
        """
        Sends a command to the PiSugar power management system via a socket connection.
        
        Args:
            command (str): The command to be sent to the PiSugar system.
        
        Returns:
            str: The response from the PiSugar system if the command is successfully sent and a response is received.
        
        Raises:
            PiSugarError: If there is an error creating or using the socket connection.
        """
        try:
            with socket.create_connection(("127.0.0.1", 8423), timeout=1) as sock:
                # Send the command directly via the socket
                sock.sendall(f"{command}\n".encode('utf-8'))
                response = sock.recv(1024).decode('utf-8').strip()
                return response
        except socket.error as e:
            # If an exception is raised, the system is not available
            raise PiSugarError(f"Failed to send command to PiSugar: {e}") from e
            
    def __init__(self):
        """Initialize the PowerHelper class with a logger."""
        self.logger = logging.getLogger('maginkcal')

        # Set battery input protection 
        self.send_command_to_pisugar("set_battery_input_protect true")

    def get_battery(self):
        """
        Get the current battery level.

        Returns:
            float: The battery level as a float between 0 and 100,
                   or -1 if unable to retrieve the battery level.
        """
        # command = ['echo "get battery" | nc -q 0 127.0.0.1 8423']
        battery_float = -1
        try:
            response = self.send_command_to_pisugar("get battery")
            battery_level = response.split()[-1]
            battery_float = float(battery_level)
        except ValueError:
            self.logger.info('Invalid battery output')
        return battery_float

    def battery_power_plugged(self):
        """
        Check if the battery is currently being charged.

        Returns:
            bool: True if the battery is plugged in and charging, False otherwise.
        """
        # command = ['echo "get battery_power_plugged" | nc -q 0 127.0.0.1 8423']
        battery_power_plugged = False
        try:
            response = self.send_command_to_pisugar("get battery_power_plugged")
            battery_power_plugged = response.split(': ')[-1].strip().lower() == 'true'
        except (ValueError, PiSugarError) as e:
            self.logger.info('Invalid battery output')
            self.logger.error(e)
        return battery_power_plugged

    def sync_time(self):
        """
        Synchronize the PiSugar RTC with the current system time.

        This method attempts to sync the RTC using a netcat command.
        If the sync fails, it logs an error message.
        """
        # To sync PiSugar RTC with current time
        try:
            response = self.send_command_to_pisugar("rtc_rtc2pi")
            if "done" not in response.lower():
                self.logger.info('Invalid time sync command')
        except PiSugarError as e:
            self.logger.error(f"Failed to sync time with PiSugar: {e}")
