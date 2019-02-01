from pathlib import Path
from . import rstparser
from .util import ast_to_testing_string
from .types import Diagnostic, ProjectConfig
from .parser import parse_rst, JSONVisitor


def test_tabs() -> None:
    root = Path('test_data')
    tabs_path = Path(root).joinpath(Path('test_tabs.rst'))
    project_config = ProjectConfig(root, '')
    parser = rstparser.Parser(project_config, JSONVisitor)
    page, diagnostics = parse_rst(parser, tabs_path, None)

    assert ast_to_testing_string(page.ast) == ''.join((
        '<root>',

        '<directive name="tabs"><directive name="tab"><text>bionic</text>',
        '<paragraph><text>Bionic content</text></paragraph></directive>',

        '<directive name="tab"><text>xenial</text><paragraph><text>',
        'Xenial content</text></paragraph></directive>',

        '<directive name="tab"><text>trusty</text><paragraph><text>',
        'Trusty content</text></paragraph></directive></directive>',

        '<directive name="tabs"><directive name="tab"><text>trusty</text><paragraph><text>',
        'Trusty content</text></paragraph></directive>',

        '<directive name="tab"><text>xenial</text><paragraph><text>',
        'Xenial content</text></paragraph></directive></directive>',

        '</root>'
    ))

    assert len(diagnostics) == 1 and \
        diagnostics[0].message.startswith('Unexpected field') and \
        diagnostics[0].start[0] == 36


def test_codeblock() -> None:
    root = Path('test_data')
    tabs_path = Path(root).joinpath(Path('test.rst'))
    project_config = ProjectConfig(root, '')
    parser = rstparser.Parser(project_config, JSONVisitor)

    # Test a simple code-block
    page, diagnostics = parse_rst(parser, tabs_path, '''
.. code-block:: sh

   foo bar
     indented
   end''')
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == ''.join((
        '<root>',
        '<code lang="sh" copyable="True">foo bar\n  indented\nend</code>'
        '</root>'
    ))

    # Test parsing of emphasize-lines
    page, diagnostics = parse_rst(parser, tabs_path, '''
.. code-block:: sh
   :copyable: false
   :emphasize-lines: 1, 2-3

   foo
   bar
   baz''')
    assert diagnostics == []
    assert ast_to_testing_string(page.ast) == ''.join((
        '<root>',
        '<code lang="sh" emphasize_lines="[(1, 1), (2, 3)]">foo\nbar\nbaz</code>'
        '</root>'
    ))

    # Test handling of out-of-range lines
    page, diagnostics = parse_rst(parser, tabs_path, '''
.. code-block:: sh
   :emphasize-lines: 10

   foo''')
    assert diagnostics[0].severity == Diagnostic.Level.warning
