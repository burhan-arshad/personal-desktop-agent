
from agent.graph import run_cli


def main():
    try:
        run_cli()

    except KeyboardInterrupt:
        print("\n\n[EXIT] Desktop AI Agent stopped by user.")

    except Exception as error:
        print(f"\n[STARTUP ERROR] {error}")


if __name__ == "__main__":
    main()
