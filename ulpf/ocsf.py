"""Class-specific projections of the normalized model into interchange JSON."""


def retain_context(record, names):
    context = {name: record.pop(name) for name in names if name in record}
    if context:
        record["unmapped"] = {"source_fields": record["unmapped"], "normalized_context": context}


def project_class(event, record):
    if event.class_uid == 2004:
        retain_context(record, ("src_endpoint", "dst_endpoint", "actor"))
