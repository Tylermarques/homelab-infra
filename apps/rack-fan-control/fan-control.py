import logging
import os
import subprocess
import time

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

CPU_WARNING_TEMP = 80
CPU_CRITICAL_TEMP = 90
# Define the fan curve as a dictionary of temperature/fan speed pairs
SERVER_FAN_CURVE = {0: 15, 35: 25, 40: 30, 50: 35, 65: 40, 75: 70, CPU_WARNING_TEMP: 85, CPU_CRITICAL_TEMP: 100}

RACK_FAN_CURVE = {40: 50, 65: 60, 75: 70, CPU_WARNING_TEMP: 85, CPU_CRITICAL_TEMP: 100}


class IDRACControl:
    def __init__(self, HOST, USER, PASSWORD):
        # Enter ipmi ip address, username, and password

        self.IPADDR = HOST
        self.USER = USER
        self.PASSWORD = PASSWORD
        self.IPMIBASE = f"ipmitool -I lanplus -H {self.IPADDR} -U {self.USER} -P {self.PASSWORD}"
        # Enable manual fan control
        # subprocess.run(IPMIBASE.split() + ['0x01', '0x00'], check=True)

        # Set the IPMI tool command to adjust the fan speed
        self.FAN_CMD = self.IPMIBASE + " raw 0x30 0x30 0x02 0xff"

        # Initialize the fan speed and CPU temperature to 0
        self.FAN_SPEED = 0
        self.CPU_TEMP = 0

        # IPMI command to fetch temperatures
        self.TEMP_CMD = f"ipmitool -I lanplus -H {self.IPADDR} -U {self.USER} -P {self.PASSWORD} sdr type temperature"

    def get_current_temp(self):
        # Read the Exhaust temperature using IPMI
        temperature_output = subprocess.check_output(self.TEMP_CMD.split()).decode()
        for line in temperature_output.splitlines():
            # Parse the First CPU Temp value, it tends to be the hottest
            if "0Eh" in line:
                NEW_CPU_TEMP = float(line.split("|")[4].strip().split()[0])

                # Print the CPU temperature to the console if it has changed
                if NEW_CPU_TEMP != self.CPU_TEMP:
                    logging.info(f"CPU Temperature: {NEW_CPU_TEMP}°C")
                    self.CPU_TEMP = NEW_CPU_TEMP
                if NEW_CPU_TEMP >= CPU_WARNING_TEMP:
                    logging.warning(f"CPU reached {NEW_CPU_TEMP}, check airflow.")
                break
        return self.CPU_TEMP

    def update_fan_speed_percentage(self, fan_speed):
        # Set the fan speed using IPMI tool if it has changed
        if fan_speed != self.FAN_SPEED:
            logging.info(f"Setting fan speed to {fan_speed}%")
            NEW_FAN_SPEED_HEX = "{:02x}".format(fan_speed)
            subprocess.run((self.FAN_CMD + f" 0x{NEW_FAN_SPEED_HEX}").split(), check=True)
            self.FAN_SPEED = fan_speed


class RackFan:
    def __init__(self, HOST, token):
        self.HOME_ASSISTANT_URL = HOST
        self.token = token
        self.entity_id = "fan.rack_exhaust_fan"

    def update_fan_speed_percentage(self, percentage):
        url = f"{self.HOME_ASSISTANT_URL}/api/services/fan/set_percentage"
        data = {"entity_id": self.entity_id, "percentage": percentage}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "content-type": "application/json",
        }
        response = requests.post(url, headers=headers, json=data)
        logging.info(f"Set rack fan speed to {percentage}%")
        if response.status_code != 200:
            print(f"Error updating Home Assistant: {response.text}")


if __name__ == "__main__":
    heather = IDRACControl(HOST=os.environ.get("IDRAC_HOST"), USER=os.environ.get("IDRAC_USER"), PASSWORD=os.environ.get("IDRAC_PASSWORD"))
    rack_fan = RackFan(HOST=os.environ.get("HASS_HOST"), token=os.environ.get("HASS_TOKEN"))

    NEW_SERVER_FAN_SPEED = 50
    NEW_RACK_FAN_SPEED = 50
    while True:
        cpu_temp = heather.get_current_temp()
        # Find the fan speed corresponding to the current temperature
        for TEMP, SPEED in sorted(SERVER_FAN_CURVE.items()):
            if cpu_temp >= TEMP:
                NEW_SERVER_FAN_SPEED = SPEED
            else:
                break
        heather.update_fan_speed_percentage(NEW_SERVER_FAN_SPEED)
        # Find the fan speed corresponding to the current temperature
        for TEMP, SPEED in sorted(RACK_FAN_CURVE.items()):
            if cpu_temp >= TEMP:
                NEW_RACK_FAN_SPEED = SPEED
            else:
                break
        rack_fan.update_fan_speed_percentage(NEW_RACK_FAN_SPEED)
        time.sleep(5)
