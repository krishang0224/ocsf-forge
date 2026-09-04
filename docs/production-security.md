# Production security checklist

The Compose defaults are for a single-machine, loopback-only development environment. Lakekeeper logs a deliberate warning because authentication is disabled. Do not publish the services unchanged.

Before production:

1. Terminate TLS at every external boundary and configure HTTPS between clients, Trino, Lakekeeper, and object storage where the network is not fully trusted.
2. Configure Trino password, certificate, or OAuth 2.0 authentication and map authenticated principals to writer, dashboard, and analyst roles. Keep the file authorization policy or replace it with a centrally managed equivalent.
3. Configure Lakekeeper OIDC and its production authorizer. Remove anonymous bootstrap/catalog access after the initial administrator is established.
4. Replace root MinIO credentials with scoped service credentials delivered by a secrets manager. Rotate the database, catalog encryption, object-store, and identity-provider secrets.
5. Put the services on private networks. Expose only the reverse proxy or application endpoint; restrict database, catalog, Trino, Kafka, and MinIO administrative ports with firewall and network policy.
6. Encrypt persistent volumes and backups, define retention by data classification, and audit access to raw and quarantine evidence.
7. Send application, Trino, Lakekeeper, Kafka, MinIO, and PostgreSQL audit logs to a separate protected destination.
8. Scan and pin container images by digest in a controlled release pipeline, apply security updates, and test disaster recovery.

The repository cannot ship production OIDC client IDs, certificates, keys, network policy, or secret-manager bindings because they belong to the deployment environment. Treat those controls as release prerequisites, not optional application settings.
