FROM docker.io/library/busybox:1.37.0-musl AS tools
FROM quay.io/lakekeeper/catalog:v0.13.1

COPY --from=tools /bin/busybox /bin/busybox
ENTRYPOINT ["/bin/busybox", "sh", "-c"]
CMD ["/home/nonroot/lakekeeper migrate && exec /home/nonroot/lakekeeper serve"]
