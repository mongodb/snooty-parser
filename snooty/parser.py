import collections
import docutils.nodes
import logging
import multiprocessing
import os
import pwd
import subprocess
from functools import partial
from pathlib import Path, PurePath
from typing import Any, Dict, Tuple, Optional, Set, List, Iterable
from typing_extensions import Protocol
import docutils.utils

from . import gizaparser, rstparser, util
from .gizaparser.nodes import GizaCategory
from .types import Diagnostic, SerializableType, EmbeddedRstParser, Page, \
    StaticAsset, ProjectConfigError, ProjectConfig

NO_CHILDREN = {'substitution_reference'}
RST_EXTENSIONS = {'.rst', '.txt'}
logger = logging.getLogger(__name__)


def transform_literal_include(path: Path,
                              doc: Dict[str, SerializableType],
                              options: Dict[str, SerializableType]) -> None:
    """Transform a literal-include directive AST node into a code node."""
    text = path.read_text(encoding='utf-8')
    lines = text.split('\n')
    start_after = 0
    end_before = len(lines)
    if 'start-after' in options:
        start_after_text = options['start-after']
        assert isinstance(start_after_text, str)
        start_after = next((idx for idx, line in enumerate(lines)
                            if start_after_text in line), -1)
        if start_after < 0:
            raise ValueError(f'"{start_after_text}" not found in {path}')

    if 'end-before' in options:
        end_before_text = options['end-before']
        assert isinstance(end_before_text, str)
        end_before = next((idx for idx, line in enumerate(lines, start=start_after)
                           if end_before_text in line), -1)
        if end_before < 0:
            raise ValueError(f'"{end_before_text}" not found in {path}')
        end_before -= start_after

    lines = lines[(start_after + 1):end_before]

    if 'dedent' in options:
        try:
            dedent = min(len(line) - len(line.lstrip()) for line in lines if len(line.lstrip()) > 0)
        except ValueError:
            # Handle the (unlikely) case where there are no non-empty lines
            dedent = 0
        lines = [line[dedent:] for line in lines]

    doc.clear()
    doc.update({
        'type': 'code',
        'lang': options['language'] if 'language' in options else path.suffix.lstrip('.'),
        'copyable': 'copyable' in options,
        'value': '\n'.join(lines)
    })

    if 'emphasize_lines' in options:
        doc['emphasize_lines'] = options['emphasize_lines']

    options.clear()


class JSONVisitor:
    """Node visitor that creates a JSON-serializable structure."""
    def __init__(self,
                 source_path: Path,
                 docpath: PurePath,
                 document: docutils.nodes.document) -> None:
        self.source_path = source_path
        self.docpath = docpath
        self.document = document
        self.state: List[Dict[str, Any]] = []
        self.diagnostics: List[Diagnostic] = []
        self.static_assets: Set[StaticAsset] = set()

    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        node_name = node.__class__.__name__
        if node_name == 'system_message':
            level = int(node['level'])
            if level >= 2:
                level = Diagnostic.Level.from_docutils(level)
                msg = node[0].astext()
                self.diagnostics.append(Diagnostic.create(level, msg, util.get_line(node)))
            raise docutils.nodes.SkipNode()
        elif node_name in ('definition', 'field_list'):
            return

        if node_name == 'document':
            self.state.append({
                'type': 'root',
                'children': [],
                'position': {
                    'start': {'line': 0}
                }
            })
            return

        doc: Dict[str, SerializableType] = {
            'type': node_name,
            'position': {
                'start': {'line': util.get_line(node)}
            }
        }

        if node_name == 'field':
            key = node.children[0].astext()
            value = node.children[1].astext()
            self.state[-1].setdefault('options', {})[key] = value
            raise docutils.nodes.SkipNode()
        elif node_name == 'code':
            doc['type'] = 'code'
            doc['lang'] = node['lang']
            doc['copyable'] = node['copyable']
            if node['emphasize_lines']:
                doc['emphasize_lines'] = node['emphasize_lines']
            doc['value'] = node.astext()
            self.state[-1]['children'].append(doc)
            raise docutils.nodes.SkipNode()

        self.state.append(doc)

        if node_name == 'Text':
            doc['type'] = 'text'
            doc['value'] = str(node)
            return

        if node_name == 'directive':
            self.handle_directive(node, doc)
            return
        elif node_name == 'role':
            doc['name'] = node['name']
            if 'label' in node:
                doc['label'] = node['label']
            if 'target' in node:
                doc['target'] = node['target']
        elif node_name == 'target':
            doc['type'] = 'target'
            doc['ids'] = node['ids']
            if 'refuri' in node:
                doc['refuri'] = node['refuri']
        elif node_name == 'definition_list':
            doc['type'] = 'definitionList'
        elif node_name == 'definition_list_item':
            doc['type'] = 'definitionListItem'
            doc['term'] = []
        elif node_name == 'bullet_list':
            doc['type'] = 'list'
            doc['ordered'] = False
        elif node_name == 'enumerated_list':
            doc['type'] = 'list'
            doc['ordered'] = True
        elif node_name == 'list_item':
            doc['type'] = 'listItem'
        elif node_name == 'title':
            doc['type'] = 'heading'
        elif node_name == 'reference':
            for attr_name in ('refuri', 'refname'):
                if attr_name in node:
                    doc[attr_name] = node[attr_name]
        elif node_name == 'substitution_definition':
            name = node['names'][0]
            doc['name'] = name
        elif node_name == 'substitution_reference':
            doc['name'] = node['refname']
            return

        doc['children'] = []

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        node_name = node.__class__.__name__
        if len(self.state) == 1 or node_name == 'definition':
            return

        popped = self.state.pop()

        if popped['type'] == 'term':
            self.state[-1]['term'] = popped['children']
        elif self.state[-1]['type'] not in NO_CHILDREN:
            if 'children' not in self.state[-1]:
                print(self.state[-1])
            self.state[-1]['children'].append(popped)

    def handle_directive(self, node: docutils.nodes.Node, doc: Dict[str, SerializableType]) -> None:
        name = node['name']
        doc['name'] = name

        options = node['options'] or {}
        if node.children and node.children[0].__class__.__name__ == 'directive_argument':
            visitor = self.__make_child_visitor()
            node.children[0].walkabout(visitor)
            argument = visitor.state[-1]['children']
            doc['argument'] = argument
            node.children = node.children[1:]
        else:
            argument = []
            doc['argument'] = argument

        argument_text = None
        try:
            argument_text = argument[0]['value']
        except (IndexError, KeyError):
            pass

        if name in {'figure', 'image'}:
            if argument_text is None:
                self.diagnostics.append(
                    Diagnostic.error(f'"{name}" expected a path argument', util.get_line(node)))
                return

            try:
                static_asset = self.add_static_asset(Path(argument_text))
                options['checksum'] = static_asset.checksum
            except OSError as err:
                msg = f'"{name}" could not open "{argument_text}": {os.strerror(err.errno)}'
                self.diagnostics.append(Diagnostic.error(msg, util.get_line(node)))
        elif name == 'literalinclude':
            if argument_text is None:
                lineno = util.get_line(node)
                self.diagnostics.append(
                    Diagnostic.error('"literalinclude" expected a path argument', lineno))
                return

            try:
                code_path = Path(argument_text)
                _, code_path = util.reroot_path(code_path, self.docpath, self.source_path)
                transform_literal_include(code_path, doc, options)
            except OSError as err:
                msg = '"literalinclude" could not open "{}": {}'.format(
                    argument_text, os.strerror(err.errno))
                self.diagnostics.append(Diagnostic.error(msg, util.get_line(node)))
            except ValueError as err:
                msg = f'Invalid "literalinclude": {err}'
                self.diagnostics.append(Diagnostic.error(msg, util.get_line(node)))
            return

        if options:
            doc['options'] = options

        doc['children'] = []

    def add_static_asset(self, path: Path) -> StaticAsset:
        fileid, path = util.reroot_path(path, self.docpath, self.source_path)
        static_asset = StaticAsset.load(fileid.as_posix(), path)
        self.static_assets.add(static_asset)
        return static_asset

    def add_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)

    def __make_child_visitor(self) -> 'JSONVisitor':
        visitor = type(self)(self.source_path, self.docpath, self.document)
        visitor.diagnostics = self.diagnostics
        return visitor


class InlineJSONVisitor(JSONVisitor):
    """A JSONVisitor subclass which does not emit block nodes."""
    def dispatch_visit(self, node: docutils.nodes.Node) -> None:
        if isinstance(node, docutils.nodes.Body):
            return

        JSONVisitor.dispatch_visit(self, node)

    def dispatch_departure(self, node: docutils.nodes.Node) -> None:
        if isinstance(node, docutils.nodes.Body):
            return

        JSONVisitor.dispatch_departure(self, node)


def parse_rst(parser: rstparser.Parser[JSONVisitor],
              path: Path,
              text: Optional[str] = None) -> Tuple[Page, List[Diagnostic]]:
    visitor, text = parser.parse(path, text)

    return Page(
        path,
        text,
        visitor.state[-1],
        visitor.static_assets), visitor.diagnostics


def make_embedded_rst_parser(project_config: ProjectConfig,
                             page: Page,
                             diagnostics: List[Diagnostic]) -> EmbeddedRstParser:
    def parse_embedded_rst(rst: str,
                           lineno: int,
                           inline: bool) -> List[SerializableType]:
        # Crudely make docutils line numbers match
        text = '\n' * lineno + rst.strip()
        visitor_class = InlineJSONVisitor if inline else JSONVisitor
        parser = rstparser.Parser(project_config, visitor_class)
        visitor, _ = parser.parse(page.source_path, text)
        children: List[SerializableType] = visitor.state[-1]['children']

        diagnostics.extend(visitor.diagnostics)
        page.static_assets.update(visitor.static_assets)

        return children

    return parse_embedded_rst


def get_giza_category(path: PurePath) -> str:
    return path.name.split('-', 1)[0]


class ProjectBackend(Protocol):
    def on_progress(self, progress: int, total: int, message: str) -> None: ...

    def on_diagnostics(self, path: PurePath, diagnostics: List[Diagnostic]) -> None: ...

    def on_update(self, prefix: List[str], page_id: str, page: Page) -> None: ...

    def on_delete(self, page_id: str) -> None: ...


class Project:
    def __init__(self,
                 root: Path,
                 backend: ProjectBackend) -> None:
        root = root.resolve(strict=True)
        self.config, config_diagnostics = ProjectConfig.open(root)

        if config_diagnostics:
            backend.on_diagnostics(self.config.root, config_diagnostics)
            raise ProjectConfigError()

        self.root = self.config.source_path
        self.parser = rstparser.Parser(self.config, JSONVisitor)
        self.static_assets: Dict[PurePath, Set[StaticAsset]] = collections.defaultdict(set)
        self.backend = backend

        self.yaml_mapping: Dict[str, GizaCategory[Any]] = {
            'steps': gizaparser.steps.GizaStepsCategory(self.config),
            'extracts': gizaparser.extracts.GizaExtractsCategory(self.config),
            'release': gizaparser.release.GizaReleaseSpecificationCategory(self.config),
        }

        username = pwd.getpwuid(os.getuid()).pw_name
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            cwd=root,
            encoding='utf-8').strip()
        self.prefix = [self.config.name, username, branch]

    def get_page_id(self, path: PurePath) -> str:
        page_id = path.with_suffix('').relative_to(self.root).as_posix()
        return '/'.join(self.prefix + [page_id])

    def update(self, path: Path, optional_text: Optional[str] = None) -> None:
        diagnostics: Dict[PurePath, List[Diagnostic]] = {path: []}
        prefix = get_giza_category(path)
        _, ext = os.path.splitext(path)
        pages: List[Page] = []
        if ext in RST_EXTENSIONS:
            page, page_diagnostics = parse_rst(self.parser, path, optional_text)
            pages.append(page)
            diagnostics[path] = page_diagnostics
        elif ext == '.yaml' and prefix in self.yaml_mapping:
            file_id = os.path.basename(path)
            giza_category = self.yaml_mapping[prefix]
            needs_rebuild = set((file_id,)).union(*(
                category.dg.dependents[file_id] for category in self.yaml_mapping.values()))
            logger.debug('needs_rebuild: %s', ','.join(needs_rebuild))
            for file_id in needs_rebuild:
                file_diagnostics: List[Diagnostic] = []
                try:
                    giza_node = giza_category.reify_file_id(file_id, diagnostics)
                except KeyError:
                    logging.warn('No file found in registry: %s', file_id)
                    continue

                steps, text, parse_diagnostics = giza_category.parse(path, optional_text)
                file_diagnostics.extend(parse_diagnostics)

                def create_page() -> Tuple[Page, EmbeddedRstParser]:
                    page = Page(giza_node.path, text, {})
                    return page, make_embedded_rst_parser(self.config, page, file_diagnostics)

                giza_category.add(path, text, steps)
                pages = giza_category.to_pages(create_page, giza_node.data)
                path = giza_node.path
                diagnostics.setdefault(path).extend(file_diagnostics)
        else:
            raise ValueError('Unknown file type: ' + str(path))

        for source_path, diagnostic_list in diagnostics.items():
            self.backend.on_diagnostics(source_path, diagnostic_list)

        for page in pages:
            self.backend.on_update(self.prefix, self.get_page_id(path), page)

    def delete(self, path: PurePath) -> None:
        file_id = os.path.basename(path)
        for giza_category in self.yaml_mapping.values():
            del giza_category[file_id]

        self.backend.on_delete(self.get_page_id(path))

    def build(self) -> None:
        all_yaml_diagnostics: Dict[PurePath, List[Diagnostic]] = {}
        with multiprocessing.Pool() as pool:
            paths = util.get_files(self.root, RST_EXTENSIONS)
            logger.debug('Processing rst files')
            for page, diagnostics in pool.imap_unordered(partial(parse_rst, self.parser), paths):
                self.backend.on_update(self.prefix, self.get_page_id(page.get_id()), page)
                self.backend.on_diagnostics(page.source_path, diagnostics)

        # Categorize our YAML files
        logger.debug('Categorizing YAML files')
        categorized: Dict[str, List[Path]] = collections.defaultdict(list)
        for path in util.get_files(self.root, ('.yaml',)):
            prefix = get_giza_category(path)
            if prefix in self.yaml_mapping:
                categorized[prefix].append(path)

        # Initialize our YAML file registry
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug('Parsing %s YAML', prefix)
            for path in categorized[prefix]:
                steps, text, diagnostics = giza_category.parse(path)
                all_yaml_diagnostics[path] = diagnostics
                giza_category.add(path, text, steps)

        # Now that all of our YAML files are loaded, generate a page for each one
        for prefix, giza_category in self.yaml_mapping.items():
            logger.debug('Processing %s YAML: %d nodes', prefix, len(giza_category))
            for file_id, giza_node in giza_category.reify_all_files(all_yaml_diagnostics):
                def create_page() -> Tuple[Page, EmbeddedRstParser]:
                    page = Page(giza_node.path, giza_node.text, {})
                    return page, make_embedded_rst_parser(
                        self.config, page, all_yaml_diagnostics.setdefault(giza_node.path, []))

                for page in giza_category.to_pages(create_page, giza_node.data):
                    self.backend.on_update(self.prefix, self.get_page_id(page.get_id()), page)
                    self.backend.on_diagnostics(
                        page.source_path, all_yaml_diagnostics.get(page.source_path, []))
