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
        Path("test_data/test_product_landing"), backend, build_identifiers
    ) as project:
        project.build()

    return backend


def test_queryable_fields(backend: Backend) -> None:
    page_id = FileId("index.txt")
    page = backend.pages[page_id]

    # Assert index has successfully added itself to the toctree
    assert backend.metadata.get("toctree") == {
        "title": [
            {
                "type": "text",
                "position": {"start": {"line": 0}},
                "value": "Product Title",
            }
        ],
        "slug": "/",
        "children": [
            {
                "title": [
                    {
                        "type": "text",
                        "position": {"start": {"line": 0}},
                        "value": "Overview",
                    }
                ],
                "slug": "/",
                "children": [],
                "options": {"drawer": True},
            }
        ],
    }

    ast = page.ast
    section1 = ast.children[0]
    assert isinstance(section1, n.Section)

    # Section 1: Product Elevator Pitch

    # Skip "Elevator Pitch" Heading

    introduction = section1.children[1]
    check_ast_testing_string(
        introduction,
        """<directive domain="landing" name="introduction">
           <paragraph>
           <text>Elevator pitch.</text>
           </paragraph>
           </directive>""",
    )

    button = section1.children[2]
    check_ast_testing_string(
        button,
        """<directive domain="landing" name="button" class="left-column" uri="/path/to/download">
            <text>Download Compass</text></directive>""",
    )

    # Skip refrole

    image = section1.children[4]
    check_ast_testing_string(
        image,
        """<directive name="image" alt="Alternate captioning" class="right-column">
        <text>/path/to/image.png</text>
        </directive>""",
    )

    kicker = section1.children[5]
    check_ast_testing_string(
        kicker,
        """<directive domain="landing" name="kicker"><text>What You Can Do</text></directive>""",
    )

    # Section 2: Features and Use Cases
    section2 = section1.children[6]
    assert isinstance(section2, n.Section)

    # Skip "Features and Use Cases" Heading

    # Skip paragraph

    tabs = section2.children[2]
    assert isinstance(tabs, n.Parent)
    # There should be 2 tabs
    assert len(tabs.children) == 2

    tab1 = tabs.children[0]
    check_ast_testing_string(
        tab1,
        """<directive name="tab" tabid="import">
        <text>Import Your Data</text>
        <paragraph><text>Paragraph.</text></paragraph>
        <directive domain="landing" name="procedure">
            <directive domain="landing" name="step">
                <paragraph><text>Connect to Your Deployment</text></paragraph>
                <paragraph><text>Paragraph.</text></paragraph>
                <paragraph>
                    <ref_role domain="std" name="label" target="Connect to MongoDB">
                        <text>To learn more, see Connect to MongoDB</text>
                    </ref_role>
                </paragraph>
            </directive>
            <directive domain="landing" name="step">
                <paragraph><text>Import Your Data</text></paragraph>
                <paragraph><text>Paragraph.</text></paragraph>
                <paragraph>
                    <ref_role domain="std" name="label" target="Import and Export Data">
                        <text>To learn more, see Import and Export Data</text>
                    </ref_role>
                </paragraph>
            </directive>
        </directive>
    <directive name="image" class="right-column" alt="Alternate captioning"><text>/path/to/image.png</text></directive></directive>""",
    )

    tab2 = tabs.children[1]
    check_ast_testing_string(
        tab2,
        """<directive name="tab" tabid="query"><text>Query Your Data</text></directive>""",
    )

    kicker = section2.children[3]
    check_ast_testing_string(
        kicker,
        """<directive domain="landing" name="kicker"><text>Related Products &amp; Resources</text></directive>""",
    )

    # Section 3: Deeper Engagement
    section3 = section1.children[7]
    assert isinstance(section3, n.Section)

    # Skip paragraph

    card_group = section3.children[2]
    assert isinstance(card_group, n.Parent)
    assert len(card_group.children) == 3
    check_ast_testing_string(
        card_group,
        """<directive domain="landing" name="card-group" columns="3" style="compact">
            <directive domain="landing" name="card" cta="Call to action" url="https://www.url.com" icon="/path/to/icon" icon-alt="/path/to/icon-alt">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
            <directive domain="landing" name="card" cta="Call to action" url="https://www.url.com" icon="/path/to/icon" icon-alt="/path/to/icon-alt">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
            <directive domain="landing" name="card" cta="Call to action" url="https://www.url.com" icon="/path/to/icon" icon-alt="/path/to/icon-alt">
                <paragraph><text>Paragraph.</text></paragraph>
            </directive>
        </directive>""",
    )
