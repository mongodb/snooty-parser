# RPC Methods

`language_server.py` utilizes RPC methods that the snooty parser uses to communicate with the VS Code extension.

## textDocument/resolve
Given an artifact's path relative to the project's source directory, return a corresponding source file path relative to the project's root.

### Parameters

| Parameter           | Description                                              |
| :------------------ | :------------------------------------------------------- |
|`fileName`: `str`    | Name of the target or directive to be resolved.          |
|`docPath`: `str`     | Path of the text document that `fileName` is found in.   |
|`resolveType`: `str` | Identifies how the method should resolve the `fileName`. |

Resolve types that are currently supported:
* `directive` - Given an `include`, `literalinclude`, or `figure` directive, the full path to the directive link is returned.
* `doc` - Given a `doc` role target, the full path to the target with a `.txt` extension is returned.

### Return
| Return Type | Description                                              |
| :---------- | :------------------------------------------------------- |
| `str`       | The full path of where the `fileName` should be located. |