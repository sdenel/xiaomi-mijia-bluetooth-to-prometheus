#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import logging

# 127.0.0.1 to allow only local usages
# 0.0.0.0 to allow other computers in your network to access the service
ADDRESS = "0.0.0.0"
PORT = 9191
# This is the MAC of my probe. Put you own here!
YOUR_PROBE_MAC_ADDRESS = "4C:65:A8:D4:C5:2D"

log = logging.getLogger("my-logger")


def run_cmd(cmd):
    logging.debug("Executing: " + cmd)
    ps = subprocess.Popen(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    result = ps.communicate()[0].decode('utf-8').strip()
    logging.debug("Result: " + result)
    return result


def measures_to_prometheus_format(measures):
    """
    >>> print(measures_to_prometheus_format(
    ... {'hygrometry': 45.0, 'battery_level': 93.75, 'temperature': 26.5}
    ... ))
    # HELP
    # TYPE temperature gauge
    temperature 26.5
    # HELP
    # TYPE hygrometry gauge
    hygrometry 45.0
    # HELP
    # TYPE battery_level gauge
    battery_level 93.75
    """
    prometheus_str_as_list = [
        "# HELP",
        "# TYPE temperature gauge",
        "temperature " + str(measures['temperature']),
        "# HELP",
        "# TYPE hygrometry gauge",
        "hygrometry " + str(measures['hygrometry']),
        "# HELP",
        "# TYPE battery_level gauge",
        "battery_level " + str(measures['battery_level'])
    ]
    return "\n".join(prometheus_str_as_list)


def parse_temperature_humidity_hex_to_plaintext(data_hex):
    """
    >>> parse_temperature_humidity_hex_to_plaintext(
    ... "Notification handle = 0x000e value: " +
    ... "54 3d 32 38 2e 33 20 48 3d 35 34 2e 31 00"
    ... )
    'T=28.3 H=54.1'
    """
    hex = data_hex[data_hex.find(':') + 2:]
    if hex.endswith("00"):
        hex = hex[:-3]
    hex = hex.split(' ')
    return ''.join([str(chr(int(x, 16))) for x in hex])


def parse_temperature_humidity_plaintext_to_numeric(data_plaintext):
    """
    >>> r = parse_temperature_humidity_plaintext_to_numeric("T=28.3 H=54.1")
    >>> r == {'temperature': 28.3, 'hygrometry': 54.1}
    True
    """
    data_plaintext_splitted = data_plaintext.split(' ')
    return {
        'temperature': float(data_plaintext_splitted[0].split('=')[1]),
        'hygrometry': float(data_plaintext_splitted[1].split('=')[1])
    }


def parse_battery_level_hex_to_numeric(battery_raw):
    """
    >>> parse_battery_level_hex_to_numeric('60')
    93.75
    """
    return 100 * float(battery_raw) / 64.0


def pull_measures():
    # Checking temperature and humidity
    cmd = "timeout 60 gatttool -b " + YOUR_PROBE_MAC_ADDRESS + \
          " --char-write-req --handle=0x10 -n 0100 --listen" + \
          " | head -n 2 | tail -n 1"
    data_raw = run_cmd(cmd)
    if not data_raw.startswith("Notification handle = "):
        raise IOError(data_raw)
    data_hex = parse_temperature_humidity_hex_to_plaintext(data_raw)
    measures = parse_temperature_humidity_plaintext_to_numeric(data_hex)

    # Checking the battery level
    cmd = "timeout 60 gatttool -b " + YOUR_PROBE_MAC_ADDRESS + \
          " --char-read --handle=0x18"
    battery_raw = run_cmd(cmd).split(':')[-1].strip()
    battery = parse_battery_level_hex_to_numeric(battery_raw)
    measures['battery_level'] = battery
    return measures


class SimpleHttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            measures = pull_measures()
            # Send response status code
            self.send_response(200)

            self.send_header('Content-type', 'text/plain')
            self.end_headers()

            self.wfile.write(
                bytes(measures_to_prometheus_format(measures), "utf8")
            )
        except IOError as e:
            logging.error(e)
            self.send_response(500)

            self.send_header('Content-type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes(str(e), "utf8"))
        return


if __name__ == '__main__':
    log.setLevel(logging.NOTSET)
    logging.basicConfig(
        format="%(levelname)s\t%(message)s",
        level=logging.NOTSET
    )
    log.info(
        'Checking the probe once before starting the webserver: ' +
        str(pull_measures())
    )
    log.info('Starting webserver on ' + ADDRESS + ':' + str(PORT))
    server_address = (ADDRESS, PORT)
    httpd = HTTPServer(server_address, SimpleHttpHandler)
    httpd.serve_forever()
