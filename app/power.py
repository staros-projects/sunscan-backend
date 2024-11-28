import subprocess
import logging
import requests

class PowerHelper:
    """A helper class for managing power-related functions."""

    def __init__(self):
        """Initialize the PowerHelper class with a logger."""
        self.logger = logging.getLogger('maginkcal')

        try:
            # Set battery input protection 
            ps = subprocess.Popen(('echo', 'set_battery_input_protect true'), stdout=subprocess.PIPE)
            result = subprocess.check_output(('nc', '-q', '0', '127.0.0.1', '8423'), stdin=ps.stdout)
            ps.wait()
            
        except Exception as e:
            self.logger.info('Invalid battery')


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
            ps = subprocess.Popen(('echo', 'get battery'), stdout=subprocess.PIPE)
            result = subprocess.check_output(('nc', '-q', '0', '127.0.0.1', '8423'), stdin=ps.stdout)
            ps.wait()
            result_str = result.decode('utf-8').rstrip()
            battery_level = result_str.split()[-1]
            battery_float = float(battery_level)
            


        except (ValueError, subprocess.CalledProcessError) as e:
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
            ps = subprocess.Popen(('echo', 'get battery_power_plugged'), stdout=subprocess.PIPE)
            result = subprocess.check_output(('nc', '-q', '0', '127.0.0.1', '8423'), stdin=ps.stdout)
            ps.wait()
            result_str = result.decode('utf-8').rstrip()
            
            battery_res = result_str.split(': ')[-1]

            battery_power_plugged = True if battery_res == 'true' else False
        except (ValueError, subprocess.CalledProcessError) as e:
            self.logger.info('Invalid battery output')
        return battery_power_plugged

    def set_next_boot_datetime(self, datetime):
        """
        Set the next boot datetime.

        Args:
            datetime: The datetime for the next boot.

        Returns:
            bool: Always returns True (placeholder implementation).

        Note:
            This is a placeholder method. The actual implementation for
            scheduling the next boot is not yet available.
        """
        # TODO: For directly scheduling next boot instead of using PiSugar's web interface
        # Currently, it can be done manually through the PiSugar web interface
        return True

    def sync_time(self):
        """
        Synchronize the PiSugar RTC with the current system time.

        This method attempts to sync the RTC using a netcat command.
        If the sync fails, it logs an error message.
        """
        # To sync PiSugar RTC with current time
        try:
            ps = subprocess.Popen(('echo', 'rtc_rtc2pi'), stdout=subprocess.PIPE)
            result = subprocess.check_output(('nc', '-q', '0', '127.0.0.1', '8423'), stdin=ps.stdout)
            ps.wait()
        except subprocess.CalledProcessError:
            self.logger.info('Invalid time sync command')