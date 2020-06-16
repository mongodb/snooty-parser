from pathlib import Path
from .parse import parse
from .extracts import Extract
from ..types import ProjectConfig


def test_invalid_yaml() -> None:
    project_config = ProjectConfig(Path("test_data"), "", False)
    pages, text, diagnostics = parse(
        Extract,
        Path(""),
        project_config,
        """
ref: troubleshooting-monitoring-agent-fails-to-collect-data
edition: onprem
content: |

   Fails to Collect Data
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  Possible causes for this state:
""",
    )
    assert len(diagnostics) == 1
    assert diagnostics[0].start[0] == 6
