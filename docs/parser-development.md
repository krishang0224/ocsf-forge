# Parser development

Each source parser lives in `ulpf/parsing/` and implements the `LogParser` protocol from `base.py`:

```python
class VendorParser:
    name = "vendor_product"
    source_format = "vendor"
    version = "1.0.0"

    def detect(self, value: str) -> float:
        ...

    def parse(self, value: str, observed_at: datetime) -> dict:
        ...
```

`detect()` returns a confidence from `0.0` to `1.0`. It must be fast, deterministic, and side-effect free. `parse()` returns a dictionary consumed by `OCSFNormalizer`; set `_parsed` to `False` and include `parse_notes` when syntax is recognized but invalid.

Register the parser in `default_registry` in `ulpf/parsing/registry.py`. Use a narrow detector so it does not steal records from other formats. Increment `version` when output semantics change; raw and normalized tables retain parser name/version for reprocessing audits.

At minimum, tests should cover:

- a representative valid record;
- malformed input and required-field validation;
- delimiters, escaping, spaces, Unicode, and empty values;
- timestamp offsets and subsecond precision;
- an overlap case against the most similar existing parser;
- deterministic output for a fixed record and observation time.

Do not replace a missing or invalid source timestamp with ingestion time. A genuinely timestamp-less format may opt into observation time explicitly by returning `timestamp_missing_ok=True`; the normalizer records `time_source="collector"` so consumers can distinguish it.
