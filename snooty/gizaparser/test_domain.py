from pathlib import Path

from ..diagnostics import ErrorParsingYAMLFile, GitMergeConflictArtifactFound
from ..n import FileId
from ..util_test import make_test


def test_yaml_with_read_error() -> None:
    """Ensure that read errors get properly propagated from YAML files."""
    with make_test(
        {
            Path(
                "source/includes/extracts-test1.yaml"
            ): """
ref: create-resource-lock
content: |

    Test
...

<<<<<<< testing\nfoobar\n=======\n>>>>>>> foobaz
"""
        }
    ) as result:
        assert [
            type(d) for d in result.diagnostics[FileId("includes/extracts-test1.yaml")]
        ] == [GitMergeConflictArtifactFound, ErrorParsingYAMLFile]
