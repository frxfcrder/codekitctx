from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tree_sitter import Language, Node, Parser

from codekitctx.parser.base import Symbol

_LANG_BY_SUFFIX: Dict[str, Tuple[str, str]] = {
    ".py": ("python", "python"),
    ".pyi": ("python", "python"),
    ".js": ("javascript", "javascript"),
    ".jsx": ("javascript", "javascript"),
    ".mjs": ("javascript", "javascript"),
    ".cjs": ("javascript", "javascript"),
    ".ts": ("typescript", "typescript"),
    ".mts": ("typescript", "typescript"),
    ".cts": ("typescript", "typescript"),
    ".tsx": ("typescript", "tsx"),
    ".rs": ("rust", "rust"),
    ".go": ("go", "go"),
    ".java": ("java", "java"),
    ".c": ("c", "c"),
    ".h": ("c", "c"),
    ".cpp": ("cpp", "cpp"),
    ".cc": ("cpp", "cpp"),
    ".cxx": ("cpp", "cpp"),
    ".hpp": ("cpp", "cpp"),
    ".hh": ("cpp", "cpp"),
    ".hxx": ("cpp", "cpp"),
    ".cs": ("csharp", "csharp"),
    ".rb": ("ruby", "ruby"),
    ".rake": ("ruby", "ruby"),
    ".gemspec": ("ruby", "ruby"),
}

_NODE_KINDS: Dict[str, Dict[str, str]] = {
    "python": {
        "function_definition": "function",
        "class_definition": "class",
    },
    "javascript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "class_declaration": "class",
        "lexical_declaration": "variable",
        "variable_declaration": "variable",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
    },
    "typescript": {
        "function_declaration": "function",
        "generator_function_declaration": "function",
        "method_definition": "method",
        "class_declaration": "class",
        "lexical_declaration": "variable",
        "variable_declaration": "variable",
        "interface_declaration": "interface",
        "type_alias_declaration": "type",
        "enum_declaration": "enum",
        "abstract_class_declaration": "class",
    },
    "rust": {
        "function_item": "function",
        "struct_item": "struct",
        "enum_item": "enum",
        "trait_item": "trait",
        "impl_item": "impl",
        "mod_item": "module",
        "macro_definition": "macro",
        "type_item": "type",
        "const_item": "const",
        "static_item": "static",
    },
    "go": {
        "function_declaration": "function",
        "method_declaration": "method",
        "type_declaration": "type",
    },
    "java": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "enum_declaration": "enum",
        "record_declaration": "class",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "annotation_type_declaration": "annotation",
    },
    "c": {
        "function_definition": "function",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "type_definition": "type",
        "declaration": "declaration",
    },
    "cpp": {
        "function_definition": "function",
        "class_specifier": "class",
        "struct_specifier": "struct",
        "enum_specifier": "enum",
        "namespace_definition": "namespace",
        "template_declaration": "template",
        "type_definition": "type",
        "declaration": "declaration",
    },
    "csharp": {
        "class_declaration": "class",
        "interface_declaration": "interface",
        "struct_declaration": "struct",
        "enum_declaration": "enum",
        "record_declaration": "class",
        "method_declaration": "method",
        "constructor_declaration": "constructor",
        "property_declaration": "property",
        "delegate_declaration": "delegate",
    },
    "ruby": {
        "method": "method",
        "singleton_method": "method",
        "class": "class",
        "module": "module",
        "singleton_class": "class",
    },
}

_NAME_FIELDS = ("name", "declarator")


class SitterParser:
    def __init__(self) -> None:
        self._languages = self._load_languages()
        self._parsers: Dict[str, Parser] = {}

    @staticmethod
    def _load_languages() -> Dict[str, Language]:
        import tree_sitter_c
        import tree_sitter_c_sharp
        import tree_sitter_cpp
        import tree_sitter_go
        import tree_sitter_java
        import tree_sitter_javascript
        import tree_sitter_python
        import tree_sitter_ruby
        import tree_sitter_rust
        import tree_sitter_typescript

        return {
            "python": Language(tree_sitter_python.language()),
            "javascript": Language(tree_sitter_javascript.language()),
            "typescript": Language(tree_sitter_typescript.language_typescript()),
            "tsx": Language(tree_sitter_typescript.language_tsx()),
            "rust": Language(tree_sitter_rust.language()),
            "go": Language(tree_sitter_go.language()),
            "java": Language(tree_sitter_java.language()),
            "c": Language(tree_sitter_c.language()),
            "cpp": Language(tree_sitter_cpp.language()),
            "csharp": Language(tree_sitter_c_sharp.language()),
            "ruby": Language(tree_sitter_ruby.language()),
        }

    def parse(self, content: str, path: Path) -> List[Symbol]:
        resolved = self.resolve_language(path)
        if resolved is None:
            return []

        lang_key, variant = resolved
        language = self._languages.get(variant) or self._languages.get(lang_key)
        if language is None:
            return []

        cache_key = variant if variant in self._languages else lang_key
        parser = self._parsers.get(cache_key)
        if parser is None:
            parser = Parser(language)
            self._parsers[cache_key] = parser

        tree = parser.parse(content.encode("utf-8"))
        kind_map = _NODE_KINDS.get(lang_key, {})
        return self._walk(tree.root_node, kind_map, parent=None)

    @staticmethod
    def resolve_language(path: Path) -> Optional[Tuple[str, str]]:
        return _LANG_BY_SUFFIX.get(path.suffix.lower())

    @staticmethod
    def supported_suffixes() -> List[str]:
        return sorted(_LANG_BY_SUFFIX)

    def _walk(
        self,
        node: Node,
        kind_map: Dict[str, str],
        parent: Optional[str],
    ) -> List[Symbol]:
        symbols: List[Symbol] = []
        for child in node.children:
            if not child.is_named:
                continue
            kind = kind_map.get(child.type)
            if kind is not None:
                symbol = self._to_symbol(child, kind, parent, kind_map)
                if symbol is not None:
                    symbols.append(symbol)
            else:
                symbols.extend(self._walk(child, kind_map, parent))
        return symbols

    def _to_symbol(
        self,
        node: Node,
        kind: str,
        parent: Optional[str],
        kind_map: Dict[str, str],
    ) -> Optional[Symbol]:
        name = self._extract_name(node)
        if not name and kind != "impl":
            name = kind

        # JS/TS lexical_declaration wraps the real binding
        if kind == "variable":
            name = self._extract_variable_name(node) or name
            if not name:
                return None

        # Go type_declaration wraps type specs
        if kind == "type":
            name = self._extract_type_name(node) or name
            if not name:
                return None

        # Rust impl_item: show type if present
        if kind == "impl":
            name = self._extract_impl_name(node) or "impl"

        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        signature = self._signature(node)

        # Nest container members under their parent name
        next_parent = name if kind in (
            "class", "trait", "impl", "interface", "module", "struct", "enum", "namespace", "record", "annotation"
        ) else parent
        if kind in ("method", "function", "constructor", "property"):
            next_parent = parent

        children = self._walk(node, kind_map, parent=next_parent) if kind in (
            "class", "trait", "impl", "interface", "module", "enum", "type",
            "struct", "namespace", "record", "annotation"
        ) else []

        # For methods/functions inside classes, attach parent for display
        if parent and kind in ("method", "function"):
            pass  # parent already set

        # Collect nested symbols that appear as direct named children for rust impl etc.
        if kind == "impl" and not children:
            children = self._walk(node, kind_map, parent=name)

        return Symbol(
            name=name,
            kind=kind,
            line_start=line_start,
            line_end=line_end,
            signature=signature,
            parent=parent,
            children=children,
        )

    @staticmethod
    def _extract_name(node: Node) -> str:
        for field_name in _NAME_FIELDS:
            child = node.child_by_field_name(field_name)
            if child is None:
                continue
            name = SitterParser._name_from_node(child)
            if name:
                return name
        for child in node.children:
            if not child.is_named:
                continue
            if child.type in ("identifier", "type_identifier", "field_identifier", "property_identifier", "constant"):
                return child.text.decode("utf-8") if child.text else ""
        return ""

    @staticmethod
    def _name_from_node(node: Node) -> str:
        if node.type in ("identifier", "type_identifier", "field_identifier", "property_identifier", "constant", "namespace_identifier"):
            return node.text.decode("utf-8") if node.text else ""

        for field_name in ("name", "declarator", "identifier"):
            child = node.child_by_field_name(field_name)
            if child is not None:
                name = SitterParser._name_from_node(child)
                if name:
                    return name

        # Walk declarator chains: function_declarator -> pointer_declarator -> identifier
        for child in node.children:
            if not child.is_named:
                continue
            if child.type in (
                "function_declarator", "pointer_declarator", "reference_declarator",
                "array_declarator", "parenthesized_declarator", "qualified_identifier",
                "template_function", "operator_name", "namespace_identifier",
            ):
                name = SitterParser._name_from_node(child)
                if name:
                    return name
            if child.type in ("identifier", "type_identifier", "field_identifier", "property_identifier", "constant", "namespace_identifier"):
                return child.text.decode("utf-8") if child.text else ""
        return ""

    @staticmethod
    def _extract_variable_name(node: Node) -> str:
        for child in node.children:
            if not child.is_named:
                continue
            if child.type in ("lexical_declaration", "variable_declaration", "variable_declarator", "pair"):
                nested = SitterParser._extract_name(child)
                if nested:
                    return nested
            if child.type in ("variable_declarator", "pair", "identifier", "property_identifier"):
                name = SitterParser._extract_name(child)
                if name:
                    return name
                if child.text:
                    first = child.text.decode("utf-8").split("=")[0].strip()
                    first = first.replace("const ", "").replace("let ", "").replace("var ", "").strip()
                    if first:
                        return first.split()[0].strip(",;")
        return ""

    @staticmethod
    def _extract_type_name(node: Node) -> str:
        for child in node.children:
            if not child.is_named:
                continue
            if child.type == "type_spec":
                name = SitterParser._extract_name(child)
                if name:
                    return name
            if child.type in ("type_identifier", "identifier"):
                return child.text.decode("utf-8") if child.text else ""
        return ""

    @staticmethod
    def _extract_impl_name(node: Node) -> str:
        for field in ("type", "trait"):
            child = node.child_by_field_name(field)
            if child is not None and child.text:
                return child.text.decode("utf-8").split("<")[0].strip()
        for child in node.children:
            if not child.is_named:
                continue
            if child.type in ("type_identifier", "generic_type", "trait_bound"):
                text = child.text.decode("utf-8") if child.text else ""
                if text:
                    return text.split("<")[0].split(" for ")[-1].strip()
        return ""

    def _signature(self, node: Node) -> str:
        # signature = first line up to body/block
        text = node.text.decode("utf-8") if node.text else ""
        if not text:
            return ""
        for marker in (" {\n", " {\r\n", "{\n", ":\n", ":\r\n"):
            idx = text.find(marker)
            if idx != -1:
                text = text[:idx]
                break
        else:
            text = text.split("\n", 1)[0]
        return " ".join(text.split())


_parser: Optional[SitterParser] = None


def get_parser() -> SitterParser:
    global _parser
    if _parser is None:
        _parser = SitterParser()
    return _parser


def extract_symbols(content: str, path: Path) -> List[Symbol]:
    return get_parser().parse(content, path)
