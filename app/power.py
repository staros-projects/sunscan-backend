import subprocess
import logging

class PowerHelper:

    def __init__(self):
        self.logger = logging.getLogger('maginkcal')

    def get_battery(self):
        # command = ['echo "get battery" | nc -q 0 127.0.0.1 8423']
        battery_float = -1
        try:
            ps = subprocess.Popen(('echo', 'get battery'), stdout=subprocess.PIPE)
            result = subprocess.check_output(('nc', '-q', '0', '127.0.0.1', '8423'), stdin=ps.stdout)
            ps.wait()
            result_str = result.decode('utf-8').rstrip()
            battery_level = result_str.split()[-1]
            battery_float = float(battery_level)
            #battery_level = "{:.3f}".format(battery_float)
        except (ValueError, subprocess.CalledProcessError) as e:
            self.logger.info('Invalid battery output')
        return battery_float

    def battery_power_plugged(self):
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
        # TODO: For directly scheduling next boot instead of using PiSugar's web interface
        # Currently, it can be done manually through the PiSugar web interface
        return True

    def sync_time(self):
        # To sync PiSugar RTC with current time
        try:
            ps = subprocess.Popen(('echo', 'rtc_rtc2pi'), stdout=subprocess.PIPE)
            result = subprocess.check_output(('nc', '-q', '0', '127.0.0.1', '8423'), stdin=ps.stdout)
            ps.wait()
        except subprocess.CalledProcessError:
            self.logger.info('Invalid time sync command')