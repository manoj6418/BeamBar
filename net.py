# Standard Library
import socket

# The TV or projector's address; set by the app once it knows it.
device_host = ''


def lan_ip():
    """This Mac's address on the network the TV is on.

    A UDP connect sends nothing; it only asks which interface routes to the target.
    Routing to the TV itself picks the home network even when a VPN is the default route.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((device_host or '192.0.2.1', 9))
        return probe.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        probe.close()
