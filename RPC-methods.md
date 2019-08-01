# RPC Methods

`language_server.py` utilizes RPC methods that the snooty parser uses to communicate with the VS Code extension.

## resolve
Given an artifact's path relative to the project's source directory, return a corresponding source file path relative to the project's root.

### Parameters

| Parameter           | Description                                              |
| :------------------ | :------------------------------------------------------- |
|`fileName`: `str`    | Name of the target or directive to be resolved.          |
|`docPath`: `str`     | Path of the text document that `fileName` is found in.   |
|`resolveType`: `str` | Identifies how the method should resolve the `fileName`. |

Resolve types that are currently supported:
* `directive`
* `doc`

### Return
| Return Type | Description                                              |
| :---------- | :------------------------------------------------------- |
| `str`       | The full path of where the `fileName` should be located. |