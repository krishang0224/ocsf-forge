#!/bin/sh
set -eu

bootstrap_status=$(curl --silent --show-error -o /tmp/bootstrap-response -w '%{http_code}' \
  -X POST http://lakekeeper:8181/management/v1/bootstrap \
  -H 'Content-Type: application/json' \
  --data '{"accept-terms-of-use":true}')
case "$bootstrap_status" in
  200|201|204|409) ;;
  400)
    grep -q '"type":"CatalogAlreadyBootstrapped"' /tmp/bootstrap-response || {
      cat /tmp/bootstrap-response
      exit 1
    }
    ;;
  *) cat /tmp/bootstrap-response; exit 1 ;;
esac

payload=$(printf '{"warehouse-name":"ulpf","project-id":"00000000-0000-0000-0000-000000000000","storage-profile":{"type":"s3","bucket":"lakehouse-warehouse","key-prefix":"ulpf","endpoint":"http://minio:9000","region":"us-east-1","path-style-access":true,"flavor":"s3-compat","sts-enabled":false},"storage-credential":{"type":"s3","credential-type":"access-key","access-key-id":"%s","secret-access-key":"%s"},"delete-profile":{"type":"hard"}}' "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD")
warehouse_status=$(curl --silent --show-error -o /tmp/warehouse-response -w '%{http_code}' \
  -X POST http://lakekeeper:8181/management/v1/warehouse \
  -H 'Content-Type: application/json' \
  --data "$payload")
case "$warehouse_status" in
  200|201|204|409) ;;
  400)
    grep -q '"type":"CreateWarehouseStorageProfileOverlap"' /tmp/warehouse-response || {
      cat /tmp/warehouse-response
      exit 1
    }
    ;;
  *) cat /tmp/warehouse-response; exit 1 ;;
esac

touch /tmp/ready
exec tail -f /dev/null
