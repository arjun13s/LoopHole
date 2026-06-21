# duration parser

The public function is `parse_duration(text)`. It accepts compact strings like
`45m`, `2h`, and `1h30m` and returns total minutes. The test suite has multiple
failures, but the intended fix is one local parser change. Do not edit tests.
