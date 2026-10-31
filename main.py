"""실행: python main.py commit | python main.py pr  (옵션은 --help)"""

from app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
