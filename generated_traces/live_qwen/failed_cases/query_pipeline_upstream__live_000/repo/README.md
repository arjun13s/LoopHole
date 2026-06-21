# query pipeline

The public function is `render_query(text)`. It tokenizes, parses, then formats.
The failing test checks final rendered output; do not assume the formatter is
the bug. Trace the data flow backward before patching.
