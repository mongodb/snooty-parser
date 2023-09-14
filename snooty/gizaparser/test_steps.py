import collections
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..diagnostics import Diagnostic, DocUtilsParseError, FailedToInheritRef
from ..n import FileId
from ..page import Page
from ..parser import EmbeddedRstParser
from ..types import ProjectConfig
from ..util_test import (
    BackendTestResults,
    ast_to_testing_string,
    check_ast_testing_string,
    make_test,
    make_test_project,
)
from .steps import GizaStepsCategory


def test_step() -> None:
    root_path = Path("test_data/test_gizaparser")
    project_config, project_diagnostics = ProjectConfig.open(root_path)
    assert project_diagnostics == []

    category = GizaStepsCategory(project_config)

    fileid = FileId("includes/steps-test.yaml")
    child_fileid = FileId("includes/steps-test-child.yaml")
    grandchild_fileid = FileId("includes/steps-test-grandchild.yaml")

    all_diagnostics: Dict[FileId, List[Diagnostic]] = collections.defaultdict(list)
    for current_path in [fileid, child_fileid, grandchild_fileid]:
        steps, text, parse_diagnostics = category.parse(current_path)
        category.add(current_path, text, steps, parse_diagnostics)
        if parse_diagnostics:
            all_diagnostics[fileid] = parse_diagnostics

    assert len(category) == 3
    file_id, giza_node = next(category.reify_all_files(all_diagnostics))

    def create_page(filename: Optional[str]) -> Tuple[Page, EmbeddedRstParser]:
        page = Page.create(fileid, filename, "")
        return (page, EmbeddedRstParser(project_config, page, all_diagnostics[fileid]))

    pages = category.to_pages(fileid, create_page, giza_node)
    assert [page.fake_full_fileid().as_posix() for page in pages] == [
        "includes/steps/test.rst"
    ]
    # Ensure that no diagnostics were raised
    all_diagnostics = {k: v for k, v in all_diagnostics.items() if v}
    assert not all_diagnostics
    print(repr(ast_to_testing_string(pages[0].ast)))
    check_ast_testing_string(
        pages[0].ast,
        """
<root fileid="includes/steps-test.yaml">
<directive name="procedure" style="normal">
<directive name="step">
    <section>
    <heading id="import-the-public-key-used-by-the-package-management-system">
        <text>Import the </text>
        <emphasis><text>public key</text></emphasis>
        <text> used by the </text>
        <reference refuri="https://en.wikipedia.org/wiki/Package_manager">
        <text>package management system</text>
        </reference>
        <named_reference refname="package management system" refuri="https://en.wikipedia.org/wiki/Package_manager" />
    </heading>
    <paragraph>
        <text>Issue the following command to import the\n</text>
        <reference refuri="https://www.mongodb.org/static/pgp/server-3.4.asc">
        <text>MongoDB public GPG Key</text></reference>
        <named_reference refname="MongoDB public GPG Key" refuri="https://www.mongodb.org/static/pgp/server-3.4.asc" />
    </paragraph></section></directive>
<directive name="step">
    <section>
    <heading id="create-a-etc-apt-sources-list-d-mongodb-org-3-4-list-file-for-mongodb">
        <text>Create a </text><literal><text>
        /etc/apt/sources.list.d/mongodb-org-3.4.list</text></literal><text> file for </text>
        <role name="guilabel"><text>MongoDB</text></role>
        <text>.</text>
    </heading>
    <section><heading id="optional-action-heading">
        <text>Optional: action heading</text></heading>
        <paragraph>
            <text>Create the list file using the command appropriate for your version\nof Debian.</text>
        </paragraph>
        <paragraph><text>action-content</text></paragraph>
        <paragraph><text>action-post</text></paragraph>
    </section></section></directive>
<directive name="step"><section>
    <heading id="reload-local-package-database">
        <text>Reload local package database.</text>
    </heading>
    <paragraph>
        <text>Issue the following command to reload the local package database:</text>
    </paragraph>
    <code copyable="True" lang="sh">sudo apt-get update\n</code>
    </section></directive>
<directive name="step"><section>
    <heading id="install-the-mongodb-packages">
        <text>Install the MongoDB packages.</text>
    </heading>
    <paragraph><text>hi</text></paragraph>
    <paragraph>
        <text>You can install either the latest stable version of MongoDB or a\nspecific version of MongoDB.</text>
    </paragraph>
    <code lang="sh" copyable="True">
    echo "mongodb-org hold" | sudo dpkg --set-selections
    </code><paragraph><text>bye</text></paragraph></section></directive>
</directive></root>""",
    )


def test_overriding_replacements() -> None:
    with make_test(
        {
            Path(
                "source/includes/steps-configure-mcli.yaml"
            ): """
title: "Create a profile."
stepnum: 0
level: 4
ref: create-profile
replacement:
  serviceOption: ""
content: |

  foo{{serviceOption}}
...
""",
            Path(
                "source/includes/steps-configure-mcli-cm.yaml"
            ): """
stepnum: 1
ref: create-profile-cm
source:
  file: steps-configure-mcli.yaml
  ref: create-profile
replacement:
  serviceOption: "bar"
...
""",
        }
    ) as result:
        assert all(not x for x in result.diagnostics.values())
        page = result.pages[FileId("includes/steps/configure-mcli-cm.rst")]
    check_ast_testing_string(
        page.ast,
        """
<root fileid="includes/steps-configure-mcli-cm.yaml">
    <directive name="procedure" style="normal">
        <directive name="step">
            <section>
                <heading id="create-a-profile"><text>Create a profile.</text></heading>
                <paragraph><text>foobar</text></paragraph>
            </section>
        </directive>
    </directive>
</root>
""",
    )


def test_yaml_diagnostics_cache() -> None:
    """Ensure that when we load a cached build, we still get YAML diagnostics."""
    reference_diagnostics = {
        FileId("includes/steps-configure-mcli-cm.yaml"): [FailedToInheritRef],
        FileId("includes/steps-configure-mcli.yaml"): [DocUtilsParseError],
    }

    with make_test_project(
        {
            Path(
                "source/includes/steps-configure-mcli.yaml"
            ): """
title: "Create a profile."
stepnum: 0
level: 4
ref: create-profile
replacement:
  serviceOption: ""
content: |

  foo{{serviceOption}}

  .. foobarbaz::
...
""",
            Path(
                "source/includes/steps-configure-mcli-cm.yaml"
            ): """
stepnum: 1
ref: create-profile-cm
source:
  file: steps-configure-mcli.yaml
  ref: create-profil
replacement:
  serviceOption: "bar"
...
""",
        }
    ) as (_project, first_backend):
        _project.build()
        assert {
            k: [type(d) for d in v] for k, v in first_backend.diagnostics.items()
        } == reference_diagnostics
        _project.update_cache(False)

        # Rebuild with a cache, and ensure we get the same diagnostics
        backend = BackendTestResults()
        with _project._get_inner() as project:
            project.backend = backend
        _project.load_cache()
        _project.build()
        assert {
            k: [type(d) for d in v] for k, v in backend.diagnostics.items()
        } == reference_diagnostics
