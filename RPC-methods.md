# RPC Methods

`language_server.py` utilizes RPC methods that the snooty parser uses to communicate with the VS Code extension.

## textDocument/get_page_ast

Given a .txt file, return the abstract syntax tree (AST) of the page that is created from parsing that file.

### Parameters

| Parameter | Description |
| :--- | :--- |
| `fileName`: `str` | Name of the current file the user is focused on in VS Code. |

### Return

| Return Type | Description |
| :--- | :--- |
| `SerializableType`: `Dict` or `None` | The AST of the page created by the parser. |

## textDocument/get_page_fileid

Given a path to a file, return its `FileId`. This method is used to let the extension and the driver know what the page is called.

### Parameters

| Parameter | Description |
| :--- | :--- |
| `filePath`: `str` | Path of the current file the user is focused on in VS Code. |

### Return

| Return Type | Description |
| :--- | :--- |
|`SerializableType`: `str` or `None` | The name of the file as represented by its stringified `FileId`. |

## textDocument/get_project_name

Uses the current project's `snooty.toml` file to return the name of the project.

### Return

| Return Type | Description |
| :--- | :--- |
| `SerializableType`: `str` or `None` | The `name` that can be found within the project's `snooty.toml` file. |

## textDocument/resolve

Given an artifact's path relative to the project's source directory, return a corresponding source file path relative to the project's root.

### Parameters

| Parameter | Description |
| :-- | :-- |
| `fileName`: `str` | Name of the target or directive to be resolved. |
| `docPath`: `str` | Path of the text document that `fileName` is found in. |
| `resolveType`: `str` | Identifies how the method should resolve the `fileName`. |

Resolve types that are currently supported:

- `directive` - Given an `include`, `literalinclude`, or `figure` directive, the full path to the directive link is returned.
- `doc` - Given a `doc` role target, the full path to the target with a `.txt` extension is returned.

### Return

| Return Type | Description |
| :--- | :--- |
| `SerializableType`: `str` or `None` | The full path of where the `fileName` should be located. |
