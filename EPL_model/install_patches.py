"""Apply small compatibility patches to the installed fotmob-api package."""

from __future__ import annotations

import pathlib
import sys


def patch_fotmob_api() -> None:
    import fotmob_api

    package_file = pathlib.Path(fotmob_api.__file__).parent / "fotmob_api.py"
    source = package_file.read_text()

    original = source
    source = source.replace('from typing import Any, Dict, List\n', 'from typing import Any, Dict, List, Union\n')
    source = source.replace("teams: int | List[int]", "teams: Union[int, List[int]]")
    source = source.replace('self.base_api = "/api/"', 'self.base_api = "/api/data/"')

    if source != original:
        package_file.write_text(source)
        print(f"Patched {package_file}")
    else:
        print("fotmob-api is already patched.")


if __name__ == "__main__":
    patch_fotmob_api()
