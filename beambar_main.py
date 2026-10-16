"""Entry point of BeamBar.app: the menu bar app, or the command-line remote with --cli."""
# Standard Library
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':
        # Third Party Library
        import cli

        sys.exit(cli.main(sys.argv[2:]))
    # Third Party Library
    import app

    app.BeamBar().run()
