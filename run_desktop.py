if __name__ == "__main__":
    try:
        from quansyn_desktop.app import main

        raise SystemExit(main())
    except Exception:
        import traceback
        from pathlib import Path
        import sys
        try:
            base = Path(sys.executable).resolve().parent if bool(getattr(sys, "frozen", False)) else Path.cwd()
            with (base / "startup.log").open("a", encoding="utf-8") as f:
                f.write("run_desktop: exception\n")
                f.write(traceback.format_exc() + "\n")
        except Exception:
            pass
        raise
