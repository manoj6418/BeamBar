# Standard Library
import json
import sys

# Third Party Library
import commands
import control


def main(argv):
    text = ' '.join(argv).strip()
    if not text or text in ('help', '-h', '--help'):
        print(commands.HELP)
        return 0
    try:
        reply = control.send({'command': text})
    except (FileNotFoundError, ConnectionRefusedError):
        print('beambar: the menu bar app is not running', file=sys.stderr)
        return 2
    if not reply.get('ok'):
        print(f"beambar: {reply.get('error', 'failed')}", file=sys.stderr)
        return 1
    result = reply.get('result')
    if isinstance(result, (dict, list)):
        print(json.dumps(result, indent=2))
    elif result:
        print(result)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
