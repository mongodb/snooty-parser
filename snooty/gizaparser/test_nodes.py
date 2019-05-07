from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
from . import nodes
from ..types import Diagnostic, ProjectConfig


@dataclass
class Child:
    foo: str


@dataclass
class Parent:
    foo2: str


@dataclass
class SubstitutionTest(Parent):
    foo: str
    child: Child


def test_substitution() -> None:
    diagnostics: List[Diagnostic] = []
    replacements = {
        'verb': 'test',
        'noun': 'substitution'
    }
    test_string = r'{{verb}}ing {{noun}}. {{verb}}.'
    substituted_string = 'testing substitution. test.'
    assert nodes.substitute_text(test_string, replacements, diagnostics) == substituted_string

    obj = object()
    assert nodes.substitute(obj, replacements, diagnostics) is obj

    # Test complex substitution
    node = SubstitutionTest(
        foo=test_string,
        foo2=test_string,
        child=Child(test_string))
    substituted_node = nodes.substitute(node, replacements, diagnostics)
    assert substituted_node == SubstitutionTest(
        foo=substituted_string,
        foo2=substituted_string,
        child=Child(substituted_string))

    # Make sure that no substitution == ''
    assert diagnostics == []
    del replacements['noun']
    assert nodes.substitute_text(test_string, replacements, diagnostics) == 'testing . test.'
    assert len(diagnostics) == 1

    # Ensure the identity of the zero-substitutions case remains the same
    diagnostics = []
    test_string = 'foo'
    assert nodes.substitute_text(test_string, {}, diagnostics) is test_string
    assert not diagnostics


def test_inheritance() -> None:
    @dataclass
    class TestNode(nodes.Inheritable):
        content: Optional[str]

    project_config, diagnostics = ProjectConfig.open(Path('test_data'))
    parent = TestNode(
        ref='_parent',
        replacement={'foo': 'bar', 'old': ''},
        source=None,
        inherit=None,
        content='{{bar}}')
    child = TestNode(
        ref='child',
        replacement={'bar': 'baz', 'old': 'new'},
        source=nodes.Inherit('self.yaml', 'parent'),
        inherit=None,
        content=None)
    parent = nodes.inherit(project_config, parent, None, diagnostics)
    child = nodes.inherit(project_config, child, parent, diagnostics)

    assert child.replacement == {
        'foo': 'bar',
        'bar': 'baz',
        'old': 'new'}
    assert child.content == 'baz'
    assert not diagnostics
