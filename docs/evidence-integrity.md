# Evidence hashes: what they prove

Each normalized input record already receives a SHA-256 digest in `OCSFNormalizer`. The raw, normalized and quarantine tables store it as `raw_payload_hash`; the raw and quarantine tables also retain the corresponding payload. Event IDs incorporate that digest plus the source identity and offset for replay deduplication.

This checks **consistency**, not authenticated provenance. A writer able to change both the payload and its digest can recompute the hash. There is no signed manifest, independent trusted timestamp, immutable object-retention policy or hash-chain guarantee in this project. A SHA-256 column by itself is not forensic chain of custody.

## Verify stored raw records

With an identity authorized to read raw evidence, run this Trino query:

```sql
SELECT event_id, source_id, source_offset
FROM iceberg.logging.raw_events
WHERE raw_payload_hash IS NULL
   OR raw_payload_hash <> lower(to_hex(sha256(to_utf8(raw_payload))))
LIMIT 100;
```

In the homelab SQL workspace, use DuckDB's string hash function:

```sql
SELECT event_id, source_id, source_offset
FROM raw_events
WHERE raw_payload_hash IS NULL
   OR raw_payload_hash <> sha256(raw_payload)
LIMIT 100;
```

Rows returned are mismatches requiring investigation. Zero rows means the checked payloads match their stored digests, not that the originating device, collector or database is trustworthy. The Trino analyst role intentionally cannot read `raw_events`; do not grant broader access just to run this query in an analyst console.

## Exact boundaries

The digest covers the UTF-8 representation of the retained **logical record**, not necessarily the uploaded file's original bytes. JSON arrays, CSV and XML documents are split and may be reserialized before normalization; Log4j continuation lines become one logical record. Invalid UTF-8 is represented safely as text, while original bytes are preserved separately in `metadata.raw_bytes_base64` for quarantine. A document-level legal evidence workflow needs an independently retained original file and digest, access controls and external audit records.

See [operations and backups](operations.md) and [production security](production-security.md). Do not advertise the existing raw-event store as cryptographically tamper-proof.
