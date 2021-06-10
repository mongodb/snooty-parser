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
    with Project(
        Path("test_data/test_mongodb_domain"), backend, build_identifiers
    ) as project:
        project.build()

    return backend


# Test all directives exclusive to the mongodb domain
def test_mongodb_directives(backend: Backend) -> None:
    page_id = FileId("index.txt")
    page = backend.pages[page_id]
    assert len(page.static_assets) == 1

    ast = page.ast
    section = ast.children[0]
    assert isinstance(section, n.Section)

    introduction = section.children[1]
    check_ast_testing_string(
        introduction,
        """<directive domain="mongodb" name="introduction">
            <paragraph><text>
            This test project tests directives exclusive to the mongodb domain, which is used for mongodb-specific directives.
            </text></paragraph>
        </directive>""",
    )

    button = section.children[2]
    check_ast_testing_string(
        button,
        """<directive domain="mongodb" name="button" uri="/path/to/download">
            <text>Button text</text></directive>""",
    )

    card_group = section.children[3]
    assert isinstance(card_group, n.Parent)
    assert len(card_group.children) == 3
    check_ast_testing_string(
        card_group,
        """<directive domain="mongodb" name="card-group" columns="3" style="compact" layout="carousel">
            <directive domain="mongodb" name="card" headline="Run a self-managed database" cta="Get started with MongoDB" url="http://mongodb.com" icon="/images/pink.png" icon-alt="Alt text" tag="server" checksum="71bf03ab0c5b8d46f0c03b77db6bd18a77d984d216c62c3519dfb45c162cd86b">
                <paragraph><text>Download and install the MongoDB database on your own\ninfrastructure.</text></paragraph>
            </directive>
            <directive domain="mongodb" name="card" cta="Call to action" url="https://www.url.com" icon="/images/pink.png" icon-alt="Alt text" checksum="71bf03ab0c5b8d46f0c03b77db6bd18a77d984d216c62c3519dfb45c162cd86b">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
            <directive domain="mongodb" name="card" cta="Call to action" url="https://www.url.com" icon="/images/pink.png" icon-alt="Alt text" checksum="71bf03ab0c5b8d46f0c03b77db6bd18a77d984d216c62c3519dfb45c162cd86b">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
        </directive>""",
    )

    kicker = section.children[4]
    check_ast_testing_string(
        kicker,
        """<directive domain="mongodb" name="kicker"><text>A kicker is a subheader above a main header</text></directive>""",
    )

    procedure = section.children[5]
    check_ast_testing_string(
        procedure,
        """
        <directive domain="mongodb" name="procedure">
            <directive domain="mongodb" name="step">
                <text>Connect to Your Deployment</text>
                <paragraph><text>Paragraph.</text></paragraph>
                <paragraph>
                    <ref_role domain="std" name="label" target="Connect to MongoDB">
                        <text>To learn more, see Connect to MongoDB</text>
                    </ref_role>
                </paragraph>
            </directive>
            <directive domain="mongodb" name="step">
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

    cta = section.children[6]
    check_ast_testing_string(
        cta,
        """<directive domain="mongodb" name="cta"><paragraph><reference refuri="https://docs.mongodb.com/manual/introduction/"><text>Read the Introduction to MongoDB</text></reference></paragraph></directive>""",
    )
