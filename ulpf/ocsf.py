"""Class-specific projections of the normalized model into interchange JSON."""


def retain_context(record, names):
    context = {name: record.pop(name) for name in names if name in record}
    if context:
        original = record["unmapped"]
        if "normalized_context" in original:
            original = {"source_fields": original}
        record["unmapped"] = {**original, "normalized_context": context}


def project_class(event, record):
    if event.class_uid == 2004:
        retain_context(record, ("src_endpoint", "dst_endpoint", "actor"))
    elif event.class_uid == 3002:
        if event.user:
            record["user"] = {"name": event.user}
            record.pop("actor", None)
        service = (event.metadata or {}).get("service")
        if isinstance(service, str) and service:
            record["service"] = {"name": service}
    elif event.class_uid == 4002:
        retain_context(record, ("actor",))
        fields = event.metadata or {}
        code = fields.get("http_status")
        if type(code) is int:
            record["http_response"] = {"code": code}
            if type(fields.get("bytes")) is int:
                record["http_response"]["body_length"] = fields["bytes"]
