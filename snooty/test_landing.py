from pathlib import Path

import pytest

from . import n
from .parser import Project
from .test_project import Backend
from .types import BuildIdentifierSet, FileId
from .util_test import check_ast_testing_string


@pytest.fixture
def backend() -> Backend:
    backend = Backend()
    build_identifiers: BuildIdentifierSet = {}
    with Project(Path("test_data/test_landing"), backend, build_identifiers) as project:
        project.build()

    return backend


# Test all directives exclusive to the landing domain
def test_landing_directives(backend: Backend) -> None:
    page_id = FileId("index.txt")
    page = backend.pages[page_id]
    assert len(page.static_assets) == 1

    ast = page.ast
    section = ast.children[0]
    assert isinstance(section, n.Section)

    introduction = section.children[1]
    check_ast_testing_string(
        introduction,
        """<directive domain="landing" name="introduction">
            <paragraph><text>
            This test project tests all directives exclusive to the landing domain, which is used for docs-landing and product landing pages.
            </text></paragraph>
        </directive>""",
    )

    button = section.children[2]
    check_ast_testing_string(
        button,
        """<directive domain="landing" name="button" uri="/path/to/download">
            <text>Button text</text></directive>""",
    )

    card_group = section.children[3]
    assert isinstance(card_group, n.Parent)
    assert len(card_group.children) == 3
    check_ast_testing_string(
        card_group,
        """<directive domain="landing" name="card-group" columns="3" style="compact">
            <directive domain="landing" name="card" headline="Run a self-managed database" cta="Get started with MongoDB" url="http://mongodb.com" icon="/images/pink.png" icon-alt="Alt text" tag="server" checksum="71bf03ab0c5b8d46f0c03b77db6bd18a77d984d216c62c3519dfb45c162cd86b">
                <paragraph><text>Download and install the MongoDB database on your own\ninfrastructure.</text></paragraph>
            </directive>
            <directive domain="landing" name="card" cta="Call to action" url="https://www.url.com" icon="/images/pink.png" icon-alt="Alt text" checksum="71bf03ab0c5b8d46f0c03b77db6bd18a77d984d216c62c3519dfb45c162cd86b">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
            <directive domain="landing" name="card" cta="Call to action" url="https://www.url.com" icon="/images/pink.png" icon-alt="Alt text" checksum="71bf03ab0c5b8d46f0c03b77db6bd18a77d984d216c62c3519dfb45c162cd86b">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
        </directive>""",
    )

    cta = section.children[4]
    check_ast_testing_string(
        cta,
        """<directive domain="landing" name="cta"><paragraph><reference refuri="https://docs.mongodb.com/manual/introduction/"><text>Read the Introduction to MongoDB</text></reference></paragraph></directive>""",
    )

    kicker = section.children[5]
    check_ast_testing_string(
        kicker,
        """<directive domain="landing" name="kicker"><text>A kicker is a subheader above a main header</text></directive>""",
    )

    procedure = section.children[6]
    check_ast_testing_string(
        procedure,
        """
        <directive domain="landing" name="procedure">
            <directive domain="landing" name="step">
                <text>Connect to Your Deployment</text>
                <paragraph><text>Paragraph.</text></paragraph>
                <paragraph>
                    <ref_role domain="std" name="label" target="Connect to MongoDB">
                        <text>To learn more, see Connect to MongoDB</text>
                    </ref_role>
                </paragraph>
            </directive>
            <directive domain="landing" name="step">
                <text>Import Your Data</text>
                <paragraph><text>Paragraph.</text></paragraph>
                <paragraph>
                    <ref_role domain="std" name="label" target="Import and Export Data">
                        <text>To learn more, see Import and Export Data</text>
                    </ref_role>
                </paragraph>
            </directive>
        </directive>""",
    )
