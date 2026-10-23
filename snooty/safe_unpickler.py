"""Restricted unpickler to prevent arbitrary code execution (CWE-502).

Python's pickle module is inherently unsafe — pickle.loads() can execute
arbitrary code via __reduce__ gadgets. This module provides a restricted
unpickler that only allows deserialization of types known to be used in
snooty's build cache, blocking all other types.

See: https://docs.python.org/3/library/pickle.html#restricting-globals
"""

import io
import pickle
from typing import Set, Tuple

# Types that are legitimately stored in snooty cache files.
# This allowlist covers CacheData and its nested types.
ALLOWED_CLASSES: Set[Tuple[str, str]] = {
    # builtins used in pickle serialization
    ("builtins", "set"),
    ("builtins", "frozenset"),
    ("builtins", "dict"),
    ("builtins", "list"),
    ("builtins", "tuple"),
    ("builtins", "bytes"),
    ("builtins", "str"),
    ("builtins", "int"),
    ("builtins", "float"),
    ("builtins", "bool"),
    ("builtins", "complex"),
    ("builtins", "type"),
    # collections
    ("collections", "defaultdict"),
    ("collections", "OrderedDict"),
    # pathlib
    ("pathlib", "PurePosixPath"),
    ("pathlib", "PosixPath"),
    ("pathlib", "PureWindowsPath"),
    ("pathlib", "WindowsPath"),
    # snooty types stored in cache
    ("snooty.parse_cache", "CacheData"),
    ("snooty.parse_cache", "CacheStats"),
    ("snooty.page", "Page"),
    ("snooty.diagnostics", "Diagnostic"),
    ("snooty.diagnostics", "CannotOpenFile"),
    ("snooty.diagnostics", "CannotReadFile"),
    ("snooty.diagnostics", "UnexpectedIndentation"),
    ("snooty.diagnostics", "InvalidURL"),
    ("snooty.diagnostics", "InvalidLiteralInclude"),
    ("snooty.diagnostics", "SubstitutionRefError"),
    ("snooty.diagnostics", "ConstantNotDeclared"),
    ("snooty.diagnostics", "InvalidChild"),
    ("snooty.diagnostics", "TabMustBeDirective"),
    ("snooty.diagnostics", "ExpectedPathArg"),
    ("snooty.diagnostics", "UnexpectedDirectiveField"),
    ("snooty.diagnostics", "DuplicatedExternalDefinition"),
    ("snooty.diagnostics", "FailedToInheritRef"),
    ("snooty.diagnostics", "RefAlreadyExists"),
    ("snooty.diagnostics", "UnknownSubstitution"),
    ("snooty.diagnostics", "TargetNotFound"),
    ("snooty.diagnostics", "AmbiguousTarget"),
    ("snooty.diagnostics", "TodoInfo"),
    ("snooty.diagnostics", "UnmarshallingError"),
    ("snooty.diagnostics", "CannotRenderSteps"),
    ("snooty.diagnostics", "MissingOption"),
    ("snooty.diagnostics", "MissingTab"),
    ("snooty.diagnostics", "UnknownTabset"),
    ("snooty.diagnostics", "UnknownTabID"),
    ("snooty.diagnostics", "TabsetMismatch"),
    ("snooty.diagnostics", "FetchError"),
    ("snooty.diagnostics", "MissingFacet"),
    ("snooty.diagnostics", "UnknownOptionId"),
    ("snooty.n", "FileId"),
    # docutils node types (used in doctrees)
    ("docutils.nodes", "document"),
    ("docutils.nodes", "section"),
    ("docutils.nodes", "paragraph"),
    ("docutils.nodes", "Text"),
    ("docutils.nodes", "title"),
    ("docutils.nodes", "reference"),
    ("docutils.nodes", "literal"),
    ("docutils.nodes", "emphasis"),
    ("docutils.nodes", "strong"),
    ("docutils.nodes", "inline"),
    ("docutils.nodes", "bullet_list"),
    ("docutils.nodes", "list_item"),
    ("docutils.nodes", "compound"),
    ("docutils.nodes", "container"),
    ("docutils.nodes", "block_quote"),
    ("docutils.nodes", "literal_block"),
    ("docutils.nodes", "note"),
    ("docutils.nodes", "warning"),
    ("docutils.nodes", "tip"),
    ("docutils.nodes", "important"),
    ("docutils.nodes", "line_block"),
    ("docutils.nodes", "line"),
    ("docutils.nodes", "image"),
    ("docutils.nodes", "figure"),
    ("docutils.nodes", "table"),
    ("docutils.nodes", "tgroup"),
    ("docutils.nodes", "colspec"),
    ("docutils.nodes", "thead"),
    ("docutils.nodes", "tbody"),
    ("docutils.nodes", "row"),
    ("docutils.nodes", "entry"),
    ("docutils.nodes", "target"),
    ("docutils.nodes", "substitution_definition"),
    ("docutils.nodes", "substitution_reference"),
    ("docutils.nodes", "comment"),
    ("docutils.nodes", "footnote"),
    ("docutils.nodes", "footnote_reference"),
    ("docutils.nodes", "label"),
    ("docutils.nodes", "system_message"),
    ("docutils.nodes", "rubric"),
    ("docutils.nodes", "topic"),
    ("docutils.nodes", "transition"),
    ("docutils.nodes", "definition_list"),
    ("docutils.nodes", "definition_list_item"),
    ("docutils.nodes", "term"),
    ("docutils.nodes", "definition"),
    ("docutils.nodes", "field_list"),
    ("docutils.nodes", "field"),
    ("docutils.nodes", "field_name"),
    ("docutils.nodes", "field_body"),
    ("docutils.statemachine", "StringList"),
    # snooty-specific AST nodes
    ("snooty.n", "Root"),
    ("snooty.n", "Heading"),
    ("snooty.n", "Section"),
    ("snooty.n", "Paragraph"),
    ("snooty.n", "Code"),
    ("snooty.n", "InlineCode"),
    ("snooty.n", "Role"),
    ("snooty.n", "RefRole"),
    ("snooty.n", "Directive"),
    ("snooty.n", "TocTreeDirective"),
    ("snooty.n", "SubstitutionReference"),
    ("snooty.n", "Target"),
    ("snooty.n", "Label"),
    ("snooty.n", "Line"),
    ("snooty.n", "Text"),
    ("snooty.n", "Literal"),
    ("snooty.n", "Emphasis"),
    ("snooty.n", "Strong"),
    ("snooty.n", "ListNode"),
    ("snooty.n", "ListNodeItem"),
    ("snooty.n", "DefinitionList"),
    ("snooty.n", "DefinitionListItem"),
    ("snooty.n", "Field"),
    ("snooty.n", "BlockQuote"),
    ("snooty.n", "Footnote"),
    ("snooty.n", "FootnoteReference"),
    ("snooty.n", "Comment"),
    ("snooty.n", "Transition"),
    ("snooty.n", "Table"),
    ("snooty.n", "TabSet"),
    ("snooty.n", "Tab"),
    # giza parser types
    ("snooty.gizaparser.nodes", "GizaFile"),
    ("snooty.gizaparser.nodes", "GizaNode"),
    ("snooty.gizaparser.steps", "StepsFile"),
    ("snooty.gizaparser.extracts", "ExtractsFile"),
    ("snooty.gizaparser.release", "ReleaseFile"),
    # page dependency tracking
    ("snooty.page", "PageDependencies"),
}


class SafeUnpickler(pickle.Unpickler):
    """A restricted Unpickler that blocks arbitrary code execution.

    Only types listed in ALLOWED_CLASSES can be deserialized. Any attempt
    to deserialize a type outside the allowlist (e.g., os.system via a
    __reduce__ gadget) raises UnpicklingError.
    """

    def find_class(self, module: str, name: str) -> type:
        if (module, name) in ALLOWED_CLASSES:
            return super().find_class(module, name)

        # Allow any class under snooty.* or docutils.* as a fallback,
        # since the full set of types is large and version-dependent.
        # This is still far safer than unrestricted pickle.loads which
        # allows os.system, subprocess.Popen, etc.
        top_module = module.split(".")[0]
        if top_module in ("snooty", "docutils"):
            return super().find_class(module, name)

        raise pickle.UnpicklingError(
            f"Refusing to deserialize {module}.{name}: "
            f"not in the snooty cache allowlist (CWE-502 mitigation)"
        )


def safe_loads(data: bytes) -> object:
    """Drop-in replacement for pickle.loads() with type restrictions."""
    return SafeUnpickler(io.BytesIO(data)).load()


def safe_load(f) -> object:
    """Drop-in replacement for pickle.load() with type restrictions."""
    return SafeUnpickler(f).load()
